"""Explicitly authorized offline research fitting; never deployment promotion."""

from __future__ import annotations

import json
from collections import Counter
from datetime import date
from importlib.metadata import version
from pathlib import Path

from threadpoolctl import threadpool_limits
from trailforge.ports import AdapterCapabilities, FunctionAdapter, VerifiedResult
from trailforge.runtime import Goal, Harness, Task

from marketpulse.baselines import CLASSES, _choose, validate_features
from marketpulse.dataset import frozen_identity, make_row, split_sessions, validate_contract
from marketpulse.features import _load_snapshot, build_features
from marketpulse.modeling import (
    MODEL_NAMES,
    calibrate,
    evaluate_comparison,
    fit_comparison,
    score_comparison,
)
from marketpulse.outcomes import validate_saved_outcome
from marketpulse.preprocessing import (
    NEWS_MASK_POLICY,
    PREPROCESSING_VERSION,
    extend_news_registry,
    mask_seen_stories,
)
from marketpulse.research import _verify_input_receipt, saved_pipeline
from marketpulse.storage import ExtractionStore, RawStore, canonical_bytes, digest

RESEARCH_VERSION = "authorized-offline-research/1"


def load_training_authorization(path: Path) -> dict:
    if not path.is_file() or path.stat().st_size > 16384:
        raise ValueError("bounded private training authorization is required")
    value = json.loads(path.read_text(encoding="utf-8"))
    fields = {"schema", "contract_hash", "report_hash", "authorized", "evidence"}
    if (not isinstance(value, dict) or set(value) not in (fields, fields | {"news_mask_policy"})
            or value["schema"] != RESEARCH_VERSION or value["authorized"] is not True
            or value.get("news_mask_policy") not in (None, NEWS_MASK_POLICY)
            or not isinstance(value["evidence"], str)
            or not 1 <= len(value["evidence"].strip()) <= 500
            or not isinstance(value["contract_hash"], str)
            or any(not isinstance(value.get(field), str) or len(value[field]) != 64
                   or any(char not in "0123456789abcdef" for char in value[field])
                   for field in ("contract_hash", "report_hash"))):
        raise ValueError("explicit user authorization for offline research fitting is required")
    return value


def research_report_ready(report: dict, *, mask_previous_stories: bool = False) -> bool:
    duplicates = bool(report.get("leakage", {}).get("provider_ids_crossing_splits")
                      or report.get("leakage", {}).get("headline_groups_crossing_splits"))
    return bool(report.get("status") in {"COMPLETE_RESEARCH_REVIEW_REQUIRED", "INTEGRITY_BLOCKED"}
                and report.get("accepted_rows", 0) > 0
                and report.get("accepted_rows") == report.get("expected_rows")
                and not report.get("missing_rows") and not report.get("lineage_errors")
                and not report.get("batch_failures")
                and (not duplicates or mask_previous_stories)
                and (report["status"] != "INTEGRITY_BLOCKED" or duplicates))


