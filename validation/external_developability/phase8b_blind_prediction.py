"""Frozen, label-blind GDPa3 HIC inference and canonical serialization."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import tempfile
from pathlib import Path
from typing import Any

import pandas as pd

from validation.schemas.dataset_schema import sequence_hash


ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT_PATH = ROOT / "validation/data/external_developability/gdpa3_phase8a/gdpa3_hic_sequence_snapshot.csv"
MODEL_DIR = ROOT / "artifacts/ml_models"
MODEL_PATH = MODEL_DIR / "hic_esm2_v1.joblib"
MODEL_MANIFEST_PATH = MODEL_DIR / "model_manifest.json"
OUTPUT_PATH = ROOT / "validation/data/external_developability/gdpa3_phase8b/gdpa3_hic_blind_predictions.csv"

EXPECTED_SNAPSHOT_SHA256 = "5c41700df82dce43b8d379afbf054228818bf868f0ae4b89fa9270e8d1daf3e7"
EXPECTED_MODEL_SHA256 = "b6b05c0f5e45bf2b53ef5878bef8f248c3a7ce50ee7b78e5f8cd09044ca309b4"
EXPECTED_ROW_COUNT = 79
EXPECTED_MODEL_ID = "hic_esm2_v1"
EXPECTED_MODEL_VERSION = "phase5-frozen-v1"
EXPECTED_ESM_MODEL = "facebook/esm2_t30_150M_UR50D"
EXPECTED_ESM_REVISION = "a695f6045e2e32885fa60af20c13cb35398ce30c"
EXPECTED_BENCHMARK = "AINTIBODY_INTERNAL_ENTITY_EXACT_V1"
EXPECTED_PHASE5_COMMIT = "7826881c04887d274f73e737caf35d83e7b62dd2"
SNAPSHOT_COLUMNS = ("antibody_id", "VH", "VL", "VH_hash", "VL_hash", "paired_hash")
PREDICTION_COLUMNS = ("antibody_id", "paired_hash", "hic_prediction", "model_version")


class BlindPredictionInputError(ValueError):
    """Raised when a frozen sequence-only input violates its contract."""


class FrozenModelContractError(ValueError):
    """Raised when model bytes or provenance differ from the preregistration."""


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_snapshot_frame(frame: pd.DataFrame, *, expected_rows: int = EXPECTED_ROW_COUNT) -> None:
    if tuple(frame.columns) != SNAPSHOT_COLUMNS:
        raise BlindPredictionInputError("Snapshot must have the exact frozen sequence-only schema and column order")
    if len(frame) != expected_rows:
        raise BlindPredictionInputError(f"Expected exactly {expected_rows} frozen sequence rows")
    for column in SNAPSHOT_COLUMNS:
        values = frame[column].astype(str)
        if values.eq("").any() or values.str.strip().eq("").any():
            raise BlindPredictionInputError(f"Snapshot contains an empty value in {column}")
    if frame["antibody_id"].duplicated().any():
        raise BlindPredictionInputError("Snapshot antibody_id values must be unique")
    if frame["paired_hash"].duplicated().any():
        raise BlindPredictionInputError("Snapshot paired_hash values must be unique")

    for row in frame.itertuples(index=False):
        vh_hash = hashlib.sha256(str(row.VH).encode("ascii")).hexdigest()
        vl_hash = hashlib.sha256(str(row.VL).encode("ascii")).hexdigest()
        pair_hash = sequence_hash(row.VH, row.VL)
        if (row.VH_hash, row.VL_hash, row.paired_hash) != (vh_hash, vl_hash, pair_hash):
            raise BlindPredictionInputError("Snapshot sequence hashes do not match their sequence fields")


def load_frozen_snapshot(
    path: str | Path = SNAPSHOT_PATH,
    *,
    expected_sha256: str = EXPECTED_SNAPSHOT_SHA256,
    expected_rows: int = EXPECTED_ROW_COUNT,
) -> pd.DataFrame:
    source = Path(path)
    actual_sha256 = sha256_file(source)
    if actual_sha256 != expected_sha256:
        raise BlindPredictionInputError("Frozen sequence snapshot SHA256 mismatch")
    frame = pd.read_csv(source, dtype=str, keep_default_na=False, encoding="utf-8")
    validate_snapshot_frame(frame, expected_rows=expected_rows)
    return frame


def validate_frozen_model(
    model_path: str | Path = MODEL_PATH,
    manifest_path: str | Path = MODEL_MANIFEST_PATH,
    *,
    expected_sha256: str = EXPECTED_MODEL_SHA256,
) -> dict[str, Any]:
    model_file = Path(model_path)
    if sha256_file(model_file) != expected_sha256:
        raise FrozenModelContractError("Frozen HIC model artifact SHA256 mismatch")
    try:
        manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        details = manifest["models"][EXPECTED_MODEL_ID]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as error:
        raise FrozenModelContractError("Frozen HIC model manifest is missing or invalid") from error

    contract = (
        manifest.get("benchmark") == EXPECTED_BENCHMARK
        and manifest.get("phase5_finalization_commit") == EXPECTED_PHASE5_COMMIT
        and manifest.get("esm_model_name") == EXPECTED_ESM_MODEL
        and manifest.get("esm_model_revision") == EXPECTED_ESM_REVISION
        and manifest.get("training_population_policy") == "TRAIN+VALIDATION only"
        and manifest.get("test_rows_used_for_training") == 0
        and details.get("model_id") == EXPECTED_MODEL_ID
        and details.get("model_version") == EXPECTED_MODEL_VERSION
        and details.get("artifact") == model_file.name
        and details.get("artifact_sha256") == expected_sha256
        and details.get("estimator") == "Ridge"
        and details.get("hyperparameter", {}).get("alpha") == 100.0
        and details.get("feature_dimension") == 1280
        and details.get("training_row_count") == 355
    )
    if not contract:
        raise FrozenModelContractError("Frozen HIC model manifest differs from the preregistered contract")
    return manifest


def write_canonical_predictions(frame: pd.DataFrame, path: str | Path) -> None:
    """Write UTF-8 CSV, comma-delimited, LF, row order preserved, float .17g."""

    if tuple(frame.columns) != PREDICTION_COLUMNS:
        raise ValueError("Prediction frame has an unexpected schema")
    if frame["antibody_id"].duplicated().any() or frame["paired_hash"].duplicated().any():
        raise ValueError("Prediction identities must remain unique")
    for value in frame["hic_prediction"]:
        if not math.isfinite(float(value)):
            raise ValueError("HIC predictions must all be finite")

    destination = Path(path)
    if destination.exists():
        raise FileExistsError(f"Refusing to overwrite immutable prediction artifact: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            dir=destination.parent,
            prefix=".phase8b-",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary_path = Path(stream.name)
            writer = csv.writer(stream, delimiter=",", lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
            writer.writerow(PREDICTION_COLUMNS)
            for row in frame.itertuples(index=False):
                writer.writerow((row.antibody_id, row.paired_hash, format(float(row.hic_prediction), ".17g"), row.model_version))
        os.replace(temporary_path, destination)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def run_blind_prediction() -> pd.DataFrame:
    """Run only the pinned HIC model over the pinned sequence-only snapshot."""

    snapshot = load_frozen_snapshot(SNAPSHOT_PATH, expected_sha256=EXPECTED_SNAPSHOT_SHA256)
    manifest = validate_frozen_model(MODEL_PATH, MODEL_MANIFEST_PATH, expected_sha256=EXPECTED_MODEL_SHA256)
    model_version = str(manifest["models"][EXPECTED_MODEL_ID]["model_version"])
    if model_version != EXPECTED_MODEL_VERSION:
        raise FrozenModelContractError("Frozen HIC model version differs from the preregistered contract")

    from ml_inference.predictor import FrozenMLPredictor

    predictor = FrozenMLPredictor(artifact_dir=MODEL_DIR)

    output_rows: list[dict[str, Any]] = []
    for row in snapshot.itertuples(index=False):
        prediction = predictor.predict_hic(row.VH, row.VL)
        value = float(prediction.predicted_value)
        if not math.isfinite(value):
            raise ValueError("Frozen HIC runtime returned a non-finite prediction")
        if str(prediction.model_version) != EXPECTED_MODEL_VERSION:
            raise FrozenModelContractError("Inference runtime returned an unexpected model version")
        output_rows.append(
            {
                "antibody_id": row.antibody_id,
                "paired_hash": row.paired_hash,
                "hic_prediction": value,
                "model_version": EXPECTED_MODEL_VERSION,
            }
        )

    predictions = pd.DataFrame(output_rows, columns=PREDICTION_COLUMNS)
    if predictions["antibody_id"].tolist() != snapshot["antibody_id"].tolist():
        raise RuntimeError("Prediction row order does not match the frozen snapshot")
    if predictions["paired_hash"].tolist() != snapshot["paired_hash"].tolist():
        raise RuntimeError("Prediction sequence identities do not match the frozen snapshot")
    write_canonical_predictions(predictions, OUTPUT_PATH)
    return predictions


def main() -> None:
    predictions = run_blind_prediction()
    print(f"Blind prediction rows: {len(predictions)}")
    print(f"Prediction artifact: {OUTPUT_PATH}")
    print(f"Prediction SHA256: {sha256_file(OUTPUT_PATH)}")


if __name__ == "__main__":
    main()
