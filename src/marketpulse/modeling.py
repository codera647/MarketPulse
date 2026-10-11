"""Portable JSON text/combined models and date-separated fixture calibration."""

from __future__ import annotations

import math
import re
import warnings
from collections import Counter

import numpy as np
from sklearn.exceptions import ConvergenceWarning
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, log_loss

from marketpulse.baselines import (
    CLASSES,
    FIT_SETTINGS,
    PRICE_FEATURES,
    _choose,
    fit_baselines,
    predict_baselines,
    validate_features,
    validate_model,
)
from marketpulse.clock import parse_time, session_window
from marketpulse.storage import digest

MODEL_SCHEMA = "news-comparison/1"
MODEL_NAMES = ("majority", "price_only", "text_only", "combined")
TOKEN_PATTERN = r"(?u)\b\w\w+\b"


def headline_text(item: dict) -> str:
    """Accept input-only text; a feature document never includes future prices/labels."""
    from datetime import date

    features = item["features"]
    validate_features(features)
    window = session_window(date.fromisoformat(features["session"]))
    news = item.get("news", [])
    if len(news) != features["values"]["news_article_count"]:
        raise ValueError("text and numeric news counts disagree")
    if [article["version_hash"] for article in news] != features["article_version_hashes"]:
        raise ValueError("text versions differ from feature snapshot")
    for article in news:
        if (
            not window.previous_close
            < parse_time(article["created_at"])
            <= parse_time(article["updated_at"])
            <= window.cutoff
        ):
            raise ValueError("post-cutoff text is not a prediction input")
        if not isinstance(article["headline"], str) or len(article["headline"]) > 10000:
            raise ValueError("invalid headline")
    return " ".join(article["headline"] for article in news) or "noeligibleheadline"


def _softmax(scores) -> np.ndarray:
    scores = np.asarray(scores, dtype=float)
    if scores.shape != (3,) or not np.isfinite(scores).all():
        raise ValueError("invalid class scores")
    values = np.exp(scores - scores.max())
    return values / values.sum()


def _tfidf(model: dict, text: str) -> np.ndarray:
    counts = Counter(re.findall(TOKEN_PATTERN, text.lower()))
    values = np.array([counts[word] for word in model["vocabulary"]]) * model["idf"]
    norm = float(np.linalg.norm(values))
    return values / norm if norm else values


def _price_vector(model: dict, features: dict) -> np.ndarray:
    params = model["price_only"]
    values = np.array(
        [
            np.nan if features["values"][name] is None else features["values"][name]
            for name in PRICE_FEATURES
        ],
        dtype=float,
    )
    return (np.where(np.isnan(values), params["medians"], values) - params["means"]) / params[
        "scales"
    ]


def _classifier(x, labels) -> tuple[dict, LogisticRegression]:
    estimator = LogisticRegression(**FIT_SETTINGS)
    with warnings.catch_warnings():
        warnings.simplefilter("error", ConvergenceWarning)
        estimator.fit(x, labels)
    if estimator.classes_.tolist() != list(CLASSES):
        raise ValueError("classifier class order mismatch")
    return {
        "coefficients": estimator.coef_.tolist(),
        "intercepts": estimator.intercept_.tolist(),
    }, estimator


