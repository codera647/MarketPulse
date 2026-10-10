from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas_market_calendars as mcal
import pytest

from marketpulse.alpaca import AlpacaClient, CapturedPage
from marketpulse.cli import sessions_between
from marketpulse.clock import session_window, utc_iso
from marketpulse.constants import SYMBOLS, ZONE
from marketpulse.extraction import ExtractionConfig, ExtractionPipeline

SESSION = date(2026, 10, 9)
AFTER_CUTOFF = datetime(2026, 10, 10, 0, 0, tzinfo=timezone.utc)
BEFORE_CUTOFF = datetime(2026, 10, 9, 8, 58, tzinfo=ZoneInfo(ZONE))


def sample_bars() -> dict:
    schedule = mcal.get_calendar("NYSE").schedule(
        start_date=SESSION - timedelta(days=45), end_date=SESSION - timedelta(days=1)
    )
    dates = schedule.index.date[-21:]
    return {
        symbol: [
            {"t": utc_iso(datetime.combine(day, time.min, ZoneInfo(ZONE))),
             "o": 100.0, "h": 102.0, "l": 99.0, "c": 101.0, "v": 1000}
            for day in dates
        ]
        for symbol in SYMBOLS
    }


def sample_news() -> list[dict]:
    created = session_window(SESSION).previous_close + timedelta(minutes=30)
    return [
        {"id": 42, "created_at": utc_iso(created), "updated_at": utc_iso(created),
         "headline": "Apple announces a new product", "summary": "Sample news",
         "symbols": ["AAPL"]}
    ]


class FakeClient:
    def __init__(self, *, news=None, bars=None, received=AFTER_CUTOFF):
        self.news = sample_news() if news is None else news
        self.bars = sample_bars() if bars is None else bars
        self.received = received
        self.calls = []

    def pages(self, source, endpoint, params, item_key, *, max_pages):
        self.calls.append((source, endpoint, params, max_pages))
        if source == "alpaca_news":
            items = self.news
        elif source == "alpaca_outcome_bars":
            items = {
                symbol: [
                    {"t": utc_iso(datetime.combine(SESSION, time.min, ZoneInfo(ZONE))),
                     "o": 101.0, "h": 102.0, "l": 99.0, "c": 100.0, "v": 1200}
                ]
                for symbol in SYMBOLS
            }
        else:
            items = self.bars
        payload = {item_key: items, "next_page_token": None}
        return [CapturedPage(source, endpoint, params, utc_iso(self.received), "fake-id", payload)]


def test_extraction_records_snapshots_and_trailforge_receipts(tmp_path):
    client = FakeClient()
    pipeline = ExtractionPipeline(tmp_path, client, clock=lambda: AFTER_CUTOFF)
    first = pipeline.run(ExtractionConfig(SESSION))
    assert first["state"] == "COMPLETE"
    assert first["tier"] == "HISTORICAL_APPROXIMATE"
    assert first["eligible_article_versions"] == 1
    assert first["bar_versions"] == 147
    assert len(first["snapshots"]) == 6
    assert set(first["trailforge_receipts"]) == {"news", "bars", "verify"}
    assert pipeline.run(ExtractionConfig(SESSION)) == first
    assert len(client.calls) == 2
    with sqlite3.connect(tmp_path / "marketpulse.sqlite3") as db:
        assert db.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0] == 6
        assert db.execute("SELECT news_count FROM snapshots WHERE symbol='AAPL'").fetchone()[0] == 1
        assert db.execute("SELECT news_count FROM snapshots WHERE symbol='NVDA'").fetchone()[0] == 0
    from trailforge.runtime import Harness

    # The harness authority is separate from the product ledger.
    assert (tmp_path / "trailforge.sqlite3").is_file()
    assert Harness is not None


def test_healthy_empty_news_is_not_provider_failure(tmp_path):
    manifest = ExtractionPipeline(
        tmp_path, FakeClient(news=[]), clock=lambda: AFTER_CUTOFF
    ).run(ExtractionConfig(SESSION))
    assert manifest["state"] == "COMPLETE"
    assert manifest["eligible_article_versions"] == 0


def test_missing_or_future_price_bar_fails_verification(tmp_path):
    bars = sample_bars()
    bars["SPY"] = []
    manifest = ExtractionPipeline(
        tmp_path / "missing", FakeClient(bars=bars), clock=lambda: AFTER_CUTOFF
    ).run(ExtractionConfig(SESSION))
    assert manifest["state"] == "FAILED"
    with sqlite3.connect(tmp_path / "missing" / "marketpulse.sqlite3") as db:
        assert db.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0] == 0

    bars = sample_bars()
    bars["AAPL"].append(
        {"t": utc_iso(datetime.combine(SESSION, time.min, ZoneInfo(ZONE))),
         "o": 100, "h": 102, "l": 99, "c": 101, "v": 1000}
    )
    manifest = ExtractionPipeline(
        tmp_path / "future", FakeClient(bars=bars), clock=lambda: AFTER_CUTOFF
    ).run(ExtractionConfig(SESSION))
    assert manifest["state"] == "FAILED"


