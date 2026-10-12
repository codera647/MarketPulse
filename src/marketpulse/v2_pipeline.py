"""Authorized v2 build: immutable source lineage, ablations and development release."""

from __future__ import annotations

import json
from collections import Counter
from datetime import date
from importlib.metadata import version
from pathlib import Path

import numpy as np

from marketpulse.baselines import CLASSES
from marketpulse.real_training import (
    authorized_rows,
    load_research_release,
    validation_segments,
)
from marketpulse.research import saved_pipeline
from marketpulse.storage import RawStore, digest
from marketpulse.v2_features import FEATURE_VERSION, enrich_input, mask_rows
from marketpulse.v2_models import (
    calibrate_candidate,
    candidate_id,
    candidate_settings,
    detailed_metrics,
    fit_candidate,
    fold_rosters,
    score_candidate,
)
from marketpulse.v2_news import MODEL_SPEC, capture_sentiment, load_sentiment
from marketpulse.v2_runtime import (
    SCHEMA,
    Artifacts,
    check_receipt,
    environment,
    owned_run,
    supervised,
)
from marketpulse.v2_sources import capture_context, load_context


def _base_rows(base: Path, root: Path, release_hash: str, checkpoint) -> dict:
    artifacts = Artifacts(root / "artifacts")
    release = load_research_release(base, release_hash)
    binding = {
        "base_release_hash": release_hash,
        "report_hash": release["binding"]["report_hash"],
        "entity_projection": "verified-source-entity-tags/1",
    }
    # The existing authorized loader rechecks native v1 source receipts and outcomes.
    # Keep this potentially long preflight outside a neutral Harness's <=300s lease.
    # Cached complete v2 work is checked by supervised(), without re-executing it.
    loaded = None

    def load():
        nonlocal loaded
        if loaded is None:
            train, validation, report = authorized_rows(
                saved_pipeline(base),
                release["contract"],
                release["authorization"],
                progress=lambda event: checkpoint({"stage": "VERIFYING_V1_LINEAGE", **event}),
            )
            loaded = train + validation
        return loaded

    from marketpulse.storage import ExtractionStore
    from marketpulse.v2_runtime import environment

    task_key = digest({"stage": "base_rows", "binding": {**binding, "environment": environment()}})
    prior = ExtractionStore(root / "v2-jobs.sqlite3").get_job(task_key)
    if prior is None or prior["run_id"] is None:
        load()

    def execute():
        rows = load()
        with saved_pipeline(base).store.connect() as db:
            tags = {
                row["version_hash"]: json.loads(row["symbols_json"])
                for row in db.execute("SELECT version_hash,symbols_json FROM article_versions")
            }
        needed = {a["version_hash"] for row in rows for a in row["news"]}
        projection = {key: tags[key] for key in sorted(needed)}
        return {
            "base_rows_hash": artifacts.put(rows),
            "rows": len(rows),
            "entity_tags_hash": artifacts.put(projection),
        }

    def verify(result):
        rows = artifacts.get(result["base_rows_hash"])
        report = RawStore(base / "datasets").get(binding["report_hash"])
        expected = {entry["row_hash"] for entry in report["rows"] if entry["split"] != "test"}
        if (
            len(rows) != result["rows"]
            or {row["row_hash"] for row in rows} != expected
            or len(rows) != len(expected)
            or any(row["split"] not in {"train", "validation"} for row in rows)
        ):
            raise ValueError("v2 original audited training roster mismatch")
        source = RawStore(base / "datasets")
        entity_tags = artifacts.get(result["entity_tags_hash"])
        with saved_pipeline(base).store.connect() as db:
            current = {
                row["version_hash"]: json.loads(row["symbols_json"])
                for row in db.execute("SELECT version_hash,symbols_json FROM article_versions")
            }
        needed = {a["version_hash"] for row in rows for a in row["news"]}
        if entity_tags != {key: current[key] for key in sorted(needed)}:
            raise ValueError("v2 entity projection differs from verified source versions")
        for row in rows:
            original = source.get(row["row_hash"])
            if {k: v for k, v in row.items() if k != "row_hash"} != original:
                raise ValueError("v2 original row evidence changed")
            if any(row["symbol"] not in entity_tags[a["version_hash"]] for a in row["news"]):
                raise ValueError("v2 news source entity does not include target")
        if load_research_release(base, release_hash) != release:
            raise ValueError("v1 release changed")

    return supervised(root, "base_rows", binding, execute, verify)


