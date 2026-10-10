"""Read-only, provisional labels from separately captured after-close bars."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from marketpulse.audit import outcome_bars_from_pages
from marketpulse.clock import parse_time, session_window, utc_iso
from marketpulse.constants import STOCKS
from marketpulse.storage import RawStore, digest

LABEL_CONTRACT = "provisional-daily-bar-label/1"


def _threshold(value: str) -> Decimal:
    try:
        threshold = Decimal(value)
    except (InvalidOperation, ValueError) as error:
        raise ValueError("threshold must be a positive finite decimal") from error
    if not threshold.is_finite() or threshold <= 0 or threshold >= 1:
        raise ValueError("threshold must be a positive finite decimal below 1")
    return threshold.normalize()


def classify_return(movement: Decimal, threshold: Decimal) -> str:
    """Equality at either material-move boundary belongs to the middle class."""
    if not movement.is_finite() or not threshold.is_finite() or threshold <= 0:
        raise ValueError("return and threshold must be finite, with positive threshold")
    if movement > threshold:
        return "UP"
    if movement < -threshold:
        return "DOWN"
    return "NO_MATERIAL_MOVE"


def _manifest(row: sqlite3.Row | None, kind: str) -> dict:
    if row is None or row["status"] != "COMPLETE" or not row["manifest_json"]:
        raise ValueError(f"{kind} job is missing or incomplete")
    manifest = json.loads(row["manifest_json"])
    if manifest.get("state") != "COMPLETE" or manifest.get("job_key") != row["job_key"]:
        raise ValueError(f"{kind} manifest disagrees with job")
    return manifest


def preview_label(
    data_dir: Path, snapshot_hash: str, outcome_job_key: str, threshold: str
) -> dict:
    """Calculate, but never persist, a label under an explicitly provisional convention."""
    theta = _threshold(threshold)
    if len(snapshot_hash) != 64 or len(outcome_job_key) != 64:
        raise ValueError("snapshot and outcome IDs must be full SHA-256 hashes")
    database_path = data_dir / "marketpulse.sqlite3"
    if not database_path.is_file():
        raise ValueError("application database does not exist")
    with closing(sqlite3.connect(f"{database_path.as_uri()}?mode=ro", uri=True)) as db:
        db.row_factory = sqlite3.Row
        snapshot = db.execute(
            "SELECT * FROM snapshots WHERE snapshot_hash=?", (snapshot_hash,)
        ).fetchone()
        if snapshot is None:
            raise ValueError("snapshot does not exist")
        if snapshot["symbol"] not in STOCKS:
            raise ValueError("SPY is a benchmark, not a prediction target")
        source_row = db.execute(
            "SELECT * FROM extraction_jobs WHERE job_key=?", (snapshot["job_key"],)
        ).fetchone()
        outcome_row = db.execute(
            "SELECT * FROM extraction_jobs WHERE job_key=?", (outcome_job_key,)
        ).fetchone()
        source = _manifest(source_row, "source")
        outcome = _manifest(outcome_row, "outcome")
        page_rows = db.execute(
            "SELECT digest, received_at FROM source_pages WHERE job_key=? "
            "ORDER BY digest", (outcome_job_key,)
        ).fetchall()

    session = date.fromisoformat(snapshot["session"])
    window = session_window(session)
    if (source.get("session") != snapshot["session"]
            or outcome.get("session") != snapshot["session"]
            or source.get("snapshots", {}).get(snapshot["symbol"]) != snapshot_hash):
        raise ValueError("source, snapshot, and outcome session or identity mismatch")
    if source.get("feed") != outcome.get("feed") or source.get("adjustment") != outcome.get(
        "adjustment"
    ):
        raise ValueError("source and outcome price conventions differ")
    if snapshot["cutoff_utc"] != utc_iso(window.cutoff):
        raise ValueError("snapshot cutoff is not the agreed 09:00 ET cutoff")
    snapshot_content = {
        "job_key": snapshot["job_key"], "session": snapshot["session"],
        "symbol": snapshot["symbol"], "cutoff_utc": snapshot["cutoff_utc"],
        "availability_tier": snapshot["availability_tier"],
        "fresh_for_0900": bool(snapshot["fresh_for_0900"]),
        "article_hashes": json.loads(snapshot["article_hashes_json"]),
        "bar_hashes": json.loads(snapshot["bar_hashes_json"]),
        "spy_bar_hashes": json.loads(snapshot["spy_bar_hashes_json"]),
        "news_count": snapshot["news_count"],
    }
    if digest(snapshot_content) != snapshot_hash:
        raise ValueError("snapshot identity check failed")
    evidence = outcome.get("trailforge") or {}
    if (evidence.get("state") != "COMPLETED"
            or (evidence.get("verify_evidence") or {}).get("verdict") != "PASS"
            or not outcome.get("trailforge_verify_receipt")):
        raise ValueError("outcome has no passing Trailforge verification")
    manifest_pages = outcome.get("pages") or []
    page_digests = [page["digest"] for page in manifest_pages]
    if (not page_digests or len(set(page_digests)) != len(page_digests)
            or sorted(page_digests) != [row["digest"] for row in page_rows]):
        raise ValueError("outcome page manifest does not match the source ledger")
    if any(parse_time(row["received_at"]) <= window.market_close for row in page_rows):
        raise ValueError("outcome capture was not observed after the session close")
    raw = RawStore(data_dir / "raw")
    ledger_times = {row["digest"]: row["received_at"] for row in page_rows}
    for page_meta in manifest_pages:
        raw_page = raw.get(page_meta["digest"])
        params = raw_page.get("params") or {}
        if (raw_page.get("source") != "alpaca_outcome_bars"
                or raw_page.get("received_at") != page_meta["received_at"]
                or raw_page.get("received_at") != ledger_times[page_meta["digest"]]
                or raw_page.get("request_id") != page_meta["request_id"]
                or params.get("feed") != outcome["feed"]
                or params.get("adjustment") != outcome["adjustment"]
                or params.get("timeframe") != "1Day"):
            raise ValueError("raw outcome page disagrees with provider request or receipt")
    bars = outcome_bars_from_pages(raw, page_digests, session)
    if bars != outcome.get("symbols"):
        raise ValueError("outcome manifest disagrees with immutable raw pages")
    bar = bars[snapshot["symbol"]]
    opening_price = Decimal(str(bar["open"]))
    closing_price = Decimal(str(bar["close"]))
    movement = closing_price / opening_price - Decimal(1)
    label = classify_return(movement, theta)
    content = {
        "contract": LABEL_CONTRACT,
        "snapshot_hash": snapshot_hash,
        "outcome_job_key": outcome_job_key,
        "threshold": str(theta),
        "label": label,
        "return_fraction": str(movement),
    }
    return {
        **content,
        "preview_hash": digest(content),
        "session": session.isoformat(),
        "symbol": snapshot["symbol"],
        "feed": source["feed"],
        "adjustment": source["adjustment"],
        "open": str(opening_price),
        "close": str(closing_price),
        "outcome_bar_time_utc": bar["bar_time"],
        "market_close_utc": utc_iso(window.market_close),
        "outcome_page_digests": page_digests,
        "trailforge_verify_receipt": outcome["trailforge_verify_receipt"],
        "availability_tier": snapshot["availability_tier"],
        "status": "PROVISIONAL_DAILY_BAR_CONVENTION",
        "ready_for_training": False,
        "note": (
            "Daily-bar open/close has not been certified as the intended "
            "regular-session target."
        ),
    }
