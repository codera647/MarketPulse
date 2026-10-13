"""Isolated news/market probability experts using already-audited v2 inputs."""

from __future__ import annotations

import math
import tempfile
from copy import deepcopy
from importlib.metadata import version
from pathlib import Path

import numpy as np
from scipy.special import softmax
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

from marketpulse.baselines import CLASSES
from marketpulse.constants import STOCKS
from marketpulse.price_expert_models import IDENTITY_NAMES, expected_cutoff
from marketpulse.storage import digest
from marketpulse.v2_features import FEATURE_VERSION
from marketpulse.v2_models import class_weights, detailed_metrics
from marketpulse.v2_news import MODEL_SPEC
from marketpulse.v2_runtime import Artifacts, environment

NEWS_NAMES = (
    "earnings_consensus_missing",
    "earnings_schedule_missing",
    "news_eligible_count",
    "news_entity_relevance_mean",
    "news_event_acquisition",
    "news_event_analyst",
    "news_event_earnings",
    "news_event_guidance",
    "news_event_layoffs",
    "news_event_legal",
    "news_latest_age_hours",
    "news_meaning_missing",
    "news_sentiment_negative",
    "news_sentiment_neutral",
    "news_sentiment_positive",
    "news_truncated_count",
    "numeric_earnings_surprise",
    "scheduled_earnings_today",
)
SPY_NAMES = (
    "spy_prior_return_1d",
    "spy_prior_return_5d",
    "spy_prior_return_20d",
    "spy_prior_volatility_20d",
)
SECTOR_NAMES = (
    "sector_return_1d",
    "sector_return_5d",
    "sector_return_20d",
    "sector_volatility_20d",
    "sector_prior_coverage",
    "sector_missing",
)
RELATIVE_NAMES = tuple(
    f"{group}_relative_return_{lag}"
    for group in ("sector_spy", "company_sector")
    for lag in ("1d", "5d", "20d")
)


