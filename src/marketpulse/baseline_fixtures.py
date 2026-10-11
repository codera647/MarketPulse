"""Synthetic software examples, never evidence about financial prediction."""

from __future__ import annotations

import json
import random
from datetime import date, datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo

from marketpulse.clock import session_window, utc_iso
from marketpulse.constants import STOCKS, SYMBOLS, ZONE
from marketpulse.dataset import market_sessions
from marketpulse.features import build_features
from marketpulse.labels import classify_return
from marketpulse.storage import RawStore, digest

FIXTURE_VERSION = "baseline-fixtures/1"


def generate_fixture_catalog(store: RawStore, *, seed: int = 42, with_news: bool = False) -> str:
    """Persist a small synthetic catalog; external datasets are not accepted here."""
    if type(seed) is not int or not 0 <= seed <= 2147483647:
        raise ValueError("fixture seed must be a bounded nonnegative integer")
    if type(with_news) is not bool:
        raise ValueError("news fixture flag must be a boolean")
    rng = random.Random(seed)
    bounds = {
        "train": (date(2024, 7, 1), date(2024, 7, 19)),
        "validation": (date(2024, 7, 22), date(2024, 7, 26)),
        "test": (date(2024, 7, 29), date(2024, 8, 2)),
    }
    history_days = market_sessions(date(2024, 5, 1), date(2024, 8, 2))
    history = {}
    for symbol_index, symbol in enumerate(SYMBOLS):
        drift = (-0.003, 0.0001, 0.003)[symbol_index % 3] if symbol != "SPY" else 0.0002
        history[symbol] = [
            {"symbol": symbol, "feed": "sip", "adjustment": "split",
             "bar_time": utc_iso(datetime.combine(day, time.min, ZoneInfo(ZONE))),
             "close": (100 + symbol_index * 10) * (1 + drift) ** index
             * (1 + rng.uniform(-0.0002, 0.0002)),
             "volume": 100000 + rng.randrange(20000)}
            for index, day in enumerate(history_days)
        ]
    entries = []
    for split, (start, end) in bounds.items():
        days = market_sessions(start, end)
        if split != "train":
            days = days[1:]  # Same date-grouped boundary-embargo idea, synthetic dates only.
        for day in days:
            window = session_window(day)
            for index, symbol in enumerate(STOCKS):
                prior = [item for item, bar_day in zip(history[symbol], history_days)
                         if bar_day < day][-21:]
                spy = [item for item, bar_day in zip(history["SPY"], history_days)
                       if bar_day < day][-21:]
                identity = {"fixture": FIXTURE_VERSION, "seed": seed,
                            "symbol": symbol, "session": day.isoformat()}
                articles = []
                if with_news:
                    identity["news_fixture"] = "manufactured-news/1"
                    headline = ("Company warns of weaker demand and earnings",
                                "Company announces a routine business update",
                                "Company raises growth outlook and earnings")[index % 3]
                    article_time = utc_iso(window.cutoff.replace(hour=window.cutoff.hour - 1))
                    articles = [{"headline": headline, "summary": "Synthetic example only",
                                 "created_at": article_time, "updated_at": article_time,
                                 "job_received_at": article_time,
                                 "symbols_json": json.dumps([symbol]),
                                 "version_hash": digest({**identity, "headline": headline})}]
                snapshot_hash = digest(identity)
                snapshot = {
                    "snapshot_hash": snapshot_hash, "symbol": symbol,
                    "session": day.isoformat(), "cutoff_utc": utc_iso(window.cutoff),
                    "availability_tier": "FIXTURE", "news_count": len(articles),
                    "fresh_for_0900": False, "article_hashes_json": json.dumps(
                        [article["version_hash"] for article in articles]),
                }
                source = {"session": day.isoformat(), "tier": "FIXTURE",
                          "feed": "sip", "adjustment": "split"}
                features = build_features(snapshot, source, prior, spy, articles)
                # Intentionally manufactured relation: it tests the learner, not markets.
                movement = (Decimal("-0.02"), Decimal("0.005"), Decimal("0.02"))[index % 3]
                if with_news and split == "test" and day == days[-1] and index == 0:
                    # Explicit manufactured held-out shock for a visible forecast miss.
                    movement = Decimal("0.02")
                row = {
                    "schema": FIXTURE_VERSION, "split": split, "symbol": symbol,
                    "session": day.isoformat(), "availability_tier": "FIXTURE",
                    "features": features, "return_fraction": str(movement),
                    "threshold": "0.01", "label": classify_return(movement, Decimal("0.01")),
                }
                if with_news:
                    row["news"] = [{"headline": item["headline"], "summary": item["summary"],
                                    "created_at": item["created_at"],
                                    "updated_at": item["updated_at"],
                                    "version_hash": item["version_hash"]} for item in articles]
                entries.append({"row_hash": store.put(row), "split": split,
                                "session": day.isoformat(), "symbol": symbol})
    return store.put({"schema": FIXTURE_VERSION, "availability_tier": "FIXTURE",
                      "seed": seed, "rows": entries,
                      "notice": "Manufactured data; no financial predictive evidence"})
