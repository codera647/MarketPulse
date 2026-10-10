"""Bounded historical batches and immutable, date-grouped research examples."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import date, timedelta
from decimal import Decimal
from functools import lru_cache
from importlib.metadata import version
from pathlib import Path

import pandas_market_calendars as mcal

from marketpulse.clock import session_window
from marketpulse.constants import STOCKS
from marketpulse.extraction import CONTRACT_VERSION, ExtractionConfig, ExtractionPipeline
from marketpulse.features import FEATURE_SCHEMA, _load_snapshot, build_features
from marketpulse.labels import _threshold, classify_return
from marketpulse.outcomes import OUTCOME_CONTRACT, capture_regular_outcome, validate_saved_outcome
from marketpulse.storage import RawStore, digest

DATASET_CONTRACT = "historical-dataset/1"
SPLITS = ("train", "validation", "test")
FIELDS = {
    "schema", "symbols", "feed", "adjustment", "threshold", "outcome_convention",
    "splits", "embargo_sessions", "plan_approved", "rights_confirmed", "rights_evidence",
}


def load_contract(path: Path) -> dict:
    if not path.is_file() or path.stat().st_size > 16384:
        raise ValueError("contract must be a regular JSON file below 16 KiB")

    def unique_keys(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("duplicate contract key")
            value[key] = item
        return value

    contract = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_keys)
    validate_contract(contract)
    return contract


def validate_contract(contract: dict, *, require_approval: bool = False) -> None:
    if (not isinstance(contract, dict) or set(contract) != FIELDS
            or contract["schema"] != DATASET_CONTRACT
            or contract["symbols"] != list(STOCKS)
            or contract["outcome_convention"] != OUTCOME_CONTRACT
            or contract["feed"] not in {"iex", "sip"}
            or contract["adjustment"] not in {"raw", "split", "all"}):
        raise ValueError("unsupported dataset contract")
    if not isinstance(contract["threshold"], str):
        raise ValueError("threshold must be an explicit decimal string")
    _threshold(contract["threshold"])
    if type(contract["embargo_sessions"]) is not int or not 1 <= contract["embargo_sessions"] <= 5:
        raise ValueError("embargo must be 1 to 5 exchange sessions")
    if any(type(contract[name]) is not bool for name in ("plan_approved", "rights_confirmed")):
        raise ValueError("approvals must be explicit booleans")
    evidence = contract["rights_evidence"]
    if evidence is not None and (not isinstance(evidence, str) or not 1 <= len(evidence) <= 250):
        raise ValueError("rights evidence must be a short non-secret reference or null")
    if not isinstance(contract["splits"], dict) or set(contract["splits"]) != set(SPLITS):
        raise ValueError("contract needs train, validation and test date ranges")
    previous_end = None
    total = 0
    for split in SPLITS:
        bounds = contract["splits"][split]
        if not isinstance(bounds, list) or len(bounds) != 2:
            raise ValueError("split must have exactly start and end dates")
        start, end = (date.fromisoformat(value) for value in bounds)
        if end < start or (previous_end and start <= previous_end):
            raise ValueError("splits must be disjoint and chronological")
        if (end - start).days > 1500:
            raise ValueError("split date range exceeds the bounded research scope")
        sessions = market_sessions(start, end)
        if len(sessions) <= (0 if split == "train" else contract["embargo_sessions"]):
            raise ValueError("split has no usable sessions after embargo")
        total += len(sessions)
        previous_end = end
    if total > 1000:
        raise ValueError("contract exceeds the 1000-session research limit")
    if require_approval and (not contract["plan_approved"] or not contract["rights_confirmed"]
                             or not evidence):
        raise ValueError("bulk materialization needs plan approval and recorded data rights")


@lru_cache(maxsize=128)
def market_sessions(start: date, end: date) -> tuple[date, ...]:
    return tuple(value.date() for value in mcal.get_calendar("NYSE").valid_days(
        start_date=start, end_date=end))


def split_sessions(contract: dict) -> dict[str, str]:
    result = {}
    for split in SPLITS:
        start, end = (date.fromisoformat(value) for value in contract["splits"][split])
        sessions = market_sessions(start, end)
        if split != "train":
            sessions = sessions[contract["embargo_sessions"]:]
        result.update({day.isoformat(): split for day in sessions})
    return result


def frozen_identity(contract: dict, pipeline: ExtractionPipeline) -> dict:
    return {
        "contract": contract, "extraction_version": CONTRACT_VERSION,
        "feature_schema": FEATURE_SCHEMA, "outcome_version": OUTCOME_CONTRACT,
        "data_url": getattr(pipeline.client, "base_url", "https://data.alpaca.markets"),
        "availability_tier": "HISTORICAL_APPROXIMATE",
        "calendar_version": version("pandas-market-calendars"),
        "cutoff_zone": "America/New_York", "cutoff_local": "09:00",
        "session_splits": split_sessions(contract),
    }


def make_row(pipeline: ExtractionPipeline, snapshot_hash: str, outcome: dict,
             contract_hash: str, contract: dict, split: str) -> dict:
    # Input hydration/feature calculation happens before the independent outcome lookup.
    snapshot, source, company, spy, articles = _load_snapshot(pipeline.data_dir, snapshot_hash)
    features = build_features(snapshot, source, company, spy, articles)
    binding = outcome["binding"]
    if (features["session"] != binding["session"]
            or features["availability_tier"] != "HISTORICAL_APPROXIMATE"
            or features["feed"] != binding["feed"] or features["feed"] != contract["feed"]
            or features["adjustment"] != binding["adjustment"]
            or features["adjustment"] != contract["adjustment"]
            or source.get("include_content") or binding["contract"] != OUTCOME_CONTRACT
            or split_sessions(contract).get(features["session"]) != split):
        raise ValueError("dataset input, outcome or split incompatibility")
    bars = validate_saved_outcome(pipeline, outcome)
    bar = bars[snapshot["symbol"]]
    movement = Decimal(bar["return_fraction"])
    news = [{
        "version_hash": item["version_hash"], "provider_id": item["provider_id"],
        "headline": item["headline"], "summary": item["summary"],
        "created_at": item["created_at"], "updated_at": item["updated_at"],
        "raw_page_digest": item["job_raw_page_digest"],
        "headline_group": digest(" ".join(item["headline"].casefold().split())),
    } for item in articles]
    return {
        "schema": DATASET_CONTRACT, "contract_hash": contract_hash,
        "session": features["session"], "symbol": snapshot["symbol"], "split": split,
        "snapshot_hash": snapshot_hash, "source_job_key": snapshot["job_key"],
        "features": features, "news": news, "healthy_no_news": not news,
        "outcome_hash": digest(outcome), "outcome_job_key": outcome["job_key"],
        "outcome_page_digests": [page["digest"] for page in outcome["pages"]],
        "return_fraction": str(movement), "threshold": str(_threshold(contract["threshold"])),
        "label": classify_return(movement, _threshold(contract["threshold"])),
        "price_convention": OUTCOME_CONTRACT,
        "missing_interior_outcome_minutes": bar["missing_interior_minutes"],
    }


def dataset_report(pipeline: ExtractionPipeline, identity: dict) -> dict:
    """Manifest includes completeness and conservative exact-story leakage checks."""
    contract = identity["contract"]
    contract_hash = digest(identity)
    artifact_store = RawStore(pipeline.data_dir / "datasets")
    expected = split_sessions(contract)
    with pipeline.store.connect() as db:
        index = [dict(row) for row in db.execute(
            "SELECT * FROM dataset_rows WHERE contract_hash=? ORDER BY session,symbol",
            (contract_hash,))]
    counts, date_counts, no_news, missing_values = Counter(), Counter(), Counter(), Counter()
    outcome_gaps = []
    article_splits = defaultdict(set)
    headline_splits = defaultdict(set)
    observed = set()
    errors = []
    manifests = []
    for entry in index:
        try:
            row = artifact_store.get(entry["row_hash"])
            if (row["contract_hash"] != contract_hash or row["session"] != entry["session"]
                    or row["symbol"] != entry["symbol"] or row["symbol"] not in STOCKS
                    or expected.get(row["session"]) != row["split"]):
                raise ValueError("row identity mismatch")
            job = pipeline.store.get_job(row["outcome_job_key"])
            if not job or job["status"] != "COMPLETE":
                raise ValueError("outcome job missing")
            rebuilt = make_row(pipeline, row["snapshot_hash"], json.loads(job["manifest_json"]),
                               contract_hash, contract, row["split"])
            if rebuilt != row:
                raise ValueError("row disagrees with verified lineage")
        except (OSError, ValueError, KeyError, TypeError):
            errors.append({"row_hash": entry["row_hash"], "reason": "row_lineage_failed"})
            continue
        observed.add((row["session"], row["symbol"]))
        counts[f"{row['split']}:{row['symbol']}"] += 1
        date_counts[row["session"]] += 1
        no_news[f"{row['split']}:{row['symbol']}"] += int(row["healthy_no_news"])
        missing_values.update(name for name, value in row["features"]["values"].items()
                              if value is None)
        if row["missing_interior_outcome_minutes"]:
            outcome_gaps.append({"session": row["session"], "symbol": row["symbol"],
                                 "missing_minutes": row["missing_interior_outcome_minutes"]})
        for article in row["news"]:
            article_splits[article["provider_id"]].add(row["split"])
            headline_splits[article["headline_group"]].add(row["split"])
        manifests.append({"row_hash": entry["row_hash"], "session": row["session"],
                          "symbol": row["symbol"], "split": row["split"]})
    missing = [{"session": day, "symbol": symbol, "split": split}
               for day, split in expected.items() for symbol in STOCKS
               if (day, symbol) not in observed]
    leakage = {
        "provider_ids_crossing_splits": sorted(key for key, splits in article_splits.items()
                                               if len(splits) > 1),
        "headline_groups_crossing_splits": sorted(key for key, splits in headline_splits.items()
                                                  if len(splits) > 1),
        "semantic_event_grouping_verified": False,
    }
    leakage_fail = bool(leakage["provider_ids_crossing_splits"]
                        or leakage["headline_groups_crossing_splits"])
    return {
        "schema": DATASET_CONTRACT, "contract_hash": contract_hash,
        "expected_rows": len(expected) * len(STOCKS), "accepted_rows": len(manifests),
        "counts_by_split_ticker": dict(sorted(counts.items())),
        "counts_by_session": dict(sorted(date_counts.items())),
        "outcome_interior_gaps": outcome_gaps,
        "healthy_no_news_by_split_ticker": dict(sorted(no_news.items())),
        "feature_missing_values": dict(sorted(missing_values.items())),
        "missing_rows": missing, "lineage_errors": errors, "leakage": leakage,
        "rows": manifests, "test_label_statistics_withheld": True,
        "status": ("INTEGRITY_BLOCKED" if errors or leakage_fail else
                   "INCOMPLETE" if missing else "COMPLETE_RESEARCH_REVIEW_REQUIRED"),
        "ready_for_training": False,
        "remaining_review": ["Historical news is not certified point-in-time",
                             "Corporate-action and semantic-event audit required",
                             "Human dataset promotion required before M04"],
    }


def run_dataset_batch(pipeline: ExtractionPipeline, contract: dict, start: date, end: date) -> dict:
    validate_contract(contract, require_approval=True)
    if end < start:
        raise ValueError("batch end precedes start")
    if (end - start).days > 60:
        raise ValueError("batch date span exceeds 60 calendar days")
    eligible = split_sessions(contract)
    days = [day for day in market_sessions(start, end) if day.isoformat() in eligible]
    if not 1 <= len(days) <= 31:
        raise ValueError("batch needs 1 to 31 eligible exchange sessions")
    # Reject unfinished dates for the entire batch before freezing or requesting anything.
    if any(pipeline.clock() <= session_window(day).market_close + timedelta(minutes=15)
           for day in days):
        raise ValueError("all batch sessions must have closed more than 15 minutes ago")
    identity = frozen_identity(contract, pipeline)
    contract_hash = RawStore(pipeline.data_dir / "contracts").put(identity)
    artifacts = RawStore(pipeline.data_dir / "datasets")
    failures = []
    for day in days:
        try:
            source = pipeline.run(ExtractionConfig(day, feed=contract["feed"],
                                                   adjustment=contract["adjustment"]))
            if source["state"] != "COMPLETE":
                failures.append({"session": day.isoformat(), "stage": "inputs",
                                 "state": source["state"]})
                break  # Held work needs review; don't sweep the rest of the provider history.
            outcome = capture_regular_outcome(pipeline, day, feed=contract["feed"],
                                              adjustment=contract["adjustment"])
            if outcome["state"] != "COMPLETE":
                failures.append({"session": day.isoformat(), "stage": "outcomes",
                                 "state": outcome["state"]})
                break
            for symbol in STOCKS:
                row = make_row(pipeline, source["snapshots"][symbol], outcome, contract_hash,
                               contract, eligible[day.isoformat()])
                pipeline.store.append_dataset_row(artifacts.put(row), contract_hash, row)
        except (ValueError, OSError, KeyError, TypeError) as error:
            failures.append({"session": day.isoformat(), "stage": "materialization",
                             "state": type(error).__name__})
            break
    report = dataset_report(pipeline, identity)
    report["batch_failures"] = failures
    if failures:
        report["status"] = "BATCH_BLOCKED"
    report_hash = artifacts.put(report)
    return {"contract_hash": contract_hash, "report_hash": report_hash,
            "status": report["status"], "expected_rows": report["expected_rows"],
            "accepted_rows": report["accepted_rows"], "batch_failures": failures,
            "ready_for_training": False}
