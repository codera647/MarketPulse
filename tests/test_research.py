from __future__ import annotations

import json
from copy import deepcopy
from datetime import date, timedelta
from pathlib import Path

import pytest
from test_dataset import NOW, DatasetClient, contract

from marketpulse import cli
from marketpulse.alpaca import CapturedPage
from marketpulse.clock import parse_time, utc_iso
from marketpulse.constants import SYMBOLS
from marketpulse.dataset import frozen_identity, load_contract
from marketpulse.extraction import ExtractionPipeline
from marketpulse.outcomes import SOURCE
from marketpulse.research import (
    REVIEW_VERSION,
    collect_dataset,
    collection_plan,
    inspect_dataset,
    load_review,
    promote_dataset,
    reviewed_rows,
    saved_pipeline,
    train_reviewed_baselines,
    validate_review,
)
from marketpulse.storage import RawStore, digest


class CompleteSyntheticClient(DatasetClient):
    """Synthetic wire responses, not live provider evidence or financial performance."""

    def pages(self, source, endpoint, params, item_key, *, max_pages):
        if source != SOURCE:
            return super().pages(source, endpoint, params, item_key, max_pages=max_pages)
        self.calls.append(source)
        start, end = parse_time(params["start"]), parse_time(params["end"])
        bars = {}
        for index, symbol in enumerate(SYMBOLS):
            closing = (98, 100, 102)[index % 3]
            bars[symbol] = [{"t": utc_iso(start + timedelta(minutes=minute)),
                             "o": 100, "h": 103, "l": 97, "c": closing, "v": 100}
                            for minute in range(int((end - start).total_seconds() / 60) + 1)]
        return [CapturedPage(source, endpoint, params, utc_iso(NOW), "synthetic-test-only",
                             {"bars": bars, "next_page_token": None})]


def review_for(result):
    return {"schema": REVIEW_VERSION, "contract_hash": result["contract_hash"],
            "report_hash": result["report_hash"], "reviewer": "pytest-synthetic-only",
            "reviewed_at_utc": "2026-10-09T20:00:00Z", "approved": True,
            "checks": {"corporate_actions": "Synthetic prices; no actual corporate action",
                       "semantic_events": "Synthetic healthy empty news",
                       "outcome_gaps": "Synthetic complete regular-minute grids",
                       "historical_approximation": "Test wire responses; NOT market evidence"}}


@pytest.fixture(scope="module")
def collected(tmp_path_factory):
    data_dir = tmp_path_factory.mktemp("research-synthetic")
    client = CompleteSyntheticClient()
    pipeline = ExtractionPipeline(data_dir, client, clock=lambda: NOW)
    value = contract()
    first = collect_dataset(pipeline, value, batch_sessions=1, max_batches=1)
    calls = len(client.calls)
    assert first["accepted_rows"] == 6
    assert first["status"] == "INCOMPLETE"
    final = collect_dataset(pipeline, value, batch_sessions=1, max_batches=2)
    assert len(client.calls) - calls == 6  # Two missing sessions, three requests each.
    assert final["accepted_rows"] == final["expected_rows"] == 18
    assert final["status"] == "COMPLETE_RESEARCH_REVIEW_REQUIRED"
    promotion = promote_dataset(pipeline, value, review_for(final))
    return pipeline, value, final, promotion


def test_plan_keeps_frozen_dates_and_bounds_every_batch():
    value = load_contract(Path("doc/dataset_contract.proposed.json"))
    plan = collection_plan(value)
    assert plan["expected_rows"] == 1878
    assert plan["sessions_by_split"] == {"train": 128, "validation": 60, "test": 125}
    assert sum(batch["sessions"] for batch in plan["batches"]) == 313
    assert all(1 <= batch["sessions"] <= 20 for batch in plan["batches"])
    assert all((date.fromisoformat(batch["end"]) - date.fromisoformat(batch["start"])).days <= 60
               for batch in plan["batches"])
    assert plan["rights_confirmed"] is False
    assert plan["network_used"] is False


@pytest.mark.parametrize("count", [0, 32, True, -1])
def test_bad_batch_sizes_are_rejected(count):
    with pytest.raises(ValueError):
        collection_plan(contract(), batch_sessions=count)


def test_cli_rights_gate_precedes_credentials_and_disk(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "load_alpaca_settings", lambda *a, **kw:
                        pytest.fail("rights gate must run before credentials"))
    path = "doc/dataset_contract.proposed.json"
    assert cli.main(["pipeline-plan", "--contract", path]) == 0
    assert json.loads(capsys.readouterr().out)["expected_rows"] == 1878
    assert cli.main(["pipeline-collect", "--contract", path,
                     "--data-dir", str(tmp_path / "absent")]) == 2
    assert cli.main(["baseline-train", "--contract", path,
                     "--promotion-hash", "0" * 64,
                     "--data-dir", str(tmp_path / "absent")]) == 2
    assert not (tmp_path / "absent").exists()


def test_collect_resume_skips_complete_rows_and_no_automatic_training(collected):
    pipeline, value, _, _ = collected
    calls = len(pipeline.client.calls)
    result = collect_dataset(pipeline, value, batch_sessions=1, max_batches=3)
    assert result["batches_this_run"] == 0
    assert len(pipeline.client.calls) == calls
    assert result["training_started"] is False
    assert result["ready_for_training"] is False


