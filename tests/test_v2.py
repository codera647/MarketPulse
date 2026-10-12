"""Synthetic v2 software checks; these examples are NOT market evidence."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone

import numpy as np
import pytest

from marketpulse.alpaca import CapturedPage
from marketpulse.baselines import CLASSES
from marketpulse.clock import session_window, utc_iso
from marketpulse.storage import RawStore, digest
from marketpulse.v2_features import enrich_input, feature_matrix, mask_rows
from marketpulse.v2_models import (
    calibrate_candidate,
    candidate_settings,
    class_weights,
    fit_candidate,
    fold_rosters,
    score_candidate,
)
from marketpulse.v2_news import (
    MODEL_SPEC,
    article_text,
    capture_sentiment,
    load_sentiment,
    news_values,
    validate_sentiment,
)
from marketpulse.v2_pipeline import build_features, predict_v2, train_v2
from marketpulse.v2_runtime import Artifacts, check_receipt, owned_run, supervised
from marketpulse.v2_sources import (
    capture_context,
    load_context,
    month_queries,
    premarket_values,
    validate_pages,
)


def article(session="2025-07-01", symbol="AAPL", headline="Apple raises guidance"):
    window = session_window(date.fromisoformat(session))
    return {
        "headline": headline,
        "summary": "Quarterly earnings improve by +12%.",
        "created_at": utc_iso(window.cutoff - timedelta(hours=1)),
        "updated_at": utc_iso(window.cutoff - timedelta(minutes=30)),
        "provider_id": digest(headline),
        "symbols": [symbol],
    }


def base_row(session="2025-07-01", symbol="AAPL", news=None):
    from marketpulse.baselines import PRICE_FEATURES

    return {
        "session": session,
        "symbol": symbol,
        "row_hash": digest([session, symbol]),
        "news": [article(session, symbol)] if news is None else news,
        "features": {
            "session": session,
            "feature_hash": "f" * 64,
            "cutoff_utc": utc_iso(session_window(date.fromisoformat(session)).cutoff),
            "values": {name: 0.01 for name in PRICE_FEATURES},
        },
    }


def sentiment():
    return {"probabilities": {"positive": 0.8, "negative": 0.1, "neutral": 0.1}, "truncated": False}


def test_context_queries_bounded_scope_and_raw_sip():
    queries = month_queries(date(2018, 1, 2), date(2025, 12, 31))
    assert len(queries) == 194
    assert {q["timeframe"] for q in queries} == {"1Day", "30Min"}
    assert all(q["feed"] == "sip" and q["adjustment"] == "raw" for q in queries)
    with pytest.raises(ValueError):
        month_queries(date(2010, 1, 1), date(2026, 1, 1))


def test_context_page_provenance_and_cutoff(tmp_path):
    from dataclasses import asdict

    query = {
        "symbols": "AAPL",
        "start": "2025-07-01T00:00:00Z",
        "end": "2025-07-02T00:00:00Z",
        "timeframe": "30Min",
        "feed": "sip",
    }
    bar = {"t": "2025-07-01T12:30:00Z", "o": 100, "h": 102, "l": 99, "c": 101, "v": 1000}
    raw = RawStore(tmp_path)
    page = asdict(
        CapturedPage(
            "v2_market_context",
            "/v2/stocks/bars",
            query,
            "2026-10-12T12:00:00Z",
            None,
            {"bars": {"AAPL": [bar]}, "next_page_token": None},
        )
    )
    assert len(validate_pages(raw, query, [raw.put(page)])) == 1
    broken = deepcopy(page)
    broken["payload"]["next_page_token"] = "not-complete"
    with pytest.raises(ValueError, match="incomplete"):
        validate_pages(raw, query, [raw.put(broken)])
    broken = deepcopy(page)
    broken["payload"]["bars"]["AAPL"][0]["v"] = float("nan")
    with pytest.raises(ValueError, match="volume"):
        validate_pages(raw, query, [raw.put(broken)])
    daily = {("2025-06-30", "AAPL"): {"c": 100}}
    values = premarket_values(
        "2025-07-01", "AAPL", daily, {("2025-07-01", "AAPL"): [bar]}, "2025-06-30"
    )
    assert values["premarket_return"] == pytest.approx(0.01)
    assert values["premarket_interval_coverage"] == 0.1
    assert values["premarket_last_age_minutes"] == 0
    late = {**bar, "t": "2025-07-01T13:00:00Z"}
    with pytest.raises(ValueError, match="cutoff"):
        premarket_values(
            "2025-07-01", "AAPL", daily, {("2025-07-01", "AAPL"): [late]}, "2025-06-30"
        )


@pytest.mark.parametrize(
    "session,last_stamp",
    [("2025-07-01", "2025-07-01T12:30:00Z"), ("2025-01-02", "2025-01-02T13:30:00Z")],
)
def test_premarket_dst_boundary_and_unknown_empty(session, last_stamp):
    bar = {"t": last_stamp, "c": 100, "v": 10}
    value = premarket_values(session, "AAPL", {}, {(session, "AAPL"): [bar]}, "2024-12-31")
    assert value["premarket_last_age_minutes"] == 0
    assert value["premarket_return"] is None
    empty = premarket_values(session, "AAPL", {}, {}, "2024-12-31")
    assert empty["premarket_observed_volume"] is None
    assert empty["premarket_missing"] == 1


def test_news_meaning_is_not_price_or_calendar_truth():
    row = base_row()
    cache = {digest({"text": article_text(row["news"][0]), "spec": MODEL_SPEC}): sentiment()}
    value = news_values(row, cache)
    assert value["news_sentiment_positive"] == pytest.approx(0.8)
    assert value["news_event_guidance"] == 1 and value["news_event_earnings"] == 1
    assert value["news_entity_relevance_mean"] == 1
    assert value["scheduled_earnings_today"] is None
    assert value["numeric_earnings_surprise"] is None
    empty = news_values(base_row(news=[]), {})
    assert empty["news_sentiment_neutral"] is None and empty["news_meaning_missing"] == 1
    row["news"][0]["updated_at"] = "2025-07-01T14:00:00Z"
    with pytest.raises(ValueError, match="cutoff"):
        news_values(row, cache)
    with pytest.raises(ValueError):
        validate_sentiment(
            {"probabilities": {"positive": 1, "negative": 1, "neutral": 1}, "truncated": False}
        )


def test_masking_shared_first_date_then_later_inputs():
    first = base_row("2025-07-01")
    shared = base_row("2025-07-01", "NVDA", first["news"])
    repeated = base_row("2025-07-02", news=first["news"])
    rows = mask_rows([repeated, shared, first])
    assert [len(row["news"]) for row in rows] == [1, 1, 0]
    assert len(repeated["news"]) == 1


def test_enriched_input_contains_no_labels_and_detects_corruption():
    row = base_row(news=[])
    row["label"] = "UP"
    item = {"input": enrich_input(row, {}, {}, {}), "news": []}
    assert "label" not in item["input"] and item["input"]["outcomes_loaded"] is False
    names, matrix = feature_matrix([item], "meaning")
    assert "company_AAPL" in names and "news_sentiment_positive" in names
    assert matrix[0][names.index("premarket_return")] is None
    item["input"]["market"]["company_AAPL"] = 0
    with pytest.raises(ValueError, match="identity"):
        feature_matrix([item], "meaning")


def test_native_supervision_idempotence_failure_and_lock(tmp_path):
    calls = []

    def execute():
        calls.append(1)
        return {"output_hash": RawStore(tmp_path / "artifacts").put({"value": 7})}

    def verify(result):
        assert RawStore(tmp_path / "artifacts").get(result["output_hash"]) == {"value": 7}

    result = supervised(tmp_path, "test", {"identity": 1}, execute, verify)
    check_receipt(tmp_path, result)
    assert supervised(tmp_path, "test", {"identity": 1}, execute, verify) == result
    assert calls == [1]
    bad = {**result, "binding_hash": "0" * 64}
    with pytest.raises(ValueError):
        check_receipt(tmp_path, bad)
    with owned_run(tmp_path, {"experiment": 1}) as checkpoint:
        checkpoint({"stage": "TESTING"})
        with pytest.raises(FileExistsError):
            with owned_run(tmp_path, {"experiment": 1}):
                pass
        assert (tmp_path / "v2-build.lock").exists()
    assert not (tmp_path / "v2-build.lock").exists()
    assert json.loads((tmp_path / "v2-status.json").read_text())["stage"] == "TESTING"

    def fail(result):
        raise ValueError("induced")

    with pytest.raises(ValueError, match="not reset"):
        supervised(tmp_path, "failure", {"identity": 2}, execute, fail)
    before = len(calls)
    with pytest.raises(ValueError):
        supervised(tmp_path, "failure", {"identity": 2}, execute, fail)
    assert len(calls) == before


class FakeSentiment:
    """Manufactured sentiment only, never used in real runs."""

    def __init__(self, root):
        pass

    def score(self, texts):
        return [sentiment() for text in texts]


def test_sentiment_cache_native_receipts_and_resumability(tmp_path):
    rows = [base_row(), base_row("2025-07-02")]
    result = capture_sentiment(tmp_path, rows, lambda event: None, engine_factory=FakeSentiment)
    cache = load_sentiment(tmp_path, result["manifest_hash"])
    assert len(cache) == 1 and result["documents"] == 1
    again = capture_sentiment(tmp_path, rows, lambda event: None, engine_factory=FakeSentiment)
    assert again == result


def model_rows():
    from marketpulse.baselines import PRICE_FEATURES

    rows = []
    for year in range(2020, 2026):
        dates = [
            d.date().isoformat()
            for d in __import__("marketpulse.clock", fromlist=["exchange_calendar"])
            .exchange_calendar()
            .valid_days(start_date=f"{year}-01-01", end_date=f"{year}-02-10")
        ][:12]
        for index, session in enumerate(dates):
            for symbol in ("AAPL", "NVDA", "AMZN", "JPM", "XOM", "WMT"):
                label = CLASSES[index % 3]
                row = base_row(session, symbol, [])
                row["features"]["values"] = {
                    name: (index % 3 - 1) * 0.02 for name in PRICE_FEATURES
                }
                value = enrich_input(row, {}, {}, {})
                text = (
                    "declining outlook"
                    if label == "DOWN"
                    else "strong growth"
                    if label == "UP"
                    else "routine meeting"
                )
                news = [{"headline": text, "summary": None}]
                rows.append(
                    {
                        "session": session,
                        "symbol": symbol,
                        "role": "train" if year < 2025 else "development",
                        "base_row_hash": row["row_hash"],
                        "label": label,
                        "input": value,
                        "news": news,
                    }
                )
    return rows


def test_weights_training_counts_only_and_fold_dates():
    values = class_weights(["DOWN"] * 2 + ["UP"] * 4 + ["NO_MATERIAL_MOVE"] * 12, True, 1.5)
    assert values["DOWN"] == 4.5 and values["NO_MATERIAL_MOVE"] == 0.5
    rows = model_rows()
    folds = fold_rosters([row for row in rows if row["role"] == "train"])
    assert len(folds) == 3
    for train, validation in folds:
        assert max(row["session"] for row in train) < min(row["session"] for row in validation)
        for day in {row["session"] for row in validation}:
            assert len([row for row in validation if row["session"] == day]) == 6
    assert len(candidate_settings()) == 18


@pytest.mark.parametrize("stage", ["existing", "market", "meaning"])
def test_portable_weighted_inference_calibration_and_train_only(tmp_path, stage):
    rows = model_rows()
    artifacts = Artifacts(tmp_path / "artifacts")
    train = [row for row in rows if row["role"] == "train"]
    calibration = [{**row, "role": "calibration"} for row in rows if row["role"] != "train"]
    settings = {
        "family": "weighted_logistic",
        "stage": stage,
        "C": 0.1,
        "weighted": True,
        "move_multiplier": 1.0,
    }
    model = fit_candidate(train, settings, artifacts)
    frozen = digest(model)
    calibrated = calibrate_candidate(model, calibration, artifacts)
    assert digest(model) == frozen
    saved = artifacts.get(artifacts.put(calibrated))
    scores = score_candidate(saved, calibration, artifacts)
    assert np.allclose(np.sum(scores, axis=1), 1)
    assert (
        np.argmax(scores, axis=1).tolist()
        == np.argmax(score_candidate(model, calibration, artifacts), axis=1).tolist()
    )
    with pytest.raises(ValueError, match="training roles"):
        fit_candidate(calibration, settings, artifacts)
    with pytest.raises(ValueError, match="overlaps"):
        calibrate_candidate(model, [{**row, "role": "calibration"} for row in train], artifacts)


def test_catboost_binary_saved_model_and_corruption(tmp_path):
    pytest.importorskip("catboost")
    artifacts = Artifacts(tmp_path / "artifacts")
    rows = [row for row in model_rows() if row["role"] == "train"]
    settings = {
        "family": "catboost",
        "stage": "meaning",
        "depth": 4,
        "iterations": 12,
        "weighted": True,
        "move_multiplier": 1.0,
    }
    model = fit_candidate(rows, settings, artifacts)
    assert np.allclose(np.sum(score_candidate(model, rows, artifacts), axis=1), 1)
    path = artifacts.binary_path(model["binary_hash"])
    path.write_bytes(b"induced corruption")
    with pytest.raises(ValueError, match="digest"):
        score_candidate(model, rows, artifacts)


def test_v2_end_to_end_development_release_inference(tmp_path, monkeypatch):
    # Keep this software test fast; the real experiment uses the documented grid.
    settings = [
        {
            "family": "weighted_logistic",
            "stage": "meaning",
            "C": 0.1,
            "weighted": True,
            "move_multiplier": 1.0,
        }
    ]
    monkeypatch.setattr("marketpulse.v2_pipeline.candidate_settings", lambda: settings)
    artifacts = Artifacts(tmp_path / "artifacts")
    rows = model_rows()
    roster = []
    for row in rows:
        item = {"input": row["input"], "news": row["news"]}
        roster.append(
            {k: v for k, v in row.items() if k not in {"input", "news"}}
            | {"input_hash": artifacts.put(item)}
        )
    dataset_hash = artifacts.put({"rows": roster, "quality": {"synthetic": True}})
    result = supervised(
        tmp_path,
        "test_dataset",
        {"identity": 1},
        lambda: {"dataset_hash": dataset_hash},
        lambda output: None,
    )
    release = train_v2(tmp_path, result, lambda event: None)
    assert release["stage"] == "COMPLETE" and release["final_test_completed"] is False
    assert release["paper_action_authorized"] is False
    report = artifacts.get(release["report_hash"])
    assert report["selection_rows"] == 30 and report["calibration_rows"] == 36
    prediction = predict_v2(tmp_path, release["release_hash"], roster[-1]["input_hash"])
    assert prediction["outcomes_loaded"] is False
    assert prediction["evaluation_kind"] == "DEVELOPMENT_NOT_FINAL_TEST"
    assert sum(prediction["probabilities"].values()) == pytest.approx(1)
    assert train_v2(tmp_path, result, lambda event: None)["release_hash"] == release["release_hash"]


class FakeContextClient:
    def pages(self, source, endpoint, query, item_key, *, max_pages):
        from marketpulse.clock import exchange_calendar, parse_time

        days = exchange_calendar().valid_days(
            start_date=query["start"][:10], end_date=query["end"][:10]
        )
        bars = {symbol: [] for symbol in query["symbols"].split(",")}
        for day in days:
            if day.isoformat()[:10] == query["end"][:10]:
                continue
            session = day.date()
            stamp = (
                session_window(session).cutoff - timedelta(minutes=30)
                if query["timeframe"] == "30Min"
                else datetime.combine(session, datetime.min.time(), timezone.utc)
                + timedelta(hours=5)
            )
            assert parse_time(query["start"]) <= stamp <= parse_time(query["end"])
            for symbol in bars:
                bars[symbol].append(
                    {"t": utc_iso(stamp), "o": 100, "c": 101, "h": 102, "l": 99, "v": 1000}
                )
        return [
            CapturedPage(
                source,
                endpoint,
                query,
                "2026-10-12T12:00:00Z",
                None,
                {"bars": bars, "next_page_token": None},
            )
        ]


def test_context_feature_chunks_and_source_entity_projection(tmp_path):
    artifacts = Artifacts(tmp_path / "artifacts")
    row = base_row()
    # V1 deliberately omits entity tags from its compact article projection.
    row["news"][0]["version_hash"] = "c" * 64
    row["news"][0].pop("symbols")
    row["split"], row["label"] = "validation", "UP"
    tags_hash = artifacts.put({"c" * 64: ["AAPL"]})
    base_hash = artifacts.put([row])
    context = capture_context(
        tmp_path, FakeContextClient(), date(2025, 7, 1), date(2025, 7, 3), lambda event: None
    )
    daily, intraday = load_context(tmp_path, context["manifest_hash"])
    assert daily and intraday
    news = capture_sentiment(tmp_path, [row], lambda event: None, engine_factory=FakeSentiment)
    result = build_features(
        tmp_path,
        base_hash,
        context["manifest_hash"],
        news["manifest_hash"],
        lambda event: None,
        entity_tags_hash=tags_hash,
    )
    check_receipt(tmp_path, result)
    dataset = artifacts.get(result["dataset_hash"])
    assert dataset["quality"]["rows"] == 1
    saved_input = artifacts.get(dataset["rows"][0]["input_hash"])
    assert saved_input["news"][0]["symbols"] == ["AAPL"]
    assert saved_input["input"]["market"]["sector_missing"] == 0
    assert saved_input["input"]["market"]["premarket_missing"] == 0
    assert set(saved_input) == {"input", "news"} and "label" not in saved_input["input"]
    assert (
        build_features(
            tmp_path,
            base_hash,
            context["manifest_hash"],
            news["manifest_hash"],
            lambda event: None,
            entity_tags_hash=tags_hash,
        )
        == result
    )
