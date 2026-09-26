"""Normalize SAbDab2 sequences without deduplicating source records."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from validation.schemas.dataset_schema import assess_sequences, sequence_hash

from .schema import NORMALIZED_COLUMNS, validate_normalized_frame


REQUIRED_SOURCE_COLUMNS = {"INSTANCE", "SABDAB_ID", "VH", "VL"}


def _clean(value: Any) -> str:
    if value is None:
        return ""
    try:
        if bool(pd.isna(value)):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _json_value(value: Any) -> Any:
    return None if value is None or (isinstance(value, float) and pd.isna(value)) else value


def normalize_sabdab2_summary(source_path: str | Path, output_path: str | Path | None = None) -> pd.DataFrame:
    """Return a row-preserving normalized table from an official SAbDab2 CSV."""

    source = Path(source_path)
    raw = pd.read_csv(source, dtype=object, keep_default_na=False)
    missing = REQUIRED_SOURCE_COLUMNS - set(raw.columns)
    if missing:
        raise ValueError(f"SAbDab2 source missing columns: {sorted(missing)}")

    rows: list[dict[str, Any]] = []
    for source_row_index, (_, raw_row) in enumerate(raw.iterrows()):
        raw_vh = _clean(raw_row.get("VH"))
        raw_vl = _clean(raw_row.get("VL"))
        vh, vl, status, reason = assess_sequences(raw_vh, raw_vl)
        raw_payload = {str(key): _json_value(value) for key, value in raw_row.items()}
        raw_record_id = _clean(raw_row.get("INSTANCE"))
        raw_antibody_id = _clean(raw_row.get("SABDAB_ID"))
        rows.append(
            {
                "dataset": "SAbDab2",
                "record_id": raw_record_id,
                "antibody_id": raw_antibody_id,
                "VH": vh,
                "VL": vl,
                "sequence_status": status,
                "sequence_status_reason": reason,
                "sequence_hash": sequence_hash(raw_vh, raw_vl),
                "source": "SAbDab2 / Oxford Protein Informatics Group",
                "species": _clean(raw_row.get("organism")),
                "format": _clean(raw_row.get("type")),
                "family": "",
                "family_source": "not provided; assigned only by identity clustering",
                "experimental_labels": "",
                "label_status": "MISSING",
                "structure_method": _clean(raw_row.get("method")),
                "resolution": _clean(raw_row.get("resolution")),
                "pdb_id": _clean(raw_row.get("PDB")),
                "heavy_subclass": _clean(raw_row.get("heavy_subclass")),
                "light_subclass": _clean(raw_row.get("light_subclass")),
                "source_row_index": source_row_index,
                "raw_record_id": raw_record_id,
                "raw_antibody_id": raw_antibody_id,
                "raw_VH": raw_vh,
                "raw_VL": raw_vl,
                "source_row_json": json.dumps(raw_payload, sort_keys=True, ensure_ascii=False),
            }
        )
    normalized = pd.DataFrame(rows, columns=NORMALIZED_COLUMNS)
    validate_normalized_frame(normalized)
    if output_path is not None:
        destination = Path(output_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        normalized.to_csv(destination, index=False)
    return normalized
