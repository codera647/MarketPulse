"""Price-only multiclass experts; no news, SPY, sector or outcome features."""

from __future__ import annotations

import math
import tempfile
from copy import deepcopy
from datetime import date
from functools import lru_cache
from importlib.metadata import version
from pathlib import Path

import numpy as np
from scipy.special import softmax
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

from marketpulse.baselines import CLASSES
from marketpulse.clock import session_window, utc_iso
from marketpulse.constants import STOCKS
from marketpulse.features import FEATURE_NAMES as BASE_FEATURE_NAMES
from marketpulse.storage import digest
from marketpulse.v2_features import FEATURE_VERSION
from marketpulse.v2_models import class_weights, detailed_metrics
from marketpulse.v2_runtime import Artifacts, environment

SCHEMA = "price-expert-classification/1"
PRICE_NAMES = tuple(sorted(n for n in BASE_FEATURE_NAMES if n.startswith("prior_")))
IDENTITY_NAMES = tuple(f"company_{s}" for s in sorted(STOCKS))
PREMARKET_NAMES = (
    "premarket_bar_count",
    "premarket_interval_coverage",
    "premarket_last_age_minutes",
    "premarket_missing",
    "premarket_observed_volume",
    "premarket_prior_close_missing",
    "premarket_return",
)
FEATURE_NAMES = PRICE_NAMES + IDENTITY_NAMES + PREMARKET_NAMES


def model_environment() -> dict:
    return {**environment(), "xgboost": version("xgboost")}


def settings() -> list[dict]:
    common = {"stage": "price_only", "move_multiplier": 1.0}
    return [
        {**common, "family": "logistic", "C": c, "weighted": weighted}
        for c in (0.1, 1.0)
        for weighted in (False, True)
    ] + [
        {**common, "family": family, "depth": depth, "iterations": 200, "weighted": True}
        for family, depths in (("catboost", (4, 6)), ("xgboost", (3, 6)))
        for depth in depths
    ]


@lru_cache(maxsize=4096)
def expected_cutoff(session: str) -> str:
    return utc_iso(session_window(date.fromisoformat(session)).cutoff)


def numeric(rows: list[dict]) -> np.ndarray:
    if not rows:
        raise ValueError("price expert needs nonempty inputs")
    result = []
    for row in rows:
        value = row["input"]
        if (
            value.get("schema") != FEATURE_VERSION
            or value.get("outcomes_loaded") is not False
            or value.get("feature_hash")
            != digest({k: v for k, v in value.items() if k != "feature_hash"})
        ):
            raise ValueError("price expert input identity/schema differs")
        symbol, session = value["symbol"], value["session"]
        if (
            symbol not in STOCKS
            or value["cutoff_utc"] != expected_cutoff(session)
            or ("base_row_hash" in row and row["base_row_hash"] != value["base_row_hash"])
            or ("session" in row and row["session"] != session)
            or ("symbol" in row and row["symbol"] != symbol)
            or any(value["market"].get(f"company_{s}") != int(symbol == s) for s in STOCKS)
        ):
            raise ValueError("price expert cutoff/company identity differs")
        features = [value["price"][n] for n in PRICE_NAMES]
        features += [value["market"][n] for n in IDENTITY_NAMES + PREMARKET_NAMES]
        if any(
            v is not None
            and (isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v))
            for v in features
        ):
            raise ValueError("price expert invalid numeric feature")
        result.append([np.nan if v is None else v for v in features])
    return np.asarray(result, dtype=float)


def fit(rows: list[dict], config: dict, artifacts: Artifacts) -> dict:
    if not rows or any(row["role"] != "train" for row in rows):
        raise ValueError("price expert fitting accepts training roles only")
    if config not in settings():
        raise ValueError("price expert configuration is not frozen")
    if len({r["base_row_hash"] for r in rows}) != len(rows):
        raise ValueError("price expert duplicate training rows")
    labels = [row["label"] for row in rows]
    weights = class_weights(labels, config["weighted"], 1.0)
    imputer = SimpleImputer(strategy="median", keep_empty_features=True)
    matrix = imputer.fit_transform(numeric(rows))
    model = {
        "schema": SCHEMA,
        "settings": config,
        "classes": list(CLASSES),
        "feature_names": list(FEATURE_NAMES),
        "medians": imputer.statistics_.tolist(),
        "training_rows": [r["base_row_hash"] for r in rows],
        "training_last_session": max(r["session"] for r in rows),
        "calibration_rows": [],
        "temperature": 1.0,
        "class_weights": weights,
        "model_environment": model_environment(),
        "uses_news": False,
        "uses_market_context": False,
        "paper_action_authorized": False,
    }
    family = config["family"]
    if family == "logistic":
        scaler = StandardScaler().fit(matrix)
        matrix = scaler.transform(matrix)
        estimator = LogisticRegression(
            C=config["C"],
            class_weight=weights,
            solver="lbfgs",
            max_iter=2000,
            tol=1e-6,
            random_state=17,
        )
        with threadpool_limits(limits=2):
            estimator.fit(matrix, labels)
        if max(estimator.n_iter_) >= 2000 or estimator.classes_.tolist() != list(CLASSES):
            raise ValueError("price logistic convergence/class order failed")
        model.update(
            {
                "means": scaler.mean_.tolist(),
                "scales": scaler.scale_.tolist(),
                "coefficients": estimator.coef_.tolist(),
                "intercepts": estimator.intercept_.tolist(),
            }
        )
    elif family == "catboost":
        from catboost import CatBoostClassifier

        estimator = CatBoostClassifier(
            iterations=config["iterations"],
            depth=config["depth"],
            learning_rate=0.05,
            loss_function="MultiClass",
            class_weights=weights,
            random_seed=17,
            thread_count=2,
            verbose=False,
            allow_writing_files=False,
        )
        estimator.fit(matrix, labels)
        if estimator.classes_.tolist() != list(CLASSES):
            raise ValueError("price CatBoost class order failed")
    else:
        from xgboost import XGBClassifier

        estimator = XGBClassifier(
            n_estimators=config["iterations"],
            max_depth=config["depth"],
            learning_rate=0.05,
            objective="multi:softprob",
            num_class=3,
            eval_metric="mlogloss",
            min_child_weight=20,
            reg_lambda=10,
            tree_method="hist",
            device="cpu",
            subsample=1.0,
            colsample_bytree=1.0,
            random_state=17,
            n_jobs=2,
        )
        estimator.fit(
            matrix,
            np.asarray([CLASSES.index(label) for label in labels]),
            sample_weight=np.asarray([weights[label] for label in labels]),
        )
        if estimator.classes_.tolist() != [0, 1, 2]:
            raise ValueError("price XGBoost class order failed")
    if family != "logistic":
        suffix = ".cbm" if family == "catboost" else ".ubj"
        with tempfile.TemporaryDirectory(prefix="price-expert-", dir=artifacts.root.parent) as tmp:
            path = Path(tmp) / ("model" + suffix)
            estimator.save_model(str(path))
            model["binary_hash"] = artifacts.put_binary(path.read_bytes(), suffix)
        model["feature_importance"] = dict(zip(FEATURE_NAMES, estimator.feature_importances_))
        model["feature_importance"] = {k: float(v) for k, v in model["feature_importance"].items()}
    expected = estimator.predict_proba(matrix)
    if not np.allclose(
        predict(model, rows, artifacts, calibrated=False), expected, rtol=1e-6, atol=1e-8
    ):
        raise ValueError("price expert fitted-versus-saved predictions differ")
    return model