def authorized_rows(pipeline, contract: dict, authorization: dict, *, progress=None):
    validate_contract(contract, require_approval=True)
    identity = frozen_identity(contract, pipeline)
    key = digest(identity)
    if (authorization.get("schema") != RESEARCH_VERSION
            or authorization.get("authorized") is not True
            or authorization.get("contract_hash") != key
            or not authorization.get("evidence")
            or authorization.get("news_mask_policy") not in (None, NEWS_MASK_POLICY)):
        raise ValueError("offline fitting authorization does not bind this dataset")
    if RawStore(pipeline.data_dir / "contracts").get(key) != identity:
        raise ValueError("saved dataset identity mismatch")
    artifacts = RawStore(pipeline.data_dir / "datasets")
    report = artifacts.get(authorization["report_hash"])
    mask_previous = authorization.get("news_mask_policy") == NEWS_MASK_POLICY
    if (report.get("contract_hash") != key
            or not research_report_ready(report, mask_previous_stories=mask_previous)):
        raise ValueError("research training requires complete, integrity-checked real data")
    expected = {(day, symbol, split) for day, split in split_sessions(contract).items()
                for symbol in contract["symbols"]
                if day not in {entry["session"] for entry in report.get("exclusions", [])}}
    with pipeline.store.connect() as db:
        exclusions = [dict(row) for row in db.execute(
            "SELECT session,exclusion_hash FROM dataset_exclusions WHERE contract_hash=? "
            "ORDER BY session", (key,))]
    if exclusions != report.get("exclusions", []):
        raise ValueError("research exclusions differ from audited quarantine ledger")
    roster = [(entry["session"], entry["symbol"], entry["split"]) for entry in report["rows"]]
    if len(roster) != len(expected) or set(roster) != expected:
        raise ValueError("research roster must contain each complete company/date group")
    with pipeline.store.connect() as db:
        current = {(row["session"], row["symbol"]): row["row_hash"] for row in db.execute(
            "SELECT session,symbol,row_hash FROM dataset_rows WHERE contract_hash=?", (key,))}
    if current != {(entry["session"], entry["symbol"]): entry["row_hash"]
                   for entry in report["rows"]}:
        raise ValueError("research row index differs from audited roster")
    rows = {"train": [], "validation": []}
    checked, outcomes = set(), {}
    total = sum(entry["split"] != "test" for entry in report["rows"])
    loaded = 0
    if progress:
        progress({"phase": "VERIFYING_SAVED_DATA", "verified_rows": 0, "rows_to_verify": total})
    for entry in report["rows"]:
        if entry["split"] == "test":
            continue  # Fitting/calibration/selection never load final-test row artifacts.
        row = artifacts.get(entry["row_hash"])
        if (row.get("contract_hash") != key or any(row.get(name) != entry[name]
                                                  for name in ("session", "symbol", "split"))):
            raise ValueError("research row differs from its audited identity")
        if row["source_job_key"] not in checked:
            _verify_input_receipt(pipeline, row, identity)
            checked.add(row["source_job_key"])
        job = pipeline.store.get_job(row["outcome_job_key"])
        if not job or job["status"] != "COMPLETE":
            raise ValueError("research row lacks a completed outcome job")
        outcome = json.loads(job["manifest_json"])
        outcome_key = digest(outcome)
        if outcome_key not in outcomes:
            outcomes[outcome_key] = validate_saved_outcome(pipeline, outcome)
        if make_row(pipeline, row["snapshot_hash"], outcome, key, contract, entry["split"],
                    verified_outcome=(outcome_key, outcomes[outcome_key])) != row:
            raise ValueError("research row no longer agrees with verified source lineage")
        validate_features(row["features"], availability_tier="HISTORICAL_APPROXIMATE")
        if row["label"] not in CLASSES:
            raise ValueError("invalid training label")
        rows[entry["split"]].append({**row, "row_hash": entry["row_hash"]})
        loaded += 1
        if progress and (loaded % 300 == 0 or loaded == total):
            progress({"phase": "VERIFYING_SAVED_DATA", "verified_rows": loaded,
                      "rows_to_verify": total})
    return rows["train"], rows["validation"], report


