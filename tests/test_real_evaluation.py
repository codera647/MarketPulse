"""Synthetic wire tests only, not evidence of market predictive performance."""

import json
import sqlite3
from copy import deepcopy

import pytest
from test_real_training import wire_dataset  # noqa: F401 -- shared synthetic wire fixture

from marketpulse import modeling, real_evaluation, real_training
from marketpulse.storage import RawStore


@pytest.fixture(scope="module")
def frozen_wire(request):
    pipeline, contract, authorization, _ = request.getfixturevalue("wire_dataset")
    release = real_training.train_real_models(pipeline.data_dir, contract, authorization)
    assert release["state"] == "COMPLETE"
    return pipeline, release


def test_final_test_predictions_are_committed_before_outcomes_and_never_refit(
        frozen_wire, monkeypatch):
    pipeline, release = frozen_wire
    model_store = RawStore(pipeline.data_dir / "research-models")
    frozen = deepcopy(model_store.get(release["model_hash"]))
    report = RawStore(pipeline.data_dir / "datasets").get(release["binding"]["report_hash"])
    sealed = set()
    original = RawStore.get
    for entry in report["rows"]:
        if entry["split"] == "test":
            row = original(RawStore(pipeline.data_dir / "datasets"), entry["row_hash"])
            sealed.add(entry["row_hash"])
            sealed.update(row["outcome_page_digests"])
    opened = []

    def guard(self, key):
        if key in sealed:
            ledger = pipeline.data_dir / "research-evaluation-trailforge.sqlite3"
            assert ledger.exists(), "test outcome read before evaluation authority existed"
            with sqlite3.connect(ledger) as db:
                records = [json.loads(r[0]) for r in db.execute("SELECT payload FROM runs")]
            assert records and records[0]["tasks"]["predict"]["status"] == "DONE"
            prediction_hash = records[0]["tasks"]["predict"]["result"]["prediction_hash"]
            committed = original(RawStore(pipeline.data_dir / "research-evaluations"),
                                 prediction_hash)
            assert committed["outcomes_loaded"] is False
            saved_inputs = original(RawStore(pipeline.data_dir / "research-evaluations"),
                                    committed["input_hash"])
            assert not any(set(row) & {"label", "return_fraction", "outcome_hash"}
                           for row in saved_inputs)
            opened.append(key)
        return original(self, key)

    def forbidden(*args, **kwargs):
        raise AssertionError("held-out test attempted model fitting/calibration")

    monkeypatch.setattr(RawStore, "get", guard)
    monkeypatch.setattr(modeling, "fit_comparison", forbidden)
    monkeypatch.setattr(modeling, "calibrate", forbidden)
    monkeypatch.setattr(real_training, "train_real_models", forbidden)
    events = []
    result = real_evaluation.evaluate_real_research(
        pipeline.data_dir, release["release_hash"], evidence="Synthetic test authorization",
        progress=events.append)
    assert result["state"] == "COMPLETE" and opened
    assert result["selected_model"] == release["selected_model"]
    assert result["paper_action_authorized"] is False
    assert model_store.get(release["model_hash"]) == frozen
    artifacts = RawStore(pipeline.data_dir / "research-evaluations")
    evaluation = artifacts.get(result["evaluation_hash"])
    assert evaluation["selection_unchanged"] is True
    assert evaluation["retraining_performed"] is False
    assert set(evaluation["metrics"]) == set(modeling.MODEL_NAMES)
    assert evaluation["rows"] == result["test_rows"]
    assert len(evaluation["by_ticker"]) == 6
    assert events[-1]["stage"] == "COMPLETE"
    replay = real_evaluation.evaluate_real_research(
        pipeline.data_dir, release["release_hash"], evidence="Synthetic replay authorization")
    assert replay == result
    assert not (pipeline.data_dir / "research-final-test.lock").exists()


def test_existing_test_freeze_refuses_another_release(frozen_wire, monkeypatch):
    pipeline, release = frozen_wire
    # Ensure a freeze exists even when this test is selected independently.
    real_evaluation.evaluate_real_research(pipeline.data_dir, release["release_hash"],
                                          evidence="Synthetic test authorization")
    monkeypatch.setattr(real_evaluation, "load_research_release", lambda *a: release)
    with pytest.raises(ValueError, match="already frozen"):
        real_evaluation.evaluate_real_research(pipeline.data_dir, "a" * 64,
                                              evidence="Synthetic changed-release request")


def test_invalid_test_authority_and_existing_owner_are_refused(frozen_wire):
    pipeline, release = frozen_wire
    with pytest.raises(ValueError, match="authorization"):
        real_evaluation.evaluate_real_research(pipeline.data_dir, release["release_hash"],
                                              evidence="")
    lock = pipeline.data_dir / "research-final-test.lock"
    lock.write_text("other synthetic owner", encoding="utf-8")
    try:
        with pytest.raises(FileExistsError):
            real_evaluation.evaluate_real_research(pipeline.data_dir, release["release_hash"],
                                                  evidence="Synthetic authorization")
        assert lock.read_text() == "other synthetic owner"
    finally:
        lock.unlink()


def test_summary_requires_matched_probabilities_without_scoring(frozen_wire, monkeypatch):
    pipeline, release = frozen_wire
    model = RawStore(pipeline.data_dir / "research-models").get(release["model_hash"])
    identity, _, roster = real_evaluation.test_roster(
        real_evaluation.saved_pipeline(pipeline.data_dir), release)
    inputs = real_evaluation.test_inputs(pipeline, identity, roster)
    scores = modeling.chronological_scores(model, inputs)
    rows = real_evaluation.test_outcomes(pipeline, release, inputs)

    def forbidden(*args, **kwargs):
        raise AssertionError("summary must not rerun inference or refit")

    monkeypatch.setattr(modeling, "chronological_scores", forbidden)
    result = modeling.summarize_comparison(model, rows, scores, split="test")
    assert result["rows"] == len(rows)
    with pytest.raises(ValueError, match="probability"):
        modeling.summarize_comparison(model, rows, scores[:-1], split="test")