def predict(model: dict, rows: list[dict], artifacts: Artifacts, *, calibrated=True) -> list:
    if (
        model["schema"] != SCHEMA
        or model["classes"] != list(CLASSES)
        or model["feature_names"] != list(FEATURE_NAMES)
        or model["model_environment"] != model_environment()
        or model["uses_news"] is not False
        or model["uses_market_context"] is not False
        or model["paper_action_authorized"] is not False
    ):
        raise ValueError("price expert saved-model identity differs")
    matrix = numeric(rows)
    matrix = np.where(np.isnan(matrix), np.asarray(model["medians"]), matrix)
    family = model["settings"]["family"]
    if family == "logistic":
        matrix = (matrix - np.asarray(model["means"])) / np.asarray(model["scales"])
        values = softmax(
            matrix @ np.asarray(model["coefficients"]).T + np.asarray(model["intercepts"]), axis=1
        )
    elif family == "catboost":
        from catboost import CatBoostClassifier

        estimator = CatBoostClassifier(thread_count=2)
        estimator.load_model(str(artifacts.binary_path(model["binary_hash"], ".cbm")))
        if estimator.classes_.tolist() != list(CLASSES):
            raise ValueError("saved price CatBoost class order differs")
        values = estimator.predict_proba(matrix, thread_count=2)
    elif family == "xgboost":
        from xgboost import XGBClassifier

        estimator = XGBClassifier(n_jobs=2)
        estimator.load_model(str(artifacts.binary_path(model["binary_hash"], ".ubj")))
        if estimator.classes_.tolist() != [0, 1, 2]:
            raise ValueError("saved price XGBoost class order differs")
        values = estimator.predict_proba(matrix)
    else:
        raise ValueError("unsupported price expert family")
    # XGBoost returns float32 probabilities. Validate, then normalize in float64
    # to avoid spurious sklearn log-loss sum warnings; do not change class order.
    values = np.asarray(values, dtype=float)
    if (
        values.shape != (len(rows), 3)
        or not np.isfinite(values).all()
        or (values < 0).any()
        or not np.allclose(values.sum(axis=1), 1)
    ):
        raise ValueError("price expert produced invalid probabilities")
    values = values / values.sum(axis=1, keepdims=True)
    if calibrated:
        temperature = model["temperature"]
        if (
            isinstance(temperature, bool)
            or not isinstance(temperature, (int, float))
            or not math.isfinite(temperature)
            or not 0.1 <= temperature <= 10
        ):
            raise ValueError("invalid price expert temperature")
        values = softmax(np.log(np.maximum(values, 1e-15)) / temperature, axis=1)
    if (
        values.shape != (len(rows), 3)
        or not np.isfinite(values).all()
        or (values < 0).any()
        or not np.allclose(values.sum(axis=1), 1)
    ):
        raise ValueError("price expert produced invalid probabilities")
    return values.tolist()


def calibrate(model: dict, rows: list[dict], artifacts: Artifacts) -> dict:
    if (
        not rows
        or any(r["role"] != "calibration" for r in rows)
        or set(model["training_rows"]) & {r["base_row_hash"] for r in rows}
        or model["training_last_session"] >= min(r["session"] for r in rows)
    ):
        raise ValueError("price calibration must follow and exclude training")
    raw = np.asarray(predict(model, rows, artifacts, calibrated=False))
    losses = []
    for temperature in (0.5, 0.75, 1.0, 1.5, 2.0):
        values = softmax(np.log(np.maximum(raw, 1e-15)) / temperature, axis=1).tolist()
        losses.append((detailed_metrics(rows, values)["log_loss"], temperature))
    result = deepcopy(model)
    result["temperature"] = min(losses)[1]
    result["calibration_rows"] = [r["base_row_hash"] for r in rows]
    return result