def validation_segments(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    dates = sorted({row["session"] for row in rows})
    if len(dates) < 8:
        raise ValueError("at least eight validation dates required for separated calibration")
    midpoint = len(dates) // 2
    calibration_dates, selection_dates = set(dates[:midpoint]), set(dates[midpoint + 1:])
    # A complete date group is embargoed between calibration and model selection.
    return ([row for row in rows if row["session"] in calibration_dates],
            [row for row in rows if row["session"] in selection_dates])


def training_roster(artifacts: RawStore, calibration: list[dict], selection: list[dict]) -> dict:
    """Keep ordered full rosters immutable, outside bounded adapter messages."""
    manifest = {"schema": "research-training-roster/1",
                "calibration_rows": [row["row_hash"] for row in calibration],
                "selection_rows": [row["row_hash"] for row in selection]}
    return {"roster_manifest_hash": artifacts.put(manifest),
            "calibration_row_count": len(calibration), "selection_row_count": len(selection)}


def validate_training_roster(artifacts: RawStore, binding: dict) -> dict:
    manifest = artifacts.get(binding["roster_manifest_hash"])
    if (not isinstance(manifest, dict) or set(manifest) != {
            "schema", "calibration_rows", "selection_rows"}
            or manifest["schema"] != "research-training-roster/1"):
        raise ValueError("invalid training roster manifest")
    for segment in ("calibration", "selection"):
        hashes = manifest[f"{segment}_rows"]
        if (not isinstance(hashes, list) or not hashes
                or len(hashes) != binding[f"{segment}_row_count"]
                or any(not isinstance(key, str) or len(key) != 64
                       or any(char not in "0123456789abcdef" for char in key) for key in hashes)
                or len(set(hashes)) != len(hashes)):
            raise ValueError("training roster count or row identities changed")
    if set(manifest["calibration_rows"]) & set(manifest["selection_rows"]):
        raise ValueError("training roster segments overlap")
    return manifest


def train_real_models(data_dir: Path, contract: dict, authorization: dict, *,
                      progress=None) -> dict:
    pipeline = saved_pipeline(data_dir)
    train, validation, report = authorized_rows(
        pipeline, contract, authorization, progress=progress)
    calibration, selection = validation_segments(validation)
    artifacts = RawStore(data_dir / "research-models")
    report_hash = RawStore(data_dir / "datasets").put(report)
    binding = {"schema": RESEARCH_VERSION, "contract_hash": report["contract_hash"],
               "report_hash": report_hash, "authorization_hash": digest(authorization),
               "preprocessing_version": PREPROCESSING_VERSION,
               "news_mask_policy": authorization.get("news_mask_policy"),
               "max_text_features": 1024, "sklearn_version": version("scikit-learn"),
               "numpy_version": version("numpy"),
               "threadpoolctl_version": version("threadpoolctl"), "blas_threads": 2,
               "selection_rule": "validation_macro_f1_then_log_loss_then_name",
               **training_roster(artifacts, calibration, selection),
               "final_test_released": False, "paper_action_authorized": False}
    key = digest(binding)

    def check_roster():
        manifest = validate_training_roster(artifacts, binding)
        if (manifest["calibration_rows"] != [row["row_hash"] for row in calibration]
                or manifest["selection_rows"] != [row["row_hash"] for row in selection]):
            raise ValueError("training roster differs from verified saved rows")

    def fitted():
        # Bound CPU use and avoid BLAS oversubscription inside a finite harness lease.
        with threadpool_limits(limits=2):
            model = calibrate(fit_comparison(
                train, availability_tier="HISTORICAL_APPROXIMATE", max_text_features=1024,
                mask_previous_stories=authorization.get("news_mask_policy") == NEWS_MASK_POLICY),
                calibration)
            if "news_registry" in model:
                # Only after train-only weight/vocabulary fitting and calibration;
                # add selection INPUT history, never selection/test outcomes.
                extend_news_registry(model["news_registry"], selection)
            return model

    def fit(request):
        check_roster()
        if progress:
            progress({"phase": "FITTING_MODELS", "train_rows": len(train)})
        return {"model_hash": artifacts.put(fitted())}

    def evaluate(request):
        check_roster()
        if progress:
            progress({"phase": "EVALUATING_VALIDATION", "selection_rows": len(selection)})
        model = artifacts.get(request.dependencies["fit"]["model_hash"])
        evaluation = evaluate_comparison(model, selection, split="validation")
        return {"evaluation_hash": artifacts.put(evaluation)}

    def verify(request):
        try:
            check_roster()
            if progress:
                progress({"phase": "VERIFYING_MODELS", "train_rows": len(train)})
            model = artifacts.get(request.dependencies["fit"]["model_hash"])
            evaluation = artifacts.get(request.dependencies["evaluate"]["evaluation_hash"])
            if model != fitted() or evaluation != evaluate_comparison(
                    model, selection, split="validation"):
                raise ValueError("independent research replay mismatch")
            return VerifiedResult("PASS", request.goal_digest,
                                  {"train_rows": len(train), "final_test_opened": False,
                                   "paper_action_authorized": False})
        except (KeyError, TypeError, ValueError):
            return VerifiedResult("FAIL", request.goal_digest, {"reason": "research_check_failed"})
        except OSError:
            return VerifiedResult("UNKNOWN", request.goal_digest,
                                  {"reason": "research_artifact_unavailable"})

    adapters = [FunctionAdapter(AdapterCapabilities(f"marketpulse.real_{name}/1", kind, effect), fn)
                for name, kind, effect, fn in (
                    ("fit", "MODEL", "CANDIDATE_WRITE", fit),
                    ("evaluate", "TOOL", "CANDIDATE_WRITE", evaluate),
                    ("verify", "VERIFY", "PURE", verify))]
    goal = Goal("local-demo", f"marketpulse:real_training:{key}",
                "Verify authorized offline research models without deployment promotion",
                tuple(Task(name, f"marketpulse.real_{name}/1", binding, dependencies)
                      for name, dependencies in (("fit", ()), ("evaluate", ("fit",)),
                                                 ("verify", ("fit", "evaluate")))),
                ("verify",), allowed_effects=("PURE", "CANDIDATE_WRITE"), budget_units=6)
    harness = Harness(data_dir / "research-model-trailforge.sqlite3", tenant_id=goal.tenant_id,
                      resource_id=goal.resource_id, adapters=adapters, lease_seconds=300,
                      tenant_limit=100000, global_limit=1000000)
    index = ExtractionStore(data_dir / "research-model-jobs.sqlite3")
    index.reserve_job(key, "HISTORICAL_APPROXIMATE")
    prior = index.get_job(key)
    run_id = prior["run_id"] or harness.start(goal)
    if prior["run_id"] is None:
        index.set_run_id(key, run_id)
    record = harness.advance(run_id, goal)
    if record["state"] != "COMPLETED":
        index.set_status(key, record["state"])
        return {"state": record["state"], "run_id": run_id, "job_key": key}
    model_hash = record["tasks"]["fit"]["result"]["model_hash"]
    evaluation_hash = record["tasks"]["evaluate"]["result"]["evaluation_hash"]
    model = artifacts.get(model_hash)
    evaluation = artifacts.get(evaluation_hash)
    if set(evaluation["metrics"]) != set(MODEL_NAMES) or evaluation["model_hash"] != model_hash:
        raise ValueError("stored model/evaluation mismatch")
    selected = min(MODEL_NAMES, key=lambda name: (-evaluation["metrics"][name]["macro_f1"],
                                                evaluation["metrics"][name]["log_loss"], name))
    release = {"schema": RESEARCH_VERSION, "binding": binding, "contract": contract,
               "authorization": authorization, "model_hash": model_hash,
               "validation_report_hash": evaluation_hash, "selected_model": selected,
               "train_rows": len(train), "calibration_rows": len(calibration),
               "selection_rows": len(selection), "training_counts": dict(Counter(
                   row["label"] for row in train)), "run_id": run_id,
               "vocabulary_size": len(model["vocabulary"]),
               "availability_tier": "HISTORICAL_APPROXIMATE", "final_test_opened": False,
               "human_dataset_reviewed": False, "deployment_promoted": False,
               "rows_with_interior_minute_gaps": len(report["outcome_interior_gaps"]),
               "paper_action_authorized": False,
               "trailforge_verify_receipt": record["tasks"]["verify"]["receipt"]["receipt_id"]}
    if "news_registry" in model:
        release["news_mask_policy"] = NEWS_MASK_POLICY
        release["masked_story_instances"] = {
            split: sum(len(row["news"]) - len(mask_seen_stories(
                model["news_registry"], row["news"], row["session"])) for row in rows)
            for split, rows in (("train", train), ("calibration", calibration),
                                ("selection", selection))}
    release_hash = artifacts.put(release)
    with index.connect() as db:
        db.execute("UPDATE extraction_jobs SET status='COMPLETE',manifest_json=? WHERE job_key=?",
                   (canonical_bytes({"release_hash": release_hash}).decode(), key))
    return {"state": "COMPLETE", "release_hash": release_hash, **release}


def predict_real_research(data_dir: Path, release_hash: str, symbol: str, session: str) -> dict:
    artifacts = RawStore(data_dir / "research-models")
    release = artifacts.get(release_hash)
    if (release.get("schema") != RESEARCH_VERSION or release.get("deployment_promoted") is not False
            or release.get("paper_action_authorized") is not False
            or symbol not in release["contract"]["symbols"]):
        raise ValueError("incompatible research release or ticker")
    binding = release["binding"]
    key = digest(binding)
    harness = Harness(data_dir / "research-model-trailforge.sqlite3", tenant_id="local-demo",
                      resource_id=f"marketpulse:real_training:{key}", adapters=[],
                      tenant_limit=100000, global_limit=1000000)
    record = harness.inspect(release["run_id"])
    verified = record["tasks"]["verify"]
    index = ExtractionStore(data_dir / "research-model-jobs.sqlite3")
    job = index.get_job(key)
    if (record["state"] != "COMPLETED" or (verified.get("result") or {}).get("verdict") != "PASS"
            or (verified.get("receipt") or {}).get("receipt_id")
            != release.get("trailforge_verify_receipt")
            or record["goal"]["tasks"][-1]["input"] != binding
            or record["tasks"]["fit"]["result"]["model_hash"] != release["model_hash"]
            or record["tasks"]["evaluate"]["result"]["evaluation_hash"]
            != release["validation_report_hash"]
            or not job or job["status"] != "COMPLETE"
            or json.loads(job["manifest_json"]) != {"release_hash": release_hash}):
        raise ValueError("research release lacks compatible passing harness authority")
    if "roster_manifest_hash" in binding:
        # Legacy releases retain their original inline binding. New releases must
        # retain the independently hash-checked manifest used by the fit/verifier.
        manifest = validate_training_roster(artifacts, binding)
        candidate = artifacts.get(release["model_hash"])
        evaluation = artifacts.get(release["validation_report_hash"])
        if (manifest["selection_rows"] != evaluation["row_hashes"]
                or any(manifest["calibration_rows"] != value["row_hashes"]
                       for value in candidate["calibrators"].values())):
            raise ValueError("research model calibration/evaluation roster mismatch")
    pipeline = saved_pipeline(data_dir)
    with pipeline.store.connect() as db:
        found = db.execute(
            "SELECT s.snapshot_hash FROM snapshots s JOIN extraction_jobs j "
            "ON j.job_key=s.job_key WHERE s.session=? AND s.symbol=? AND j.status='COMPLETE' "
            "AND json_extract(j.manifest_json,'$.feed')=? "
            "AND json_extract(j.manifest_json,'$.adjustment')=?",
            (session, symbol, release["contract"]["feed"],
             release["contract"]["adjustment"])).fetchall()
    if len(found) != 1:
        raise ValueError("research prediction requires one unambiguous saved input snapshot")
    snapshot, source, company, spy, articles = _load_snapshot(data_dir, found[0][0])
    _verify_input_receipt(pipeline, {"source_job_key": snapshot["job_key"], "session": session},
                          frozen_identity(release["contract"], pipeline))
    features = build_features(snapshot, source, company, spy, articles)
    model = artifacts.get(release["model_hash"])
    scores = score_comparison(model, {"features": features, "news": articles})
    name = release["selected_model"]
    probabilities = dict(zip(CLASSES, scores[name]))
    return {"schema": RESEARCH_VERSION, "release_hash": release_hash, "symbol": symbol,
            "session": date.fromisoformat(session).isoformat(), "model": name,
            "probabilities": probabilities, "class": _choose(scores[name]),
            "snapshot_hash": found[0][0], "availability_tier": "HISTORICAL_APPROXIMATE",
            "news_mask_policy": model.get("news_mask_policy"),
            "news_history_scope": "frozen_training_and_validation_inputs",
            "research_only": True, "outcome_loaded": False, "paper_action_authorized": False}
