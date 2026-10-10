from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timedelta, timezone

import pytest

from marketpulse.alpaca import CapturedPage
from marketpulse.clock import session_window, utc_iso
from marketpulse.constants import SYMBOLS
from marketpulse.extraction import ExtractionPipeline
from marketpulse.outcomes import (
    SOURCE,
    capture_regular_outcome,
    outcome_binding,
    regular_outcomes,
)
from marketpulse.storage import RawStore

DAY = date(2025, 11, 28)
NOW = datetime(2026, 10, 10, tzinfo=timezone.utc)


def envelope(day=DAY):
    binding = outcome_binding(day, "sip", "split", "https://data.alpaca.markets")
    params = {key: binding[key] for key in
              ("feed", "adjustment", "timeframe", "start", "end", "asof", "limit")}
    params.update({"symbols": ",".join(SYMBOLS), "sort": "asc"})
    return binding, {
        "source": SOURCE, "endpoint": "/v2/stocks/bars", "params": params,
        "base_url": binding["data_url"], "received_at": utc_iso(NOW), "request_id": "fixture",
        "payload": {"bars": {symbol: [
            {"t": binding["start"], "o": 100, "h": 103, "l": 99, "c": 102, "v": 100},
            {"t": binding["end"], "o": 102, "h": 103, "l": 99, "c": 101, "v": 100},
        ] for symbol in SYMBOLS}, "next_page_token": None},
    }


def test_exact_early_close_and_decimal_proxy(tmp_path):
    binding, page = envelope()
    raw = RawStore(tmp_path)
    result = regular_outcomes(raw, [raw.put(page)], binding)
    assert result["AAPL"]["return_fraction"] == "0.01"
    assert result["AAPL"]["expected_minutes"] == 210
    assert result["AAPL"]["missing_interior_minutes"] == 208
    assert result["AAPL"]["closing_minute_utc"] == "2025-11-28T17:59:00Z"


@pytest.mark.parametrize("fault", ["boundary", "after_hours", "duplicate", "nan", "boolean",
                                  "pagination", "receipt", "feed", "timeframe", "asof",
                                  "host", "symbol", "grid", "price"])
def test_invalid_regular_outcomes_are_rejected(tmp_path, fault):
    binding, page = envelope()
    bars = page["payload"]["bars"]["AAPL"]
    if fault == "boundary":
        bars.pop()
    elif fault == "after_hours":
        bars[-1]["t"] = utc_iso(session_window(DAY).market_close)
    elif fault == "duplicate":
        bars.append(deepcopy(bars[0]))
    elif fault == "nan":
        bars[0]["o"] = "NaN"
    elif fault == "boolean":
        bars[0]["v"] = True
    elif fault == "pagination":
        page["payload"]["next_page_token"] = "more"
    elif fault == "receipt":
        page["received_at"] = utc_iso(session_window(DAY).market_close)
    elif fault in {"feed", "timeframe", "asof"}:
        page["params"][fault] = "wrong"
    elif fault == "host":
        page["base_url"] = "https://example.com"
    elif fault == "symbol":
        page["payload"]["bars"]["OTHER"] = bars
    elif fault == "grid":
        bars[0]["t"] = utc_iso(session_window(DAY).market_open + timedelta(seconds=1))
    elif fault == "price":
        bars[0]["h"] = 90
    raw = RawStore(tmp_path)
    with pytest.raises(ValueError):
        regular_outcomes(raw, [raw.put(page)], binding)


def test_pagination_receipts_link_in_order(tmp_path):
    binding, first = envelope()
    second = deepcopy(first)
    first["payload"]["bars"] = {key: value[:1] for key, value in first["payload"]["bars"].items()}
    first["payload"]["next_page_token"] = "second"
    second["params"]["page_token"] = "second"
    second["payload"]["bars"] = {key: value[1:] for key, value in
                                  second["payload"]["bars"].items()}
    raw = RawStore(tmp_path)
    hashes = [raw.put(first), raw.put(second)]
    assert len(regular_outcomes(raw, hashes, binding)) == 7
    with pytest.raises(ValueError):
        regular_outcomes(raw, hashes[::-1], binding)


class MinuteClient:
    def __init__(self, *, fail=False):
        self.calls = 0
        self.fail = fail

    def pages(self, source, endpoint, params, item_key, *, max_pages):
        self.calls += 1
        if self.fail:
            raise TimeoutError("fixture")
        _, page = envelope()
        return [CapturedPage(source, endpoint, params, page["received_at"], "fixture",
                             page["payload"])]


def test_outcome_ledger_is_separate_idempotent_and_rechecked(tmp_path):
    client = MinuteClient()
    pipeline = ExtractionPipeline(tmp_path, client, clock=lambda: NOW)
    result = capture_regular_outcome(pipeline, DAY, feed="sip", adjustment="split")
    assert result["state"] == "COMPLETE"
    assert result["official_auction_prices"] is False
    assert capture_regular_outcome(pipeline, DAY, feed="sip", adjustment="split") == result
    assert client.calls == 1
    with pipeline.store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM session_outcomes").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM price_bars").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0] == 0
    key = result["pages"][0]["digest"]
    path = pipeline.raw.root / key[:2] / f"{key}.json"
    path.unlink()
    with pytest.raises(OSError):
        capture_regular_outcome(pipeline, DAY, feed="sip", adjustment="split")


def test_unknown_outcome_is_not_silently_retried(tmp_path):
    client = MinuteClient(fail=True)
    pipeline = ExtractionPipeline(tmp_path, client, clock=lambda: NOW)
    first = capture_regular_outcome(pipeline, DAY, feed="sip", adjustment="split")
    assert first["state"] == "WAITING_HUMAN"
    assert capture_regular_outcome(pipeline, DAY, feed="sip", adjustment="split") == first
    assert client.calls == 1


def test_not_closed_outcome_never_calls_provider(tmp_path):
    client = MinuteClient()
    pipeline = ExtractionPipeline(tmp_path, client, clock=lambda: session_window(DAY).market_close)
    with pytest.raises(ValueError):
        capture_regular_outcome(pipeline, DAY, feed="sip", adjustment="split")
    assert client.calls == 0
