"""Portable multinomial combiner of strictly chronological expert probabilities."""

from __future__ import annotations

from copy import deepcopy
from importlib.metadata import version

import numpy as np

from marketpulse.baselines import CLASSES
from marketpulse.constants import STOCKS
from marketpulse.context_expert_models import ExpertAPI
from marketpulse.price_expert_models import expected_cutoff
from marketpulse.storage import digest
from marketpulse.v2_runtime import environment

SCHEMA = "chronological-expert-stack/1"
INPUT_SCHEMA = "chronological-expert-probabilities/1"
EXPERTS = ("price", "news", "market")


def probability_input(row: dict, probabilities: dict, used_through: str) -> dict:
    value = {
        "schema": INPUT_SCHEMA,
        "session": row["session"],
        "symbol": row["symbol"],
        "cutoff_utc": expected_cutoff(row["session"]),
        "base_row_hash": row["base_row_hash"],
        "source_input_hash": row["input_hash"],
        "classes": list(CLASSES),
        "probabilities": deepcopy(probabilities),
        "used_outcomes_through": used_through,
        "outcomes_loaded": False,
    }
    value["feature_hash"] = digest(value)
    return value


class MetaAPI(ExpertAPI):
    """Nine probability features; inherited train-only scaler/LR and calibration."""

    def __init__(self):
        self.EXPERT = "stack"
        self.SCHEMA = SCHEMA
        self.FEATURE_NAMES = tuple(f"{expert}_{label}" for expert in EXPERTS for label in CLASSES)

    def model_environment(self) -> dict:
        return {**environment(), "xgboost": version("xgboost"), "lightgbm": version("lightgbm")}

    def numeric(self, rows: list[dict]) -> np.ndarray:
        if not rows:
            raise ValueError("stack needs nonempty probability inputs")
        values = []
        for row in rows:
            value = row["input"]
            if (
                value.get("schema") != INPUT_SCHEMA
                or value.get("symbol") not in STOCKS
                or value.get("outcomes_loaded") is not False
                or value.get("classes") != list(CLASSES)
                or value.get("feature_hash")
                != digest({k: v for k, v in value.items() if k != "feature_hash"})
                or value["used_outcomes_through"] >= value["session"]
                or value["cutoff_utc"] != expected_cutoff(value["session"])
                or set(value["probabilities"]) != set(EXPERTS)
                or any(
                    k in row and row[k] != value[k] for k in ("symbol", "session", "base_row_hash")
                )
            ):
                raise ValueError("stack input identity/chronology differs")
            matrix = np.asarray([value["probabilities"][e] for e in EXPERTS], dtype=float)
            if (
                matrix.shape != (3, 3)
                or not np.isfinite(matrix).all()
                or (matrix < 0).any()
                or (matrix > 1).any()
                or not np.allclose(matrix.sum(axis=1), 1)
            ):
                raise ValueError("invalid expert probabilities")
            values.append(matrix.reshape(9).tolist())
        return np.asarray(values, dtype=float)
