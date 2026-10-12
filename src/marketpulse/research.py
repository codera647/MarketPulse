"""Bounded collection orchestration, explicit human promotion, and research training."""

from __future__ import annotations

import json
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from trailforge.runtime import Harness

from marketpulse.clock import parse_time, session_window
from marketpulse.constants import STOCKS
from marketpulse.dataset import (
    DATASET_CONTRACT,
    dataset_report,
    frozen_identity,
    make_row,
    run_dataset_batch,
    split_sessions,
    validate_contract,
)
from marketpulse.extraction import CONTRACT_VERSION, ExtractionPipeline
from marketpulse.storage import RawStore, digest

PIPELINE_VERSION = "research-pipeline/1"
REVIEW_VERSION = "dataset-review/1"
PROMOTION_VERSION = "dataset-promotion/1"
REVIEW_CHECKS = {"corporate_actions", "semantic_events", "outcome_gaps",
                 "historical_approximation"}


class OfflineClient:
    base_url = "https://data.alpaca.markets"

    def pages(self, *args, **kwargs):
        raise ValueError("offline dataset review/training cannot request provider data")


def saved_pipeline(data_dir: Path) -> ExtractionPipeline:
    if not (data_dir / "marketpulse.sqlite3").is_file():
        raise ValueError("collect a dataset before reviewing or training")
    if not (data_dir / "trailforge.sqlite3").is_file():
        raise ValueError("dataset harness authority is missing")
    return ExtractionPipeline(data_dir, OfflineClient())


def collection_plan(contract: dict, *, batch_sessions: int = 20) -> dict:
    validate_contract(contract)
    if type(batch_sessions) is not int or not 1 <= batch_sessions <= 31:
        raise ValueError("batch size must be 1 to 31 exchange sessions")
    sessions = split_sessions(contract)
    batches, pending = [], []
    for day in sessions:
        if pending and (len(pending) == batch_sessions or
                        (date.fromisoformat(day) - date.fromisoformat(pending[0])).days > 60):
            batches.append(pending)
            pending = []
        pending.append(day)
    if pending:
        batches.append(pending)
    return {
        "schema": PIPELINE_VERSION, "sessions_by_split": dict(Counter(sessions.values())),
        "expected_rows": len(sessions) * len(STOCKS),
        "batches": [{"start": days[0], "end": days[-1], "sessions": len(days)}
                    for days in batches],
        "batch_sessions": batch_sessions, "plan_approved": contract["plan_approved"],
        "rights_confirmed": contract["rights_confirmed"], "network_used": False,
        "ready_for_training": False,
    }


def _report_result(pipeline: ExtractionPipeline, identity: dict, report: dict) -> dict:
    report_hash = RawStore(pipeline.data_dir / "datasets").put(report)
    return {"contract_hash": digest(identity), "report_hash": report_hash,
            "status": report["status"], "accepted_rows": report["accepted_rows"],
            "expected_rows": report["expected_rows"], "ready_for_training": False}


def inspect_dataset(pipeline: ExtractionPipeline, contract: dict) -> dict:
    validate_contract(contract)
    identity = frozen_identity(contract, pipeline)
    if RawStore(pipeline.data_dir / "contracts").get(digest(identity)) != identity:
        raise ValueError("saved contract identity mismatch")
    return _report_result(pipeline, identity, dataset_report(pipeline, identity))


