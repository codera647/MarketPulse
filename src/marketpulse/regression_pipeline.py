"""Separate verified regression experiment; never edits classification releases."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import date
from decimal import Decimal
from pathlib import Path

import numpy as np

from marketpulse.clock import session_window, utc_iso
from marketpulse.constants import STOCKS
from marketpulse.labels import classify_return
from marketpulse.real_training import validation_segments
from marketpulse.regression_models import REGRESSION_SCHEMA, evaluate, fit, predict, settings
from marketpulse.storage import ExtractionStore, digest
from marketpulse.v2_features import FEATURE_VERSION
from marketpulse.v2_models import fold_rosters
from marketpulse.v2_runtime import (
    Artifacts,
    check_receipt,
    environment,
    owned_run,
    reconciliation_store,
    retained_expired,
    supervised,
)


def authority(root: Path, field: str, value: str) -> dict:
    with ExtractionStore(root / "v2-jobs.sqlite3").connect() as db:
        records = [json.loads(r[0]) for r in db.execute(
            "SELECT manifest_json FROM extraction_jobs WHERE status='COMPLETE' "
            "AND manifest_json IS NOT NULL")]
    matching = [r for r in records if r.get(field) == value]
    if len(matching) != 1:
        raise ValueError("artifact has no unique positive verification authority")
    check_receipt(root, matching[0])
    return matching[0]


def source_catalog(source: Path, release_hash: str) -> tuple[dict, dict]:
    authority(source, "release_hash", release_hash)
    artifacts = Artifacts(source / "artifacts")
    release = artifacts.get(release_hash)
    if (release.get("evaluation_kind") != "DEVELOPMENT_NOT_FINAL_TEST"
            or release.get("paper_action_authorized") is not False
            or release.get("final_test_completed") is not False):
        raise ValueError("source must be a verified unpromoted v2 development release")
    authority(source, "dataset_hash", release["dataset_hash"])
    dataset = artifacts.get(release["dataset_hash"])
    binding = dataset["binding"]
    if binding["feature_version"] != FEATURE_VERSION:
        raise ValueError("unsupported source features")
    authority(source, "base_rows_hash", binding["base_hash"])
    for chunk in dataset["chunks"]:
        check_receipt(source, chunk)
    original = artifacts.get(binding["base_hash"])
    originals = {r["row_hash"]: r for r in original}
    if len(originals) != len(original) or len(dataset["rows"]) != len(original):
        raise ValueError("source roster size/uniqueness differs")
    return dataset, originals


def project_rows(source: Path, entries: list[dict], originals: dict) -> list[dict]:
    artifacts = Artifacts(source / "artifacts")
    rows = []
    for entry in entries:
        row = originals[entry["base_row_hash"]]
        if row["row_hash"] != digest({k: v for k, v in row.items() if k != "row_hash"}):
            raise ValueError("original target row identity differs")
        session, symbol = entry["session"], entry["symbol"]
        identity = (session, symbol)
        if (symbol not in STOCKS or identity != (row["session"], row["symbol"])
                or entry["role"] not in {"train", "development"}
                or not "2018-01-01" <= session <= "2025-12-31"
                or (entry["role"] == "train") != (session < "2025-01-01")
                or row["price_convention"] != "regular-minute-proxy/1"
                or Decimal(row["threshold"]) != Decimal("0.01")):
            raise ValueError("regression source scope/target convention differs")
        movement = Decimal(row["return_fraction"])
        if (not movement.is_finite() or movement <= -1
                or classify_return(movement, Decimal("0.01")) != entry["label"]
                or entry["label"] != row["label"]):
            raise ValueError("continuous target disagrees with audited classification")
        payload = artifacts.get(entry["input_hash"])
        value = payload["input"]
        cutoff = utc_iso(session_window(date.fromisoformat(session)).cutoff)
        if (set(payload) != {"input", "news"} or value["schema"] != FEATURE_VERSION
                or value["outcomes_loaded"] is not False
                or (value["session"], value["symbol"]) != identity
                or value["base_row_hash"] != entry["base_row_hash"]
                or value["cutoff_utc"] != cutoff):
            raise ValueError("regression input identity/cutoff differs")
        rows.append({**entry, "target": float(movement)})
    return rows


def complete_roster(rows: list[dict]):
    groups, seen = defaultdict(set), set()
    for row in rows:
        identity = (row["session"], row["symbol"])
        if identity in seen:
            raise ValueError("duplicate regression company-date")
        seen.add(identity)
        groups[row["session"]].add(row["symbol"])
    if any(group != set(STOCKS) for group in groups.values()):
        raise ValueError("incomplete regression company-date group")


def source_rows(source: Path, release_hash: str) -> list[dict]:
    dataset, originals = source_catalog(source, release_hash)
    rows = project_rows(source, dataset["rows"], originals)
    complete_roster(rows)
    return rows


def bounded_source(source: Path, root: Path, release_hash: str, checkpoint,
                   *, parent_key=None, candidate_hash=None) -> dict:
    # Read-only authority/catalog preflight is outside any bounded attempt.
    dataset, originals = source_catalog(source, release_hash)
    artifacts = Artifacts(root / "artifacts")
    candidate = artifacts.get(candidate_hash) if candidate_hash else None
    if candidate is not None and len(candidate) != len(dataset["rows"]):
        raise ValueError("expired regression roster is incomplete")
    results = []
    for start in range(0, len(dataset["rows"]), 300):
        entries = dataset["rows"][start:start + 300]
        checkpoint({"schema": REGRESSION_SCHEMA, "stage": "VERIFYING_REGRESSION_CHUNKS",
                    "rows_complete": start, "rows_total": len(dataset["rows"])})
        binding = {
            "schema": REGRESSION_SCHEMA, "source_validator": "bounded-300/2",
            "source_release_hash": release_hash, "source_binding": dataset["binding"],
            "roster_hash": artifacts.put(entries), "parent_job_key": parent_key,
            "candidate_rows_hash": candidate_hash, "offset": start,
        }

        def execute():
            rows = (candidate[start:start + 300] if candidate is not None
                    else project_rows(source, entries, originals))
            return {"chunk_hash": artifacts.put(rows)}

        def verify(result):
            if artifacts.get(result["chunk_hash"]) != project_rows(source, entries, originals):
                raise ValueError("independent bounded regression target/input replay differs")

        results.append(supervised(root, "regression_source_chunk", binding, execute, verify))
    assembled = []
    for result in results:
        check_receipt(root, result)
        assembled.extend(artifacts.get(result["chunk_hash"]))
    complete_roster(assembled)
    rows_hash = artifacts.put(assembled)
    if candidate_hash and rows_hash != candidate_hash:
        raise ValueError("reconciled whole regression roster differs")
    receipt_hash = artifacts.put(results)

    def verify_assembly(result):
        for value in results:
            check_receipt(root, value)
        if result["rows_hash"] != rows_hash or artifacts.get(rows_hash) != assembled:
            raise ValueError("regression source assembly differs")

    return supervised(
        root, "regression_source_assembly",
        {"source_release_hash": release_hash, "receipts_hash": receipt_hash,
         "parent_job_key": parent_key, "rows_hash": rows_hash},
        lambda: {"rows_hash": rows_hash}, verify_assembly,
    )


def reconcile_source(source: Path, root: Path, parent_key: str, candidate_hash: str,
                     *, evidence: str, progress=None) -> dict:
    if not isinstance(evidence, str) or not 1 <= len(evidence.strip()) <= 500:
        raise ValueError("bounded explicit regression source reconciliation evidence required")
    job, _record, original = retained_expired(root, parent_key, "regression_source")
    if original["schema"] != REGRESSION_SCHEMA or original["configurations"] != settings():
        raise ValueError("expired regression source specification differs")
    result = bounded_source(source, root, original["source_release_hash"],
                            progress or (lambda event: None), parent_key=parent_key,
                            candidate_hash=candidate_hash)
    binding = {"parent_job_key": parent_key, "parent_run_id": job["run_id"],
               "rows_hash": candidate_hash, "assembly": result, "evidence": evidence,
               "original_adapter_reexecuted": False}

    def verify(value):
        retained_expired(root, parent_key, "regression_source")
        check_receipt(root, result)
        if value["rows_hash"] != candidate_hash:
            raise ValueError("reconciliation roster identity differs")

    reconciled = supervised(
        root, "regression_source_reconciliation", binding,
        lambda: {"rows_hash": candidate_hash, "original_held_run": job["run_id"],
                 "original_adapter_reexecuted": False}, verify,
    )
    with reconciliation_store(root).connect() as db:
        prior = db.execute("SELECT result_json FROM v2_capture_reconciliations "
                           "WHERE parent_job_key=?", (parent_key,)).fetchone()
        if prior and json.loads(prior[0]) != reconciled:
            raise ValueError("regression source recovery already has different evidence")
        db.execute("INSERT OR IGNORE INTO v2_capture_reconciliations VALUES (?,?)",
                   (parent_key, json.dumps(reconciled, sort_keys=True)))
    return reconciled


def registered_source(root: Path, binding: dict) -> dict | None:
    key = digest({
        "stage": "regression_source", "binding": {**binding, "environment": environment()},
    })
    with reconciliation_store(root).connect() as db:
        row = db.execute("SELECT result_json FROM v2_capture_reconciliations "
                         "WHERE parent_job_key=?", (key,)).fetchone()
    if row is None:
        original = ExtractionStore(root / "v2-jobs.sqlite3").get_job(key)
        if original and original["run_id"]:
            raise ValueError("original regression source requires explicit recovery; never reset")
        return None
    result = json.loads(row[0])
    check_receipt(root, result)
    retained_expired(root, key, "regression_source")
    return result


def hydrate(source: Path, rows: list[dict]) -> list[dict]:
    artifacts = Artifacts(source / "artifacts")
    return [{**r, **artifacts.get(r["input_hash"])} for r in rows]


def fit_score(root: Path, train: list[dict], evaluation: list[dict], config: dict,
              phase: str, checkpoint, *, model_api=None) -> dict:
    artifacts = Artifacts(root / "artifacts")
    schema = model_api.MODEL_SCHEMA if model_api else REGRESSION_SCHEMA
    fit_model = model_api.fit if model_api else fit
    predict_model = model_api.predict if model_api else predict
    if (not train or not evaluation
            or max(r["session"] for r in train) >= min(r["session"] for r in evaluation)
            or {r["base_row_hash"] for r in train} & {r["base_row_hash"] for r in evaluation}):
        raise ValueError("regression chronology/row separation failed")
    binding = {
        "schema": schema, "config": config, "phase": phase,
        "train_hash": artifacts.put([
            {k: r[k] for k in ("base_row_hash", "input_hash", "target")} for r in train]),
        "evaluation_hash": artifacts.put([
            {k: r[k] for k in ("base_row_hash", "input_hash", "target")} for r in evaluation]),
        "feature_version": FEATURE_VERSION,
    }
    if model_api:
        binding["model_environment"] = model_api.model_environment()

    def execute():
        checkpoint({"schema": schema, "stage": "TRAINING_REGRESSION",
                    "family": config["family"], "phase": phase, "train_rows": len(train)})
        model_hash = artifacts.put(fit_model(train, config, artifacts))
        values = predict_model(artifacts.get(model_hash), evaluation, artifacts)
        prediction_hash = artifacts.put({
            "model_hash": model_hash, "input_hashes": [r["input_hash"] for r in evaluation],
            "return_fractions": values,
        })
        report_hash = artifacts.put({
            "model_hash": model_hash, "prediction_hash": prediction_hash, "binding": binding,
            "metrics": evaluate([r["target"] for r in evaluation], values),
        })
        return {"model_hash": model_hash, "prediction_hash": prediction_hash,
                "report_hash": report_hash}

    def verify(result):
        model = artifacts.get(result["model_hash"])
        if (model["training_rows"] != [r["base_row_hash"] for r in train]
                or model["config"] != config):
            raise ValueError("saved regression training identity differs")
        replay = predict_model(model, evaluation, artifacts)
        saved = artifacts.get(result["prediction_hash"])
        expected_report = {
            "model_hash": result["model_hash"], "prediction_hash": result["prediction_hash"],
            "binding": binding, "metrics": evaluate([r["target"] for r in evaluation], replay),
        }
        if (saved["model_hash"] != result["model_hash"]
                or saved["input_hashes"] != [r["input_hash"] for r in evaluation]
                or not np.allclose(saved["return_fractions"], replay, atol=1e-12, rtol=1e-10)
                or artifacts.get(result["report_hash"]) != expected_report):
            raise ValueError("independent saved regression replay differs")

    return supervised(root, "regression_fit", binding, execute, verify)


def train(root: Path, source: Path, rows: list[dict], source_release: str, checkpoint,
          *, model_api=None) -> dict:
    artifacts = Artifacts(root / "artifacts")
    schema = model_api.MODEL_SCHEMA if model_api else REGRESSION_SCHEMA
    train_rows = hydrate(source, [r for r in rows if r["role"] == "train"])
    development = [r for r in rows if r["role"] == "development"]
    reserved, selection = validation_segments(development)
    selection = hydrate(source, selection)
    folds, configurations, search = (
        fold_rosters(train_rows), model_api.settings() if model_api else settings(), [])
    for i, config in enumerate(configurations):
        outcomes = []
        for j, (fitting, evaluating) in enumerate(folds):
            checkpoint({"schema": schema, "stage": "REGRESSION_CROSS_VALIDATING",
                        "candidate_index": i + 1, "candidates_total": len(configurations),
                        "fold": j + 1})
            outcomes.append(fit_score(
                root, fitting, evaluating, config, f"fold_{j + 1}", checkpoint,
                model_api=model_api))
        scores = [artifacts.get(r["report_hash"])["metrics"] for r in outcomes]
        search.append({
            "config": config, "folds": outcomes,
            "mean_rmse": float(np.mean([s["rmse"] for s in scores])),
            "mean_mae": float(np.mean([s["mae"] for s in scores])),
        })
    chosen = {}
    for entry in search:
        family = entry["config"]["family"]
        candidates = [r for r in search if r["config"]["family"] == family]
        chosen[family] = min(candidates, key=lambda r: (
            r["mean_rmse"], r["mean_mae"], digest(r["config"])))
    finals = {family: fit_score(root, train_rows, selection, entry["config"],
                               "2025_selection", checkpoint, model_api=model_api)
              for family, entry in chosen.items()}
    metrics = {name: artifacts.get(result["report_hash"])["metrics"]
               for name, result in finals.items()}
    mean = float(np.mean([r["target"] for r in train_rows]))
    for name, value in (("zero_return", 0.0), ("training_mean_return", mean)):
        metrics[name] = evaluate([r["target"] for r in selection], [value] * len(selection))
    selected = min(metrics, key=lambda name: (metrics[name]["rmse"], metrics[name]["mae"], name))
    search_hash = artifacts.put({"search": search, "chosen": chosen})
    report = {
        "schema": schema, "source_release_hash": source_release,
        "search_hash": search_hash, "candidates": finals, "metrics": metrics,
        "selected_candidate": selected, "train_rows": len(train_rows),
        "reserved_early_2025_rows": len(reserved), "selection_rows": len(selection),
        "selection_input_hashes": [r["input_hash"] for r in selection],
        "selection_row_hashes": [r["base_row_hash"] for r in selection],
        "selection_first_session": min(r["session"] for r in selection),
        "selection_last_session": max(r["session"] for r in selection),
        "evaluation_kind": "RETROSPECTIVE_DEVELOPMENT_NOT_FINAL_TEST",
        "availability_tier": "HISTORICAL_APPROXIMATE", "paper_action_authorized": False,
        "final_test_completed": False,
    }
    report_hash = artifacts.put(report)
    release = {
        "schema": schema, "source_release_hash": source_release,
        "report_hash": report_hash, "selected_candidate": selected,
        "selected_model_hash": finals[selected]["model_hash"] if selected in finals else None,
        "constant_return": mean if selected == "training_mean_return" else 0.0,
        "feature_version": FEATURE_VERSION,
        "evaluation_kind": "RETROSPECTIVE_DEVELOPMENT_NOT_FINAL_TEST",
        "availability_tier": "HISTORICAL_APPROXIMATE", "paper_action_authorized": False,
        "final_test_completed": False, "deployment_promoted": False,
    }

    def verify_release(result):
        for value in finals.values():
            check_receipt(root, value)
        if artifacts.get(result["release_hash"]) != release:
            raise ValueError("regression release differs")

    saved = supervised(root, "regression_release", {"report_hash": report_hash},
                       lambda: {"release_hash": artifacts.put(release)}, verify_release)
    return {"schema": schema, "stage": "COMPLETE", **saved,
            "report_hash": report_hash, "selected_candidate": selected, "metrics": metrics,
            "train_rows": len(train_rows), "selection_rows": len(selection),
            "reserved_early_2025_rows": len(reserved), "final_test_completed": False,
            "paper_action_authorized": False}


def build(source: Path, root: Path, release_hash: str, *, evidence: str, progress=None) -> dict:
    if (source.resolve() == root.resolve() or not isinstance(evidence, str)
            or not 1 <= len(evidence.strip()) <= 500):
        raise ValueError("separate regression directory and bounded authorization required")
    binding = {
        "schema": REGRESSION_SCHEMA, "source_release_hash": release_hash,
        "evidence": evidence, "configurations": settings(), "feature_version": FEATURE_VERSION,
    }
    with owned_run(root, binding, progress) as checkpoint:
        checkpoint({"schema": REGRESSION_SCHEMA, "stage": "VERIFYING_REGRESSION_SOURCE"})
        artifacts = Artifacts(root / "artifacts")

        saved = (registered_source(root, binding)
                 or bounded_source(source, root, release_hash, checkpoint))
        check_receipt(root, saved)
        result = train(root, source, artifacts.get(saved["rows_hash"]), release_hash, checkpoint)
        result["source_release_hash"] = release_hash
        result["build_binding_hash"] = digest(binding)
        checkpoint(result)
        return result


def saved_predict(root: Path, source: Path, release_hash: str, input_hash: str) -> dict:
    from marketpulse import boosting_models

    authority(root, "release_hash", release_hash)
    artifacts = Artifacts(root / "artifacts")
    release = artifacts.get(release_hash)
    if (release["schema"] not in {REGRESSION_SCHEMA, boosting_models.MODEL_SCHEMA}
            or release["paper_action_authorized"] is not False
            or release["deployment_promoted"] is not False):
        raise ValueError("invalid regression research release")
    payload = Artifacts(source / "artifacts").get(input_hash)
    if set(payload) != {"input", "news"} or payload["input"]["schema"] != FEATURE_VERSION:
        raise ValueError("saved regression inference requires compatible label-free inputs")
    if release["selected_model_hash"] is None:
        from marketpulse.regression_models import numeric

        numeric([payload])  # validate input hash/schema even for a constant baseline
        value = release["constant_return"]
    else:
        model = artifacts.get(release["selected_model_hash"])
        if model["schema"] != release["schema"]:
            raise ValueError("regression release/model schema differs")
        predict_model = (boosting_models.predict
                         if release["schema"] == boosting_models.MODEL_SCHEMA else predict)
        value = predict_model(model, [payload], artifacts)[0]
    return {
        "schema": release["schema"], "release_hash": release_hash, "input_hash": input_hash,
        "symbol": payload["input"]["symbol"], "session": payload["input"]["session"],
        "predicted_return_fraction": value, "predicted_return_percent": 100 * value,
        "derived_class": classify_return(Decimal(str(value)), Decimal("0.01")),
        "outcomes_loaded": False, "paper_action_authorized": False,
        "evaluation_kind": "RETROSPECTIVE_DEVELOPMENT_NOT_FINAL_TEST",
    }