def build_features(
    root: Path,
    base_hash: str,
    context_hash: str,
    sentiment_hash: str,
    checkpoint,
    *,
    entity_tags_hash: str | None = None,
) -> dict:
    artifacts = Artifacts(root / "artifacts")
    binding = {
        "base_hash": base_hash,
        "context_hash": context_hash,
        "sentiment_hash": sentiment_hash,
        "feature_version": FEATURE_VERSION,
        "entity_tags_hash": entity_tags_hash,
    }

    original = artifacts.get(base_hash)
    rows = mask_rows(original)
    if entity_tags_hash:
        tags = artifacts.get(entity_tags_hash)
        rows = [
            {
                **row,
                "news": [
                    {**article, "symbols": tags[article["version_hash"]]} for article in row["news"]
                ],
            }
            for row in rows
        ]
    daily, intraday = load_context(root, context_hash)
    sentiments = load_sentiment(root, sentiment_hash)

    def prepared(chunk, *, persist):
        enriched, missing = [], {}
        for row in chunk:
            value = enrich_input(row, daily, intraday, sentiments)
            for group in ("market", "meaning"):
                for name, feature in value[group].items():
                    missing[name] = missing.get(name, 0) + int(feature is None)
            # Separate input-only artifacts enable inference without opening labels.
            payload = {"input": value, "news": row["news"]}
            input_hash = artifacts.put(payload) if persist else digest(payload)
            if not persist and artifacts.get(input_hash) != payload:
                raise ValueError("v2 input artifact replay differs")
            enriched.append(
                {
                    "session": row["session"],
                    "symbol": row["symbol"],
                    "role": "train" if row["split"] == "train" else "development",
                    "base_row_hash": row["row_hash"],
                    "label": row["label"],
                    "input_hash": input_hash,
                }
            )
        quality = {
            "rows": len(enriched),
            "news_documents": len(sentiments),
            "availability_tier": "HISTORICAL_APPROXIMATE",
            "earnings_calendar_available": False,
            "earnings_consensus_available": False,
            "finbert_historical_audit": "INCOMPLETE",
            "by_feature_missing": missing,
        }
        return {"rows": enriched, "quality": quality}

    chunks = []
    for start in range(0, len(rows), 300):
        chunk = rows[start : start + 300]
        chunk_binding = {**binding, "roster_hash": artifacts.put([r["row_hash"] for r in chunk])}

        def execute_chunk():
            checkpoint(
                {"stage": "BUILDING_V2_DATASET", "rows_complete": start, "rows_total": len(rows)}
            )
            return {"chunk_hash": artifacts.put(prepared(chunk, persist=True))}

        def verify_chunk(result):
            if artifacts.get(result["chunk_hash"]) != prepared(chunk, persist=False):
                raise ValueError("v2 independent feature replay differs")

        chunks.append(supervised(root, "dataset_chunk", chunk_binding, execute_chunk, verify_chunk))

    assembled, missing = [], {}
    for result in chunks:
        check_receipt(root, result)
        saved = artifacts.get(result["chunk_hash"])
        assembled.extend(saved["rows"])
        for name, count in saved["quality"]["by_feature_missing"].items():
            missing[name] = missing.get(name, 0) + count
    quality = {
        **artifacts.get(chunks[0]["chunk_hash"])["quality"],
        "rows": len(assembled),
        "by_feature_missing": missing,
    }
    dataset = {"rows": assembled, "quality": quality, "binding": binding, "chunks": chunks}

    def execute():
        return {"dataset_hash": artifacts.put(dataset)}

    def verify(result):
        checkpoint({"stage": "VERIFYING_V2_DATASET"})
        if artifacts.get(result["dataset_hash"]) != dataset:
            raise ValueError("v2 feature replay differs")

    return supervised(root, "dataset", binding, execute, verify)


def hydrate(artifacts: Artifacts, roster: list[dict]) -> list[dict]:
    return [{**row, **artifacts.get(row["input_hash"])} for row in roster]


