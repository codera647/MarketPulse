"""Synthetic wire tests only; never evidence of real model performance."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
from test_research import CompleteSyntheticClient

from marketpulse.dataset import load_contract
from marketpulse.extraction import ExtractionPipeline
from marketpulse.modeling import score_comparison
from marketpulse.preprocessing import clean_financial_text, clean_news_text
from marketpulse.real_training import (
    RESEARCH_VERSION,
    authorized_rows,
    load_training_authorization,
    predict_real_research,
    train_real_models,
    validation_segments,
)
from marketpulse.research import collect_dataset, collection_plan, saved_pipeline
from marketpulse.storage import RawStore


def test_text_cleaning_preserves_financial_meaning():
    value = '<p>AAPL does NOT cut guidance: +12.5% &amp; $4.50.</p><script>junk()</script>'
    cleaned = clean_financial_text(value + ' https://example.com/tracking\u200b')
    assert "NOT" in cleaned and "+12.5%" in cleaned and "$4.50" in cleaned
    assert "junk" not in cleaned and "https" not in cleaned and "<p>" not in cleaned
    assert clean_financial_text(None) == ""
    assert clean_news_text([{"headline": "Same", "summary": None}] * 2) == "Same"
    with pytest.raises(ValueError):
        clean_financial_text(123)


def test_larger_plan_still_has_bounded_batches():
    value = load_contract(Path("doc/dataset_contract.proposed.json"))
    value["splits"] = {"train": ["2018-01-01", "2024-12-31"],
                       "validation": ["2025-01-01", "2025-12-31"],
                       "test": ["2026-01-01", "2026-09-30"]}
    plan = collection_plan(value, batch_sessions=31)
    assert plan["expected_rows"] == 13176
    assert all(batch["sessions"] <= 31 for batch in plan["batches"])
    assert plan["rights_confirmed"] is False


@pytest.fixture(scope="module")
def wire_dataset(tmp_path_factory):
    from test_dataset import NOW, contract

    root = tmp_path_factory.mktemp("real-training-synthetic-wire")
    value = contract()
    value["splits"] = {"train": ["2024-07-01", "2024-07-08"],
                       "validation": ["2024-07-09", "2024-07-23"],
                       "test": ["2024-07-24", "2024-07-26"]}
    pipeline = ExtractionPipeline(root, CompleteSyntheticClient(), clock=lambda: NOW)
    result = collect_dataset(pipeline, value, batch_sessions=31, max_batches=1,
                             audit_each_batch=False)
    assert result["status"] == "COMPLETE_RESEARCH_REVIEW_REQUIRED"
    authorization = {"schema": RESEARCH_VERSION, "contract_hash": result["contract_hash"],
                     "report_hash": result["report_hash"], "authorized": True,
                     "evidence": "Synthetic test authority; NOT a real provider grant"}
    return pipeline, value, authorization, result


def test_authorization_and_complete_quality_report_are_required(wire_dataset):
    pipeline, contract, authorization, result = wire_dataset
    invalid = {**authorization, "authorized": False}
    with pytest.raises(ValueError, match="authorization"):
        authorized_rows(pipeline, contract, invalid)
    store = RawStore(pipeline.data_dir / "datasets")
    incomplete = deepcopy(store.get(result["report_hash"]))
    incomplete["status"] = "INCOMPLETE"
    invalid = {**authorization, "report_hash": store.put(incomplete)}
    with pytest.raises(ValueError, match="complete"):
        authorized_rows(pipeline, contract, invalid)


def test_no_final_test_artifacts_are_read_during_fitting(wire_dataset, monkeypatch):
    pipeline, contract, authorization, result = wire_dataset
    store = RawStore(pipeline.data_dir / "datasets")
    report = store.get(result["report_hash"])
    sealed = set()
    for entry in report["rows"]:
        if entry["split"] == "test":
            row = store.get(entry["row_hash"])
            sealed.add(entry["row_hash"])
            sealed.update(row["outcome_page_digests"])
    original = RawStore.get

    def guarded(self, key):
        assert key not in sealed, "research fit read a sealed final-test artifact"
        return original(self, key)

    monkeypatch.setattr(RawStore, "get", guarded)
    fitted = train_real_models(pipeline.data_dir, contract, authorization)
    assert fitted["state"] == "COMPLETE"
    assert fitted["final_test_opened"] is False
    assert fitted["deployment_promoted"] is False
    assert fitted["human_dataset_reviewed"] is False
    assert fitted["paper_action_authorized"] is False
    assert train_real_models(pipeline.data_dir, contract, authorization) == fitted


def test_saved_research_inference_never_reads_outcomes(wire_dataset, monkeypatch):
    pipeline, contract, authorization, _ = wire_dataset
    fitted = train_real_models(pipeline.data_dir, contract, authorization)
    original = RawStore.get

    def guarded(self, key):
        value = original(self, key)
        assert not (isinstance(value, dict) and ("return_fraction" in value
                    or value.get("source") == "alpaca_regular_minutes"))
        return value

    monkeypatch.setattr(RawStore, "get", guarded)
    forecast = predict_real_research(pipeline.data_dir, fitted["release_hash"],
                                    "AAPL", "2024-07-25")
    assert forecast["outcome_loaded"] is False
    assert sum(forecast["probabilities"].values()) == pytest.approx(1)
    assert forecast["research_only"] is True
    with pytest.raises(ValueError):
        predict_real_research(pipeline.data_dir, fitted["release_hash"], "TSLA", "2024-07-25")


def test_real_model_cannot_score_fixture_tier(wire_dataset):
    pipeline, contract, authorization, _ = wire_dataset
    fitted = train_real_models(pipeline.data_dir, contract, authorization)
    model = RawStore(pipeline.data_dir / "research-models").get(fitted["model_hash"])
    train, validation, _ = authorized_rows(
        saved_pipeline(pipeline.data_dir), contract, authorization)
    calibration, selection = validation_segments(validation)
    assert not {r["session"] for r in calibration} & {r["session"] for r in selection}
    bad = deepcopy(train[0])
    bad["features"]["availability_tier"] = "FIXTURE"
    with pytest.raises(ValueError, match="tier"):
        score_comparison(model, bad)


def test_loading_training_authorization(tmp_path, wire_dataset):
    _, _, authorization, _ = wire_dataset
    path = tmp_path / "authorization.json"
    # Test fixture generation is not a project artifact or provider permission.
    path.write_text(json.dumps(authorization), encoding="utf-8")
    assert load_training_authorization(path) == authorization
    authorization = {**authorization, "authorized": False}
    path.write_text(json.dumps(authorization), encoding="utf-8")
    with pytest.raises(ValueError):
        load_training_authorization(path)
