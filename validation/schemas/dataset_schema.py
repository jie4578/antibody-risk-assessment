"""Small, dataset-neutral helpers for validation tables.

Sequence validation deliberately delegates to the product's existing
``core.validate_sequence`` implementation. No scientific rule is copied here.
"""

from __future__ import annotations

import hashlib
import math
from typing import Any

import pandas as pd

from core import normalize_sequence, validate_sequence

COMMON_COLUMNS = [
    "dataset", "record_id", "antibody_id", "VH", "VL", "sequence_status",
    "sequence_status_reason", "sequence_hash",
]


def is_missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def clean_text(value: Any) -> str:
    return "" if is_missing(value) else str(value).strip()


def assess_sequences(vh: Any, vl: Any) -> tuple[str, str, str, str]:
    vh_norm, vl_norm = normalize_sequence(clean_text(vh)), normalize_sequence(clean_text(vl))
    vh_ok, vh_error = validate_sequence(vh_norm, allow_empty=True)
    vl_ok, vl_error = validate_sequence(vl_norm, allow_empty=True)
    if not vh_ok or not vl_ok:
        status = "INVALID"
    elif vh_ok and vl_ok and vh_norm and vl_norm:
        status = "VALID"
    elif (vh_ok and vh_norm) or (vl_ok and vl_norm):
        status = "PARTIAL"
    else:
        status = "INVALID"
    reasons = []
    if not vh_norm:
        reasons.append("VH missing")
    elif not vh_ok:
        reasons.append(f"VH: {vh_error}")
    if not vl_norm:
        reasons.append("VL missing")
    elif not vl_ok:
        reasons.append(f"VL: {vl_error}")
    return vh_norm, vl_norm, status, "; ".join(reasons)


def sequence_hash(vh: Any, vl: Any) -> str:
    vh_norm, vl_norm, _, _ = assess_sequences(vh, vl)
    # UTF-8 keeps the hash total and deterministic even when an invalid raw
    # sequence contains a non-ASCII character; validation still reports it as
    # INVALID rather than dropping the record.
    return hashlib.sha256(f"{vh_norm}\n{vl_norm}".encode("utf-8", "surrogatepass")).hexdigest()


def missing_summary(frame: pd.DataFrame) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for column in frame.columns:
        missing = int(frame[column].map(is_missing).sum())
        total = len(frame)
        result[str(column)] = {
            "non_missing_n": total - missing,
            "missing_n": missing,
            "missing_percentage": round((missing / total * 100) if total else 0.0, 4),
        }
    return result


def duplicate_count(frame: pd.DataFrame, column: str) -> int:
    if column not in frame:
        return 0
    values = frame[column].map(clean_text)
    return int(values[values != ""].duplicated(keep=False).sum())


def json_safe(value: Any) -> Any:
    if is_missing(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    if isinstance(value, float) and math.isnan(value):
        return None
    return value
