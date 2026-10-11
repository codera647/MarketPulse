from __future__ import annotations

import json
from copy import deepcopy

import numpy as np
import pytest

from marketpulse import cli
from marketpulse.baseline_fixtures import generate_fixture_catalog
from marketpulse.baselines import (
    CLASSES,
    PRICE_FEATURES,
    _choose,
    fit_baselines,
    predict_baselines,
    run_baseline_demo,
    selected_rows,
    validate_features,
    validate_model,
    validation_report,
)
from marketpulse.features import FEATURE_NAMES, FEATURE_SCHEMA
from marketpulse.storage import RawStore, digest


@pytest.fixture(scope="module")
def inputs(tmp_path_factory):
    store = RawStore(tmp_path_factory.mktemp("baseline-inputs"))
    catalog_hash = generate_fixture_catalog(store)
    train, validation = selected_rows(store, catalog_hash)
    model = fit_baselines(train)
    return store, catalog_hash, train, validation, model


def rehash_features(features):
    features["feature_hash"] = digest({
        "schema": FEATURE_SCHEMA, "snapshot_hash": features["snapshot_hash"],
        "values": [features["values"][name] for name in FEATURE_NAMES],
    })


def test_fixture_builder_uses_shared_schema_and_fixed_splits(inputs):
    store, catalog_hash, train, validation, _ = inputs
    assert len(train) == 84
    assert len(validation) == 24
    assert len(store.get(catalog_hash)["rows"]) == 132
    assert max(row["session"] for row in train) < min(row["session"] for row in validation)
    assert set(row["label"] for row in train) == set(CLASSES)
    assert all(row["features"]["availability_tier"] == "FIXTURE" for row in train)
    assert all(row["features"]["feature_names"] == list(FEATURE_NAMES) for row in train)
    assert not any(name.startswith("news_") for name in PRICE_FEATURES)
    assert not any("outcome" in name for name in PRICE_FEATURES)


def test_training_reader_never_opens_final_test(inputs):
    store, catalog_hash, _, _, _ = inputs
    catalog = store.get(catalog_hash)
    withheld = {entry["row_hash"] for entry in catalog["rows"] if entry["split"] == "test"}
    opened = []

    class GuardedStore:
        def get(self, key):
            assert key not in withheld, "final-test artifact must remain unopened"
            opened.append(key)
            return store.get(key)

    train, validation = selected_rows(GuardedStore(), catalog_hash)
    assert len(train) + len(validation) == 108
    assert not withheld.intersection(opened)


def test_json_replay_returns_named_finite_probabilities_and_no_paper_action(inputs):
    _, _, _, validation, model = inputs
    detached = json.loads(json.dumps(model))
    for row in validation:
        predicted = predict_baselines(detached, row["features"])
        assert predicted["class_names"] == list(CLASSES)
        for baseline in ("majority", "price_only"):
            values = predicted[baseline]["probabilities"]
            assert len(values) == 3
            assert all(np.isfinite(value) and 0 <= value <= 1 for value in values)
            assert sum(values) == pytest.approx(1)
            assert predicted[baseline]["class"] in CLASSES
        assert predicted["calibrated"] is False
        assert predicted["paper_action_authorized"] is False


