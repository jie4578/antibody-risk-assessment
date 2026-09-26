from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from validation.external_developability import phase8b_blind_prediction as phase8b
from validation.schemas.dataset_schema import sequence_hash


def _snapshot_frame(count: int = phase8b.EXPECTED_ROW_COUNT) -> pd.DataFrame:
    rows = []
    vh = "ACDEFGHIKLMNPQRSTVWY"
    for index in range(count):
        vl = "ACDEFGHIKLMNPQRSTVWY" + ("A" * (index + 1))
        rows.append(
            {
                "antibody_id": f"GDP-{index:03d}",
                "VH": vh,
                "VL": vl,
                "VH_hash": hashlib.sha256(vh.encode("ascii")).hexdigest(),
                "VL_hash": hashlib.sha256(vl.encode("ascii")).hexdigest(),
                "paired_hash": sequence_hash(vh, vl),
            }
        )
    return pd.DataFrame(rows, columns=phase8b.SNAPSHOT_COLUMNS)


def _write_snapshot(path: Path, frame: pd.DataFrame) -> str:
    frame.to_csv(path, index=False, encoding="utf-8", lineterminator="\n")
    return phase8b.sha256_file(path)


def _write_model(tmp_path: Path) -> tuple[Path, Path, str]:
    model_path = tmp_path / "hic_esm2_v1.joblib"
    model_path.write_bytes(b"test-only frozen model placeholder")
    model_sha = phase8b.sha256_file(model_path)
    manifest_path = tmp_path / "model_manifest.json"
    manifest = {
        "benchmark": phase8b.EXPECTED_BENCHMARK,
        "phase5_finalization_commit": phase8b.EXPECTED_PHASE5_COMMIT,
        "esm_model_name": phase8b.EXPECTED_ESM_MODEL,
        "esm_model_revision": phase8b.EXPECTED_ESM_REVISION,
        "training_population_policy": "TRAIN+VALIDATION only",
        "test_rows_used_for_training": 0,
        "models": {
            phase8b.EXPECTED_MODEL_ID: {
                "model_id": phase8b.EXPECTED_MODEL_ID,
                "model_version": phase8b.EXPECTED_MODEL_VERSION,
                "artifact": model_path.name,
                "artifact_sha256": model_sha,
                "estimator": "Ridge",
                "hyperparameter": {"alpha": 100.0},
                "feature_dimension": 1280,
                "training_row_count": 355,
            }
        },
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return model_path, manifest_path, model_sha


class _FakePredictor:
    def __init__(self) -> None:
        self.seen: list[tuple[str, str]] = []

    def predict_hic(self, vh: str, vl: str) -> SimpleNamespace:
        self.seen.append((vh, vl))
        return SimpleNamespace(predicted_value=float(len(self.seen)) / 7.0, model_version=phase8b.EXPECTED_MODEL_VERSION)


def test_runner_accepts_exact_sequence_only_schema(tmp_path: Path) -> None:
    snapshot = _snapshot_frame()
    path = tmp_path / "snapshot.csv"
    digest = _write_snapshot(path, snapshot)
    loaded = phase8b.load_frozen_snapshot(path, expected_sha256=digest)
    assert tuple(loaded.columns) == phase8b.SNAPSHOT_COLUMNS
    assert len(loaded) == 79


def test_runner_rejects_extra_experimental_column(tmp_path: Path) -> None:
    snapshot = _snapshot_frame().assign(hic_rt_avg=[1.0] * 79)
    path = tmp_path / "snapshot.csv"
    digest = _write_snapshot(path, snapshot)
    with pytest.raises(phase8b.BlindPredictionInputError, match="exact frozen"):
        phase8b.load_frozen_snapshot(path, expected_sha256=digest)


def test_runner_stops_on_snapshot_sha_mismatch(tmp_path: Path) -> None:
    path = tmp_path / "snapshot.csv"
    _write_snapshot(path, _snapshot_frame())
    with pytest.raises(phase8b.BlindPredictionInputError, match="SHA256 mismatch"):
        phase8b.load_frozen_snapshot(path)


def test_runner_stops_on_model_sha_mismatch(tmp_path: Path) -> None:
    model_path, manifest_path, _ = _write_model(tmp_path)
    with pytest.raises(phase8b.FrozenModelContractError, match="SHA256 mismatch"):
        phase8b.validate_frozen_model(model_path, manifest_path)


def test_runner_requires_exactly_79_rows(tmp_path: Path) -> None:
    path = tmp_path / "snapshot.csv"
    digest = _write_snapshot(path, _snapshot_frame(78))
    with pytest.raises(phase8b.BlindPredictionInputError, match="exactly 79"):
        phase8b.load_frozen_snapshot(path, expected_sha256=digest)


def test_runner_rejects_duplicate_antibody_id(tmp_path: Path) -> None:
    snapshot = _snapshot_frame()
    snapshot.loc[1, "antibody_id"] = snapshot.loc[0, "antibody_id"]
    path = tmp_path / "snapshot.csv"
    digest = _write_snapshot(path, snapshot)
    with pytest.raises(phase8b.BlindPredictionInputError, match="antibody_id.*unique"):
        phase8b.load_frozen_snapshot(path, expected_sha256=digest)


def test_runner_rejects_duplicate_paired_hash(tmp_path: Path) -> None:
    snapshot = _snapshot_frame()
    snapshot.loc[1, "paired_hash"] = snapshot.loc[0, "paired_hash"]
    path = tmp_path / "snapshot.csv"
    digest = _write_snapshot(path, snapshot)
    with pytest.raises(phase8b.BlindPredictionInputError, match="paired_hash.*unique"):
        phase8b.load_frozen_snapshot(path, expected_sha256=digest)


def test_prediction_schema_has_only_permitted_fields(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    snapshot = _snapshot_frame()
    snapshot_path = tmp_path / "snapshot.csv"
    snapshot_sha = _write_snapshot(snapshot_path, snapshot)
    model_path, manifest_path, model_sha = _write_model(tmp_path)
    monkeypatch.setattr(phase8b, "SNAPSHOT_PATH", snapshot_path)
    monkeypatch.setattr(phase8b, "EXPECTED_SNAPSHOT_SHA256", snapshot_sha)
    monkeypatch.setattr(phase8b, "MODEL_PATH", model_path)
    monkeypatch.setattr(phase8b, "MODEL_MANIFEST_PATH", manifest_path)
    monkeypatch.setattr(phase8b, "MODEL_DIR", tmp_path)
    monkeypatch.setattr(phase8b, "EXPECTED_MODEL_SHA256", model_sha)
    predictor = _FakePredictor()
    import ml_inference.predictor as runtime

    monkeypatch.setattr(runtime, "FrozenMLPredictor", lambda artifact_dir: predictor)
    output = tmp_path / "predictions.csv"
    monkeypatch.setattr(phase8b, "OUTPUT_PATH", output)
    predictions = phase8b.run_blind_prediction()
    assert tuple(predictions.columns) == ("antibody_id", "paired_hash", "hic_prediction", "model_version")
    assert not {"VH", "VL", "hic_rt", "hic_rt_avg", "assay", "label"}.intersection(predictions.columns)
    stored = pd.read_csv(output, dtype=str, keep_default_na=False)
    assert tuple(stored.columns) == phase8b.PREDICTION_COLUMNS
    assert not {"VH", "VL"}.intersection(stored.columns)
    assert stored["antibody_id"].tolist() == snapshot["antibody_id"].tolist()
    assert stored["paired_hash"].tolist() == snapshot["paired_hash"].tolist()
    assert len(predictor.seen) == 79


def test_prediction_output_preserves_snapshot_order_and_is_immutable(tmp_path: Path) -> None:
    frame = pd.DataFrame(
        [
            {"antibody_id": "a", "paired_hash": "hash-a", "hic_prediction": 1.2345678901234567, "model_version": phase8b.EXPECTED_MODEL_VERSION},
            {"antibody_id": "b", "paired_hash": "hash-b", "hic_prediction": -4.0, "model_version": phase8b.EXPECTED_MODEL_VERSION},
        ],
        columns=phase8b.PREDICTION_COLUMNS,
    )
    path = tmp_path / "result.csv"
    phase8b.write_canonical_predictions(frame, path)
    data = path.read_bytes()
    assert b"\r\n" not in data
    assert data.startswith(b"antibody_id,paired_hash,hic_prediction,model_version\n")
    assert b"1.2345678901234567" in data
    with pytest.raises(FileExistsError, match="Refusing to overwrite"):
        phase8b.write_canonical_predictions(frame, path)


def test_runner_source_has_no_metric_or_raw_workbook_path() -> None:
    source_path = Path(phase8b.__file__)
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden_calls = {"spearmanr", "pearsonr", "kendalltau", "corr", "roc_auc_score", "mean_squared_error"}
    called = {
        node.func.id if isinstance(node.func, ast.Name) else node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, (ast.Name, ast.Attribute))
    }
    assert not called.intersection(forbidden_calls)
    assert "GDPa3_20260106_full.xlsx" not in source
    assert "hic_rt_avg" not in source
    assert "PR-CHO" not in source
