"""Desktop adapter for the frozen Phase 6A local inference runtime.

The adapter keeps the UI independent from model construction and makes the
inference service replaceable by deterministic fakes in UI tests.
"""

from __future__ import annotations

import importlib.util
from typing import Any

from ml_inference.predictor import FrozenMLPredictor, get_ml_runtime_status


STATUS_READY = "READY"
STATUS_MODEL_ARTIFACTS_MISSING = "MODEL_ARTIFACTS_MISSING"
STATUS_ESM_MODEL_NOT_CACHED = "ESM_MODEL_NOT_CACHED"
STATUS_DEPENDENCY_MISSING = "DEPENDENCY_MISSING"
STATUS_ERROR = "ERROR"


def _dependencies_available() -> bool:
    return all(importlib.util.find_spec(name) is not None for name in ("torch", "transformers", "pandas"))


class DesktopMLService:
    """Lazily construct and call the frozen Phase 6A predictor."""

    def __init__(self) -> None:
        self._predictor: FrozenMLPredictor | None = None

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
        if self._predictor is None:
            self._predictor = FrozenMLPredictor()
        return self._predictor.predict_supported_tasks(vh, vl)


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
