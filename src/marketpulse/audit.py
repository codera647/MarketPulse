"""Evidence-first audit of the existing Trailforge-backed extraction pipeline."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

import pandas_market_calendars as mcal
from trailforge.ports import AdapterCapabilities, FunctionAdapter, VerifiedResult
from trailforge.runtime import Goal, Harness, Task

from marketpulse.clock import parse_time, session_window, utc_iso
from marketpulse.constants import STOCKS, SYMBOLS, ZONE
from marketpulse.extraction import ExtractionConfig, ExtractionPipeline
from marketpulse.storage import RawStore, digest

CASE_KINDS = {"ordinary", "earnings", "early_close", "correction", "holiday"}
REQUIRED_CATEGORIES = {"ordinary", "earnings", "early_close", "correction", "holiday"}
AUDIT_VERSION = "source-audit/2"


@dataclass(frozen=True)
class AuditCase:
    kind: str
    session: date

    @classmethod
    def parse(cls, value: str) -> AuditCase:
        try:
            kind, day = value.split(":", 1)
            result = cls(kind, date.fromisoformat(day))
        except ValueError as error:
            raise ValueError("case must look like earnings:YYYY-MM-DD") from error
        if kind not in CASE_KINDS:
            raise ValueError(f"case kind must be one of {', '.join(sorted(CASE_KINDS))}")
        return result


def validate_cases(cases: tuple[AuditCase, ...]) -> None:
    if not 1 <= len(cases) <= 12:
        raise ValueError("audit accepts 1 to 12 cases")
    if len({(case.kind, case.session) for case in cases}) != len(cases):
        raise ValueError("duplicate audit case")
    for case in cases:
        try:
            session_window(case.session)
            is_open = True
        except ValueError:
            is_open = False
        if case.kind == "holiday" and is_open:
            raise ValueError(f"{case.session} is a trading session, not a holiday")
        if case.kind != "holiday" and not is_open:
            raise ValueError(f"{case.session} is not a trading session")
    if all(case.kind == "holiday" for case in cases):
        raise ValueError("audit needs at least one trading-session case")


def _harness_evidence(
    pipeline: ExtractionPipeline, job_key: str, run_id: str, *, kind: str = "extract"
) -> dict:
    harness = Harness(
        pipeline.harness_path, tenant_id="local-demo",
        resource_id=f"marketpulse:{kind}:{job_key}", adapters=[],
        tenant_limit=100000, global_limit=1000000,
    )
    record = harness.inspect(run_id)
    return {
        "state": record["state"],
        "task_status": {
            name: {"status": task["status"], "error_code": task["error_code"]}
            for name, task in record["tasks"].items()
        },
        "verify_evidence": (record["tasks"].get("verify") or {}).get("result"),
    }


def outcome_bars_from_pages(raw: RawStore, hashes: list[str], day: date) -> dict:
    """Read audit-only daily bars; never return them to the prediction snapshot builder."""
    found: dict[str, dict] = {}
    for key in hashes:
        page = raw.get(key)
        if page["source"] != "alpaca_outcome_bars":
            raise ValueError("outcome probe source mismatch")
        container = page["payload"]["bars"]
        if not isinstance(container, dict):
            raise ValueError("outcome bars payload is not an object")
        for symbol, items in container.items():
            if symbol not in SYMBOLS or not isinstance(items, list):
                raise ValueError("outcome probe returned an unexpected symbol")
            for bar in items:
                timestamp = parse_time(bar["t"])
                if timestamp.astimezone(ZoneInfo(ZONE)).date() != day:
                    raise ValueError("outcome bar has wrong session date")
                values = [float(bar[field]) for field in ("o", "h", "l", "c", "v")]
                opening, high, low, closing, volume = values
                if (not all(math.isfinite(value) for value in values)
                        or min(opening, high, low, closing) <= 0 or volume < 0
                        or high < max(opening, closing, low)
                        or low > min(opening, closing, high)):
                    raise ValueError("invalid outcome OHLC or volume")
                if symbol in found:
                    raise ValueError("duplicate outcome bar for a symbol")
                found[symbol] = {
                    "bar_time": utc_iso(timestamp), "open": opening,
                    "close": closing, "volume": volume,
                }
    if set(found) != set(SYMBOLS):
        raise ValueError("outcome bar missing for one or more symbols")
    return found


def _probe_outcomes(
    pipeline: ExtractionPipeline, case: AuditCase, feed: str, adjustment: str
) -> dict:
    binding = {
        "contract": "outcome-source-audit/2", "session": case.session.isoformat(),
        "feed": feed, "adjustment": adjustment,
    }
    job_key = digest(binding)
    prior = pipeline.store.get_job(job_key)
    if prior and prior["status"] == "COMPLETE":
        return json.loads(prior["manifest_json"])
    local_zone = ZoneInfo(ZONE)
    start = utc_iso(datetime.combine(case.session, time.min, local_zone))
    # Alpaca's end bound is inclusive; exclude the next local day's midnight bar.
    end = utc_iso(
        datetime.combine(case.session + timedelta(days=1), time.min, local_zone)
        - timedelta(microseconds=1)
    )

    def fetch(request):
        pages = pipeline.client.pages(
            "alpaca_outcome_bars", "/v2/stocks/bars",
            {
                "symbols": ",".join(SYMBOLS), "start": request.input["start"],
                "end": request.input["end"], "timeframe": "1Day",
                "limit": 1000, "feed": feed, "adjustment": adjustment,
                "sort": "asc",
            },
            "bars", max_pages=4,
        )
        return pipeline._capture_pages(pages)

    def verify(request):
        try:
            result = request.dependencies["fetch"]
            if not result["hashes"] or result["pages"] != len(result["hashes"]):
                raise ValueError("incomplete outcome page list")
            bars = outcome_bars_from_pages(pipeline.raw, result["hashes"], case.session)
            return VerifiedResult(
                "PASS", request.goal_digest,
                {"symbols": sorted(bars), "page_count": result["pages"]},
            )
        except (KeyError, TypeError, ValueError) as error:
            return VerifiedResult("FAIL", request.goal_digest, {"reason": str(error)[:250]})
        except OSError:
            return VerifiedResult("UNKNOWN", request.goal_digest, {"reason": "raw_unavailable"})

    adapters = [
        FunctionAdapter(
            AdapterCapabilities("marketpulse.audit_outcome_fetch/1", "TOOL", "CANDIDATE_WRITE"),
            fetch,
        ),
        FunctionAdapter(
            AdapterCapabilities("marketpulse.audit_outcome_verify/1", "VERIFY", "PURE"),
            verify,
        ),
    ]
    goal = Goal(
        "local-demo", f"marketpulse:outcome_audit:{job_key}",
        f"Audit close-of-session source bars for {case.session}",
        (
            Task("fetch", "marketpulse.audit_outcome_fetch/1", {"start": start, "end": end}),
            Task("verify", "marketpulse.audit_outcome_verify/1", binding, ("fetch",)),
        ),
        ("verify",), allowed_effects=("PURE", "CANDIDATE_WRITE"), budget_units=4,
    )
    harness = Harness(
        pipeline.harness_path, tenant_id=goal.tenant_id, resource_id=goal.resource_id,
        adapters=adapters, lease_seconds=180, tenant_limit=100000, global_limit=1000000,
    )
    pipeline.store.reserve_job(job_key, case.session.isoformat())
    prior = pipeline.store.get_job(job_key)
    run_id = prior["run_id"] or harness.start(goal)
    if prior["run_id"] is None:
        pipeline.store.set_run_id(job_key, run_id)
    record = harness.advance(run_id, goal)
    if record["state"] != "COMPLETED":
        pipeline.store.set_status(job_key, record["state"])
        return {
            "state": record["state"], "job_key": job_key, "run_id": run_id,
            "trailforge": _harness_evidence(
                pipeline, job_key, run_id, kind="outcome_audit"
            ),
        }
    result = record["tasks"]["fetch"]["result"]
    bars = outcome_bars_from_pages(pipeline.raw, result["hashes"], case.session)
    page_rows = []
    for key in result["hashes"]:
        page = pipeline.raw.get(key)
        page_rows.append({
            "digest": key, "source": page["source"],
            "received_at": page["received_at"], "request_id": page.get("request_id"),
        })
    manifest = {
        "state": "COMPLETE", "job_key": job_key, "run_id": run_id,
        "session": case.session.isoformat(),
        "feed": feed, "adjustment": adjustment,
        "pages": page_rows, "symbols": bars,
        "trailforge": _harness_evidence(
            pipeline, job_key, run_id, kind="outcome_audit"
        ),
        "trailforge_verify_receipt": record["tasks"]["verify"]["receipt"]["receipt_id"],
        "note": "Audit-only outcome bars; not present in pre-open prediction snapshots.",
    }
    pipeline.store.commit_audit_pages(job_key, manifest, page_rows)
    return manifest


def _case_evidence(pipeline: ExtractionPipeline, manifest: dict, case: AuditCase) -> dict:
    key = manifest["job_key"]
    with pipeline.store.connect() as db:
        page_rows = [
            dict(row) for row in db.execute(
                "SELECT digest, source, received_at, request_id FROM source_pages "
                "WHERE job_key=? ORDER BY source, received_at, digest", (key,)
            )
        ]
        article_rows = [
            dict(row) for row in db.execute(
                "SELECT a.provider_id, a.symbols_json, a.created_at, a.updated_at, "
                "j.received_at FROM job_article_versions j "
                "JOIN article_versions a ON a.version_hash=j.version_hash "
                "WHERE j.job_key=?", (key,)
            )
        ]
        bar_rows = [
            dict(row) for row in db.execute(
                "SELECT b.symbol, b.bar_time, b.feed, b.adjustment FROM price_bars b "
                "JOIN job_price_bars j ON j.version_hash=b.version_hash "
                "WHERE j.job_key=?", (key,)
            )
        ]
        snapshot_rows = [
            dict(row) for row in db.execute(
                "SELECT symbol, news_count, snapshot_hash FROM snapshots "
                "WHERE job_key=? ORDER BY symbol", (key,)
            )
        ]
    window = session_window(case.session)
    previous_day = window.previous_close.astimezone(ZoneInfo(ZONE)).date()
    by_symbol = {}
    expected_dates = {
        day.date() for day in mcal.get_calendar("NYSE").valid_days(
            start_date=window.bars_start, end_date=previous_day
        )[-21:]
    }
    for symbol in SYMBOLS:
        dates = sorted({
            parse_time(row["bar_time"]).astimezone(ZoneInfo(ZONE)).date()
            for row in bar_rows if row["symbol"] == symbol
        })
        by_symbol[symbol] = {
            "prior_daily_bar_dates": len(dates),
            "first_bar_date": dates[0].isoformat() if dates else None,
            "latest_bar_date": dates[-1].isoformat() if dates else None,
            "previous_session_covered": bool(dates and dates[-1] == previous_day),
            "missing_last_21_sessions": sorted(
                day.isoformat() for day in expected_dates - set(dates)
            ),
            "eligible_articles": next(
                (row["news_count"] for row in snapshot_rows if row["symbol"] == symbol),
                None,
            ) if symbol in STOCKS else None,
        }
    news_pages = [row for row in page_rows if row["source"] == "alpaca_news"]
    bar_pages = [row for row in page_rows if row["source"] == "alpaca_bars"]
    raw_articles = [
        item for row in news_pages for item in pipeline.raw.get(row["digest"])["payload"]["news"]
    ]
    raw_bars = [
        item for row in bar_pages
        for items in pipeline.raw.get(row["digest"])["payload"]["bars"].values()
        for item in items
    ]
    result = {
        "provider_request_ids": {
            "news": [row["request_id"] for row in news_pages],
            "bars": [row["request_id"] for row in bar_pages],
        },
        "raw_page_digests": [row["digest"] for row in page_rows],
        "news_pages": len(news_pages),
        "bar_pages": len(bar_pages),
        "raw_news_items": len(raw_articles),
        "observed_news_fields": sorted({field for item in raw_articles for field in item}),
        "observed_bar_fields": sorted({field for item in raw_bars for field in item}),
        "observed_news_field_types": {
            field: sorted({type(item[field]).__name__ for item in raw_articles if field in item})
            for field in sorted({field for item in raw_articles for field in item})
        },
        "observed_bar_field_types": {
            field: sorted({type(item[field]).__name__ for item in raw_bars if field in item})
            for field in sorted({field for item in raw_bars for field in item})
        },
        "observed_news_sources": sorted({str(item.get("source", "")) for item in raw_articles}),
        "news_pagination_traversed": len(news_pages) > 1,
        "bars_pagination_traversed": len(bar_pages) > 1,
        "post_cutoff_revision_items": sum(
            parse_time(item["updated_at"]) > window.cutoff for item in raw_articles
        ),
        "explicit_correction_headline_candidates": sum(
            "correction" in str(item.get("headline", "")).casefold() for item in raw_articles
        ),
        "eligible_article_versions": len(article_rows),
        "raw_news_with_content": sum(bool(item.get("content")) for item in raw_articles),
        "updated_after_created_candidates": sum(
            parse_time(item["updated_at"]) > parse_time(item["created_at"])
            for item in raw_articles
        ),
        "earnings_headline_candidates": sum(
            any(word in str(item.get("headline", "")).casefold()
                for word in ("earnings", "quarterly results", "quarter results"))
            for item in raw_articles
        ),
        "symbols": by_symbol,
        "snapshot_count": len(snapshot_rows),
        "news_receipt_after_cutoff": sum(
            parse_time(row["received_at"]) > window.cutoff for row in news_pages
        ),
        "bar_feeds": sorted({row["feed"] for row in bar_rows}),
        "bar_adjustments": sorted({row["adjustment"] for row in bar_rows}),
        "regular_open_utc": utc_iso(window.market_open),
        "regular_close_utc": utc_iso(window.market_close),
    }
    return result


def _render_markdown(report: dict) -> str:
    lines = [
        "# MarketPulse source audit",
        "",
        f"Generated: {report['generated_at']}",
        f"Mode: {report['mode']}; status: **{report['status']}**.",
        f"Price feed: {report['feed']}; adjustment: {report['adjustment']}; "
        f"article content requested: {report['include_content']}.",
        "",
        "This report is about data availability and integrity, not model accuracy. "
        "Historical news retrieval does not prove the exact article version visible at 09:00 ET.",
        "",
        "## Cases",
        "",
        "| Type | Session | Result | News items | Eligible versions | "
        "Prior bars | Outcome bars | Notes |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for case in report["cases"]:
        evidence = case.get("evidence") or {}
        symbols = evidence.get("symbols") or {}
        prior_complete = sum(
            bool(item.get("previous_session_covered")) for item in symbols.values()
        )
        prior = f"{prior_complete}/7" if symbols else "n/a"
        outcome_probe = case.get("outcome_probe") or {}
        outcome_count = len(outcome_probe.get("symbols") or {})
        outcome = f"{outcome_count}/7" if outcome_probe else "n/a"
        note = case.get("note", "")
        lines.append(
            f"| {case['kind']} | {case['session']} | {case['status']} | "
            f"{evidence.get('raw_news_items', 'n/a')} | "
            f"{evidence.get('eligible_article_versions', 'n/a')} | "
            f"{prior} | {outcome} | {note.replace('|', '/')} |"
        )
    lines += ["", "## Unresolved gates", ""]
    lines += [f"- {item}" for item in report["unresolved_gates"]]
    lines += [
        "", "Per-symbol coverage, raw page digests, request IDs, and harness evidence "
        "are in the adjacent JSON report. No article body or credential is copied "
        "into this report.", "",
    ]
    return "\n".join(lines)


def write_report(report: dict, output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = report["generated_at"].replace("-", "").replace(":", "").replace("Z", "Z")
    stem = f"source-audit-{stamp}-{uuid4().hex[:8]}"
    json_path = output_dir / f"{stem}.json"
    markdown_path = output_dir / f"{stem}.md"
    with json_path.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, sort_keys=True)
    with markdown_path.open("x", encoding="utf-8") as handle:
        handle.write(_render_markdown(report))
    return json_path, markdown_path


def run_audit(
    cases: tuple[AuditCase, ...],
    *,
    pipeline: ExtractionPipeline | None,
    feed: str,
    adjustment: str,
    include_content: bool,
    output_dir: Path,
    clock=None,
    page_size: int | None = None,
) -> tuple[dict, tuple[Path, Path]]:
    validate_cases(cases)
    if feed not in {"iex", "sip"} or adjustment not in {"raw", "split", "all"}:
        raise ValueError("invalid feed or adjustment")
    if page_size is not None and not 10 <= page_size <= 50:
        raise ValueError("audit page size must be between 10 and 50")
    now = clock() if clock is not None else datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("audit clock must be timezone-aware")
    planned = pipeline is None
    if not planned:
        today_et = now.astimezone(ZoneInfo(ZONE)).date()
        if any(case.session >= today_et for case in cases if case.kind != "holiday"):
            raise ValueError("live audit requires completed past market sessions")
    report = {
        "version": AUDIT_VERSION,
        "generated_at": utc_iso(now),
        "mode": "PLAN_NO_NETWORK" if planned else "LIVE_PROVIDER",
        "status": "NOT_RUN" if planned else "IN_PROGRESS",
        "feed": feed,
        "adjustment": adjustment,
        "include_content": include_content,
        "provider_page_size_override": page_size,
        "price_convention": "PROVIDER_DAILY_NOT_CERTIFIED_REGULAR_SESSION",
        "cases": [],
        "missing_case_categories": sorted(REQUIRED_CATEGORIES - {case.kind for case in cases}),
        "unresolved_gates": [],
    }
    for case in cases:
        item = {"kind": case.kind, "session": case.session.isoformat()}
        if case.kind == "holiday":
            item.update(status="CALENDAR_CLOSED", note="calendar-only; no market extraction")
        elif planned:
            item.update(status="NOT_RUN", note="credentials/network not used")
        else:
            failure_start = len(getattr(pipeline.client, "failures", []))
            try:
                manifest = pipeline.run(
                    ExtractionConfig(
                        case.session, feed=feed, adjustment=adjustment,
                        include_content=include_content,
                        news_page_size=page_size or 50,
                        bar_page_size=page_size or 10000,
                    )
                )
                item["job_key"] = manifest["job_key"]
                item["run_id"] = manifest["run_id"]
                item["trailforge"] = _harness_evidence(
                    pipeline, manifest["job_key"], manifest["run_id"]
                )
                if manifest["state"] == "COMPLETE":
                    item["status"] = "EXTRACTED"
                    item["manifest"] = manifest
                    item["evidence"] = _case_evidence(pipeline, manifest, case)
                    outcome_probe = _probe_outcomes(pipeline, case, feed, adjustment)
                    item["outcome_probe"] = outcome_probe
                    if outcome_probe["state"] != "COMPLETE":
                        item["status"] = "OUTCOME_SOURCE_BLOCKED"
                        item["note"] = "regular-session open/close source could not be verified"
                    evidence = item["evidence"]
                    flags = []
                    if evidence["snapshot_count"] != len(STOCKS):
                        flags.append("snapshot_count_mismatch")
                    if evidence["bar_feeds"] != [feed]:
                        flags.append("bar_feed_mismatch")
                    if evidence["bar_adjustments"] != [adjustment]:
                        flags.append("bar_adjustment_mismatch")
                    if any(not row["previous_session_covered"]
                           for row in evidence["symbols"].values()):
                        flags.append("previous_session_gap")
                    if any(row["missing_last_21_sessions"]
                           for row in evidence["symbols"].values()):
                        flags.append("rolling_window_gap")
                    item["integrity_flags"] = flags
                    if flags:
                        item["status"] = "CASE_MISMATCH"
                    if case.kind == "early_close":
                        local_close = session_window(case.session).market_close.astimezone(
                            ZoneInfo(ZONE)
                        )
                        if local_close.hour >= 16:
                            item["status"] = "CASE_MISMATCH"
                            item["note"] = "calendar does not show an early close"
                    elif case.kind == "ordinary":
                        local_close = session_window(case.session).market_close.astimezone(
                            ZoneInfo(ZONE)
                        )
                        if local_close.hour < 16:
                            item["status"] = "CASE_MISMATCH"
                            item["note"] = "calendar shows an early close, not ordinary session"
                    elif case.kind == "earnings":
                        item["note"] = "headline candidates are heuristic, not event proof"
                    elif case.kind == "correction":
                        item["note"] = "updated_at > created_at is not original-version proof"
                else:
                    item["status"] = manifest["state"]
                    item["note"] = "no accepted snapshots; inspect Trailforge evidence"
            except Exception as error:
                # Do not dump provider bodies, URLs with query tokens, or credentials.
                item.update(status="ERROR", error_type=type(error).__name__,
                            note="inspect local logs/provider entitlement; no acceptance")
            item["provider_failures"] = getattr(pipeline.client, "failures", [])[failure_start:]
        report["cases"].append(item)
    if not planned:
        report["status"] = (
            "TECHNICAL_REVIEW_REQUIRED"
            if all(item["status"] in {"EXTRACTED", "CALENDAR_CLOSED"}
                   for item in report["cases"])
            else "BLOCKED"
        )
    gates = [
        "Verify provider account entitlements, terms, raw-payload retention, "
        "and redistribution rights manually.",
        "Historical article retrieval cannot certify original receipt time "
        "or earlier text revisions.",
        "Confirm earnings/correction case labels against independent source "
        "evidence; counters are only leads.",
        "Compare IEX and SIP only if both are entitled; do not mix feeds in one training dataset.",
        "A present 1Day bar does not establish an official regular-session opening "
        "or closing fill; validate the target convention separately.",
    ]
    if planned:
        gates.insert(
            0, "No provider request was made. Configure local Alpaca credentials "
            "and rerun live."
        )
    if not include_content:
        gates.append(
            "Article body availability was not tested because include_content was disabled."
        )
    if report["missing_case_categories"]:
        missing = ", ".join(report["missing_case_categories"])
        gates.append(f"Add representative cases for: {missing}")
    report["unresolved_gates"] = gates
    return report, write_report(report, output_dir)
