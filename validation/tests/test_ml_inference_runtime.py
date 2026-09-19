from __future__ import annotations

import hashlib
import json
from pathlib import Path

import joblib
import numpy as np
import pytest

from ml_inference.predictor import FrozenMLPredictor, InferenceInputError, MODEL_NAME, MODEL_REVISION, get_ml_runtime_status
from validation.ml_benchmark.build_deployment_models import build_deployment_models
from validation.ml_benchmark.esm2_embeddings import file_sha256


ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def built_models(tmp_path_factory: pytest.TempPathFactory) -> Path:
    output = tmp_path_factory.mktemp("phase6a_models")
    build_deployment_models(output_dir=output)
    return output


def _embedding(value_vh: str, value_vl: str) -> np.ndarray:
    del value_vh, value_vl
    return np.linspace(0.0, 1.0, 1280, dtype=np.float32).reshape(1, -1)


def test_frozen_model_manifest_and_authoritative_hyperparameters(built_models: Path) -> None:
    manifest = json.loads((built_models / "model_manifest.json").read_text(encoding="utf-8"))
    config = json.loads(
        (ROOT / "validation/data/ml_benchmark/entity_exact_v1/modeling/selected_model_config.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["benchmark"] == "AINTIBODY_INTERNAL_ENTITY_EXACT_V1"
    assert manifest["phase5_finalization_commit"] == "7826881c04887d274f73e737caf35d83e7b62dd2"
    assert manifest["esm_model_name"] == MODEL_NAME
    assert manifest["esm_model_revision"] == MODEL_REVISION
    assert manifest["test_rows_used_for_training"] == 0
    assert manifest["models"]["hic_esm2_v1"]["hyperparameter"]["alpha"] == config["continuous_selected"]["HIC|ESM2"]["alpha"]
    assert manifest["models"]["developability_esm2_v1"]["hyperparameter"]["C"] == config["classification_selected"]["ESM2"]["C"]
    assert manifest["models"]["hic_esm2_v1"]["feature_dimension"] == 1280
    assert manifest["models"]["developability_esm2_v1"]["feature_dimension"] == 1280
    assert manifest["models"]["hic_esm2_v1"]["training_row_count"] == 355
    assert manifest["models"]["developability_esm2_v1"]["training_row_count"] == 378


def test_artifact_hashes_and_training_hashes_are_recorded(built_models: Path) -> None:
    manifest = json.loads((built_models / "model_manifest.json").read_text(encoding="utf-8"))
    for model_id, details in manifest["models"].items():
        artifact = built_models / details["artifact"]
        assert artifact.exists()
        assert details["artifact_sha256"] == file_sha256(artifact)
        assert len(details["training_sequence_hash_sha256"]) == 64
        assert len(details["feature_order"]) == 1280


def test_builder_does_not_reference_or_load_sealed_test_labels() -> None:
    source = (ROOT / "validation/ml_benchmark/build_deployment_models.py").read_text(encoding="utf-8")
    assert "sealed_test_labels.csv" not in source
    assert "final_test" not in source
    assert "TEST_LABEL_PATH" not in source


def test_runtime_is_lazy_and_keeps_vh_before_vl(built_models: Path) -> None:
    calls: list[tuple[str, str]] = []
    loaded: list[Path] = []

    def embedding_loader(vh: str, vl: str) -> np.ndarray:
        calls.append((vh, vl))
        return _embedding(vh, vl)

    def model_loader(path: Path):
        loaded.append(path)
        return joblib.load(path)

    predictor = FrozenMLPredictor(
        built_models,
        embedding_loader=embedding_loader,
        model_loader=model_loader,
    )
    assert loaded == []
    result = predictor.predict_hic(" vhac ", "vlac")
    assert loaded == [built_models / "hic_esm2_v1.joblib"]
    assert calls == [("VHAC", "VLAC")]
    assert result.model_id == "hic_esm2_v1"
    assert result.scientific_status == "research_support"
    assert result.experimental_verification_required is True
    assert result.to_dict()["task"] == "hic"
    assert result.to_dict()["predicted_hic"] == result.to_dict()["predicted_value"]


def test_invalid_empty_and_untruncated_sequences_are_handled(built_models: Path) -> None:
    predictor = FrozenMLPredictor(embedding_loader=_embedding)
    with pytest.raises(InferenceInputError, match="Invalid VH"):
        predictor.predict_hic("ACDX", "ACDE")
    with pytest.raises(InferenceInputError, match="Invalid VL"):
        predictor.predict_hic("ACDE", "")

    seen: list[tuple[str, str]] = []

    def capture(vh: str, vl: str) -> np.ndarray:
        seen.append((vh, vl))
        return _embedding(vh, vl)

    # The injected embedder makes this a local contract test without loading ESM.
    predictor = FrozenMLPredictor(built_models, embedding_loader=capture)
    predictor.predict_hic("A" * 200, "C" * 200)
    assert seen == [("A" * 200, "C" * 200)]


def test_prediction_schemas_probability_and_metadata(built_models: Path) -> None:
    predictor = FrozenMLPredictor(built_models, embedding_loader=_embedding)
    hic = predictor.predict_hic("ACDE", "FGHI")
    composite = predictor.predict_developability("ACDE", "FGHI")
    assert hic.to_dict()["predicted_value"] == hic.predicted_value
    assert hic.phase5_test_evidence == {"spearman": 0.834662, "r2": 0.625834, "n": 72}
    payload = composite.to_dict()
    assert 0.0 <= payload["probability_not_developable"] <= 1.0
    assert payload["positive_class"] == "NOT_DEVELOPABLE"
    assert "decision" not in payload
    assert "probability_developable" not in payload
    assert composite.phase5_test_evidence["n"] == 95


def test_status_is_non_predictive_and_reports_supported_tasks(built_models: Path) -> None:
    status = get_ml_runtime_status(built_models)
    assert status["model_artifacts_available"] is True
    assert status["supported_tasks"] == ["hic", "developability"]
    assert status["device"] in {"cpu", "cuda"}
    assert status["esm_model"] == MODEL_NAME
    assert status["esm_revision"] == MODEL_REVISION


def test_no_external_provider_and_cpu_fallback_in_runtime_source() -> None:
    source = (ROOT / "ml_inference/predictor.py").read_text(encoding="utf-8").lower()
    assert "deepseek" not in source
    assert "openai" not in source
    assert "europepmc" not in source
    assert "pubmed" not in source
    assert "cuda" in source and "cpu" in source


def test_build_is_reproducible_on_frozen_reference_embeddings(tmp_path: Path) -> None:
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    first = build_deployment_models(output_dir=first_dir)
    second = build_deployment_models(output_dir=second_dir)
    assert first["models"].keys() == second["models"].keys()
    for model_id in first["models"]:
        left = first["models"][model_id]
        right = second["models"][model_id]
        assert left["hyperparameter"] == right["hyperparameter"]
        assert left["training_row_count"] == right["training_row_count"]
        assert left["training_sequence_hash_sha256"] == right["training_sequence_hash_sha256"]
        left_model = joblib.load(first_dir / left["artifact"])
        right_model = joblib.load(second_dir / right["artifact"])
        reference = np.zeros((3, 1280), dtype=np.float32)
        np.testing.assert_allclose(left_model.predict(reference), right_model.predict(reference), rtol=0.0, atol=1e-12)


def test_core_and_scoring_are_not_modified() -> None:
    import subprocess

    result = subprocess.run(
        ["git", "diff", "--quiet", "--", "core.py", "scoring.py"],
        cwd=ROOT,
        check=False,
    )
    assert result.returncode == 0
