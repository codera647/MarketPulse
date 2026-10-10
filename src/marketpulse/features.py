"""Versioned pre-open features shared by replay and future model training."""

from __future__ import annotations

import json
import math
import sqlite3
import statistics
from contextlib import closing
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas_market_calendars as mcal

from marketpulse.clock import parse_time, session_window, utc_iso
from marketpulse.constants import STOCKS, ZONE
from marketpulse.storage import RawStore, digest

FEATURE_SCHEMA = "preopen-numeric/1"
FEATURE_NAMES = (
    "prior_return_1d", "prior_return_5d", "prior_return_20d",
    "prior_volatility_20d", "prior_volume_mean_5d", "prior_volume_mean_20d",
    "prior_volume_ratio_5d_20d", "spy_prior_return_1d", "spy_prior_return_5d",
    "spy_prior_return_20d", "spy_prior_volatility_20d", "news_article_count",
    "news_summary_count", "news_earnings_headline_count",
    "news_guidance_headline_count", "news_acquisition_headline_count",
    "news_regulatory_headline_count", "news_latest_age_minutes",
)
HEADLINE_RULES = {
    "earnings": ("earnings", "quarterly results", "quarter results"),
    "guidance": ("guidance", "outlook", "forecast"),
    "acquisition": ("acquisition", "acquires", "merger", "buyout"),
    "regulatory": ("regulator", "regulatory", "lawsuit", "antitrust", "ftc", "sec"),
}


def _manifest(row: sqlite3.Row | None) -> dict:
    if row is None or row["status"] != "COMPLETE" or not row["manifest_json"]:
        raise ValueError("snapshot source job is missing or incomplete")
    manifest = json.loads(row["manifest_json"])
    if manifest.get("state") != "COMPLETE" or manifest.get("job_key") != row["job_key"]:
        raise ValueError("snapshot source manifest disagrees with job")
    return manifest


def _load_snapshot(data_dir: Path, snapshot_hash: str) -> tuple[dict, dict, list, list, list]:
    if len(snapshot_hash) != 64 or any(c not in "0123456789abcdef" for c in snapshot_hash):
        raise ValueError("snapshot ID must be a full lowercase SHA-256 hash")
    data_dir = data_dir.resolve()
    database = data_dir / "marketpulse.sqlite3"
    if not database.is_file():
        raise ValueError("application database does not exist")
    with closing(sqlite3.connect(f"{database.as_uri()}?mode=ro", uri=True)) as db:
        db.row_factory = sqlite3.Row
        row = db.execute(
            "SELECT * FROM snapshots WHERE snapshot_hash=?", (snapshot_hash,)
        ).fetchone()
        if row is None or row["symbol"] not in STOCKS:
            raise ValueError("target company snapshot does not exist")
        snapshot = dict(row)
        source = _manifest(db.execute(
            "SELECT * FROM extraction_jobs WHERE job_key=?", (snapshot["job_key"],)
        ).fetchone())
        bar_rows = [dict(item) for item in db.execute(
            "SELECT b.*, j.received_at AS job_received_at, "
            "j.raw_page_digest AS job_raw_page_digest "
            "FROM job_price_bars j JOIN price_bars b "
            "ON b.version_hash=j.version_hash WHERE j.job_key=?", (snapshot["job_key"],)
        )]
        article_rows = [dict(item) for item in db.execute(
            "SELECT a.*, j.received_at AS job_received_at, "
            "j.raw_page_digest AS job_raw_page_digest FROM job_article_versions j "
            "JOIN article_versions a ON a.version_hash=j.version_hash "
            "WHERE j.job_key=?", (snapshot["job_key"],)
        )]
    article_hashes = json.loads(snapshot["article_hashes_json"])
    company_hashes = json.loads(snapshot["bar_hashes_json"])
    spy_hashes = json.loads(snapshot["spy_bar_hashes_json"])
    content = {
        "job_key": snapshot["job_key"], "session": snapshot["session"],
        "symbol": snapshot["symbol"], "cutoff_utc": snapshot["cutoff_utc"],
        "availability_tier": snapshot["availability_tier"],
        "fresh_for_0900": bool(snapshot["fresh_for_0900"]),
        "article_hashes": article_hashes, "bar_hashes": company_hashes,
        "spy_bar_hashes": spy_hashes, "news_count": snapshot["news_count"],
    }
    if digest(content) != snapshot_hash:
        raise ValueError("snapshot identity check failed")
    if source.get("snapshots", {}).get(snapshot["symbol"]) != snapshot_hash:
        raise ValueError("snapshot not present in source manifest")
    if any(len(set(items)) != len(items)
           for items in (article_hashes, company_hashes, spy_hashes)):
        raise ValueError("duplicate source version in snapshot")
    bar_index = {item["version_hash"]: item for item in bar_rows}
    article_index = {item["version_hash"]: item for item in article_rows}
    if (any(key not in bar_index for key in (*company_hashes, *spy_hashes))
            or any(key not in article_index for key in article_hashes)):
        raise ValueError("snapshot version is missing from its extraction job")
    company_bars = [bar_index[key] for key in company_hashes]
    spy_bars = [bar_index[key] for key in spy_hashes]
    articles = [article_index[key] for key in article_hashes]
    _verify_raw_versions(data_dir, source, [*company_bars, *spy_bars], articles)
    return (
        snapshot, source,
        company_bars, spy_bars, articles,
    )


