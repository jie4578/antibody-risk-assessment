from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from openpyxl import Workbook

from validation.external_developability import run_phase8c_hic_external_evaluation as phase8c
from validation.schemas.dataset_schema import assess_sequences, sequence_hash


def _identity_rows(n: int) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    snapshot_rows = []
    prediction_rows = []
    label_rows = []
    base = "ACDEFGHIKLMNPQRSTVWY"
    for index in range(n):
        antibody_id = f"synthetic-{index:03d}"
        vh_raw = base + ("A" * index)
        vl_raw = base + ("C" * (index + 1))
        vh, vl, status, _ = assess_sequences(vh_raw, vl_raw)
        assert status == "VALID"
        pair_hash = sequence_hash(vh, vl)
        snapshot_rows.append(
            {
                "antibody_id": antibody_id,
                "VH": vh,
                "VL": vl,
                "VH_hash": hashlib.sha256(vh.encode("ascii")).hexdigest(),
                "VL_hash": hashlib.sha256(vl.encode("ascii")).hexdigest(),
                "paired_hash": pair_hash,
            }
        )
        prediction_rows.append(
            {
                "antibody_id": antibody_id,
                "paired_hash": pair_hash,
                "hic_prediction": float(index),
                "model_version": "phase5-frozen-v1",
            }
        )
        label_rows.append({"antibody_id": antibody_id, "paired_hash": pair_hash, "hic_rt_avg": float(index * 2 + 3)})
    return (
        pd.DataFrame(prediction_rows, columns=phase8c.PREDICTION_COLUMNS),
        pd.DataFrame(snapshot_rows, columns=phase8c.SNAPSHOT_COLUMNS),
        pd.DataFrame(label_rows, columns=phase8c.LABEL_COLUMNS),
    )


def test_synthetic_workbook_reader_returns_only_hic_label_fields(tmp_path: Path) -> None:
    path = tmp_path / "synthetic.xlsx"
    workbook = Workbook()
    sequence_ws = workbook.active
    sequence_ws.title = "Sequences"
    sequence_ws.append(["antibody_id", "vh_protein_sequence", "lc_protein_sequence", "notes"])
    average_ws = workbook.create_sheet("Assay Data - average")
    average_ws.append(["antibody_id", "non_target_assay", "hic_rt_avg", "PR-CHO"])
    base = "ACDEFGHIKLMNPQRSTVWY"
    for index in range(4):
        antibody_id = f"synthetic-{index}"
        vh = base + ("A" * index)
        vl = base + ("C" * (index + 1))
        sequence_ws.append([antibody_id, vh, vl, "not an analysis field"])
        average_ws.append([antibody_id, "DO-NOT-READ", None if index == 3 else index + 0.5, "DO-NOT-READ"])
    workbook.save(path)
    workbook.close()

    labels = phase8c.read_gdpa3_hic_label_table(
        path,
        expected_raw_sha256=phase8c.sha256_file(path),
        expected_n=3,
        expected_source_n=4,
    )
    assert tuple(labels.columns) == ("antibody_id", "paired_hash", "hic_rt_avg")
    assert len(labels) == 3
    assert labels["antibody_id"].tolist() == ["synthetic-0", "synthetic-1", "synthetic-2"]


def test_join_requires_both_id_and_paired_hash() -> None:
    predictions, snapshot, labels = _identity_rows(4)
    labels.loc[2, "paired_hash"] = "0" * 64
    with pytest.raises(phase8c.Phase8CInputError, match="join integrity failed"):
        phase8c.join_hic_labels(predictions, snapshot, labels, expected_n=4)


def test_join_preserves_prediction_order_and_reports_full_integrity() -> None:
    predictions, snapshot, labels = _identity_rows(5)
    labels = labels.iloc[::-1].reset_index(drop=True)
    joined, integrity = phase8c.join_hic_labels(predictions, snapshot, labels, expected_n=5)
    assert joined["antibody_id"].tolist() == predictions["antibody_id"].tolist()
    assert integrity == {"matched_rows": 5, "prediction_only_rows": 0, "label_only_rows": 0, "hash_mismatches": 0}
    assert tuple(joined.columns) == (*phase8c.PREDICTION_COLUMNS, "hic_rt_avg")


