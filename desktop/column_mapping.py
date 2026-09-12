from __future__ import annotations

import re
import unicodedata

from desktop.chain_inference import infer_column_chain


def normalize_column_name(value):
    value = unicodedata.normalize("NFKC", str(value or "")).strip().casefold()
    return re.sub(r"[\s_-]+", "", value)


ALIASES = {
    "antibody_id": {"antibodyid", "id", "antibody", "clone", "cloneid", "sample", "sampleid", "antibodynumber", "抗体编号", "抗体id", "样本编号", "克隆编号"},
    "VH": {"vh", "heavy", "heavychain", "heavysequence", "heavychainsequence", "hc", "hchain", "重链", "重链序列", "重链氨基酸序列", "vhsequence"},
    "VL": {"vl", "light", "lightchain", "lightsequence", "lightchainsequence", "lc", "lchain", "轻链", "轻链序列", "轻链氨基酸序列", "vlsequence"},
    "Sequence": {"sequence", "seq", "antibodysequence", "proteinsequence", "aasequence", "aminoacidsequence", "序列", "蛋白序列", "氨基酸序列"},
}


def infer_mapping(columns):
    columns = list(columns)
    candidates = {field: [column for column in columns if normalize_column_name(column) in {normalize_column_name(alias) for alias in aliases}] for field, aliases in ALIASES.items()}
    mapping = {}
    ambiguous = []
    for field in ("antibody_id", "VH", "VL"):
        if len(candidates[field]) == 1: mapping[field] = candidates[field][0]
        elif len(candidates[field]) > 1: ambiguous.append(field)
    if len(candidates["Sequence"]) == 1: mapping["Sequence"] = candidates["Sequence"][0]
    elif len(candidates["Sequence"]) > 1: ambiguous.append("Sequence")
    if "VH" in mapping and "Sequence" in mapping: mapping.pop("Sequence")
    usable = "VH" in mapping or "VL" in mapping or "Sequence" in mapping
    return mapping, bool(ambiguous) or not usable, candidates


def apply_mapping(frame, mapping):
    out = frame.copy()
    def selected(field):
        column = mapping.get(field)
        return out[column] if column else ""
    result = out.__class__({"antibody_id": selected("antibody_id"), "VH": selected("VH"), "VL": selected("VL")})
    sequence_column = mapping.get("Sequence")
    if sequence_column and "VH" not in mapping and "VL" not in mapping: result["VH"] = out[sequence_column]; result["VL"] = ""
    return result[["antibody_id", "VH", "VL"]]


def infer_smart_mapping(frame):
    mapping, ambiguous, candidates = infer_mapping(frame.columns)
    if ambiguous and any(candidates[field] for field in ("VH", "VL")):
        return mapping, ambiguous
    used = set(mapping.values())
    strong = []; unknown_columns = []
    for column in frame.columns:
        if column not in used:
            prediction = infer_column_chain(frame[column])
            if prediction.chain in {"VH", "VL"} and prediction.confidence >= 0.9: strong.append((column, prediction.chain))
            elif prediction.unknown_count or prediction.chain == "AMBIGUOUS": unknown_columns.append(column)
    for chain in ("VH", "VL"):
        matches = [column for column, predicted in strong if predicted == chain]
        if chain not in mapping and len(matches) == 1: mapping[chain] = matches[0]
    return mapping, bool(unknown_columns) or not ("VH" in mapping or "VL" in mapping or "Sequence" in mapping)
