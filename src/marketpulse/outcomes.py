"""Separate after-close ledger for a precise, non-auction regular-minute proxy."""

from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from trailforge.ports import AdapterCapabilities, FunctionAdapter, VerifiedResult
from trailforge.runtime import Goal, Harness, Task

from marketpulse.clock import parse_time, session_window, utc_iso
from marketpulse.constants import SYMBOLS
from marketpulse.extraction import ExtractionPipeline
from marketpulse.storage import RawStore, digest

OUTCOME_CONTRACT = "regular-minute-proxy/1"
SOURCE = "alpaca_regular_minutes"


class MissingOutcomeBoundary(ValueError):
    """Validated response lacks one or more exact label-boundary minutes."""


def outcome_binding(session: date, feed: str, adjustment: str, data_url: str) -> dict:
    if feed not in {"iex", "sip"} or adjustment not in {"raw", "split", "all"}:
        raise ValueError("invalid outcome feed or adjustment")
    window = session_window(session)
    return {
        "contract": OUTCOME_CONTRACT, "session": session.isoformat(), "feed": feed,
        "adjustment": adjustment, "data_url": data_url, "timeframe": "1Min",
        "start": utc_iso(window.market_open),
        "end": utc_iso(window.market_close - timedelta(minutes=1)),
        "asof": session.isoformat(), "symbols": list(SYMBOLS), "limit": 10000,
        "max_pages": 4,
    }


def regular_outcomes(raw: RawStore, hashes: list[str], binding: dict) -> dict:
    """Independently validate requests, pagination, receipts and exact boundary bars."""
    if not hashes or len(set(hashes)) != len(hashes) or len(hashes) > binding["max_pages"]:
        raise ValueError("incomplete or duplicated outcome page list")
    window = session_window(date.fromisoformat(binding["session"]))
    last = window.market_close - timedelta(minutes=1)
    expected_minutes = int((window.market_close - window.market_open).total_seconds() / 60)
    found = {symbol: {} for symbol in SYMBOLS}
    expected_token = None
    for key in hashes:
        page = raw.get(key)
        params = page["params"]
        required = {
            name: binding[name] for name in
            ("feed", "adjustment", "timeframe", "start", "end", "asof", "limit")
        }
        required.update({"symbols": ",".join(SYMBOLS), "sort": "asc"})
        if (page["source"] != SOURCE or page["endpoint"] != "/v2/stocks/bars"
                or page.get("base_url") != binding["data_url"]
                or any(params.get(name) != value for name, value in required.items())
                or params.get("page_token") != expected_token):
            raise ValueError("outcome source or request mismatch")
        if parse_time(page["received_at"]) <= window.market_close:
            raise ValueError("outcome receipt is not after close")
        container = page["payload"]["bars"]
        if not isinstance(container, dict) or set(container) - set(SYMBOLS):
            raise ValueError("unexpected outcome symbols")
        for symbol, items in container.items():
            if not isinstance(items, list):
                raise ValueError("outcome bars must be a list")
            for item in items:
                timestamp = parse_time(item["t"])
                if (not window.market_open <= timestamp <= last
                        or timestamp.second or timestamp.microsecond):
                    raise ValueError("outcome bar outside regular minute grid")
                try:
                    if any(isinstance(item[name], bool) for name in ("o", "h", "l", "c", "v")):
                        raise ValueError("boolean outcome price")
                    o, h, low, c, v = (Decimal(str(item[name])) for name in
                                       ("o", "h", "l", "c", "v"))
                    if (not all(value.is_finite() for value in (o, h, low, c, v))
                            or min(o, h, low, c) <= 0 or v <= 0
                            or h < max(o, low, c) or low > min(o, h, c)):
                        raise ValueError("invalid outcome OHLCV")
                except InvalidOperation as error:
                    raise ValueError("invalid outcome number") from error
                if timestamp in found[symbol]:
                    raise ValueError("duplicate outcome minute")
                found[symbol][timestamp] = (o, c)
        expected_token = page["payload"].get("next_page_token")
        if key != hashes[-1] and not expected_token:
            raise ValueError("outcome pagination ended prematurely")
    if expected_token:
        raise ValueError("outcome pagination incomplete")
    result = {}
    for symbol, bars in found.items():
        if window.market_open not in bars or last not in bars:
            raise MissingOutcomeBoundary("missing exact opening or last regular minute")
        opening, closing = bars[window.market_open][0], bars[last][1]
        result[symbol] = {
            "open": str(opening), "close": str(closing),
            "return_fraction": str(closing / opening - Decimal(1)),
            "opening_minute_utc": utc_iso(window.market_open),
            "closing_minute_utc": utc_iso(last), "observed_minutes": len(bars),
            "expected_minutes": expected_minutes,
            "missing_interior_minutes": expected_minutes - len(bars),
        }
    return result


