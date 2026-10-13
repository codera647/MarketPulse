"""Synthetic price-expert correctness checks, not evidence of forecasting skill."""

from copy import deepcopy
from datetime import date

import numpy as np
import pytest
from test_regression import synthetic_source

from marketpulse import price_expert_models as models
from marketpulse.baselines import CLASSES
from marketpulse.clock import session_window, utc_iso
from marketpulse.constants import STOCKS
from marketpulse.price_expert_pipeline import build, reuse_roster, saved_predict
from marketpulse.regression_pipeline import authority, bounded_source
from marketpulse.storage import digest
from marketpulse.v2_features import FEATURE_VERSION
from marketpulse.v2_pipeline import _fit_and_score
from marketpulse.v2_runtime import Artifacts


def payload(session, symbol, row_hash, number):
    value = {
        "schema": FEATURE_VERSION,
        "session": session,
        "symbol": symbol,
        "base_row_hash": row_hash,
        "outcomes_loaded": False,
        "cutoff_utc": utc_iso(session_window(date.fromisoformat(session)).cutoff),
        "price": {
            **{n: float(np.sin(number)) for n in models.PRICE_NAMES},
            "spy_prior_return_1d": 0.2,
        },
        "market": {
            **{f"company_{s}": int(symbol == s) for s in STOCKS},
            **{n: (None if n == "premarket_return" else 1.0) for n in models.PREMARKET_NAMES},
            "sector_return_1d": 0.5,
        },
        "meaning": {"news_sentiment_positive": 0.7},
    }
    value["feature_hash"] = digest(value)
    return {"input": value, "news": []}


def rows(session="2020-01-02", role="train"):
    return [
        {
            "role": role,
            "base_row_hash": digest([session, i]),
            "input_hash": digest([session, i, 1]),
            "session": session,
            "symbol": STOCKS[i % len(STOCKS)],
            "label": CLASSES[i % 3],
            **payload(session, STOCKS[i % len(STOCKS)], digest([session, i]), i),
        }
        for i in range(90)
    ]


def test_price_feature_whitelist_and_cutoff():
    assert len(models.FEATURE_NAMES) == 20 and len(models.settings()) == 8
    assert not any(n.startswith(("spy_", "sector_", "news_")) for n in models.FEATURE_NAMES)
    inputs = rows()
    matrix = models.numeric(inputs)
    assert matrix.shape == (90, 20) and np.isnan(matrix).any()
    changed = deepcopy(inputs)
    for r in changed:
        r["input"]["meaning"] = {"news_sentiment_positive": -1000}
        r["input"]["price"]["spy_prior_return_1d"] = 9999
        r["input"]["market"]["sector_return_1d"] = -9999
        r["input"]["feature_hash"] = digest(
            {k: v for k, v in r["input"].items() if k != "feature_hash"}
        )
        r["news"] = [{"headline": "This must not reach the price expert"}]
    assert np.allclose(matrix, models.numeric(changed), equal_nan=True)
    changed[0]["input"]["price"][models.PRICE_NAMES[0]] += 1
    with pytest.raises(ValueError, match="identity"):
        models.numeric(changed)
    bad = deepcopy(inputs)
    bad[0]["input"]["cutoff_utc"] = "2020-01-02T15:00:00Z"
    bad[0]["input"]["feature_hash"] = digest(
        {k: v for k, v in bad[0]["input"].items() if k != "feature_hash"}
    )
    with pytest.raises(ValueError, match="cutoff"):
        models.numeric(bad)


@pytest.mark.parametrize("family", ["logistic", "catboost", "xgboost"])
def test_saved_price_probability_replay_and_no_labels(tmp_path, family):
    artifacts = Artifacts(tmp_path / "artifacts")
    training = rows()
    config = next(c for c in models.settings() if c["family"] == family)
    model = models.fit(training, config, artifacts)
    saved = artifacts.get(artifacts.put(model))
    inputs = [{"input": r["input"]} for r in training]
    probabilities = models.predict(saved, inputs, artifacts)
    assert np.allclose(probabilities, models.predict(model, training, artifacts))
    assert np.allclose(np.sum(probabilities, axis=1), 1)
    calibration = rows("2021-01-04", "calibration")
    calibrated = models.calibrate(saved, calibration, artifacts)
    assert calibrated["calibration_rows"] == [r["base_row_hash"] for r in calibration]
    with pytest.raises(ValueError, match="training roles"):
        models.fit(calibration, config, artifacts)
    with pytest.raises(ValueError, match="follow"):
        models.calibrate(saved, [{**r, "role": "calibration"} for r in training], artifacts)
    second = models.fit(training, config, artifacts)
    assert np.allclose(probabilities, models.predict(second, inputs, artifacts), atol=1e-12)


def test_price_fit_rejects_leaking_calibration(tmp_path):
    with pytest.raises(ValueError, match="calibration must"):
        _fit_and_score(
            tmp_path,
            rows(),
            rows("2022-01-03", "selection"),
            models.settings()[0],
            lambda event: None,
            calibration=rows("2023-01-03", "calibration"),
            model_api=models,
        )


def test_complete_price_receipts_saved_inference_and_resume(tmp_path, monkeypatch):
    monkeypatch.setattr("test_regression.payload", payload)
    source, roster_root, root = tmp_path / "source", tmp_path / "roster", tmp_path / "price"
    release = synthetic_source(source)
    proof = bounded_source(source, roster_root, release, lambda event: None)
    assert len(reuse_roster(source, roster_root, release, proof["rows_hash"])) == 102
    chosen = [
        next(c for c in models.settings() if c["family"] == family)
        for family in ("logistic", "catboost", "xgboost")
    ]
    monkeypatch.setattr(models, "settings", lambda: chosen)
    result = build(source, roster_root, root, release, proof["rows_hash"], evidence="Synthetic")
    assert result["stage"] == "COMPLETE" and result["fits_complete"] == 12
    assert result["final_test_completed"] is False
    authority(root, "release_hash", result["release_hash"])
    report = Artifacts(root / "artifacts").get(result["report_hash"])
    assert set(report["candidates"]) == {"logistic", "catboost", "xgboost"}
    for outcome in report["candidates"].values():
        authority(root, "model_hash", outcome["model_hash"])
    output = saved_predict(
        root, source, result["release_hash"], report["selection_input_hashes"][0]
    )
    assert output["outcomes_loaded"] is False and set(output["probabilities"]) == set(CLASSES)
    monkeypatch.setattr(models, "fit", lambda *a: pytest.fail("verified resume must not refit"))
    assert (
        build(source, roster_root, root, release, proof["rows_hash"], evidence="Synthetic")
        == result
    )
    assert not (root / "v2-build.lock").exists()
    with pytest.raises(ValueError, match="binding differs"):
        build(source, roster_root, root, release, proof["rows_hash"], evidence="Different")
    with pytest.raises(ValueError, match="matching positive"):
        reuse_roster(source, roster_root, "0" * 64, proof["rows_hash"])
    with pytest.raises(ValueError, match="separate"):
        build(source, roster_root, roster_root, release, proof["rows_hash"], evidence="Synthetic")