def _fit_and_score(
    root: Path,
    train: list[dict],
    evaluation: list[dict],
    settings: dict,
    checkpoint,
    *,
    calibration=None,
    phase="fold",
) -> dict:
    artifacts = Artifacts(root / "artifacts")
    binding = {
        "train_roster_hash": artifacts.put([row["base_row_hash"] for row in train]),
        "evaluation_roster_hash": artifacts.put([row["base_row_hash"] for row in evaluation]),
        "calibration_roster_hash": artifacts.put(
            [row["base_row_hash"] for row in calibration or []]
        ),
        "settings": settings,
        "phase": phase,
        "dataset_feature_version": FEATURE_VERSION,
        "train_input_hashes": artifacts.put([row["input_hash"] for row in train]),
        "eval_input_hashes": artifacts.put([row["input_hash"] for row in evaluation]),
        "calibration_input_hashes": artifacts.put([row["input_hash"] for row in calibration or []]),
    }
    if (
        not train
        or not evaluation
        or max(row["session"] for row in train) >= min(row["session"] for row in evaluation)
        or {row["base_row_hash"] for row in train} & {row["base_row_hash"] for row in evaluation}
    ):
        raise ValueError("v2 model evaluation overlaps training chronology")

    def execute():
        checkpoint(
            {
                "stage": "TRAINING_V2",
                "phase": phase,
                "candidate": candidate_id(settings),
                "train_rows": len(train),
                "evaluation_rows": len(evaluation),
            }
        )
        model = fit_candidate(train, settings, artifacts)
        if calibration:
            model = calibrate_candidate(model, calibration, artifacts)
        model_hash = artifacts.put(model)
        probabilities = score_candidate(model, evaluation, artifacts)
        prediction_hash = artifacts.put(
            {
                "model_hash": model_hash,
                "input_hashes": [row["input_hash"] for row in evaluation],
                "probabilities": probabilities,
            }
        )
        report = {
            "model_hash": model_hash,
            "prediction_hash": prediction_hash,
            "metrics": detailed_metrics(evaluation, probabilities),
            "first_session": min(row["session"] for row in evaluation),
            "last_session": max(row["session"] for row in evaluation),
            "evaluation_kind": "DEVELOPMENT_NOT_FINAL_TEST",
            "binding": binding,
        }
        return {
            "report_hash": artifacts.put(report),
            "model_hash": model_hash,
            "prediction_hash": prediction_hash,
        }

    def verify(result):
        model = artifacts.get(result["model_hash"])
        if (
            model["training_rows"] != [row["base_row_hash"] for row in train]
            or model["settings"] != settings
            or model["calibration_rows"] != [row["base_row_hash"] for row in calibration or []]
        ):
            raise ValueError("v2 model training/calibration identity changed")
        # Recompute from saved coefficients/binary, never refit during VERIFY.
        replay = score_candidate(model, evaluation, artifacts)
        predictions = artifacts.get(result["prediction_hash"])
        if (
            predictions["model_hash"] != result["model_hash"]
            or predictions["input_hashes"] != [row["input_hash"] for row in evaluation]
            or not np.allclose(replay, predictions["probabilities"], atol=1e-10)
        ):
            raise ValueError("v2 independent inference replay differs")
        report = artifacts.get(result["report_hash"])
        if (
            report["binding"] != binding
            or report["model_hash"] != result["model_hash"]
            or report["metrics"] != detailed_metrics(evaluation, replay)
        ):
            raise ValueError("v2 independent metric replay differs")

    return supervised(root, "fit_score", binding, execute, verify)