class ExpertAPI:
    """Frozen specialist spec plus portable fit/predict/calibration operations."""

    def __init__(self, expert: str):
        if expert not in {"news", "market"}:
            raise ValueError("unsupported context expert")
        self.EXPERT = expert
        self.SCHEMA = f"{expert}-expert-classification/1"
        self.FEATURE_NAMES = (
            (NEWS_NAMES + IDENTITY_NAMES)
            if expert == "news"
            else (SPY_NAMES + SECTOR_NAMES + IDENTITY_NAMES + RELATIVE_NAMES)
        )
        if expert == "news":
            self.FINBERT_SPEC = deepcopy(MODEL_SPEC)

    def model_environment(self) -> dict:
        result = environment()
        if self.EXPERT == "market":
            result["lightgbm"] = version("lightgbm")
        return result

    def settings(self) -> list[dict]:
        common = {"stage": f"{self.EXPERT}_only", "move_multiplier": 1.0}
        configs = [
            {**common, "family": "logistic", "C": c, "weighted": weighted}
            for c in (0.1, 1.0)
            for weighted in (False, True)
        ]
        if self.EXPERT == "market":
            configs += [
                {
                    **common,
                    "family": "lightgbm",
                    "leaves": leaves,
                    "iterations": 200,
                    "weighted": weighted,
                }
                for leaves in (15, 31)
                for weighted in (False, True)
            ]
        return configs

    def numeric(self, rows: list[dict]) -> np.ndarray:
        if not rows:
            raise ValueError("context expert needs nonempty inputs")
        result = []
        for row in rows:
            value = row["input"]
            if (
                value.get("schema") != FEATURE_VERSION
                or value.get("outcomes_loaded") is not False
                or value.get("feature_hash")
                != digest({k: v for k, v in value.items() if k != "feature_hash"})
            ):
                raise ValueError("context expert input identity/schema differs")
            symbol, session = value["symbol"], value["session"]
            if (
                symbol not in STOCKS
                or value["cutoff_utc"] != expected_cutoff(session)
                or ("base_row_hash" in row and row["base_row_hash"] != value["base_row_hash"])
                or ("symbol" in row and row["symbol"] != symbol)
                or ("session" in row and row["session"] != session)
                or any(value["market"].get(f"company_{s}") != int(symbol == s) for s in STOCKS)
            ):
                raise ValueError("context expert cutoff/company identity differs")
            values = {n: value["market"][n] for n in IDENTITY_NAMES}
            if self.EXPERT == "news":
                values.update({n: value["meaning"][n] for n in NEWS_NAMES})
                for name in ("positive", "negative", "neutral"):
                    score = values[f"news_sentiment_{name}"]
                    if score is not None and not 0 <= score <= 1:
                        raise ValueError("invalid FinBERT sentiment probability")
            else:
                values.update({n: value["price"][n] for n in SPY_NAMES})
                values.update({n: value["market"][n] for n in SECTOR_NAMES})
                for lag in ("1d", "5d", "20d"):
                    sector, spy = values[f"sector_return_{lag}"], values[f"spy_prior_return_{lag}"]
                    company = value["price"][f"prior_return_{lag}"]
                    for name, first, second in (
                        (f"sector_spy_relative_return_{lag}", sector, spy),
                        (f"company_sector_relative_return_{lag}", company, sector),
                    ):
                        if any(
                            v is not None
                            and (
                                isinstance(v, bool)
                                or not isinstance(v, (int, float))
                                or not math.isfinite(v)
                            )
                            for v in (first, second)
                        ):
                            raise ValueError("invalid relative-performance input")
                        values[name] = None if first is None or second is None else first - second
            features = [values[n] for n in self.FEATURE_NAMES]
            if any(
                v is not None
                and (isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v))
                for v in features
            ):
                raise ValueError("invalid context expert numeric feature")
            result.append([np.nan if v is None else v for v in features])
        return np.asarray(result, dtype=float)

    def fit(self, rows: list[dict], config: dict, artifacts: Artifacts) -> dict:
        if not rows or any(r["role"] != "train" for r in rows):
            raise ValueError("context expert fitting accepts training roles only")
        if config not in self.settings():
            raise ValueError("context expert configuration is not frozen")
        if len({r["base_row_hash"] for r in rows}) != len(rows):
            raise ValueError("duplicate context training rows")
        labels = [r["label"] for r in rows]
        weights = class_weights(labels, config["weighted"], 1.0)
        imputer = SimpleImputer(strategy="median", keep_empty_features=True)
        matrix = imputer.fit_transform(self.numeric(rows))
        model = {
            "schema": self.SCHEMA,
            "settings": config,
            "classes": list(CLASSES),
            "feature_names": list(self.FEATURE_NAMES),
            "medians": imputer.statistics_.tolist(),
            "training_rows": [r["base_row_hash"] for r in rows],
            "training_last_session": max(r["session"] for r in rows),
            "calibration_rows": [],
            "temperature": 1.0,
            "class_weights": weights,
            "model_environment": self.model_environment(),
            "uses_news": self.EXPERT == "news",
            "uses_market_context": self.EXPERT == "market",
            "paper_action_authorized": False,
            **({"finbert_spec": self.FINBERT_SPEC} if self.EXPERT == "news" else {}),
        }
        if config["family"] == "logistic":
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
            with threadpool_limits(limits=1):
                estimator.fit(matrix, labels)
            if max(estimator.n_iter_) >= 2000:
                raise ValueError("context logistic convergence check failed")
            model.update(
                {
                    "means": scaler.mean_.tolist(),
                    "scales": scaler.scale_.tolist(),
                    "coefficients": estimator.coef_.tolist(),
                    "intercepts": estimator.intercept_.tolist(),
                }
            )
        else:
            from lightgbm import LGBMClassifier

            estimator = LGBMClassifier(
                objective="multiclass",
                n_estimators=config["iterations"],
                num_leaves=config["leaves"],
                learning_rate=0.05,
                min_child_samples=20,
                reg_lambda=10,
                class_weight=weights,
                subsample=1.0,
                colsample_bytree=1.0,
                random_state=17,
                n_jobs=1,
                deterministic=True,
                force_col_wise=True,
                verbosity=-1,
                data_random_seed=17,
                feature_fraction_seed=17,
                bagging_seed=17,
                drop_seed=17,
            )
            estimator.fit(matrix, labels)
            with tempfile.TemporaryDirectory(
                prefix="market-expert-", dir=artifacts.root.parent
            ) as tmp:
                path = Path(tmp) / "model.lgb"
                estimator.booster_.save_model(str(path))
                model["binary_hash"] = artifacts.put_binary(path.read_bytes(), ".lgb")
            model["feature_importance"] = dict(
                zip(self.FEATURE_NAMES, [float(v) for v in estimator.feature_importances_])
            )
        if estimator.classes_.tolist() != list(CLASSES):
            raise ValueError("context expert class order differs")
        if config["family"] == "logistic":
            expected = estimator.predict_proba(matrix)
        else:
            expected = estimator.booster_.predict(matrix, num_threads=1)
        if not np.allclose(
            self.predict(model, rows, artifacts, calibrated=False), expected, rtol=1e-6, atol=1e-8
        ):
            raise ValueError("context fitted-versus-saved probability replay differs")
        return model

    def predict(
        self, model: dict, rows: list[dict], artifacts: Artifacts, *, calibrated=True
    ) -> list:
        if (
            model["schema"] != self.SCHEMA
            or model["classes"] != list(CLASSES)
            or model["feature_names"] != list(self.FEATURE_NAMES)
            or model["model_environment"] != self.model_environment()
            or model["uses_news"] != (self.EXPERT == "news")
            or model["uses_market_context"] != (self.EXPERT == "market")
            or model["paper_action_authorized"] is not False
            or (self.EXPERT == "news" and model["finbert_spec"] != self.FINBERT_SPEC)
        ):
            raise ValueError("context saved-model identity differs")
        matrix = self.numeric(rows)
        matrix = np.where(np.isnan(matrix), np.asarray(model["medians"]), matrix)
        if model["settings"]["family"] == "logistic":
            matrix = (matrix - np.asarray(model["means"])) / np.asarray(model["scales"])
            values = softmax(
                matrix @ np.asarray(model["coefficients"]).T + np.asarray(model["intercepts"]),
                axis=1,
            )
        elif model["settings"]["family"] == "lightgbm" and self.EXPERT == "market":
            from lightgbm import Booster

            estimator = Booster(model_file=str(artifacts.binary_path(model["binary_hash"], ".lgb")))
            values = estimator.predict(matrix, num_threads=1)
        else:
            raise ValueError("unsupported context model family")
        values = np.asarray(values, dtype=float)
        if (
            values.shape != (len(rows), 3)
            or not np.isfinite(values).all()
            or (values < 0).any()
            or not np.allclose(values.sum(axis=1), 1)
        ):
            raise ValueError("context expert produced invalid probabilities")
        values /= values.sum(axis=1, keepdims=True)
        if calibrated:
            temperature = model["temperature"]
            if (
                isinstance(temperature, bool)
                or not isinstance(temperature, (int, float))
                or not math.isfinite(temperature)
                or not 0.1 <= temperature <= 10
            ):
                raise ValueError("invalid context calibration temperature")
            values = softmax(np.log(np.maximum(values, 1e-15)) / temperature, axis=1)
        return values.tolist()

    def calibrate(self, model: dict, rows: list[dict], artifacts: Artifacts) -> dict:
        if (
            not rows
            or any(r["role"] != "calibration" for r in rows)
            or set(model["training_rows"]) & {r["base_row_hash"] for r in rows}
            or model["training_last_session"] >= min(r["session"] for r in rows)
        ):
            raise ValueError("context calibration must follow and exclude training")
        raw = np.asarray(self.predict(model, rows, artifacts, calibrated=False))
        losses = []
        for temperature in (0.5, 0.75, 1.0, 1.5, 2.0):
            values = softmax(np.log(np.maximum(raw, 1e-15)) / temperature, axis=1).tolist()
            losses.append((detailed_metrics(rows, values)["log_loss"], temperature))
        result = deepcopy(model)
        result["temperature"] = min(losses)[1]
        result["calibration_rows"] = [r["base_row_hash"] for r in rows]
        return result
