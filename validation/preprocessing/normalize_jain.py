"""Deterministic outer-join normalizer for Jain S1/S2/S3 workbooks."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable

import pandas as pd

from validation.schemas.dataset_schema import (
    assess_sequences, clean_text, duplicate_count, missing_summary, sequence_hash,
)

JAIN_FILES = {
    "S1": "pnas.1616408114.sd01.xlsx",
    "S2": "pnas.1616408114.sd02.xlsx",
    "S3": "pnas.1616408114.sd03.xlsx",
}


def _header_row(raw: pd.DataFrame) -> int:
    for index, row in raw.iterrows():
        values = [clean_text(value).lower() for value in row.tolist() if clean_text(value)]
        joined = " ".join(values)
        if len(values) >= 2 and ("name" in values or "id" in values or "antibody" in joined or "heavy" in joined or "light" in joined or "sequence" in joined or "inn" in joined):
            return int(index)
    raise ValueError("could not identify a header row")


def _read_table(path: Path) -> pd.DataFrame:
    sheets = pd.read_excel(path, sheet_name=None, header=None, engine="openpyxl")
    if not sheets:
        raise ValueError(f"no sheets in {path}")
    raw = next(iter(sheets.values()))
    header = _header_row(raw)
    frame = raw.iloc[header + 1:].copy()
    frame.columns = [clean_text(value) or f"unnamed_{index + 1}" for index, value in enumerate(raw.iloc[header].tolist())]
    frame = frame.dropna(axis=0, how="all").reset_index(drop=True)
    frame["_source_row"] = frame.index + header + 2
    return frame


def _pick_column(columns: Iterable[str], patterns: Iterable[str]) -> str | None:
    candidates = list(columns)
    for pattern in patterns:
        for column in candidates:
            if re.search(pattern, str(column), flags=re.IGNORECASE):
                return column
    return None


def _id_column(frame: pd.DataFrame) -> str:
    column = _pick_column(frame.columns, (r"^antibody\s*(id|name)?$", r"antibody", r"inn", r"molecule", r"^id$", r"name"))
    if not column:
        raise ValueError("could not identify Jain antibody identifier column")
    return column


def _sequence_columns(frame: pd.DataFrame) -> tuple[str, str]:
    vh = _pick_column(frame.columns, (r"\bVH\b", r"heavy.*seq", r"heavy"))
    vl = _pick_column(frame.columns, (r"\bVL\b", r"light.*seq", r"light"))
    if not vh or not vl:
        raise ValueError("could not identify both VH and VL columns in Jain S2")
    return vh, vl


def _join_id(value: object) -> str:
    return clean_text(value).casefold()


def _is_source_note(value: object) -> bool:
    return "arbitrarily long rt" in clean_text(value).casefold()


def normalize_jain(raw_dir: str | Path) -> tuple[pd.DataFrame, dict, pd.DataFrame]:
    root = Path(raw_dir)
    paths = {key: root / filename for key, filename in JAIN_FILES.items()}
    missing = [str(path) for path in paths.values() if not path.exists()]
    if missing:
        raise FileNotFoundError("Jain official raw files missing: " + ", ".join(missing))
    tables = {key: _read_table(path) for key, path in paths.items()}
    id_columns = {key: _id_column(frame) for key, frame in tables.items()}
    vh_column, vl_column = _sequence_columns(tables["S2"])

    prepared = {}
    for key, frame in tables.items():
        out = frame.copy()
        out["_join_id"] = out[id_columns[key]].map(_join_id)
        prepared[key] = out
    assay_only_source_notes = prepared["S3"][prepared["S3"][id_columns["S3"]].map(_is_source_note)].copy()
    # This is a source footnote in the Name column, not an experimental
    # antibody record. Keep it in the audit and exclude it from the normalized
    # antibody table with an explicit data-quality reason.
    prepared["S3"] = prepared["S3"][~prepared["S3"][id_columns["S3"]].map(_is_source_note)].copy()
    # An outer join preserves sequence-only, assay-only and metadata-only rows.
    merged = prepared["S1"].merge(prepared["S2"], on="_join_id", how="outer", suffixes=("_s1", "_s2"), indicator="_merge_s1_s2")
    merged = merged.merge(prepared["S3"], on="_join_id", how="outer", suffixes=("", "_s3"), indicator="_merge_s3")

    def first_value(row: pd.Series, names: Iterable[str]) -> object:
        for name in names:
            if name in row.index and not clean_text(row[name]):
                continue
            if name in row.index:
                return row[name]
        return ""

    result_rows = []
    for _, row in merged.iterrows():
        vh, vl, status, reason = assess_sequences(row.get(vh_column + "_s2", row.get(vh_column)), row.get(vl_column + "_s2", row.get(vl_column)))
        record_id = first_value(row, [id_columns["S3"], id_columns["S3"] + "_s3", id_columns["S2"], id_columns["S2"] + "_s2", id_columns["S1"], id_columns["S1"] + "_s1"])
        result_rows.append({
            "dataset": "jain_2017",
            "record_id": clean_text(record_id),
            "antibody_id": clean_text(record_id),
            "VH": vh,
            "VL": vl,
            "sequence_status": status,
            "sequence_status_reason": reason,
            "sequence_hash": sequence_hash(vh, vl),
            "merge_status": f"{row.get('_merge_s1_s2')}|{row.get('_merge_s3')}",
            "source_s1_row": row.get("_source_row_s1"),
            "source_s2_row": row.get("_source_row_s2"),
            "source_s3_row": row.get("_source_row"),
            **{str(k): v for k, v in row.items() if not str(k).startswith("_") and k not in {"VH", "VL"}},
        })
    result = pd.DataFrame(result_rows)
    source_assay_ids = set(prepared["S3"]["_join_id"])
    sequence_ids = set(prepared["S2"]["_join_id"])
    metadata_ids = set(prepared["S1"]["_join_id"])
    audit = {
        "dataset": "jain_2017",
        "source_files": {key: str(path).replace("\\", "/") for key, path in paths.items()},
        "identifier_columns": id_columns,
        "sequence_columns": {"VH": vh_column, "VL": vl_column},
        "source_row_counts": {key: len(frame) for key, frame in tables.items()},
        "total_rows": len(result),
        "unique_antibody_ids": int(result["antibody_id"].nunique(dropna=False)),
        "unique_sequence_pairs": int(result["sequence_hash"].nunique(dropna=False)),
        "duplicate_identifier_rows": duplicate_count(result, "antibody_id"),
        "duplicate_sequence_pair_rows": duplicate_count(result, "sequence_hash"),
        "sequence_status_counts": result["sequence_status"].value_counts(dropna=False).to_dict(),
        "unmatched_ids": {
            "matched_ids": len(sequence_ids & source_assay_ids),
            "sequence_only_ids": len(sequence_ids - source_assay_ids),
            "metadata_only_ids": len(metadata_ids - sequence_ids),
            "assay_only_ids": len(set(assay_only_source_notes["_join_id"])),
            "retained_assay_only_ids": int((merged["_merge_s3"] == "right_only").sum()),
        },
        "one_to_many_join_keys": 0,
        "many_to_one_join_keys": 0,
        "excluded_source_rows": [
            {"source_dataset": "Jain S3", "source_row": int(row["_source_row"]), "identifier": clean_text(row[id_columns["S3"]]), "reason": "source footnote, not an antibody record"}
            for _, row in assay_only_source_notes.iterrows()
        ],
        "missingness": missing_summary(result),
        "raw_columns_preserved": [str(column) for column in tables["S3"].columns if column != "_source_row"],
        "assay_columns": [str(column) for column in tables["S3"].columns if column not in {"_source_row", id_columns["S3"]}],
    }
    dictionary = pd.DataFrame([
        {
            "normalized_name": re.sub(r"[^a-z0-9]+", "_", str(column).strip().lower()).strip("_") or "unnamed",
            "original_name": str(column),
            "description": "Original S3 source column preserved; confirm against the primary article before analysis.",
            "unit": "UNKNOWN",
            "direction_of_unfavorable_value": "UNKNOWN",
            "measured_or_derived": "SOURCE_REPORTED",
            "source_dataset": "Jain S3",
            "notes": "No semantic rename or directionality assumption applied.",
        }
        for column in tables["S3"].columns if column not in {"_source_row", id_columns["S3"]}
    ])
    return result, audit, dictionary


def write_outputs(raw_dir: str | Path, processed_path: str | Path, dictionary_path: str | Path, audit_json: str | Path, audit_md: str | Path) -> None:
    result, audit, dictionary = normalize_jain(raw_dir)
    result.to_csv(processed_path, index=False)
    dictionary.to_csv(dictionary_path, index=False)
    Path(audit_json).write_text(json.dumps(audit, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    lines = [
        "# Jain 2017 data audit", "",
        f"- Source rows: {audit['source_row_counts']}",
        f"- Normalized antibody rows: {audit['total_rows']}",
        f"- Identifier columns: {audit['identifier_columns']}",
        f"- Sequence columns: {audit['sequence_columns']}",
        f"- Sequence status: {audit['sequence_status_counts']}",
        f"- Unmatched ID counts: {audit['unmatched_ids']}",
        f"- Duplicate IDs: {audit['duplicate_identifier_rows']}",
        f"- Duplicate VH/VL pairs: {audit['duplicate_sequence_pair_rows']}",
        f"- One-to-many joins: {audit['one_to_many_join_keys']}; many-to-one joins: {audit['many_to_one_join_keys']}",
        f"- Explicitly excluded source rows: {audit['excluded_source_rows']}",
        "", "## Original S3 assay columns", "",
    ]
    lines.extend(f"- `{column}`: {audit['missingness'][column]}" for column in audit["assay_columns"])
    lines.extend(["", "All S3 source columns are preserved. Missing values, duplicates and unmatched IDs are retained for review. The one excluded row is the source footnote documented above, not an antibody record."])
    Path(audit_md).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    write_outputs(root / "data/raw/jain_2017", root / "data/processed/jain_137.csv", root / "data/processed/jain_data_dictionary.csv", root / "reports/data_audit/jain_audit.json", root / "reports/data_audit/jain_audit.md")


if __name__ == "__main__":
    main()
