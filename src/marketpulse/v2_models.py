"""Train-only preprocessing, weighted ablations, portable saved-model inference."""

from __future__ import annotations

import math
import tempfile
from collections import Counter
from copy import deepcopy
from pathlib import Path

import numpy as np
from scipy.special import softmax
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

from marketpulse.baselines import CLASSES
from marketpulse.modeling import metrics
from marketpulse.preprocessing import FINANCIAL_TOKEN_PATTERN, clean_news_text
from marketpulse.storage import digest
from marketpulse.v2_features import feature_matrix
from marketpulse.v2_runtime import SCHEMA, Artifacts


def candidate_settings() -> list[dict]:
    result = [
        {
            "family": "control_logistic",
            "stage": "existing",
            "C": c,
            "weighted": False,
            "move_multiplier": 1.0,
        }
        for c in (0.1, 1.0)
    ]
    for stage in ("existing", "market", "meaning"):
        for c in (0.1, 1.0):
            for multiplier in (1.0, 1.5):
                result.append(
                    {
                        "family": "weighted_logistic",
                        "stage": stage,
                        "C": c,
                        "weighted": True,
                        "move_multiplier": multiplier,
                    }
                )
    for depth in (4, 6):
        for multiplier in (1.0, 1.5):
            result.append(
                {
                    "family": "catboost",
                    "stage": "meaning",
                    "depth": depth,
                    "iterations": 200,
                    "weighted": True,
                    "move_multiplier": multiplier,
                }
            )
    return result


def class_weights(labels: list[str], weighted: bool, multiplier: float) -> dict:
    counts = Counter(labels)
    if set(counts) != set(CLASSES) or min(counts.values()) < 2:
        raise ValueError("v2 training needs all classes with >=2 observations")
    if type(weighted) is not bool or multiplier not in (1.0, 1.5):
        raise ValueError("unsupported weighting policy")
    return {
        label: (
            len(labels) / (3 * counts[label]) * (multiplier if label != "NO_MATERIAL_MOVE" else 1.0)
        )
        if weighted
        else 1.0
        for label in CLASSES
    }


def fold_rosters(rows: list[dict]) -> list[tuple[list[dict], list[dict]]]:
    from datetime import date

    from marketpulse.clock import exchange_calendar

    folds = []
    for year in (2022, 2023, 2024):
        train = [row for row in rows if row["session"][:4] < str(year)]
        validation = [row for row in rows if row["session"][:4] == str(year)]
        if not train or not validation:
            raise ValueError("v2 expanding-fold history missing")
        # Remove the final exchange date before validation, even if source QA excluded it.
        start = date.fromisoformat(min(row["session"] for row in validation))
        prior = (
            exchange_calendar()
            .valid_days(start_date=date(year - 1, 12, 1), end_date=start)
            .date.tolist()
        )
        embargo = [day.isoformat() for day in prior if day < start][-1]
        train = [row for row in train if row["session"] < embargo]
        if not train or max(row["session"] for row in train) >= min(
            row["session"] for row in validation
        ):
            raise ValueError("v2 chronology/embargo failed")
        folds.append((train, validation))
    return folds


def _numeric(rows: list[dict], stage: str):
    names, matrix = feature_matrix(rows, stage)
    return names, np.asarray(
        [[np.nan if value is None else value for value in values] for values in matrix], dtype=float
    )


def fit_candidate(rows: list[dict], settings: dict, artifacts: Artifacts) -> dict:
    if not rows or any(row["role"] != "train" for row in rows):
        raise ValueError("v2 fitting accepts training roles only")
    labels = [row["label"] for row in rows]
    weights = class_weights(labels, settings["weighted"], settings["move_multiplier"])
    names, matrix = _numeric(rows, settings["stage"])
    imputer = SimpleImputer(strategy="median", keep_empty_features=True)
    numeric = imputer.fit_transform(matrix)
    model = {
        "schema": SCHEMA,
        "settings": settings,
        "classes": list(CLASSES),
        "feature_names": names,
        "medians": imputer.statistics_.tolist(),
        "training_rows": [row["base_row_hash"] for row in rows],
        "training_counts": dict(Counter(labels)),
        "class_weights": weights,
        "temperature": 1.0,
        "calibration_rows": [],
        "paper_action_authorized": False,
    }
    if settings["family"] == "catboost":
        from catboost import CatBoostClassifier

        estimator = CatBoostClassifier(
            iterations=settings["iterations"],
            depth=settings["depth"],
            learning_rate=0.05,
            loss_function="MultiClass",
            class_weights=weights,
            random_seed=17,
            thread_count=2,
            verbose=False,
            allow_writing_files=False,
        )
        estimator.fit(numeric, labels)
        if estimator.classes_.tolist() != list(CLASSES):
            raise ValueError("v2 CatBoost class order mismatch")
        with tempfile.TemporaryDirectory(
            prefix="marketpulse-v2-", dir=artifacts.root.parent
        ) as tmp:
            path = Path(tmp) / "candidate.cbm"
            estimator.save_model(str(path))
            model["binary_hash"] = artifacts.put_binary(path.read_bytes(), ".cbm")
        model["feature_importance"] = dict(zip(names, estimator.feature_importances_.tolist()))
        model["uses_tfidf"] = False
        expected = estimator.predict_proba(numeric)
    else:
        scaler = StandardScaler().fit(numeric)
        numeric = scaler.transform(numeric)
        vectorizer = TfidfVectorizer(max_features=1024, token_pattern=FINANCIAL_TOKEN_PATTERN)
        text = vectorizer.fit_transform([clean_news_text(row["news"]) for row in rows])
        matrix = np.column_stack((numeric, text.toarray()))
        estimator = LogisticRegression(
            C=settings["C"],
            class_weight=weights,
            solver="lbfgs",
            max_iter=2000,
            tol=1e-6,
            random_state=17,
        )
        with threadpool_limits(limits=2):
            estimator.fit(matrix, labels)
        if estimator.classes_.tolist() != list(CLASSES) or max(estimator.n_iter_) >= 2000:
            raise ValueError("v2 classifier failed class-order/convergence checks")
        model.update(
            {
                "uses_tfidf": True,
                "means": scaler.mean_.tolist(),
                "scales": scaler.scale_.tolist(),
                "vocabulary": vectorizer.get_feature_names_out().tolist(),
                "idf": vectorizer.idf_.tolist(),
                "token_pattern": FINANCIAL_TOKEN_PATTERN,
                "coefficients": estimator.coef_.tolist(),
                "intercepts": estimator.intercept_.tolist(),
            }
        )
        expected = estimator.predict_proba(matrix)
    actual = score_candidate(model, rows, artifacts, calibrated=False)
    if not np.allclose(actual, expected, rtol=1e-6, atol=1e-8):
        raise ValueError("v2 saved model inference mismatch")
    return model


