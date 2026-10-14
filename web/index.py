"""Small read-only dashboard. All deployment URLs must use Vercel Authentication."""
from __future__ import annotations

import logging
import os
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import psycopg
from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.responses import FileResponse

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
ROOT = Path(__file__).resolve().parent / "static"
HOST = "ep-lively-wind-b70bl7t0-pooler.c-13.us-east-1.aws.neon.tech"
logger = logging.getLogger("marketpulse.dashboard")


@app.middleware("http")
async def private_headers(request, call_next):
    response = await call_next(request)
    response.headers.update({
        "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer", "X-Frame-Options": "DENY",
        "Content-Security-Policy": "default-src 'self'; script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
        "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
    })
    return response


def connection():
    value = os.environ.get("MARKETPULSE_DASHBOARD_DATABASE_URL", "")
    parsed = urlsplit(value)
    if (parsed.scheme != "postgresql" or parsed.hostname != HOST
            or parsed.username != "marketpulse_reader" or not parsed.password
            or parsed.path != "/marketpulse" or parsed.fragment
            or parsed.port not in {None, 5432}
            or parse_qs(parsed.query).get("sslmode") != ["require"]):
        raise ValueError("restricted dashboard target not configured")
    return psycopg.connect(value, connect_timeout=10, autocommit=True)


def read_dashboard(period):
    with connection() as db:
        if db.execute("SELECT current_user").fetchone() != ("marketpulse_reader",):
            raise ValueError("dashboard role mismatch")
        if db.execute("SHOW default_transaction_read_only").fetchone() != ("on",):
            raise ValueError("dashboard role is not read-only")
        research = db.execute(
            "SELECT payload FROM marketpulse.dashboard_research "
            "WHERE payload->>'period'=%s ORDER BY created_at DESC LIMIT 1", (period,)
        ).fetchone()
        forward = db.execute("SELECT payload FROM marketpulse.dashboard_forward "
                             "ORDER BY created_at DESC LIMIT 1").fetchone()
        jobs = db.execute("SELECT kind,status,updated_at FROM marketpulse.dashboard_jobs "
                          "ORDER BY updated_at DESC LIMIT 20").fetchall()
    return {"research": research[0] if research else None,
            "forward": forward[0] if forward else None,
            "jobs": [{"kind": kind, "status": status, "updated_at": updated.isoformat()}
                     for kind, status, updated in jobs],
            "paper_action_authorized": False, "model_auto_promotion_enabled": False}


@app.get("/api/health")
def health():
    return {"status": "OK", "service": "marketpulse-read-only-dashboard", "version": 1}


@app.get("/api/dashboard")
def dashboard(period: str = Query("2026 retrospective", max_length=24)):
    if period not in {"2026 retrospective", "2025 development"}:
        raise HTTPException(400, "Choose a published research period.")
    try:
        return read_dashboard(period)
    except Exception as error:
        # Driver messages can contain passwords/SQL. Log type only, never exception repr/traceback.
        logger.error("dashboard_read_failed type=%s", type(error).__name__)
        raise HTTPException(503, "Research data is temporarily unavailable.") from None


@app.get("/")
def home():
    return FileResponse(ROOT / "index.html")


@app.get("/assets/{name}")
def asset(name: str):
    if name not in {"app.js", "app.css"}:
        return Response(status_code=404)
    return FileResponse(ROOT / name)
