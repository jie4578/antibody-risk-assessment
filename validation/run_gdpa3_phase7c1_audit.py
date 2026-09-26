"""Run the Phase 7C.1 GDPa3 workbook and sequence-only overlap audit."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from validation.external_developability.gdpa3_audit import (
    audit_sequence_sources,
    inspect_gdpa3_workbook,
    write_audit_outputs,
)


ROOT = Path(__file__).resolve().parents[1]
WORKBOOK = ROOT / "validation/external_developability/raw/GDPa3_20260106_full.xlsx"


def run_audit() -> dict[str, object]:
    workbook_audit, gdpa3_records = inspect_gdpa3_workbook(WORKBOOK)
    # These usecols are the safety boundary: no AIntibody assay/outcome column is loaded.
    jain = pd.read_csv(
        ROOT / "validation/data/processed/jain_137.csv",
        usecols=["antibody_id", "VH", "VL"],
        dtype=str,
        keep_default_na=False,
    )
    aintibody = pd.read_csv(
        ROOT / "validation/data/processed/aintibody_2026.csv",
        usecols=["record_id", "VH", "VL", "sequence_hash"],
        dtype=str,
        keep_default_na=False,
    )
    # Frozen membership has only sequence hashes and split names; sealed labels are never opened.
    split_membership = pd.read_csv(
        ROOT / "validation/data/ml_benchmark/entity_exact_v1/split_manifest.csv",
        usecols=["sequence_hash", "split"],
        dtype=str,
        keep_default_na=False,
    )
    sabdab = pd.read_csv(
        ROOT / "validation/external_family_validation/data/raw/sabdab2_all_summary.csv",
        usecols=["VH", "VL"],
        dtype=str,
        keep_default_na=False,
    )
    comparisons = audit_sequence_sources(gdpa3_records, jain, aintibody, split_membership, sabdab)
    paths = write_audit_outputs(workbook_audit, comparisons, ROOT / "validation/reports")
    return {
        "decision": "READY_HIC_ONLY",
        "json_report": str(paths[0].relative_to(ROOT)),
        "markdown_report": str(paths[1].relative_to(ROOT)),
        "sequence_audit": workbook_audit["sequence_audit"],
        "exact_overlap": comparisons["exact_overlap"],
        "train_validation_nearest_identity": comparisons["AIntibody_train_validation_similarity"]["nearest_paired_min"],
        "identity_clusters": {
            threshold: {
                "clusters": report["clusters"],
                "largest_cluster": report["largest_cluster"],
            }
            for threshold, report in comparisons["identity_proxy_clusters"].items()
        },
        "HIC_average_nonmissing_n": next(
            assay["average_nonmissing_antibodies"]
            for assay in workbook_audit["assay_inventory"]
            if assay["field"] == "hic_rt"
        ),
        "AIntibody_TEST_labels_accessed": False,
        "performance_or_correlations_calculated": False,
    }


if __name__ == "__main__":
    print(json.dumps(run_audit(), indent=2, ensure_ascii=False))
