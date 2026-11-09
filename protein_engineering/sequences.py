"""Protein identity normalization only. No antibody rules, numbering or scores."""
from dataclasses import dataclass
import hashlib

_UPPER = str.maketrans("abcdefghijklmnopqrstuvwxyz", "ABCDEFGHIJKLMNOPQRSTUVWXYZ")
_ALPHABET = frozenset("ACDEFGHIKLMNPQRSTVWYUOBZXJ")


@dataclass(frozen=True)
class ProteinSequence:
    original: str
    normalized: str
    sha256: str
    status: str
    invalid_characters: tuple[str, ...]
    notes: tuple[str, ...]


def normalize_sequence(value: str) -> ProteinSequence:
    if not isinstance(value, str):
        raise ValueError("sequence 必须为文本，不接受数字或缺失值")
    normalized = "".join(value.split()).translate(_UPPER)
    invalid = tuple(sorted(set(normalized) - _ALPHABET))
    notes = []
    if "".join(value.split()) != value:
        notes.append("WHITESPACE_REMOVED")
    if normalized != "".join(value.split()):
        notes.append("ASCII_CASE_NORMALIZED")
    if set(normalized) & set("BZXJ"):
        notes.append("AMBIGUOUS_RESIDUES_RETAINED")
    if set(normalized) & set("UO"):
        notes.append("SELENOCYSTEINE_OR_PYRROLYSINE_RETAINED")
    status = "INVALID" if invalid or not normalized else "AMBIGUOUS" if set(normalized) & set("BZXJ") else "VALID"
    return ProteinSequence(value, normalized, hashlib.sha256(normalized.encode("utf-8")).hexdigest(), status, invalid, tuple(notes))
