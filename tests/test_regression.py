"""Synthetic regression verification; no examples here are market evidence."""

import json
from copy import deepcopy
from datetime import date
from decimal import Decimal

import numpy as np
import pytest

from marketpulse.clock import exchange_calendar, session_window, utc_iso
from marketpulse.constants import STOCKS
from marketpulse.labels import classify_return
from marketpulse.regression_models import evaluate, fit, predict, settings, tree_score
from marketpulse.regression_pipeline import (
    build,
    fit_score,
    reconcile_source,
    registered_source,
    saved_predict,
    source_rows,
)
from marketpulse.storage import digest
from marketpulse.v2_features import FEATURE_VERSION
from marketpulse.v2_runtime import Artifacts, check_receipt, supervised


def payload(session, symbol, row_hash, number):
    value = {
        "schema": FEATURE_VERSION, "session": session, "symbol": symbol,
        "cutoff_utc": utc_iso(session_window(date.fromisoformat(session)).cutoff),
        "base_row_hash": row_hash, "outcomes_loaded": False,
        "price": {"synthetic_price": float(np.sin(number))},
        "market": {"synthetic_market": float(number % 3), "missing": None},
        "meaning": {"synthetic_sentiment": float(np.cos(number))},
    }
    value["feature_hash"] = digest(value)
    return {"input": value, "news": []}


def training_rows():
    return [
        {"role": "train", "base_row_hash": digest(i), "input_hash": digest([i]),
         "session": "2020-01-02", "target": float(0.02 * np.sin(i)),
         **payload("2020-01-02", "AAPL", digest(i), i)} for i in range(90)
    ]


@pytest.mark.parametrize("family", ["linear", "ridge", "random_forest",
                                   "hist_gradient_boosting", "catboost"])
def test_regressor_saved_replay_and_input_only_inference(tmp_path, family):
    artifacts = Artifacts(tmp_path / "artifacts")
    rows = training_rows()
    config = next(s for s in settings() if s["family"] == family)
    model = fit(rows, config, artifacts)
    saved = artifacts.get(artifacts.put(model))
    inputs = [{"input": r["input"], "news": r["news"]} for r in rows]
    assert np.allclose(predict(model, rows, artifacts), predict(saved, inputs, artifacts))
    assert np.isfinite(predict(saved, inputs, artifacts)).all()
    bad = deepcopy(inputs)
    bad[0]["input"]["price"]["synthetic_price"] += 1
    with pytest.raises(ValueError, match="identity"):
        predict(saved, bad, artifacts)
    with pytest.raises(ValueError, match="training"):
        fit([{**r, "role": "development"} for r in rows], config, artifacts)


def test_fixed_boundary_metrics_and_zero_baseline():
    targets = [-0.02, -0.01, 0.0, 0.01, 0.02]
    perfect = evaluate(targets, targets)
    assert perfect["rmse"] == 0 and perfect["r_squared"] == 1
    assert perfect["derived_class_accuracy"] == 1
    assert perfect["per_class"]["NO_MATERIAL_MOVE"]["support"] == 3
    zero = evaluate(targets, [0.0] * 5)
    assert zero["derived_class_accuracy"] == 0.6
    assert zero["derived_class_balanced_accuracy"] == 1 / 3
    assert zero["mae_percentage_points"] == pytest.approx(1.2)
    assert evaluate([0.0], [0.0])["r_squared"] is None
    with pytest.raises(ValueError):
        evaluate(targets, [float("nan")] * 5)


def test_portable_tree_rejects_cycles_and_invalid_nodes():
    bad = {"left": [0], "right": [0], "feature": [0], "threshold": [0.0],
           "value": [0.0], "leaf": [False]}
    with pytest.raises(ValueError, match="cyclic"):
        tree_score(bad, np.zeros((2, 1)))
    bad["right"] = [2]
    with pytest.raises(ValueError, match="invalid"):
        tree_score(bad, np.zeros((2, 1)))


def synthetic_source(root):
    artifacts = Artifacts(root / "artifacts")
    originals, entries = [], []
    sessions = [f"{year}-01-02" for year in (2018, 2019, 2020, 2024)]
    sessions += ["2021-01-04", "2022-01-03", "2023-01-03"]
    sessions += [d.date().isoformat() for d in exchange_calendar().valid_days(
        start_date="2025-01-02", end_date="2025-01-20")][:10]
    for session in sorted(sessions):
        for i, symbol in enumerate(STOCKS):
            target = (-0.02, 0.0, 0.02)[i % 3]
            original = {
                "session": session, "symbol": symbol, "return_fraction": str(target),
                "threshold": "0.01", "price_convention": "regular-minute-proxy/1",
                "label": classify_return(Decimal(str(target)), Decimal("0.01")),
            }
            key = digest(original)
            originals.append({**original, "row_hash": key})
            entries.append({
                "session": session, "symbol": symbol, "base_row_hash": key,
                "role": "train" if session < "2025-01-01" else "development",
                "label": original["label"],
                "input_hash": artifacts.put(payload(session, symbol, key, i)),
            })
    base_hash = artifacts.put(originals)
    supervised(root, "base_rows", {"synthetic": True},
               lambda: {"base_rows_hash": base_hash}, lambda result: None)
    chunk = supervised(root, "dataset_chunk", {"synthetic": True},
                       lambda: {"chunk_hash": artifacts.put(entries)}, lambda result: None)
    dataset = {"rows": entries, "chunks": [chunk], "binding": {
        "feature_version": FEATURE_VERSION, "base_hash": base_hash,
    }}
    dataset_hash = artifacts.put(dataset)
    supervised(root, "dataset", {"synthetic": True},
               lambda: {"dataset_hash": dataset_hash}, lambda result: None)
    release = artifacts.put({
        "dataset_hash": dataset_hash, "evaluation_kind": "DEVELOPMENT_NOT_FINAL_TEST",
        "paper_action_authorized": False, "final_test_completed": False,
    })
    supervised(root, "release", {"synthetic": True},
               lambda: {"release_hash": release}, lambda result: None)
    return release