def test_join_rejects_extra_label_fields_and_duplicate_labels() -> None:
    predictions, snapshot, labels = _identity_rows(4)
    with pytest.raises(phase8c.Phase8CInputError, match="outside the authorized scope"):
        phase8c.join_hic_labels(predictions, snapshot, labels.assign(other_assay=1), expected_n=4)
    duplicate = pd.concat([labels.iloc[:3], labels.iloc[[0]]], ignore_index=True)
    with pytest.raises(phase8c.Phase8CInputError, match="unique"):
        phase8c.join_hic_labels(predictions, snapshot, duplicate, expected_n=4)


def test_preregistered_metrics_and_bootstrap_only() -> None:
    predictions, snapshot, labels = _identity_rows(79)
    joined, _ = phase8c.join_hic_labels(predictions, snapshot, labels)
    result = phase8c.compute_preregistered_statistics(joined)
    assert result["primary"]["n"] == 79
    assert result["primary"]["estimate"] == pytest.approx(1.0)
    assert result["bootstrap"]["resamples"] == 2000
    assert result["bootstrap"]["seed"] == 20260926
    assert result["bootstrap"]["bit_generator"] == "PCG64"
    assert result["bootstrap"]["valid_n"] + result["bootstrap"]["degenerate_n"] == 2000
    assert result["bootstrap"]["ci"] == pytest.approx([1.0, 1.0])
    assert result["secondary"]["pearson_r"]["n"] == 79
    assert result["secondary"]["pearson_r"]["estimate"] == pytest.approx(1.0)
    assert result["secondary"]["kendall_tau_b"]["n"] == 79
    assert result["secondary"]["kendall_tau_b"]["estimate"] == pytest.approx(1.0)
    assert result["similarity_bins"] == {
        "counts": {"<0.70": 71, "0.70–<0.80": 7, "0.80–<0.90": 1, ">=0.90": 0},
        "n": 79,
    }
    assert not {"mae", "rmse", "r2", "subgroup_correlations"}.intersection(result)


def test_constant_resamples_are_counted_not_redrawn() -> None:
    n = 79
    joined = pd.DataFrame({"hic_prediction": np.zeros(n), "hic_rt_avg": np.arange(n, dtype=float)})
    result = phase8c.compute_preregistered_statistics(joined)
    assert result["primary"]["estimate"] is None
    assert result["bootstrap"]["valid_n"] == 0
    assert result["bootstrap"]["degenerate_n"] == 2000
    assert result["bootstrap"]["ci"] is None


def test_result_and_report_preserve_protocol_limits() -> None:
    predictions, snapshot, labels = _identity_rows(79)
    joined, integrity = phase8c.join_hic_labels(predictions, snapshot, labels)
    metrics = phase8c.compute_preregistered_statistics(joined)
    result = phase8c.build_result(
        metrics,
        integrity,
        raw_sha256="raw-sha",
        prediction_sha256="prediction-sha",
        snapshot_sha256="snapshot-sha",
        model_sha256="model-sha",
        phase8c_code_commit="code-commit",
        timestamp_utc="2026-01-01T00:00:00Z",
    )
    report = phase8c.build_human_report(result, "result-sha")
    assert result["status"] == "OBSERVED_ONE_TIME_EXTERNAL_EVALUATION"
    assert result["cross_source_cross_protocol"] is True
    assert result["model_trained"] is False and result["model_tuned"] is False
    assert result["absolute_error_metrics"] == "NOT_CALCULATED"
    assert "What this result does NOT establish" in report
    assert "no statistical test comparing the correlations was run" in report
    assert "family-independent" in report
    assert "result-sha" in report
