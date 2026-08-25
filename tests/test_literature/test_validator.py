# tests/test_literature/test_validator.py
# Citation Validator：合法/非法 PMID、DOI、无引用警告。

from literature.evidence import Evidence
from literature.validator import extract_references, validate_citations


def _evidence(pmid="12345678", doi="10.1000/abc"):
    return Evidence(
        evidence_id=f"e:{pmid}", title="T", pmid=pmid, doi=doi, abstract="A",
        source="europepmc",
    )


def test_extract_references():
    refs = extract_references("研究表明[PMID: 12345678]和PMID：87654321, DOI 10.1000/abc123 相关")
    assert "12345678" in refs["pmids"]
    assert "87654321" in refs["pmids"]
    assert "10.1000/abc123" in refs["dois"]


def test_citation_valid():
    evs = [_evidence()]
    res = validate_citations("研究表明(PMID: 12345678)", evs)
    assert res["valid"] is True
    assert res["invalid_references"] == []


def test_citation_invalid_pmid_not_in_evidence():
    evs = [_evidence(pmid="12345678")]
    res = validate_citations("研究表明[PMID: 99999999]", evs)
    assert res["valid"] is False
    assert {"type": "pmid", "value": "99999999"} in res["invalid_references"]


def test_citation_invalid_doi_not_in_evidence():
    evs = [_evidence(doi="10.1000/abc")]
    res = validate_citations("研究见 DOI 10.9999/fake", evs)
    assert res["valid"] is False
    assert any(r["type"] == "doi" for r in res["invalid_references"])


def test_no_citations_warning_but_valid():
    evs = [_evidence()]
    res = validate_citations("基于检索结果，证据不足。", evs)
    assert res["valid"] is True
    assert any("未包含" in w for w in res["warnings"])


def test_mixed_valid_and_invalid():
    evs = [_evidence(pmid="12345678")]
    res = validate_citations("A (PMID: 12345678), B (PMID: 99999999)", evs)
    assert res["valid"] is False
    assert len(res["invalid_references"]) == 1