def test_source_targets_and_full_verified_regression_resume(tmp_path, monkeypatch):
    source, root = tmp_path / "source", tmp_path / "regression"
    release = synthetic_source(source)
    rows = source_rows(source, release)
    assert {r["target"] for r in rows} == {-0.02, 0.0, 0.02}
    chosen = [next(s for s in settings() if s["family"] == family) for family in
              ("linear", "ridge", "random_forest", "hist_gradient_boosting", "catboost")]
    monkeypatch.setattr("marketpulse.regression_pipeline.settings", lambda: chosen)
    result = build(source, root, release, evidence="Synthetic regression authorization")
    check_receipt(root, {k: result[k] for k in
                       ("release_hash", "run_id", "job_key", "binding_hash", "verify_receipt")})
    assert result["stage"] == "COMPLETE" and result["final_test_completed"] is False
    report = Artifacts(root / "artifacts").get(result["report_hash"])
    assert len(report["candidates"]) == 5 and len(report["metrics"]) == 7
    replay = saved_predict(
        root, source, result["release_hash"], report["selection_input_hashes"][0])
    assert replay["outcomes_loaded"] is False
    monkeypatch.setattr("marketpulse.regression_pipeline.fit",
                        lambda *args: pytest.fail("Completed regression must not refit"))
    assert build(source, root, release, evidence="Synthetic regression authorization") == result
    status = json.loads((root / "v2-status.json").read_text())
    assert status["stage"] == "COMPLETE" and not (root / "v2-build.lock").exists()
    with pytest.raises(ValueError, match="separate"):
        build(source, source, release, evidence="Synthetic regression authorization")


def test_fit_score_rejects_overlapping_dates(tmp_path):
    rows = training_rows()
    with pytest.raises(ValueError, match="chronology"):
        fit_score(tmp_path, rows, rows, settings()[0], "synthetic", lambda event: None)


def test_expired_source_recovery_keeps_unknown_and_checks_complete_targets(tmp_path):
    import time

    from trailforge.core import ConflictError
    from trailforge.runtime import Harness

    from marketpulse.regression_models import REGRESSION_SCHEMA
    from marketpulse.storage import ExtractionStore
    from marketpulse.v2_runtime import environment

    source, root = tmp_path / "source", tmp_path / "regression"
    release = synthetic_source(source)
    artifacts = Artifacts(root / "artifacts")
    rows = source_rows(source, release)
    candidate = artifacts.put(rows)
    binding = {
        "schema": REGRESSION_SCHEMA, "source_release_hash": release,
        "evidence": "Synthetic expired authorization", "configurations": settings(),
        "feature_version": FEATURE_VERSION,
    }
    calls = []

    def expire():
        calls.append(1)
        time.sleep(0.02)
        return {"rows_hash": candidate}

    with pytest.raises(ConflictError):
        supervised(root, "regression_source", binding, expire, lambda result: None, lease=0.001)
    key = digest({
        "stage": "regression_source", "binding": {**binding, "environment": environment()},
    })
    with pytest.raises(ValueError, match="explicit recovery"):
        registered_source(root, binding)
    with pytest.raises(ValueError, match="incomplete"):
        reconcile_source(source, root, key, artifacts.put(rows[:-6]), evidence="Synthetic check")
    altered = deepcopy(rows)
    altered[0]["target"] += 0.1
    with pytest.raises(ValueError, match="held"):
        reconcile_source(source, root, key, artifacts.put(altered), evidence="Synthetic check")
    result = reconcile_source(source, root, key, candidate, evidence="Synthetic independent check")
    check_receipt(root, result)
    assert registered_source(root, binding) == result and calls == [1]
    job = ExtractionStore(root / "v2-jobs.sqlite3").get_job(key)
    native = Harness(root / "v2-trailforge.sqlite3", tenant_id="local-demo",
                     resource_id=f"marketpulse:v2:{key}", adapters=[],
                     tenant_limit=1000000, global_limit=10000000).inspect(job["run_id"])
    assert native["state"] == "WAITING_HUMAN" and native["units_reserved"] == 1
    assert native["tasks"]["execute"]["attempts"] == 1
    assert native["tasks"]["execute"]["error_code"] == "EXPIRED_ATTEMPT"
