"""Dashboard boundaries use synthetic evidence; never depend on private real data."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import numpy as np
import pytest
from streamlit.testing.v1 import AppTest
from trailforge.core import ContractError

import marketpulse.dashboard_data as data
from marketpulse.baselines import CLASSES
from marketpulse.constants import STOCKS
from marketpulse.storage import RawStore, digest
from marketpulse.v2_models import detailed_metrics
from marketpulse.v2_runtime import supervised


@pytest.fixture
def research(tmp_path, monkeypatch):
    """Small test-only reports with genuine native positive authority."""
    root = tmp_path / "evaluation"
    artifacts = RawStore(root / "artifacts")
    targets = RawStore(tmp_path / "real-2018-2026" / "datasets")
    rows, hashes = [], []
    for session in ("2026-01-05", "2026-02-02", "2026-03-02"):
        for index, symbol in enumerate(sorted(STOCKS)):
            label = CLASSES[index % 3]
            row = {
                "session": session,
                "symbol": symbol,
                "label": label,
                "return_fraction": {"DOWN": "-0.02", "NO_MATERIAL_MOVE": "0", "UP": "0.02"}[label],
                "threshold": "0.01",
                "price_convention": "regular-minute-proxy/1",
                "news": [{"headline": "TEST ONLY private article must not reach projection"}],
            }
            rows.append(row)
            hashes.append(targets.put(row))
    price = [[0.7, 0.2, 0.1] if r["label"] == "DOWN" else [0.1, 0.7, 0.2] for r in rows]
    probabilities = {"price": price, "stack": price, "majority": [[0.2, 0.6, 0.2]] * len(rows)}
    predictions = artifacts.put(
        {
            "row_hashes": hashes,
            "input_hashes": [digest({"i": i}) for i in range(len(rows))],
            "probabilities": probabilities,
            "outcomes_loaded": False,
            "release_hash": data.RELEASE,
        }
    )
    report = {
        "schema": "frozen-stack-2026-retrospective/1",
        "release_hash": data.RELEASE,
        "availability_tier": "HISTORICAL_APPROXIMATE",
        "paper_action_authorized": False,
        "evaluation_kind": "RETROSPECTIVE_2026_PREVIOUSLY_EXPOSED",
        "prediction_hash": predictions,
        "metrics": {name: detailed_metrics(rows, values) for name, values in probabilities.items()},
    }
    key = artifacts.put(report)
    receipt = supervised(
        root,
        "dashboard_test",
        {"test_report_hash": key},
        lambda: {"report_hash": key},
        lambda result: artifacts.get(result["report_hash"]),
    )
    monkeypatch.setitem(data.REPORTS, "2026 retrospective", ("evaluation", key))
    # Stabilize the fixture's writer WAL before checking byte-for-byte read-only access.
    with closing(sqlite3.connect(root / "v2-jobs.sqlite3")) as db:
        db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    return tmp_path, root, report, receipt


def test_read_only_verified_metrics_and_safe_replay(research):
    parent, root, _, _ = research
    database_before = {p.name: p.read_bytes() for p in root.glob("*.sqlite3")}
    view = data.load_research(parent, "2026 retrospective")
    indexes = view.filter(["AAPL", "NVDA"], "2026-01-01", "2026-02-28")
    assert len(indexes) == 4
    assert data.comparison(view, indexes).Examples.tolist() == [4, 4, 4]
    prediction = view.prediction(0, "price")
    assert not {"label", "return_fraction", "news", "headline", "row_hash"} & prediction.keys()
    assert not prediction["live"] and prediction["availability_tier"] == "HISTORICAL_APPROXIMATE"
    assert np.isclose(sum(prediction["probabilities"].values()), 1)
    assert view.outcome(0)["label"] in data.LABEL_NAMES.values()
    assert database_before == {p.name: p.read_bytes() for p in root.glob("*.sqlite3")}
    with data.read_database(root / "v2-jobs.sqlite3") as db:
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            db.execute("DELETE FROM extraction_jobs")


def test_missing_data_does_not_create_directories(tmp_path):
    missing = tmp_path / "absent"
    with pytest.raises(sqlite3.OperationalError):
        data.load_research(missing, "2026 retrospective")
    assert not missing.exists()


def test_native_authority_corruption_fails_closed(research):
    parent, root, _, receipt = research
    with sqlite3.connect(root / "v2-trailforge.sqlite3") as db:
        db.execute("UPDATE runs SET checksum=? WHERE run_id=?", ("0" * 64, receipt["run_id"]))
    with pytest.raises(ContractError, match="checksum"):
        data.load_research(parent, "2026 retrospective")


def test_artifact_corruption_fails_closed(research):
    parent, root, _, _ = research
    key = data.REPORTS["2026 retrospective"][1]
    (root / "artifacts" / key[:2] / f"{key}.json").write_bytes(b"{}")
    with pytest.raises(ValueError, match="digest"):
        data.load_research(parent, "2026 retrospective")


@pytest.mark.parametrize(
    "failure", ["metrics", "probabilities", "duplicate", "incomplete", "label"]
)
def test_inconsistent_population_refused(research, monkeypatch, failure):
    parent, root, report, _ = research
    artifacts = RawStore(root / "artifacts")
    predictions = artifacts.get(report["prediction_hash"])
    if failure == "metrics":
        report["metrics"]["price"]["accuracy"] = 1
    elif failure == "probabilities":
        predictions["probabilities"]["price"][0] = [0.9, 0.9, 0.9]
    elif failure == "duplicate":
        predictions["row_hashes"][1] = predictions["row_hashes"][0]
    elif failure == "incomplete":
        predictions["row_hashes"] = predictions["row_hashes"][:-1]
        predictions["input_hashes"] = predictions["input_hashes"][:-1]
    elif failure == "label":
        targets = RawStore(parent / "real-2018-2026" / "datasets")
        row = targets.get(predictions["row_hashes"][0])
        row["label"] = "UP"
        predictions["row_hashes"][0] = targets.put(row)
    report["prediction_hash"] = artifacts.put(predictions)
    key = artifacts.put(report)
    supervised(
        root,
        "dashboard_test",
        {"test_report_hash": key},
        lambda: {"report_hash": key},
        lambda result: artifacts.get(result["report_hash"]),
    )
    monkeypatch.setitem(data.REPORTS, "2026 retrospective", ("evaluation", key))
    with pytest.raises(ValueError):
        data.load_research(parent, "2026 retrospective")


def research_app(parent, monkeypatch):
    from marketpulse.research_ui import cached_research

    cached_research.clear()
    monkeypatch.setenv("MARKETPULSE_DASHBOARD_MODE", "research")
    monkeypatch.setenv("MARKETPULSE_RESEARCH_DATA_DIR", str(parent))
    return AppTest.from_file(
        str(Path(__file__).parents[1] / "src/marketpulse/ui.py"), default_timeout=45
    ).run()


def test_all_views_filter_reveal_reset_and_exports(research, monkeypatch):
    app = research_app(research[0], monkeypatch)
    assert not app.exception and not app.error
    app.radio[0].set_value("Model diagnostics").run()
    assert not app.exception and len(app.dataframe) == 1
    app.radio[0].set_value("Prediction replay").run()
    assert not app.exception and "research_revealed" not in app.session_state
    assert not app.info
    next(b for b in app.button if b.label == "Reveal actual outcome").click().run()
    assert not app.exception and app.info
    next(s for s in app.selectbox if s.label == "Replay company").select("NVDA").run()
    assert not app.exception and not app.info
    assert "research_revealed" not in app.session_state
    app.radio[0].set_value("Data & provenance").run()
    assert not app.exception and len(app.dataframe) == 1
    app.radio[0].set_value("Operations").run()
    assert not app.exception and len(app.dataframe) == 2
    app.radio[0].set_value("Overview").run()
    app.multiselect[0].set_value([]).run()
    assert not app.exception and "No company-day examples" in app.info[0].value


def test_ui_unavailable_never_falls_back_to_fixture(tmp_path, monkeypatch):
    app = research_app(tmp_path / "missing", monkeypatch)
    assert not app.exception
    assert "No demo results have been substituted" in app.error[0].value
    assert not (tmp_path / "missing").exists()


def test_operations_verifies_receipts_without_writes(research):
    result = data.operations(research[0], "2026 retrospective")
    assert result["counts"] == {"Verified complete": 1}
    assert result["reported_stage"] == "Not recorded"
    assert not result["build_lock_present"]


def test_development_requires_native_release_to_report_binding(research, monkeypatch):
    parent, root, original_report, _ = research
    artifacts = RawStore(root / "artifacts")
    targets = RawStore(parent / "real-2018-2026" / "datasets")
    predictions = artifacts.get(original_report["prediction_hash"])
    hashes = []
    for row_hash in predictions["row_hashes"]:
        row = targets.get(row_hash)
        row["session"] = row["session"].replace("2026", "2025")
        hashes.append(targets.put(row))
    report = {
        "schema": "chronological-expert-stack/1",
        "availability_tier": "HISTORICAL_APPROXIMATE",
        "paper_action_authorized": False,
        "evaluation_kind": "DEVELOPMENT_NOT_FINAL_TEST",
        "selection_row_hashes": hashes,
        "selection_input_hashes": predictions["input_hashes"],
        "predictions_hash": artifacts.put(predictions["probabilities"]),
        "metrics": original_report["metrics"],
    }
    report_hash = artifacts.put(report)
    release_hash = artifacts.put({"report_hash": report_hash})
    supervised(
        root,
        "dashboard_test",
        {"test_release_hash": release_hash},
        lambda: {"release_hash": release_hash},
        lambda result: artifacts.get(result["release_hash"]),
    )
    monkeypatch.setattr(data, "RELEASE", release_hash)
    monkeypatch.setitem(data.REPORTS, "2025 development", ("evaluation", report_hash))
    view = data.load_research(parent, "2025 development")
    assert len(view.rows) == 18 and all(view.rows.session.str.startswith("2025"))
    assert view.report_hash == report_hash
    monkeypatch.setitem(data.REPORTS, "2025 development", ("evaluation", digest({"wrong": True})))
    with pytest.raises(ValueError, match="Release/report binding"):
        data.load_research(parent, "2025 development")


def test_operations_retains_held_states_without_auto_retry(research):
    parent, root, _, _ = research
    with sqlite3.connect(root / "v2-jobs.sqlite3") as db:
        db.execute(
            "INSERT INTO extraction_jobs VALUES (?, ?, ?, ?, ?)",
            ("held-test", "2026-01-05", None, "UNKNOWN", None),
        )
    assert data.operations(parent, "2026 retrospective")["counts"] == {
        "Verified complete": 1,
        "UNKNOWN": 1,
    }
    with data.read_database(root / "v2-jobs.sqlite3") as db:
        assert db.execute(
            "SELECT status FROM extraction_jobs WHERE job_key='held-test'"
        ).fetchone() == ("UNKNOWN",)


def test_cli_research_does_not_require_or_initialize_fixture(tmp_path, monkeypatch):
    import subprocess

    from marketpulse.cli import main

    calls = []
    monkeypatch.setattr(
        subprocess, "call", lambda command, **kwargs: calls.append((command, kwargs)) or 0
    )
    assert (
        main(
            [
                "dashboard",
                "--research-data-dir",
                str(tmp_path),
                "--data-dir",
                str(tmp_path / "no-demo"),
            ]
        )
        == 0
    )
    assert not (tmp_path / "no-demo").exists()
    assert calls[0][1]["env"]["MARKETPULSE_DASHBOARD_MODE"] == "research"
    assert "--server.address=127.0.0.1" in calls[0][0]
    assert "--browser.gatherUsageStats=false" in calls[0][0]


def test_cli_fixture_still_requires_ready_service(tmp_path, monkeypatch):
    import subprocess

    from marketpulse.cli import main

    calls = []
    monkeypatch.setattr(subprocess, "call", lambda *args, **kwargs: calls.append(args) or 0)
    assert main(["dashboard", "--mode", "fixture", "--data-dir", str(tmp_path)]) == 2
    assert not calls
