"""Separate boosting experiment using the existing verified target/input funnel."""

from __future__ import annotations

import json
from pathlib import Path

from marketpulse import boosting_models
from marketpulse.regression_pipeline import bounded_source, train
from marketpulse.storage import digest
from marketpulse.v2_features import FEATURE_VERSION
from marketpulse.v2_runtime import Artifacts, check_receipt, owned_run


def build(source: Path, root: Path, release_hash: str, *, evidence: str, progress=None) -> dict:
    if (source.resolve() == root.resolve() or not isinstance(evidence, str)
            or not 1 <= len(evidence.strip()) <= 500):
        raise ValueError("separate boosting directory and bounded authorization required")
    status = root / "v2-status.json"
    if status.exists() and json.loads(status.read_text())["schema"] != boosting_models.MODEL_SCHEMA:
        raise ValueError("existing data root belongs to another experiment")
    binding = {
        "schema": boosting_models.MODEL_SCHEMA, "source_release_hash": release_hash,
        "evidence": evidence, "configurations": boosting_models.settings(),
        "feature_version": FEATURE_VERSION,
        "model_environment": boosting_models.model_environment(),
    }
    with owned_run(root, binding, progress) as checkpoint:
        checkpoint({"schema": boosting_models.MODEL_SCHEMA, "stage": "VERIFYING_BOOSTING_SOURCE"})
        saved = bounded_source(
            source, root, release_hash,
            lambda event: checkpoint({**event, "schema": boosting_models.MODEL_SCHEMA}))
        check_receipt(root, saved)
        result = train(
            root, source, Artifacts(root / "artifacts").get(saved["rows_hash"]),
            release_hash, checkpoint, model_api=boosting_models)
        result["source_release_hash"] = release_hash
        result["build_binding_hash"] = digest(binding)
        checkpoint(result)
        return result
