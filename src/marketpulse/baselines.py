"""Baseline fitting and JSON scoring; real data enters only through reviewed loaders."""

from __future__ import annotations

import math
import warnings
from collections import Counter, defaultdict
from datetime import date, timedelta
from importlib.metadata import version
from pathlib import Path

import numpy as np
from sklearn.exceptions import ConvergenceWarning
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, log_loss
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from trailforge.ports import AdapterCapabilities, FunctionAdapter, VerifiedResult
from trailforge.runtime import Goal, Harness, Task

from marketpulse.baseline_fixtures import FIXTURE_VERSION, generate_fixture_catalog
from marketpulse.clock import session_window, utc_iso
from marketpulse.constants import STOCKS
from marketpulse.features import FEATURE_NAMES, FEATURE_SCHEMA, _expected_prior_dates
from marketpulse.labels import _threshold, classify_return
from marketpulse.storage import RawStore, canonical_bytes, digest

BASELINE_VERSION = "baseline-experiment/1"
CLASSES = ("DOWN", "NO_MATERIAL_MOVE", "UP")
TIE_PRIORITY = ("NO_MATERIAL_MOVE", "DOWN", "UP")
PRICE_FEATURES = tuple(name for name in FEATURE_NAMES
                       if name.startswith(("prior_", "spy_prior_")))
FIT_SETTINGS = {"C": 1.0, "solver": "lbfgs", "max_iter": 2000, "tol": 0.000001,
                "random_state": 17, "class_weight": None}


def validate_features(features: dict, *, availability_tier: str = "FIXTURE") -> None:
    if availability_tier not in {"FIXTURE", "HISTORICAL_APPROXIMATE"}:
        raise ValueError("unsupported baseline availability tier")
    if (features.get("feature_schema") != FEATURE_SCHEMA
            or features.get("feature_names") != list(FEATURE_NAMES)
            or set(features.get("values", {})) != set(FEATURE_NAMES)
            or features.get("availability_tier") != availability_tier):
        raise ValueError("baseline feature schema or availability tier mismatch")
    values = features["values"]
    if any(value is not None and (isinstance(value, bool)
                                 or not isinstance(value, (int, float))
                                 or not math.isfinite(value)) for value in values.values()):
        raise ValueError("invalid or nonfinite feature value")
    if digest({"schema": FEATURE_SCHEMA, "snapshot_hash": features["snapshot_hash"],
               "values": [values[name] for name in FEATURE_NAMES]}) != features["feature_hash"]:
        raise ValueError("feature identity mismatch")
    window = session_window(date.fromisoformat(features["session"]))
    expected_dates = [day.isoformat() for day in _expected_prior_dates(window.session)]
    if (features["cutoff_utc"] != utc_iso(window.cutoff)
            or features["source_bar_dates"] != expected_dates
            or features["spy_bar_dates"] != expected_dates):
        raise ValueError("baseline feature cutoff or prior-session coverage mismatch")


