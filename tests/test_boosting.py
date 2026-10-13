"""Synthetic boosting tests; fixtures are not stock performance evidence."""

from copy import deepcopy

import numpy as np
import pytest
from test_regression import synthetic_source, training_rows

from marketpulse import boosting_models as models
from marketpulse.boosting_pipeline import build
from marketpulse.regression_pipeline import authority, saved_predict
from marketpulse.v2_runtime import Artifacts, environment


@pytest.mark.parametrize("family", ["xgboost", "lightgbm", "adaboost"])
def test_booster_replay_repeatability_missingness_and_input_only(tmp_path, family):
    artifacts = Artifacts(tmp_path / "artifacts")
    rows = training_rows()
    config = next(s for s in models.settings() if s["family"] == family)
    first = models.fit(rows, config, artifacts)
    second = models.fit(rows, config, artifacts)
    inputs = [{"input": r["input"], "news": r["news"]} for r in rows]
    predictions = models.predict(first, inputs, artifacts)
    assert np.array_equal(predictions, models.predict(second, inputs, artifacts))
    saved = artifacts.get(artifacts.put(first))
    assert np.array_equal(predictions, models.predict(saved, inputs, artifacts))
    assert np.isfinite(predictions).all()
    assert "xgboost" not in environment() and "lightgbm" not in environment()
    assert first["environment"] == models.model_environment()
    # Synthetic entirely-missing training column has train-fitted zero imputation.
    assert 0.0 in first["medians"]
    with pytest.raises(ValueError, match="training"):
        models.fit([{**rows[0], "role": "development"}], config, artifacts)
    invalid = deepcopy(first)
    invalid["environment"]["xgboost"] = "different"
    with pytest.raises(ValueError, match="incompatible"):
        models.predict(invalid, inputs, artifacts)
    bad_inputs = deepcopy(inputs)
    bad_inputs[0]["input"]["market"]["synthetic_market"] += 1
    with pytest.raises(ValueError, match="identity"):
        models.predict(first, bad_inputs, artifacts)
    if family != "adaboost":
        suffix = ".ubj" if family == "xgboost" else ".lgb"
        path = artifacts.binary_path(first["binary_hash"], suffix)
        path.write_bytes(path.read_bytes() + b"corrupt")  # corrupt private test artifact
        with pytest.raises(ValueError, match="digest"):
            models.predict(first, inputs, artifacts)
    else:
        invalid = deepcopy(first)
        invalid["weights"][0] = -1.0
        with pytest.raises(ValueError, match="weights"):
            models.predict(invalid, inputs, artifacts)


def test_adaboost_weighted_median_is_not_weighted_mean():
    trees = [
        {"left": [-1], "right": [-1], "feature": [-2], "threshold": [-2.0],
         "value": [v], "leaf": [True]} for v in (1.0, 2.0, 100.0)]
    assert models.weighted_median(trees, [1, 2, 1], np.zeros((2, 1))).tolist() == [2, 2]
    assert models.weighted_median(trees, [0, 0, 0], np.zeros((2, 1))).tolist() == [1, 1]
    with pytest.raises(ValueError, match="weights"):
        models.weighted_median(trees, [1, -2, 1], np.zeros((2, 1)))


def test_boosting_complete_receipts_and_resume_without_refitting(tmp_path, monkeypatch):
    source, root = tmp_path / "source", tmp_path / "boosting"
    release = synthetic_source(source)
    chosen = [next(s for s in models.settings() if s["family"] == family)
              for family in ("xgboost", "lightgbm", "adaboost")]
    monkeypatch.setattr(models, "settings", lambda: chosen)
    result = build(source, root, release, evidence="Synthetic boosting authorization")
    assert result["stage"] == "COMPLETE" and result["schema"] == models.MODEL_SCHEMA
    assert result["final_test_completed"] is False and result["paper_action_authorized"] is False
    authority(root, "release_hash", result["release_hash"])
    report = Artifacts(root / "artifacts").get(result["report_hash"])
    assert set(report["candidates"]) == {"xgboost", "lightgbm", "adaboost"}
    for candidate in report["candidates"].values():
        authority(root, "model_hash", candidate["model_hash"])
    output = saved_predict(
        root, source, result["release_hash"], report["selection_input_hashes"][0])
    assert output["outcomes_loaded"] is False and output["schema"] == models.MODEL_SCHEMA
    assert "target" not in output
    monkeypatch.setattr(models, "fit", lambda *a: pytest.fail("verified resume must not refit"))
    again = build(source, root, release, evidence="Synthetic boosting authorization")
    assert again == result and not (root / "v2-build.lock").exists()
    with pytest.raises(ValueError, match="separate"):
        build(source, source, release, evidence="Synthetic")


def test_boosting_rejects_existing_other_experiment(tmp_path):
    import json

    (tmp_path / "v2-status.json").write_text(json.dumps({"schema": "continuous-return-research/1"}))
    with pytest.raises(ValueError, match="another experiment"):
        build(tmp_path / "source", tmp_path, "unused", evidence="Synthetic")


def test_native_suffix_allowlist(tmp_path):
    artifacts = Artifacts(tmp_path)
    with pytest.raises(ValueError, match="unsupported"):
        artifacts.put_binary(b"executable", ".pkl")
    with pytest.raises(ValueError, match="unsupported"):
        artifacts.binary_path("0" * 64, ".pkl")