def score_candidate(model: dict, rows: list[dict], artifacts: Artifacts, *, calibrated=True):
    if (
        model["schema"] != SCHEMA
        or model["paper_action_authorized"] is not False
        or model["classes"] != list(CLASSES)
    ):
        raise ValueError("incompatible v2 model")
    names, numeric = _numeric(rows, model["settings"]["stage"])
    if names != model["feature_names"]:
        raise ValueError("v2 scoring feature order mismatch")
    numeric = np.where(np.isnan(numeric), np.asarray(model["medians"]), numeric)
    if model["uses_tfidf"]:
        vectorizer = TfidfVectorizer(
            vocabulary={word: i for i, word in enumerate(model["vocabulary"])},
            token_pattern=model["token_pattern"],
        )
        vectorizer.idf_ = np.asarray(model["idf"])
        text = vectorizer.transform([clean_news_text(row["news"]) for row in rows]).toarray()
        numeric = (numeric - np.asarray(model["means"])) / np.asarray(model["scales"])
        matrix = np.column_stack((numeric, text))
        with threadpool_limits(limits=2):
            values = softmax(
                matrix @ np.asarray(model["coefficients"]).T + np.asarray(model["intercepts"]),
                axis=1,
            )
    else:
        from catboost import CatBoostClassifier

        estimator = CatBoostClassifier(thread_count=2)
        estimator.load_model(str(artifacts.binary_path(model["binary_hash"])))
        if estimator.classes_.tolist() != list(CLASSES):
            raise ValueError("saved CatBoost class order changed")
        values = estimator.predict_proba(numeric, thread_count=2)
    if calibrated:
        temperature = model["temperature"]
        if (
            not isinstance(temperature, (int, float))
            or not math.isfinite(temperature)
            or not (0.1 <= temperature <= 10)
        ):
            raise ValueError("invalid v2 temperature")
        values = softmax(np.log(np.maximum(values, 1e-15)) / temperature, axis=1)
    if (
        not np.isfinite(values).all()
        or (values < 0).any()
        or not np.allclose(values.sum(axis=1), 1)
    ):
        raise ValueError("v2 scoring produced invalid probabilities")
    return values.tolist()


def calibrate_candidate(model: dict, rows: list[dict], artifacts: Artifacts) -> dict:
    if (
        not rows
        or any(row["role"] != "calibration" for row in rows)
        or set(model["training_rows"]) & {row["base_row_hash"] for row in rows}
    ):
        raise ValueError("v2 calibration overlaps training or has wrong roles")
    raw = np.asarray(score_candidate(model, rows, artifacts, calibrated=False))
    labels = [row["label"] for row in rows]
    candidates = []
    for temperature in (0.5, 0.75, 1.0, 1.5, 2.0):
        values = softmax(np.log(np.maximum(raw, 1e-15)) / temperature, axis=1).tolist()
        candidates.append((metrics(labels, values)["log_loss"], temperature))
    result = deepcopy(model)
    result["temperature"] = min(candidates)[1]
    result["calibration_rows"] = [row["base_row_hash"] for row in rows]
    return result


def detailed_metrics(rows: list[dict], probabilities: list[list[float]]) -> dict:
    result = metrics([row["label"] for row in rows], probabilities)
    matrix = result["confusion_matrix"]
    result["per_class"] = {
        label: {
            "recall": matrix[i][i] / sum(matrix[i]) if sum(matrix[i]) else 0.0,
            "precision": matrix[i][i] / sum(row[i] for row in matrix)
            if sum(row[i] for row in matrix)
            else 0.0,
            "support": sum(matrix[i]),
        }
        for i, label in enumerate(CLASSES)
    }
    result["prediction_counts"] = {
        label: sum(CLASSES[int(np.argmax(p))] == label for p in probabilities) for label in CLASSES
    }
    return result


def candidate_id(settings: dict) -> str:
    return f"{settings['family']}_{settings['stage']}_{digest(settings)[:12]}"