def selected_rows(store: RawStore, catalog_hash: str) -> tuple[list[dict], list[dict]]:
    """Validate the roster, then open train/validation artifacts ONLY, never test rows."""
    from decimal import Decimal

    catalog = store.get(catalog_hash)
    if catalog.get("schema") != FIXTURE_VERSION or catalog.get("availability_tier") != "FIXTURE":
        raise ValueError("real-data training requires a promoted M03 dataset; fixture-only path")
    entries = catalog["rows"]
    if not isinstance(entries, list) or not 18 <= len(entries) <= 600:
        raise ValueError("fixture catalog exceeds bounded row count")
    seen, groups, dates = set(), defaultdict(set), defaultdict(set)
    row_hashes = set()
    for entry in entries:
        split, day, symbol = entry["split"], entry["session"], entry["symbol"]
        if split not in {"train", "validation", "test"} or symbol not in STOCKS:
            raise ValueError("unexpected fixture split or symbol")
        key = entry["row_hash"]
        if (not isinstance(key, str) or len(key) != 64
                or any(char not in "0123456789abcdef" for char in key) or key in row_hashes):
            raise ValueError("invalid or duplicated fixture row reference")
        row_hashes.add(key)
        session_window(date.fromisoformat(day))
        if (day, symbol) in seen:
            raise ValueError("duplicate company/date row")
        seen.add((day, symbol))
        groups[day].add(split)
        dates[split].add(day)
    if (set(dates) != {"train", "validation", "test"}
            or any(len(group) != 1 for group in groups.values())
            or max(dates["train"]) >= min(dates["validation"])
            or max(dates["validation"]) >= min(dates["test"])):
        raise ValueError("splits must keep date groups together and be chronological")
    if any({symbol for day, symbol in seen if day == current} != set(STOCKS)
           for current in groups):
        raise ValueError("incomplete six-company date group")
    for earlier, later in (("train", "validation"), ("validation", "test")):
        if date.fromisoformat(min(dates[later])) <= session_window(
                date.fromisoformat(max(dates[earlier]))).session + timedelta(days=1):
            raise ValueError("missing chronological split-boundary gap")
        from marketpulse.dataset import market_sessions

        if len(market_sessions(date.fromisoformat(max(dates[earlier])),
                               date.fromisoformat(min(dates[later])))) < 3:
            raise ValueError("at least one exchange session must be embargoed")
    results = {"train": [], "validation": []}
    for entry in entries:
        if entry["split"] == "test":
            continue
        row = store.get(entry["row_hash"])
        if (row.get("schema") != FIXTURE_VERSION or row.get("availability_tier") != "FIXTURE"
                or any(row.get(name) != entry[name] for name in ("session", "symbol", "split"))
                or row.get("label") not in CLASSES
                or row.get("threshold") != "0.01"
                or row["features"]["session"] != row["session"]
                or row["features"]["symbol"] != row["symbol"]
                or row["label"] != classify_return(Decimal(row["return_fraction"]),
                                                    _threshold(row["threshold"]))):
            raise ValueError("fixture row/label identity mismatch")
        validate_features(row["features"])
        results[entry["split"]].append({**row, "row_hash": entry["row_hash"]})
    return (sorted(results["train"], key=lambda row: (row["session"], row["symbol"])),
            sorted(results["validation"], key=lambda row: (row["session"], row["symbol"])))


def _matrix(rows: list[dict]) -> np.ndarray:
    return np.array([[np.nan if row["features"]["values"][name] is None else
                      row["features"]["values"][name] for name in PRICE_FEATURES]
                     for row in rows], dtype=float)


def _choose(probabilities: list[float]) -> str:
    best = max(probabilities)
    return next(label for label in TIE_PRIORITY if probabilities[CLASSES.index(label)] == best)


def fit_baselines(train: list[dict], *, availability_tier: str = "FIXTURE") -> dict:
    if not train or any(row["split"] != "train" for row in train):
        raise ValueError("fit accepts training rows only")
    for row in train:
        validate_features(row["features"], availability_tier=availability_tier)
    counts = Counter(row["label"] for row in train)
    if set(counts) != set(CLASSES) or min(counts.values()) < 2:
        raise ValueError("price baseline requires at least two training rows per class")
    x_train = _matrix(train)
    if np.isnan(x_train).all(axis=0).any():
        raise ValueError("all-missing training price feature is not silently dropped")
    estimator = Pipeline([
        ("imputer", SimpleImputer(strategy="median", keep_empty_features=True)),
        ("scaler", StandardScaler()),
        ("classifier", LogisticRegression(**FIT_SETTINGS)),
    ])
    with warnings.catch_warnings():
        warnings.simplefilter("error", ConvergenceWarning)
        estimator.fit(x_train, [row["label"] for row in train])
    imputer, scaler, classifier = (estimator.named_steps[name] for name in
                                    ("imputer", "scaler", "classifier"))
    if classifier.classes_.tolist() != list(CLASSES):
        raise ValueError("classifier class order mismatch")
    priors = [counts[label] / len(train) for label in CLASSES]
    model = {
        "schema": BASELINE_VERSION, "availability_tier": availability_tier,
        "feature_schema": FEATURE_SCHEMA, "class_names": list(CLASSES),
        "price_feature_names": list(PRICE_FEATURES),
        "training_row_hashes": [row["row_hash"] for row in train],
        "training_counts": {label: counts[label] for label in CLASSES},
        "sklearn_version": version("scikit-learn"), "fit_settings": dict(FIT_SETTINGS),
        "majority": {"class": _choose(priors), "probabilities": priors},
        "price_only": {"medians": imputer.statistics_.tolist(),
                       "means": scaler.mean_.tolist(), "scales": scaler.scale_.tolist(),
                       "coefficients": classifier.coef_.tolist(),
                       "intercepts": classifier.intercept_.tolist()},
        "calibrated": False, "paper_action_authorized": False,
    }
    validate_model(model)
    replayed = np.array([predict_baselines(model, row["features"])["price_only"]["probabilities"]
                         for row in train])
    if not np.allclose(replayed, estimator.predict_proba(x_train), atol=1e-12, rtol=1e-12):
        raise ValueError("JSON scoring does not match fitted sklearn pipeline")
    return model


