"""Bounded numeric return regressors; portable non-executable model exports."""

from __future__ import annotations

import math
import tempfile
from decimal import Decimal
from pathlib import Path

import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.metrics import confusion_matrix, f1_score
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

from marketpulse.baselines import CLASSES
from marketpulse.labels import classify_return
from marketpulse.v2_features import feature_matrix
from marketpulse.v2_runtime import Artifacts, environment

REGRESSION_SCHEMA = "continuous-return-research/1"


def settings() -> list[dict]:
    result = [{"family": "linear", "alpha": 0.0}]
    result += [{"family": "ridge", "alpha": a} for a in (0.1, 1.0, 10.0, 100.0)]
    result += [
        {"family": "random_forest", "trees": 150, "depth": d, "min_leaf": n}
        for d in (6, 12) for n in (20, 50)
    ]
    result += [
        {"family": "hist_gradient_boosting", "iterations": 200, "leaves": n, "l2": a}
        for n in (15, 31) for a in (1.0, 10.0)
    ]
    result += [
        {"family": "catboost", "iterations": 200, "depth": d, "l2": a}
        for d in (4, 6) for a in (3.0, 10.0)
    ]
    return result


def numeric(rows: list[dict]) -> tuple[list[str], np.ndarray]:
    names, values = feature_matrix(rows, "meaning")
    matrix = np.asarray([[np.nan if v is None else v for v in r] for r in values])
    if np.isinf(matrix).any():
        raise ValueError("non-finite regression feature")
    return names, matrix.astype(float)


def export_tree(tree, *, histogram=False) -> dict:
    if histogram:
        nodes = tree.nodes
        if np.any(nodes["is_categorical"]):
            raise ValueError("categorical histogram serialization is not supported")
        return {
            "left": nodes["left"].tolist(), "right": nodes["right"].tolist(),
            "feature": nodes["feature_idx"].tolist(),
            "threshold": nodes["num_threshold"].tolist(),
            "value": nodes["value"].tolist(), "leaf": nodes["is_leaf"].tolist(),
        }
    return {
        "left": tree.children_left.tolist(), "right": tree.children_right.tolist(),
        "feature": tree.feature.tolist(), "threshold": tree.threshold.tolist(),
        "value": tree.value[:, 0, 0].tolist(), "leaf": (tree.children_left < 0).tolist(),
    }


def tree_score(tree: dict, matrix: np.ndarray) -> np.ndarray:
    left, right, feature = (np.asarray(tree[k], dtype=int) for k in ("left", "right", "feature"))
    threshold, value = (np.asarray(tree[k], dtype=float) for k in ("threshold", "value"))
    leaf = np.asarray(tree["leaf"], dtype=bool)
    length = len(value)
    if (
        not length or any(len(v) != length for v in (left, right, feature, threshold, leaf))
        or not np.isfinite(value).all() or not np.isfinite(threshold).all()
        or np.any((~leaf) & ((feature < 0) | (feature >= matrix.shape[1])))
        or np.any((~leaf) & ((left < 0) | (right < 0) | (left >= length) | (right >= length)))
    ):
        raise ValueError("invalid portable regression tree")
    position = np.zeros(len(matrix), dtype=int)
    # Traversal is bounded by node count; cyclic/tampered trees cannot hang.
    for _ in range(length):
        active = np.flatnonzero(~leaf[position])
        if not len(active):
            return value[position]
        node = position[active]
        position[active] = np.where(
            matrix[active, feature[node]] <= threshold[node], left[node], right[node]
        )
    raise ValueError("cyclic portable regression tree")


def fit(rows: list[dict], config: dict, artifacts: Artifacts) -> dict:
    if config not in settings() or not rows or any(r["role"] != "train" for r in rows):
        raise ValueError("regression fitting requires approved training rows/settings")
    y = np.asarray([r["target"] for r in rows], dtype=float)
    if not np.isfinite(y).all() or np.any(y <= -1):
        raise ValueError("invalid return targets")
    names, matrix = numeric(rows)
    imputer = SimpleImputer(strategy="median", keep_empty_features=True)
    matrix = imputer.fit_transform(matrix)
    model = {
        "schema": REGRESSION_SCHEMA, "config": config, "environment": environment(),
        "feature_names": names, "medians": imputer.statistics_.tolist(),
        "training_rows": [r["base_row_hash"] for r in rows], "paper_action_authorized": False,
        "target": "regular-minute-open-to-close-return-fraction", "threshold": "0.01",
    }
    family = config["family"]
    with threadpool_limits(limits=2):
        if family in {"linear", "ridge"}:
            scaler = StandardScaler().fit(matrix)
            matrix = scaler.transform(matrix)
            estimator = LinearRegression() if family == "linear" else Ridge(alpha=config["alpha"])
            estimator.fit(matrix, y)
            model.update({
                "means": scaler.mean_.tolist(), "scales": scaler.scale_.tolist(),
                "coefficients": estimator.coef_.tolist(), "intercept": float(estimator.intercept_),
            })
        elif family == "random_forest":
            estimator = RandomForestRegressor(
                n_estimators=config["trees"], max_depth=config["depth"],
                min_samples_leaf=config["min_leaf"], n_jobs=2, random_state=17,
            ).fit(matrix, y)
            model["trees"] = [export_tree(t.tree_) for t in estimator.estimators_]
        elif family == "hist_gradient_boosting":
            estimator = HistGradientBoostingRegressor(
                max_iter=config["iterations"], max_leaf_nodes=config["leaves"],
                l2_regularization=config["l2"], learning_rate=0.05, min_samples_leaf=20,
                early_stopping=False, random_state=17,
            ).fit(matrix, y)
            model["baseline"] = float(estimator._baseline_prediction[0, 0])
            model["trees"] = [export_tree(p[0], histogram=True) for p in estimator._predictors]
        else:
            from catboost import CatBoostRegressor

            estimator = CatBoostRegressor(
                iterations=config["iterations"], depth=config["depth"],
                l2_leaf_reg=config["l2"], learning_rate=0.05, loss_function="RMSE",
                random_seed=17, thread_count=2, verbose=False, allow_writing_files=False,
            ).fit(matrix, y)
            with tempfile.TemporaryDirectory(
                prefix="regression-", dir=artifacts.root.parent
            ) as tmp:
                path = Path(tmp) / "model.cbm"
                estimator.save_model(str(path))
                model["binary_hash"] = artifacts.put_binary(path.read_bytes(), ".cbm")
        expected = estimator.predict(matrix)
    actual = predict(model, rows, artifacts)
    if not np.allclose(actual, expected, rtol=1e-7, atol=1e-10):
        raise ValueError("portable regressor differs from fitted estimator")
    return model


