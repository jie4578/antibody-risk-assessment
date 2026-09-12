from __future__ import annotations

from dataclasses import dataclass


_CATEGORY_TERMS = {
    "脱酰胺": "deamidation", "脱酰胺化": "deamidation", "deamidation": "deamidation",
    "异构化": "isomerization", "isomerization": "isomerization",
    "氧化": "oxidation", "oxidation": "oxidation",
    "n-糖基化": "glycosylation", "糖基化": "glycosylation", "glycosylation": "glycosylation",
}
_RESIDUES = {"A": "alanine", "D": "aspartate", "E": "glutamate", "G": "glycine", "N": "asparagine", "Q": "glutamine", "M": "methionine", "S": "serine"}


@dataclass(frozen=True)
class LiteratureContext:
    source: str
    risk_category: str = ""
    motif: str = ""
    position: str = ""
    region: str = ""
    chain: str = "Unspecified"
    mutation: str = ""
    change_type: str = ""
    safe_query: str = ""
    display_summary: str = ""


def _category(category: str) -> str:
    value = str(category or "").strip().lower()
    return _CATEGORY_TERMS.get(value, value)


def build_safe_query(*, category: str, motif: str = "", region: str = "", mutation: str = "", change_type: str = "") -> str:
    terms = ["antibody"]
    category_term = _category(category)
    if category_term:
        terms.append(category_term)
    if motif:
        terms.extend([str(motif).strip().upper(), "motif"])
    if str(region or "").upper().startswith("CDR"):
        terms.append("CDR")
    if mutation:
        terms.extend(["mutation"])
        target = str(mutation).strip().upper()[-1:]
        if target in _RESIDUES:
            terms.append(_RESIDUES[target])
    return " ".join(term for term in terms if term)


def single_risk_context(risk, chain: str = "Unspecified") -> LiteratureContext:
    query = build_safe_query(category=risk.category, motif=risk.motif, region=risk.region)
    summary = f"Risk: {risk.category} | Motif: {risk.motif} | Region: {risk.region} | Position: {risk.position}"
    return LiteratureContext("single", str(risk.category), str(risk.motif), str(risk.position), str(risk.region), str(chain or "Unspecified"), safe_query=query, display_summary=summary)


def mutation_risk_context(mutation: str, risk, change_type: str, chain: str = "Unspecified") -> LiteratureContext:
    query = build_safe_query(category=risk.category, motif=risk.motif, region=risk.region, mutation=mutation, change_type=change_type)
    summary = f"Mutation: {mutation} | Change: {change_type} risk | Risk: {risk.category} | Motif: {risk.motif} | Region: {risk.region}"
    return LiteratureContext("mutation", str(risk.category), str(risk.motif), str(risk.position), str(risk.region), str(chain or "Unspecified"), str(mutation), str(change_type), query, summary)
