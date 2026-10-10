from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from functools import lru_cache
from zoneinfo import ZoneInfo

import pandas_market_calendars as mcal

from marketpulse.constants import ZONE


def utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("naive datetime is not permitted")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("provider timestamp has no timezone")
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True)
class SessionWindow:
    session: date
    previous_close: datetime
    cutoff: datetime
    market_open: datetime
    market_close: datetime
    bars_start: datetime
    bars_end: datetime


@lru_cache(maxsize=2048)
def session_window(session: date) -> SessionWindow:
    calendar = mcal.get_calendar("NYSE")
    schedule = calendar.schedule(start_date=session - timedelta(days=45), end_date=session)
    today = schedule[schedule.index.date == session]
    earlier = schedule[schedule.index.date < session]
    if today.empty or earlier.empty:
        raise ValueError(f"{session} is not a supported NYSE session")
    opening = today.iloc[0]["market_open"].to_pydatetime()
    closing = today.iloc[0]["market_close"].to_pydatetime()
    previous_close = earlier.iloc[-1]["market_close"].to_pydatetime()
    cutoff = datetime.combine(session, time(9, 0), ZoneInfo(ZONE)).astimezone(timezone.utc)
    if not previous_close < cutoff < opening < closing:
        raise ValueError("invalid exchange schedule or cutoff")
    # The entire preceding 45-day window is eligible, never today's daily bar.
    bars_start = datetime.combine(session - timedelta(days=45), time.min, ZoneInfo(ZONE))
    bars_end = datetime.combine(session, time.min, ZoneInfo(ZONE)) - timedelta(seconds=1)
    return SessionWindow(session, previous_close, cutoff, opening, closing, bars_start, bars_end)
