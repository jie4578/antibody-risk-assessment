from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from batch_analysis import batch_analysis
from core import analyze_sequence, normalize_sequence
from input_parser import parse_fasta
from desktop.column_mapping import apply_mapping, infer_smart_mapping
from desktop.chain_inference import infer_chain


CDR_ARGS = (31, 35, 50, 65, 99, 110)
REQUIRED = {"antibody_id", "VH", "VL"}


@dataclass
class BatchRecord:
    antibody_id: str
    vh_length: int = 0
    vl_length: int = 0
    risk_score: float = float("nan")
    risk_level: str = "N/A"
    total_sites: int = 0
    cdr_sites: int = 0
    ptm_sites: int = 0
    liability_sites: int = 0
    status: str = "INVALID"
    warnings: list[str] = field(default_factory=list)
    risks: list = field(default_factory=list)
    vh_sequence: str = ""
    vl_sequence: str = ""


@dataclass
class BatchResult:
    records: list[BatchRecord]
    source_name: str

    @property
    def loaded(self): return len(self.records)
    @property
    def success(self): return sum(r.status in {"SUCCESS", "WARNING"} for r in self.records)
    @property
    def partial(self): return sum(r.status == "PARTIAL" for r in self.records)
    @property
    def invalid(self): return sum(r.status == "INVALID" for r in self.records)


def _cell(value):
    if value is None: return ""
    try:
        if pd.isna(value): return ""
    except (TypeError, ValueError): pass
    return str(value).strip()


class MappingRequiredError(ValueError):
    pass


def input_mapping(source):
    path = Path(source)
    if path.suffix.lower() not in {".csv", ".xlsx"}: return None
    frame = pd.read_csv(path, nrows=100) if path.suffix.lower() == ".csv" else pd.read_excel(path, nrows=100)
    mapping, ambiguous = infer_smart_mapping(frame)
    return None if ambiguous else mapping


def fasta_requires_chain(source):
    path = Path(source)
    if path.suffix.lower() not in {".fasta", ".fa", ".faa"}: return False
    sequence = []; chainless = False
    for line in path.read_text(encoding="utf-8").splitlines() + [">__end__"]:
        if line.startswith(">"):
            if chainless and infer_chain("".join(sequence)).chain == "UNKNOWN": return True
            token = line[1:].strip().split()[0] if line != ">__end__" else ""
            label = token.rsplit("|", 1)[-1] if "|" in token else (token.rsplit("_", 1)[-1] if "_" in token else "")
            chainless = bool(line != ">__end__" and label.upper().replace("-", "_") not in {"VH", "H", "HC", "HEAVY", "HEAVY_CHAIN", "HEAVYCHAIN", "VL", "L", "LC", "LIGHT", "LIGHT_CHAIN", "LIGHTCHAIN"}); sequence = []
        elif chainless: sequence.append(line)
    return False


def _load_frame(path: Path, mapping=None) -> pd.DataFrame:
    if path.suffix.lower() == ".csv": df = pd.read_csv(path)
    elif path.suffix.lower() == ".xlsx": df = pd.read_excel(path)
    else: raise ValueError("Unsupported file type. Use CSV, XLSX, or FASTA.")
    if mapping is None:
        mapping, ambiguous = infer_smart_mapping(df)
        if ambiguous: raise MappingRequiredError("Please confirm column mapping")
    out = apply_mapping(df, mapping)
    out["antibody_id"] = out["antibody_id"].map(_cell)
    out["VH"] = out["VH"].map(lambda v: normalize_sequence(_cell(v)))
    out["VL"] = out["VL"].map(lambda v: normalize_sequence(_cell(v)))
    return out


def _smart_fasta(path: Path, chain=None) -> pd.DataFrame:
    content = path.read_text(encoding="utf-8"); lines = []; current_header = None; sequence_lines = []
    chain_aliases = {"VH": {"VH", "H", "HC", "HEAVY", "HEAVYCHAIN"}, "VL": {"VL", "L", "LC", "LIGHT", "LIGHTCHAIN"}}
    def flush():
        if current_header is None: return
        token = current_header[1:].strip().split()[0]; parts = token.split("|", 1)
        aid, label = (parts[0], parts[1]) if len(parts) == 2 else (token.rsplit("_", 1)[0], token.rsplit("_", 1)[1] if "_" in token else "")
        normalized = label.upper().replace("-", "_")
        selected = next((name for name, aliases in chain_aliases.items() if normalized in aliases), None)
        if selected is None:
            selected = chain or infer_chain("".join(sequence_lines)).chain
            if selected not in chain_aliases: raise MappingRequiredError("FASTA sequences without chain labels require VH or VL selection")
            aid = token
        lines.append(f">{aid}|{selected}"); lines.extend(sequence_lines)
    for line in content.splitlines():
        if line.startswith(">"):
            flush(); current_header = line; sequence_lines = []
        elif current_header is not None: sequence_lines.append(line)
    flush()
    return parse_fasta("\n".join(lines))


def _frame(path: Path, mapping=None, chain=None) -> pd.DataFrame:
    if path.suffix.lower() in {".fasta", ".fa", ".faa"}: return _smart_fasta(path, chain)
    return _load_frame(path, mapping)


def analyze_file(source, mapping=None, chain=None) -> BatchResult:
    path = Path(source)
    frame = _frame(path, mapping, chain)
    duplicate_counts = frame["antibody_id"].value_counts(dropna=False).to_dict()
    summary = batch_analysis(frame, *CDR_ARGS)
    records = []
    for index, row in frame.reset_index(drop=True).iterrows():
        sid = _cell(row.get("antibody_id"))
        warnings = []
        if not sid:
            sid = f"Unnamed-{index + 1:03d}"; warnings.append("Original antibody ID was blank")
        if duplicate_counts.get(_cell(row.get("antibody_id")), 0) > 1:
            warnings.append("Duplicate antibody ID")
        result_row = summary.iloc[index]
        vh = analyze_sequence(row["VH"], *CDR_ARGS) if row["VH"] else None
        vl = analyze_sequence(row["VL"], *CDR_ARGS) if row["VL"] else None
        risks = ([('VH', risk) for risk in vh.risks] if vh is not None else []) + ([('VL', risk) for risk in vl.risks] if vl is not None else [])
        risk_items = [risk for _, risk in risks]
        status = {"success": "SUCCESS", "partial_error": "PARTIAL", "error": "INVALID"}.get(result_row["analysis_status"], "INVALID")
        if status == "SUCCESS" and warnings: status = "WARNING"
        records.append(BatchRecord(sid, int(result_row["VH_length"]), int(result_row["VL_length"]), result_row["risk_score"], result_row["risk_level"], len(risk_items), sum(str(r.region).startswith("CDR") for r in risk_items), sum(r.category in {"N-糖基化", "O-糖基化"} for r in risk_items), sum(r.category not in {"N-糖基化", "O-糖基化"} for r in risk_items), status, warnings + ([result_row["warnings"]] if _cell(result_row["warnings"]) else []), risks, row["VH"], row["VL"]))
    records.sort(key=lambda r: (r.status == "INVALID", -(r.risk_score if pd.notna(r.risk_score) else float("-inf"))))
    return BatchResult(records, path.name)
