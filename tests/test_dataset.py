from __future__ import annotations

import json
from copy import deepcopy
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas_market_calendars as mcal
import pytest

from marketpulse import cli
from marketpulse.alpaca import CapturedPage
from marketpulse.clock import parse_time, session_window, utc_iso
from marketpulse.constants import STOCKS, SYMBOLS, ZONE
from marketpulse.dataset import (
    DATASET_CONTRACT,
    dataset_report,
    frozen_identity,
    load_contract,
    run_dataset_batch,
    split_sessions,
    validate_contract,
)
from marketpulse.extraction import ExtractionPipeline
from marketpulse.outcomes import OUTCOME_CONTRACT, SOURCE
from marketpulse.storage import RawStore, digest

NOW = datetime(2026, 10, 10, tzinfo=timezone.utc)


def contract():
    return {
        "schema": DATASET_CONTRACT, "symbols": list(STOCKS), "feed": "sip",
        "adjustment": "split", "threshold": "0.01", "outcome_convention": OUTCOME_CONTRACT,
        "splits": {"train": ["2026-10-05", "2026-10-05"],
                   "validation": ["2026-10-06", "2026-10-07"],
                   "test": ["2026-10-08", "2026-10-09"]},
        "embargo_sessions": 1, "plan_approved": True, "rights_confirmed": True,
        "rights_evidence": "Synthetic fixtures only, not a provider license",
    }


class DatasetClient:
    def __init__(self, *, news=False, missing_boundary=False):
        self.calls = []
        self.news = news
        self.missing_boundary = missing_boundary

    def pages(self, source, endpoint, params, item_key, *, max_pages):
        self.calls.append(source)
        if source == "alpaca_news":
            day = parse_time(params["end"]).astimezone(ZoneInfo(ZONE)).date()
            created = session_window(day).previous_close + timedelta(minutes=30)
            items = [{"id": day.toordinal(), "symbols": ["AAPL"],
                      "created_at": utc_iso(created), "updated_at": utc_iso(created),
                      "headline": "Identical syndicated headline", "summary": "Fixture"}]
            payload = {"news": items if self.news else [], "next_page_token": None}
        elif source == SOURCE:
            items = [{"t": params["start"], "o": 100, "h": 103, "l": 99,
                      "c": 102, "v": 100},
                     {"t": params["end"], "o": 102, "h": 103, "l": 99,
                      "c": 101, "v": 100}]
            if self.missing_boundary:
                items.pop()
            payload = {"bars": {symbol: deepcopy(items) for symbol in SYMBOLS},
                       "next_page_token": None}
        else:
            start = parse_time(params["start"]).astimezone(ZoneInfo(ZONE)).date()
            end = parse_time(params["end"]).astimezone(ZoneInfo(ZONE)).date()
            dates = mcal.get_calendar("NYSE").valid_days(start_date=start, end_date=end)[-21:]
            items = [{"t": utc_iso(datetime.combine(value.date(), time.min, ZoneInfo(ZONE))),
                      "o": 100, "h": 103, "l": 99, "c": 101, "v": 100}
                     for value in dates]
            payload = {"bars": {symbol: deepcopy(items) for symbol in SYMBOLS},
                       "next_page_token": None}
        return [CapturedPage(source, endpoint, params, utc_iso(NOW), "fixture", payload)]


def test_date_groups_embargo_and_contract_validation():
    value = contract()
    validate_contract(value, require_approval=True)
    assert split_sessions(value) == {"2026-10-05": "train", "2026-10-07": "validation",
                                     "2026-10-09": "test"}


@pytest.mark.parametrize("fault", ["overlap", "threshold", "universe", "no_embargo",
                                  "empty_split", "approval", "rights", "evidence",
                                  "extra_field", "wrong_target"])
def test_invalid_contract_cannot_run(fault):
    value = contract()
    if fault == "overlap":
        value["splits"]["validation"][0] = "2026-10-05"
    elif fault == "threshold":
        value["threshold"] = "NaN"
    elif fault == "universe":
        value["symbols"].append("SPY")
    elif fault == "no_embargo":
        value["embargo_sessions"] = 0
    elif fault == "empty_split":
        value["splits"]["validation"][1] = "2026-10-06"
    elif fault == "approval":
        value["plan_approved"] = False
    elif fault == "rights":
        value["rights_confirmed"] = False
    elif fault == "evidence":
        value["rights_evidence"] = None
    elif fault == "extra_field":
        value["unknown"] = "no"
    elif fault == "wrong_target":
        value["outcome_convention"] = "daily"
    with pytest.raises(ValueError):
        validate_contract(value, require_approval=True)


