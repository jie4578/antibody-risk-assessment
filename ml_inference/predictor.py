"""Lazy local inference for the two frozen Phase 6A ML tasks.

This module is deliberately separate from the rule engine, Agent, providers,
and Desktop UI. It loads only locally built artifacts and the frozen ESM2
representation. No sequence is sent to an external service by this runtime.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

import numpy as np

from core import normalize_sequence, validate_sequence
from validation.ml_benchmark.esm2_embeddings import file_sha256


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARTIFACT_DIR = ROOT / "artifacts" / "ml_models"
MODEL_NAME = "facebook/esm2_t30_150M_UR50D"
MODEL_REVISION = "a695f6045e2e32885fa60af20c13cb35398ce30c"
BENCHMARK = "AINTIBODY_INTERNAL_ENTITY_EXACT_V1"
PHASE5_COMMIT = "7826881c04887d274f73e737caf35d83e7b62dd2"
MODEL_VERSION = "phase5-frozen-v1"
ESM_DIMENSION = 1280


class MLInferenceError(RuntimeError):
    """Base error for local frozen-model inference."""


class InferenceInputError(ValueError, MLInferenceError):
    """Raised when VH/VL input violates the local inference contract."""


class ModelArtifactError(MLInferenceError):
    """Raised when a required local model artifact is unavailable or invalid."""


class ESMDependencyError(MLInferenceError):
    """Raised when live ESM2 dependencies are unavailable."""


class ModelRevisionError(MLInferenceError):
    """Raised when the frozen ESM2 revision cannot be loaded."""


@dataclass(frozen=True)
class HICPrediction:
    task: str
    model_id: str
    predicted_value: float
    unit: str
    scientific_status: str
    benchmark_scope: str
    experimental_verification_required: bool
    model_version: str
    training_population: str
    representation: str
    benchmark: str
    phase5_test_evidence: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["predicted_hic"] = payload["predicted_value"]
        return payload


@dataclass(frozen=True)
class DevelopabilityPrediction:
    task: str
    model_id: str
    probability_not_developable: float
    positive_class: str
    scientific_status: str
    benchmark_scope: str
    experimental_verification_required: bool
    model_version: str
    training_population: str
    representation: str
    benchmark: str
    phase5_test_evidence: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _artifact_manifest_path(artifact_dir: Path) -> Path:
    return artifact_dir / "model_manifest.json"


def _read_manifest(artifact_dir: Path) -> dict[str, Any]:
    path = _artifact_manifest_path(artifact_dir)
    if not path.exists():
        raise ModelArtifactError(
            f"Frozen ML model artifacts are missing: {path}. "
            "Run validation.ml_benchmark.build_deployment_models first."
        )
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ModelArtifactError(f"Could not read ML model manifest: {path}") from error
    if manifest.get("benchmark") != BENCHMARK or manifest.get("phase5_finalization_commit") != PHASE5_COMMIT:
        raise ModelArtifactError("ML model manifest does not match the frozen Phase 5 provenance")
    if manifest.get("esm_model_revision") != MODEL_REVISION or manifest.get("esm_model_name") != MODEL_NAME:
        raise ModelArtifactError("ML model manifest ESM2 provenance does not match the frozen contract")
    for model_id, details in manifest.get("models", {}).items():
        artifact = artifact_dir / str(details.get("artifact", ""))
        expected_hash = str(details.get("artifact_sha256", ""))
        if not artifact.exists() or not expected_hash or file_sha256(artifact) != expected_hash:
            raise ModelArtifactError(f"ML model artifact hash verification failed: {model_id}")
    return manifest


def _validate_inputs(vh: object, vl: object) -> tuple[str, str]:
    normalized: list[str] = []
    for chain, value in (("VH", vh), ("VL", vl)):
        sequence = normalize_sequence(value)
        valid, error = validate_sequence(sequence)
        if not valid:
            raise InferenceInputError(f"Invalid {chain} sequence: {error}")
        normalized.append(sequence)
    return normalized[0], normalized[1]


def _cached_esm_snapshot_exists() -> bool:
    cache_root = Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface"))
    model_root = cache_root / "hub" / "models--facebook--esm2_t30_150M_UR50D" / "snapshots" / MODEL_REVISION
    if not model_root.exists():
        return False
    config = model_root / "config.json"
    weights = any((model_root / name).exists() for name in ("pytorch_model.bin", "model.safetensors", "pytorch_model.bin.index.json"))
    return config.exists() and weights


def get_ml_runtime_status(artifact_dir: str | Path = DEFAULT_ARTIFACT_DIR) -> dict[str, Any]:
    """Return availability metadata without loading models or predicting."""

    directory = Path(artifact_dir)
    manifest_path = _artifact_manifest_path(directory)
    artifacts_available = manifest_path.exists()
    model_versions: dict[str, str] = {}
    if artifacts_available:
        try:
            manifest = _read_manifest(directory)
            model_versions = {
                model_id: str(details.get("model_version", MODEL_VERSION))
                for model_id, details in manifest.get("models", {}).items()
            }
        except MLInferenceError:
            artifacts_available = False
    try:
        import torch

        device = "cuda" if bool(torch.cuda.is_available()) else "cpu"
    except ImportError:
        device = "cpu"
    return {
        "model_artifacts_available": artifacts_available,
        "esm_cache_available": _cached_esm_snapshot_exists(),
        "device": device,
        "supported_tasks": ["hic", "developability"],
        "model_versions": model_versions,
        "esm_model": MODEL_NAME,
        "esm_revision": MODEL_REVISION,
    }


class FrozenMLPredictor:
    """Lazy-loading predictor for the frozen HIC and composite models."""

    def __init__(
        self,
        artifact_dir: str | Path = DEFAULT_ARTIFACT_DIR,
        *,
        embedding_loader: Callable[[str, str], np.ndarray] | None = None,
        model_loader: Callable[[Path], Any] | None = None,
    ) -> None:
        self.artifact_dir = Path(artifact_dir)
        self._embedding_loader = embedding_loader
        self._model_loader = model_loader
        self._manifest: dict[str, Any] | None = None
        self._models: dict[str, Any] = {}
        self._esm_runtime: tuple[Any, Any, Any, Any] | None = None

    def _get_manifest(self) -> dict[str, Any]:
        if self._manifest is None:
            self._manifest = _read_manifest(self.artifact_dir)
        return self._manifest

    def _load_model(self, model_id: str) -> Any:
        if model_id not in self._models:
            manifest = self._get_manifest()
            details = manifest.get("models", {}).get(model_id)
            if not details:
                raise ModelArtifactError(f"Model is not registered in the frozen manifest: {model_id}")
            path = self.artifact_dir / str(details["artifact"])
            if not path.exists():
                raise ModelArtifactError(f"Model artifact is missing: {path}")
            try:
                loader = self._model_loader
                if loader is None:
                    import joblib

                    loader = joblib.load
                model = loader(path)
            except Exception as error:
                raise ModelArtifactError(f"Could not load model artifact: {model_id}") from error
            self._models[model_id] = model
        return self._models[model_id]

    def _embed(self, vh: str, vl: str) -> np.ndarray:
        if self._embedding_loader is not None:
            embedding = np.asarray(self._embedding_loader(vh, vl), dtype=np.float32)
        else:
            try:
                import torch
                from validation.ml_benchmark.esm2_embeddings import (
                    extract_paired_embeddings,
                    load_frozen_model,
                )
            except ImportError as error:
                raise ESMDependencyError("torch and transformers are required for local ESM2 inference") from error
            if self._esm_runtime is None:
                try:
                    tokenizer, model, revision, provenance = load_frozen_model(
                        MODEL_NAME,
                        revision=MODEL_REVISION,
                    )
                except Exception as error:
                    raise ModelRevisionError(
                        f"Could not load frozen ESM2 revision {MODEL_REVISION}; "
                        "ensure the model is cached or available for download."
                    ) from error
                if revision != MODEL_REVISION:
                    raise ModelRevisionError("Loaded ESM2 revision differs from the frozen revision")
                self._esm_runtime = (tokenizer, model, torch, torch.device(provenance["device"]))
            tokenizer, model, torch_module, device = self._esm_runtime
            import pandas as pd

            frame = pd.DataFrame({"sequence_hash": ["inference"], "VH": [vh], "VL": [vl]})
            try:
                embedding = extract_paired_embeddings(frame, tokenizer, model, torch_module, device).paired_embeddings
            except Exception as error:
                raise MLInferenceError(f"Local ESM2 inference failed: {error}") from error
        if embedding.shape != (1, ESM_DIMENSION) or not np.isfinite(embedding).all():
            raise MLInferenceError(f"Expected one finite ESM2 embedding with shape (1, {ESM_DIMENSION})")
        return embedding

    def predict_hic(self, vh: object, vl: object) -> HICPrediction:
        normalized_vh, normalized_vl = _validate_inputs(vh, vl)
        model = self._load_model("hic_esm2_v1")
        prediction = float(model.predict(self._embed(normalized_vh, normalized_vl))[0])
        details = self._get_manifest()["models"]["hic_esm2_v1"]
        return HICPrediction(
            task="hic",
            model_id="hic_esm2_v1",
            predicted_value=prediction,
            unit="benchmark HIC retention-time scale",
            scientific_status="research_support",
            benchmark_scope="AIntibody internal sequence landscape",
            experimental_verification_required=True,
            model_version=str(details["model_version"]),
            training_population=f"TRAIN+VALIDATION only (N={details['training_row_count']})",
            representation="ESM2 paired VH/VL, VH||VL, 1280 dimensions",
            benchmark=BENCHMARK,
            phase5_test_evidence={"spearman": 0.834662, "r2": 0.625834, "n": 72},
        )

    def predict_developability(self, vh: object, vl: object) -> DevelopabilityPrediction:
        normalized_vh, normalized_vl = _validate_inputs(vh, vl)
        model = self._load_model("developability_esm2_v1")
        probability = float(model.predict_proba(self._embed(normalized_vh, normalized_vl))[0, 1])
        if not 0.0 <= probability <= 1.0:
            raise MLInferenceError("Composite model returned a probability outside [0, 1]")
        details = self._get_manifest()["models"]["developability_esm2_v1"]
        return DevelopabilityPrediction(
            task="developability",
            model_id="developability_esm2_v1",
            probability_not_developable=probability,
            positive_class="NOT_DEVELOPABLE",
            scientific_status="research_support",
            benchmark_scope="AIntibody internal sequence landscape",
            experimental_verification_required=True,
            model_version=str(details["model_version"]),
            training_population=f"TRAIN+VALIDATION only (N={details['training_row_count']})",
            representation="ESM2 paired VH/VL, VH||VL, 1280 dimensions",
            benchmark=BENCHMARK,
            phase5_test_evidence={"pr_auc": 0.611665, "roc_auc": 0.691468, "prevalence": 0.336842, "n": 95},
        )

    def predict_supported_tasks(self, vh: object, vl: object) -> dict[str, dict[str, Any]]:
        return {
            "hic": self.predict_hic(vh, vl).to_dict(),
            "developability": self.predict_developability(vh, vl).to_dict(),
        }
