"""Loopback fixture service: bounded forecasts, append-only decisions and outcome reveal."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
from trailforge.ports import AdapterCapabilities, FunctionAdapter, VerifiedResult
from trailforge.runtime import Goal, Harness, Task

from marketpulse.baselines import CLASSES, _choose
from marketpulse.clock import session_window, utc_iso
from marketpulse.constants import STOCKS
from marketpulse.modeling import score_comparison, validate_comparison
from marketpulse.storage import RawStore, canonical_bytes, digest

_LOCKS: dict[str, threading.RLock] = {}
_LOCK_GUARD = threading.Lock()
SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS settings (name TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS runs (
  request_key TEXT PRIMARY KEY, run_id TEXT, binding_json TEXT NOT NULL, state TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS decisions (
  decision_id TEXT PRIMARY KEY, artifact_hash TEXT NOT NULL, session TEXT NOT NULL,
  symbol TEXT NOT NULL, action TEXT NOT NULL, latency_ms REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS revealed_outcomes (
  decision_id TEXT PRIMARY KEY, artifact_hash TEXT NOT NULL,
  FOREIGN KEY(decision_id) REFERENCES decisions(decision_id)
);
"""
FAULTS = {"NONE", "STALE", "MISSING_NEWS", "TIMEOUT", "EXPIRED", "LOW_CONFIDENCE"}


