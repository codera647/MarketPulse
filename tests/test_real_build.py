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
