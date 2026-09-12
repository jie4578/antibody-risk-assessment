from __future__ import annotations

from pathlib import Path

import pandas as pd

from desktop.batch_adapter import BatchResult


EXPORT_COLUMNS = [
    "antibody_id", "VH_length", "VL_length", "risk_score", "risk_level",
    "total_sites", "CDR_sites", "PTM_sites", "liability_sites",
    "analysis_status", "warnings",
]


def summary_frame(result: BatchResult) -> pd.DataFrame:
    rows = []
    for record in result.records:
        rows.append({
            "antibody_id": record.antibody_id,
            "VH_length": record.vh_length or None,
            "VL_length": record.vl_length or None,
            "risk_score": None if pd.isna(record.risk_score) else record.risk_score,
            "risk_level": record.risk_level,
            "total_sites": record.total_sites,
            "CDR_sites": record.cdr_sites,
            "PTM_sites": record.ptm_sites,
            "liability_sites": record.liability_sites,
            "analysis_status": record.status,
            "warnings": "; ".join(record.warnings),
        })
    return pd.DataFrame(rows, columns=EXPORT_COLUMNS)


def write_summary_csv(result: BatchResult, path) -> None:
    summary_frame(result).to_csv(Path(path), index=False)


def write_summary_xlsx(result: BatchResult, path) -> None:
    with pd.ExcelWriter(Path(path), engine="openpyxl") as writer:
        summary_frame(result).to_excel(writer, index=False, sheet_name="Batch Summary")


def write_template(path) -> None:
    pd.DataFrame(columns=["antibody_id", "VH", "VL"]).to_excel(Path(path), index=False, sheet_name="Antibody Input")