def collect_dataset(pipeline: ExtractionPipeline, contract: dict, *, batch_sessions: int = 20,
                    max_batches: int = 1, progress=None, audit_each_batch: bool = True,
                    workers: int = 1, pipeline_factory=None,
                    allow_story_duplicates: bool = False) -> dict:
    """Resume verified missing dates; stop at the first failure/hold or explicit budget."""
    validate_contract(contract, require_approval=True)
    if type(allow_story_duplicates) is not bool:
        raise ValueError("story-duplicate collection override must be explicit")
    if type(workers) is not int or not 1 <= workers <= 3:
        raise ValueError("collection needs one to three workers")
    if workers > 1 and pipeline_factory is None:
        raise ValueError("parallel collection requires isolated provider sessions")
    plan = collection_plan(contract, batch_sessions=batch_sessions)
    if type(max_batches) is not int or not 1 <= max_batches <= 50:
        raise ValueError("collection budget must be 1 to 50 batches")
    days = split_sessions(contract)
    # All dates use one exchange calendar and are chronological. If the latest
    # planned close is safely in the past, every earlier planned close is too.
    # Avoid thousands of redundant holiday-calendar constructions in a large run.
    if pipeline.clock() <= session_window(date.fromisoformat(max(days))).market_close \
            + timedelta(minutes=15):
        raise ValueError("all planned sessions must be closed more than 15 minutes ago")
    identity = frozen_identity(contract, pipeline)
    RawStore(pipeline.data_dir / "contracts").put(identity)
    report = dataset_report(pipeline, identity)
    completed_batches = []
    missing_days = {row["session"] for row in report["missing_rows"]}
    for batch in plan["batches"]:
        duplicate_only = (not report["lineage_errors"] and not report.get("batch_failures")
                          and bool(report["leakage"]["provider_ids_crossing_splits"]
                                   or report["leakage"]["headline_groups_crossing_splits"]))
        if report["status"] == "INTEGRITY_BLOCKED" and not (
                allow_story_duplicates and duplicate_only):
            break
        eligible = [day for day in days if batch["start"] <= day <= batch["end"]
                    and day in missing_days]
        if not eligible:
            continue
        if len(completed_batches) >= max_batches:
            break
        result = run_dataset_batch(pipeline, contract, date.fromisoformat(eligible[0]),
                                   date.fromisoformat(eligible[-1]), audit=audit_each_batch,
                                   progress=progress, workers=workers,
                                   pipeline_factory=pipeline_factory)
        completed_batches.append(result)
        if audit_each_batch:
            report = RawStore(pipeline.data_dir / "datasets").get(result["report_hash"])
            missing_days = {row["session"] for row in report["missing_rows"]}
        else:
            missing_days.difference_update(eligible)
        if progress:
            progress({"batch": len(completed_batches), "status": result["status"],
                      "accepted_rows": result["accepted_rows"],
                      "expected_rows": result["expected_rows"]})
        if result["batch_failures"] or result["status"] == "INTEGRITY_BLOCKED":
            break
    if not audit_each_batch:
        report = dataset_report(pipeline, identity)
        failures = [failure for batch in completed_batches for failure in batch["batch_failures"]]
        if failures:
            report["batch_failures"] = failures
            report["status"] = "BATCH_BLOCKED"
    result = {"schema": PIPELINE_VERSION, **_report_result(pipeline, identity, report),
              "batches_this_run": len(completed_batches), "max_batches": max_batches,
              "batch_results": completed_batches, "final_test_metrics_emitted": False,
              "training_started": False}
    return {**result, "pipeline_result_hash":
            RawStore(pipeline.data_dir / "pipeline-results").put(result)}


def load_review(path: Path) -> dict:
    if not path.is_file() or path.stat().st_size > 16384:
        raise ValueError("review must be a JSON file below 16 KiB")

    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("duplicate review key")
            value[key] = item
        return value

    review = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique)
    validate_review(review)
    return review


def validate_review(review: dict) -> None:
    if (not isinstance(review, dict) or set(review) != {
            "schema", "contract_hash", "report_hash", "reviewer", "reviewed_at_utc",
            "approved", "checks"} or review["schema"] != REVIEW_VERSION
            or review["approved"] is not True):
        raise ValueError("explicit human dataset review approval is required")
    for name in ("contract_hash", "report_hash"):
        value = review[name]
        if (not isinstance(value, str) or len(value) != 64
                or any(char not in "0123456789abcdef" for char in value)):
            raise ValueError("review must bind full dataset/report hashes")
    if (not isinstance(review["reviewer"], str)
            or not 1 <= len(review["reviewer"].strip()) <= 120):
        raise ValueError("record a reviewer identifier, not private account information")
    if (not isinstance(review["checks"], dict) or set(review["checks"]) != REVIEW_CHECKS
            or any(not isinstance(value, str) or not 1 <= len(value.strip()) <= 500
                   for value in review["checks"].values())):
        raise ValueError("all quality checks need short non-secret evidence references")
    reviewed = parse_time(review["reviewed_at_utc"])
    if reviewed > datetime.now(timezone.utc):
        raise ValueError("review cannot be dated in the future")


