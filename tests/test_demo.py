from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from marketpulse.api import create_app
from marketpulse.backup import backup_demo, restore_demo
from marketpulse.baseline_fixtures import generate_fixture_catalog
from marketpulse.baselines import selected_rows
from marketpulse.demo import run_full_demo, select_policy
from marketpulse.modeling import (
    MODEL_NAMES,
    calibrate,
    evaluate_comparison,
    fit_comparison,
    headline_text,
    metrics,
    score_comparison,
    validate_comparison,
)
from marketpulse.service import DemoService
from marketpulse.storage import RawStore


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    root = tmp_path_factory.mktemp("full-demo")
    result = run_full_demo(root)
    assert result["state"] == "COMPLETE"
    service = DemoService(root)
    model = service.artifacts.get(service.release()["model_hash"])
    catalog = service.release()["binding"]["catalog_hash"]
    train, validation = selected_rows(service.artifacts, catalog)
    return root, result, service, model, train, validation


def test_demo_has_separated_freezes_and_fixture_only_release(demo):
    _, result, service, model, train, validation = demo
    release = service.release()
    assert [
        result[name] for name in ("train_rows", "calibration_rows", "selection_rows", "test_rows")
    ] == [84, 12, 12, 24]
    assert release["test_opened_only_after_choices_frozen"] is True
    assert release["trailforge_verify_receipt"]
    assert service.ready()["real_data_mode_available"] is False
    policy = service.artifacts.get(release["policy_hash"])
    calibration = set(model["calibrators"]["combined"]["row_hashes"])
    selection = set(policy["selected_on_row_hashes"])
    assert not calibration & selection
    assert not (calibration | selection) & set(model["training_row_hashes"])
    assert len(calibration) == len(selection) == 12
    assert all(word not in model["vocabulary"] for word in ("futureword", "label"))
    assert max(row["session"] for row in train) < min(row["session"] for row in validation)


def test_safe_json_four_model_replay_and_calibration(demo):
    _, _, _, model, _, validation = demo
    detached = json.loads(json.dumps(model, allow_nan=False))
    for row in validation:
        result = score_comparison(detached, row)
        assert set(result) == set(MODEL_NAMES)
        for probs in result.values():
            assert len(probs) == 3 and np.isfinite(probs).all()
            assert sum(probs) == pytest.approx(1)
    assert detached["paper_action_authorized"] is False
    assert detached["calibration_fitted"] is True


def test_full_demo_repeat_reuses_run_and_release(demo):
    root, original, _, _, _, _ = demo
    repeated = run_full_demo(root)
    assert repeated["release_hash"] == original["release_hash"]
    assert repeated["run_id"] == original["run_id"]
    assert repeated["real_data_collected"] is False


def test_healthy_empty_news_is_valid_and_unknown_words_do_not_expand_vocabulary(demo, tmp_path):
    store = RawStore(tmp_path / "empty-news")
    catalog = generate_fixture_catalog(store)
    _, validation = selected_rows(store, catalog)
    model = demo[3]
    assert headline_text(validation[0]) == "noeligibleheadline"
    scored = score_comparison(model, validation[0])
    assert all(sum(probs) == pytest.approx(1) for probs in scored.values())
    altered = deepcopy(demo[5][0])
    altered["news"][0]["headline"] += " futureword"
    before = deepcopy(model)
    score_comparison(model, altered)
    assert model == before and "futureword" not in model["vocabulary"]


def test_bad_fixture_options_are_rejected(tmp_path):
    with pytest.raises(ValueError):
        generate_fixture_catalog(RawStore(tmp_path), with_news="yes")


@pytest.mark.parametrize("mutation", ["real", "class_order", "nan", "vocabulary", "temperature"])
def test_tampered_models_fail_closed(demo, mutation):
    model = deepcopy(demo[3])
    if mutation == "real":
        model["availability_tier"] = "HISTORICAL_APPROXIMATE"
    elif mutation == "class_order":
        model["class_names"].reverse()
    elif mutation == "nan":
        model["combined"]["coefficients"][0][0] = float("nan")
    elif mutation == "vocabulary":
        model["vocabulary"].append(model["vocabulary"][0])
    else:
        model["calibrators"]["combined"]["temperature"] = True
    with pytest.raises(ValueError):
        validate_comparison(model)


def test_text_cutoff_and_version_mismatch_rejected(demo):
    row = deepcopy(demo[5][0])
    row["news"][0]["updated_at"] = "2099-01-01T12:00:00Z"
    with pytest.raises(ValueError, match="post-cutoff"):
        headline_text(row)
    row = deepcopy(demo[5][0])
    row["news"][0]["version_hash"] = "a" * 64
    with pytest.raises(ValueError, match="versions"):
        headline_text(row)