def validate_model(model: dict) -> None:
    if (model.get("schema") != BASELINE_VERSION
            or model.get("availability_tier") not in {"FIXTURE", "HISTORICAL_APPROXIMATE"}
            or model.get("feature_schema") != FEATURE_SCHEMA
            or model.get("class_names") != list(CLASSES)
            or model.get("price_feature_names") != list(PRICE_FEATURES)
            or model.get("fit_settings") != FIT_SETTINGS
            or model.get("calibrated") is not False
            or model.get("paper_action_authorized") is not False):
        raise ValueError("incompatible or unauthorized baseline model")
    n_features = len(PRICE_FEATURES)
    for field, shape in (("medians", (n_features,)), ("means", (n_features,)),
                         ("scales", (n_features,)), ("coefficients", (3, n_features)),
                         ("intercepts", (3,))):
        values = np.asarray(model["price_only"][field], dtype=float)
        if values.shape != shape or not np.isfinite(values).all():
            raise ValueError("invalid model dimensions or nonfinite parameters")
    if (np.asarray(model["price_only"]["scales"]) <= 0).any():
        raise ValueError("invalid model scale")
    probabilities = model["majority"]["probabilities"]
    if (len(probabilities) != 3 or any(not math.isfinite(p) or not 0 <= p <= 1
                                     for p in probabilities)
            or not math.isclose(sum(probabilities), 1, abs_tol=1e-12)
            or model["majority"]["class"] != _choose(probabilities)):
        raise ValueError("invalid majority distribution")


def predict_baselines(model: dict, features: dict) -> dict:
    """Shared scoring with matching data tiers; no pickle loading or paper authority."""
    validate_model(model)
    validate_features(features, availability_tier=model["availability_tier"])
    price = model["price_only"]
    inputs = np.array([np.nan if features["values"][name] is None else features["values"][name]
                       for name in PRICE_FEATURES], dtype=float)
    imputed = np.where(np.isnan(inputs), price["medians"], inputs)
    with np.errstate(over="raise", invalid="raise", divide="raise"):
        transformed = (imputed - price["means"]) / price["scales"]
        scores = np.asarray(price["coefficients"]) @ transformed + price["intercepts"]
        probabilities = np.exp(scores - np.max(scores))
        probabilities /= probabilities.sum()
    if not np.isfinite(probabilities).all():
        raise ValueError("nonfinite baseline probabilities")
    probs = probabilities.tolist()
    return {
        "class_names": list(CLASSES), "availability_tier": model["availability_tier"],
        "majority": {"class": model["majority"]["class"],
                     "probabilities": list(model["majority"]["probabilities"])},
        "price_only": {"class": _choose(probs), "probabilities": probs},
        "calibrated": False, "paper_action_authorized": False,
    }


