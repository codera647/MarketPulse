"""Synthetic chronology/provenance checks, not financial performance evidence."""

from copy import deepcopy
from datetime import date
from decimal import Decimal

import numpy as np
import pytest
from test_context_experts import payload

from marketpulse.baselines import CLASSES
from marketpulse.clock import exchange_calendar
from marketpulse.constants import STOCKS
from marketpulse.labels import classify_return
from marketpulse.regression_pipeline import authority, bounded_source
from marketpulse.stacking_models import EXPERTS, MetaAPI, probability_input
from marketpulse.stacking_pipeline import (
    assemble_oof,
    build,
    expert_apis,
    inner_rosters,
    saved_predict,
    select_experts,
    tail_calibration,
)
from marketpulse.storage import digest
from marketpulse.v2_features import FEATURE_VERSION
from marketpulse.v2_news import MODEL_SPEC
from marketpulse.v2_runtime import Artifacts, supervised


def source_fixture(root):
    artifacts, originals, entries = Artifacts(root / "artifacts"), [], []
    for year in range(2018, 2026):
        dates = exchange_calendar().valid_days(
            start_date=date(year, 1, 1), end_date=date(year, 2, 15)
        )
        for stamp in dates[:18]:
            session = stamp.date().isoformat()
            for i, symbol in enumerate(STOCKS):
                target = (-0.02, 0.0, 0.02)[i % 3]
                original = {
                    "session": session,
                    "symbol": symbol,
                    "return_fraction": str(target),
                    "threshold": "0.01",
                    "price_convention": "regular-minute-proxy/1",
                    "label": classify_return(Decimal(str(target)), Decimal("0.01")),
                }
                key = digest(original)
                originals.append({**original, "row_hash": key})
                entries.append(
                    {
                        "session": session,
                        "symbol": symbol,
                        "base_row_hash": key,
                        "label": original["label"],
                        "input_hash": artifacts.put(payload(session, symbol, key, i)),
                        "role": "train" if year < 2025 else "development",
                    }
                )
    base_hash = artifacts.put(originals)
    supervised(
        root,
        "base_rows",
        {"synthetic": True},
        lambda: {"base_rows_hash": base_hash},
        lambda result: None,
    )
    chunk = supervised(
        root,
        "dataset_chunk",
        {"synthetic": True},
        lambda: {"chunk_hash": artifacts.put(entries)},
        lambda result: None,
    )
    dataset_hash = artifacts.put(
        {
            "rows": entries,
            "chunks": [chunk],
            "binding": {"feature_version": FEATURE_VERSION, "base_hash": base_hash},
        }
    )
    supervised(
        root,
        "dataset",
        {"synthetic": True},
        lambda: {"dataset_hash": dataset_hash},
        lambda result: None,
    )
    release = artifacts.put(
        {
            "dataset_hash": dataset_hash,
            "finbert_spec": MODEL_SPEC,
            "evaluation_kind": "DEVELOPMENT_NOT_FINAL_TEST",
            "paper_action_authorized": False,
            "final_test_completed": False,
        }
    )
    supervised(
        root, "release", {"synthetic": True}, lambda: {"release_hash": release}, lambda result: None
    )
    return release, entries


def meta_rows():
    rows = []
    for i in range(90):
        row = {
            "session": "2022-01-03",
            "symbol": STOCKS[i % 6],
            "base_row_hash": digest(i),
            "input_hash": digest([i, 1]),
            "label": CLASSES[i % 3],
            "role": "train",
        }
        probabilities = {n: (np.eye(3)[i % 3] * 0.6 + 0.4 / 3).tolist() for n in EXPERTS}
        value = probability_input(row, probabilities, "2021-12-30")
        rows.append({**row, "input": value})
    return rows


