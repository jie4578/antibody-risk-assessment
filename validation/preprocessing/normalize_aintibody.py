"""Deterministically normalize AIntibody Supplementary Data 3.

All source columns remain in the output. Added fields are explicitly derived
identity/status helpers and never overwrite source values.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from validation.schemas.dataset_schema import (
    assess_sequences, clean_text, duplicate_count, missing_summary, sequence_hash,
)

TARGET_SHEET = "Dataset 3"
SOURCE_HEADER_ROW = 1
SEQUENCE_COLUMNS = {"VH": "sequence_aa_heavy", "VL": "sequence_aa_light"}


def _read_source(path: str | Path, sheet: str = TARGET_SHEET) -> pd.DataFrame:
    frame = pd.read_excel(path, sheet_name=sheet, header=SOURCE_HEADER_ROW, engine="openpyxl")
    frame = frame.dropna(axis=0, how="all").reset_index(drop=True)
    frame.columns = [str(column).strip() for column in frame.columns]
    return frame


def normalize_aintibody(path: str | Path) -> tuple[pd.DataFrame, dict]:
    source = _read_source(path)
    records = []
    for index, row in source.iterrows():
        vh, vl, status, reason = assess_sequences(row.get(SEQUENCE_COLUMNS["VH"]), row.get(SEQUENCE_COLUMNS["VL"]))
        paper_id = clean_text(row.get("PAPER_ID"))
        record_id = clean_text(row.get("ID"))
        control = clean_text(row.get("control")).lower()
        record_type = "control" if control in {"true", "1", "yes"} else "submission"
        derived = {
            "dataset": "aintibody_2026",
            "record_id": record_id,
            "antibody_id": paper_id or record_id,
            "paper_id": paper_id,
            # Keep the source value, including NaN. Do not turn missing source
            # metadata into a derived empty string.
            "challenge": row.get("challenge"),
            "organization": clean_text(row.get("group")) or clean_text(row.get("company_group")),
            "record_type": record_type,
            "VH": vh,
            "VL": vl,
            "sequence_status": status,
            "sequence_status_reason": reason,
            "sequence_hash": sequence_hash(vh, vl),
            "source_sheet": TARGET_SHEET,
            "source_row": index + SOURCE_HEADER_ROW + 2,
        }
        records.append({**derived, **{str(k): v for k, v in row.to_dict().items() if str(k) not in derived}})
    output = pd.DataFrame(records)
    audit = {
        "dataset": "aintibody_2026",
        "source_sheet": TARGET_SHEET,
        "total_rows": len(output),
        "unique_record_ids": int(output["record_id"].nunique(dropna=False)),
        "unique_antibody_ids": int(output["antibody_id"].nunique(dropna=False)),
        "unique_sequence_pairs": int(output["sequence_hash"].nunique(dropna=False)),
        "duplicate_record_ids_rows": duplicate_count(output, "record_id"),
        "duplicate_sequence_pair_rows": duplicate_count(output, "sequence_hash"),
        "sequence_status_counts": output["sequence_status"].value_counts(dropna=False).to_dict(),
        "missingness": missing_summary(output),
        "source_columns": [str(column) for column in source.columns],
        "preserved_assays": {
            "developability": ["HIC RT in gradient (min)", "average BVP score", "Tm, C", "Tagg, C", "average dPW"],
            "per_assay_status": ["construct performance, HIC", "construct performance, BVP", "construct performance, Tm", "construct performance, Tagg", "construct performance, AC-SINS"],
            "composite": ["total_developability_score"],
        },
        "affinity_fields": ["KD_SPR", "KD_KinExA", "KinExA_Screen_KD_Estimate", "Mean KD (M)"],
        "derived_fields": ["antibody_id", "record_type", "organization", "VH", "VL", "sequence_status", "sequence_status_reason", "sequence_hash", "source_sheet", "source_row"],
    }
    return output, audit


def write_outputs(raw_path: str | Path, processed_path: str | Path, audit_json: str | Path, audit_md: str | Path) -> None:
    output, audit = normalize_aintibody(raw_path)
    output.to_csv(processed_path, index=False)
    Path(audit_json).write_text(json.dumps(audit, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    lines = ["# AIntibody 2026 data audit", "", f"- Source sheet: `{audit['source_sheet']}`", f"- Total rows: {audit['total_rows']}", f"- Unique record IDs: {audit['unique_record_ids']}", f"- Unique VH/VL hashes: {audit['unique_sequence_pairs']}", f"- Duplicate record-id rows: {audit['duplicate_record_ids_rows']}", f"- Duplicate sequence-pair rows: {audit['duplicate_sequence_pair_rows']}", "", "## Sequence status", ""]
    lines.extend(f"- {key}: {value}" for key, value in audit["sequence_status_counts"].items())
    lines.extend(["", "All source assay and affinity columns are preserved. Added identity and sequence fields are derived and labeled; no values are imputed or deduplicated."])
    Path(audit_md).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    write_outputs(root / "data/raw/aintibody_2026/41587_2026_3238_MOESM4_ESM.xlsx", root / "data/processed/aintibody_2026.csv", root / "reports/data_audit/aintibody_audit.json", root / "reports/data_audit/aintibody_audit.md")


if __name__ == "__main__":
    main()
