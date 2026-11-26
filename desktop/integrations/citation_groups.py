"""Conservative grouping of already validated literature snapshots."""
from dataclasses import dataclass

from .common import Evidence


@dataclass(frozen=True)
class CitationCounts:
    records: int
    groups: int
    unresolved: int


def count_citations(evidence: tuple[Evidence, ...]) -> CitationCounts:
    keys = set()
    unresolved = 0
    for item in evidence:
        if (item.location_status != "RESULT_TEXT_MATCH" or not item.has_raw_quote
                or not item.batch_id or not item.document_id or not item.source_content_sha256
                or not item.quote or type(item.page_start) is not int or type(item.page_end) is not int
                or not 0 < item.page_start <= item.page_end):
            unresolved += 1
            continue
        # This producer supplies no stable character offset. Exact text equality is deliberate.
        keys.add((item.batch_id, item.document_id, item.source_content_sha256,
                  item.page_start, item.page_end, item.quote))
    return CitationCounts(len(evidence), len(keys), unresolved)