def fit_comparison(train: list[dict]) -> dict:
    if not train or any(row["split"] != "train" for row in train):
        raise ValueError("text vocabulary/classifiers fit on training rows only")
    base = fit_baselines(train)
    texts = [headline_text(row) for row in train]
    vectorizer = TfidfVectorizer(max_features=256, token_pattern=TOKEN_PATTERN)
    text_matrix = vectorizer.fit_transform(texts).toarray()
    price_matrix = np.array([_price_vector(base, row["features"]) for row in train])
    labels = [row["label"] for row in train]
    text, text_estimator = _classifier(text_matrix, labels)
    combined, combined_estimator = _classifier(np.column_stack((price_matrix, text_matrix)), labels)
    model = {
        "schema": MODEL_SCHEMA,
        "availability_tier": "FIXTURE",
        "base": base,
        "class_names": list(CLASSES),
        "vocabulary": vectorizer.get_feature_names_out().tolist(),
        "idf": vectorizer.idf_.tolist(),
        "text_only": text,
        "combined": combined,
        "training_row_hashes": [row["row_hash"] for row in train],
        "calibrators": {name: {"temperature": 1.0, "row_hashes": []} for name in MODEL_NAMES},
        "calibration_fitted": False,
        "paper_action_authorized": False,
    }
    for index, row in enumerate(train):
        raw = score_comparison(model, row, calibrated=False)
        if not np.allclose(
            raw["text_only"],
            text_estimator.predict_proba(text_matrix[index : index + 1])[0],
            atol=1e-12,
            rtol=1e-12,
        ) or not np.allclose(
            raw["combined"],
            combined_estimator.predict_proba(
                np.column_stack((price_matrix, text_matrix))[index : index + 1]
            )[0],
            atol=1e-12,
            rtol=1e-12,
        ):
            raise ValueError("portable text scoring differs from sklearn")
    return model


def validate_comparison(model: dict) -> None:
    if (
        model.get("schema") != MODEL_SCHEMA
        or model.get("availability_tier") != "FIXTURE"
        or model.get("class_names") != list(CLASSES)
        or model.get("paper_action_authorized") is not False
    ):
        raise ValueError("incompatible comparison model")
    validate_model(model["base"])
    if model["base"]["availability_tier"] != "FIXTURE":
        raise ValueError("fixture comparison cannot wrap a real model")
    words, idf = model["vocabulary"], np.asarray(model["idf"], dtype=float)
    if (
        not 1 <= len(words) <= 256
        or len(set(words)) != len(words)
        or any(not isinstance(word, str) or len(word) > 100 for word in words)
        or idf.shape != (len(words),)
        or not np.isfinite(idf).all()
        or (idf <= 0).any()
    ):
        raise ValueError("invalid text vocabulary/idf")
    for name, width in (("text_only", len(words)), ("combined", len(words) + len(PRICE_FEATURES))):
        for field, shape in (("coefficients", (3, width)), ("intercepts", (3,))):
            value = np.asarray(model[name][field], dtype=float)
            if value.shape != shape or not np.isfinite(value).all():
                raise ValueError("invalid classifier parameters")
    if set(model["calibrators"]) != set(MODEL_NAMES):
        raise ValueError("missing named calibrator")
    for calibrator in model["calibrators"].values():
        temperature = calibrator["temperature"]
        if (
            isinstance(temperature, bool)
            or not isinstance(temperature, (int, float))
            or not math.isfinite(temperature)
            or not 0.1 <= temperature <= 10
        ):
            raise ValueError("invalid calibration temperature")


def score_comparison(model: dict, item: dict, *, calibrated: bool = True) -> dict:
    validate_comparison(model)
    text = headline_text(item)
    baseline = predict_baselines(model["base"], item["features"])
    vectors = {"text_only": _tfidf(model, text)}
    vectors["combined"] = np.concatenate(
        (_price_vector(model["base"], item["features"]), vectors["text_only"])
    )
    scores = {
        name: np.array(baseline[name]["probabilities"]) for name in ("majority", "price_only")
    }
    for name, vector in vectors.items():
        scores[name] = _softmax(
            np.asarray(model[name]["coefficients"]) @ vector + model[name]["intercepts"]
        )
    if calibrated:
        if model["calibration_fitted"] is not True:
            raise ValueError("calibration has not been fitted")
        scores = {
            name: _softmax(
                np.log(np.maximum(prob, 1e-15)) / model["calibrators"][name]["temperature"]
            )
            for name, prob in scores.items()
        }
    return {name: value.tolist() for name, value in scores.items()}