def predict(model: dict, rows: list[dict], artifacts: Artifacts) -> list[float]:
    if (model["schema"] != REGRESSION_SCHEMA or model["environment"] != environment()
            or model["paper_action_authorized"] is not False or model["config"] not in settings()):
        raise ValueError("incompatible regression model")
    names, matrix = numeric(rows)
    if names != model["feature_names"]:
        raise ValueError("regression feature order differs")
    matrix = np.where(np.isnan(matrix), np.asarray(model["medians"]), matrix)
    family = model["config"]["family"]
    with threadpool_limits(limits=2):
        if family in {"linear", "ridge"}:
            matrix = (matrix - np.asarray(model["means"])) / np.asarray(model["scales"])
            values = matrix @ np.asarray(model["coefficients"]) + model["intercept"]
        elif family in {"random_forest", "hist_gradient_boosting"}:
            if not model["trees"]:
                raise ValueError("missing regression trees")
            if family == "random_forest":
                matrix = matrix.astype(np.float32)  # sklearn's tree prediction input convention
            values = sum(tree_score(t, matrix) for t in model["trees"])
            values = (values / len(model["trees"]) if family == "random_forest"
                      else values + model["baseline"])
        else:
            from catboost import CatBoostRegressor

            estimator = CatBoostRegressor(thread_count=2)
            estimator.load_model(str(artifacts.binary_path(model["binary_hash"])))
            values = estimator.predict(matrix, thread_count=2)
    if np.asarray(values).shape != (len(rows),) or not np.isfinite(values).all():
        raise ValueError("invalid regression predictions")
    return np.asarray(values).tolist()


def evaluate(targets: list[float], predictions: list[float]) -> dict:
    y, p = np.asarray(targets, dtype=float), np.asarray(predictions, dtype=float)
    if not len(y) or y.shape != p.shape or not np.isfinite(y).all() or not np.isfinite(p).all():
        raise ValueError("regression metric inputs invalid")
    error = y - p
    mae, rmse = float(np.mean(np.abs(error))), float(np.sqrt(np.mean(error**2)))
    denominator = float(np.sum((y - np.mean(y)) ** 2))
    labels = [classify_return(Decimal(str(v)), Decimal("0.01")) for v in y]
    predicted = [classify_return(Decimal(str(v)), Decimal("0.01")) for v in p]
    matrix = confusion_matrix(labels, predicted, labels=list(CLASSES)).tolist()
    per_class = {
        label: {
            "support": sum(matrix[i]),
            "recall": matrix[i][i] / sum(matrix[i]) if sum(matrix[i]) else 0.0,
            "precision": matrix[i][i] / sum(row[i] for row in matrix)
            if sum(row[i] for row in matrix) else 0.0,
        } for i, label in enumerate(CLASSES)
    }
    if not all(math.isfinite(v) for v in (mae, rmse)):
        raise ValueError("non-finite regression metric")
    return {
        "rows": len(y), "mae": mae, "rmse": rmse,
        "mae_percentage_points": 100 * mae, "rmse_percentage_points": 100 * rmse,
        "r_squared": 1 - float(np.sum(error**2)) / denominator if denominator else None,
        "derived_class_accuracy": sum(matrix[i][i] for i in range(3)) / len(y),
        "derived_class_balanced_accuracy": sum(v["recall"] for v in per_class.values()) / 3,
        "derived_class_macro_f1": float(f1_score(
            labels, predicted, labels=list(CLASSES), average="macro", zero_division=0)),
        "per_class": per_class, "confusion_matrix": matrix,
        "prediction_counts": {label: predicted.count(label) for label in CLASSES},
    }
