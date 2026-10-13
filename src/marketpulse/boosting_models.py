"""Fixed-seed CPU return boosting; native/portable, never executable-pickle models."""

from __future__ import annotations

import tempfile
from importlib.metadata import version
from pathlib import Path

import numpy as np
from sklearn.ensemble import AdaBoostRegressor
from sklearn.impute import SimpleImputer
from sklearn.tree import DecisionTreeRegressor
from threadpoolctl import threadpool_limits

from marketpulse.regression_models import export_tree, numeric, tree_score
from marketpulse.v2_runtime import Artifacts, environment

MODEL_SCHEMA = "continuous-return-boosting/1"
PINNED = {"xgboost": "3.4.1", "lightgbm": "4.7.0"}


def model_environment() -> dict:
    extra = {name: version(name) for name in PINNED}
    if extra != PINNED:
        raise ValueError("boosting requires the pinned private research dependencies")
    return {**environment(), **extra}


def settings() -> list[dict]:
    return [
        {"family": "xgboost", "trees": 200, "depth": d, "l2": a}
        for d in (3, 6) for a in (1.0, 10.0)
    ] + [
        {"family": "lightgbm", "trees": 200, "leaves": n, "l2": a}
        for n in (15, 31) for a in (1.0, 10.0)
    ] + [
        {"family": "adaboost", "trees": 200, "depth": d, "learning_rate": a}
        for d in (2, 4) for a in (0.05, 0.1)
    ]


def fit(rows: list[dict], config: dict, artifacts: Artifacts) -> dict:
    if config not in settings() or not rows or any(r["role"] != "train" for r in rows):
        raise ValueError("boosting fitting requires approved training rows/settings")
    y = np.asarray([r["target"] for r in rows], dtype=float)
    if not np.isfinite(y).all() or np.any(y <= -1):
        raise ValueError("invalid return targets")
    names, matrix = numeric(rows)
    imputer = SimpleImputer(strategy="median", keep_empty_features=True)
    matrix = imputer.fit_transform(matrix)
    model = {
        "schema": MODEL_SCHEMA, "config": config, "environment": model_environment(),
        "feature_names": names, "medians": imputer.statistics_.tolist(),
        "training_rows": [r["base_row_hash"] for r in rows], "paper_action_authorized": False,
        "target": "regular-minute-open-to-close-return-fraction", "threshold": "0.01",
        "random_seed": 17, "device": "cpu", "thread_limit": 2,
    }
    family = config["family"]
    with threadpool_limits(limits=2):
        if family == "xgboost":
            from xgboost import XGBRegressor

            estimator = XGBRegressor(
                n_estimators=config["trees"], max_depth=config["depth"],
                reg_lambda=config["l2"], min_child_weight=20, learning_rate=0.05,
                objective="reg:squarederror", tree_method="hist", device="cpu",
                subsample=1.0, colsample_bytree=1.0, random_state=17, n_jobs=2,
            ).fit(matrix, y)
            with tempfile.TemporaryDirectory(prefix="boost-", dir=artifacts.root.parent) as tmp:
                path = Path(tmp) / "model.ubj"
                estimator.save_model(path)
                model["binary_hash"] = artifacts.put_binary(path.read_bytes(), ".ubj")
        elif family == "lightgbm":
            from lightgbm import LGBMRegressor

            estimator = LGBMRegressor(
                n_estimators=config["trees"], num_leaves=config["leaves"],
                reg_lambda=config["l2"], min_child_samples=20, learning_rate=0.05,
                objective="regression", boosting_type="gbdt", device_type="cpu",
                subsample=1.0, subsample_freq=0, colsample_bytree=1.0,
                random_state=17, data_random_seed=17, feature_fraction_seed=17,
                bagging_seed=17, deterministic=True, force_col_wise=True,
                n_jobs=2, verbosity=-1,
            ).fit(matrix, y)
            # Native text, not pickle: retains exact tree thresholds and shrinkage.
            model["binary_hash"] = artifacts.put_binary(
                estimator.booster_.model_to_string().encode("utf-8"), ".lgb")
        else:
            estimator = AdaBoostRegressor(
                estimator=DecisionTreeRegressor(
                    max_depth=config["depth"], min_samples_leaf=20, random_state=17),
                n_estimators=config["trees"], learning_rate=config["learning_rate"],
                loss="linear", random_state=17,
            ).fit(matrix, y)
            model["trees"] = [export_tree(t.tree_) for t in estimator.estimators_]
            model["weights"] = estimator.estimator_weights_[:len(estimator.estimators_)].tolist()
            model["effective_estimators"] = len(estimator.estimators_)
            model["zero_estimator_weights"] = sum(model["weights"]) == 0
        # Native LightGBM inference avoids sklearn feature-name warnings.
        expected = (estimator.booster_.predict(matrix, num_threads=2) if family == "lightgbm"
                    else estimator.predict(matrix))
    actual = predict(model, rows, artifacts)
    if not np.allclose(actual, expected, rtol=1e-7, atol=1e-10):
        raise ValueError("saved booster differs from fitted estimator")
    return model


def weighted_median(trees: list[dict], weights: list[float], matrix: np.ndarray) -> np.ndarray:
    weights = np.asarray(weights, dtype=float)
    if (not trees or weights.shape != (len(trees),) or not np.isfinite(weights).all()
            or np.any(weights < 0) or not np.isfinite(weights.sum())):
        raise ValueError("invalid AdaBoost tree weights")
    # sklearn retains a first weak learner with zero weight if its error >= .5.
    # Its zero-total CDF rule is still defined; reproduce it, never invent weights.
    scores = np.asarray([tree_score(t, matrix.astype(np.float32)) for t in trees]).T
    order = np.argsort(scores, axis=1)
    cumulative = np.cumsum(weights[order], axis=1)
    median = (cumulative >= 0.5 * cumulative[:, -1, None]).argmax(axis=1)
    return scores[np.arange(len(scores)), order[np.arange(len(scores)), median]]


def predict(model: dict, rows: list[dict], artifacts: Artifacts) -> list[float]:
    if (model["schema"] != MODEL_SCHEMA or model["environment"] != model_environment()
            or model["paper_action_authorized"] is not False or model["config"] not in settings()
            or model["random_seed"] != 17 or model["device"] != "cpu"
            or model["thread_limit"] != 2):
        raise ValueError("incompatible boosting model")
    names, matrix = numeric(rows)
    medians = np.asarray(model["medians"], dtype=float)
    if (names != model["feature_names"] or medians.shape != (len(names),)
            or not np.isfinite(medians).all()):
        raise ValueError("boosting feature order/imputation differs")
    matrix = np.where(np.isnan(matrix), medians, matrix)
    family = model["config"]["family"]
    with threadpool_limits(limits=2):
        if family == "xgboost":
            from xgboost import XGBRegressor

            estimator = XGBRegressor(n_jobs=2, device="cpu")
            estimator.load_model(artifacts.binary_path(model["binary_hash"], ".ubj"))
            estimator.set_params(n_jobs=2, device="cpu")
            values = estimator.predict(matrix)
        elif family == "lightgbm":
            from lightgbm import Booster

            estimator = Booster(model_file=str(artifacts.binary_path(model["binary_hash"], ".lgb")))
            values = estimator.predict(matrix, num_threads=2)
        else:
            values = weighted_median(model["trees"], model["weights"], matrix)
    if np.asarray(values).shape != (len(rows),) or not np.isfinite(values).all():
        raise ValueError("invalid boosting predictions")
    return np.asarray(values).tolist()