def promote_dataset(pipeline: ExtractionPipeline, contract: dict, review: dict, *,
                    news_models: bool = False) -> dict:
    """Record a human decision, never manufacture rights or auto-approve quality."""
    validate_contract(contract, require_approval=True)
    validate_review(review)
    identity = frozen_identity(contract, pipeline)
    if review["contract_hash"] != digest(identity):
        raise ValueError("review belongs to a different dataset identity")
    if RawStore(pipeline.data_dir / "contracts").get(digest(identity)) != identity:
        raise ValueError("saved contract identity mismatch")
    stored = RawStore(pipeline.data_dir / "datasets").get(review["report_hash"])
    report = dataset_report(pipeline, identity)
    if (stored.get("batch_failures") or
            {key: value for key, value in stored.items() if key != "batch_failures"} != report
            or report["status"] != "COMPLETE_RESEARCH_REVIEW_REQUIRED"):
        raise ValueError("promotion needs a complete, current, integrity-checked report")
    promotion = {"schema": PROMOTION_VERSION, "contract_hash": digest(identity),
                 "report_hash": review["report_hash"], "review": review,
                 "availability_tier": "HISTORICAL_APPROXIMATE",
                 "purpose": ("MAJORITY_PRICE_NEWS_VALIDATION_ONLY" if news_models else
                             "MAJORITY_PRICE_VALIDATION_ONLY"), "final_test_released": False,
                 "paper_action_authorized": False}
    key = RawStore(pipeline.data_dir / "promotions").put(promotion)
    return {"promotion_hash": key, "contract_hash": digest(identity),
            "status": "PROMOTED_FOR_BASELINE_RESEARCH", "final_test_released": False,
            "paper_action_authorized": False}


def reviewed_rows(pipeline: ExtractionPipeline, contract: dict,
                  promotion_hash: str) -> tuple[list[dict], list[dict]]:
    """Validate complete roster; rehydrate train/validation only. No test row reads."""
    validate_contract(contract, require_approval=True)
    promotion = RawStore(pipeline.data_dir / "promotions").get(promotion_hash)
    identity = frozen_identity(contract, pipeline)
    key = digest(identity)
    if RawStore(pipeline.data_dir / "contracts").get(key) != identity:
        raise ValueError("saved contract identity mismatch")
    validate_review(promotion["review"])
    if (promotion.get("schema") != PROMOTION_VERSION or promotion.get("contract_hash") != key
            or promotion["review"]["contract_hash"] != key
            or promotion["review"]["report_hash"] != promotion["report_hash"]
            or promotion.get("availability_tier") != "HISTORICAL_APPROXIMATE"
            or promotion.get("purpose") not in {"MAJORITY_PRICE_VALIDATION_ONLY",
                                                "MAJORITY_PRICE_NEWS_VALIDATION_ONLY"}
            or promotion.get("final_test_released") is not False
            or promotion.get("paper_action_authorized") is not False):
        raise ValueError("dataset promotion is missing, incompatible or unauthorized")
    store = RawStore(pipeline.data_dir / "datasets")
    report = store.get(promotion["report_hash"])
    if (report.get("schema") != DATASET_CONTRACT or report.get("contract_hash") != key
            or report.get("status") != "COMPLETE_RESEARCH_REVIEW_REQUIRED"
            or report.get("missing_rows") or report.get("lineage_errors")
            or report.get("batch_failures")
            or report["leakage"]["provider_ids_crossing_splits"]
            or report["leakage"]["headline_groups_crossing_splits"]):
        raise ValueError("promoted report has unresolved integrity or coverage failures")
    expected = {(day, symbol, split) for day, split in split_sessions(contract).items()
                for symbol in STOCKS}
    entries = report["rows"]
    roster = [(entry["session"], entry["symbol"], entry["split"]) for entry in entries]
    if (len(roster) != len(expected) or set(roster) != expected
            or len({entry["row_hash"] for entry in entries}) != len(entries)
            or report["accepted_rows"] != len(expected)
            or report["expected_rows"] != len(expected)):
        raise ValueError("promoted roster must have every six-company date group exactly once")
    with pipeline.store.connect() as db:
        current = {(entry["session"], entry["symbol"]): entry["row_hash"] for entry in db.execute(
            "SELECT session,symbol,row_hash FROM dataset_rows WHERE contract_hash=?", (key,))}
    if current != {(entry["session"], entry["symbol"]): entry["row_hash"] for entry in entries}:
        raise ValueError("dataset row index differs from the promoted roster")
    results = {"train": [], "validation": []}
    checked_sources = set()
    verified_outcomes = {}
    for entry in entries:
        if entry["split"] == "test":
            continue  # Do not load or recompute test rows/outcomes in a learning workflow.
        row = store.get(entry["row_hash"])
        if (any(row.get(name) != entry[name] for name in ("session", "symbol", "split"))
                or row.get("contract_hash") != key):
            raise ValueError("promoted row identity mismatch")
        if row["source_job_key"] not in checked_sources:
            _verify_input_receipt(pipeline, row, identity)
            checked_sources.add(row["source_job_key"])
        job = pipeline.store.get_job(row["outcome_job_key"])
        if not job or job["status"] != "COMPLETE":
            raise ValueError("reviewed outcome job is missing")
        from marketpulse.outcomes import validate_saved_outcome

        outcome = json.loads(job["manifest_json"])
        outcome_key = digest(outcome)
        if outcome_key not in verified_outcomes:
            verified_outcomes[outcome_key] = validate_saved_outcome(pipeline, outcome)
        rebuilt = make_row(pipeline, row["snapshot_hash"], outcome,
                           key, contract, entry["split"],
                           verified_outcome=(outcome_key, verified_outcomes[outcome_key]))
        if rebuilt != row:
            raise ValueError("promoted row no longer matches source lineage")
        results[entry["split"]].append({**row, "row_hash": entry["row_hash"]})
    return tuple(sorted(results[split], key=lambda row: (row["session"], row["symbol"]))
                 for split in ("train", "validation"))


