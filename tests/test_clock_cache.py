from datetime import date, timedelta

import pytest

from marketpulse.clock import exchange_calendar, session_window


@pytest.mark.parametrize("value", ["2018-01-02", "2018-07-03", "2018-12-06", "2020-03-09",
                                   "2024-11-29", "2025-06-20", "2026-09-08", "2026-10-05"])
def test_annual_cache_preserves_original_schedule_boundaries(value):
    day = date.fromisoformat(value)
    reference = exchange_calendar().schedule(start_date=day - timedelta(days=45), end_date=day)
    actual = session_window(day)
    assert actual.market_open == reference.iloc[-1]["market_open"].to_pydatetime()
    assert actual.market_close == reference.iloc[-1]["market_close"].to_pydatetime()
    assert actual.previous_close == reference.iloc[-2]["market_close"].to_pydatetime()


def test_unusual_exchange_closure_remains_a_non_session():
    with pytest.raises(ValueError, match="NYSE"):
        session_window(date(2018, 12, 5))
