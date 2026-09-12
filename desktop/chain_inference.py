from __future__ import annotations

from dataclasses import dataclass

from core import normalize_sequence, validate_sequence


@dataclass(frozen=True)
class ChainPrediction:
    chain: str
    confidence: float
    reason: str


@dataclass(frozen=True)
class ColumnChainPrediction:
    chain: str
    confidence: float
    vh_count: int
    vl_count: int
    unknown_count: int
    total_valid: int
    total_unknown: int


def infer_chain(sequence) -> ChainPrediction:
    sequence = normalize_sequence(sequence)
    valid, _ = validate_sequence(sequence, allow_empty=False)
    if not valid or len(sequence) < 80:
        return ChainPrediction("UNKNOWN", 0.0, "invalid or too short for chain inference")
    vh = vl = 0; signals = []
    prefix = sequence[:8]
    if prefix.startswith(("EVQL", "QVQL", "VQL", "DVQL")):
        vh += 3; signals.append("VH-like N-terminus")
    if prefix.startswith(("DIQM", "DIVM", "EIVL", "QIVL")):
        vl += 3; signals.append("VL-like N-terminus")
    if "WGQG" in sequence or "CSRW" in sequence:
        vh += 1; signals.append("VH-like variable-domain motif")
    if "CQQ" in sequence or "FGG" in sequence:
        vl += 1; signals.append("VL-like variable-domain motif")
    if vh == vl or max(vh, vl) < 3:
        return ChainPrediction("UNKNOWN", 0.0, "insufficient or conflicting sequence signals")
    chain, score = ("VH", vh) if vh > vl else ("VL", vl)
    confidence = round(min(0.99, 0.7 + 0.1 * min(score, 2)), 2)
    return ChainPrediction(chain, confidence, "; ".join(signals))


def infer_column_chain(sequences, max_samples=100) -> ColumnChainPrediction:
    vh = vl = unknown = valid_total = 0
    for sequence in list(sequences)[:max_samples]:
        prediction = infer_chain(sequence)
        if prediction.chain == "VH": vh += 1; valid_total += 1
        elif prediction.chain == "VL": vl += 1; valid_total += 1
        elif normalize_sequence(sequence): unknown += 1
    classified = vh + vl
    if not classified: chain, confidence = "UNKNOWN", 0.0
    else:
        dominant, dominant_count, other = (("VH", vh, vl) if vh >= vl else ("VL", vl, vh))
        fraction = dominant_count / classified
        chain, confidence = (dominant, fraction) if fraction >= 0.9 and (classified >= 3 or other == 0) else ("AMBIGUOUS", fraction)
    return ColumnChainPrediction(chain, confidence, vh, vl, unknown, valid_total, unknown)