def train_v2(root: Path, dataset_result: dict, checkpoint) -> dict:
    artifacts = Artifacts(root / "artifacts")
    check_receipt(root, dataset_result)
    dataset = artifacts.get(dataset_result["dataset_hash"])
    train = hydrate(artifacts, [row for row in dataset["rows"] if row["role"] == "train"])
    development = hydrate(
        artifacts, [row for row in dataset["rows"] if row["role"] == "development"]
    )
    folds = fold_rosters(train)
    settings = candidate_settings()
    search = []
    for i, config in enumerate(settings):
        outcomes = []
        for fold, (fitting, evaluation) in enumerate(folds):
            checkpoint(
                {
                    "stage": "CROSS_VALIDATING",
                    "candidate_index": i + 1,
                    "candidates_total": len(settings),
                    "fold": fold + 1,
                }
            )
            outcomes.append(
                _fit_and_score(
                    root,
                    fitting,
                    evaluation,
                    config,
                    checkpoint,
                    phase=f"development_fold_{fold + 1}",
                )
            )
        reports = [artifacts.get(result["report_hash"]) for result in outcomes]
        search.append(
            {
                "settings": config,
                "folds": outcomes,
                "mean_macro_f1": float(np.mean([r["metrics"]["macro_f1"] for r in reports])),
                "mean_log_loss": float(np.mean([r["metrics"]["log_loss"] for r in reports])),
            }
        )
    groups = {}
    for entry in search:
        group = entry["settings"]["family"] + "/" + entry["settings"]["stage"]
        groups.setdefault(group, []).append(entry)
    chosen = {
        group: min(
            entries,
            key=lambda entry: (
                -entry["mean_macro_f1"],
                entry["mean_log_loss"],
                candidate_id(entry["settings"]),
            ),
        )
        for group, entries in groups.items()
    }
    search_hash = artifacts.put(
        {
            "search": search,
            "chosen": chosen,
            "selection_rule": "mean_fold_macro_f1_then_log_loss_then_id",
        }
    )
    calibration, selection = validation_segments(development)
    calibration = [{**row, "role": "calibration"} for row in calibration]
    selection = [{**row, "role": "selection"} for row in selection]
    results = {
        group: _fit_and_score(
            root,
            train,
            selection,
            entry["settings"],
            checkpoint,
            calibration=calibration,
            phase="2025_selection",
        )
        for group, entry in chosen.items()
    }
    labels = [row["label"] for row in train]
    counts = Counter(labels)
    majority = [[counts[label] / len(train) for label in CLASSES] for row in selection]
    comparison = {
        group: artifacts.get(result["report_hash"])["metrics"] for group, result in results.items()
    }
    comparison["majority"] = detailed_metrics(selection, majority)
    selected = min(
        comparison,
        key=lambda name: (-comparison[name]["macro_f1"], comparison[name]["log_loss"], name),
    )
    report = {
        "schema": SCHEMA,
        "dataset_hash": dataset_result["dataset_hash"],
        "search_hash": search_hash,
        "candidates": results,
        "metrics": comparison,
        "selected_candidate": selected,
        "train_rows": len(train),
        "calibration_rows": len(calibration),
        "selection_rows": len(selection),
        "selection_row_hashes": [row["base_row_hash"] for row in selection],
        "selection_input_hashes": [row["input_hash"] for row in selection],
        "evaluation_kind": "DEVELOPMENT_NOT_FINAL_TEST",
        "final_test_completed": False,
        "paper_action_authorized": False,
        "deployment_promoted": False,
        "by_ticker": {},
    }
    for group, result in results.items():
        probabilities = artifacts.get(result["prediction_hash"])["probabilities"]
        report["by_ticker"][group] = {}
        for symbol in sorted({row["symbol"] for row in selection}):
            indices = [i for i, row in enumerate(selection) if row["symbol"] == symbol]
            report["by_ticker"][group][symbol] = detailed_metrics(
                [selection[i] for i in indices], [probabilities[i] for i in indices]
            )
    report_hash = artifacts.put(report)
    binding = {
        "report_hash": report_hash,
        "dataset_hash": dataset_result["dataset_hash"],
        "search_hash": search_hash,
    }

    def release(*, persist=True):
        payload = {
            "schema": SCHEMA,
            **binding,
            "selected_candidate": selected,
            "selected_model_hash": results[selected]["model_hash"]
            if selected != "majority"
            else None,
            "majority_priors": majority[0],
            "availability_tier": "HISTORICAL_APPROXIMATE",
            "evaluation_kind": "DEVELOPMENT_NOT_FINAL_TEST",
            "finbert_spec": MODEL_SPEC,
            "environment": environment(),
            "human_dataset_reviewed": False,
            "final_test_completed": False,
            "paper_action_authorized": False,
            "deployment_promoted": False,
        }
        release_hash = artifacts.put(payload) if persist else digest(payload)
        if not persist and artifacts.get(release_hash) != payload:
            raise ValueError("v2 saved release artifact differs")
        return {"release_hash": release_hash}

    def verify_release(result):
        for value in results.values():
            check_receipt(root, value)
        if result != release(persist=False):
            raise ValueError("v2 release differs from frozen development selection")

    saved = supervised(root, "release", binding, release, verify_release)
    return {
        "stage": "COMPLETE",
        **saved,
        "report_hash": report_hash,
        "selected_candidate": selected,
        "metrics": comparison,
        "train_rows": len(train),
        "calibration_rows": len(calibration),
        "selection_rows": len(selection),
        "final_test_completed": False,
        "paper_action_authorized": False,
    }