def validation_report(model: dict, train: list[dict], validation: list[dict]) -> dict:
    if not validation or any(row["split"] != "validation" for row in validation):
        raise ValueError("evaluation accepts validation rows only; final test is locked")
    if model["training_row_hashes"] != [row["row_hash"] for row in train]:
        raise ValueError("model training lineage mismatch")
    predicted = [predict_baselines(model, row["features"]) for row in validation]
    truth = [row["label"] for row in validation]
    metrics = {}
    for name in ("majority", "price_only"):
        labels = [item[name]["class"] for item in predicted]
        probabilities = np.array([item[name]["probabilities"] for item in predicted])
        one_hot = np.array([[int(label == actual) for label in CLASSES] for actual in truth])
        metrics[name] = {
            "accuracy": float(accuracy_score(truth, labels)),
            "macro_f1": float(f1_score(truth, labels, labels=list(CLASSES),
                                       average="macro", zero_division=0)),
            "log_loss": float(log_loss(truth, probabilities, labels=list(CLASSES))),
            "multiclass_brier": float(np.mean(np.sum((probabilities - one_hot) ** 2, axis=1))),
            "confusion_matrix": confusion_matrix(truth, labels, labels=list(CLASSES)).tolist(),
            "by_ticker": {
                symbol: {"rows": sum(row["symbol"] == symbol for row in validation),
                         "correct": sum(row["symbol"] == symbol and labels[index] == row["label"]
                                        for index, row in enumerate(validation))}
                for symbol in STOCKS
            },
        }
    return {
        "schema": BASELINE_VERSION,
        "status": ("FIXTURE_SOFTWARE_CHECK_ONLY" if model["availability_tier"] == "FIXTURE"
                   else "HISTORICAL_RESEARCH_VALIDATION"),
        "availability_tier": model["availability_tier"], "model_hash": digest(model),
        "class_names": list(CLASSES), "train_rows": len(train),
        "validation_rows": len(validation),
        "validation_row_hashes": [row["row_hash"] for row in validation],
        "validation_counts": {label: truth.count(label) for label in CLASSES},
        "metrics": metrics, "final_test_opened": False,
        "calibrated": False, "paper_action_authorized": False,
        "notice": ("Artificial fixture relationships; these scores are not market accuracy"
                   if model["availability_tier"] == "FIXTURE" else
                   "Approximate historical replay; uncalibrated, not investment advice"),
    }


def run_baseline_demo(data_dir: Path, *, seed: int = 42) -> dict:
    store = RawStore(data_dir / "baseline-artifacts")
    catalog_hash = generate_fixture_catalog(store, seed=seed)
    return _run_baseline_experiment(data_dir, catalog_hash,
                                    lambda: selected_rows(store, catalog_hash))


