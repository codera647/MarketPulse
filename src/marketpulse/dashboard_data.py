"""Read-only, verified projections of pinned local research releases for the UI."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd
from trailforge.store import SQLiteRunStore

from marketpulse.baselines import CLASSES
from marketpulse.constants import STOCKS
from marketpulse.labels import classify_return
from marketpulse.regression_pipeline import complete_roster
from marketpulse.storage import RawStore, digest
from marketpulse.v2_models import detailed_metrics

RELEASE = "7fa2667f7268de276953112d6fa81e06c6315ba958e771786f4842b4cbe21951"
REPORTS = {
    "2026 retrospective": (
        "stacking-eval-2026-20261013",
        "617a7f51186f0cfd192af5b5862c6fa5254d9fc0bdf4732b350defdb6ef2deea",
    ),
    "2025 development": (
        "stacking-20261013",
        "85183e7e622c4c556ae46003cc7d0837134f9e16a61222bfe804b60bff96f7c5",
    ),
}
MODEL_NAMES = {
    "stack": "Stack · Logistic Regression",
    "price": "Price · CatBoost",
    "news": "News · Logistic Regression",
    "market": "Market · LightGBM",
    "previous_price_xgboost": "Earlier price · XGBoost",
    "simple_average": "Simple average",
    "calibrated_average": "Calibrated average",
    "majority": "Neutral-only baseline",
}
LABEL_NAMES = {"DOWN": "Down", "NO_MATERIAL_MOVE": "Neutral", "UP": "Up"}
COMPANIES = {
    "AAPL": ("Apple", "Technology"),
    "AMZN": ("Amazon", "Consumer discretionary"),
    "JPM": ("JPMorgan Chase", "Financials"),
    "NVDA": ("NVIDIA", "Technology"),
    "WMT": ("Walmart", "Consumer staples"),
    "XOM": ("Exxon Mobil", "Energy"),
}


@contextmanager
def read_database(path: Path):
    connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)
    try:
        yield connection
    finally:
        connection.close()


class ReadOnlyRuns(SQLiteRunStore):
    """Reuse Trailforge checkpoint validation without its initializing/writing constructor."""

    def __init__(self, path: Path):
        self.path = path
        self.protocol = "trailforge/execution/0.1"

    def connect(self):
        return read_database(self.path)


def verified_report(root: Path, key: str, *, release: bool = False) -> dict:
    with read_database(root / "v2-jobs.sqlite3") as db:
        rows = db.execute(
            "SELECT job_key,run_id,manifest_json FROM extraction_jobs WHERE status='COMPLETE' "
            "AND manifest_json IS NOT NULL"
        ).fetchall()
    receipts = []
    for job_key, run_id, manifest in rows:
        receipt = json.loads(manifest)
        if receipt.get("job_key") != job_key or receipt.get("run_id") != run_id:
            raise ValueError("Application/native task identity differs")
        receipts.append(receipt)
    field = "release_hash" if release else "report_hash"
    matches = [receipt for receipt in receipts if receipt.get(field) == key]
    if len(matches) != 1:
        raise ValueError("Report has no unique completed authority")
    receipt = matches[0]
    verify_native(root, receipt)
    return receipt


def verify_native(root: Path, receipt: dict) -> None:
    record = ReadOnlyRuns(root / "v2-trailforge.sqlite3").load(receipt["run_id"])
    if (
        record["state"] != "COMPLETED"
        or digest(record["goal"]["tasks"][0]["input"]) != receipt["binding_hash"]
        or record["tasks"]["verify"]["result"]["verdict"] != "PASS"
        or record["tasks"]["verify"]["receipt"]["receipt_id"] != receipt["verify_receipt"]
        or any(receipt.get(k) != v for k, v in record["tasks"]["execute"]["result"].items())
    ):
        raise ValueError("Report native verification mismatch")


def operations(data_parent: Path, period: str) -> dict:
    """Verify each completed receipt without trusting a stale PID or running a task."""
    folder, _ = REPORTS[period]
    root = data_parent / folder
    with read_database(root / "v2-jobs.sqlite3") as db:
        jobs = db.execute(
            "SELECT job_key,run_id,status,manifest_json FROM extraction_jobs"
        ).fetchall()
    counts: dict[str, int] = {}
    for job_key, run_id, status, manifest in jobs:
        label = status
        if status == "COMPLETE":
            if manifest is None:
                raise ValueError("Completed task has no receipt")
            receipt = json.loads(manifest)
            if receipt.get("job_key") != job_key or receipt.get("run_id") != run_id:
                raise ValueError("Application/native task identity differs")
            verify_native(root, receipt)
            label = "Verified complete"
        counts[label] = counts.get(label, 0) + 1
    status_path = root / "v2-status.json"
    status = json.loads(status_path.read_text(encoding="utf-8")) if status_path.exists() else {}
    return {
        "counts": counts,
        "updated_at_utc": status.get("updated_at_utc"),
        "reported_stage": status.get("stage", "Not recorded"),
        "build_lock_present": (root / "v2-build.lock").exists(),
    }


@dataclass
class ResearchView:
    period: str
    rows: pd.DataFrame
    probabilities: dict[str, np.ndarray]
    report: dict
    report_hash: str
    receipt: dict

    def filter(self, symbols: list[str], start: str, end: str) -> np.ndarray:
        return np.flatnonzero(
            self.rows["symbol"].isin(symbols) & self.rows["session"].between(start, end)
        )

    def metrics(self, indexes: np.ndarray, candidate: str) -> dict:
        if candidate not in self.probabilities or not len(indexes):
            raise ValueError("Select a candidate and at least one example")
        return detailed_metrics(
            self.rows.iloc[indexes].to_dict("records"), self.probabilities[candidate][indexes]
        )

    def prediction(self, index: int, candidate: str) -> dict:
        """Projection intentionally excludes outcomes, raw articles and internal paths."""
        row = self.rows.iloc[index]
        probabilities = self.probabilities[candidate][index]
        return {
            "session": row["session"],
            "symbol": row["symbol"],
            "model": MODEL_NAMES[candidate],
            "predicted": LABEL_NAMES[CLASSES[int(np.argmax(probabilities))]],
            "probabilities": dict(zip(CLASSES, probabilities.tolist(), strict=True)),
            "release_hash": RELEASE,
            "input_hash": row["input_hash"],
            "availability_tier": "HISTORICAL_APPROXIMATE",
            "live": False,
        }

    def outcome(self, index: int) -> dict:
        row = self.rows.iloc[index]
        return {"label": LABEL_NAMES[row["label"]], "return_fraction": row["return_fraction"]}


def load_research(data_parent: Path, period: str) -> ResearchView:
    """Fail closed. No directory creation, providers, estimator loading, or training."""
    folder, key = REPORTS[period]
    root = data_parent / folder
    receipt = verified_report(
        root, RELEASE if period.startswith("2025") else key, release=period.startswith("2025")
    )
    artifacts = RawStore(root / "artifacts")
    if period.startswith("2025") and artifacts.get(RELEASE)["report_hash"] != key:
        raise ValueError("Release/report binding differs")
    report = artifacts.get(key)
    if (
        report.get("availability_tier") != "HISTORICAL_APPROXIMATE"
        or report.get("paper_action_authorized") is not False
    ):
        raise ValueError("Unsupported research authority")
    if period == "2026 retrospective":
        if (
            report.get("schema") != "frozen-stack-2026-retrospective/1"
            or report.get("evaluation_kind") != "RETROSPECTIVE_2026_PREVIOUSLY_EXPOSED"
            or report.get("release_hash") != RELEASE
        ):
            raise ValueError("Unexpected retrospective experiment")
        predictions = artifacts.get(report["prediction_hash"])
        if predictions["outcomes_loaded"] is not False or predictions["release_hash"] != RELEASE:
            raise ValueError("Prediction binding differs")
        hashes, input_hashes = predictions["row_hashes"], predictions["input_hashes"]
        probabilities = predictions["probabilities"]
    else:
        if (
            report.get("schema") != "chronological-expert-stack/1"
            or report.get("evaluation_kind") != "DEVELOPMENT_NOT_FINAL_TEST"
            or receipt.get("release_hash") != RELEASE
        ):
            raise ValueError("Unexpected development experiment")
        hashes, input_hashes = report["selection_row_hashes"], report["selection_input_hashes"]
        probabilities = artifacts.get(report["predictions_hash"])
    if len(set(hashes)) != len(hashes) or len(input_hashes) != len(hashes) or not hashes:
        raise ValueError("Prediction identities differ")
    targets = RawStore(data_parent / "real-2018-2026" / "datasets")
    rows = []
    for key_row, key_input in zip(hashes, input_hashes, strict=True):
        original = targets.get(key_row)
        movement = Decimal(original["return_fraction"])
        if (
            original["symbol"] not in STOCKS
            or Decimal(original["threshold"]) != Decimal("0.01")
            or original["price_convention"] != "regular-minute-proxy/1"
            or not movement.is_finite()
            or movement <= -1
            or classify_return(movement, Decimal("0.01")) != original["label"]
            or not original["session"].startswith(period[:4])
        ):
            raise ValueError("Target identity/convention differs")
        rows.append(
            {
                "session": original["session"],
                "symbol": original["symbol"],
                "label": original["label"],
                "return_fraction": float(movement),
                "row_hash": key_row,
                "input_hash": key_input,
            }
        )
    complete_roster(rows)
    matrices = {}
    if set(probabilities) != set(report["metrics"]) or not set(probabilities) <= MODEL_NAMES.keys():
        raise ValueError("Candidate roster differs")
    for candidate, values in probabilities.items():
        matrix = np.asarray(values, dtype=float)
        if (
            matrix.shape != (len(rows), 3)
            or not np.isfinite(matrix).all()
            or (matrix < 0).any()
            or (matrix > 1).any()
            or not np.allclose(matrix.sum(axis=1), 1, atol=1e-8)
        ):
            raise ValueError("Invalid probability array")
        metrics = detailed_metrics(rows, matrix)
        expected = report["metrics"][candidate]
        for metric in ("accuracy", "macro_f1", "log_loss", "multiclass_brier", "ece_10_bins"):
            if not np.isclose(metrics[metric], expected[metric], atol=1e-10, rtol=0):
                raise ValueError("Saved metric replay differs")
        if metrics["confusion_matrix"] != expected["confusion_matrix"]:
            raise ValueError("Saved confusion replay differs")
        matrices[candidate] = matrix
    return ResearchView(period, pd.DataFrame(rows), matrices, report, key, receipt)


def comparison(view: ResearchView, indexes: np.ndarray) -> pd.DataFrame:
    records = []
    for candidate in view.probabilities:
        metric = view.metrics(indexes, candidate)
        records.append(
            {
                "Model": MODEL_NAMES[candidate],
                "candidate": candidate,
                "Accuracy": metric["accuracy"],
                "Equal-class recall": np.mean(
                    [metric["per_class"][label]["recall"] for label in CLASSES]
                ),
                "Macro-F1": metric["macro_f1"],
                "Log loss": metric["log_loss"],
                "Up recall": metric["per_class"]["UP"]["recall"],
                "Down recall": metric["per_class"]["DOWN"]["recall"],
                "Examples": len(indexes),
            }
        )
    return pd.DataFrame(records)
