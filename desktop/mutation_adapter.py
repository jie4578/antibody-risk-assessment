"""Deterministic Desktop mutation-domain adapter.

This module owns Desktop input validation and comparison presentation only.
Scientific scanning and scoring remain in core.py and scoring.py.
"""

from __future__ import annotations

from dataclasses import dataclass
import re

from core import VALID_AMINO_ACIDS, analyze_sequence, mutate_sequence, normalize_sequence, validate_sequence
from scoring import compute_risk_score


CDR_ARGS = (31, 35, 50, 65, 99, 110)
_MUTATION_RE = re.compile(r"([A-Za-z])(\d+)([A-Za-z])\Z")
_CHAINS = {"VH", "VL", "UNSPECIFIED"}


class MutationValidationError(ValueError):
    """User-presentable validation error for the Desktop mutation workflow."""


@dataclass(frozen=True)
class RiskSite:
    chain: str
    position: str | int
    motif: str
    category: str
    region: str


@dataclass(frozen=True)
class MutationComparison:
    antibody_id: str
    chain: str
    mutation: str
    original_sequence: str
    mutant_sequence: str
    original_score: float
    original_level: str
    original_total_sites: int
    original_cdr_sites: int
    mutant_score: float
    mutant_level: str
    mutant_total_sites: int
    mutant_cdr_sites: int
    delta_score: float
    delta_total_sites: int
    delta_cdr_sites: int
    removed_risks: tuple[RiskSite, ...]
    added_risks: tuple[RiskSite, ...]
    unchanged_risks: tuple[RiskSite, ...]


def normalize_mutation(mutation: str) -> str:
    value = str(mutation or "").strip()
    match = _MUTATION_RE.fullmatch(value)
    if not match:
        raise MutationValidationError("Invalid mutation format; use one mutation such as N55Q.")
    old, position, new = match.groups()
    old, new = old.upper(), new.upper()
    if old not in VALID_AMINO_ACIDS:
        raise MutationValidationError(f"Invalid source residue: {old}.")
    if new not in VALID_AMINO_ACIDS:
        raise MutationValidationError(f"Invalid target residue: {new}.")
    if old == new:
        raise MutationValidationError("Mutation does not change the residue.")
    if int(position) < 1:
        raise MutationValidationError("Mutation position must be 1-based and greater than zero.")
    return f"{old}{int(position)}{new}"


def _site(chain: str, risk) -> RiskSite:
    return RiskSite(chain, risk.position, risk.motif, risk.category, risk.region)


def _site_key(site: RiskSite):
    try:
        position = int(str(site.position).split("-", 1)[0])
    except (TypeError, ValueError):
        position = 0
    return (site.chain, position, str(site.position), site.motif, site.category, site.region)


def _sites(chain: str, analysis) -> tuple[RiskSite, ...]:
    return tuple(sorted((_site(chain, risk) for risk in analysis.risks), key=_site_key))


def compare_mutation(
    sequence: str,
    mutation: str,
    antibody_id: str = "",
    chain: str | None = "Unspecified",
) -> MutationComparison:
    """Validate, simulate and compare one independent mutation to its baseline."""
    original = normalize_sequence(sequence)
    valid, error = validate_sequence(original, allow_empty=False)
    if not valid:
        raise MutationValidationError(error)
    canonical_mutation = normalize_mutation(mutation)
    canonical_chain = str(chain or "Unspecified").strip().upper()
    if canonical_chain not in _CHAINS:
        raise MutationValidationError("Chain must be VH, VL, or Unspecified.")
    canonical_chain = "Unspecified" if canonical_chain == "UNSPECIFIED" else canonical_chain

    try:
        mutant = mutate_sequence(original, canonical_mutation)
    except ValueError as exc:
        raise MutationValidationError(str(exc)) from exc
    original_analysis = analyze_sequence(original, *CDR_ARGS)
    mutant_analysis = analyze_sequence(mutant, *CDR_ARGS)
    original_score = compute_risk_score([(canonical_chain, original_analysis)])
    mutant_score = compute_risk_score([(canonical_chain, mutant_analysis)])
    original_sites = set(_sites(canonical_chain, original_analysis))
    mutant_sites = set(_sites(canonical_chain, mutant_analysis))
    sort_key = _site_key
    return MutationComparison(
        antibody_id=str(antibody_id or ""), chain=canonical_chain, mutation=canonical_mutation,
        original_sequence=original, mutant_sequence=mutant,
        original_score=original_score.overall_score, original_level=original_score.risk_level,
        original_total_sites=len(original_sites), original_cdr_sites=sum(s.region.startswith("CDR") for s in original_sites),
        mutant_score=mutant_score.overall_score, mutant_level=mutant_score.risk_level,
        mutant_total_sites=len(mutant_sites), mutant_cdr_sites=sum(s.region.startswith("CDR") for s in mutant_sites),
        delta_score=round(mutant_score.overall_score - original_score.overall_score, 2),
        delta_total_sites=len(mutant_sites) - len(original_sites),
        delta_cdr_sites=sum(s.region.startswith("CDR") for s in mutant_sites) - sum(s.region.startswith("CDR") for s in original_sites),
        removed_risks=tuple(sorted(original_sites - mutant_sites, key=sort_key)),
        added_risks=tuple(sorted(mutant_sites - original_sites, key=sort_key)),
        unchanged_risks=tuple(sorted(original_sites & mutant_sites, key=sort_key)),
    )
