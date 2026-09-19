"""Deterministic aggregation of already-computed research evidence.

This module deliberately has no Qt, provider, literature-client, rule-engine,
or ML-runtime dependency.  It converts structured application state into a
snapshot for human review; it never calculates a new scientific result.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, fields, is_dataclass, replace
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from desktop.ml_metadata import BENCHMARK_ID, BENCHMARK_SCOPE, LIMITATION, RESEARCH_SUPPORT_NOTICE, evidence_text


RULE_LIMITATION = (
    "Rule-based liability screening does not constitute broad antibody "
    "developability prediction."
)
FAMILY_LIMITATION = (
    "Phase 5 ML benchmark is internal and contains substantial residual "
    "sequence similarity: 84/95 held-out TEST sequences had paired-min "
    "identity >=0.90 to training data."
)
GENERALIZATION_LIMITATION = "Family-independent generalization is unknown."
ML_VERIFICATION_LIMITATION = "ML estimates require experimental verification."
MUTATION_EFFECT_LIMITATION = (
    "Mutation ML deltas are not validated mutation-effect measurements."
)
LITERATURE_LIMITATION = (
    "Literature evidence may provide mechanism/context without validating "
    "this exact antibody or mutation."
)
MUTATION_ML_WARNING = (
    "ML Δ values are differences between model estimates and are not "
    "validated experimental mutation-effect measurements."
)
MUTATION_ML_EXPANDED_LIMITATION = (
    "The underlying models were benchmarked on antibody-level experimental "
    "properties. Single-mutation effect-size accuracy has not been "
    "independently validated."
)


def _data(value: Any) -> Any:
    """Convert application DTOs to plain deterministic data without invoking them."""

    if is_dataclass(value):
        return {field.name: _data(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): _data(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_data(item) for item in value]
    if isinstance(value, set):
        return sorted((_data(item) for item in value), key=lambda item: repr(item))
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return _data(value.to_dict())
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _get(value: Any, *names: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        for name in names:
            if name in value and value[name] is not None:
                return value[name]
    else:
        for name in names:
            item = getattr(value, name, None)
            if item is not None:
                return item
    return default


def _plain(value: Any) -> Any:
    return _data(value)


def _sequence_hash(value: Any) -> str:
    normalized = "".join(str(value or "").split()).upper()
    if not normalized:
        return ""
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _risk_site(value: Any) -> Dict[str, Any]:
    item = _plain(value)
    if not isinstance(item, Mapping):
        return {"value": item}
    return {
        key: item[key]
        for key in ("chain", "position", "motif", "category", "region")
        if key in item
    }


def _sequence_section(state: Any) -> Dict[str, Any]:
    raw = _plain(_get(state, "sequence_analysis", "rule_analysis", "single_analysis", "sequence", default={}))
    if not isinstance(raw, Mapping):
        raw = {}
    analysis = raw.get("analysis") or {}
    if not isinstance(analysis, Mapping):
        analysis = _plain(analysis)
    score = raw.get("risk_score", raw.get("score"))
    if isinstance(score, Mapping):
        calculated_score = score.get("overall_score", score.get("calculated_score"))
        risk_level = score.get("risk_level", raw.get("risk_level"))
    else:
        calculated_score = score
        risk_level = raw.get("risk_level")
    risks = raw.get("risks", analysis.get("risks", raw.get("detected_sites", []))) or []
    site_rows = [_risk_site(item) for item in risks]
    total_sites = raw.get("total_sites")
    if total_sites is None and site_rows:
        total_sites = len(site_rows)
    cdr_sites = raw.get("cdr_sites")
    if cdr_sites is None and site_rows:
        cdr_sites = sum(str(item.get("region", "")).upper().startswith("CDR") for item in site_rows)
    categories = raw.get("categories")
    if categories is None:
        categories = sorted({str(item.get("category", "")) for item in site_rows if item.get("category")})
    vh = raw.get("vh")
    vl = raw.get("vl")
    sequence = raw.get("sequence")
    hashes = dict(raw.get("sequence_hashes", {}) or {})
    if vh and "VH" not in hashes:
        hashes["VH"] = _sequence_hash(vh)
    if vl and "VL" not in hashes:
        hashes["VL"] = _sequence_hash(vl)
    if sequence and not hashes:
        hashes["sequence"] = _sequence_hash(sequence)
    output: Dict[str, Any] = {
        "antibody_id": raw.get("antibody_id", _get(state, "antibody_id", default="")) or "",
        "chain_context": raw.get("chain_context", raw.get("chain", "")) or "",
        "calculated_score": calculated_score,
        "risk_level": risk_level,
        "total_sites": total_sites,
        "cdr_sites": cdr_sites,
        "categories": list(categories or []),
        "representative_sites": site_rows[:10],
        "sequence_hashes": hashes,
    }
    if raw.get("sequence_length") is not None:
        output["sequence_length"] = raw["sequence_length"]
    if raw.get("rule_result_id") is not None:
        output["rule_result_id"] = raw["rule_result_id"]
    return output


def _ml_section(value: Any) -> Optional[Dict[str, Any]]:
    if value is None:
        return None
    raw = _plain(value)
    if not isinstance(raw, Mapping):
        return None
    result = raw.get("result", raw)
    if not isinstance(result, Mapping):
        result = {}
    hic = result.get("hic", {}) or {}
    developability = result.get("developability", {}) or {}
    metadata = result.get("metadata", {}) or {}
    provenance = raw.get("provenance", {}) or {}
    if isinstance(hic, Mapping):
        hic_value = hic.get("predicted_hic", hic.get("predicted_value", hic.get("value")))
        hic_model_id = hic.get("model_id")
    else:
        hic_value = hic
        hic_model_id = None
    if isinstance(developability, Mapping):
        probability = developability.get("probability_not_developable", developability.get("value"))
        developability_model_id = developability.get("model_id")
    else:
        probability = developability
        developability_model_id = None
    model_ids = metadata.get("model_ids", {}) if isinstance(metadata, Mapping) else {}
    output: Dict[str, Any] = {
        "hic_estimate": hic_value,
        "probability_not_developable": probability,
        "hic_model_id": hic_model_id or _get(provenance, "hic_model_id", default=None) or _get(model_ids, "hic", default=None),
        "developability_model_id": developability_model_id or _get(provenance, "developability_model_id", default=None) or _get(model_ids, "developability", default=None),
        "benchmark": _get(provenance, "benchmark", default=None) or _get(metadata, "benchmark", default=None) or BENCHMARK_ID,
        "model_version": _get(provenance, "model_version", default=None) or _get(metadata, "model_version", default=None),
        "model_manifest": _get(provenance, "model_manifest", default=None) or _get(metadata, "model_manifest", default=None),
        "scope": BENCHMARK_SCOPE,
        "hic_evidence": evidence_text("hic"),
        "developability_evidence": evidence_text("developability"),
        "research_support": True,
        "experimental_verification_required": True,
        "no_categorical_threshold": True,
    }
    for key in ("device", "vh_sha256_prefix", "vl_sha256_prefix"):
        if key in provenance:
            output[key] = provenance[key]
    return output


def _mutation_section(value: Any) -> Optional[Dict[str, Any]]:
    if value is None:
        return None
    raw = _plain(value)
    if not isinstance(raw, Mapping):
        return None
    allowed = (
        "antibody_id", "chain", "mutation", "original_score", "mutant_score",
        "delta_score", "original_total_sites", "mutant_total_sites", "delta_total_sites",
        "original_cdr_sites", "mutant_cdr_sites", "delta_cdr_sites",
        "original_level", "mutant_level", "original_sequence", "mutant_sequence",
    )
    output = {key: raw[key] for key in allowed if key in raw}
    for key in ("removed_risks", "added_risks", "unchanged_risks"):
        output[key] = [_risk_site(item) for item in (raw.get(key) or [])]
    sequences = {}
    for name in ("original_sequence", "mutant_sequence"):
        if raw.get(name):
            sequences[name.replace("_sequence", "_hash")] = _sequence_hash(raw[name])
            output.pop(name, None)
    if sequences:
        output["sequence_hashes"] = sequences
    return output


def _literature_section(value: Any) -> List[Dict[str, Any]]:
    if value is None:
        return []
    raw = _plain(value)
    if isinstance(raw, Mapping):
        raw = [raw]
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        raw = [raw]
    fields_to_keep = (
        "evidence_id", "title", "authors", "journal", "year", "pmid", "pmcid",
        "doi", "source", "source_url", "relevance", "is_open_access", "full_text_available",
    )
    result = []
    for item in raw:
        item = _plain(item)
        if not isinstance(item, Mapping):
            continue
        result.append({key: item.get(key, "") for key in fields_to_keep})
    return result


def _mutation_ml_section(value: Any) -> Optional[Dict[str, Any]]:
    if value is None:
        return None
    raw = _plain(value)
    if not isinstance(raw, Mapping):
        return None
    if all(key in raw for key in ("baseline_hic", "mutant_hic", "delta_hic")):
        raw = {
            "baseline": {"hic": raw.get("baseline_hic"), "probability": raw.get("baseline_probability")},
            "mutant": {"hic": raw.get("mutant_hic"), "probability": raw.get("mutant_probability")},
            "delta": {"hic": raw.get("delta_hic"), "probability": raw.get("delta_probability")},
            "metadata": raw.get("metadata", {}),
        }
    return dict(raw)


def _canonical(value: Any) -> Any:
    value = _plain(value)
    if isinstance(value, Mapping):
        return {key: _canonical(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [_canonical(item) for item in value]
    return value


def summary_fingerprint(state: Any) -> str:
    """Return a stable identity for relevant evidence, excluding UI/timestamps."""

    payload = {
        "sequence_analysis": _sequence_section(state),
        "ml_estimates": _ml_section(_get(state, "ml_estimates", "experimental_ml", "single_ml", default=None)),
        "mutation_analysis": _mutation_section(_get(state, "mutation_analysis", "mutation_comparison", "mutation", default=None)),
        "mutation_ml": _mutation_ml_section(_get(state, "mutation_ml", default=None)),
        "literature_evidence": _literature_section(_get(state, "literature_evidence", "selected_literature", "literature", default=None)),
    }
    encoded = json.dumps(_canonical(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ResearchDecisionSummary:
    """Structured evidence snapshot; no overall score or final verdict exists."""

    sequence_analysis: Dict[str, Any]
    ml_estimates: Optional[Dict[str, Any]]
    mutation_analysis: Optional[Dict[str, Any]]
    mutation_ml: Optional[Dict[str, Any]]
    literature_evidence: Tuple[Dict[str, Any], ...]
    evidence_gaps: Tuple[str, ...]
    limitations: Tuple[str, ...]
    provenance: Dict[str, Any]
    fingerprint: str
    created_at_utc: str
    stale: bool = False

    @property
    def is_stale(self) -> bool:
        return self.stale

    def mark_stale(self) -> "ResearchDecisionSummary":
        return replace(self, stale=True)

    def stale_for(self, state: Any) -> bool:
        return self.fingerprint != summary_fingerprint(state)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sequence_analysis": _plain(self.sequence_analysis),
            "ml_estimates": _plain(self.ml_estimates),
            "mutation_analysis": _plain(self.mutation_analysis),
            "mutation_ml": _plain(self.mutation_ml),
            "literature_evidence": _plain(list(self.literature_evidence)),
            "evidence_gaps": list(self.evidence_gaps),
            "limitations": list(self.limitations),
            "provenance": _plain(self.provenance),
            "fingerprint": self.fingerprint,
            "created_at_utc": self.created_at_utc,
            "stale": self.stale,
        }

    def render_text(self) -> str:
        lines = ["Research Decision Summary", ""]
        if self.stale:
            lines.extend(["Outdated — evidence has changed. Rebuild Summary.", ""])
        lines.extend(["Sequence Liability Screening", "----------------------------"])
        sequence = self.sequence_analysis
        if sequence.get("calculated_score") is None and sequence.get("total_sites") is None:
            lines.append("Rule-based screening result not available.")
        else:
            if sequence.get("calculated_score") is not None:
                lines.append(f"Calculated rule score: {sequence['calculated_score']}")
            if sequence.get("risk_level"):
                lines.append(f"Risk level: {sequence['risk_level']}")
            if sequence.get("total_sites") is not None:
                lines.append(f"Detected liability sites: {sequence['total_sites']}")
            if sequence.get("cdr_sites") is not None:
                lines.append(f"CDR liability sites: {sequence['cdr_sites']}")
            if sequence.get("categories"):
                lines.append("PTM / chemical-liability categories: " + ", ".join(sequence["categories"]))
            sites = sequence.get("representative_sites") or []
            if sites:
                rendered = []
                for site in sites:
                    rendered.append("@".join(str(site.get(key, "")) for key in ("motif", "position", "region") if site.get(key) != ""))
                lines.append("Representative detected sites: " + "; ".join(rendered))
            lines.append("Higher calculated score represents a lower calculated rule penalty; it is not a developability probability.")
        lines.extend(["", "Experimental ML Estimates", "-------------------------"])
        if self.ml_estimates is None:
            lines.append("Experimental ML estimates not calculated.")
        else:
            ml = self.ml_estimates
            if ml.get("hic_estimate") is not None:
                lines.append(f"HIC model estimate: {ml['hic_estimate']}")
            if ml.get("probability_not_developable") is not None:
                lines.append(f"P(NOT_DEVELOPABLE): {ml['probability_not_developable']}")
            lines.append(f"HIC model ID: {ml.get('hic_model_id') or 'not recorded'}")
            lines.append(f"Developability model ID: {ml.get('developability_model_id') or 'not recorded'}")
            lines.append(f"Benchmark: {ml.get('benchmark') or BENCHMARK_ID}; scope: {ml.get('scope') or BENCHMARK_SCOPE}.")
            if ml.get("hic_evidence"):
                lines.append(ml["hic_evidence"])
            if ml.get("developability_evidence"):
                lines.append(ml["developability_evidence"])
            lines.append("Research-support model estimate. Experimental verification is required.")
            lines.append(RESEARCH_SUPPORT_NOTICE)
            lines.append("This benchmark is internal and not family-independent.")
            lines.append("No categorical decision threshold is defined.")
        lines.extend(["", "Mutation Comparison", "--------------------"])
        if self.mutation_analysis is None:
            lines.append("No mutation hypothesis is included in this summary.")
        else:
            mutation = self.mutation_analysis
            for label, key in (("Mutation", "mutation"), ("Chain", "chain"), ("Baseline calculated rule score", "original_score"), ("Mutant calculated rule score", "mutant_score"), ("Score delta", "delta_score")):
                if mutation.get(key) is not None:
                    lines.append(f"{label}: {mutation[key]}")
            for label, key in (("Removed risks", "removed_risks"), ("Added risks", "added_risks"), ("Unchanged risks", "unchanged_risks")):
                lines.append(f"{label}: {len(mutation.get(key) or [])}")
        lines.extend(["", "Mutation ML", "-----------"])
        if self.mutation_ml is None:
            if self.mutation_analysis is not None:
                lines.append("Mutation ML comparison has not been calculated.")
            else:
                lines.append("No Mutation ML comparison is attached.")
        else:
            mm = self.mutation_ml
            baseline = mm.get("baseline", {}) or {}
            mutant = mm.get("mutant", {}) or {}
            delta = mm.get("delta", {}) or {}
            lines.append(f"Baseline HIC estimate: {baseline.get('hic')}")
            lines.append(f"Mutant HIC estimate: {mutant.get('hic')}")
            lines.append(f"Δ HIC: {delta.get('hic')}")
            lines.append(f"Baseline P(NOT_DEVELOPABLE): {baseline.get('probability')}")
            lines.append(f"Mutant P(NOT_DEVELOPABLE): {mutant.get('probability')}")
            lines.append(f"Δ probability (percentage points): {float(delta.get('probability', 0)) * 100:+.3f} pp")
            lines.append(MUTATION_ML_WARNING)
            lines.append(MUTATION_ML_EXPANDED_LIMITATION)
        lines.extend(["", "Literature Evidence", "-------------------"])
        if not self.literature_evidence:
            lines.append("No literature evidence has been attached to this summary.")
        else:
            for index, paper in enumerate(self.literature_evidence, 1):
                lines.append(f"Paper {index}: {paper.get('title') or 'Untitled'}")
                lines.append(f"  Authors: {', '.join(paper.get('authors', [])) if isinstance(paper.get('authors'), list) else paper.get('authors', '')}")
                lines.append(f"  Journal / Year: {paper.get('journal') or '-'} / {paper.get('year') or '-'}")
                lines.append(f"  PMID: {paper.get('pmid') or '-'}; PMCID: {paper.get('pmcid') or '-'}; DOI: {paper.get('doi') or '-'}")
                lines.append(f"  Source: {paper.get('source') or '-'}; Relevance: {paper.get('relevance') or '-'}")
            lines.append(LITERATURE_LIMITATION)
        lines.extend(["", "Evidence Gaps", "-------------"])
        lines.extend(self.evidence_gaps or ("No evidence gaps recorded.",))
        lines.extend(["", "Scientific Limitations", "-----------------------"])
        lines.extend(self.limitations)
        lines.extend(["", "Provenance", "----------"])
        for key, value in self.provenance.items():
            lines.append(f"{key}: {value}")
        lines.extend(["", "Use these evidence layers to support human review and experimental planning."])
        return "\n".join(lines)


def build_research_summary(state: Any) -> ResearchDecisionSummary:
    """Build a summary from existing state only; no scientific operation is called."""

    sequence = _sequence_section(state)
    ml = _ml_section(_get(state, "ml_estimates", "experimental_ml", "single_ml", default=None))
    mutation = _mutation_section(_get(state, "mutation_analysis", "mutation_comparison", "mutation", default=None))
    mutation_ml = _mutation_ml_section(_get(state, "mutation_ml", default=None))
    literature = tuple(_literature_section(_get(state, "literature_evidence", "selected_literature", "literature", default=None)))
    gaps: List[str] = []
    if ml is None:
        gaps.append("Experimental ML estimates have not been calculated.")
    if not literature:
        gaps.append("No literature evidence has been attached.")
    if mutation is None:
        gaps.append("No mutation hypothesis is included in this summary.")
    elif mutation_ml is None:
        gaps.append("Mutation ML comparison has not been calculated.")
    limitations = (
        RULE_LIMITATION,
        FAMILY_LIMITATION,
        GENERALIZATION_LIMITATION,
        ML_VERIFICATION_LIMITATION,
        MUTATION_EFFECT_LIMITATION,
        LITERATURE_LIMITATION,
    )
    source_provenance = _plain(_get(state, "provenance", default={}))
    if not isinstance(source_provenance, Mapping):
        source_provenance = {}
    provenance: Dict[str, Any] = dict(source_provenance)
    provenance.setdefault("sequence_hashes", sequence.get("sequence_hashes", {}))
    provenance.setdefault("rule_result_id", sequence.get("rule_result_id", ""))
    if ml:
        provenance.setdefault("ml_model_ids", {key: ml.get(key) for key in ("hic_model_id", "developability_model_id") if ml.get(key)})
        provenance.setdefault("ml_benchmark", ml.get("benchmark"))
    if mutation:
        provenance.setdefault("mutation", mutation.get("mutation", ""))
    provenance["literature_identifiers"] = [
        {key: paper.get(key, "") for key in ("evidence_id", "pmid", "pmcid", "doi", "source")}
        for paper in literature
    ]
    created_at = _get(state, "summary_created_at_utc", "created_at_utc", default=None)
    if not created_at:
        created_at = datetime.now(timezone.utc).isoformat()
    provenance["summary_created_at_utc"] = str(created_at)
    return ResearchDecisionSummary(
        sequence_analysis=sequence,
        ml_estimates=ml,
        mutation_analysis=mutation,
        mutation_ml=mutation_ml,
        literature_evidence=literature,
        evidence_gaps=tuple(gaps),
        limitations=tuple(limitations),
        provenance=provenance,
        fingerprint=summary_fingerprint(state),
        created_at_utc=str(created_at),
    )


def render_research_summary(summary: ResearchDecisionSummary) -> str:
    """Render a summary for the Desktop panel or a future safe export."""

    return summary.render_text()


__all__ = [
    "ResearchDecisionSummary",
    "build_research_summary",
    "render_research_summary",
    "summary_fingerprint",
    "MUTATION_ML_WARNING",
    "MUTATION_ML_EXPANDED_LIMITATION",
]