def test_hold_stops_collection_and_does_not_retry_unknown(tmp_path):
    class UncertainClient(DatasetClient):
        def pages(self, *args, **kwargs):
            self.calls.append("uncertain")
            raise TimeoutError("synthetic timeout")

    client = UncertainClient()
    pipeline = ExtractionPipeline(tmp_path, client, clock=lambda: NOW)
    first = collect_dataset(pipeline, contract(), batch_sessions=1, max_batches=3)
    assert first["status"] == "BATCH_BLOCKED"
    assert first["batches_this_run"] == 1
    assert first["accepted_rows"] == 0
    calls = len(client.calls)
    second = collect_dataset(pipeline, contract(), batch_sessions=1, max_batches=3)
    assert second["status"] == "BATCH_BLOCKED"
    assert len(client.calls) == calls


@pytest.mark.parametrize("fault", ["approval", "identity", "hash", "check", "reviewer", "future"])
def test_review_cannot_be_empty_or_implicit(collected, fault):
    _, _, result, _ = collected
    value = review_for(result)
    if fault == "approval":
        value["approved"] = False
    elif fault == "identity":
        value["extra"] = "not allowed"
    elif fault == "hash":
        value["contract_hash"] = "../bad"
    elif fault == "check":
        value["checks"]["corporate_actions"] = " "
    elif fault == "reviewer":
        value["reviewer"] = None
    elif fault == "future":
        value["reviewed_at_utc"] = "2099-01-01T00:00:00Z"
    with pytest.raises((ValueError, TypeError)):
        validate_review(value)


def test_draft_review_and_duplicate_keys_are_refused(tmp_path, monkeypatch):
    with pytest.raises(ValueError):
        load_review(Path("doc/dataset_review.proposed.json"))
    with pytest.raises(ValueError):
        load_review(tmp_path / "missing.json")
    monkeypatch.setattr(Path, "read_text", lambda *a, **kw: '{"approved":true,"approved":true}')
    with pytest.raises(ValueError, match="duplicate"):
        load_review(Path("doc/dataset_review.proposed.json"))


def test_incomplete_dataset_cannot_be_promoted(tmp_path):
    pipeline = ExtractionPipeline(tmp_path, CompleteSyntheticClient(), clock=lambda: NOW)
    result = collect_dataset(pipeline, contract(), batch_sessions=1, max_batches=1)
    with pytest.raises(ValueError, match="complete"):
        promote_dataset(pipeline, contract(), review_for(result))
    assert not (tmp_path / "promotions").exists()


def test_stale_or_wrong_review_cannot_promote(collected):
    pipeline, value, result, _ = collected
    wrong = review_for(result)
    wrong["contract_hash"] = "0" * 64
    with pytest.raises(ValueError, match="different"):
        promote_dataset(pipeline, value, wrong)
    stale = deepcopy(RawStore(pipeline.data_dir / "datasets").get(result["report_hash"]))
    stale["accepted_rows"] -= 1
    wrong = review_for(result)
    wrong["report_hash"] = RawStore(pipeline.data_dir / "datasets").put(stale)
    with pytest.raises(ValueError, match="current"):
        promote_dataset(pipeline, value, wrong)


def test_offline_inspection_needs_no_credentials_or_provider(collected):
    pipeline, value, _, _ = collected
    offline = saved_pipeline(pipeline.data_dir)
    result = inspect_dataset(offline, value)
    assert result["accepted_rows"] == 18
    assert result["contract_hash"] == digest(frozen_identity(value, pipeline))
    with pytest.raises(ValueError, match="offline"):
        offline.client.pages()


def test_training_and_verifier_never_read_test_rows_or_raw_pages(collected, monkeypatch):
    pipeline, value, result, promotion = collected
    store = RawStore(pipeline.data_dir / "datasets")
    report = store.get(result["report_hash"])
    test_rows = [entry for entry in report["rows"] if entry["split"] == "test"]
    # Identify sealed artifacts BEFORE installing the read guard; no learning has begun.
    sealed = {entry["row_hash"] for entry in test_rows}
    for entry in test_rows:
        row = store.get(entry["row_hash"])
        sealed.update(row["outcome_page_digests"])
    original = RawStore.get

    def guarded(self, key):
        assert key not in sealed, "learner/verifier attempted to open final-test data"
        return original(self, key)

    monkeypatch.setattr(RawStore, "get", guarded)
    train, validation = reviewed_rows(pipeline, value, promotion["promotion_hash"])
    assert len(train) == len(validation) == 6
    trained = train_reviewed_baselines(saved_pipeline(pipeline.data_dir), value,
                                      promotion["promotion_hash"])
    assert trained["state"] == "COMPLETE"
    assert trained["availability_tier"] == "HISTORICAL_APPROXIMATE"
    assert trained["final_test_opened"] is False
    assert trained["paper_action_authorized"] is False
    assert trained["trailforge_verify_receipt"].startswith("sha256:")
    assert train_reviewed_baselines(saved_pipeline(pipeline.data_dir), value,
                                    promotion["promotion_hash"]) == trained


def test_training_rechecks_row_index_instead_of_trusting_promotion(collected):
    pipeline, value, _, promotion = collected
    with pipeline.store.connect() as db:
        row = db.execute("SELECT * FROM dataset_rows ORDER BY session,symbol LIMIT 1").fetchone()
        db.execute("UPDATE dataset_rows SET row_hash=? WHERE row_hash=?",
                   ("f" * 64, row["row_hash"]))
    try:
        with pytest.raises(ValueError, match="index"):
            reviewed_rows(pipeline, value, promotion["promotion_hash"])
    finally:
        with pipeline.store.connect() as db:
            db.execute("UPDATE dataset_rows SET row_hash=? WHERE row_hash=?",
                       (row["row_hash"], "f" * 64))


def test_offline_entry_refuses_missing_database(tmp_path):
    with pytest.raises(ValueError, match="collect"):
        saved_pipeline(tmp_path / "absent")
    assert not (tmp_path / "absent").exists()
