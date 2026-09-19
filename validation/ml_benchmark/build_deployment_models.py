"""Build the two frozen Phase 6A local inference artifacts.

Only Phase 5 TRAIN and VALIDATION inputs are read.  This module intentionally
does not load the sealed TEST labels, TEST predictions, or TEST metrics.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from validation.ml_benchmark.esm2_embeddings import (
    MODEL_NAME as ESM_MODEL_NAME,
    PAIRED_DIMENSION,
    file_sha256,
    embedding_feature_names,
)
from validation.ml_benchmark.phase5c import (
    ENDPOINTS,
    PHASE_5B_REVISION,
    ROOT,
    build_feature_blocks,
    load_phase5c_data,
)


PHASE5_FINALIZATION_COMMIT = "7826881c04887d274f73e737caf35d83e7b62dd2"
BENCHMARK = "AINTIBODY_INTERNAL_ENTITY_EXACT_V1"
MODEL_VERSION = "phase5-frozen-v1"
DEFAULT_OUTPUT_DIR = ROOT / "artifacts" / "ml_models"
FROZEN_CONFIG = ROOT / "validation/data/ml_benchmark/entity_exact_v1/modeling/selected_model_config.json"


def _sequence_hash_sha256(values: list[str]) -> str:
    return hashlib.sha256("\n".join(values).encode("utf-8")).hexdigest()


def _load_selected_hyperparameters(root: Path) -> tuple[dict[str, float], float]:
    config_path = root / "validation/data/ml_benchmark/entity_exact_v1/modeling/selected_model_config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    continuous = {
        key: float(value["alpha"])
        for key, value in config["continuous_selected"].items()
        if key.endswith("|ESM2")
    }
    hic_alpha = continuous["HIC|ESM2"]
    composite_c = float(config["classification_selected"]["ESM2"]["C"])
    if config.get("test_labels_accessed") or config.get("test_predictions_created") or config.get("test_metrics_calculated"):
        raise RuntimeError("Frozen Phase 5C config indicates TEST use")
    if set(continuous) != {f"{endpoint}|ESM2" for endpoint in ENDPOINTS}:
        raise RuntimeError("Frozen ESM2 continuous configuration is incomplete")
    return {"HIC|ESM2": hic_alpha}, composite_c


def _fit_pipeline(estimator: Any, features: np.ndarray, target: np.ndarray) -> Pipeline:
    pipeline = Pipeline([("scaler", StandardScaler()), ("estimator", estimator)])
    pipeline.fit(features, target)
    return pipeline


def _training_frame(data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    return pd.concat([data["TRAIN"], data["VALIDATION"]], ignore_index=True)


def build_deployment_models(root: str | Path = ROOT, output_dir: str | Path = DEFAULT_OUTPUT_DIR) -> dict[str, Any]:
    """Fit and write frozen local artifacts from TRAIN+VALIDATION only."""

    root_path = Path(root)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    data = load_phase5c_data(root_path)
    train_blocks, validation_blocks, _ = build_feature_blocks(root_path, data)
    selected, composite_c = _load_selected_hyperparameters(root_path)
    combined = _training_frame(data)
    combined_blocks = {
        name: np.vstack([train_blocks[name], validation_blocks[name]])
        for name in ("ESM2",)
    }
    models: dict[str, dict[str, Any]] = {}

    hic_mask = pd.to_numeric(combined["HIC"], errors="coerce").notna().to_numpy()
    hic_features = combined_blocks["ESM2"][hic_mask]
    hic_target = pd.to_numeric(combined.loc[hic_mask, "HIC"], errors="coerce").to_numpy(dtype=float)
    hic_hashes = combined.loc[hic_mask, "sequence_hash"].astype(str).tolist()
    hic_model = _fit_pipeline(Ridge(alpha=selected["HIC|ESM2"]), hic_features, hic_target)
    hic_path = output / "hic_esm2_v1.joblib"
    joblib.dump(hic_model, hic_path, compress=3)
    models["hic_esm2_v1"] = {
        "model_id": "hic_esm2_v1",
        "model_version": MODEL_VERSION,
        "task": "hic",
        "estimator": "Ridge",
        "hyperparameter": {"alpha": selected["HIC|ESM2"]},
        "feature_dimension": PAIRED_DIMENSION,
        "feature_order": embedding_feature_names(),
        "training_row_count": int(len(hic_target)),
        "training_sequence_hash_sha256": _sequence_hash_sha256(hic_hashes),
        "artifact": hic_path.name,
        "artifact_sha256": file_sha256(hic_path),
    }

    composite_mask = combined["composite_class"].notna().to_numpy()
    composite_features = combined_blocks["ESM2"][composite_mask]
    composite_target = (combined.loc[composite_mask, "composite_class"] == "NOT_DEVELOPABLE").astype(int).to_numpy()
    composite_hashes = combined.loc[composite_mask, "sequence_hash"].astype(str).tolist()
    composite_model = _fit_pipeline(
        LogisticRegression(C=composite_c, penalty="l2", solver="lbfgs", max_iter=5000, random_state=20260919),
        composite_features,
        composite_target,
    )
    composite_path = output / "developability_esm2_v1.joblib"
    joblib.dump(composite_model, composite_path, compress=3)
    models["developability_esm2_v1"] = {
        "model_id": "developability_esm2_v1",
        "model_version": MODEL_VERSION,
        "task": "developability_probability",
        "estimator": "LogisticRegression",
        "hyperparameter": {"C": composite_c, "penalty": "l2", "solver": "lbfgs"},
        "positive_class": "NOT_DEVELOPABLE",
        "feature_dimension": PAIRED_DIMENSION,
        "feature_order": embedding_feature_names(),
        "training_row_count": int(len(composite_target)),
        "training_sequence_hash_sha256": _sequence_hash_sha256(composite_hashes),
        "artifact": composite_path.name,
        "artifact_sha256": file_sha256(composite_path),
    }

    manifest = {
        "benchmark": BENCHMARK,
        "phase5_finalization_commit": PHASE5_FINALIZATION_COMMIT,
        "phase5_test_evaluation_number": 1,
        "esm_model_name": ESM_MODEL_NAME,
        "esm_model_revision": PHASE_5B_REVISION,
        "training_population_policy": "TRAIN+VALIDATION only",
        "train_rows_available": 285,
        "validation_rows_available": 96,
        "test_rows_used_for_training": 0,
        "models": models,
        "benchmark_limitations": [
            "Internal AIntibody sequence landscape benchmark.",
            "Not family-independent generalization.",
            "Experimental verification remains required.",
        ],
    }
    manifest_path = output / "model_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


if __name__ == "__main__":
    result = build_deployment_models()
    print(json.dumps(result, indent=2))
