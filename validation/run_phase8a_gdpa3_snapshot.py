"""Freeze the preregistered GDPa3 HIC inference population as sequences only."""

from __future__ import annotations

import json
from pathlib import Path

from validation.external_developability.phase8_preregistration import (
    EXPECTED_EVALUATION_N,
    build_sequence_only_snapshot,
    load_gdpa3_phase8_inputs,
    sha256_file,
    write_sequence_snapshot,
)


ROOT = Path(__file__).resolve().parents[1]
RAW_WORKBOOK = ROOT / "validation/external_developability/raw/GDPa3_20260106_full.xlsx"
SNAPSHOT_PATH = ROOT / "validation/data/external_developability/gdpa3_phase8a/gdpa3_hic_sequence_snapshot.csv"


def freeze_snapshot() -> dict[str, object]:
    sequences, eligible_ids, target = load_gdpa3_phase8_inputs(RAW_WORKBOOK)
    snapshot = build_sequence_only_snapshot(
        sequences,
        eligible_ids,
        expected_n=EXPECTED_EVALUATION_N,
    )
    snapshot_sha256 = write_sequence_snapshot(snapshot, SNAPSHOT_PATH)
    return {
        "snapshot_path": str(SNAPSHOT_PATH.relative_to(ROOT)).replace("\\", "/"),
        "snapshot_rows": int(len(snapshot)),
        "snapshot_columns": list(snapshot.columns),
        "snapshot_sha256": snapshot_sha256,
        "raw_workbook_sha256": sha256_file(RAW_WORKBOOK),
        "hic_target": target,
        "label_magnitudes_used_for_selection": False,
        "model_prediction_generated": False,
        "performance_evaluated": False,
    }


if __name__ == "__main__":
    print(json.dumps(freeze_snapshot(), ensure_ascii=False, indent=2))