def test_majority_uses_training_frequency_and_neutral_tie_break(inputs):
    _, _, train, _, model = inputs
    assert model["majority"]["class"] == "NO_MATERIAL_MOVE"
    assert model["majority"]["probabilities"] == pytest.approx([1 / 3] * 3)
    assert model["training_counts"] == {label: len(train) // 3 for label in CLASSES}
    assert _choose([0.5, 0, 0.5]) == "DOWN"


def test_imputer_and_scaler_fit_train_only(inputs):
    _, _, train, validation, model = inputs
    x = np.array([[row["features"]["values"][name] for name in PRICE_FEATURES] for row in train])
    assert model["price_only"]["medians"] == pytest.approx(np.median(x, axis=0))
    assert model["price_only"]["means"] == pytest.approx(x.mean(axis=0))
    scales = x.std(axis=0)
    scales[scales == 0] = 1
    assert model["price_only"]["scales"] == pytest.approx(scales)
    changed = deepcopy(validation)
    for row in changed:
        row["features"]["values"][PRICE_FEATURES[0]] = 1000000
        row["label"] = "UP"
        rehash_features(row["features"])
    before = deepcopy(model)
    validation_report(model, train, changed)
    assert model == before
    assert fit_baselines(train) == model


def test_training_only_missing_value_imputation(inputs):
    _, _, train, validation, _ = inputs
    changed = deepcopy(train)
    feature = PRICE_FEATURES[0]
    changed[0]["features"]["values"][feature] = None
    rehash_features(changed[0]["features"])
    model = fit_baselines(changed)
    expected = np.median([row["features"]["values"][feature] for row in changed[1:]])
    assert model["price_only"]["medians"][0] == pytest.approx(expected)
    features = deepcopy(validation[0]["features"])
    features["values"][feature] = None
    rehash_features(features)
    assert sum(predict_baselines(model, features)["price_only"]["probabilities"]) == pytest.approx(
        1)
    for row in changed:
        row["features"]["values"][feature] = None
        rehash_features(row["features"])
    with pytest.raises(ValueError, match="all-missing"):
        fit_baselines(changed)


def test_matched_validation_counts_confusion_and_majority_hand_calculation(inputs):
    _, _, train, validation, model = inputs
    report = validation_report(model, train, validation)
    majority = report["metrics"]["majority"]
    assert report["validation_counts"] == {label: 8 for label in CLASSES}
    assert majority["accuracy"] == pytest.approx(1 / 3)
    assert majority["macro_f1"] == pytest.approx(1 / 6)
    assert majority["log_loss"] == pytest.approx(np.log(3))
    assert majority["multiclass_brier"] == pytest.approx(2 / 3)
    assert majority["confusion_matrix"] == [[0, 8, 0], [0, 8, 0], [0, 8, 0]]
    for metric in report["metrics"].values():
        assert sum(sum(row) for row in metric["confusion_matrix"]) == len(validation)
        assert sum(item["rows"] for item in metric["by_ticker"].values()) == len(validation)
    assert report["final_test_opened"] is False
    assert report["status"] == "FIXTURE_SOFTWARE_CHECK_ONLY"


def test_fit_and_evaluation_reject_wrong_split(inputs):
    _, _, train, validation, model = inputs
    with pytest.raises(ValueError, match="training rows only"):
        fit_baselines(train + validation)
    changed = deepcopy(validation)
    changed[0]["split"] = "test"
    with pytest.raises(ValueError, match="final test is locked"):
        validation_report(model, train, changed)


@pytest.mark.parametrize("fault", ["schema", "future_bar", "cutoff", "feature_hash",
                                  "nan", "boolean", "extra_outcome", "real_tier"])
def test_invalid_prediction_features_are_rejected(inputs, fault):
    _, _, _, validation, _ = inputs
    features = deepcopy(validation[0]["features"])
    if fault == "schema":
        features["feature_schema"] = "future/2"
    elif fault == "future_bar":
        features["source_bar_dates"][-1] = features["session"]
    elif fault == "cutoff":
        features["cutoff_utc"] = "2024-07-23T14:00:00Z"
    elif fault == "feature_hash":
        features["feature_hash"] = "0" * 64
    elif fault == "nan":
        features["values"][PRICE_FEATURES[0]] = float("nan")
    elif fault == "boolean":
        features["values"][PRICE_FEATURES[0]] = True
    elif fault == "extra_outcome":
        features["values"]["today_close"] = 123
    elif fault == "real_tier":
        features["availability_tier"] = "HISTORICAL_APPROXIMATE"
    with pytest.raises(ValueError):
        validate_features(features)


@pytest.mark.parametrize("fault", ["dimensions", "nan", "scale", "class_order", "action"])
def test_incompatible_model_cannot_score(inputs, fault):
    _, _, _, _, model = inputs
    value = deepcopy(model)
    if fault == "dimensions":
        value["price_only"]["coefficients"][0].pop()
    elif fault == "nan":
        value["price_only"]["intercepts"][0] = float("nan")
    elif fault == "scale":
        value["price_only"]["scales"][0] = 0
    elif fault == "class_order":
        value["class_names"].reverse()
    elif fault == "action":
        value["paper_action_authorized"] = True
    with pytest.raises(ValueError):
        validate_model(value)


@pytest.mark.parametrize("fault", ["date_split", "missing_stock", "real_catalog", "duplicate"])
def test_bad_fixture_catalog_blocks_training(inputs, fault, tmp_path):
    store, catalog_hash, _, _, _ = inputs
    catalog = deepcopy(store.get(catalog_hash))
    if fault == "date_split":
        catalog["rows"][0]["split"] = "validation"
    elif fault == "missing_stock":
        catalog["rows"].pop(0)
    elif fault == "real_catalog":
        catalog["availability_tier"] = "HISTORICAL_APPROXIMATE"
    elif fault == "duplicate":
        catalog["rows"].append(catalog["rows"][0])
    # The bad roster is rejected before any row content is requested.
    isolated = RawStore(tmp_path)
    bad_hash = isolated.put(catalog)
    with pytest.raises(ValueError):
        selected_rows(isolated, bad_hash)


def test_demo_runs_under_trailforge_and_reuses_known_run(tmp_path):
    first = run_baseline_demo(tmp_path)
    assert first["state"] == "COMPLETE"
    assert first["train_rows"] == 84
    assert first["validation_rows"] == 24
    assert first["availability_tier"] == "FIXTURE"
    assert first["final_test_opened"] is False
    assert first["trailforge_verify_receipt"].startswith("sha256:")
    assert run_baseline_demo(tmp_path) == first
    assert not (tmp_path / "marketpulse.sqlite3").exists()
    assert (tmp_path / "baseline-trailforge.sqlite3").is_file()
    assert (tmp_path / "baseline-jobs.sqlite3").is_file()
    store = RawStore(tmp_path / "baseline-artifacts")
    key = first["model_hash"]
    (store.root / key[:2] / f"{key}.json").unlink()
    with pytest.raises(OSError):
        run_baseline_demo(tmp_path)


def test_demo_cli_never_reads_credentials(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "load_alpaca_settings", lambda *args, **kwargs:
                        pytest.fail("synthetic baseline must not load credentials"))
    assert cli.main(["baseline-demo", "--data-dir", str(tmp_path), "--seed", "7"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "FIXTURE_SOFTWARE_CHECK_ONLY"
    assert result["paper_action_authorized"] is False
    assert cli.main(["baseline-demo", "--data-dir", str(tmp_path), "--seed", "-1"]) == 2


def test_model_missing_a_training_class_is_blocked(inputs):
    _, _, train, _, _ = inputs
    with pytest.raises(ValueError, match="per class"):
        fit_baselines([row for row in train if row["label"] != "UP"])


def test_altered_candidate_cannot_authorize_its_own_completion(tmp_path, monkeypatch):
    from marketpulse import baselines

    original = baselines.fit_baselines
    calls = []

    def altered_once(train):
        calls.append(True)
        model = original(train)
        if len(calls) == 1:
            model["majority"] = {"class": "DOWN", "probabilities": [0.5, 0.3, 0.2]}
        return model

    monkeypatch.setattr(baselines, "fit_baselines", altered_once)
    result = run_baseline_demo(tmp_path)
    assert result["state"] == "FAILED"
    assert len(calls) == 2
    assert not (tmp_path / "baseline-results").exists()


def test_uncertain_training_task_is_held_without_retry(tmp_path, monkeypatch):
    from marketpulse import baselines

    calls = []

    def uncertain(train):
        calls.append(True)
        raise TimeoutError("fixture uncertainty")

    monkeypatch.setattr(baselines, "fit_baselines", uncertain)
    first = run_baseline_demo(tmp_path)
    assert first["state"] == "WAITING_HUMAN"
    assert run_baseline_demo(tmp_path) == first
    assert len(calls) == 1
    assert not (tmp_path / "baseline-results").exists()
