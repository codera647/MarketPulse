"""Bounded monthly SIP captures for prior-sector and before-cutoff market inputs."""

from __future__ import annotations

import json
import math
from dataclasses import asdict
from datetime import date, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from marketpulse.clock import parse_time
from marketpulse.constants import STOCKS
from marketpulse.storage import ExtractionStore, RawStore, canonical_bytes, digest
from marketpulse.v2_runtime import check_receipt, environment, supervised

SECTOR_PROXY = {
    "AAPL": "XLK",
    "NVDA": "XLK",
    "AMZN": "XLY",
    "JPM": "XLF",
    "XOM": "XLE",
    "WMT": "XLP",
}


def _reconciliation_table(root: Path):
    store = ExtractionStore(root / "v2-jobs.sqlite3")
    with store.connect() as db:
        db.execute(
            "CREATE TABLE IF NOT EXISTS v2_capture_reconciliations ("
            "parent_job_key TEXT PRIMARY KEY, result_json TEXT NOT NULL)"
        )
    return store


def reconcile_capture(root: Path, parent_key: str, capture_hash: str, *, evidence: str) -> dict:
    """Explicit host reconciliation of a COMPLETE capture, not a retry/reset of UNKNOWN."""
    from trailforge.runtime import Harness

    if not isinstance(evidence, str) or not 1 <= len(evidence.strip()) <= 500:
        raise ValueError("bounded independent source reconciliation evidence required")
    index, artifacts = _reconciliation_table(root), RawStore(root / "artifacts")
    job = index.get_job(parent_key)
    if not job or not job["run_id"]:
        raise ValueError("original source task missing")
    old = Harness(
        root / "v2-trailforge.sqlite3",
        tenant_id="local-demo",
        resource_id=f"marketpulse:v2:{parent_key}",
        adapters=[],
        tenant_limit=1000000,
        global_limit=10000000,
    ).inspect(job["run_id"])
    input_value = old["goal"]["tasks"][0]["input"]
    if (
        old["goal"]["tasks"][0]["adapter_id"] != "marketpulse.v2_context/2"
        or input_value.get("environment") != environment()
    ):
        raise ValueError("only matching-version context captures can be reconciled")
    query = {k: v for k, v in input_value.items() if k != "environment"}

    def no_execution():
        raise ValueError("reconciliation must never repeat the original source effect")

    # Let the native protocol retain an EXPIRED_ATTEMPT as UNKNOWN. Never resolve_unknown(RETRY).
    try:
        supervised(root, "context", query, no_execution, lambda result: None)
    except ValueError:
        pass

    def check_parent():
        record = Harness(
            root / "v2-trailforge.sqlite3",
            tenant_id="local-demo",
            resource_id=f"marketpulse:v2:{parent_key}",
            adapters=[],
            tenant_limit=1000000,
            global_limit=10000000,
        ).inspect(job["run_id"])
        if (
            record["state"] != "WAITING_HUMAN"
            or record["active"] is not None
            or record["tasks"]["execute"]["status"] != "UNKNOWN"
            or record["tasks"]["execute"]["error_code"] != "EXPIRED_ATTEMPT"
        ):
            raise ValueError("original source is not a retained expired UNKNOWN")

    def verify_saved(result):
        check_parent()
        if result["capture_hash"] != capture_hash:
            raise ValueError("reconciled capture identity mismatch")
        saved = artifacts.get(capture_hash)
        if saved["query"] != query or saved["records"] != len(
            validate_pages(RawStore(root / "raw-context"), query, saved["pages"])
        ):
            raise ValueError("candidate capture is incomplete or disagrees with source pages")

    check_parent()
    verify_saved({"capture_hash": capture_hash})
    binding = {
        "query": query,
        "parent_job_key": parent_key,
        "parent_run_id": job["run_id"],
        "capture_hash": capture_hash,
        "evidence": evidence,
        "original_authority_reset": False,
        "source_refetched": False,
    }
    result = supervised(
        root,
        "context_reconciliation",
        binding,
        lambda: {
            "capture_hash": capture_hash,
            "original_held_run": job["run_id"],
            "source_refetched": False,
        },
        verify_saved,
    )
    with index.connect() as db:
        prior = db.execute(
            "SELECT result_json FROM v2_capture_reconciliations WHERE parent_job_key=?",
            (parent_key,),
        ).fetchone()
        if prior and json.loads(prior[0]) != result:
            raise ValueError("source reconciliation already bound to different evidence")
        db.execute(
            "INSERT OR IGNORE INTO v2_capture_reconciliations VALUES (?,?)",
            (parent_key, canonical_bytes(result).decode()),
        )
    return result