def test_meta_probability_identity_chronology_and_saved_replay(tmp_path):
    api, rows = MetaAPI(), meta_rows()
    artifacts = Artifacts(tmp_path / "artifacts")
    model = api.fit(rows, api.settings()[0], artifacts)
    assert len(model["feature_names"]) == 9
    actual = api.predict(model, [{"input": r["input"]} for r in rows], artifacts)
    assert np.allclose(actual, api.predict(artifacts.get(artifacts.put(model)), rows, artifacts))
    bad = deepcopy(rows)
    bad[0]["input"]["used_outcomes_through"] = bad[0]["session"]
    bad[0]["input"]["feature_hash"] = digest(
        {k: v for k, v in bad[0]["input"].items() if k != "feature_hash"}
    )
    with pytest.raises(ValueError, match="chronology"):
        api.numeric(bad)
    bad = deepcopy(rows)
    bad[0]["input"]["probabilities"]["price"] = [0, 0, 2]
    bad[0]["input"]["feature_hash"] = digest(
        {k: v for k, v in bad[0]["input"].items() if k != "feature_hash"}
    )
    with pytest.raises(ValueError, match="probabilities"):
        api.numeric(bad)


def test_nested_stack_complete_receipts_and_no_refit_resume(tmp_path, monkeypatch):
    source, roster, root = tmp_path / "source", tmp_path / "roster", tmp_path / "stack"
    release, entries = source_fixture(source)
    proof = bounded_source(source, roster, release, lambda event: None)
    apis = expert_apis()
    for api in apis.values():
        config = api.settings()[0]
        monkeypatch.setattr(api, "settings", lambda c=config: [c])
    monkeypatch.setattr("marketpulse.stacking_pipeline.expert_apis", lambda: apis)
    meta_config = MetaAPI().settings()[0]
    monkeypatch.setattr(MetaAPI, "settings", lambda self: [meta_config])
    result = build(source, roster, root, release, proof["rows_hash"], evidence="Synthetic")
    assert result["stage"] == "COMPLETE" and result["fits_complete"] == 27
    authority(root, "release_hash", result["release_hash"])
    artifacts = Artifacts(root / "artifacts")
    report = artifacts.get(result["report_hash"])
    assert report["oof_rows"] == 324 and report["oof_years"] == ["2022", "2023", "2024"]
    for selected in report["nested_selections"]:
        assert selected["used_outcomes_through"] < selected["forecast_first_session"]
    assert set(report["metrics"]) == {
        "stack",
        "simple_average",
        "calibrated_average",
        "majority",
        *EXPERTS,
    }
    output = saved_predict(
        root, source, result["release_hash"], report["selection_input_hashes"][0]
    )
    assert output["outcomes_loaded"] is False and len(output["expert_probabilities"]) == 3
    with pytest.raises(ValueError, match="calibration history"):
        saved_predict(root, source, result["release_hash"], entries[0]["input_hash"])
    past = report["nested_selections"][0]
    altered = {**past, "used_outcomes_through": "2023-01-03"}
    from marketpulse.regression_pipeline import hydrate

    block = hydrate(source, [r for r in entries if r["session"][:4] == "2022"])
    with pytest.raises(ValueError, match="identity"):
        assemble_oof(root, block, altered)
    for api in apis.values():
        monkeypatch.setattr(api, "fit", lambda *a: pytest.fail("verified resume must not refit"))
    monkeypatch.setattr(MetaAPI, "fit", lambda *a: pytest.fail("verified resume must not refit"))
    assert build(source, roster, root, release, proof["rows_hash"], evidence="Synthetic") == result
    assert not (root / "v2-build.lock").exists()


def test_nested_blocks_purge_dates_and_reject_future_history(tmp_path):
    source = tmp_path / "source"
    _, entries = source_fixture(source)
    history = [r for r in entries if r["session"] < "2022-01-01"]
    fitting, calibration, selection = inner_rosters(history)
    assert max(r["session"] for r in fitting) < min(r["session"] for r in calibration)
    assert max(r["session"] for r in calibration) < min(r["session"] for r in selection)
    fitting, calibration = tail_calibration(history)
    assert max(r["session"] for r in fitting) < min(r["session"] for r in calibration)
    with pytest.raises(ValueError, match="future outcomes"):
        select_experts(
            tmp_path / "stack",
            history,
            history,
            "bad",
            expert_apis(),
            lambda event: None,
            {"complete": 0, "total": 1},
        )
