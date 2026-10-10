from __future__ import annotations

import json
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import pytest
from test_extraction import FakeClient

from marketpulse.audit import AuditCase, run_audit, validate_cases
from marketpulse.clock import parse_time
from marketpulse.constants import ZONE
from marketpulse.extraction import ExtractionPipeline

NOW = datetime(2026, 10, 10, 16, 0, tzinfo=timezone.utc)


def test_audit_case_validation():
    assert AuditCase.parse("ordinary:2026-10-09") == AuditCase("ordinary", date(2026, 10, 9))
    with pytest.raises(ValueError, match="case kind"):
        AuditCase.parse("unknown:2026-10-09")
    with pytest.raises(ValueError, match="not a trading session"):
        validate_cases((AuditCase("ordinary", date(2026, 10, 10)),))
    with pytest.raises(ValueError, match="not a holiday"):
        validate_cases((AuditCase("holiday", date(2026, 10, 9)),))
    with pytest.raises(ValueError, match="at least one trading-session"):
        validate_cases((AuditCase("holiday", date(2025, 11, 27)),))


def test_plan_creates_dated_report_without_provider(tmp_path):
    report, paths = run_audit(
        (AuditCase("ordinary", date(2026, 10, 9)),
         AuditCase("holiday", date(2025, 11, 27))),
        pipeline=None, feed="iex", adjustment="split", include_content=False,
        output_dir=tmp_path, clock=lambda: NOW,
    )
    assert report["status"] == "NOT_RUN"
    assert report["cases"][0]["status"] == "NOT_RUN"
    assert report["cases"][1]["status"] == "CALENDAR_CLOSED"
    assert "earnings" in report["missing_case_categories"]
    assert json.loads(paths[0].read_text(encoding="utf-8"))["status"] == "NOT_RUN"
    assert "No provider request was made" in paths[1].read_text(encoding="utf-8")


def test_live_fixture_audit_has_coverage_and_harness_evidence(tmp_path):
    pipeline = ExtractionPipeline(tmp_path / "runtime", FakeClient(), clock=lambda: NOW)
    report, paths = run_audit(
        (AuditCase("ordinary", date(2026, 10, 9)),),
        pipeline=pipeline, feed="iex", adjustment="split", include_content=False,
        output_dir=tmp_path / "reports", clock=lambda: NOW,
    )
    assert report["status"] == "TECHNICAL_REVIEW_REQUIRED"
    case = report["cases"][0]
    assert case["status"] == "EXTRACTED"
    assert case["evidence"]["snapshot_count"] == 6
    assert case["evidence"]["symbols"]["SPY"]["previous_session_covered"]
    assert case["evidence"]["symbols"]["AAPL"]["eligible_articles"] == 1
    assert case["evidence"]["symbols"]["AAPL"]["missing_last_21_sessions"] == []
    assert case["evidence"]["observed_bar_field_types"]["t"] == ["str"]
    assert "headline" in case["evidence"]["observed_news_fields"]
    assert case["provider_failures"] == []
    assert case["trailforge"]["state"] == "COMPLETED"
    assert case["trailforge"]["verify_evidence"]["verdict"] == "PASS"
    assert case["outcome_probe"]["state"] == "COMPLETE"
    assert case["outcome_probe"]["trailforge"]["verify_evidence"]["verdict"] == "PASS"
    assert case["outcome_probe"]["symbols"]["AAPL"]["open"] == 101.0
    outcome_call = next(call for call in pipeline.client.calls if call[0] == "alpaca_outcome_bars")
    assert parse_time(outcome_call[2]["end"]).astimezone(ZoneInfo(ZONE)).date() == date(2026, 10, 9)
    with pipeline.store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM price_bars").fetchone()[0] == 147
    assert paths[0].is_file() and paths[1].is_file()


def test_live_audit_reports_sanitized_entitlement_failure(tmp_path):
    from marketpulse.alpaca import ProviderError

    class ForbiddenClient:
        failures = []

        def pages(self, source, *args, **kwargs):
            self.failures.append({"source": source, "status_code": 403, "reason": "http_error"})
            raise ProviderError(source, 403, "http_error")

    report, _ = run_audit(
        (AuditCase("ordinary", date(2026, 10, 9)),),
        pipeline=ExtractionPipeline(tmp_path / "runtime", ForbiddenClient(), clock=lambda: NOW),
        feed="sip", adjustment="split", include_content=False,
        output_dir=tmp_path / "reports", clock=lambda: NOW,
    )
    assert report["status"] == "BLOCKED"
    assert report["cases"][0]["provider_failures"][0]["status_code"] == 403
    assert "secret" not in json.dumps(report)


