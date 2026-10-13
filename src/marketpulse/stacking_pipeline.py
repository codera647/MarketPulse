"""Nested past-only expert selection, walk-forward meta fitting and audited release."""

from __future__ import annotations

import json
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

import numpy as np
from scipy.special import softmax

from marketpulse import price_expert_models
from marketpulse.baselines import CLASSES
from marketpulse.clock import exchange_calendar
from marketpulse.context_expert_models import ExpertAPI
from marketpulse.price_expert_pipeline import reuse_roster
from marketpulse.real_training import validation_segments
from marketpulse.regression_pipeline import authority, complete_roster, hydrate
from marketpulse.stacking_models import EXPERTS, SCHEMA, MetaAPI, probability_input
from marketpulse.storage import digest
from marketpulse.v2_models import detailed_metrics, fold_rosters
from marketpulse.v2_news import MODEL_SPEC
from marketpulse.v2_pipeline import _fit_and_score
from marketpulse.v2_runtime import Artifacts, check_receipt, owned_run, supervised


def expert_apis() -> dict:
    return {"price": price_expert_models, "news": ExpertAPI("news"), "market": ExpertAPI("market")}


def purge_before(rows: list[dict], next_session: str) -> list[dict]:
    start = date.fromisoformat(next_session)
    dates = exchange_calendar().valid_days(start_date=start - timedelta(days=14), end_date=start)
    prior = [d.date().isoformat() for d in dates if d.date() < start]
    if not prior:
        raise ValueError("exchange embargo boundary missing")
    return [r for r in rows if r["session"] < prior[-1]]


