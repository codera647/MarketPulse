"""Confirmed coverage failures may be excluded; unknown work may not."""

from datetime import date

import pytest
from test_dataset import NOW, DatasetClient, contract

from marketpulse.dataset import frozen_identity, run_dataset_batch
from marketpulse.extraction import ExtractionPipeline
from marketpulse.quarantine import QUALITY_POLICY, record_exclusion, validated_exclusions
from marketpulse.storage import RawStore, digest


def test_quarantine_complete_date_and_preserve_failed_receipt(tmp_path):
    value = {**contract(), "quality_policy": QUALITY_POLICY}
    pipeline = ExtractionPipeline(tmp_path, DatasetClient(missing_boundary=True), clock=lambda: NOW)
    result = run_dataset_batch(pipeline, value, date(2026, 10, 5), date(2026, 10, 9))
    report = RawStore(tmp_path / "datasets").get(result["report_hash"])
    assert report["accepted_rows"] == 0 and report["excluded_rows"] == 18
    assert report["expected_rows"] == 0 and report["planned_rows"] == 18
    assert len(report["exclusions"]) == 3 and not report["missing_rows"]
    assert result["batch_failures"] == []
    evidence = RawStore(tmp_path / "exclusions").get(report["exclusions"][0]["exclusion_hash"])
    assert evidence["symbols"] == value["symbols"]
    assert evidence["labels_fabricated"] is False and evidence["verify_receipt"]
    assert pipeline.store.get_job(evidence["outcome_job_key"])["status"] == "FAILED"
    assert validated_exclusions(pipeline, value, result["contract_hash"]) == report["exclusions"]
    # Saved raw captures must remain available and intact for re-audit.
    path = pipeline.raw.root / evidence["raw_page_digests"][0][:2]
    path /= evidence["raw_page_digests"][0] + ".json"
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError):
        validated_exclusions(pipeline, value, result["contract_hash"])


def test_no_unknown_or_unfetched_work_can_be_quarantined(tmp_path):
    value = {**contract(), "quality_policy": QUALITY_POLICY}
    pipeline = ExtractionPipeline(tmp_path, DatasetClient(), clock=lambda: NOW)
    key = digest(frozen_identity(value, pipeline))
    with pytest.raises(ValueError, match="confirmed"):
        record_exclusion(pipeline, value, key, "2026-10-05")


def test_parallel_date_waves_use_isolated_clients_and_same_roster(tmp_path):
    value = contract()
    clients = []

    def factory():
        client = DatasetClient()
        clients.append(client)
        return ExtractionPipeline(tmp_path, client, clock=lambda: NOW)

    pipeline = factory()
    result = run_dataset_batch(pipeline, value, date(2026, 10, 5), date(2026, 10, 9),
                               workers=3, pipeline_factory=factory)
    assert result["status"] == "COMPLETE_RESEARCH_REVIEW_REQUIRED"
    assert result["accepted_rows"] == 18 and len(clients) == 4
    assert len({id(client) for client in clients}) == 4
    with pytest.raises(ValueError, match="isolated"):
        run_dataset_batch(pipeline, value, date(2026, 10, 5), date(2026, 10, 9), workers=2)