def calibrate(model: dict, rows: list[dict]) -> dict:
    from copy import deepcopy

    if not rows or any(row["split"] != "validation" for row in rows):
        raise ValueError("calibration requires its held-out validation segment")
    if set(model["training_row_hashes"]) & {row["row_hash"] for row in rows}:
        raise ValueError("calibration overlaps training")
    result = deepcopy(model)
    raw = [score_comparison(model, row, calibrated=False) for row in rows]
    labels = [row["label"] for row in rows]
    for name in MODEL_NAMES:
        candidates = []
        for temperature in (0.5, 0.75, 1.0, 1.5, 2.0):
            probs = [_softmax(np.log(np.maximum(item[name], 1e-15)) / temperature) for item in raw]
            candidates.append((float(log_loss(labels, probs, labels=list(CLASSES))), temperature))
        result["calibrators"][name] = {
            "temperature": min(candidates)[1],
            "row_hashes": [row["row_hash"] for row in rows],
        }
    result["calibration_fitted"] = True
    return result


def metrics(labels: list[str], probabilities: list[list[float]]) -> dict:
    values = np.asarray(probabilities, dtype=float)
    if (
        not labels
        or values.shape != (len(labels), 3)
        or not np.isfinite(values).all()
        or (values < 0).any()
        or (values > 1).any()
        or not np.allclose(values.sum(axis=1), 1)
    ):
        raise ValueError("invalid evaluation probabilities")
    predictions = [_choose(row.tolist()) for row in values]
    one_hot = np.array([[int(label == actual) for label in CLASSES] for actual in labels])
    confidence = values.max(axis=1)
    correct = np.array([a == b for a, b in zip(labels, predictions)])
    bins, ece = [], 0.0
    for index in range(10):
        mask = (confidence >= index / 10) & (confidence < (index + 1) / 10)
        if index == 9:
            mask = (confidence >= 0.9) & (confidence <= 1)
        count = int(mask.sum())
        if count:
            accuracy, average = float(correct[mask].mean()), float(confidence[mask].mean())
            ece += count / len(labels) * abs(accuracy - average)
            bins.append({"bin": index, "rows": count, "accuracy": accuracy, "confidence": average})
    return {
        "rows": len(labels),
        "accuracy": float(accuracy_score(labels, predictions)),
        "macro_f1": float(
            f1_score(labels, predictions, labels=list(CLASSES), average="macro", zero_division=0)
        ),
        "log_loss": float(log_loss(labels, values, labels=list(CLASSES))),
        "multiclass_brier": float(np.mean(np.sum((values - one_hot) ** 2, axis=1))),
        "confusion_matrix": confusion_matrix(labels, predictions, labels=list(CLASSES)).tolist(),
        "counts": {name: labels.count(name) for name in CLASSES},
        "ece_10_bins": ece,
        "calibration_bins": bins,
    }


def evaluate_comparison(model: dict, rows: list[dict], *, split: str) -> dict:
    if (
        not rows
        or split not in {"validation", "test"}
        or any(row["split"] != split for row in rows)
    ):
        raise ValueError("evaluation needs matched held-out rows")
    used = set(model["training_row_hashes"])
    used.update(model["calibrators"]["combined"]["row_hashes"])
    if used & {row["row_hash"] for row in rows}:
        raise ValueError("evaluation overlaps fit/calibration rows")
    scores = [score_comparison(model, row) for row in rows]
    results = {
        name: metrics([row["label"] for row in rows], [item[name] for item in scores])
        for name in MODEL_NAMES
    }
    # Resample dates, not individual stocks. These intervals describe manufactured fixtures only.
    days = sorted({row["session"] for row in rows})
    rng = np.random.default_rng(123)
    for name in MODEL_NAMES:
        samples = []
        for _ in range(100):
            selected = [
                index
                for day in rng.choice(days, size=len(days), replace=True)
                for index, row in enumerate(rows)
                if row["session"] == day
            ]
            samples.append(
                metrics([rows[i]["label"] for i in selected], [scores[i][name] for i in selected])[
                    "accuracy"
                ]
            )
        results[name]["date_bootstrap_accuracy_95"] = np.quantile(samples, [0.025, 0.975]).tolist()
    return {
        "schema": MODEL_SCHEMA,
        "status": "FIXTURE_SOFTWARE_CHECK_ONLY",
        "availability_tier": "FIXTURE",
        "split": split,
        "rows": len(rows),
        "model_hash": digest(model),
        "row_hashes": [row["row_hash"] for row in rows],
        "metrics": results,
        "notice": "Manufactured relationships; NOT market accuracy",
    }
