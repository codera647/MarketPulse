"""Quiesced, credential-free fixture backups with integrity-checked restore drills."""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from pathlib import Path

from marketpulse.service import DemoService
from marketpulse.storage import RawStore

STORES = ("demo-artifacts", "demo-inputs", "demo-outcomes", "demo-decisions", "demo-releases")
DATABASES = (
    "demo.sqlite3",
    "demo-build-trailforge.sqlite3",
    "demo-build-jobs.sqlite3",
    "forecast-trailforge.sqlite3",
)


def _fresh_destination(source: Path, destination: Path) -> tuple[Path, Path]:
    source, destination = source.resolve(), destination.resolve()
    if (
        destination.exists()
        or source == destination
        or source in destination.parents
        or destination in source.parents
        or destination.parent == destination
    ):
        raise ValueError("destination must be new and outside the source tree")
    return source, destination


def _hash_file(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def backup_demo(data_dir: Path, destination: Path) -> dict:
    source, destination = _fresh_destination(data_dir, destination)
    service = DemoService(source)
    service.ready()
    # Quiesce API/UI and any other processes first: this lock covers this process only.
    with service.lock:
        destination.mkdir(parents=True)
        for name in STORES:
            root = source / name
            if root.exists():
                for path in root.rglob("*.json"):
                    if path.is_symlink():
                        raise ValueError("symbolic-link artifacts are not backed up")
                    RawStore(root).get(path.stem)
                    target = destination / path.relative_to(source)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(path, target)
        for name in DATABASES:
            path = source / name
            if path.exists():
                with sqlite3.connect(path) as src, sqlite3.connect(destination / name) as dst:
                    src.backup(dst)
        files = sorted(path for path in destination.rglob("*") if path.is_file())
        manifest = {
            "schema": "fixture-backup/1",
            "availability_tier": "FIXTURE",
            "release_hash": service.release_hash,
            "cross_process_quiescence_required": True,
            "files": [
                {"path": path.relative_to(destination).as_posix(), "sha256": _hash_file(path)}
                for path in files
            ],
        }
        key = RawStore(destination / "backup-manifests").put(manifest)
    return {"manifest_hash": key, "files": len(files), "availability_tier": "FIXTURE"}


def restore_demo(backup_dir: Path, destination: Path, manifest_hash: str) -> dict:
    source, destination = _fresh_destination(backup_dir, destination)
    manifest = RawStore(source / "backup-manifests").get(manifest_hash)
    if (
        manifest.get("schema") != "fixture-backup/1"
        or manifest.get("availability_tier") != "FIXTURE"
    ):
        raise ValueError("incompatible backup manifest")
    paths = []
    for item in manifest["files"]:
        relative = Path(item["path"])
        path = (source / relative).resolve()
        if (
            relative.is_absolute()
            or source not in path.parents
            or path.is_symlink()
            or ".." in relative.parts
            or _hash_file(path) != item["sha256"]
            or not (relative.parts[0] in STORES or relative.as_posix() in DATABASES)
        ):
            raise ValueError("unsafe or corrupted backup entry")
        paths.append((path, relative))
    destination.mkdir(parents=True)
    for path, relative in paths:
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    service = DemoService(destination)
    service.ready()
    if service.release_hash != manifest["release_hash"]:
        raise ValueError("restored release differs")
    with service.connect() as db:
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("restored product database integrity failure")
        decisions = [dict(row) for row in db.execute("SELECT * FROM decisions")]
        outcomes = [dict(row) for row in db.execute("SELECT * FROM revealed_outcomes")]
    for row in decisions:
        decision = service.get_decision(row["decision_id"])
        if json.loads(json.dumps(decision))["simulation_only"] is not True:
            raise ValueError("unexpected real decision in fixture backup")
    for row in outcomes:
        service.outcomes.get(row["artifact_hash"])
    return {
        "status": "RESTORE_VERIFIED",
        "availability_tier": "FIXTURE",
        "release_hash": service.release_hash,
        "decisions": len(decisions),
        "revealed_outcomes": len(outcomes),
    }
