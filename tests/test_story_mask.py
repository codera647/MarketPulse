"""Chronological input cleaning: no future labels or destructive dataset edits."""

from copy import deepcopy
from datetime import date

import pytest
from test_dataset import NOW, contract
from test_research import CompleteSyntheticClient

from marketpulse import modeling, real_build
from marketpulse.extraction import ExtractionPipeline
from marketpulse.preprocessing import (
    NEWS_MASK_POLICY,
    extend_news_registry,
    mask_seen_stories,
    story_keys,
)
from marketpulse.real_training import RESEARCH_VERSION, authorized_rows, train_real_models
from marketpulse.research import collect_dataset
from marketpulse.storage import RawStore


def item(session, identifier, headline):
    return {"features": {"session": session},
            "news": [{"provider_id": identifier, "headline": headline, "summary": None}]}


def test_first_date_is_retained_for_all_companies_and_later_duplicates_are_masked():
    rows = [item("2024-07-01", 1, "Repeated headline"),
            item("2024-07-01", 1, "Repeated headline"),
            item("2024-07-02", 2, "  REPEATED   headline "),
            item("2024-07-03", 3, "New unique story")]
    registry = {"provider_ids": {}, "headline_groups": {}}
    extend_news_registry(registry, rows[:2])
    assert all(mask_seen_stories(registry, row["news"], "2024-07-01") for row in rows[:2])
    assert mask_seen_stories(registry, rows[2]["news"], "2024-07-02") == []
    assert mask_seen_stories(registry, rows[3]["news"], "2024-07-03") == rows[3]["news"]
    unchanged = mask_seen_stories(registry, rows[3]["news"], "2024-07-03")
    extend_news_registry(registry, [item("2024-07-05", 3, "New unique story")])
    assert mask_seen_stories(registry, rows[3]["news"], "2024-07-03") == unchanged


def test_chronological_replay_never_reads_labels_or_changes_frozen_model(monkeypatch):
    class InputOnly(dict):
        def __getitem__(self, key):
            assert key not in {"label", "return_fraction", "outcome_hash"}
            return super().__getitem__(key)

    rows = [InputOnly(item("2024-07-02", 2, "Same")),
            InputOnly(item("2024-07-01", 1, "Same"))]
    model = {"news_registry": {"provider_ids": {}, "headline_groups": {}}}
    frozen = deepcopy(model)

    def score(working, row, **kwargs):
        return {"kept": len(mask_seen_stories(working["news_registry"], row["news"],
                                             row["features"]["session"]))}

    monkeypatch.setattr(modeling, "score_comparison", score)
    assert modeling.chronological_scores(model, rows) == [{"kept": 0}, {"kept": 1}]
    assert model == frozen


@pytest.fixture(scope="module")
def duplicated_wire(tmp_path_factory):
    root = tmp_path_factory.mktemp("masked-synthetic-wire")
    value = contract()
    value["splits"] = {"train": ["2024-07-01", "2024-07-08"],
                       "validation": ["2024-07-09", "2024-07-23"],
                       "test": ["2024-07-24", "2024-07-26"]}
    pipeline = ExtractionPipeline(root, CompleteSyntheticClient(news=True), clock=lambda: NOW)
    result = collect_dataset(pipeline, value, batch_sessions=31, max_batches=1,
                             audit_each_batch=False, allow_story_duplicates=True)
    assert result["status"] == "INTEGRITY_BLOCKED"  # Raw duplicate evidence remains strict.
    assert result["accepted_rows"] == result["expected_rows"]
    authorization = {"schema": RESEARCH_VERSION, "contract_hash": result["contract_hash"],
                     "report_hash": result["report_hash"], "authorized": True,
                     "evidence": "Synthetic test authority, not real user/provider permission"}
    return pipeline, value, result, authorization


def test_mask_authority_allows_research_fit_without_opening_test_data(duplicated_wire, monkeypatch):
    pipeline, value, result, authorization = duplicated_wire
    with pytest.raises(ValueError, match="complete"):
        authorized_rows(pipeline, value, authorization)
    store = RawStore(pipeline.data_dir / "datasets")
    report = store.get(result["report_hash"])
    sealed = set()
    test_stories = []
    for entry in report["rows"]:
        if entry["split"] == "test":
            row = store.get(entry["row_hash"])
            sealed.add(entry["row_hash"])
            sealed.update(row["outcome_page_digests"])
            test_stories.extend(story_keys(article)[0] for article in row["news"])
    original = RawStore.get

    def guarded(self, key):
        assert key not in sealed, "masked fitting opened a sealed final-test artifact"
        return original(self, key)

    monkeypatch.setattr(RawStore, "get", guarded)
    authority = {**authorization, "news_mask_policy": NEWS_MASK_POLICY}
    fitted = train_real_models(pipeline.data_dir, value, authority)
    assert fitted["state"] == "COMPLETE" and fitted["final_test_opened"] is False
    assert fitted["masked_story_instances"]["train"] > 0
    model = RawStore(pipeline.data_dir / "research-models").get(fitted["model_hash"])
    assert not set(test_stories) & set(model["news_registry"]["provider_ids"])
    assert store.get(result["report_hash"])["status"] == "INTEGRITY_BLOCKED"
    # A historical one-off forecast uses the frozen earlier-data registry only.
    first_test = next(entry for entry in report["rows"] if entry["split"] == "test")
    assert date.fromisoformat(first_test["session"]) > date(2024, 7, 23)


def test_builder_preserves_raw_duplicate_block_but_records_mask_authority(tmp_path, monkeypatch):
    from types import SimpleNamespace

    pipeline = SimpleNamespace(data_dir=tmp_path, client=SimpleNamespace())
    report = {"status": "INTEGRITY_BLOCKED", "accepted_rows": 18, "expected_rows": 18,
              "contract_hash": "a" * 64, "missing_rows": [], "lineage_errors": [],
              "leakage": {"provider_ids_crossing_splits": [],
                          "headline_groups_crossing_splits": ["b" * 64]}}
    key = RawStore(tmp_path / "datasets").put(report)
    result = {**report, "report_hash": key}
    monkeypatch.setattr(real_build, "collect_dataset", lambda *a, **k: result)

    def fit(root, value, authority):
        assert authority["news_mask_policy"] == NEWS_MASK_POLICY
        return {"state": "COMPLETE"}

    monkeypatch.setattr(real_build, "train_real_models", fit)
    built = real_build.build_real_research(pipeline, contract(), evidence="Synthetic authority",
                                          mask_previous_stories=True)
    assert built["state"] == "COMPLETE"
    assert built["collection"]["status"] == "INTEGRITY_BLOCKED"
