from __future__ import annotations

from pathlib import Path
from zipfile import ZipFile

import pandas as pd
import pytest
from openpyxl import Workbook

from validation.external_developability.phase8_preregistration import (
    SNAPSHOT_COLUMNS,
    build_sequence_only_snapshot,
    nonblank_cell_row_numbers,
    validate_sequence_snapshot_schema,
    write_sequence_snapshot,
)


VH_A = "ACDEFGHIKLMNPQRSTVWY"
VL_A = "YWVTSRQPNMLKIHGFEDCA"
VH_B = "CDEFGHIKLMNPQRSTVWYA"
VL_B = "WVTSRQPNMLKIHGFEDCAY"


def _sequence_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"antibody_id": "Ab-B", "vh_protein_sequence": VH_B, "lc_protein_sequence": VL_B},
            {"antibody_id": "Ab-A", "vh_protein_sequence": VH_A, "lc_protein_sequence": VL_A},
        ],
        columns=["antibody_id", "vh_protein_sequence", "lc_protein_sequence"],
    )


def test_snapshot_is_deterministic_and_contains_only_sequence_identity_fields(tmp_path: Path) -> None:
    snapshot = build_sequence_only_snapshot(_sequence_frame(), {"Ab-A", "Ab-B"}, expected_n=2)
    assert tuple(snapshot.columns) == SNAPSHOT_COLUMNS
    assert snapshot["antibody_id"].tolist() == ["Ab-A", "Ab-B"]
    assert snapshot["paired_hash"].is_unique
    assert not {"HIC", "hic_rt_avg", "tm2_nanodsf_avg", "titer_avg"}.intersection(snapshot.columns)

    destination = tmp_path / "snapshot.csv"
    first_sha = write_sequence_snapshot(snapshot, destination)
    first_bytes = destination.read_bytes()
    second_sha = write_sequence_snapshot(snapshot, destination)
    assert second_sha == first_sha
    assert destination.read_bytes() == first_bytes
    validate_sequence_snapshot_schema(pd.read_csv(destination, dtype=str, keep_default_na=False))


def test_snapshot_builder_rejects_label_bearing_sequence_input() -> None:
    frame = _sequence_frame().assign(hic_rt_avg=[1.0, 2.0])
    with pytest.raises(ValueError, match="only antibody_id"):
        build_sequence_only_snapshot(frame, {"Ab-A", "Ab-B"}, expected_n=2)


def test_snapshot_schema_rejects_extra_or_label_columns() -> None:
    snapshot = build_sequence_only_snapshot(_sequence_frame(), {"Ab-A", "Ab-B"}, expected_n=2)
    with pytest.raises(ValueError, match="unexpected or label-bearing"):
        validate_sequence_snapshot_schema(snapshot.assign(hic_rt_avg=[1.0, 2.0]))


def test_snapshot_requires_complete_valid_unique_population() -> None:
    with pytest.raises(ValueError, match="Expected 2 eligible"):
        build_sequence_only_snapshot(_sequence_frame(), {"Ab-A"}, expected_n=2)

    invalid = _sequence_frame()
    invalid.loc[0, "lc_protein_sequence"] = "VL*"
    with pytest.raises(ValueError, match="invalid paired sequence"):
        build_sequence_only_snapshot(invalid, {"Ab-A", "Ab-B"}, expected_n=2)

    duplicate = pd.concat([_sequence_frame(), _sequence_frame().iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="duplicate antibody IDs"):
        build_sequence_only_snapshot(duplicate, {"Ab-A", "Ab-B"}, expected_n=2)


def test_availability_reader_returns_cell_presence_rows_not_measurement_values(tmp_path: Path) -> None:
    path = tmp_path / "synthetic.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Assay Data - average"
    sheet.append(["antibody_id", "hic_rt_avg"])
    sheet.append(["A", 1.25])
    sheet.append(["B", None])
    workbook.save(path)
    workbook.close()

    with ZipFile(path) as archive:
        assert archive.testzip() is None
    assert nonblank_cell_row_numbers(path, sheet_name="Assay Data - average", column_letter="B") == {2}


def test_phase8a_runner_has_no_prediction_or_model_runtime_path() -> None:
    runner = Path(__file__).resolve().parents[2] / "run_phase8a_gdpa3_snapshot.py"
    source = runner.read_text(encoding="utf-8")
    assert "predict_hic" not in source
    assert "ml_inference" not in source
    assert "hic_prediction" not in source
    assert "SNAPSHOT_PATH" in source


def test_frozen_protocol_records_preregistered_analysis_and_firewall() -> None:
    protocol = Path(__file__).resolve().parents[1] / "PHASE8_HIC_EXTERNAL_VALIDATION_PROTOCOL.md"
    text = " ".join(protocol.read_text(encoding="utf-8").split()).replace("`", "")
    for required in (
        "hic_rt_avg",
        "Spearman",
        "2,000",
        "20260926",
        "CROSS-SOURCE / CROSS-PROTOCOL",
        "no rho/metric threshold defines success or failure",
        "do not claim family-independent",
        "developability_esm2_v1 is not evaluated",
        "prediction-first seal",
    ):
        assert required.lower() in text.lower()
    assert "no gdpa3 prediction or performance result has been generated" in text.lower()