def _verify_input_receipt(pipeline: ExtractionPipeline, row: dict, identity: dict) -> None:
    job = pipeline.store.get_job(row["source_job_key"])
    if not job or job["status"] != "COMPLETE":
        raise ValueError("input job is missing")
    source = json.loads(job["manifest_json"])
    harness = Harness(pipeline.harness_path, tenant_id="local-demo",
                      resource_id=f"marketpulse:extract:{row['source_job_key']}", adapters=[],
                      tenant_limit=100000, global_limit=1000000)
    record = harness.inspect(job["run_id"])
    verified = record["tasks"]["verify"]
    binding = record["goal"]["tasks"][-1]["input"]
    if (record["state"] != "COMPLETED" or verified.get("result", {}).get("verdict") != "PASS"
            or source.get("job_key") != row["source_job_key"]
            or source.get("run_id") != job["run_id"]
            or source.get("trailforge_receipts", {}).get("verify")
            != verified.get("receipt", {}).get("receipt_id")
            or not source.get("trailforge_receipts", {}).get("verify")
            or digest(binding) != row["source_job_key"]
            or binding.get("contract") != CONTRACT_VERSION
            or binding.get("data_url") != identity["data_url"]
            or binding.get("session") != row["session"]
            or binding.get("feed") != identity["contract"]["feed"]
            or binding.get("adjustment") != identity["contract"]["adjustment"]
            or binding.get("mode") != "historical" or binding.get("include_content") is not False
            or binding.get("web_urls") != [] or binding.get("min_prior_bars") != 21):
        raise ValueError("input lacks compatible passing Trailforge evidence")


def train_reviewed_baselines(pipeline: ExtractionPipeline, contract: dict,
                             promotion_hash: str) -> dict:
    from marketpulse.baselines import _run_baseline_experiment

    # Validate before starting a model harness or writing any candidate model.
    reviewed_rows(pipeline, contract, promotion_hash)
    return _run_baseline_experiment(
        pipeline.data_dir / "research-baselines", promotion_hash,
        lambda: reviewed_rows(pipeline, contract, promotion_hash),
        availability_tier="HISTORICAL_APPROXIMATE",
        dataset_binding={"pipeline_version": PIPELINE_VERSION,
                         "contract_hash": digest(frozen_identity(contract, pipeline)),
                         "promotion_hash": promotion_hash, "final_test_released": False})