def test_rolling_gap_is_detected_even_with_21_bars(tmp_path):
    from marketpulse.clock import session_window, utc_iso

    class GapClient(FakeClient):
        def pages(self, source, endpoint, params, item_key, *, max_pages):
            pages = super().pages(source, endpoint, params, item_key, max_pages=max_pages)
            if source == "alpaca_bars":
                bars = pages[0].payload["bars"]["AAPL"]
                bars.pop(-2)
                bars.append({**bars[0], "t": utc_iso(session_window(date(2026, 10, 9)).bars_start)})
            return pages

    report, _ = run_audit(
        (AuditCase("ordinary", date(2026, 10, 9)),),
        pipeline=ExtractionPipeline(tmp_path / "runtime", GapClient(), clock=lambda: NOW),
        feed="iex", adjustment="split", include_content=False,
        output_dir=tmp_path / "reports", clock=lambda: NOW, page_size=10,
    )
    assert report["cases"][0]["evidence"]["symbols"]["AAPL"]["prior_daily_bar_dates"] == 21
    assert report["status"] == "BLOCKED"
    assert "rolling_window_gap" in report["cases"][0]["integrity_flags"]


def test_plan_cli_does_not_read_env_file(tmp_path, monkeypatch):
    from marketpulse import cli

    def forbidden(*args, **kwargs):
        raise AssertionError("plan mode must not read credential files")

    monkeypatch.setattr(cli, "load_alpaca_settings", forbidden)
    assert cli.main(["audit", "--plan", "--case", "ordinary:2026-10-09",
                     "--env-file", str(tmp_path / "missing"),
                     "--data-dir", str(tmp_path)]) == 0


def test_missing_outcome_symbol_blocks_label_source(tmp_path):
    class MissingOutcomeClient(FakeClient):
        def pages(self, source, endpoint, params, item_key, *, max_pages):
            result = super().pages(source, endpoint, params, item_key, max_pages=max_pages)
            if source == "alpaca_outcome_bars":
                result[0].payload["bars"].pop("SPY")
            return result

    pipeline = ExtractionPipeline(tmp_path / "runtime", MissingOutcomeClient(), clock=lambda: NOW)
    report, _ = run_audit(
        (AuditCase("ordinary", date(2026, 10, 9)),),
        pipeline=pipeline, feed="iex", adjustment="split", include_content=False,
        output_dir=tmp_path / "reports", clock=lambda: NOW,
    )
    assert report["status"] == "BLOCKED"
    case = report["cases"][0]
    assert case["status"] == "OUTCOME_SOURCE_BLOCKED"
    assert case["outcome_probe"]["trailforge"]["verify_evidence"]["verdict"] == "FAIL"
    with pipeline.store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM price_bars").fetchone()[0] == 147


def test_provider_failure_blocks_audit(tmp_path):
    class FailingClient:
        def pages(self, *args, **kwargs):
            raise TimeoutError("simulated")

    pipeline = ExtractionPipeline(tmp_path / "runtime", FailingClient(), clock=lambda: NOW)
    report, _ = run_audit(
        (AuditCase("ordinary", date(2026, 10, 9)),),
        pipeline=pipeline, feed="iex", adjustment="split", include_content=False,
        output_dir=tmp_path / "reports", clock=lambda: NOW,
    )
    assert report["status"] == "BLOCKED"
    assert report["cases"][0]["status"] == "WAITING_HUMAN"
    assert report["cases"][0]["trailforge"]["task_status"]["news"]["status"] == "UNKNOWN"


def test_repeated_data_versions_still_link_to_each_audit_job(tmp_path):
    pipeline = ExtractionPipeline(tmp_path / "runtime", FakeClient(), clock=lambda: NOW)
    first, _ = run_audit(
        (AuditCase("ordinary", date(2026, 10, 9)),),
        pipeline=pipeline, feed="iex", adjustment="split", include_content=False,
        output_dir=tmp_path / "reports", clock=lambda: NOW,
    )
    second, _ = run_audit(
        (AuditCase("ordinary", date(2026, 10, 9)),),
        pipeline=pipeline, feed="iex", adjustment="split", include_content=True,
        output_dir=tmp_path / "reports", clock=lambda: NOW,
    )
    assert first["cases"][0]["job_key"] != second["cases"][0]["job_key"]
    assert second["cases"][0]["evidence"]["symbols"]["AAPL"]["prior_daily_bar_dates"] == 21
    with pipeline.store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM job_price_bars").fetchone()[0] == 294
        assert db.execute("SELECT COUNT(*) FROM price_bars").fetchone()[0] == 147