def reconciled_context(root: Path, query: dict) -> dict | None:
    parent_key = digest({"stage": "context", "binding": {**query, "environment": environment()}})
    with _reconciliation_table(root).connect() as db:
        row = db.execute(
            "SELECT result_json FROM v2_capture_reconciliations WHERE parent_job_key=?",
            (parent_key,),
        ).fetchone()
    if row is None:
        return None
    result = json.loads(row[0])
    check_receipt(root, result)
    saved = RawStore(root / "artifacts").get(result["capture_hash"])
    if saved["query"] != query:
        raise ValueError("source reconciliation query mismatch")
    return result


def month_queries(first: date, last: date) -> list[dict]:
    if last < first or (last - first).days > 3653:
        raise ValueError("v2 captures require a bounded <=10-year range")
    current = (first - timedelta(days=45)).replace(day=1)
    queries = []
    while current <= last:
        following = (current.replace(day=28) + timedelta(days=4)).replace(day=1)
        for timeframe, symbols in (
            ("1Day", sorted(set(STOCKS) | set(SECTOR_PROXY.values()))),
            ("30Min", sorted(STOCKS)),
        ):
            if timeframe == "30Min" and following <= first:
                continue
            queries.append(
                {
                    "symbols": ",".join(symbols),
                    "timeframe": timeframe,
                    "start": current.isoformat() + "T00:00:00Z",
                    "end": following.isoformat() + "T00:00:00Z",
                    "feed": "sip",
                    "adjustment": "raw",
                    "sort": "asc",
                    "limit": 10000,
                }
            )
        current = following
    return queries


def validate_pages(store: RawStore, query: dict, hashes: list[str]) -> list[dict]:
    if not hashes or len(hashes) > 12:
        raise ValueError("v2 page bounds exceeded")
    records, seen, token = [], set(), None
    start, end = parse_time(query["start"]), parse_time(query["end"])
    for key in hashes:
        page = store.get(key)
        expected = {**query, **({"page_token": token} if token else {})}
        if (
            page["params"] != expected
            or page["endpoint"] != "/v2/stocks/bars"
            or page["base_url"] != "https://data.alpaca.markets"
            or page["source"] != "v2_market_context"
            or not parse_time(page["received_at"])
        ):
            raise ValueError("v2 captured query provenance mismatch")
        payload = page["payload"]
        if not isinstance(payload.get("bars"), dict):
            raise ValueError("v2 malformed bars")
        for symbol, bars in payload["bars"].items():
            if symbol not in query["symbols"].split(",") or not isinstance(bars, list):
                raise ValueError("v2 bar symbol/scope mismatch")
            for bar in bars:
                stamp = parse_time(bar["t"])
                if not start <= stamp <= end or (symbol, bar["t"]) in seen:
                    raise ValueError("v2 out-of-scope or duplicated bar")
                seen.add((symbol, bar["t"]))
                if any(
                    isinstance(bar[field], bool)
                    or not isinstance(bar[field], (int, float))
                    or not math.isfinite(bar[field])
                    or bar[field] <= 0
                    for field in ("o", "h", "l", "c")
                ):
                    raise ValueError("v2 nonfinite/invalid prices")
                if (
                    not isinstance(bar["v"], (int, float))
                    or isinstance(bar["v"], bool)
                    or not math.isfinite(bar["v"])
                    or bar["v"] < 0
                    or bar["h"] < max(bar["o"], bar["c"], bar["l"])
                    or bar["l"] > min(bar["o"], bar["c"], bar["h"])
                ):
                    raise ValueError("v2 invalid volume or OHLC")
                records.append({"symbol": symbol, **bar, "raw_page_hash": key})
        next_token = payload.get("next_page_token")
        if next_token is not None and (not isinstance(next_token, str) or not next_token):
            raise ValueError("v2 invalid pagination token")
        token = next_token
    if token:
        raise ValueError("v2 incomplete pagination")
    return records