def test_wrong_split_and_calibration_overlap_rejected(demo):
    _, _, _, model, train, validation = demo
    with pytest.raises(ValueError):
        fit_comparison(validation)
    with pytest.raises(ValueError):
        calibrate(model, train)
    with pytest.raises(ValueError, match="overlaps"):
        evaluate_comparison(model, validation[:12], split="validation")
    with pytest.raises(ValueError):
        evaluate_comparison(model, validation, split="test")


def test_policy_refuses_calibration_and_training_overlap(demo):
    # The same explicit independent segments reproduce the frozen policy.
    _, _, service, model, _, validation = demo
    selection = validation[12:]
    with pytest.raises(ValueError):
        select_policy(model, validation[:12])
    with pytest.raises(ValueError):
        select_policy(model, demo[4])
    assert select_policy(model, selection) == service.artifacts.get(
        service.release()["policy_hash"]
    )


@pytest.mark.parametrize("probs", [[[0.2, 0.2, 0.2]], [[1.1, -0.1, 0]], [[float("nan"), 0, 1]]])
def test_evaluation_rejects_invalid_probabilities(probs):
    with pytest.raises(ValueError):
        metrics(["UP"], probs)


def test_forecast_does_not_read_outcomes_and_reveal_does_not_mutate(demo, monkeypatch):
    service = demo[2]
    original = service.outcomes.get

    def forbidden(key):
        raise AssertionError("future outcome opened by forecast")

    monkeypatch.setattr(service.outcomes, "get", forbidden)
    decision = service.forecast("NVDA", "2024-07-30")
    assert "label" not in decision and "return_fraction" not in decision
    assert "outcome_hash" not in decision["binding"]
    assert decision["verify_receipt"] and decision["simulation_only"]
    monkeypatch.setattr(service.outcomes, "get", original)
    before = deepcopy(decision)
    actual = service.reveal_outcome(decision["decision_id"])
    assert actual["availability_tier"] == "FIXTURE"
    assert service.get_decision(decision["decision_id"]) == before
    assert service.reveal_outcome(decision["decision_id"]) == actual


@pytest.mark.parametrize(
    "fault,action,reason",
    [
        ("STALE", "BLOCKED", "STALE_DATA"),
        ("MISSING_NEWS", "BLOCKED", "NEWS_FEED_UNAVAILABLE"),
        ("EXPIRED", "BLOCKED", "SIGNAL_EXPIRED"),
        ("LOW_CONFIDENCE", "ABSTAIN", "LOW_CONFIDENCE"),
    ],
)
def test_failure_fixtures_do_not_create_positions(demo, fault, action, reason):
    decision = demo[2].forecast("JPM", "2024-07-30", fault=fault)
    assert decision["action"] == action and decision["reason_codes"] == [reason]


def test_timeout_is_held_and_never_auto_retried(demo):
    service = demo[2]
    first = service.forecast("JPM", "2024-07-31", fault="TIMEOUT")
    second = service.forecast("JPM", "2024-07-31", fault="TIMEOUT")
    assert first == second
    assert first["state"] != "COMPLETE" and first["action"] is None
    with pytest.raises(KeyError):
        service.get_decision(first["request_key"])


def test_concurrent_duplicate_requests_share_one_immutable_decision(demo):
    root = demo[0]
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(
            pool.map(lambda _: DemoService(root).forecast("AMZN", "2024-07-31"), range(8))
        )
    assert all(result == results[0] for result in results)
    with demo[2].connect() as db:
        assert (
            db.execute(
                "SELECT COUNT(*) FROM decisions WHERE decision_id=?", (results[0]["decision_id"],)
            ).fetchone()[0]
            == 1
        )


def test_verified_run_repairs_product_record_after_crash(demo, monkeypatch):
    service = demo[2]
    crashes = []

    def crash_once(key):
        if not crashes:
            crashes.append(key)
            raise RuntimeError("simulated crash after verification")

    monkeypatch.setattr(service, "_after_verified", crash_once)
    with pytest.raises(RuntimeError):
        service.forecast("XOM", "2024-08-01")
    with service.connect() as db:
        prior = db.execute("SELECT run_id FROM runs WHERE request_key=?", (crashes[0],)).fetchone()[
            0
        ]
    restarted = DemoService(demo[0])
    repaired = restarted.reconcile()
    assert repaired["materialized"] >= 1
    decision = restarted.get_decision(crashes[0])
    assert decision["run_id"] == prior
    assert restarted.forecast("XOM", "2024-08-01") == decision


def test_manufactured_missed_prediction_visible_only_after_reveal(demo):
    service = demo[2]
    decision = service.forecast("AAPL", "2024-08-02")
    assert decision["top_class"] == "DOWN"
    actual = service.reveal_outcome(decision["decision_id"])
    assert actual["label"] == "UP" and actual["prediction_correct"] is False


