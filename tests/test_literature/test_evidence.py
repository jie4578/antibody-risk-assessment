# tests/test_literature/test_evidence.py
# Evidence 模型：schema / 序列化 / 有效性 / 去重键。

from literature.evidence import Evidence


def _base(**kw):
    data = {
        "evidence_id": "europepmc:123",
        "title": "Deamidation of antibodies",
        "pmid": "12345678",
        "abstract": "Some abstract.",
    }
    data.update(kw)
    return data


def test_evidence_valid_title_abstract():
    assert Evidence.from_dict(_base()).is_valid()


def test_evidence_valid_title_pmid_without_abstract():
    ev = Evidence.from_dict(_base(abstract=""))
    assert ev.is_valid()


def test_evidence_invalid_title_only():
    ev = Evidence.from_dict(_base(title="", abstract=""))
    assert not ev.is_valid()


def test_evidence_invalid_empty():
    assert not Evidence().is_valid()


def test_evidence_roundtrip_dict():
    ev = Evidence.from_dict(_base(authors=["Zhang Y", "Li W"], doi="10.1/x", year=2022))
    d = ev.to_dict()
    ev2 = Evidence.from_dict(d)
    assert ev2.to_dict() == d
    assert ev2.authors == ["Zhang Y", "Li W"]


def test_evidence_missing_fields_are_empty_not_none_in_serialization():
    ev = Evidence.from_dict(_base())  # 缺 journal/pmcid/doi → 空串
    d = ev.to_dict()
    assert d["journal"] == ""
    assert d["pmcid"] == ""
    assert d["doi"] == ""


def test_evidence_citation_key_prefers_pmid():
    ev = Evidence.from_dict(_base(pmid="11111111", pmcid="PMC222", doi="10.1/z"))
    assert ev.citation_key() == "11111111"


def test_evidence_citation_key_falls_back():
    ev = Evidence.from_dict(_base(pmid="", pmcid="", doi="10.1/z"))
    assert ev.citation_key() == "10.1/z"
