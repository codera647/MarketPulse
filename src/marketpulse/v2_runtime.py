"""Separate private v2 artifact authority; never resets v1 or UNKNOWN work."""

from __future__ import annotations

import hashlib
import json
import os
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from trailforge.ports import AdapterCapabilities, FunctionAdapter, VerifiedResult
from trailforge.runtime import Goal, Harness, Task

from marketpulse.storage import ExtractionStore, RawStore, canonical_bytes, digest

SCHEMA = "enriched-weighted-research/2"


@contextmanager
def system_awake(request=None):
    """Temporary Windows idle-sleep request; no display or power-plan changes."""
    if request is None:
        if os.name != "nt":
            yield False
            return
        import ctypes

        request = ctypes.WinDLL("kernel32", use_last_error=True).SetThreadExecutionState
        request.argtypes = [ctypes.c_uint]
        request.restype = ctypes.c_uint
    previous = request(0x80000001)  # ES_CONTINUOUS | ES_SYSTEM_REQUIRED, never DISPLAY/AWAYMODE
    if not previous:
        raise OSError("temporary Windows idle-sleep request refused")
    try:
        yield True
    finally:
        if not request(previous | 0x80000000):
            raise OSError("temporary Windows idle-sleep request restoration failed")


def reconciliation_store(root: Path):
    store = ExtractionStore(root / "v2-jobs.sqlite3")
    with store.connect() as db:
        db.execute(
            "CREATE TABLE IF NOT EXISTS v2_capture_reconciliations ("
            "parent_job_key TEXT PRIMARY KEY, result_json TEXT NOT NULL)"
        )
    return store


def retained_expired(root: Path, parent_key: str, stage: str) -> tuple[dict, dict, dict]:
    """Retain an expired original attempt without invoking either original adapter."""
    if stage not in {"context", "sentiment"}:
        raise ValueError("unsupported capture reconciliation stage")
    job = ExtractionStore(root / "v2-jobs.sqlite3").get_job(parent_key)
    if not job or not job["run_id"]:
        raise ValueError("original capture task missing")
    harness = Harness(
        root / "v2-trailforge.sqlite3",
        tenant_id="local-demo",
        resource_id=f"marketpulse:v2:{parent_key}",
        adapters=[],
        tenant_limit=1000000,
        global_limit=10000000,
    )
    record = harness.inspect(job["run_id"])
    binding = record["goal"]["tasks"][0]["input"]
    if (
        record["goal"]["tasks"][0]["adapter_id"] != f"marketpulse.v2_{stage}/2"
        or binding.get("environment") != environment()
        or digest({"stage": stage, "binding": binding}) != parent_key
    ):
        raise ValueError("capture scope/version differs from original task")
    original = {k: v for k, v in binding.items() if k != "environment"}
    if record["state"] == "RUNNING":
        if not record["active"] or record["active"]["expires_at"] >= time.time():
            raise ValueError("original capture is not an expired active attempt")

        def forbidden(*args):
            raise AssertionError("original capture effect must never be repeated")

        try:
            supervised(root, stage, original, forbidden, forbidden)
        except ValueError:
            pass
        record = harness.inspect(job["run_id"])
    if (
        record["state"] != "WAITING_HUMAN"
        or record["active"] is not None
        or not any(
            task["status"] == "UNKNOWN" and task["error_code"] == "EXPIRED_ATTEMPT"
            for task in record["tasks"].values()
        )
    ):
        raise ValueError("original capture is not a retained expired UNKNOWN")
    return job, record, original


def environment() -> dict:
    result = {}
    for name in ("numpy", "scikit-learn", "catboost", "transformers", "torch"):
        try:
            result[name] = version(name)
        except PackageNotFoundError:
            result[name] = None
    return result


class Artifacts(RawStore):
    def put_binary(self, content: bytes, suffix: str) -> str:
        if suffix not in {".cbm"}:
            raise ValueError("unsupported private model type")
        key = hashlib.sha256(content).hexdigest()
        path = self.root / key[:2] / (key + suffix)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with path.open("xb") as handle:
                handle.write(content)
        except FileExistsError:
            if path.read_bytes() != content:
                raise ValueError("binary artifact mismatch") from None
        return key

    def binary_path(self, key: str) -> Path:
        if len(key) != 64 or any(c not in "0123456789abcdef" for c in key):
            raise ValueError("invalid model digest")
        path = self.root / key[:2] / (key + ".cbm")
        if hashlib.sha256(path.read_bytes()).hexdigest() != key:
            raise ValueError("model binary digest mismatch")
        return path


