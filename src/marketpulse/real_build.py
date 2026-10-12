"""Bounded real collection -> full audit -> explicitly authorized offline fitting."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from marketpulse.dataset import frozen_identity, validate_contract
from marketpulse.preprocessing import NEWS_MASK_POLICY
from marketpulse.real_training import RESEARCH_VERSION, research_report_ready, train_real_models
from marketpulse.research import collect_dataset
from marketpulse.storage import RawStore, digest


def build_real_research(pipeline, contract: dict, *, evidence: str, workers: int = 1,
                        pipeline_factory=None, cycles: int = 3, progress=None,
                        mask_previous_stories: bool = False) -> dict:
    """No fitting on partial/blocked data; no invented human review or deployment."""
    validate_contract(contract, require_approval=True)
    if type(mask_previous_stories) is not bool:
        raise ValueError("story masking needs explicit authorization")
    if not isinstance(evidence, str) or not 1 <= len(evidence.strip()) <= 500:
        raise ValueError("explicit user offline-training authorization evidence is required")
    if type(cycles) is not int or not 1 <= cycles <= 3:
        raise ValueError("build needs one to three bounded collection cycles")
    if type(workers) is not int or not 1 <= workers <= 3:
        raise ValueError("build needs one to three workers")
    if workers > 1 and pipeline_factory is None:
        raise ValueError("parallel build needs isolated provider sessions")
    identity = frozen_identity(contract, pipeline)
    artifacts = RawStore(pipeline.data_dir / "build-runs")
    intent = {"schema": "real-build-intent/1", "contract_hash": digest(identity),
              "authorization_evidence": evidence, "cycles": cycles, "workers": workers,
              "news_mask_policy": NEWS_MASK_POLICY if mask_previous_stories else None,
              "human_review_claimed": False, "deployment_authorized": False}
    intent_hash = artifacts.put(intent)
    latest = pipeline.data_dir / "real-build-status.json"

    def checkpoint(value):
        event = {"intent_hash": intent_hash,
                 "updated_at_utc": datetime.now(timezone.utc).isoformat(), **value}
        # Generated runtime status, never source code or provider credential output.
        candidate = latest.with_suffix(".tmp")
        candidate.write_text(json.dumps(event, sort_keys=True, indent=2), encoding="utf-8")
        candidate.replace(latest)
        if progress:
            progress(event)

    checkpoint({"stage": "COLLECTING", "training_started": False})
    previous_count = None
    result = None
    ready = False
    for cycle in range(1, cycles + 1):
        try:
            result = collect_dataset(
                pipeline, contract, batch_sessions=31, max_batches=50, audit_each_batch=False,
                workers=workers, pipeline_factory=pipeline_factory,
                allow_story_duplicates=mask_previous_stories,
                progress=lambda event: checkpoint({"stage": "COLLECTING", "cycle": cycle,
                                                   "training_started": False, **event}))
        except Exception as error:
            stopped = {"state": "STOPPED", "error_type": type(error).__name__,
                       "training_started": False, "authority_reset": False}
            checkpoint({"stage": "COLLECTION_ERROR", **stopped})
            return stopped
        checkpoint({"stage": "AUDITED", "cycle": cycle, **result})
        ready = result["status"] == "COMPLETE_RESEARCH_REVIEW_REQUIRED"
        duplicate_only = False
        if mask_previous_stories and result["status"] == "INTEGRITY_BLOCKED":
            report = RawStore(pipeline.data_dir / "datasets").get(result["report_hash"])
            ready = research_report_ready(report, mask_previous_stories=True)
            duplicate_only = (not report.get("lineage_errors") and not report.get("batch_failures")
                              and bool(report["leakage"]["provider_ids_crossing_splits"]
                                       or report["leakage"]["headline_groups_crossing_splits"]))
        if ready:
            break
        if ((result["status"] != "INCOMPLETE" and not duplicate_only)
                or result["accepted_rows"] == previous_count):
            stopped = {"state": "BLOCKED", "collection": result, "training_started": False}
            checkpoint({"stage": "BLOCKED", **stopped})
            return stopped
        previous_count = result["accepted_rows"]
    if not ready:
        stopped = {"state": "BUDGET_STOP", "collection": result, "training_started": False}
        checkpoint({"stage": "BUDGET_STOP", **stopped})
        return stopped
    authorization = {"schema": RESEARCH_VERSION, "contract_hash": result["contract_hash"],
                     "report_hash": result["report_hash"], "authorized": True,
                     "evidence": evidence}
    if mask_previous_stories:
        authorization["news_mask_policy"] = NEWS_MASK_POLICY
    authorization_hash = RawStore(pipeline.data_dir / "training-authorizations").put(authorization)
    checkpoint({"stage": "TRAINING", "collection": result,
                "authorization_hash": authorization_hash, "training_started": True})
    try:
        fitted = train_real_models(pipeline.data_dir, contract, authorization)
    except Exception as error:
        stopped = {"state": "STOPPED", "error_type": type(error).__name__,
                   "training_started": True, "authority_reset": False}
        checkpoint({"stage": "TRAINING_ERROR", **stopped})
        return stopped
    complete = {"state": fitted["state"], "collection": result,
                "authorization_hash": authorization_hash, "model": fitted}
    complete["build_result_hash"] = artifacts.put(complete)
    checkpoint({"stage": fitted["state"], **complete})
    return complete