def _verify_raw_versions(
    data_dir: Path, source: dict, bars: list[dict], articles: list[dict]
) -> None:
    raw = RawStore(data_dir / "raw")
    page_cache: dict[str, dict] = {}
    bar_indexes: dict[str, dict] = {}
    article_indexes: dict[str, dict] = {}

    def page_for(row: dict, expected_source: str) -> dict:
        key = row["job_raw_page_digest"]
        if key not in page_cache:
            page_cache[key] = raw.get(key)
        page = page_cache[key]
        if page.get("source") != expected_source or page.get("received_at") != row[
            "job_received_at"
        ]:
            raise ValueError("raw source page or receipt mismatch")
        return page

    for row in bars:
        page = page_for(row, "alpaca_bars")
        params = page.get("params") or {}
        if (params.get("feed") != source["feed"]
                or params.get("adjustment") != source["adjustment"]
                or params.get("timeframe") != "1Day"):
            raise ValueError("raw bar request convention mismatch")
        key = row["job_raw_page_digest"]
        if key not in bar_indexes:
            container = page.get("payload", {}).get("bars")
            if not isinstance(container, dict):
                raise ValueError("raw bar page is malformed")
            bar_indexes[key] = {
                digest({"source": "alpaca", "feed": source["feed"],
                        "adjustment": source["adjustment"], "symbol": symbol,
                        "item": item}): (symbol, item)
                for symbol, items in container.items() for item in items
            }
        found = bar_indexes[key].get(row["version_hash"])
        if found is None:
            raise ValueError("bar version absent from its raw page")
        symbol, item = found
        if (symbol != row["symbol"] or utc_iso(parse_time(item["t"])) != row["bar_time"]
                or any(float(item[field]) != row[column] for field, column in (
                    ("o", "open"), ("h", "high"), ("l", "low"),
                    ("c", "close"), ("v", "volume"),
                ))):
            raise ValueError("normalized bar disagrees with immutable raw version")

    for row in articles:
        page = page_for(row, "alpaca_news")
        key = row["job_raw_page_digest"]
        if key not in article_indexes:
            items = page.get("payload", {}).get("news")
            if not isinstance(items, list):
                raise ValueError("raw news page is malformed")
            article_indexes[key] = {
                digest({"source": "alpaca_benzinga", "item": item}): item
                for item in items
            }
        item = article_indexes[key].get(row["version_hash"])
        if item is None:
            raise ValueError("article version absent from its raw page")
        if (str(item["id"]) != row["provider_id"]
                or utc_iso(parse_time(item["created_at"])) != row["created_at"]
                or utc_iso(parse_time(item["updated_at"])) != row["updated_at"]
                or str(item["headline"]).strip() != row["headline"]
                or item.get("summary") != row["summary"]
                or sorted(set(item.get("symbols") or []) & set(STOCKS))
                != json.loads(row["symbols_json"])):
            raise ValueError("normalized article disagrees with immutable raw version")


@lru_cache(maxsize=2048)
def _expected_prior_dates(session: date) -> tuple[date, ...]:
    dates = [item.date() for item in mcal.get_calendar("NYSE").valid_days(
        start_date=session - timedelta(days=60), end_date=session - timedelta(days=1)
    )]
    if len(dates) < 21:
        raise ValueError("calendar has fewer than 21 prior exchange sessions")
    return tuple(dates[-21:])


def _price_features(rows: list[dict], symbol: str, source: dict, session: date) -> dict:
    if any(row["symbol"] != symbol or row["feed"] != source["feed"]
           or row["adjustment"] != source["adjustment"] for row in rows):
        raise ValueError("snapshot price symbol, feed, or adjustment mismatch")
    indexed: dict[date, dict] = {}
    for row in rows:
        day = parse_time(row["bar_time"]).astimezone(ZoneInfo(ZONE)).date()
        if day >= session or day in indexed:
            raise ValueError("future or duplicate price session in snapshot")
        indexed[day] = row
    dates = _expected_prior_dates(session)
    if any(day not in indexed for day in dates):
        raise ValueError(f"{symbol}: missing one or more of 21 prior exchange sessions")
    ordered = [indexed[day] for day in dates]
    closes = [float(row["close"]) for row in ordered]
    volumes = [float(row["volume"]) for row in ordered]
    if (any(not math.isfinite(value) or value <= 0 for value in closes)
            or any(not math.isfinite(value) or value <= 0 for value in volumes)):
        raise ValueError("nonpositive or nonfinite prior close/volume")
    returns = [closes[index] / closes[index - 1] - 1 for index in range(1, 21)]
    mean_5 = statistics.fmean(volumes[-5:])
    mean_20 = statistics.fmean(volumes[-20:])
    return {
        "return_1d": returns[-1],
        "return_5d": closes[-1] / closes[-6] - 1,
        "return_20d": closes[-1] / closes[0] - 1,
        "volatility_20d": statistics.pstdev(returns),
        "volume_mean_5d": mean_5,
        "volume_mean_20d": mean_20,
        "volume_ratio_5d_20d": mean_5 / mean_20,
        "bar_dates": [day.isoformat() for day in dates],
    }