def test_draft_cli_needs_no_credentials_and_refuses_bulk(monkeypatch, capsys):
    def forbidden(*args, **kwargs):
        raise AssertionError("draft must not load credentials")
    monkeypatch.setattr(cli, "load_alpaca_settings", forbidden)
    path = "doc/dataset_contract.proposed.json"
    assert cli.main(["dataset-plan", "--contract", path]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["network_used"] is False
    assert result["plan_approved"] is True
    assert cli.main(["dataset-batch", "--contract", path,
                     "--start", "2025-07-01", "--end", "2025-07-02"]) == 2


def test_duplicate_json_keys_are_rejected(tmp_path, monkeypatch):
    from pathlib import Path

    path = Path("doc/dataset_contract.proposed.json")
    value = load_contract(path)
    assert value["rights_confirmed"] is False
    with pytest.raises(ValueError):
        load_contract(tmp_path / "missing.json")
    monkeypatch.setattr(Path, "read_text", lambda *args, **kwargs:
                        '{"schema":"first","schema":"duplicate"}')
    with pytest.raises(ValueError, match="duplicate"):
        load_contract(path)


def test_resumable_batches_complete_immutable_no_news_rows(tmp_path):
    client = DatasetClient()
    pipeline = ExtractionPipeline(tmp_path, client, clock=lambda: NOW)
    value = contract()
    first = run_dataset_batch(pipeline, value, date(2026, 10, 5), date(2026, 10, 5))
    assert first["accepted_rows"] == 6
    assert first["status"] == "INCOMPLETE"
    calls = len(client.calls)
    assert run_dataset_batch(pipeline, value, date(2026, 10, 5), date(2026, 10, 5)) == first
    assert len(client.calls) == calls
    final = run_dataset_batch(pipeline, value, date(2026, 10, 7), date(2026, 10, 9))
    assert final["accepted_rows"] == final["expected_rows"] == 18
    assert final["status"] == "COMPLETE_RESEARCH_REVIEW_REQUIRED"
    report = RawStore(tmp_path / "datasets").get(final["report_hash"])
    assert not report["missing_rows"]
    assert sum(report["healthy_no_news_by_split_ticker"].values()) == 18
    assert report["feature_missing_values"] == {"news_latest_age_minutes": 18}
    assert report["test_label_statistics_withheld"] is True
    row = RawStore(tmp_path / "datasets").get(report["rows"][0]["row_hash"])
    assert row["label"] == "NO_MATERIAL_MOVE"  # Exact +1% belongs to the middle class.
    assert all("outcome" not in name for name in row["features"]["feature_names"])
    assert row["missing_interior_outcome_minutes"] == 388
    with pipeline.store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM session_outcomes").fetchone()[0] == 3
        assert db.execute("SELECT COUNT(*) FROM dataset_rows").fetchone()[0] == 18
    with pytest.raises(ValueError, match="conflict"):
        pipeline.store.append_dataset_row(digest({"changed": True}), first["contract_hash"], row)
    changed = deepcopy(value)
    changed["threshold"] = "0.02"
    assert digest(frozen_identity(changed, pipeline)) != first["contract_hash"]


def test_duplicate_story_crossing_splits_blocks_promotion(tmp_path):
    pipeline = ExtractionPipeline(tmp_path, DatasetClient(news=True), clock=lambda: NOW)
    result = run_dataset_batch(pipeline, contract(), date(2026, 10, 5), date(2026, 10, 9))
    assert result["status"] == "INTEGRITY_BLOCKED"
    report = RawStore(tmp_path / "datasets").get(result["report_hash"])
    assert report["leakage"]["headline_groups_crossing_splits"]
    assert not report["leakage"]["provider_ids_crossing_splits"]


def test_missing_boundary_keeps_all_labels_out(tmp_path):
    pipeline = ExtractionPipeline(tmp_path, DatasetClient(missing_boundary=True), clock=lambda: NOW)
    result = run_dataset_batch(pipeline, contract(), date(2026, 10, 5), date(2026, 10, 9))
    assert result["status"] == "BATCH_BLOCKED"
    assert result["accepted_rows"] == 0
    assert len(result["batch_failures"]) == 1
    with pipeline.store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM session_outcomes").fetchone()[0] == 0


def test_report_detects_missing_immutable_row(tmp_path):
    pipeline = ExtractionPipeline(tmp_path, DatasetClient(), clock=lambda: NOW)
    value = contract()
    result = run_dataset_batch(pipeline, value, date(2026, 10, 5), date(2026, 10, 5))
    report = RawStore(tmp_path / "datasets").get(result["report_hash"])
    key = report["rows"][0]["row_hash"]
    (tmp_path / "datasets" / key[:2] / f"{key}.json").unlink()
    checked = dataset_report(pipeline, frozen_identity(value, pipeline))
    assert checked["status"] == "INTEGRITY_BLOCKED"
    assert checked["accepted_rows"] == 5
    assert checked["lineage_errors"][0]["reason"] == "row_lineage_failed"


def test_unapproved_or_future_batch_has_no_provider_effect(tmp_path):
    client = DatasetClient()
    pipeline = ExtractionPipeline(tmp_path, client, clock=lambda: datetime(
        2026, 10, 5, 12, tzinfo=timezone.utc))
    with pytest.raises(ValueError):
        run_dataset_batch(pipeline, contract(), date(2026, 10, 5), date(2026, 10, 5))
    assert not client.calls
    assert not (tmp_path / "contracts").exists()