def test_exposure_limit_across_releases_and_cached_replay(demo):
    root, _, service, _, _, _ = demo
    first = service.forecast("AMZN", "2024-08-01")
    assert first["action"] == "PAPER_LONG"
    # A new policy release cannot create another position for the same company/date.
    release = deepcopy(service.release())
    release["notice"] += " exposure-test variant"
    changed = RawStore(root / "demo-releases").put(release)
    new_service = DemoService(root, release_hash=changed)
    repeated = new_service.forecast("AMZN", "2024-08-01")
    assert repeated["action"] == "ABSTAIN" and repeated["reason_codes"] == ["EXPOSURE_LIMIT"]
    assert service.forecast("AMZN", "2024-08-01") == first


def test_http_api_strict_inputs_health_and_separate_reveal(demo):
    client = TestClient(create_app(demo[0]))
    assert client.get("/health/live").status_code == 200
    assert client.get("/health/ready").json()["availability_tier"] == "FIXTURE"
    assert "outcome_hash" not in client.get("/catalog").text
    body = {"symbol": "WMT", "session": "2024-07-30"}
    response = client.post("/predict", json=body)
    assert response.status_code == 200
    decision = response.json()
    assert "label" not in response.text and "return_fraction" not in response.text
    assert client.post("/predict", json=body).json() == decision
    assert client.get(f"/decisions/{decision['decision_id']}").json() == decision
    assert client.post(f"/decisions/{decision['decision_id']}/reveal").json()["label"] == "UP"
    assert client.post("/predict", json={**body, "symbol": "MSFT"}).status_code == 422
    assert client.post("/predict", json={**body, "url": "http://unsafe"}).status_code == 422
    assert client.post("/predict", json={**body, "session": "2026-10-11"}).status_code == 409
    assert client.post("/predict", content="x" * 16385).status_code == 413
    assert client.get("/health/live", headers={"host": "evil.example"}).status_code == 400
    assert client.get("/orders").status_code == 404


def test_api_timeout_and_missing_release_are_not_ready(demo, tmp_path):
    client = TestClient(create_app(demo[0]))
    response = client.post(
        "/predict", json={"symbol": "AAPL", "session": "2024-07-31", "fault": "TIMEOUT"}
    )
    assert response.status_code == 202 and response.json()["action"] is None
    assert TestClient(create_app(tmp_path)).get("/health/ready").status_code == 503


def test_backup_restore_preserves_decisions_outcomes_and_receipts(demo, tmp_path):
    service = demo[2]
    decision = service.forecast("NVDA", "2024-08-01")
    outcome = service.reveal_outcome(decision["decision_id"])
    backup = tmp_path / "backup"
    result = backup_demo(demo[0], backup)
    target = tmp_path / "restored"
    restored = restore_demo(backup, target, result["manifest_hash"])
    assert restored["status"] == "RESTORE_VERIFIED"
    service2 = DemoService(target)
    assert service2.forecast("NVDA", "2024-08-01") == decision
    assert service2.reveal_outcome(decision["decision_id"]) == outcome
    assert not any(".env" in path.name for path in backup.rglob("*"))
    with pytest.raises(ValueError):
        backup_demo(demo[0], demo[0] / "recursive-backup")
    with pytest.raises(ValueError):
        restore_demo(backup, target, result["manifest_hash"])


def test_corrupted_backup_is_rejected_before_restore(demo, tmp_path):
    backup = tmp_path / "backup"
    result = backup_demo(demo[0], backup)
    # Alter just the content-addressed manifest reference, not user artifacts.
    manifest = RawStore(backup / "backup-manifests").get(result["manifest_hash"])
    manifest["files"][0]["sha256"] = "0" * 64
    broken = RawStore(backup / "backup-manifests").put(manifest)
    target = tmp_path / "restored"
    with pytest.raises(ValueError):
        restore_demo(backup, target, broken)
    assert not target.exists()


def test_dashboard_forecast_reveal_and_selector_reset(demo, monkeypatch):
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("MARKETPULSE_DEMO_DATA_DIR", str(demo[0]))
    ui = Path(__file__).parents[1] / "src" / "marketpulse" / "ui.py"
    app = AppTest.from_file(str(ui), default_timeout=30).run()
    assert not app.exception
    assert "outcome" not in app.session_state
    app.button[0].click().run()
    assert not app.exception and "decision" in app.session_state
    assert "outcome" not in app.session_state
    reveal = next(button for button in app.button if button.label == "Reveal outcome")
    reveal.click().run()
    assert not app.exception and "outcome" in app.session_state
    app.selectbox[1].select("NVDA").run()
    assert not app.exception and "outcome" not in app.session_state