def test_forward_capture_is_strict_only_if_all_pages_arrive_by_cutoff(tmp_path):
    manifest = ExtractionPipeline(
        tmp_path, FakeClient(received=BEFORE_CUTOFF), clock=lambda: BEFORE_CUTOFF
    ).run(ExtractionConfig(SESSION, mode="forward"))
    assert manifest["tier"] == "RECORDED_STRICT"
    assert manifest["news_query_end_utc"] == utc_iso(BEFORE_CUTOFF)


def test_agent_reach_capture_is_supplementary(tmp_path):
    url = "https://example.com/public-article"
    manifest = ExtractionPipeline(
        tmp_path, FakeClient(), clock=lambda: AFTER_CUTOFF,
        web_reader=lambda requested: "Example article about a company" if requested == url else "",
    ).run(ExtractionConfig(SESSION, web_urls=(url,)))
    assert manifest["supplementary_web_captures"] == 1
    assert manifest["eligible_article_versions"] == 1
    with sqlite3.connect(tmp_path / "marketpulse.sqlite3") as db:
        assert db.execute("SELECT COUNT(*) FROM web_captures").fetchone()[0] == 1
        assert db.execute("SELECT news_count FROM snapshots WHERE symbol='AAPL'").fetchone()[0] == 1


def test_provider_error_is_held_without_accepted_snapshot(tmp_path):
    class FailingClient:
        calls = 0

        def pages(self, *args, **kwargs):
            self.calls += 1
            raise TimeoutError("simulated provider timeout")

    client = FailingClient()
    pipeline = ExtractionPipeline(tmp_path, client, clock=lambda: AFTER_CUTOFF)
    first = pipeline.run(ExtractionConfig(SESSION))
    assert first["state"] == "WAITING_HUMAN"
    assert pipeline.run(ExtractionConfig(SESSION)) == first
    assert client.calls == 1  # Trailforge does not silently retry an UNKNOWN task.
    with sqlite3.connect(tmp_path / "marketpulse.sqlite3") as db:
        assert db.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0] == 0


def test_post_cutoff_revision_is_not_an_eligible_article(tmp_path):
    article = sample_news()[0]
    article["updated_at"] = utc_iso(session_window(SESSION).cutoff + timedelta(minutes=1))
    manifest = ExtractionPipeline(
        tmp_path, FakeClient(news=[article]), clock=lambda: AFTER_CUTOFF
    ).run(ExtractionConfig(SESSION))
    assert manifest["eligible_article_versions"] == 0


def test_backfill_range_is_bounded_to_exchange_sessions():
    assert sessions_between(date(2026, 10, 9), date(2026, 10, 10)) == [SESSION]


def test_non_session_is_rejected_and_early_close_is_respected():
    with pytest.raises(ValueError, match="not a supported NYSE session"):
        session_window(date(2026, 10, 10))
    early = session_window(date(2026, 11, 27))
    assert early.market_close.astimezone(ZoneInfo(ZONE)).hour == 13


def test_early_forward_capture_is_recorded_but_not_fresh(tmp_path):
    early = datetime(2026, 10, 9, 8, 30, tzinfo=ZoneInfo(ZONE))
    manifest = ExtractionPipeline(
        tmp_path, FakeClient(received=early), clock=lambda: early
    ).run(ExtractionConfig(SESSION, mode="forward"))
    assert manifest["tier"] == "RECORDED_STRICT"
    assert manifest["fresh_for_0900"] is False


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload
        self.content = json.dumps(payload).encode("utf-8")
        self.headers = {"X-Request-ID": "test"}

    def raise_for_status(self):
        return None

    def iter_content(self, chunk_size):
        yield self.content

    def close(self):
        return None


class FakeSession:
    def __init__(self):
        self.tokens = []

    def mount(self, *args):
        return None

    def get(self, url, *, params, headers, timeout, stream):
        self.tokens.append(params.get("page_token"))
        if len(self.tokens) == 1:
            return FakeResponse({"news": [{"id": 1}], "next_page_token": "next"})
        return FakeResponse({"news": [{"id": 2}], "next_page_token": None})


def test_alpaca_pagination_follows_next_token():
    fake = FakeSession()
    client = AlpacaClient("key", "secret", session=fake)
    pages = client.pages("alpaca_news", "/v1beta1/news", {"symbols": "AAPL"},
                         "news", max_pages=2)
    assert len(pages) == 2
    assert fake.tokens == [None, "next"]