def capture_context(root: Path, client, first: date, last: date, checkpoint) -> dict:
    raw, artifacts = RawStore(root / "raw-context"), RawStore(root / "artifacts")
    queries = month_queries(first, last)
    results = []
    for i, query in enumerate(queries):
        checkpoint(
            {
                "stage": "COLLECTING_CONTEXT",
                "queries_complete": i,
                "queries_total": len(queries),
                "timeframe": query["timeframe"],
                "month": query["start"][:7],
            }
        )

        def execute():
            pages = client.pages(
                "v2_market_context", "/v2/stocks/bars", query, "bars", max_pages=12
            )
            hashes = [raw.put(asdict(page)) for page in pages]
            count = len(validate_pages(raw, query, hashes))
            return {
                "capture_hash": artifacts.put({"query": query, "pages": hashes, "records": count})
            }

        def verify(result):
            saved = artifacts.get(result["capture_hash"])
            if saved["query"] != query or saved["records"] != len(
                validate_pages(raw, query, saved["pages"])
            ):
                raise ValueError("v2 source replay differs")

        results.append(
            reconciled_context(root, query) or supervised(root, "context", query, execute, verify)
        )
    return {
        "manifest_hash": artifacts.put({"captures": results, "feed": "sip", "adjustment": "raw"}),
        "queries": len(queries),
    }


def load_context(root: Path, manifest_hash: str) -> tuple[dict, dict]:
    artifacts, raw = RawStore(root / "artifacts"), RawStore(root / "raw-context")
    daily, intraday = {}, {}
    for result in artifacts.get(manifest_hash)["captures"]:
        check_receipt(root, result)
        capture = artifacts.get(result["capture_hash"])
        query = capture["query"]
        bars = validate_pages(raw, query, capture["pages"])
        if len(bars) != capture["records"]:
            raise ValueError("v2 changed capture count")
        for bar in bars:
            local = parse_time(bar["t"]).astimezone(ZoneInfo("America/New_York"))
            key = (local.date().isoformat(), bar["symbol"])
            if query["timeframe"] == "1Day":
                if key in daily and daily[key] != bar:
                    raise ValueError("v2 ambiguous daily context")
                daily[key] = bar
            else:
                # Store only same-day intervals capable of ending before 09:00.
                if 4 <= local.hour < 9:
                    intraday.setdefault(key, []).append(bar)
    for key in intraday:
        intraday[key].sort(key=lambda bar: bar["t"])
        if len({bar["t"] for bar in intraday[key]}) != len(intraday[key]):
            raise ValueError("v2 duplicated context interval")
    return daily, intraday


def premarket_values(
    session: str, symbol: str, daily: dict, intraday: dict, previous_session: str
) -> dict:
    from marketpulse.clock import session_window

    cutoff = session_window(date.fromisoformat(session)).cutoff
    bars = intraday.get((session, symbol), [])
    starts = []
    for bar in bars:
        stamp = parse_time(bar["t"])
        local = stamp.astimezone(ZoneInfo("America/New_York"))
        if (
            local.date().isoformat() != session
            or local.hour < 4
            or stamp + timedelta(minutes=30) > cutoff
        ):
            raise ValueError("v2 pre-market bar crosses cutoff or local-date boundary")
        starts.append(stamp)
    if len(set(starts)) != len(starts):
        raise ValueError("v2 duplicated pre-market bar")
    ordered = sorted(bars, key=lambda bar: bar["t"])
    previous = daily.get((previous_session, symbol))
    latest = parse_time(ordered[-1]["t"]) + timedelta(minutes=30) if ordered else None
    return {
        "premarket_return": (
            ordered[-1]["c"] / previous["c"] - 1 if ordered and previous else None
        ),
        "premarket_observed_volume": sum(bar["v"] for bar in ordered) if ordered else None,
        "premarket_bar_count": len(ordered),
        "premarket_interval_coverage": len(ordered) / 10,
        "premarket_last_age_minutes": (cutoff - latest).total_seconds() / 60 if latest else None,
        "premarket_missing": int(not ordered),
        "premarket_prior_close_missing": int(previous is None),
    }