def build_v2(
    base: Path,
    root: Path,
    release_hash: str,
    client,
    *,
    evidence: str,
    progress=None,
    sentiment_engine_factory=None,
) -> dict:
    if (
        base.resolve() == root.resolve()
        or not isinstance(evidence, str)
        or not (1 <= len(evidence.strip()) <= 500)
    ):
        raise ValueError("separate v2 directory and explicit authorization are required")
    binding = {
        "schema": SCHEMA,
        "base_release_hash": release_hash,
        "evidence": evidence,
        "feature_version": FEATURE_VERSION,
        "sentiment_spec": MODEL_SPEC,
        "settings": candidate_settings(),
        "versions": {
            name: version(name)
            for name in ("scikit-learn", "numpy", "catboost", "transformers", "torch")
        },
    }
    artifacts = Artifacts(root / "artifacts")
    with owned_run(root, binding, progress) as checkpoint:
        artifacts.put(binding)
        saved = _base_rows(base, root, release_hash, checkpoint)
        check_receipt(root, saved)
        rows = artifacts.get(saved["base_rows_hash"])
        context = capture_context(
            root,
            client,
            date.fromisoformat(min(r["session"] for r in rows)),
            date.fromisoformat(max(r["session"] for r in rows)),
            checkpoint,
        )
        kwargs = {"engine_factory": sentiment_engine_factory} if sentiment_engine_factory else {}
        sentiment = capture_sentiment(root, mask_rows(rows), checkpoint, **kwargs)
        dataset = build_features(
            root,
            saved["base_rows_hash"],
            context["manifest_hash"],
            sentiment["manifest_hash"],
            checkpoint,
            entity_tags_hash=saved["entity_tags_hash"],
        )
        result = train_v2(root, dataset, checkpoint)
        if (
            load_research_release(base, release_hash)["model_hash"]
            != RawStore(base / "research-models").get(release_hash)["model_hash"]
        ):
            raise ValueError("v1 model changed")
        result["base_release_hash"] = release_hash
        result["build_binding_hash"] = digest(binding)
        result["dataset_hash"] = dataset["dataset_hash"]
        result["context_queries"] = context["queries"]
        result["sentiment_documents"] = sentiment["documents"]
        artifacts.put(result)
        checkpoint(result)
        return result


def predict_v2(root: Path, release_hash: str, input_hash: str) -> dict:
    artifacts = Artifacts(root / "artifacts")
    release = artifacts.get(release_hash)
    if (
        release["schema"] != SCHEMA
        or release["paper_action_authorized"] is not False
        or release["deployment_promoted"] is not False
    ):
        raise ValueError("invalid v2 research release")
    # Resolve matching release through its native/application verification receipt.
    from marketpulse.storage import ExtractionStore

    with ExtractionStore(root / "v2-jobs.sqlite3").connect() as db:
        manifests = [
            json.loads(row[0])
            for row in db.execute(
                "SELECT manifest_json FROM extraction_jobs WHERE status='COMPLETE' "
                "AND manifest_json IS NOT NULL"
            )
        ]
    matching = [r for r in manifests if r.get("release_hash") == release_hash]
    if len(matching) != 1:
        raise ValueError("v2 release has no unique verification authority")
    check_receipt(root, matching[0])
    item = artifacts.get(input_hash)
    if set(item) != {"input", "news"}:
        raise ValueError("v2 inference requires a label-free input artifact")
    probabilities = (
        release["majority_priors"]
        if release["selected_model_hash"] is None
        else score_candidate(artifacts.get(release["selected_model_hash"]), [item], artifacts)[0]
    )
    return {
        "schema": SCHEMA,
        "release_hash": release_hash,
        "input_hash": input_hash,
        "session": item["input"]["session"],
        "symbol": item["input"]["symbol"],
        "probabilities": dict(zip(CLASSES, probabilities)),
        "evaluation_kind": "DEVELOPMENT_NOT_FINAL_TEST",
        "outcomes_loaded": False,
        "availability_tier": "HISTORICAL_APPROXIMATE",
        "paper_action_authorized": False,
    }