def supervised(root: Path, stage: str, binding: dict, execute, verify, *, lease=300) -> dict:
    """Small digest-bound task messages and explicit typed independent verification."""
    binding = {**binding, "environment": environment()}
    key = digest({"stage": stage, "binding": binding})
    store = ExtractionStore(root / "v2-jobs.sqlite3")
    store.reserve_job(key, "HISTORICAL_APPROXIMATE")
    names = (f"marketpulse.v2_{stage}/2", f"marketpulse.v2_{stage}_verify/2")

    def check(request):
        try:
            verify(request.dependencies["execute"])
            return VerifiedResult(
                "PASS",
                request.goal_digest,
                {"binding_hash": digest(binding), "paper_action_authorized": False},
            )
        except (ValueError, KeyError, TypeError, AssertionError):
            return VerifiedResult("FAIL", request.goal_digest, {"reason": "v2_replay_failed"})
        except OSError:
            return VerifiedResult("UNKNOWN", request.goal_digest, {"reason": "v2_artifact_missing"})

    adapters = [
        FunctionAdapter(
            AdapterCapabilities(names[0], "TOOL", "CANDIDATE_WRITE"), lambda request: execute()
        ),
        FunctionAdapter(AdapterCapabilities(names[1], "VERIFY", "PURE"), check),
    ]
    goal = Goal(
        "local-demo",
        f"marketpulse:v2:{key}",
        "Verify bounded private v2 research work",
        (Task("execute", names[0], binding), Task("verify", names[1], binding, ("execute",))),
        ("verify",),
        allowed_effects=("PURE", "CANDIDATE_WRITE"),
        budget_units=4,
    )
    harness = Harness(
        root / "v2-trailforge.sqlite3",
        tenant_id=goal.tenant_id,
        resource_id=goal.resource_id,
        adapters=adapters,
        lease_seconds=lease,
        tenant_limit=1000000,
        global_limit=10000000,
    )
    prior = store.get_job(key)
    if prior["run_id"] is None:
        store.set_run_id(key, harness.start(goal))
    run_id = store.get_job(key)["run_id"]
    record = harness.advance(run_id, goal)
    if record["state"] != "COMPLETED":
        store.set_status(key, record["state"])
        raise ValueError(f"v2 {stage} held in {record['state']}; authority was not reset")
    result = {
        **record["tasks"]["execute"]["result"],
        "run_id": run_id,
        "job_key": key,
        "binding_hash": digest(binding),
        "verify_receipt": record["tasks"]["verify"]["receipt"]["receipt_id"],
    }
    with store.connect() as db:
        db.execute(
            "UPDATE extraction_jobs SET status='COMPLETE',manifest_json=? WHERE job_key=?",
            (canonical_bytes(result).decode(), key),
        )
    return result


def check_receipt(root: Path, result: dict) -> None:
    with ExtractionStore(root / "v2-jobs.sqlite3").connect() as db:
        job = db.execute(
            "SELECT * FROM extraction_jobs WHERE job_key=?", (result["job_key"],)
        ).fetchone()
    if not job or job["status"] != "COMPLETE" or json.loads(job["manifest_json"]) != result:
        raise ValueError("v2 application receipt mismatch")
    harness = Harness(
        root / "v2-trailforge.sqlite3",
        tenant_id="local-demo",
        resource_id=f"marketpulse:v2:{result['job_key']}",
        adapters=[],
        tenant_limit=1000000,
        global_limit=10000000,
    )
    record = harness.inspect(result["run_id"])
    if (
        record["state"] != "COMPLETED"
        or result["binding_hash"] != digest(record["goal"]["tasks"][0]["input"])
        or record["tasks"]["verify"]["result"]["verdict"] != "PASS"
        or record["tasks"]["verify"]["receipt"]["receipt_id"] != result["verify_receipt"]
        or any(result.get(k) != v for k, v in record["tasks"]["execute"]["result"].items())
    ):
        raise ValueError("v2 native verification mismatch")


@contextmanager
def owned_run(root: Path, binding: dict, progress=None):
    root.mkdir(parents=True, exist_ok=True)
    lock = root / "v2-build.lock"
    owner = {"pid": os.getpid(), "binding_hash": digest(binding)}
    with lock.open("x", encoding="utf-8") as handle:
        json.dump(owner, handle)
    guard_enabled = False

    def checkpoint(event):
        value = {
            "schema": SCHEMA,
            **owner,
            "host_idle_sleep_guard_enabled": guard_enabled,
            "updated_at_utc": datetime.now(timezone.utc).isoformat(),
            **event,
        }
        pending = root / "v2-status.tmp"
        pending.write_text(json.dumps(value, indent=2), encoding="utf-8")
        # Windows readers may briefly deny FILE_SHARE_DELETE. Retain the last
        # complete JSON and retry only this atomic status rename, never work.
        for attempt in range(40):
            try:
                pending.replace(root / "v2-status.json")
                break
            except PermissionError:
                if attempt == 39:
                    raise
                time.sleep(0.05)
        if progress:
            progress(value)

    try:
        with system_awake() as guard_enabled:
            checkpoint({"stage": "STARTING", "final_test_completed": False})
            yield checkpoint
    except Exception as error:
        checkpoint(
            {"stage": "STOPPED", "error_type": type(error).__name__, "authority_reset": False}
        )
        raise
    finally:
        if json.loads(lock.read_text(encoding="utf-8")) == owner:
            lock.unlink()
