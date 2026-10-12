"""Software orchestration checks, not empirical training evidence."""

import json
from types import SimpleNamespace

import pytest

from marketpulse import real_build


@pytest.mark.parametrize("status", ["BATCH_BLOCKED", "INTEGRITY_BLOCKED", "INCOMPLETE"])
def test_real_build_never_fits_a_blocked_or_incomplete_collection(tmp_path, monkeypatch, status):
    from test_dataset import contract

    pipeline = SimpleNamespace(data_dir=tmp_path, client=SimpleNamespace())
    monkeypatch.setattr(real_build, "collect_dataset", lambda *a, **k: {
        "status": status, "accepted_rows": 0, "contract_hash": "a" * 64,
        "report_hash": "b" * 64})

    def forbidden(*args, **kwargs):
        raise AssertionError("fitting was attempted on incomplete data")

    monkeypatch.setattr(real_build, "train_real_models", forbidden)
    result = real_build.build_real_research(pipeline, contract(), evidence="Synthetic authority",
                                           cycles=1)
    assert result["state"] in {"BLOCKED", "BUDGET_STOP"}
    assert result["training_started"] is False
    saved = json.loads((tmp_path / "real-build-status.json").read_text())
    assert saved["training_started"] is False


def test_real_build_binds_explicit_authority_to_completed_report(tmp_path, monkeypatch):
    from test_dataset import contract

    pipeline = SimpleNamespace(data_dir=tmp_path, client=SimpleNamespace())
    report = {"status": "COMPLETE_RESEARCH_REVIEW_REQUIRED", "accepted_rows": 18,
              "contract_hash": "a" * 64, "report_hash": "b" * 64}
    monkeypatch.setattr(real_build, "collect_dataset", lambda *a, **k: report)
    received = []

    def fit(root, value, authority):
        received.append(authority)
        return {"state": "COMPLETE", "release_hash": "c" * 64}

    monkeypatch.setattr(real_build, "train_real_models", fit)
    result = real_build.build_real_research(pipeline, contract(), evidence="Synthetic authority")
    assert result["state"] == "COMPLETE"
    assert received[0]["report_hash"] == report["report_hash"]
    assert received[0]["evidence"] == "Synthetic authority"
    assert "reviewer" not in received[0]


def test_unexpected_collection_error_is_recorded_without_payload(tmp_path, monkeypatch):
    from test_dataset import contract

    pipeline = SimpleNamespace(data_dir=tmp_path, client=SimpleNamespace())

    def unavailable(*args, **kwargs):
        raise OSError("private provider details must not appear in status")

    monkeypatch.setattr(real_build, "collect_dataset", unavailable)
    result = real_build.build_real_research(pipeline, contract(), evidence="Synthetic authority")
    assert result["state"] == "STOPPED" and result["error_type"] == "OSError"
    assert result["authority_reset"] is False
    assert "private provider details" not in (tmp_path / "real-build-status.json").read_text()


def test_training_resume_preserves_error_evidence_and_never_recollects(tmp_path, monkeypatch):
    from test_dataset import contract

    from marketpulse.storage import RawStore

    previous = {"stage": "TRAINING_ERROR", "error_type": "ContractError",
                "collection": {"contract_hash": "a" * 64, "report_hash": "b" * 64}}
    (tmp_path / "real-build-status.json").write_text(json.dumps(previous), encoding="utf-8")
    authorization = {"contract_hash": "a" * 64, "report_hash": "b" * 64}

    def forbidden(*args, **kwargs):
        raise AssertionError("resume must not recollect data")

    def fit(root, value, authority, *, progress):
        progress({"phase": "FITTING_MODELS", "train_rows": 100})
        return {"state": "COMPLETE", "release_hash": "c" * 64}

    monkeypatch.setattr(real_build, "collect_dataset", forbidden)
    monkeypatch.setattr(real_build, "train_real_models", fit)
    events = []
    result = real_build.resume_real_training(tmp_path, contract(), authorization,
                                             progress=events.append)
    assert result["state"] == "COMPLETE"
    assert events[0]["phase"] == "VERIFYING_SAVED_DATA"
    assert events[-1]["stage"] == "COMPLETE"
    resume = RawStore(tmp_path / "build-runs").get(events[0]["resume_intent_hash"])
    assert RawStore(tmp_path / "build-runs").get(resume["previous_status_hash"]) == previous
    assert resume["authority_reset"] is False
    assert not (tmp_path / "research-training-resume.lock").exists()


def test_training_resume_refuses_active_builder_or_lock(tmp_path, monkeypatch):
    from test_dataset import contract

    authorization = {"contract_hash": "a" * 64, "report_hash": "b" * 64}
    status = tmp_path / "real-build-status.json"
    status.write_text(json.dumps({"stage": "TRAINING"}), encoding="utf-8")
    with pytest.raises(ValueError, match="active"):
        real_build.resume_real_training(tmp_path, contract(), authorization)
    status.write_text(json.dumps({"stage": "TRAINING_ERROR"}), encoding="utf-8")
    lock = tmp_path / "research-training-resume.lock"
    lock.write_text("other owner", encoding="utf-8")
    with pytest.raises(FileExistsError):
        real_build.resume_real_training(tmp_path, contract(), authorization)
    assert lock.read_text() == "other owner"