def _headline_tag_count(articles: list[dict], tag: str) -> int:
    import re

    phrases = HEADLINE_RULES[tag]
    return sum(any(re.search(r"\b" + re.escape(phrase) + r"\b", row["headline"], re.I)
                   for phrase in phrases) for row in articles)


def build_features(
    snapshot: dict, source: dict, company_bars: list[dict], spy_bars: list[dict],
    articles: list[dict],
) -> dict:
    """The one feature function for offline extraction, replay, and future scoring."""
    session = date.fromisoformat(snapshot["session"])
    window = session_window(session)
    if source.get("session") != snapshot["session"] or snapshot["cutoff_utc"] != utc_iso(
        window.cutoff
    ):
        raise ValueError("snapshot session or cutoff mismatch")
    if snapshot["availability_tier"] != source["tier"]:
        raise ValueError("snapshot availability tier mismatch")
    if len(articles) != snapshot["news_count"]:
        raise ValueError("snapshot news count mismatch")
    company = _price_features(company_bars, snapshot["symbol"], source, session)
    spy = _price_features(spy_bars, "SPY", source, session)
    latest_article = None
    for article in articles:
        created = parse_time(article["created_at"])
        updated = parse_time(article["updated_at"])
        received = parse_time(article["job_received_at"])
        if (snapshot["symbol"] not in json.loads(article["symbols_json"])
                or not window.previous_close < created <= updated <= window.cutoff
                or (snapshot["availability_tier"] == "RECORDED_STRICT"
                    and received > window.cutoff)):
            raise ValueError("ineligible article version in snapshot")
        latest_article = max(latest_article, updated) if latest_article else updated
    values = {
        "prior_return_1d": company["return_1d"],
        "prior_return_5d": company["return_5d"],
        "prior_return_20d": company["return_20d"],
        "prior_volatility_20d": company["volatility_20d"],
        "prior_volume_mean_5d": company["volume_mean_5d"],
        "prior_volume_mean_20d": company["volume_mean_20d"],
        "prior_volume_ratio_5d_20d": company["volume_ratio_5d_20d"],
        "spy_prior_return_1d": spy["return_1d"],
        "spy_prior_return_5d": spy["return_5d"],
        "spy_prior_return_20d": spy["return_20d"],
        "spy_prior_volatility_20d": spy["volatility_20d"],
        "news_article_count": len(articles),
        "news_summary_count": sum(bool(row["summary"]) for row in articles),
        "news_earnings_headline_count": _headline_tag_count(articles, "earnings"),
        "news_guidance_headline_count": _headline_tag_count(articles, "guidance"),
        "news_acquisition_headline_count": _headline_tag_count(articles, "acquisition"),
        "news_regulatory_headline_count": _headline_tag_count(articles, "regulatory"),
        "news_latest_age_minutes": (
            (window.cutoff - latest_article).total_seconds() / 60
            if latest_article else None
        ),
    }
    if tuple(values) != FEATURE_NAMES or any(
        value is not None and (not isinstance(value, (int, float)) or not math.isfinite(value))
        for value in values.values()
    ):
        raise ValueError("feature schema or finite-value check failed")
    identity = {
        "schema": FEATURE_SCHEMA, "snapshot_hash": snapshot["snapshot_hash"],
        "values": [values[name] for name in FEATURE_NAMES],
    }
    return {
        "feature_hash": digest(identity), "feature_schema": FEATURE_SCHEMA,
        "feature_names": list(FEATURE_NAMES), "values": values,
        "snapshot_hash": snapshot["snapshot_hash"],
        "symbol": snapshot["symbol"], "session": snapshot["session"],
        "cutoff_utc": snapshot["cutoff_utc"],
        "availability_tier": snapshot["availability_tier"],
        "fresh_for_0900": bool(snapshot["fresh_for_0900"]),
        "feed": source["feed"], "adjustment": source["adjustment"],
        "source_bar_dates": company["bar_dates"],
        "spy_bar_dates": spy["bar_dates"],
        "article_version_hashes": json.loads(snapshot["article_hashes_json"]),
        "status": "FEATURE_PREVIEW_NOT_TRAINED",
    }


def features_for_snapshot(data_dir: Path, snapshot_hash: str) -> dict:
    """Hydrate one saved snapshot, then use the same pure builder as future scoring."""
    return build_features(*_load_snapshot(data_dir, snapshot_hash))
