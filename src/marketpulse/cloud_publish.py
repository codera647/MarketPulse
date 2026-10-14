"""Publish verified retrospective research, never pretend it is live inference."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from dotenv import dotenv_values

from marketpulse.cloud_state import CloudState, sqlite_checkpoint
from marketpulse.dashboard_data import MODEL_NAMES, REPORTS, load_research
from marketpulse.storage import RawStore, canonical_bytes, digest
from marketpulse.v2_runtime import check_receipt, supervised


def projection(data_parent: Path, period: str) -> dict:
    view = load_research(data_parent, period)
    return {
        "schema": "marketpulse-cloud-projection/1", "kind": "research", "period": period,
        "report_hash": view.report_hash,
        "release_hash": view.prediction(0, "price")["release_hash"],
        "availability_tier": "HISTORICAL_APPROXIMATE", "live": False,
        "paper_action_authorized": False, "deployment_promoted": False,
        "native_receipt": view.receipt, "model_names": MODEL_NAMES,
        "classes": ["DOWN", "NO_MATERIAL_MOVE", "UP"],
        "target": "regular-minute-proxy/1", "threshold": 0.01,
        "metrics": view.report["metrics"], "rows": view.rows.to_dict("records"),
        "probabilities": {key: matrix.tolist() for key, matrix in view.probabilities.items()},
    }


def publish(values, data_parent: Path, root: Path, period: str):
    payload = projection(data_parent, period)
    payload_hash = digest(payload)
    state = CloudState(values)
    key = f"bootstrap:{payload_hash}"
    try:
        owner = state.claim(key, "bootstrap")
        if owner is None:
            return {"status": "ALREADY_COMPLETE", "period": period}
        artifacts = RawStore(root / "artifacts")

        def verify(result):
            if artifacts.get(result["projection_hash"]) != projection(data_parent, period):
                raise ValueError("independent verified research projection differs")

        receipt = supervised(
            root, "cloud_research_projection", {"report_hash": payload["report_hash"]},
            lambda: {"projection_hash": artifacts.put(payload)}, verify,
        )
        check_receipt(root, receipt)
        # Persist native authority as separate verified objects; no tar/pickle deserialization.
        checkpoint = {
            "schema": "marketpulse-cloud-native-checkpoint/1", "receipt": receipt,
            "native_db": state.put(sqlite_checkpoint(root / "v2-trailforge.sqlite3"), "checkpoint"),
            "application_db": state.put(sqlite_checkpoint(root / "v2-jobs.sqlite3"), "checkpoint"),
        }
        source_root = data_parent / REPORTS[period][0]
        checkpoint["research_native_db"] = state.put(
            sqlite_checkpoint(source_root / "v2-trailforge.sqlite3"), "checkpoint"
        )
        checkpoint["research_application_db"] = state.put(
            sqlite_checkpoint(source_root / "v2-jobs.sqlite3"), "checkpoint"
        )
        checkpoint_hash = state.put(canonical_bytes(checkpoint), "checkpoint")
        state.checkpoint(key, owner, checkpoint_hash)
        result_hash = state.put(canonical_bytes(payload), "projection")
        state.complete(key, owner, checkpoint_hash, result_hash,
                       projection_id=f"research:{period[:4]}:{payload_hash}", payload=payload)
        return {"status": "PASS", "period": period, "rows": len(payload["rows"]),
                "projection_hash": result_hash, "native_checkpoint_hash": checkpoint_hash,
                "live": False, "schedules_enabled": False}
    finally:
        state.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path(".env.cloud.local"))
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--root", type=Path, default=Path("data/cloud-bootstrap"))
    parser.add_argument("--period", choices=REPORTS, required=True)
    args = parser.parse_args(argv)
    try:
        result = publish(dotenv_values(args.env_file, interpolate=False),
                         args.data, args.root, args.period)
    except Exception as error:
        print(json.dumps({"status": "FAIL", "error_type": type(error).__name__,
                          "detail": "Publication held; private details suppressed."}))
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
