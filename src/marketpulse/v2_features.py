"""Input-only enriched features, with missingness and auditable provenance."""

from __future__ import annotations

import math
import statistics
from datetime import date, timedelta

from marketpulse.baselines import PRICE_FEATURES
from marketpulse.features import _expected_prior_dates
from marketpulse.preprocessing import extend_news_registry, mask_seen_stories
from marketpulse.storage import digest
from marketpulse.v2_news import news_values
from marketpulse.v2_sources import SECTOR_PROXY, premarket_values

FEATURE_VERSION = "preopen-enriched/4"


def mask_rows(rows: list[dict]) -> list[dict]:
    registry = {"provider_ids": {}, "headline_groups": {}}
    groups = {}
    for row in rows:
        groups.setdefault(row["session"], []).append(row)
    result = []
    for session in sorted(groups):
        current = groups[session]
        for row in sorted(current, key=lambda item: item["symbol"]):
            result.append(
                {
                    **row,
                    "news": mask_seen_stories(registry, row["news"], session),
                    "raw_news_count": len(row["news"]),
                }
            )
        # Shared date stories stay eligible for every company on their first date.
        extend_news_registry(registry, current)
    return result


def sector_values(session: str, symbol: str, daily: dict) -> dict:
    days = [day.isoformat() for day in _expected_prior_dates(date.fromisoformat(session))]
    bars = [daily.get((day, SECTOR_PROXY[symbol])) for day in days]
    complete = all(bar is not None for bar in bars)
    if not complete:
        return {
            "sector_return_1d": None,
            "sector_return_5d": None,
            "sector_return_20d": None,
            "sector_volatility_20d": None,
            "sector_prior_coverage": sum(bar is not None for bar in bars) / len(days),
            "sector_missing": 1,
        }
    closes = [bar["c"] for bar in bars]
    returns = [current / earlier - 1 for earlier, current in zip(closes, closes[1:])]
    return {
        "sector_return_1d": returns[-1],
        "sector_return_5d": closes[-1] / closes[-6] - 1,
        "sector_return_20d": closes[-1] / closes[0] - 1,
        "sector_volatility_20d": statistics.pstdev(returns),
        "sector_prior_coverage": 1.0,
        "sector_missing": 0,
    }


def enrich_input(row: dict, daily: dict, intraday: dict, sentiments: dict) -> dict:
    from marketpulse.clock import parse_time, session_window

    session, symbol = row["session"], row["symbol"]
    window = session_window(date.fromisoformat(session))
    if parse_time(row["features"]["cutoff_utc"]) != window.cutoff:
        raise ValueError("v2 cutoff differs from saved input")
    prior = [day.isoformat() for day in _expected_prior_dates(date.fromisoformat(session))]
    # Defense in depth: raw daily bars must finish strictly before target cutoff.
    for day in prior:
        for target in (symbol, SECTOR_PROXY[symbol]):
            bar = daily.get((day, target))
            if bar is not None and parse_time(bar["t"]) + timedelta(days=1) > window.cutoff:
                raise ValueError("v2 prior daily context is not complete before cutoff")
    old = {name: row["features"]["values"][name] for name in PRICE_FEATURES}
    market = {f"company_{ticker}": int(symbol == ticker) for ticker in sorted(SECTOR_PROXY)}
    market.update(sector_values(session, symbol, daily))
    market.update(premarket_values(session, symbol, daily, intraday, prior[-1]))
    meaning = news_values(row, sentiments)
    for values in (old, market, meaning):
        if any(
            value is not None
            and (
                isinstance(value, bool)
                or not isinstance(value, (float, int))
                or not math.isfinite(value)
            )
            for value in values.values()
        ):
            raise ValueError("v2 invalid numeric feature")
    lineage = {
        "sector_pages": sorted(
            {
                daily[(day, SECTOR_PROXY[symbol])]["raw_page_hash"]
                for day in prior
                if (day, SECTOR_PROXY[symbol]) in daily
            }
        ),
        "premarket_pages": sorted(
            {bar["raw_page_hash"] for bar in intraday.get((session, symbol), [])}
        ),
        "prior_raw_close_page": daily.get((prior[-1], symbol), {}).get("raw_page_hash"),
    }
    value = {
        "schema": FEATURE_VERSION,
        "session": session,
        "symbol": symbol,
        "cutoff_utc": row["features"]["cutoff_utc"],
        "base_row_hash": row["row_hash"],
        "base_feature_hash": row["features"]["feature_hash"],
        "price": old,
        "market": market,
        "meaning": meaning,
        "lineage": lineage,
        "availability_tier": "HISTORICAL_APPROXIMATE",
        "outcomes_loaded": False,
    }
    return {**value, "feature_hash": digest(value)}


def feature_matrix(rows: list[dict], stage: str) -> tuple[list[str], list[list[float | None]]]:
    if stage not in {"existing", "market", "meaning"} or not rows:
        raise ValueError("unsupported v2 ablation")
    groups = (
        ("price",)
        if stage == "existing"
        else (("price", "market") if stage == "market" else ("price", "market", "meaning"))
    )
    names = [name for group in groups for name in rows[0]["input"][group]]
    matrix = []
    for row in rows:
        value = row["input"]
        if value["feature_hash"] != digest({k: v for k, v in value.items() if k != "feature_hash"}):
            raise ValueError("v2 feature identity mismatch")
        current = [name for group in groups for name in value[group]]
        if current != names or value["outcomes_loaded"] is not False:
            raise ValueError("v2 feature schema mismatch")
        matrix.append([value[group][name] for group in groups for name in value[group]])
    return names, matrix
