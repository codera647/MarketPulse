from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from test_extraction import FakeClient

from marketpulse.audit import AuditCase, run_audit
from marketpulse.cli import main
from marketpulse.extraction import ExtractionPipeline
from marketpulse.labels import classify_return, preview_label

SESSION = date(2026, 10, 9)
NOW = datetime(2026, 10, 10, 16, tzinfo=timezone.utc)


def test_symmetric_label_boundary_with_hand_calculated_returns():
    theta = Decimal("0.01")
    assert classify_return(Decimal("0.0101"), theta) == "UP"
    assert classify_return(Decimal("0.01"), theta) == "NO_MATERIAL_MOVE"
    assert classify_return(Decimal("-0.01"), theta) == "NO_MATERIAL_MOVE"
    assert classify_return(Decimal("-0.0101"), theta) == "DOWN"


@pytest.fixture
def audited_fixture(tmp_path):
    data_dir = tmp_path / "runtime"
    pipeline = ExtractionPipeline(data_dir, FakeClient(), clock=lambda: NOW)
    report, _ = run_audit(
        (AuditCase("ordinary", SESSION),), pipeline=pipeline,
        feed="iex", adjustment="split", include_content=False,
        output_dir=tmp_path / "reports", clock=lambda: NOW,
    )
    case = report["cases"][0]
    assert case["status"] == "EXTRACTED"
    return data_dir, case["manifest"]["snapshots"], case["outcome_probe"]["job_key"]


def test_label_preview_is_explicit_provisional_and_keeps_outcomes_separate(audited_fixture):
    data_dir, snapshots, outcome_key = audited_fixture
    down = preview_label(data_dir, snapshots["AAPL"], outcome_key, "0.005")
    flat = preview_label(data_dir, snapshots["AAPL"], outcome_key, "0.01")
    assert down["label"] == "DOWN"
    assert flat["label"] == "NO_MATERIAL_MOVE"
    assert down["return_fraction"] == "-0.0099009900990099009900990099"
    assert down["ready_for_training"] is False
    assert down["status"] == "PROVISIONAL_DAILY_BAR_CONVENTION"
    assert down["preview_hash"] != flat["preview_hash"]
    assert preview_label(data_dir, snapshots["AAPL"], outcome_key, "0.005") == down
    with sqlite3.connect(data_dir / "marketpulse.sqlite3") as db:
        assert db.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0] == 6
        assert db.execute("SELECT COUNT(*) FROM price_bars").fetchone()[0] == 147


def test_label_preview_accepts_relative_data_directory(audited_fixture, monkeypatch):
    data_dir, snapshots, outcome_key = audited_fixture
    expected = preview_label(data_dir, snapshots["AAPL"], outcome_key, "0.01")
    monkeypatch.chdir(data_dir.parent)
    assert preview_label(Path("runtime"), snapshots["AAPL"], outcome_key, "0.01") == expected


def test_label_preview_rejects_missing_or_incompatible_evidence(audited_fixture):
    data_dir, snapshots, outcome_key = audited_fixture
    for threshold in ("0", "-0.01", "NaN", "Infinity", "1"):
        with pytest.raises(ValueError, match="threshold"):
            preview_label(data_dir, snapshots["AAPL"], outcome_key, threshold)
    with pytest.raises(ValueError, match="outcome job is missing"):
        preview_label(data_dir, snapshots["AAPL"], "0" * 64, "0.01")

    path = data_dir / "marketpulse.sqlite3"
    with sqlite3.connect(path) as db:
        manifest = json.loads(db.execute(
            "SELECT manifest_json FROM extraction_jobs WHERE job_key=?", (outcome_key,)
        ).fetchone()[0])
        manifest["feed"] = "sip"
        db.execute(
            "UPDATE extraction_jobs SET manifest_json=? WHERE job_key=?",
            (json.dumps(manifest), outcome_key),
        )
    with pytest.raises(ValueError, match="price conventions differ"):
        preview_label(data_dir, snapshots["AAPL"], outcome_key, "0.01")

    manifest["feed"] = "iex"
    with sqlite3.connect(path) as db:
        db.execute(
            "UPDATE extraction_jobs SET manifest_json=? WHERE job_key=?",
            (json.dumps(manifest), outcome_key),
        )
        db.execute(
            "UPDATE source_pages SET received_at=? WHERE job_key=?",
            ("2026-10-09T19:00:00Z", outcome_key),
        )
    with pytest.raises(ValueError, match="not observed after"):
        preview_label(data_dir, snapshots["AAPL"], outcome_key, "0.01")


def test_label_preview_cli_is_read_only(audited_fixture, capsys):
    data_dir, snapshots, outcome_key = audited_fixture
    status = main([
        "label-preview", "--snapshot-hash", snapshots["NVDA"],
        "--outcome-job-key", outcome_key, "--threshold", "0.01",
        "--data-dir", str(data_dir),
    ])
    result = json.loads(capsys.readouterr().out)
    assert status == 0
    assert result["symbol"] == "NVDA"
    assert result["label"] == "NO_MATERIAL_MOVE"
