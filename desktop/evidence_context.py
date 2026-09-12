from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class EvidenceContext:
    title: str = ""
    authors: str = ""
    journal: str = ""
    year: Optional[int] = None
    pmid: str = ""
    pmcid: str = ""
    doi: str = ""
    abstract_or_excerpt: str = ""
    relevance: str = ""
    source: str = ""
    source_url: str = ""
    originating_literature_query: str = ""
    originating_analysis_context_summary: str = ""

    def prompt_block(self) -> str:
        return ("SELECTED LITERATURE EVIDENCE:\n"
                f"Title: {self.title}\nAuthors: {self.authors}\nJournal: {self.journal}\n"
                f"Year: {self.year or ''}\nPMID: {self.pmid}\nPMCID: {self.pmcid}\n"
                f"DOI: {self.doi}\nRelevance: {self.relevance}\nSource: {self.source}\n"
                f"Abstract/excerpt: {self.abstract_or_excerpt}\n\n"
                "This is general external literature evidence. It does not by itself "
                "experimentally validate the current antibody or mutation.")


def from_desktop_evidence(evidence, query: str = "", analysis_summary: str = "", max_abstract_chars: int = 4000) -> EvidenceContext:
    abstract = str(getattr(evidence, "abstract", "") or "")[:max(1, int(max_abstract_chars))]
    return EvidenceContext(
        title=str(getattr(evidence, "title", "") or ""),
        authors=", ".join(getattr(evidence, "authors", []) or []),
        journal=str(getattr(evidence, "journal", "") or ""),
        year=getattr(evidence, "year", None),
        pmid=str(getattr(evidence, "pmid", "") or ""),
        pmcid=str(getattr(evidence, "pmcid", "") or ""),
        doi=str(getattr(evidence, "doi", "") or ""),
        abstract_or_excerpt=abstract,
        relevance=str(getattr(evidence, "relevance", "") or ""),
        source=str(getattr(evidence, "source", "") or ""),
        source_url=str(getattr(evidence, "source_url", "") or ""),
        originating_literature_query=str(query or ""),
        originating_analysis_context_summary=str(analysis_summary or ""),
    )
