"""Dataset-neutral schema for the Phase 7A normalized table."""

from __future__ import annotations

from typing import Any

import pandas as pd


NORMALIZED_COLUMNS = (
    "dataset",
    "record_id",
    "antibody_id",
    "VH",
    "VL",
    "sequence_status",
    "sequence_status_reason",
    "sequence_hash",
    "source",
    "species",
    "format",
    "family",
    "family_source",
    "experimental_labels",
    "label_status",
    "structure_method",
    "resolution",
    "pdb_id",
    "heavy_subclass",
    "light_subclass",
    "source_row_index",
    "raw_record_id",
    "raw_antibody_id",
    "raw_VH",
    "raw_VL",
    "source_row_json",
)


def validate_normalized_frame(frame: pd.DataFrame) -> None:
    missing = set(NORMALIZED_COLUMNS) - set(frame.columns)
    if missing:
        raise ValueError(f"normalized table missing columns: {sorted(missing)}")
    if frame["record_id"].map(_clean).eq("").any():
        raise ValueError("normalized table contains a missing record_id")
    if not frame["sequence_status"].isin({"VALID", "PARTIAL", "INVALID"}).all():
        raise ValueError("sequence_status contains an unknown value")
    if not frame["label_status"].isin({"AVAILABLE", "MISSING"}).all():
        raise ValueError("label_status contains an unknown value")


def _clean(value: Any) -> str:
    if value is None:
        return ""
    try:
        if bool(pd.isna(value)):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()
