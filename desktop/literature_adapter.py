from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional
from urllib.parse import quote

from agent.literature_relevance import _classify_for_topic, _question_topic
from literature import Evidence, search_literature


@dataclass
class DesktopEvidence:
    evidence_id: str = ""
    title: str = ""
    authors: List[str] = None
    journal: str = ""
    year: Optional[int] = None
    pmid: str = ""
    pmcid: str = ""
    doi: str = ""
    abstract: str = ""
    source: str = ""
    is_open_access: bool = False
    full_text_available: bool = False
    relevance: str = "GENERAL"
    relevance_reason: str = ""
    source_url: str = ""

    def __post_init__(self):
        if self.authors is None:
            self.authors = []


_DOI_RE = re.compile(r"^10\.\d{4,9}/[^\s<>\"']+$", re.IGNORECASE)
_PMID_RE = re.compile(r"^\d{1,9}$")
_PMCID_RE = re.compile(r"^PMC\d+$", re.IGNORECASE)


def source_url(evidence: Evidence) -> str:
    """Return a validated external source URL, preferring DOI then PMID."""
    doi = (evidence.doi or "").strip()
    if doi and _DOI_RE.fullmatch(doi):
        return "https://doi.org/" + quote(doi, safe="/._-()")
    pmid = (evidence.pmid or "").strip()
    if pmid and _PMID_RE.fullmatch(pmid):
        return f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
    pmcid = (evidence.pmcid or "").strip().upper()
    if pmcid and _PMCID_RE.fullmatch(pmcid):
        return f"https://europepmc.org/article/PMC/{pmcid[3:]}"
    return ""


def _to_desktop(evidence: Evidence, query: str) -> DesktopEvidence:
    topic = _question_topic(query)
    relevance, reason = _classify_for_topic(
        topic, (evidence.title or "").lower(), (evidence.abstract or "").lower()
    )
    return DesktopEvidence(
        evidence_id=evidence.evidence_id,
        title=evidence.title,
        authors=list(evidence.authors),
        journal=evidence.journal,
        year=evidence.year,
        pmid=evidence.pmid,
        pmcid=evidence.pmcid,
        doi=evidence.doi,
        abstract=evidence.abstract,
        source=evidence.source,
        is_open_access=evidence.is_open_access,
        full_text_available=evidence.full_text_available,
        relevance=relevance.upper(),
        relevance_reason=reason,
        source_url=source_url(evidence),
    )


def search_desktop_literature(query: str, *, source: str = "auto", max_results: int = 10) -> List[DesktopEvidence]:
    query = str(query or "").strip()
    if not query:
        raise ValueError("Please enter a literature query.")
    source = (source or "auto").lower()
    if source not in {"auto", "europepmc", "pubmed"}:
        raise ValueError("Invalid literature source.")
    max_results = min(max(int(max_results), 1), 50)
    evidence = search_literature(query, max_results=max_results, source=source)
    return [_to_desktop(item, query) for item in evidence]


def visible_results(results: List[DesktopEvidence], filter_name: str = "Direct + General") -> List[DesktopEvidence]:
    if filter_name == "Direct":
        return [item for item in results if item.relevance == "DIRECT"]
    if filter_name == "General":
        return [item for item in results if item.relevance == "GENERAL"]
    if filter_name == "All":
        return list(results)
    return [item for item in results if item.relevance in {"DIRECT", "GENERAL"}]