def validate_saved_outcome(pipeline: ExtractionPipeline, manifest: dict) -> dict:
    binding = manifest["binding"]
    key = digest(binding)
    if (binding.get("contract") != OUTCOME_CONTRACT
            or binding != outcome_binding(date.fromisoformat(binding["session"]),
                                          binding["feed"], binding["adjustment"],
                                          binding["data_url"])
            or manifest.get("job_key") != key or manifest.get("state") != "COMPLETE"):
        raise ValueError("outcome manifest identity mismatch")
    harness = Harness(pipeline.harness_path, tenant_id="local-demo",
                      resource_id=f"marketpulse:regular_outcome:{key}", adapters=[],
                      tenant_limit=100000, global_limit=1000000)
    record = harness.inspect(manifest["run_id"])
    verified = record["tasks"]["verify"]
    if (record["state"] != "COMPLETED"
            or (verified.get("result") or {}).get("verdict") != "PASS"
            or not manifest.get("trailforge_verify_receipt")
            or manifest["trailforge_verify_receipt"] != (verified.get("receipt") or {}).get(
                "receipt_id")
            or record["goal"]["tasks"][-1]["input"] != binding):
        raise ValueError("outcome lacks passing harness evidence")
    with pipeline.store.connect() as db:
        row = db.execute("SELECT * FROM session_outcomes WHERE job_key=?", (key,)).fetchone()
        pages = [dict(row) for row in db.execute(
            "SELECT digest,source,received_at,request_id FROM source_pages WHERE job_key=? "
            "ORDER BY digest", (key,))]
    if (row is None or row["outcome_hash"] != digest(manifest)
            or json.loads(row["manifest_json"]) != manifest
            or pages != sorted(manifest["pages"], key=lambda page: page["digest"])):
        raise ValueError("outcome ledger mismatch")
    for meta in manifest["pages"]:
        page = pipeline.raw.get(meta["digest"])
        if any(page.get(field) != meta[field] for field in ("source", "received_at", "request_id")):
            raise ValueError("outcome raw receipt mismatch")
    bars = regular_outcomes(pipeline.raw, [page["digest"] for page in manifest["pages"]], binding)
    if bars != manifest["symbols"]:
        raise ValueError("outcome raw values mismatch")
    return bars


def capture_regular_outcome(
    pipeline: ExtractionPipeline, session: date, *, feed: str, adjustment: str
) -> dict:
    binding = outcome_binding(session, feed, adjustment,
                              getattr(pipeline.client, "base_url", "https://data.alpaca.markets"))
    window = session_window(session)
    if pipeline.clock() <= window.market_close + timedelta(minutes=15):
        raise ValueError("regular outcomes require a session closed more than 15 minutes ago")
    key = digest(binding)
    prior = pipeline.store.get_job(key)
    if prior and prior["status"] == "COMPLETE":
        manifest = json.loads(prior["manifest_json"])
        validate_saved_outcome(pipeline, manifest)
        return manifest

    def fetch(request):
        params = {name: binding[name] for name in
                  ("feed", "adjustment", "timeframe", "start", "end", "asof", "limit")}
        params.update({"symbols": ",".join(SYMBOLS), "sort": "asc"})
        return pipeline._capture_pages(pipeline.client.pages(
            SOURCE, "/v2/stocks/bars", params, "bars", max_pages=binding["max_pages"]))

    def verify(request):
        try:
            result = request.dependencies["fetch"]
            if result["pages"] != len(result["hashes"]):
                raise ValueError("incomplete outcome pages")
            bars = regular_outcomes(pipeline.raw, result["hashes"], binding)
            return VerifiedResult("PASS", request.goal_digest, {"symbols": sorted(bars)})
        except (ValueError, KeyError, TypeError):
            return VerifiedResult("FAIL", request.goal_digest,
                                  {"reason": "regular_outcome_integrity_failed"})
        except OSError:
            return VerifiedResult("UNKNOWN", request.goal_digest, {"reason": "raw_unavailable"})

    adapters = [
        FunctionAdapter(AdapterCapabilities("marketpulse.regular_outcome_fetch/1", "TOOL",
                                            "CANDIDATE_WRITE"), fetch),
        FunctionAdapter(AdapterCapabilities("marketpulse.regular_outcome_verify/1", "VERIFY",
                                            "PURE"), verify),
    ]
    goal = Goal("local-demo", f"marketpulse:regular_outcome:{key}",
                f"Capture regular-minute proxy for {session}",
                (Task("fetch", "marketpulse.regular_outcome_fetch/1", binding),
                 Task("verify", "marketpulse.regular_outcome_verify/1", binding, ("fetch",))),
                ("verify",), allowed_effects=("PURE", "CANDIDATE_WRITE"), budget_units=4)
    harness = Harness(pipeline.harness_path, tenant_id=goal.tenant_id,
                      resource_id=goal.resource_id, adapters=adapters, lease_seconds=180,
                      tenant_limit=100000, global_limit=1000000)
    pipeline.store.reserve_job(key, session.isoformat())
    prior = pipeline.store.get_job(key)
    run_id = prior["run_id"] or harness.start(goal)
    if prior["run_id"] is None:
        pipeline.store.set_run_id(key, run_id)
    record = harness.advance(run_id, goal)
    if record["state"] != "COMPLETED":
        pipeline.store.set_status(key, record["state"])
        return {"state": record["state"], "job_key": key, "run_id": run_id}
    hashes = record["tasks"]["fetch"]["result"]["hashes"]
    pages = []
    for page_hash in hashes:
        raw_page = pipeline.raw.get(page_hash)
        pages.append({"digest": page_hash, **{field: raw_page.get(field) for field in
                                             ("source", "received_at", "request_id")}})
    manifest = {
        "state": "COMPLETE", "job_key": key, "binding": binding, "run_id": run_id,
        "pages": pages, "symbols": regular_outcomes(pipeline.raw, hashes, binding),
        "trailforge_verify_receipt": record["tasks"]["verify"]["receipt"]["receipt_id"],
        "price_convention": OUTCOME_CONTRACT, "official_auction_prices": False,
    }
    pipeline.store.commit_outcome(key, manifest, pages)
    return manifest