class DemoService:
    def __init__(self, data_dir: Path, *, release_hash: str | None = None):
        self.data_dir = data_dir.resolve()
        self.database = self.data_dir / "demo.sqlite3"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript(SCHEMA)
        with _LOCK_GUARD:
            self.lock = _LOCKS.setdefault(str(self.database), threading.RLock())
        self.release_hash = release_hash
        if release_hash is None:
            with self.connect() as db:
                row = db.execute(
                    "SELECT value FROM settings WHERE name='active_release'"
                ).fetchone()
            if row:
                self.release_hash = row[0]
        self.artifacts = RawStore(self.data_dir / "demo-artifacts")
        self.inputs = RawStore(self.data_dir / "demo-inputs")
        self.outcomes = RawStore(self.data_dir / "demo-outcomes")
        self.decisions = RawStore(self.data_dir / "demo-decisions")

    def connect(self):
        db = sqlite3.connect(self.database, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        return db

    def release(self) -> dict:
        if self.release_hash is None:
            raise ValueError("initialize the synthetic demo first")
        release = RawStore(self.data_dir / "demo-releases").get(self.release_hash)
        if (
            release.get("schema") != "full-fixture-demo/1"
            or release.get("availability_tier") != "FIXTURE"
        ):
            raise ValueError("this service does not admit real research artifacts")
        return release

    def register_release(self, key: str) -> None:
        if key != self.release_hash:
            raise ValueError("release binding mismatch")
        self.ready()
        with self.connect() as db:
            db.execute(
                "INSERT INTO settings VALUES ('active_release',?) ON CONFLICT(name) "
                "DO UPDATE SET value=excluded.value",
                (key,),
            )

    def ready(self) -> dict:
        release = self.release()
        model = self.artifacts.get(release["model_hash"])
        policy = self.artifacts.get(release["policy_hash"])
        validate_comparison(model)
        if (
            model["calibration_fitted"] is not True
            or policy.get("schema") != "fixture-policy/1"
            or policy.get("availability_tier") != "FIXTURE"
            or policy.get("real_paper_action_authorized") is not False
            or not 0 < policy["up_threshold"] <= 1
            or policy["max_positions_per_session"] != 2
        ):
            raise ValueError("incompatible policy or calibrator")
        return {
            "ready": True,
            "availability_tier": "FIXTURE",
            "release_hash": self.release_hash,
            "real_data_mode_available": False,
            "notice": release["notice"],
        }

    def catalog(self) -> list[dict]:
        return [
            {name: row[name] for name in ("symbol", "session", "split")}
            for row in self.release()["rows"]
            if row["split"] == "test"
        ]

    def _entry(self, symbol: str, session: str) -> dict:
        if symbol not in STOCKS:
            raise ValueError("ticker is outside the fixed six-stock universe")
        session_window(date.fromisoformat(session))
        entries = [
            row
            for row in self.release()["rows"]
            if row["symbol"] == symbol and row["session"] == session and row["split"] == "test"
        ]
        if len(entries) != 1:
            raise ValueError("session is outside the released synthetic replay catalog")
        return entries[0]

    def get_decision(self, decision_id: str) -> dict:
        with self.connect() as db:
            row = db.execute(
                "SELECT artifact_hash FROM decisions WHERE decision_id=?", (decision_id,)
            ).fetchone()
        if row is None:
            raise KeyError("decision not found")
        value = self.decisions.get(row[0])
        if value.get("decision_id") != decision_id:
            raise ValueError("decision record identity mismatch")
        return value

    def forecast(self, symbol: str, session: str, *, fault: str = "NONE") -> dict:
        if fault not in FAULTS:
            raise ValueError("unsupported local failure fixture")
        entry = self._entry(symbol, session)
        release = self.release()
        binding = {
            "schema": "fixture-forecast/1",
            "release_hash": self.release_hash,
            "symbol": symbol,
            "session": session,
            "input_hash": entry["input_hash"],
            "model_hash": release["model_hash"],
            "policy_hash": release["policy_hash"],
            "fault": fault,
            "availability_tier": "FIXTURE",
        }
        return self._forecast(binding)

    def _forecast(self, binding: dict) -> dict:
        key = digest(binding)
        with self.lock:
            try:
                return self.get_decision(key)
            except KeyError:
                pass
            self.ready()
            started = time.perf_counter()

            def score(request):
                if binding["fault"] == "TIMEOUT":
                    raise TimeoutError("injected synthetic model timeout")
                if binding["fault"] in {"STALE", "MISSING_NEWS"}:
                    return {
                        "quality": "BLOCKED",
                        "probabilities": None,
                        "reason": "STALE_DATA"
                        if binding["fault"] == "STALE"
                        else "NEWS_FEED_UNAVAILABLE",
                    }
                item = self.inputs.get(binding["input_hash"])
                features = item["features"]
                if (
                    features["symbol"] != binding["symbol"]
                    or features["session"] != binding["session"]
                ):
                    raise ValueError("snapshot/request mismatch")
                model = self.artifacts.get(binding["model_hash"])
                probs = score_comparison(model, item)["combined"]
                if binding["fault"] == "LOW_CONFIDENCE":
                    probs = [1 / 3] * 3
                return {
                    "quality": "VALID",
                    "probabilities": probs,
                    "feature_hash": features["feature_hash"],
                }

            def verify(request):
                try:
                    result = request.dependencies["score"]
                    if result != score(request):
                        raise ValueError("independent score replay differs")
                    return VerifiedResult(
                        "PASS",
                        request.goal_digest,
                        {
                            "availability_tier": "FIXTURE",
                            "input_hash": binding["input_hash"],
                            "quality": result["quality"],
                        },
                    )
                except (KeyError, TypeError, ValueError):
                    return VerifiedResult("FAIL", request.goal_digest, {"reason": "score_invalid"})
                except OSError:
                    return VerifiedResult(
                        "UNKNOWN", request.goal_digest, {"reason": "artifact_unavailable"}
                    )

            adapters = [
                FunctionAdapter(
                    AdapterCapabilities("marketpulse.fixture_score/1", "MODEL", "PURE"), score
                ),
                FunctionAdapter(
                    AdapterCapabilities("marketpulse.fixture_verify/1", "VERIFY", "PURE"), verify
                ),
            ]
            goal = Goal(
                "local-demo",
                f"marketpulse:forecast:{key}",
                "Verify one synthetic pre-open forecast without outcome access",
                (
                    Task("score", "marketpulse.fixture_score/1", binding),
                    Task("verify", "marketpulse.fixture_verify/1", binding, ("score",)),
                ),
                ("verify",),
                allowed_effects=("PURE",),
                budget_units=4,
            )
            harness = Harness(
                self.data_dir / "forecast-trailforge.sqlite3",
                tenant_id=goal.tenant_id,
                resource_id=goal.resource_id,
                adapters=adapters,
                lease_seconds=180,
                tenant_limit=100000,
                global_limit=1000000,
            )
            with self.connect() as db:
                db.execute(
                    "INSERT OR IGNORE INTO runs VALUES (?,NULL,?,'PENDING')",
                    (key, canonical_bytes(binding).decode()),
                )
                prior = db.execute("SELECT * FROM runs WHERE request_key=?", (key,)).fetchone()
            run_id = prior["run_id"] or harness.start(goal)
            with self.connect() as db:
                db.execute(
                    "UPDATE runs SET run_id=? WHERE request_key=? AND run_id IS NULL", (run_id, key)
                )
            record = harness.advance(run_id, goal)
            with self.connect() as db:
                db.execute("UPDATE runs SET state=? WHERE request_key=?", (record["state"], key))
            if record["state"] != "COMPLETED":
                return {
                    "state": record["state"],
                    "run_id": run_id,
                    "request_key": key,
                    "availability_tier": "FIXTURE",
                    "action": None,
                    "notice": "Held work; no accepted decision or simulated position",
                }
            self._after_verified(key)  # Fault-injection seam for cross-store recovery tests.
            result = record["tasks"]["score"]["result"]
            policy = self.artifacts.get(binding["policy_hash"])
            window = session_window(date.fromisoformat(binding["session"]))
            action, reasons = "ABSTAIN", ["LOW_CONFIDENCE"]
            if result["quality"] == "BLOCKED":
                action, reasons = "BLOCKED", [result["reason"]]
            elif binding["fault"] == "EXPIRED":
                action, reasons = "BLOCKED", ["SIGNAL_EXPIRED"]
            elif (
                policy["fixture_long_enabled"]
                and _choose(result["probabilities"]) == "UP"
                and result["probabilities"][CLASSES.index("UP")] >= policy["up_threshold"]
            ):
                action, reasons = "PAPER_LONG", ["FIXTURE_SIMULATION_ONLY"]
            latency_ms = (time.perf_counter() - started) * 1000
            with self.connect() as db:
                db.execute("BEGIN IMMEDIATE")
                existing = db.execute(
                    "SELECT artifact_hash FROM decisions WHERE decision_id=?", (key,)
                ).fetchone()
                if existing:
                    return self.decisions.get(existing[0])
                if action == "PAPER_LONG":
                    positions = db.execute(
                        "SELECT COUNT(DISTINCT symbol) FROM decisions WHERE "
                        "session=? AND action='PAPER_LONG'",
                        (binding["session"],),
                    ).fetchone()[0]
                    already = db.execute(
                        "SELECT 1 FROM decisions WHERE session=? AND symbol=? "
                        "AND action='PAPER_LONG'",
                        (binding["session"], binding["symbol"]),
                    ).fetchone()
                    if already or positions >= policy["max_positions_per_session"]:
                        action, reasons = "ABSTAIN", ["EXPOSURE_LIMIT"]
                decision = {
                    "decision_id": key,
                    "state": "COMPLETE",
                    "binding": binding,
                    "symbol": binding["symbol"],
                    "session": binding["session"],
                    "availability_tier": "FIXTURE",
                    "cutoff_utc": utc_iso(window.cutoff),
                    "expires_at_utc": utc_iso(window.market_open),
                    "created_at_utc": utc_iso(datetime.now(timezone.utc)),
                    "clock_mode": "HISTORICAL_FIXTURE_REPLAY_AT_CUTOFF",
                    "class_names": list(CLASSES),
                    "probabilities": result["probabilities"],
                    "top_class": _choose(result["probabilities"])
                    if result["probabilities"]
                    else None,
                    "action": action,
                    "reason_codes": reasons,
                    "feature_hash": result.get("feature_hash"),
                    "run_id": run_id,
                    "verify_receipt": record["tasks"]["verify"]["receipt"]["receipt_id"],
                    "latency_ms": latency_ms,
                    "simulation_only": True,
                    "real_paper_action_authorized": False,
                    "notice": "Manufactured inputs/model; NOT investment advice",
                }
                artifact_hash = self.decisions.put(decision)
                db.execute(
                    "INSERT INTO decisions VALUES (?,?,?,?,?,?)",
                    (key, artifact_hash, binding["session"], binding["symbol"], action, latency_ms),
                )
            return decision

    def _after_verified(self, request_key: str) -> None:
        pass

    def reconcile(self) -> dict:
        with self.connect() as db:
            pending = [
                dict(row)
                for row in db.execute(
                    "SELECT r.* FROM runs r LEFT JOIN decisions d "
                    "ON r.request_key=d.decision_id WHERE d.decision_id IS NULL"
                )
            ]
        results = [
            self._forecast(json.loads(row["binding_json"])) for row in pending if row["run_id"]
        ]
        return {
            "checked_known_runs": len(results),
            "materialized": sum(item["state"] == "COMPLETE" for item in results),
            "held": sum(item["state"] != "COMPLETE" for item in results),
            "orphan_start_window_still_possible": True,
        }

    def reveal_outcome(self, decision_id: str) -> dict:
        decision = self.get_decision(decision_id)
        window = session_window(date.fromisoformat(decision["session"]))
        if datetime.now(timezone.utc) <= window.market_close:
            raise ValueError("outcome cannot be revealed before session close")
        # Resolve from the ORIGINAL release, not a newly active model/catalog.
        release = RawStore(self.data_dir / "demo-releases").get(decision["binding"]["release_hash"])
        entry = next(
            row
            for row in release["rows"]
            if row["symbol"] == decision["symbol"] and row["session"] == decision["session"]
        )
        outcome = self.outcomes.get(entry["outcome_hash"])
        with self.connect() as db:
            prior = db.execute(
                "SELECT artifact_hash FROM revealed_outcomes WHERE decision_id=?", (decision_id,)
            ).fetchone()
            if prior and prior[0] != entry["outcome_hash"]:
                raise ValueError("outcome conflict")
            db.execute(
                "INSERT OR IGNORE INTO revealed_outcomes VALUES (?,?)",
                (decision_id, entry["outcome_hash"]),
            )
        return {
            "decision_id": decision_id,
            **outcome,
            "prediction_correct": decision["top_class"] == outcome["label"],
        }

    def evaluation(self) -> dict:
        release = self.release()
        return {
            "validation": self.artifacts.get(release["validation_report_hash"]),
            "test": self.artifacts.get(release["test_report_hash"]),
            "notice": release["notice"],
        }

    def operations(self) -> dict:
        with self.connect() as db:
            decisions = [dict(row) for row in db.execute("SELECT * FROM decisions")]
            runs = [dict(row) for row in db.execute("SELECT request_key,run_id,state FROM runs")]
        latencies = [row["latency_ms"] for row in decisions]
        return {
            "availability_tier": "FIXTURE",
            "decisions": len(decisions),
            "runs": runs,
            "actions": {
                name: sum(row["action"] == name for row in decisions)
                for name in ("PAPER_LONG", "ABSTAIN", "BLOCKED")
            },
            "latency_ms_p50": float(np.quantile(latencies, 0.5)) if latencies else None,
            "latency_ms_p95": float(np.quantile(latencies, 0.95)) if latencies else None,
            "positions_are_simulated": True,
            "real_order_adapter_present": False,
        }
