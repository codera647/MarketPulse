from __future__ import annotations

import math
from zoneinfo import ZoneInfo

from marketpulse.clock import SessionWindow, parse_time, utc_iso
from marketpulse.constants import STOCKS, SYMBOLS, ZONE
from marketpulse.storage import digest


class DataQualityError(ValueError):
    pass


def normalize_news(page: dict, raw_digest: str, window: SessionWindow) -> list[dict]:
    received_at = page["received_at"]
    items = page["payload"]["news"]
    if not isinstance(items, list):
        raise DataQualityError("news payload is not a list")
    normalized = []
    for item in items:
        if not isinstance(item, dict):
            raise DataQualityError("news item is not an object")
        try:
            provider_id = str(item["id"])
            created = parse_time(item["created_at"])
            updated = parse_time(item["updated_at"])
            headline = str(item["headline"]).strip()
            symbols = sorted(set(item.get("symbols") or []) & set(STOCKS))
        except (KeyError, TypeError, ValueError) as error:
            raise DataQualityError("news item lacks required provenance fields") from error
        if not provider_id or not headline or updated < created:
            raise DataQualityError("invalid article identity, headline, or update time")
        # Later revisions are unusable even for an approximate pre-open replay.
        if not (window.previous_close < created <= window.cutoff and updated <= window.cutoff):
            continue
        if not symbols:
            continue
        normalized.append(
            {
                "version_hash": digest({"source": "alpaca_benzinga", "item": item}),
                "provider_id": provider_id,
                "symbols": symbols,
                "created_at": utc_iso(created),
                "updated_at": utc_iso(updated),
                "received_at": received_at,
                "headline": headline,
                "summary": item.get("summary"),
                "raw_page_digest": raw_digest,
            }
        )
    return normalized


def normalize_bars(
    page: dict, raw_digest: str, window: SessionWindow, feed: str, adjustment: str
) -> list[dict]:
    container = page["payload"]["bars"]
    if not isinstance(container, dict):
        raise DataQualityError("bars payload is not an object")
    result = []
    for symbol, items in container.items():
        if symbol not in SYMBOLS or not isinstance(items, list):
            raise DataQualityError("unexpected symbol or malformed bar list")
        for item in items:
            try:
                timestamp = parse_time(item["t"])
                values = [float(item[field]) for field in ("o", "h", "l", "c", "v")]
            except (KeyError, TypeError, ValueError) as error:
                raise DataQualityError("bar lacks required fields") from error
            opening, high, low, close, volume = values
            if not all(math.isfinite(value) for value in values):
                raise DataQualityError("non-finite price or volume")
            if min(opening, high, low, close) <= 0 or volume < 0:
                raise DataQualityError("non-positive price or negative volume")
            if high < max(opening, close, low) or low > min(opening, close, high):
                raise DataQualityError("inconsistent OHLC bar")
            if timestamp.astimezone(ZoneInfo(ZONE)).date() >= window.session:
                raise DataQualityError("same-day or future bar entered pre-open data")
            result.append(
                {
                    "version_hash": digest(
                        {"source": "alpaca", "feed": feed, "adjustment": adjustment,
                         "symbol": symbol, "item": item}
                    ),
                    "symbol": symbol,
                    "bar_time": utc_iso(timestamp),
                    "feed": feed,
                    "adjustment": adjustment,
                    "open": opening,
                    "high": high,
                    "low": low,
                    "close": close,
                    "volume": volume,
                    "received_at": page["received_at"],
                    "raw_page_digest": raw_digest,
                }
            )
    return result


def select_latest_articles(articles: list[dict], symbol: str) -> list[dict]:
    latest: dict[str, dict] = {}
    for article in articles:
        if symbol not in article["symbols"]:
            continue
        current = latest.get(article["provider_id"])
        if current is None or (article["updated_at"], article["received_at"]) > (
            current["updated_at"], current["received_at"]
        ):
            latest[article["provider_id"]] = article
    return sorted(latest.values(), key=lambda row: (row["created_at"], row["provider_id"]))


def validate_bar_coverage(bars: list[dict], window: SessionWindow, min_prior_bars: int) -> None:
    expected_previous = window.previous_close.astimezone(ZoneInfo(ZONE)).date()
    for symbol in SYMBOLS:
        symbol_bars = [bar for bar in bars if bar["symbol"] == symbol]
        distinct_dates = {
            parse_time(bar["bar_time"]).astimezone(ZoneInfo(ZONE)).date()
            for bar in symbol_bars
        }
        if len(distinct_dates) < min_prior_bars:
            raise DataQualityError(f"{symbol}: only {len(distinct_dates)} prior bars")
        if max(distinct_dates) != expected_previous:
            raise DataQualityError(f"{symbol}: latest bar is not previous session")


def build_snapshots(
    job_key: str,
    window: SessionWindow,
    articles: list[dict],
    bars: list[dict],
    *,
    tier: str,
    fresh_for_0900: bool,
) -> list[dict]:
    spy_hashes = [
        bar["version_hash"] for bar in sorted(bars, key=lambda row: row["bar_time"])
        if bar["symbol"] == "SPY"
    ]
    result = []
    for symbol in STOCKS:
        selected = select_latest_articles(articles, symbol)
        article_hashes = [article["version_hash"] for article in selected]
        bar_hashes = [
            bar["version_hash"] for bar in sorted(bars, key=lambda row: row["bar_time"])
            if bar["symbol"] == symbol
        ]
        content = {
            "job_key": job_key,
            "session": window.session.isoformat(),
            "symbol": symbol,
            "cutoff_utc": utc_iso(window.cutoff),
            "availability_tier": tier,
            "fresh_for_0900": fresh_for_0900,
            "article_hashes": article_hashes,
            "bar_hashes": bar_hashes,
            "spy_bar_hashes": spy_hashes,
            "news_count": len(article_hashes),
        }
        result.append({**content, "snapshot_hash": digest(content)})
    return result
