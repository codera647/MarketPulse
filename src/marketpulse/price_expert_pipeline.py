"""Trailforge-managed price expert research using verified, immutable real inputs."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import numpy as np
from trailforge.runtime import Harness

from marketpulse import price_expert_models as price_models
from marketpulse.baselines import CLASSES
from marketpulse.real_training import validation_segments
from marketpulse.regression_pipeline import authority, complete_roster, hydrate, source_catalog
from marketpulse.storage import digest
from marketpulse.v2_features import FEATURE_VERSION
from marketpulse.v2_models import detailed_metrics, fold_rosters
from marketpulse.v2_pipeline import _fit_and_score
from marketpulse.v2_runtime import Artifacts, check_receipt, owned_run, supervised


def reuse_roster(source: Path, roster_root: Path, release_hash: str, rows_hash: str) -> list:
    """Reuse positive bounded source proofs, not a bare JSON candidate or old UNKNOWN."""
    receipt = authority(roster_root, "rows_hash", rows_hash)
    harness = Harness(
        roster_root / "v2-trailforge.sqlite3",
        tenant_id="local-demo",
        resource_id=f"marketpulse:v2:{receipt['job_key']}",
        adapters=[],
        tenant_limit=1000000,
        global_limit=10000000,
    )
    task = harness.inspect(receipt["run_id"])["goal"]["tasks"][0]
    binding = task["input"]
    if (
        task["adapter_id"] != "marketpulse.v2_regression_source_assembly/2"
        or binding["source_release_hash"] != release_hash
        or binding["rows_hash"] != rows_hash
        or binding.get("parent_job_key") is not None
    ):
        raise ValueError("reused roster must have matching positive fresh source authority")
    artifacts = Artifacts(roster_root / "artifacts")
    chunks = artifacts.get(binding["receipts_hash"])
    assembled = []
    for chunk in chunks:
        check_receipt(roster_root, chunk)
        assembled.extend(artifacts.get(chunk["chunk_hash"]))
    rows = artifacts.get(rows_hash)
    dataset, originals = source_catalog(source, release_hash)
    if (
        rows != assembled
        or len(rows) != len(dataset["rows"])
        or [{k: v for k, v in r.items() if k != "target"} for r in rows] != dataset["rows"]
    ):
        raise ValueError("reused roster differs from positively verified source dataset")
    # Reuse input-validation proofs; recheck immutable audited labels/targets directly.
    for row in rows:
        original = originals[row["base_row_hash"]]
        if (
            original["label"] != row["label"]
            or float(original["return_fraction"]) != row["target"]
            or row["role"] not in {"train", "development"}
            or (row["role"] == "train") != (row["session"] < "2025-01-01")
            or not "2018-01-01" <= row["session"] <= "2025-12-31"
        ):
            raise ValueError("reused roster target/role/scope differs")
    complete_roster(rows)
    return rows


def train(root: Path, source: Path, rows: list, checkpoint, *, model_api=None) -> dict:
    models = model_api or price_models
    expert = getattr(models, "EXPERT", "price")
    prefix = expert.upper()
    artifacts = Artifacts(root / "artifacts")
    checkpoint(
        {"schema": models.SCHEMA, "stage": f"LOADING_{prefix}_INPUTS", "rows_total": len(rows)}
    )
    hydrated = []
    for start in range(0, len(rows), 300):
        batch = hydrate(source, rows[start : start + 300])
        models.numeric(batch)  # Label-free schema/hash/cutoff and frozen whitelist.
        hydrated.extend(batch)
        checkpoint(
            {
                "schema": models.SCHEMA,
                "stage": f"LOADING_{prefix}_INPUTS",
                "rows_complete": len(hydrated),
                "rows_total": len(rows),
            }
        )
    fitting = [r for r in hydrated if r["role"] == "train"]
    calibration, selection = validation_segments(
        [r for r in hydrated if r["role"] == "development"]
    )
    calibration = [{**r, "role": "calibration"} for r in calibration]
    selection = [{**r, "role": "selection"} for r in selection]
    folds = fold_rosters(fitting)
    configurations, search = models.settings(), []
    families = sorted({c["family"] for c in configurations})
    fits_total = len(configurations) * len(folds) + len(families)
    for i, config in enumerate(configurations):
        outcomes = []
        for j, (past, later) in enumerate(folds):
            checkpoint(
                {
                    "schema": models.SCHEMA,
                    "stage": f"{prefix}_CROSS_VALIDATING",
                    "candidate_index": i + 1,
                    "candidates_total": len(configurations),
                    "fold": j + 1,
                    "fits_complete": i * len(folds) + j,
                    "fits_total": fits_total,
                }
            )
            outcomes.append(
                _fit_and_score(
                    root,
                    past,
                    later,
                    config,
                    checkpoint,
                    phase=f"{expert}_fold_{j + 1}",
                    model_api=models,
                )
            )
        scores = [artifacts.get(o["report_hash"])["metrics"] for o in outcomes]
        search.append(
            {
                "settings": config,
                "folds": outcomes,
                "mean_macro_f1": float(np.mean([s["macro_f1"] for s in scores])),
                "mean_log_loss": float(np.mean([s["log_loss"] for s in scores])),
            }
        )
    chosen = {
        family: min(
            [e for e in search if e["settings"]["family"] == family],
            key=lambda e: (-e["mean_macro_f1"], e["mean_log_loss"], digest(e["settings"])),
        )
        for family in families
    }
    finals = {}
    for i, (family, entry) in enumerate(chosen.items()):
        checkpoint(
            {
                "schema": models.SCHEMA,
                "stage": f"{prefix}_FINAL_FITTING",
                "fits_complete": len(configurations) * len(folds) + i,
                "fits_total": len(configurations) * len(folds) + len(chosen),
            }
        )
        finals[family] = _fit_and_score(
            root,
            fitting,
            selection,
            entry["settings"],
            checkpoint,
            calibration=calibration,
            phase=f"{expert}_2025_selection",
            model_api=models,
        )
    counts = Counter(r["label"] for r in fitting)
    priors = [counts[c] / len(fitting) for c in CLASSES]
    comparison = {
        family: artifacts.get(o["report_hash"])["metrics"] for family, o in finals.items()
    }
    comparison["majority"] = detailed_metrics(selection, [priors] * len(selection))
    selected = min(
        comparison, key=lambda n: (-comparison[n]["macro_f1"], comparison[n]["log_loss"], n)
    )
    search_hash = artifacts.put(
        {
            "search": search,
            "chosen": chosen,
            "selection_rule": "macro_f1_then_log_loss_then_digest",
            "stacking_oof_authorized": False,
            "notice": "Search folds are NOT leakage-safe meta-training rows",
        }
    )
    report = {
        "schema": models.SCHEMA,
        "search_hash": search_hash,
        "candidates": finals,
        "metrics": comparison,
        "selected_candidate": selected,
        "feature_names": list(models.FEATURE_NAMES),
        "train_rows": len(fitting),
        "calibration_rows": len(calibration),
        "selection_rows": len(selection),
        "selection_input_hashes": [r["input_hash"] for r in selection],
        "selection_row_hashes": [r["base_row_hash"] for r in selection],
        "selection_first_session": min(r["session"] for r in selection),
        "selection_last_session": max(r["session"] for r in selection),
        "by_ticker": {},
        "evaluation_kind": "DEVELOPMENT_NOT_FINAL_TEST",
        "availability_tier": "HISTORICAL_APPROXIMATE",
        "final_test_completed": False,
        "paper_action_authorized": False,
        "deployment_promoted": False,
        **({"finbert_spec": models.FINBERT_SPEC} if hasattr(models, "FINBERT_SPEC") else {}),
    }
    for family, result in finals.items():
        probabilities = artifacts.get(result["prediction_hash"])["probabilities"]
        report["by_ticker"][family] = {}
        for symbol in sorted({r["symbol"] for r in selection}):
            indices = [i for i, r in enumerate(selection) if r["symbol"] == symbol]
            report["by_ticker"][family][symbol] = detailed_metrics(
                [selection[i] for i in indices], [probabilities[i] for i in indices]
            )
    report_hash = artifacts.put(report)
    release = {
        "schema": models.SCHEMA,
        "report_hash": report_hash,
        "search_hash": search_hash,
        "selected_candidate": selected,
        "selected_model_hash": finals[selected]["model_hash"] if selected in finals else None,
        "majority_priors": priors,
        "feature_version": FEATURE_VERSION,
        "feature_names": list(models.FEATURE_NAMES),
        "model_environment": models.model_environment(),
        "evaluation_kind": "DEVELOPMENT_NOT_FINAL_TEST",
        "availability_tier": "HISTORICAL_APPROXIMATE",
        "final_test_completed": False,
        "paper_action_authorized": False,
        "deployment_promoted": False,
        **({"finbert_spec": models.FINBERT_SPEC} if hasattr(models, "FINBERT_SPEC") else {}),
    }

    def verify(result):
        for entry in search:
            for outcome in entry["folds"]:
                check_receipt(root, outcome)
        for outcome in finals.values():
            check_receipt(root, outcome)
        if artifacts.get(result["release_hash"]) != release:
            raise ValueError("price expert release differs")

    saved = supervised(
        root,
        f"{expert}_release",
        {"report_hash": report_hash},
        lambda: {"release_hash": artifacts.put(release)},
        verify,
    )
    return {
        "schema": models.SCHEMA,
        "stage": "COMPLETE",
        **saved,
        "report_hash": report_hash,
        "selected_candidate": selected,
        "metrics": comparison,
        "train_rows": len(fitting),
        "calibration_rows": len(calibration),
        "selection_rows": len(selection),
        "fits_complete": fits_total,
        "fits_total": fits_total,
        "final_test_completed": False,
        "paper_action_authorized": False,
    }


def build(
    source: Path,
    roster_root: Path,
    root: Path,
    release_hash: str,
    rows_hash: str,
    *,
    evidence: str,
    progress=None,
    model_api=None,
) -> dict:
    models = model_api or price_models
    expert = getattr(models, "EXPERT", "price")
    if (
        root.resolve() in {source.resolve(), roster_root.resolve()}
        or not isinstance(evidence, str)
        or not 1 <= len(evidence.strip()) <= 500
    ):
        raise ValueError("separate price directory and bounded authorization required")
    status = root / "v2-status.json"
    if status.exists() and json.loads(status.read_text())["schema"] != models.SCHEMA:
        raise ValueError("existing root belongs to another experiment")
    binding = {
        "schema": models.SCHEMA,
        "source_release_hash": release_hash,
        "rows_hash": rows_hash,
        "evidence": evidence,
        "settings": models.settings(),
        "feature_version": FEATURE_VERSION,
        "feature_names": list(models.FEATURE_NAMES),
        "model_environment": models.model_environment(),
    }
    if status.exists():
        previous = json.loads(status.read_text())
        if previous.get("build_binding_hash", previous["binding_hash"]) != digest(binding):
            raise ValueError("existing price experiment binding differs; use a new directory")
    with owned_run(root, binding, progress) as write_status:
        latest = {"schema": models.SCHEMA, "build_binding_hash": digest(binding)}

        def checkpoint(event):
            latest.update(event)
            write_status(latest)

        checkpoint({"schema": models.SCHEMA, "stage": f"VERIFYING_{expert.upper()}_SOURCE"})
        rows = reuse_roster(source, roster_root, release_hash, rows_hash)
        if hasattr(models, "FINBERT_SPEC"):
            source_release = Artifacts(source / "artifacts").get(release_hash)
            if source_release.get("finbert_spec") != models.FINBERT_SPEC:
                raise ValueError(
                    "cached sentiment checkpoint differs from news expert specification"
                )
        artifacts = Artifacts(root / "artifacts")

        def verify_source(result):
            authority(roster_root, "rows_hash", rows_hash)
            authority(source, "release_hash", release_hash)
            if result["rows_hash"] != rows_hash or artifacts.get(rows_hash) != rows:
                raise ValueError("reused price source differs")

        proof = supervised(
            root,
            f"{expert}_source",
            binding,
            lambda: {"rows_hash": artifacts.put(rows)},
            verify_source,
        )
        check_receipt(root, proof)
        result = train(root, source, rows, checkpoint, model_api=models)
        result.update(
            {
                "source_release_hash": release_hash,
                "source_rows_hash": rows_hash,
                "build_binding_hash": digest(binding),
            }
        )
        checkpoint(result)
        return result


def saved_predict(
    root: Path, source: Path, release_hash: str, input_hash: str, *, model_api=None
) -> dict:
    models = model_api or price_models
    authority(root, "release_hash", release_hash)
    artifacts = Artifacts(root / "artifacts")
    release = artifacts.get(release_hash)
    if (
        release["schema"] != models.SCHEMA
        or release["paper_action_authorized"] is not False
        or release["deployment_promoted"] is not False
    ):
        raise ValueError("invalid price expert release")
    payload = Artifacts(source / "artifacts").get(input_hash)
    models.numeric([payload])
    probabilities = (
        models.predict(artifacts.get(release["selected_model_hash"]), [payload], artifacts)[0]
        if release["selected_model_hash"]
        else release["majority_priors"]
    )
    return {
        "schema": models.SCHEMA,
        "release_hash": release_hash,
        "input_hash": input_hash,
        "symbol": payload["input"]["symbol"],
        "session": payload["input"]["session"],
        "probabilities": dict(zip(CLASSES, probabilities)),
        "outcomes_loaded": False,
        "paper_action_authorized": False,
        "evaluation_kind": "DEVELOPMENT_NOT_FINAL_TEST",
    }