def _run_baseline_experiment(data_dir: Path, catalog_hash: str, row_loader, *,
                             availability_tier: str = "FIXTURE",
                             dataset_binding: dict | None = None) -> dict:
    """Trusted host runner. The research entry point supplies the reviewed-data loader."""
    if availability_tier not in {"FIXTURE", "HISTORICAL_APPROXIMATE"}:
        raise ValueError("unsupported experiment tier")
    store = RawStore(data_dir / "baseline-artifacts")
    binding = {"version": BASELINE_VERSION, "catalog_hash": catalog_hash,
               "feature_schema": FEATURE_SCHEMA, "price_features": list(PRICE_FEATURES),
               "fit_settings": dict(FIT_SETTINGS), "sklearn_version": version("scikit-learn"),
               "numpy_version": version("numpy"), "data_mode": availability_tier}
    if dataset_binding is not None:
        binding["dataset_binding"] = dataset_binding
    job_key = digest(binding)
    result_store = RawStore(data_dir / "baseline-results")

    def fitted(train):
        # Preserve the fixture callback contract and never relabel real features as fixtures.
        return (fit_baselines(train) if availability_tier == "FIXTURE" else
                fit_baselines(train, availability_tier=availability_tier))

    def fit(request):
        train, _ = row_loader()
        return {"model_hash": store.put(fitted(train))}

    def evaluate(request):
        train, validation = row_loader()
        model = store.get(request.dependencies["fit"]["model_hash"])
        return {"report_hash": store.put(validation_report(model, train, validation))}

    def verify(request):
        try:
            train, validation = row_loader()
            model = store.get(request.dependencies["fit"]["model_hash"])
            report = store.get(request.dependencies["evaluate"]["report_hash"])
            # Refit from training references only and recompute validation; candidate JSON
            # does not authorize its own completion. This checks software, not market skill.
            if (model != fitted(train)
                    or report != validation_report(model, train, validation)):
                raise ValueError("model/report replay mismatch")
            return VerifiedResult("PASS", request.goal_digest,
                                  {"data_mode": availability_tier, "train_rows": len(train),
                                   "validation_rows": len(validation), "final_test_opened": False})
        except (KeyError, TypeError, ValueError, FloatingPointError, ConvergenceWarning):
            return VerifiedResult("FAIL", request.goal_digest, {"reason": "baseline_check_failed"})
        except OSError:
            return VerifiedResult("UNKNOWN", request.goal_digest,
                                  {"reason": "artifact_unavailable"})

    prefix = ("marketpulse.baseline" if availability_tier == "FIXTURE" else
              "marketpulse.research_baseline")
    adapters = [
        FunctionAdapter(AdapterCapabilities(f"{prefix}_fit/1", "MODEL",
                                            "CANDIDATE_WRITE"), fit),
        FunctionAdapter(AdapterCapabilities(f"{prefix}_evaluate/1", "TOOL",
                                            "CANDIDATE_WRITE"), evaluate),
        FunctionAdapter(AdapterCapabilities(f"{prefix}_verify/1", "VERIFY", "PURE"),
                        verify),
    ]
    mode = "fixture" if availability_tier == "FIXTURE" else "research"
    goal = Goal("local-demo", f"marketpulse:baseline_{mode}:{job_key}",
                ("Verify synthetic majority and price-only baseline software" if mode == "fixture"
                 else "Verify reviewed historical majority and price-only baselines"),
                (Task("fit", f"{prefix}_fit/1", binding),
                 Task("evaluate", f"{prefix}_evaluate/1", binding, ("fit",)),
                 Task("verify", f"{prefix}_verify/1", binding, ("fit", "evaluate"))),
                ("verify",), allowed_effects=("PURE", "CANDIDATE_WRITE"), budget_units=6)
    harness = Harness(data_dir / "baseline-trailforge.sqlite3", tenant_id=goal.tenant_id,
                      resource_id=goal.resource_id, adapters=adapters, lease_seconds=180,
                      tenant_limit=100000, global_limit=1000000)
    # A small application job index keeps known run IDs without sharing harness transactions.
    from marketpulse.storage import ExtractionStore

    index = ExtractionStore(data_dir / "baseline-jobs.sqlite3")
    index.reserve_job(job_key, availability_tier)
    prior = index.get_job(job_key)
    run_id = prior["run_id"] or harness.start(goal)
    if prior["run_id"] is None:
        index.set_run_id(job_key, run_id)
    record = harness.advance(run_id, goal)
    if record["state"] != "COMPLETED":
        index.set_status(job_key, record["state"])
        return {"state": record["state"], "run_id": run_id, "job_key": job_key,
                "availability_tier": availability_tier, "paper_action_authorized": False}
    model_hash = record["tasks"]["fit"]["result"]["model_hash"]
    report_hash = record["tasks"]["evaluate"]["result"]["report_hash"]
    train, validation = row_loader()
    model, report = store.get(model_hash), store.get(report_hash)
    if (model != fitted(train) or report != validation_report(model, train, validation)):
        raise ValueError("stored model or validation report mismatch")
    result = {
        "state": "COMPLETE", "status": report["status"], "binding": binding,
        "job_key": job_key, "run_id": run_id, "catalog_hash": catalog_hash,
        "model_hash": model_hash, "validation_report_hash": report_hash,
        "train_rows": len(train), "validation_rows": len(validation),
        "final_test_opened": False, "availability_tier": availability_tier,
        "trailforge_verify_receipt": record["tasks"]["verify"]["receipt"]["receipt_id"],
        "paper_action_authorized": False,
    }
    result_hash = result_store.put(result)
    with index.connect() as db:
        db.execute("UPDATE extraction_jobs SET status='COMPLETE',manifest_json=? WHERE job_key=?",
                   (canonical_bytes({"result_hash": result_hash}).decode(), job_key))
    return {**result, "result_hash": result_hash}