def tail_calibration(rows: list[dict]) -> tuple[list, list]:
    dates = sorted({r["session"] for r in rows})
    count = min(60, max(4, len(dates) // 10))
    if len(dates) <= count + 4:
        raise ValueError("insufficient chronological calibration history")
    boundary = dates[-count]
    fitting = purge_before([r for r in rows if r["session"] < boundary], boundary)
    calibration = [{**r, "role": "calibration"} for r in rows if r["session"] >= boundary]
    complete_roster(fitting)
    complete_roster(calibration)
    return fitting, calibration


def inner_rosters(history: list[dict]) -> tuple[list, list, list]:
    last_year = max(r["session"][:4] for r in history)
    calibration, selection = validation_segments(
        [r for r in history if r["session"][:4] == last_year]
    )
    earlier = [r for r in history if r["session"][:4] < last_year]
    earlier = purge_before(earlier, min(r["session"] for r in calibration))
    return (earlier, [{**r, "role": "calibration"} for r in calibration], selection)


def select_experts(
    root: Path, history: list, future: list, phase: str, apis: dict, checkpoint, progress: dict
) -> dict:
    """Every candidate-selection label and calibrator precedes the predicted block."""
    if not history or max(r["session"] for r in history) >= min(r["session"] for r in future):
        raise ValueError("expert selection cannot read future outcomes")
    artifacts = Artifacts(root / "artifacts")
    inner_train, inner_calibration, inner_selection = inner_rosters(history)
    final_train, final_calibration = tail_calibration(history)
    outcomes, searches = {}, {}
    for name in EXPERTS:
        api, entries = apis[name], []
        for i, config in enumerate(api.settings()):
            checkpoint(
                {
                    "stage": "STACK_NESTED_EXPERT_SELECTION",
                    "expert": name,
                    "phase": phase,
                    "fits_complete": progress["complete"],
                    "fits_total": progress["total"],
                }
            )
            outcome = _fit_and_score(
                root,
                inner_train,
                inner_selection,
                config,
                lambda e: checkpoint({**e, "schema": SCHEMA, "expert": name}),
                calibration=inner_calibration,
                phase=f"{phase}_{name}_inner_{i}",
                model_api=api,
            )
            progress["complete"] += 1
            score = artifacts.get(outcome["report_hash"])["metrics"]
            entries.append(
                {
                    "settings": config,
                    "outcome": outcome,
                    "macro_f1": score["macro_f1"],
                    "log_loss": score["log_loss"],
                }
            )
        chosen = min(entries, key=lambda e: (-e["macro_f1"], e["log_loss"], digest(e["settings"])))
        outcome = _fit_and_score(
            root,
            final_train,
            future,
            chosen["settings"],
            lambda e: checkpoint({**e, "schema": SCHEMA, "expert": name}),
            calibration=final_calibration,
            phase=f"{phase}_{name}_forecast",
            model_api=api,
        )
        progress["complete"] += 1
        outcomes[name] = outcome
        searches[name] = {"candidates": entries, "chosen": chosen["settings"]}
    selection = {
        "phase": phase,
        "outcomes": outcomes,
        "searches": searches,
        "used_outcomes_through": max(r["session"] for r in history),
        "forecast_first_session": min(r["session"] for r in future),
        "history_row_hashes": [r["base_row_hash"] for r in history],
    }
    return {**selection, "selection_hash": artifacts.put(selection)}


def assemble_oof(root: Path, block: list, selected: dict) -> dict:
    artifacts = Artifacts(root / "artifacts")
    # Check request identity even when the supervised task is resumed from cache.
    if artifacts.get(selected["selection_hash"]) != {
        k: v for k, v in selected.items() if k != "selection_hash"
    }:
        raise ValueError("OOF expert-selection identity differs")

    def assemble():
        if artifacts.get(selected["selection_hash"]) != {
            k: v for k, v in selected.items() if k != "selection_hash"
        }:
            raise ValueError("OOF expert-selection identity differs")
        history_ids = set(selected["history_row_hashes"])
        for search in selected["searches"].values():
            for candidate in search["candidates"]:
                outcome = candidate["outcome"]
                check_receipt(root, outcome)
                binding = artifacts.get(outcome["report_hash"])["binding"]
                for key in (
                    "train_roster_hash",
                    "evaluation_roster_hash",
                    "calibration_roster_hash",
                ):
                    if not set(artifacts.get(binding[key])) <= history_ids:
                        raise ValueError("OOF expert tuning consulted outside its past history")
        probabilities = {}
        for name, outcome in selected["outcomes"].items():
            check_receipt(root, outcome)
            model = artifacts.get(outcome["model_hash"])
            if not set(model["training_rows"] + model["calibration_rows"]) <= history_ids:
                raise ValueError(
                    "OOF expert fitting/calibration consulted outside its past history"
                )
            saved = artifacts.get(outcome["prediction_hash"])
            if saved["input_hashes"] != [r["input_hash"] for r in block]:
                raise ValueError("expert OOF roster differs")
            probabilities[name] = saved["probabilities"]
        result = []
        for i, row in enumerate(block):
            value = probability_input(
                row, {n: probabilities[n][i] for n in EXPERTS}, selected["used_outcomes_through"]
            )
            MetaAPI().numeric([{"input": value}])
            result.append(
                {
                    "session": row["session"],
                    "symbol": row["symbol"],
                    "label": row["label"],
                    "base_row_hash": row["base_row_hash"],
                    "role": "train",
                    "source_input_hash": row["input_hash"],
                    "input_hash": artifacts.put({"input": value}),
                    "selection_hash": selected["selection_hash"],
                }
            )
        complete_roster(result)
        return result

    def verify(result):
        if artifacts.get(result["oof_hash"]) != assemble():
            raise ValueError("independent OOF assembly replay differs")

    return supervised(
        root,
        "stack_oof_assembly",
        {
            "selection_hash": selected["selection_hash"],
            "roster_hash": artifacts.put([r["base_row_hash"] for r in block]),
        },
        lambda: {"oof_hash": artifacts.put(assemble())},
        verify,
    )


def hydrate_meta(artifacts: Artifacts, rows: list) -> list:
    return [{**r, **artifacts.get(r["input_hash"])} for r in rows]


def meta_tuning(
    root: Path, rows: list, api: MetaAPI, checkpoint, progress: dict
) -> tuple[dict, dict]:
    artifacts = Artifacts(root / "artifacts")
    entries = []
    years = sorted({r["session"][:4] for r in rows})
    for i, config in enumerate(api.settings()):
        outcomes = []
        for year in years[1:]:
            validation = [r for r in rows if r["session"][:4] == year]
            history = purge_before(
                [r for r in rows if r["session"][:4] < year], min(r["session"] for r in validation)
            )
            fitting, calibration = tail_calibration(history)
            checkpoint(
                {
                    "stage": "STACK_META_TUNING",
                    "fits_complete": progress["complete"],
                    "fits_total": progress["total"],
                }
            )
            outcome = _fit_and_score(
                root,
                fitting,
                validation,
                config,
                lambda e: checkpoint({**e, "schema": SCHEMA}),
                calibration=calibration,
                phase=f"stack_meta_{year}_{i}",
                model_api=api,
            )
            progress["complete"] += 1
            outcomes.append(outcome)
        scores = [artifacts.get(o["report_hash"])["metrics"] for o in outcomes]
        entries.append(
            {
                "settings": config,
                "outcomes": outcomes,
                "mean_macro_f1": float(np.mean([s["macro_f1"] for s in scores])),
                "mean_log_loss": float(np.mean([s["log_loss"] for s in scores])),
            }
        )
    chosen = min(
        entries, key=lambda e: (-e["mean_macro_f1"], e["mean_log_loss"], digest(e["settings"]))
    )
    return chosen["settings"], {"entries": entries, "chosen": chosen["settings"]}


def temperature(values: list, labels: list[str]) -> float:
    rows = [{"label": label, "symbol": "AAPL"} for label in labels]
    return min(
        (detailed_metrics(rows, apply_temperature(values, t))["log_loss"], t)
        for t in (0.5, 0.75, 1.0, 1.5, 2.0)
    )[1]


def apply_temperature(values: list, t: float) -> list:
    if (
        isinstance(t, bool)
        or not isinstance(t, (int, float))
        or not np.isfinite(t)
        or t not in (0.5, 0.75, 1.0, 1.5, 2.0)
    ):
        raise ValueError("invalid averaging temperature")
    return softmax(np.log(np.maximum(values, 1e-15)) / t, axis=1).tolist()


def comparison(artifacts, history, calibration, selection, future, final_experts, meta_final):
    """Reconstruct comparisons only from verified fit predictions and fixed rosters."""
    meta_predictions = artifacts.get(meta_final["prediction_hash"])
    meta_report = artifacts.get(meta_final["report_hash"])
    roster_hash = meta_report["binding"]["evaluation_roster_hash"]
    if artifacts.get(roster_hash) != [r["base_row_hash"] for r in selection]:
        raise ValueError("stack comparison meta roster differs")
    probabilities = {"stack": meta_predictions["probabilities"]}
    experts = {}
    for name, outcome in final_experts["outcomes"].items():
        saved = artifacts.get(outcome["prediction_hash"])
        if saved["input_hashes"] != [r["input_hash"] for r in future]:
            raise ValueError("stack comparison expert roster differs")
        experts[name] = saved["probabilities"]
    by_identity = {(r["session"], r["symbol"]): i for i, r in enumerate(future)}
    indices = [by_identity[(r["session"], r["symbol"])] for r in selection]
    cal_indices = [by_identity[(r["session"], r["symbol"])] for r in calibration]
    for name in EXPERTS:
        probabilities[name] = [experts[name][i] for i in indices]
    means = np.mean([experts[n] for n in EXPERTS], axis=0).tolist()
    average_temperature = temperature(
        [means[i] for i in cal_indices], [r["label"] for r in calibration]
    )
    probabilities["simple_average"] = [means[i] for i in indices]
    probabilities["calibrated_average"] = apply_temperature(
        probabilities["simple_average"], average_temperature
    )
    counts = Counter(r["label"] for r in history)
    priors = [counts[c] / len(history) for c in CLASSES]
    probabilities["majority"] = [priors] * len(selection)
    metrics = {name: detailed_metrics(selection, values) for name, values in probabilities.items()}
    selected = min(metrics, key=lambda n: (-metrics[n]["macro_f1"], metrics[n]["log_loss"], n))
    return probabilities, metrics, selected, average_temperature, priors


def train(root: Path, source: Path, rows: list, checkpoint, apis=None) -> dict:
    apis, api = apis or expert_apis(), MetaAPI()
    artifacts = Artifacts(root / "artifacts")
    hydrated = []
    for start in range(0, len(rows), 300):
        batch = hydrate(source, rows[start : start + 300])
        for expert in apis.values():
            expert.numeric(batch)
        hydrated.extend(batch)
        checkpoint(
            {
                "stage": "LOADING_STACK_INPUTS",
                "rows_complete": len(hydrated),
                "rows_total": len(rows),
            }
        )
    history = [r for r in hydrated if r["role"] == "train"]
    calibration, selection = validation_segments(
        [r for r in hydrated if r["role"] == "development"]
    )
    folds = fold_rosters(history)
    progress = {
        "complete": 0,
        "total": (sum(len(a.settings()) for a in apis.values()) + 3) * 4
        + len(api.settings()) * 2
        + 1,
    }
    blocks, selections, proofs = [], [], []
    for i, (past, later) in enumerate(folds):
        selected = select_experts(root, past, later, f"stack_outer_{i}", apis, checkpoint, progress)
        proof = assemble_oof(root, later, selected)
        check_receipt(root, proof)
        blocks.extend(artifacts.get(proof["oof_hash"]))
        selections.append(selected)
        proofs.append(proof)
    oof = hydrate_meta(artifacts, blocks)
    config, meta_search = meta_tuning(root, oof, api, checkpoint, progress)
    future = calibration + selection
    past = purge_before(history, min(r["session"] for r in future))
    final_experts = select_experts(
        root, past, future, "stack_deployment", apis, checkpoint, progress
    )
    final_proof = assemble_oof(root, future, final_experts)
    check_receipt(root, final_proof)
    future_meta = hydrate_meta(artifacts, artifacts.get(final_proof["oof_hash"]))
    dates = {r["session"] for r in calibration}
    meta_calibration = [{**r, "role": "calibration"} for r in future_meta if r["session"] in dates]
    meta_selection = [r for r in future_meta if r["session"] not in dates]
    meta_final = _fit_and_score(
        root,
        oof,
        meta_selection,
        config,
        lambda e: checkpoint({**e, "schema": SCHEMA}),
        calibration=meta_calibration,
        phase="stack_2025_selection",
        model_api=api,
    )
    progress["complete"] += 1
    probabilities, metrics, selected, average_temperature, priors = comparison(
        artifacts, history, calibration, selection, future, final_experts, meta_final
    )
    report = {
        "schema": SCHEMA,
        "metrics": metrics,
        "selected_candidate": selected,
        "oof_rows": len(oof),
        "oof_years": sorted({r["session"][:4] for r in oof}),
        "train_source_rows": len(history),
        "calibration_rows": len(calibration),
        "selection_rows": len(selection),
        "fits_complete": progress["complete"],
        "fits_total": progress["total"],
        "oof_proofs": proofs,
        "meta_search": meta_search,
        "nested_selections": selections,
        "final_experts": final_experts,
        "meta_final": meta_final,
        "selection_input_hashes": [r["input_hash"] for r in selection],
        "selection_row_hashes": [r["base_row_hash"] for r in selection],
        "predictions_hash": artifacts.put(probabilities),
        "evaluation_kind": "DEVELOPMENT_NOT_FINAL_TEST",
        "availability_tier": "HISTORICAL_APPROXIMATE",
        "final_test_completed": False,
        "paper_action_authorized": False,
        "deployment_promoted": False,
    }
    report_hash = artifacts.put(report)
    release = {
        "schema": SCHEMA,
        "report_hash": report_hash,
        "selected_candidate": selected,
        "expert_models": {n: o["model_hash"] for n, o in final_experts["outcomes"].items()},
        "meta_model_hash": meta_final["model_hash"],
        "majority_priors": priors,
        "average_temperature": average_temperature,
        "used_outcomes_through": final_experts["used_outcomes_through"],
        "calibration_last_session": max(r["session"] for r in calibration),
        "finbert_spec": MODEL_SPEC,
        "model_environment": api.model_environment(),
        "evaluation_kind": "DEVELOPMENT_NOT_FINAL_TEST",
        "availability_tier": "HISTORICAL_APPROXIMATE",
        "final_test_completed": False,
        "paper_action_authorized": False,
        "deployment_promoted": False,
    }

    def verify(result):
        for proof in proofs + [final_proof]:
            check_receipt(root, proof)
        for selected_experts in selections + [final_experts]:
            for search in selected_experts["searches"].values():
                for entry in search["candidates"]:
                    check_receipt(root, entry["outcome"])
            for outcome in selected_experts["outcomes"].values():
                check_receipt(root, outcome)
        for entry in meta_search["entries"]:
            for outcome in entry["outcomes"]:
                check_receipt(root, outcome)
        check_receipt(root, meta_final)
        replay = comparison(
            artifacts, history, calibration, selection, future, final_experts, meta_final
        )
        if (
            replay[0] != artifacts.get(report["predictions_hash"])
            or replay[1:] != (metrics, selected, average_temperature, priors)
            or artifacts.get(report_hash) != report
        ):
            raise ValueError("independent comparison replay differs")
        if (
            artifacts.get(result["release_hash"]) != release
            or progress["complete"] != progress["total"]
        ):
            raise ValueError("stack release differs or fits incomplete")

    saved = supervised(
        root,
        "stack_release",
        {"report_hash": report_hash},
        lambda: {"release_hash": artifacts.put(release)},
        verify,
    )
    return {
        "schema": SCHEMA,
        "stage": "COMPLETE",
        **saved,
        "report_hash": report_hash,
        "selected_candidate": selected,
        "metrics": metrics,
        "oof_rows": len(oof),
        "fits_complete": progress["complete"],
        "fits_total": progress["total"],
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
) -> dict:
    if (
        root.resolve() in {source.resolve(), roster_root.resolve()}
        or not isinstance(evidence, str)
        or not 1 <= len(evidence.strip()) <= 500
    ):
        raise ValueError("separate stack directory and bounded authorization required")
    apis, api = expert_apis(), MetaAPI()
    binding = {
        "schema": SCHEMA,
        "source_release_hash": release_hash,
        "rows_hash": rows_hash,
        "expert_settings": {n: a.settings() for n, a in apis.items()},
        "meta_settings": api.settings(),
        "meta_feature_names": list(api.FEATURE_NAMES),
        "model_environment": api.model_environment(),
        "finbert_spec": MODEL_SPEC,
        "policy": "past-only-inner-selection-tail10pct-max60-min4/1",
        "evidence": evidence,
    }
    status = root / "v2-status.json"
    if status.exists():
        previous = json.loads(status.read_text())
        if previous.get("build_binding_hash", previous["binding_hash"]) != digest(binding):
            raise ValueError("existing stack binding differs; use a new directory")
    with owned_run(root, binding, progress) as write_status:
        latest = {"schema": SCHEMA, "build_binding_hash": digest(binding)}

        def checkpoint(event):
            latest.update(event)
            write_status(latest)

        checkpoint({"stage": "VERIFYING_STACK_SOURCE"})
        rows = reuse_roster(source, roster_root, release_hash, rows_hash)
        if Artifacts(source / "artifacts").get(release_hash).get("finbert_spec") != MODEL_SPEC:
            raise ValueError("stack source FinBERT specification differs")
        artifacts = Artifacts(root / "artifacts")

        def verify_source(result):
            authority(roster_root, "rows_hash", rows_hash)
            authority(source, "release_hash", release_hash)
            if result["rows_hash"] != rows_hash or artifacts.get(rows_hash) != rows:
                raise ValueError("stack source differs")

        proof = supervised(
            root, "stack_source", binding, lambda: {"rows_hash": artifacts.put(rows)}, verify_source
        )
        check_receipt(root, proof)
        result = train(root, source, rows, checkpoint, apis)
        result.update({"build_binding_hash": digest(binding), "source_release_hash": release_hash})
        checkpoint(result)
        return result


def saved_predict(root: Path, source: Path, release_hash: str, input_hash: str) -> dict:
    authority(root, "release_hash", release_hash)
    artifacts = Artifacts(root / "artifacts")
    release = artifacts.get(release_hash)
    if (
        release["schema"] != SCHEMA
        or release["paper_action_authorized"] is not False
        or release["deployment_promoted"] is not False
        or release["model_environment"] != MetaAPI().model_environment()
    ):
        raise ValueError("invalid stack release")
    payload = Artifacts(source / "artifacts").get(input_hash)
    value = payload["input"]
    if value["session"] <= release["calibration_last_session"]:
        raise ValueError("saved stack cannot forecast dates at/before its calibration history")
    apis = expert_apis()
    probabilities = {
        n: apis[n].predict(
            artifacts.get(release["expert_models"][n]), [{"input": value}], artifacts
        )[0]
        for n in EXPERTS
    }
    row = {
        "session": value["session"],
        "symbol": value["symbol"],
        "base_row_hash": value["base_row_hash"],
        "input_hash": input_hash,
    }
    meta_input = probability_input(row, probabilities, release["used_outcomes_through"])
    stack = MetaAPI().predict(
        artifacts.get(release["meta_model_hash"]), [{"input": meta_input}], artifacts
    )[0]
    mean = np.mean(list(probabilities.values()), axis=0).tolist()
    results = {
        **probabilities,
        "stack": stack,
        "simple_average": mean,
        "calibrated_average": apply_temperature([mean], release["average_temperature"])[0],
        "majority": release["majority_priors"],
    }
    return {
        "schema": SCHEMA,
        "release_hash": release_hash,
        "input_hash": input_hash,
        "symbol": value["symbol"],
        "session": value["session"],
        "selected_candidate": release["selected_candidate"],
        "probabilities": dict(zip(CLASSES, results[release["selected_candidate"]])),
        "stack_probabilities": dict(zip(CLASSES, stack)),
        "expert_probabilities": probabilities,
        "outcomes_loaded": False,
        "paper_action_authorized": False,
        "evaluation_kind": "DEVELOPMENT_NOT_FINAL_TEST",
    }
