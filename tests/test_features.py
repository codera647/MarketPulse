from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas_market_calendars as mcal
import pytest
from test_extraction import FakeClient, sample_news

from marketpulse.cli import main
from marketpulse.clock import utc_iso
from marketpulse.constants import SYMBOLS, ZONE
from marketpulse.extraction import ExtractionConfig, ExtractionPipeline
from marketpulse.features import FEATURE_NAMES, features_for_snapshot

SESSION = date(2026, 10, 9)
NOW = datetime(2026, 10, 10, 16, tzinfo=timezone.utc)


def twenty_one_bars():
    dates = [item.date() for item in mcal.get_calendar("NYSE").valid_days(
        start_date=SESSION - timedelta(days=45), end_date=SESSION - timedelta(days=1)
    )][-21:]
    return {
        symbol: [
            {
                "t": utc_iso(datetime.combine(day, time.min, ZoneInfo(ZONE))),
                "o": (200 if symbol == "SPY" else 100) + (2 if symbol == "SPY" else 1) * i - 1,
                "h": (200 if symbol == "SPY" else 100) + (2 if symbol == "SPY" else 1) * i + 1,
                "l": (200 if symbol == "SPY" else 100) + (2 if symbol == "SPY" else 1) * i - 2,
                "c": (200 if symbol == "SPY" else 100) + (2 if symbol == "SPY" else 1) * i,
                "v": 1000 + i,
            }
            for i, day in enumerate(dates)
        ] for symbol in SYMBOLS
    }


@pytest.fixture
def feature_fixture(tmp_path):
    news = sample_news()
    news[0]["headline"] = "Apple quarterly earnings and guidance"
    data_dir = tmp_path / "runtime"
    pipeline = ExtractionPipeline(
        data_dir, FakeClient(bars=twenty_one_bars(), news=news), clock=lambda: NOW
    )
    manifest = pipeline.run(ExtractionConfig(SESSION))
    assert manifest["state"] == "COMPLETE"
    return data_dir, manifest


def test_shared_feature_builder_and_cli_use_only_preopen_snapshot(feature_fixture, capsys):
    data_dir, manifest = feature_fixture
    apple_hash = manifest["snapshots"]["AAPL"]
    apple = features_for_snapshot(data_dir, apple_hash)
    assert apple["feature_names"] == list(FEATURE_NAMES)
    assert apple["values"]["prior_return_20d"] == pytest.approx(0.2)
    assert apple["values"]["prior_return_5d"] == pytest.approx(120 / 115 - 1)
    assert apple["values"]["spy_prior_return_20d"] == pytest.approx(0.2)
    assert apple["values"]["news_article_count"] == 1
    assert apple["values"]["news_earnings_headline_count"] == 1
    assert apple["values"]["news_guidance_headline_count"] == 1
    assert apple["values"]["news_latest_age_minutes"] == pytest.approx(990)
    assert apple["source_bar_dates"][-1] == "2026-10-08"
    assert apple["status"] == "FEATURE_PREVIEW_NOT_TRAINED"
    assert features_for_snapshot(data_dir, apple_hash) == apple

    assert main(["feature-preview", "--snapshot-hash", apple_hash,
                 "--data-dir", str(data_dir)]) == 0
    assert json.loads(capsys.readouterr().out) == apple

    no_news = features_for_snapshot(data_dir, manifest["snapshots"]["NVDA"])
    assert no_news["values"]["news_article_count"] == 0
    assert no_news["values"]["news_latest_age_minutes"] is None
    assert no_news["feature_hash"] != apple["feature_hash"]
    with sqlite3.connect(data_dir / "marketpulse.sqlite3") as db:
        assert db.execute("SELECT COUNT(*) FROM price_bars").fetchone()[0] == 147


def test_builder_rejects_future_price_mutation(feature_fixture):
    data_dir, manifest = feature_fixture
    snapshot_hash = manifest["snapshots"]["AAPL"]
    with sqlite3.connect(data_dir / "marketpulse.sqlite3") as db:
        bar_hash = json.loads(db.execute(
            "SELECT bar_hashes_json FROM snapshots WHERE snapshot_hash=?", (snapshot_hash,)
        ).fetchone()[0])[-1]
        original_time = db.execute(
            "SELECT bar_time FROM price_bars WHERE version_hash=?", (bar_hash,)
        ).fetchone()[0]
        db.execute(
            "UPDATE price_bars SET bar_time=? WHERE version_hash=?",
            (utc_iso(datetime.combine(SESSION, time.min, ZoneInfo(ZONE))), bar_hash),
        )
    with pytest.raises(ValueError, match="normalized bar disagrees"):
        features_for_snapshot(data_dir, snapshot_hash)
    with sqlite3.connect(data_dir / "marketpulse.sqlite3") as db:
        db.execute(
            "UPDATE price_bars SET bar_time=?, close=999 WHERE version_hash=?",
            (original_time, bar_hash),
        )
    with pytest.raises(ValueError, match="normalized bar disagrees"):
        features_for_snapshot(data_dir, snapshot_hash)


def test_builder_rejects_mutated_news_text(feature_fixture):
    data_dir, manifest = feature_fixture
    with sqlite3.connect(data_dir / "marketpulse.sqlite3") as db:
        db.execute("UPDATE article_versions SET headline='changed after capture'")
    with pytest.raises(ValueError, match="normalized article disagrees"):
        features_for_snapshot(data_dir, manifest["snapshots"]["AAPL"])


def test_twenty_bars_extract_but_are_insufficient_for_twenty_day_return(tmp_path):
    data_dir = tmp_path / "runtime"
    bars = twenty_one_bars()
    for items in bars.values():
        items.pop(0)
    manifest = ExtractionPipeline(
        data_dir, FakeClient(bars=bars), clock=lambda: NOW
    ).run(
        ExtractionConfig(SESSION, min_prior_bars=20)
    )
    assert manifest["state"] == "COMPLETE"
    with pytest.raises(ValueError, match="21 prior exchange sessions"):
        features_for_snapshot(data_dir, manifest["snapshots"]["AAPL"])
