"""Synthetic specialist isolation/replay checks; no claimed market accuracy."""

from copy import deepcopy

import numpy as np
import pytest
from test_price_expert import payload as price_payload
from test_price_expert import rows as price_rows
from test_regression import synthetic_source

from marketpulse.context_expert_models import NEWS_NAMES, SECTOR_NAMES, SPY_NAMES, ExpertAPI
from marketpulse.price_expert_pipeline import build, saved_predict
from marketpulse.regression_pipeline import authority, bounded_source
from marketpulse.storage import digest
from marketpulse.v2_news import MODEL_SPEC
from marketpulse.v2_runtime import Artifacts, supervised


def payload(session, symbol, row_hash, number):
    result = price_payload(session, symbol, row_hash, number)
    value = result["input"]
    value["meaning"] = {n: float(abs(np.sin(number))) for n in NEWS_NAMES}
    for n in ("numeric_earnings_surprise", "scheduled_earnings_today"):
        value["meaning"][n] = None
    value["price"].update({n: 0.01 for n in SPY_NAMES})
    value["market"].update({n: 0.02 for n in SECTOR_NAMES})
    value["feature_hash"] = digest({k: v for k, v in value.items() if k != "feature_hash"})
    return result


def rows(session="2020-01-02", role="train"):
    result = price_rows(session, role)
    for i, r in enumerate(result):
        r.update(payload(session, r["symbol"], r["base_row_hash"], i))
    return result


@pytest.mark.parametrize("expert", ["news", "market"])
def test_specialist_isolation_and_missingness(expert):
    api = ExpertAPI(expert)
    examples = rows()
    expected = api.numeric(examples)
    assert expected.shape == (90, 24 if expert == "news" else 22)
    assert len(api.settings()) == (4 if expert == "news" else 8)
    altered = deepcopy(examples)
    for r in altered:
        if expert == "news":
            r["input"]["price"] = {"forbidden_price": 9999}
            for n in tuple(r["input"]["market"]):
                if not n.startswith("company_"):
                    r["input"]["market"][n] = -9999
        else:
            r["input"]["meaning"] = {"forbidden_sentiment": 9999}
            for n in tuple(r["input"]["market"]):
                if n.startswith("premarket_"):
                    r["input"]["market"][n] = 9999
            r["input"]["price"]["prior_volume_mean_5d"] = -9999
        r["input"]["feature_hash"] = digest(
            {k: v for k, v in r["input"].items() if k != "feature_hash"}
        )
        r["news"] = [{"headline": "No raw text model in this experiment"}]
    assert np.allclose(expected, api.numeric(altered), equal_nan=True)
    altered[0]["input"]["outcomes_loaded"] = True
    with pytest.raises(ValueError, match="identity"):
        api.numeric(altered)
    missing = deepcopy(examples)
    for r in missing:
        if expert == "news":
            for n in ("positive", "negative", "neutral"):
                r["input"]["meaning"][f"news_sentiment_{n}"] = None
        else:
            r["input"]["market"]["sector_return_1d"] = None
        r["input"]["feature_hash"] = digest(
            {k: v for k, v in r["input"].items() if k != "feature_hash"}
        )
    assert np.isnan(api.numeric(missing)).any()


@pytest.mark.parametrize(
    "expert,family", [("news", "logistic"), ("market", "logistic"), ("market", "lightgbm")]
)
def test_saved_context_probability_replay_repeatability_and_roles(tmp_path, expert, family):
    api, artifacts = ExpertAPI(expert), Artifacts(tmp_path / "artifacts")
    training = rows()
    config = next(c for c in api.settings() if c["family"] == family)
    model = api.fit(training, config, artifacts)
    saved = artifacts.get(artifacts.put(model))
    inputs = [{"input": r["input"]} for r in training]
    expected = api.predict(model, training, artifacts)
    assert np.allclose(expected, api.predict(saved, inputs, artifacts))
    assert np.allclose(np.sum(expected, axis=1), 1)
    second = api.fit(training, config, artifacts)
    assert np.allclose(expected, api.predict(second, inputs, artifacts), atol=1e-12)
    calibrated = api.calibrate(saved, rows("2021-01-04", "calibration"), artifacts)
    assert len(calibrated["calibration_rows"]) == 90
    if expert == "news":
        assert saved["finbert_spec"] == MODEL_SPEC
    with pytest.raises(ValueError, match="training roles"):
        api.fit(rows("2021-01-04", "calibration"), config, artifacts)
    with pytest.raises(ValueError, match="follow"):
        api.calibrate(model, rows("2020-01-02", "calibration"), artifacts)
    bad = deepcopy(saved)
    bad["temperature"] = float("nan")
    with pytest.raises(ValueError, match="temperature"):
        api.predict(bad, inputs, artifacts)
    other = ExpertAPI("news" if expert == "market" else "market")
    with pytest.raises(ValueError, match="identity"):
        other.predict(saved, inputs, artifacts)


@pytest.mark.parametrize("expert", ["news", "market"])
def test_context_complete_native_receipts_and_resume(tmp_path, monkeypatch, expert):
    monkeypatch.setattr("test_regression.payload", payload)
    api = ExpertAPI(expert)
    source, roster_root, root = tmp_path / "source", tmp_path / "roster", tmp_path / expert
    release = synthetic_source(source)
    if expert == "news":
        store = Artifacts(source / "artifacts")
        release = store.put({**store.get(release), "finbert_spec": MODEL_SPEC})
        supervised(
            source,
            "context_source_release",
            {"synthetic": True},
            lambda: {"release_hash": release},
            lambda result: None,
        )
    proof = bounded_source(source, roster_root, release, lambda event: None)
    families = ("logistic",) if expert == "news" else ("logistic", "lightgbm")
    configs = [next(c for c in api.settings() if c["family"] == family) for family in families]
    monkeypatch.setattr(api, "settings", lambda: configs)
    result = build(
        source, roster_root, root, release, proof["rows_hash"], evidence="Synthetic", model_api=api
    )
    assert result["stage"] == "COMPLETE" and result["fits_complete"] == len(families) * 4
    assert result["schema"] == api.SCHEMA and not result["final_test_completed"]
    authority(root, "release_hash", result["release_hash"])
    report = Artifacts(root / "artifacts").get(result["report_hash"])
    assert set(report["candidates"]) == set(families)
    for outcome in report["candidates"].values():
        authority(root, "model_hash", outcome["model_hash"])
    output = saved_predict(
        root, source, result["release_hash"], report["selection_input_hashes"][0], model_api=api
    )
    assert output["outcomes_loaded"] is False and sum(
        output["probabilities"].values()
    ) == pytest.approx(1)
    monkeypatch.setattr(api, "fit", lambda *a: pytest.fail("verified resume must not refit"))
    assert (
        build(
            source,
            roster_root,
            root,
            release,
            proof["rows_hash"],
            evidence="Synthetic",
            model_api=api,
        )
        == result
    )
    assert not (root / "v2-build.lock").exists()
