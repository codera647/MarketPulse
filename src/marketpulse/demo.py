"""Finite, credential-free full demo build under Trailforge; never a real-data release."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from trailforge.ports import AdapterCapabilities, FunctionAdapter, VerifiedResult
from trailforge.runtime import Goal, Harness, Task

from marketpulse.baseline_fixtures import generate_fixture_catalog
from marketpulse.baselines import CLASSES, selected_rows
from marketpulse.clock import utc_iso
from marketpulse.modeling import (
    MODEL_SCHEMA,
    calibrate,
    evaluate_comparison,
    fit_comparison,
    score_comparison,
)
from marketpulse.storage import ExtractionStore, RawStore, canonical_bytes, digest

DEMO_VERSION = "full-fixture-demo/1"


def select_policy(model: dict, rows: list[dict]) -> dict:
    used = set(model["training_row_hashes"])
    used.update(model["calibrators"]["combined"]["row_hashes"])
    if (
        not rows
        or any(row["split"] != "validation" for row in rows)
        or used & {row["row_hash"] for row in rows}
    ):
        raise ValueError("policy selection requires separate held-out validation rows")
    scores = [score_comparison(model, row)["combined"] for row in rows]
    candidates = []
    for threshold in (0.5, 0.65, 0.8, 0.95):
        selected = [
            row
            for row, prob in zip(rows, scores)
            if prob[CLASSES.index("UP")] >= threshold and max(prob) == prob[CLASSES.index("UP")]
        ]
        correct = sum(row["label"] == "UP" for row in selected)
        precision = correct / len(selected) if selected else 0.0
        candidates.append(
            {"threshold": threshold, "selected": len(selected), "precision": precision}
        )
    eligible = [item for item in candidates if item["selected"] >= 2 and item["precision"] >= 0.75]
    chosen = min(eligible, key=lambda item: item["threshold"]) if eligible else None
    return {
        "schema": "fixture-policy/1",
        "availability_tier": "FIXTURE",
        "up_threshold": chosen["threshold"] if chosen else 1.0,
        "fixture_long_enabled": chosen is not None,
        "max_positions_per_session": 2,
        "selected_on_row_hashes": [row["row_hash"] for row in rows],
        "candidate_results": candidates,
        "real_paper_action_authorized": False,
        "notice": "Fixture simulation policy, NOT a validated market policy",
    }


def run_full_demo(data_dir: Path, *, seed: int = 42) -> dict:
    from importlib.metadata import version

    artifacts = RawStore(data_dir / "demo-artifacts")
    catalog_hash = generate_fixture_catalog(artifacts, seed=seed, with_news=True)
    train, validation = selected_rows(artifacts, catalog_hash)
    dates = sorted({row["session"] for row in validation})
    calibration = [row for row in validation if row["session"] in dates[:2]]
    selection = [row for row in validation if row["session"] in dates[2:]]
    if not calibration or not selection:
        raise ValueError("separate calibration and policy dates required")
    binding = {
        "schema": DEMO_VERSION,
        "catalog_hash": catalog_hash,
        "model_schema": MODEL_SCHEMA,
        "sklearn_version": version("scikit-learn"),
        "numpy_version": version("numpy"),
        "availability_tier": "FIXTURE",
    }
    key = digest(binding)

    def fit(request):
        model = calibrate(fit_comparison(train), calibration)
        policy = select_policy(model, selection)
        return {"model_hash": artifacts.put(model), "policy_hash": artifacts.put(policy)}

    def verify(request):
        try:
            model = artifacts.get(request.dependencies["fit"]["model_hash"])
            policy = artifacts.get(request.dependencies["fit"]["policy_hash"])
            if model != calibrate(fit_comparison(train), calibration) or policy != select_policy(
                model, selection
            ):
                raise ValueError("candidate replay differs")
            return VerifiedResult(
                "PASS",
                request.goal_digest,
                {
                    "data_mode": "FIXTURE",
                    "test_opened_during_fit": False,
                    "train_rows": len(train),
                    "calibration_rows": len(calibration),
                    "policy_rows": len(selection),
                },
            )
        except (KeyError, TypeError, ValueError):
            return VerifiedResult("FAIL", request.goal_digest, {"reason": "candidate_invalid"})
        except OSError:
            return VerifiedResult(
                "UNKNOWN", request.goal_digest, {"reason": "artifact_unavailable"}
            )

    adapters = [
        FunctionAdapter(
            AdapterCapabilities("marketpulse.demo_fit/1", "MODEL", "CANDIDATE_WRITE"), fit
        ),
        FunctionAdapter(AdapterCapabilities("marketpulse.demo_verify/1", "VERIFY", "PURE"), verify),
    ]
    goal = Goal(
        "local-demo",
        f"marketpulse:demo_build:{key}",
        "Verify synthetic four-model software, separated calibration and policy dates",
        (
            Task("fit", "marketpulse.demo_fit/1", binding),
            Task("verify", "marketpulse.demo_verify/1", binding, ("fit",)),
        ),
        ("verify",),
        allowed_effects=("PURE", "CANDIDATE_WRITE"),
        budget_units=6,
    )
    harness = Harness(
        data_dir / "demo-build-trailforge.sqlite3",
        tenant_id=goal.tenant_id,
        resource_id=goal.resource_id,
        adapters=adapters,
        lease_seconds=180,
        tenant_limit=100000,
        global_limit=1000000,
    )
    index = ExtractionStore(data_dir / "demo-build-jobs.sqlite3")
    index.reserve_job(key, "FIXTURE")
    prior = index.get_job(key)
    run_id = prior["run_id"] or harness.start(goal)
    if not prior["run_id"]:
        index.set_run_id(key, run_id)
    record = harness.advance(run_id, goal)
    if record["state"] != "COMPLETED":
        index.set_status(key, record["state"])
        return {"state": record["state"], "run_id": run_id, "availability_tier": "FIXTURE"}
    fit_result = record["tasks"]["fit"]["result"]
    model, policy = (artifacts.get(fit_result[name]) for name in ("model_hash", "policy_hash"))
    if model != calibrate(fit_comparison(train), calibration) or policy != select_policy(
        model, selection
    ):
        raise ValueError("cached model/policy replay differs")
    validation_hash = artifacts.put(evaluate_comparison(model, selection, split="validation"))
    # Only now, AFTER feature/model/calibration/policy choices are frozen, open synthetic test rows.
    catalog = artifacts.get(catalog_hash)
    test = [
        {**artifacts.get(item["row_hash"]), "row_hash": item["row_hash"]}
        for item in catalog["rows"]
        if item["split"] == "test"
    ]
    test_hash = artifacts.put(evaluate_comparison(model, test, split="test"))
    input_store, outcome_store = (
        RawStore(data_dir / "demo-inputs"),
        RawStore(data_dir / "demo-outcomes"),
    )
    roster = []
    for row in [*train, *validation, *test]:
        input_hash = input_store.put(
            {"features": row["features"], "news": row["news"], "availability_tier": "FIXTURE"}
        )
        outcome_hash = outcome_store.put(
            {
                "symbol": row["symbol"],
                "session": row["session"],
                "return_fraction": row["return_fraction"],
                "label": row["label"],
                "availability_tier": "FIXTURE",
                "price_convention": "MANUFACTURED_FIXTURE_RETURN",
            }
        )
        roster.append(
            {
                "symbol": row["symbol"],
                "session": row["session"],
                "split": row["split"],
                "input_hash": input_hash,
                "outcome_hash": outcome_hash,
            }
        )
    release = {
        "schema": DEMO_VERSION,
        "availability_tier": "FIXTURE",
        "binding": binding,
        **fit_result,
        "validation_report_hash": validation_hash,
        "test_report_hash": test_hash,
        "rows": roster,
        "class_names": list(CLASSES),
        "train_rows": len(train),
        "calibration_rows": len(calibration),
        "selection_rows": len(selection),
        "test_rows": len(test),
        "test_opened_only_after_choices_frozen": True,
        "trailforge_verify_receipt": record["tasks"]["verify"]["receipt"]["receipt_id"],
        "run_id": run_id,
        "notice": "SYNTHETIC SOFTWARE DEMO — NOT MARKET PERFORMANCE",
    }
    release_hash = RawStore(data_dir / "demo-releases").put(release)
    from marketpulse.service import DemoService

    service = DemoService(data_dir, release_hash=release_hash)
    service.register_release(release_hash)
    with index.connect() as db:
        db.execute(
            "UPDATE extraction_jobs SET status='COMPLETE',manifest_json=? WHERE job_key=?",
            (canonical_bytes({"release_hash": release_hash}).decode(), key),
        )
    return {
        "state": "COMPLETE",
        "release_hash": release_hash,
        "run_id": run_id,
        "availability_tier": "FIXTURE",
        "train_rows": len(train),
        "calibration_rows": len(calibration),
        "selection_rows": len(selection),
        "test_rows": len(test),
        "built_at_utc": utc_iso(datetime.now(timezone.utc)),
        "real_data_collected": False,
        "notice": release["notice"],
    }
