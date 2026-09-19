"""Desktop adapter for the frozen Phase 6A local inference runtime.

The adapter keeps the UI independent from model construction and makes the
inference service replaceable by deterministic fakes in UI tests.
"""

from __future__ import annotations

import hashlib
import importlib.util
from dataclasses import dataclass
from typing import Any

from core import normalize_sequence, validate_sequence
from ml_inference.predictor import FrozenMLPredictor, get_ml_runtime_status
from desktop.ml_metadata import BENCHMARK_ID, DEVELOPABILITY_MODEL_ID, HIC_MODEL_ID, MODEL_MANIFEST_ID


STATUS_READY = "READY"
STATUS_MODEL_ARTIFACTS_MISSING = "MODEL_ARTIFACTS_MISSING"
STATUS_ESM_MODEL_NOT_CACHED = "ESM_MODEL_NOT_CACHED"
STATUS_DEPENDENCY_MISSING = "DEPENDENCY_MISSING"
STATUS_ERROR = "ERROR"
MODEL_VERSION = "phase5-frozen-v1"


@dataclass(frozen=True)
class MLComparisonResult:
    """Numeric comparison of two independent frozen-model inferences."""

    baseline_hic: float
    mutant_hic: float
    delta_hic: float
    baseline_probability: float
    mutant_probability: float
    delta_probability: float
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "baseline": {"hic": self.baseline_hic, "probability": self.baseline_probability},
            "mutant": {"hic": self.mutant_hic, "probability": self.mutant_probability},
            "delta": {"hic": self.delta_hic, "probability": self.delta_probability},
            "metadata": dict(self.metadata),
        }


def sequence_hash(sequence: object) -> str:
    return hashlib.sha256(normalize_sequence(sequence).encode("utf-8")).hexdigest()


def prediction_cache_key(vh: object, vl: object) -> tuple[str, str, str, str, str, str]:
    return (sequence_hash(vh), sequence_hash(vl), HIC_MODEL_ID, DEVELOPABILITY_MODEL_ID, MODEL_VERSION, MODEL_MANIFEST_ID)


def build_mutation_pairs(chain: str, baseline_vh: object, baseline_vl: object, original_sequence: object, mutant_sequence: object) -> tuple[str, str, str, str]:
    """Construct baseline/mutant VH/VL pairs without mutating either baseline chain."""

    vh = normalize_sequence(baseline_vh)
    vl = normalize_sequence(baseline_vl)
    original = normalize_sequence(original_sequence)
    mutant = normalize_sequence(mutant_sequence)
    canonical_chain = str(chain or "").strip().upper()
    if canonical_chain not in {"VH", "VL"}:
        raise ValueError("Select VH or VL before running Experimental ML comparison.")
    if not vh or not vl:
        raise ValueError("Both VH and VL are required for Experimental ML comparison.")
    for chain_name, sequence in (("VH", vh), ("VL", vl), ("mutant VH", mutant if canonical_chain == "VH" else vh), ("mutant VL", mutant if canonical_chain == "VL" else vl)):
        valid, error = validate_sequence(sequence)
        if not valid:
            raise ValueError(f"Invalid {chain_name} sequence: {error}")
    if canonical_chain == "VH":
        if vh != original:
            raise ValueError("Baseline VH does not match the validated mutation comparison.")
        return vh, vl, mutant, vl
    if vl != original:
        raise ValueError("Baseline VL does not match the validated mutation comparison.")
    return vh, vl, vh, mutant


def compare_mutation_ml(service: "DesktopMLService", baseline_vh: str, baseline_vl: str, mutant_vh: str, mutant_vl: str) -> MLComparisonResult:
    """Run the same local frozen models on baseline and mutant pairs."""

    baseline = service.predict(baseline_vh, baseline_vl)
    mutant = service.predict(mutant_vh, mutant_vl)
    baseline_hic = float(baseline["hic"].get("predicted_hic") or baseline["hic"].get("predicted_value"))
    mutant_hic = float(mutant["hic"].get("predicted_hic") or mutant["hic"].get("predicted_value"))
    baseline_probability = float(baseline["developability"]["probability_not_developable"])
    mutant_probability = float(mutant["developability"]["probability_not_developable"])
    return MLComparisonResult(
        baseline_hic=baseline_hic,
        mutant_hic=mutant_hic,
        delta_hic=mutant_hic - baseline_hic,
        baseline_probability=baseline_probability,
        mutant_probability=mutant_probability,
        delta_probability=mutant_probability - baseline_probability,
        metadata={
            "model_ids": {"hic": HIC_MODEL_ID, "developability": DEVELOPABILITY_MODEL_ID},
            "model_version": MODEL_VERSION,
            "model_manifest": MODEL_MANIFEST_ID,
            "benchmark": BENCHMARK_ID,
            "baseline_vh_hash": sequence_hash(baseline_vh),
            "baseline_vl_hash": sequence_hash(baseline_vl),
            "mutant_vh_hash": sequence_hash(mutant_vh),
            "mutant_vl_hash": sequence_hash(mutant_vl),
            "mutation_effect_validation": "not_validated",
        },
    )


def _dependencies_available() -> bool:
    return all(importlib.util.find_spec(name) is not None for name in ("torch", "transformers", "pandas"))


class DesktopMLService:
    """Lazily construct and call the frozen Phase 6A predictor."""

    def __init__(self) -> None:
        self._predictor: FrozenMLPredictor | None = None
        self._prediction_cache: dict[tuple[str, str, str, str, str, str], dict[str, dict[str, Any]]] = {}

    def status(self) -> dict[str, Any]:
        try:
            status = dict(get_ml_runtime_status())
            status["dependencies_available"] = _dependencies_available()
            if not status.get("model_artifacts_available"):
                status["status"] = STATUS_MODEL_ARTIFACTS_MISSING
            elif not status["dependencies_available"]:
                status["status"] = STATUS_DEPENDENCY_MISSING
            elif not status.get("esm_cache_available"):
                status["status"] = STATUS_ESM_MODEL_NOT_CACHED
            else:
                status["status"] = STATUS_READY
            return status
        except Exception as error:
            return {"status": STATUS_ERROR, "error": str(error)}

    def predict(self, vh: str, vl: str) -> dict[str, dict[str, Any]]:
        key = prediction_cache_key(vh, vl)
        if key in self._prediction_cache:
            return self._prediction_cache[key]
        if self._predictor is None:
            self._predictor = FrozenMLPredictor()
        result = self._predictor.predict_supported_tasks(vh, vl)
        self._prediction_cache[key] = result
        return result


def status_code(status: object) -> str:
    """Read a service status while remaining friendly to injected test fakes."""

    if isinstance(status, str):
        return status
    if isinstance(status, dict):
        value = status.get("status")
        if value:
            return str(value)
        if status.get("model_artifacts_available") is False:
            return STATUS_MODEL_ARTIFACTS_MISSING
        if status.get("dependencies_available") is False:
            return STATUS_DEPENDENCY_MISSING
        if status.get("esm_cache_available") is False:
            return STATUS_ESM_MODEL_NOT_CACHED
        return STATUS_READY
    return STATUS_ERROR


def status_message(status: object) -> str:
    messages = {
        STATUS_MODEL_ARTIFACTS_MISSING: "Local ML model artifacts are not available.",
        STATUS_ESM_MODEL_NOT_CACHED: "The local sequence model is not cached. Install/download it before running ML estimates.",
        STATUS_DEPENDENCY_MISSING: "The local sequence model dependencies are not installed.",
        STATUS_ERROR: "Local ML estimates are unavailable because runtime status could not be determined.",
    }
    return messages.get(status_code(status), "")
