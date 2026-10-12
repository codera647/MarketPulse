"""Frozen retrospective final test: persist predictions before opening outcomes."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

from threadpoolctl import threadpool_limits
from trailforge.ports import AdapterCapabilities, FunctionAdapter, VerifiedResult
from trailforge.runtime import Goal, Harness, Task

from marketpulse.baselines import CLASSES, _choose
from marketpulse.dataset import frozen_identity, make_row, split_sessions, validate_contract
from marketpulse.features import _load_snapshot, build_features
from marketpulse.modeling import MODEL_NAMES, chronological_scores, summarize_comparison
from marketpulse.outcomes import validate_saved_outcome
from marketpulse.preprocessing import NEWS_MASK_POLICY
from marketpulse.real_training import load_research_release, research_report_ready
from marketpulse.research import _verify_input_receipt, saved_pipeline
from marketpulse.storage import ExtractionStore, RawStore, canonical_bytes, digest

TEST_VERSION = "research-final-test/1"


def test_roster(pipeline, release: dict) -> tuple[dict, dict, list[dict]]:
    """Only metadata/index checks here: do not open dataset rows or outcome pages."""
    contract = release["contract"]
    validate_contract(contract, require_approval=True)
    identity = frozen_identity(contract, pipeline)
    key = digest(identity)
    report = RawStore(pipeline.data_dir / "datasets").get(release["binding"]["report_hash"])
    if (key != release["binding"]["contract_hash"]
            or RawStore(pipeline.data_dir / "contracts").get(key) != identity
            or report["contract_hash"] != key
            or not research_report_ready(report, mask_previous_stories=
                                         release.get("news_mask_policy") == NEWS_MASK_POLICY)):
        raise ValueError("test requires the complete authorized frozen dataset")
    excluded = {entry["session"] for entry in report.get("exclusions", [])}
    expected = {(day, symbol, split) for day, split in split_sessions(contract).items()
                for symbol in contract["symbols"] if day not in excluded}
    observed = [(entry["session"], entry["symbol"], entry["split"]) for entry in report["rows"]]
    if len(observed) != len(expected) or set(observed) != expected:
        raise ValueError("test dataset roster differs from frozen complete date groups")
    with pipeline.store.connect() as db:
        exclusions = [dict(row) for row in db.execute(
            "SELECT session,exclusion_hash FROM dataset_exclusions WHERE contract_hash=? "
            "ORDER BY session", (key,))]
        index = {(row["session"], row["symbol"]): row["row_hash"] for row in db.execute(
            "SELECT session,symbol,row_hash FROM dataset_rows WHERE contract_hash=?", (key,))}
    if (exclusions != report.get("exclusions", [])
            or index != {(row["session"], row["symbol"]): row["row_hash"]
                         for row in report["rows"]}):
        raise ValueError("test roster/exclusions no longer match audited source index")
    roster = [row for row in report["rows"] if row["split"] == "test"]
    if not roster:
        raise ValueError("no usable final-test rows")
    return identity, report, roster


def test_inputs(pipeline, identity: dict, roster: list[dict], *, progress=None) -> list[dict]:
    """Hydrate snapshots only. No labeled row artifacts/outcome sources are read."""
    with pipeline.store.connect() as db:
        snapshots = list(db.execute(
            "SELECT s.session,s.symbol,s.snapshot_hash FROM snapshots s JOIN extraction_jobs j "
            "ON j.job_key=s.job_key WHERE j.status='COMPLETE' "
            "AND json_extract(j.manifest_json,'$.feed')=? "
            "AND json_extract(j.manifest_json,'$.adjustment')=?",
            (identity["contract"]["feed"], identity["contract"]["adjustment"])))
    selected = {}
    wanted = {(row["session"], row["symbol"]) for row in roster}
    for found in snapshots:
        group = (found["session"], found["symbol"])
        if group in wanted:
            if group in selected:
                raise ValueError("ambiguous saved test input snapshot")
            selected[group] = found["snapshot_hash"]
    if set(selected) != wanted:
        raise ValueError("missing saved test input snapshots")
    inputs, checked = [], set()
    for entry in roster:
        key = selected[(entry["session"], entry["symbol"])]
        snapshot, source, company, spy, articles = _load_snapshot(pipeline.data_dir, key)
        row = {**entry, "snapshot_hash": key, "source_job_key": snapshot["job_key"],
               "features": build_features(snapshot, source, company, spy, articles),
               "news": [{"version_hash": article["version_hash"],
                         "provider_id": article["provider_id"], "headline": article["headline"],
                         "summary": article["summary"], "created_at": article["created_at"],
                         "updated_at": article["updated_at"],
                         "raw_page_digest": article["job_raw_page_digest"],
                         "headline_group": digest(" ".join(
                             article["headline"].casefold().split()))} for article in articles]}
        if row["source_job_key"] not in checked:
            _verify_input_receipt(pipeline, row, identity)
            checked.add(row["source_job_key"])
        inputs.append(row)
        if progress and (len(inputs) % 100 == 0 or len(inputs) == len(roster)):
            progress({"phase": "VERIFYING_TEST_INPUTS", "verified_rows": len(inputs),
                      "rows_to_verify": len(roster)})
    return inputs


def test_outcomes(pipeline, release: dict, inputs: list[dict]) -> list[dict]:
    """Only the post-prediction evaluation path may open fixed test labels."""
    artifacts = RawStore(pipeline.data_dir / "datasets")
    rows, outcomes = [], {}
    for item in inputs:
        row = artifacts.get(item["row_hash"])
        if (any(row.get(field) != item[field] for field in
                ("session", "symbol", "split", "snapshot_hash", "source_job_key",
                 "features", "news"))
                or row["contract_hash"] != release["binding"]["contract_hash"]):
            raise ValueError("test label row disagrees with committed input identity")
        job = pipeline.store.get_job(row["outcome_job_key"])
        if not job or job["status"] != "COMPLETE":
            raise ValueError("test outcome lacks completed source evidence")
        outcome = json.loads(job["manifest_json"])
        key = digest(outcome)
        if key not in outcomes:
            outcomes[key] = validate_saved_outcome(pipeline, outcome)
        if make_row(pipeline, row["snapshot_hash"], outcome, row["contract_hash"],
                    release["contract"], "test", verified_outcome=(key, outcomes[key])) != row:
            raise ValueError("test label no longer matches verified price boundaries")
        rows.append({**row, "row_hash": item["row_hash"]})
    return rows


def _run_final_test(data_dir: Path, release_hash: str, evidence: str, checkpoint) -> dict:
    release = load_research_release(data_dir, release_hash)
    for library, field in (("numpy", "numpy_version"), ("scikit-learn", "sklearn_version")):
        if version(library) != release["binding"][field]:
            raise ValueError("final test must use frozen numerical library versions")
    pipeline = saved_pipeline(data_dir)
    identity, report, roster = test_roster(pipeline, release)
    artifacts = RawStore(data_dir / "research-evaluations")
    freeze = {"schema": TEST_VERSION, "release_hash": release_hash,
              "model_hash": release["model_hash"], "selected_model": release["selected_model"],
              "validation_report_hash": release["validation_report_hash"],
              "contract_hash": report["contract_hash"],
              "report_hash": release["binding"]["report_hash"],
              "test_roster": roster, "comparison_models": list(MODEL_NAMES),
              "news_history": "chronological_input_only", "refit_allowed": False,
              "reselection_allowed": False, "paper_action_authorized": False,
              "bootstrap": {"unit": "date", "samples": 100, "seed": 123},
              "earlier_source_qa_may_overlap": True}
    freeze_hash = artifacts.put(freeze)  # Persist the plan BEFORE any final-test row/label read.
    index = ExtractionStore(data_dir / "research-evaluation-jobs.sqlite3")
    with index.connect() as db:
        db.execute("CREATE TABLE IF NOT EXISTS final_test_locks (contract_hash TEXT PRIMARY KEY, "
                   "freeze_hash TEXT NOT NULL, opened_at_utc TEXT NOT NULL, "
                   "evidence_hash TEXT NOT NULL)")
        authorization_hash = artifacts.put({"schema": "research-test-authorization/1",
                                            "freeze_hash": freeze_hash, "evidence": evidence})
        db.execute("INSERT OR IGNORE INTO final_test_locks VALUES (?,?,?,?)",
                   (report["contract_hash"], freeze_hash, datetime.now(timezone.utc).isoformat(),
                    authorization_hash))
        prior = db.execute("SELECT freeze_hash FROM final_test_locks WHERE contract_hash=?",
                           (report["contract_hash"],)).fetchone()
        if prior[0] != freeze_hash:
            raise ValueError("this final test is already frozen to another release or plan")
    checkpoint({"stage": "EVALUATING", "phase": "VERIFYING_TEST_INPUTS",
                "freeze_hash": freeze_hash, "test_rows": len(roster)})
    inputs = test_inputs(pipeline, identity, roster, progress=lambda event: checkpoint({
        "stage": "EVALUATING", "freeze_hash": freeze_hash, **event}))
    input_hash = artifacts.put(inputs)
    binding = {"schema": TEST_VERSION, "freeze_hash": freeze_hash, "input_hash": input_hash,
               "release_hash": release_hash, "test_rows": len(inputs), "blas_threads": 2}
    key = digest(binding)
    model_store = RawStore(data_dir / "research-models")

    def predictions():
        model = model_store.get(release["model_hash"])
        with threadpool_limits(limits=2):
            probabilities = chronological_scores(model, artifacts.get(input_hash))
        if digest(model) != release["model_hash"]:
            raise ValueError("final-test scoring mutated the frozen model")
        return {"schema": TEST_VERSION, "freeze_hash": freeze_hash, "model_hash": digest(model),
                "input_hash": input_hash, "row_hashes": [row["row_hash"] for row in inputs],
                "probabilities": probabilities, "outcomes_loaded": False}

    def evaluate_from(committed):
        if committed != predictions():
            raise ValueError("saved test predictions disagree with frozen input-only replay")
        # This runs only AFTER the predict task has durably committed its digest.
        rows = test_outcomes(pipeline, release, inputs)
        model = model_store.get(release["model_hash"])
        with threadpool_limits(limits=2):
            result = summarize_comparison(model, rows, committed["probabilities"], split="test")
        result.update({"freeze_hash": freeze_hash, "selected_model": release["selected_model"],
                       "selection_unchanged": True, "retraining_performed": False,
                       "final_test_opened": True, "paper_action_authorized": False,
                       "dates": len({row["session"] for row in rows}),
                       "first_session": min(row["session"] for row in rows),
                       "last_session": max(row["session"] for row in rows),
                       "by_ticker": {}, "per_class": {},
                       "earlier_source_qa_may_overlap": True})
        from marketpulse.modeling import metrics

        for symbol in release["contract"]["symbols"]:
            indices = [i for i, row in enumerate(rows) if row["symbol"] == symbol]
            result["by_ticker"][symbol] = metrics([rows[i]["label"] for i in indices],
                [committed["probabilities"][i][release["selected_model"]] for i in indices])
        for name in MODEL_NAMES:
            matrix = result["metrics"][name]["confusion_matrix"]
            result["per_class"][name] = {
                label: {"support": sum(matrix[i]),
                        "recall": matrix[i][i] / sum(matrix[i]) if sum(matrix[i]) else 0.0,
                        "precision": matrix[i][i] / sum(row[i] for row in matrix)
                        if sum(row[i] for row in matrix) else 0.0}
                for i, label in enumerate(CLASSES)}
        # Named selected probabilities are not replaced by a test-set winner.
        result["selected_prediction_counts"] = dict(Counter(
            _choose(item[release["selected_model"]]) for item in committed["probabilities"]))
        return result

    def predict(request):
        checkpoint({"stage": "EVALUATING", "phase": "COMMITTING_TEST_PREDICTIONS"})
        return {"prediction_hash": artifacts.put(predictions())}

    def evaluate(request):
        committed = artifacts.get(request.dependencies["predict"]["prediction_hash"])
        checkpoint({"stage": "EVALUATING", "phase": "SCORING_TEST_OUTCOMES"})
        return {"evaluation_hash": artifacts.put(evaluate_from(committed))}

    def verify(request):
        checkpoint({"stage": "EVALUATING", "phase": "VERIFYING_TEST_RESULTS"})
        try:
            if load_research_release(data_dir, release_hash) != release:
                raise ValueError("training release changed after test freeze")
            if test_inputs(pipeline, identity, roster) != inputs:
                raise ValueError("test input lineage changed")
            committed = artifacts.get(request.dependencies["predict"]["prediction_hash"])
            saved = artifacts.get(request.dependencies["evaluate"]["evaluation_hash"])
            if saved != evaluate_from(committed):
                raise ValueError("independent test evaluation replay differs")
            return VerifiedResult("PASS", request.goal_digest,
                                  {"test_rows": len(inputs), "model_unchanged": True,
                                   "selection_unchanged": True, "paper_action_authorized": False})
        except (ValueError, KeyError, TypeError):
            return VerifiedResult("FAIL", request.goal_digest, {"reason": "test_replay_failed"})
        except OSError:
            return VerifiedResult("UNKNOWN", request.goal_digest,
                                  {"reason": "test_artifact_missing"})

    adapters = [FunctionAdapter(
        AdapterCapabilities(f"marketpulse.real_test_{name}/1", kind, effect), fn)
                for name, kind, effect, fn in (
                    ("predict", "MODEL", "CANDIDATE_WRITE", predict),
                    ("evaluate", "TOOL", "CANDIDATE_WRITE", evaluate),
                    ("verify", "VERIFY", "PURE", verify))]
    goal = Goal("local-demo", f"marketpulse:research_test:{key}",
                "Evaluate frozen models on the final test without refitting or reselection",
                tuple(Task(name, f"marketpulse.real_test_{name}/1", binding, dependencies)
                      for name, dependencies in (("predict", ()), ("evaluate", ("predict",)),
                                                 ("verify", ("predict", "evaluate")))),
                ("verify",), allowed_effects=("PURE", "CANDIDATE_WRITE"), budget_units=6)
    harness = Harness(data_dir / "research-evaluation-trailforge.sqlite3", tenant_id=goal.tenant_id,
                      resource_id=goal.resource_id, adapters=adapters, lease_seconds=300,
                      tenant_limit=100000, global_limit=1000000)
    index.reserve_job(key, "HISTORICAL_APPROXIMATE")
    prior = index.get_job(key)
    run_id = prior["run_id"] or harness.start(goal)
    if prior["run_id"] is None:
        index.set_run_id(key, run_id)
    record = harness.advance(run_id, goal)
    if record["state"] != "COMPLETED":
        index.set_status(key, record["state"])
        return {"state": record["state"], "run_id": run_id, "freeze_hash": freeze_hash}
    result = {"schema": TEST_VERSION, "state": "COMPLETE", "release_hash": release_hash,
              "freeze_hash": freeze_hash, "selected_model": release["selected_model"],
              "run_id": run_id, "test_rows": len(inputs), "final_test_opened": True,
              "model_hash": release["model_hash"], "paper_action_authorized": False,
              "prediction_hash": record["tasks"]["predict"]["result"]["prediction_hash"],
              "evaluation_hash": record["tasks"]["evaluate"]["result"]["evaluation_hash"],
              "verify_receipt": record["tasks"]["verify"]["receipt"]["receipt_id"]}
    result["test_release_hash"] = artifacts.put(result)
    with index.connect() as db:
        db.execute("UPDATE extraction_jobs SET status='COMPLETE',manifest_json=? WHERE job_key=?",
                   (canonical_bytes(result).decode(), key))
    return result


def evaluate_real_research(data_dir: Path, release_hash: str, *, evidence: str,
                           progress=None) -> dict:
    if not isinstance(evidence, str) or not 1 <= len(evidence.strip()) <= 500:
        raise ValueError("record explicit authorization to open the held-out research test")
    artifacts = RawStore(data_dir / "research-evaluations")
    latest = data_dir / "real-evaluation-status.json"

    def checkpoint(value):
        event = {"release_hash": release_hash,
                 "updated_at_utc": datetime.now(timezone.utc).isoformat(), **value}
        candidate = latest.with_suffix(".tmp")
        candidate.write_text(json.dumps(event, sort_keys=True, indent=2), encoding="utf-8")
        candidate.replace(latest)
        if progress:
            progress(event)

    lock = data_dir / "research-final-test.lock"
    with lock.open("x", encoding="utf-8") as handle:
        handle.write(release_hash)
    try:
        checkpoint({"stage": "FREEZING_TEST"})
        try:
            result = _run_final_test(data_dir, release_hash, evidence, checkpoint)
        except Exception as error:
            checkpoint({"stage": "TEST_ERROR", "error_type": type(error).__name__,
                        "state": "STOPPED", "authority_reset": False})
            raise
        checkpoint({"stage": result["state"], **result})
        artifacts.put(result)
        return result
    finally:
        lock.unlink()
