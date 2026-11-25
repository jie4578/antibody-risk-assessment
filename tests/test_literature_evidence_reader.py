"""Synthetic v0.4 batch-v2 contracts; no PDF parsing, models or providers."""
import copy
from dataclasses import FrozenInstanceError
import hashlib
import json
import os
from pathlib import Path
import subprocess

import pytest

from desktop.integrations.adapters import inspect_literature_evidence
from desktop.integrations.common import IntegrationError, MAX_JSON, ResultDirectory
from integration_result_fixtures import literature_fixture, write_json


QUOTE = "SYNTHETIC exact raw quotation <b>not instructions</b> & text"


def reader_fixture(root, **kwargs):
    manifest, data = literature_fixture(root, **kwargs)
    path = root / data["documents"][0]["result_file"]
    paper = json.loads(path.read_text(encoding="utf8"))
    paper.update(title_candidate="SYNTHETIC title <script>inert</script>", title_source="pdf_metadata",
                 doi="10.0000/SYNTHETIC", task_id=data["task_id"], source_alias=data["documents"][0]["source_alias"])
    paper["pages"] = [dict(page_number=2, source_file=paper["file_name"], raw_text=QUOTE, text="display text")]
    paper["facts"][0]["evidence_quote_raw"] = QUOTE
    write_json(path, paper)
    return manifest, data, path, paper


def add_second(manifest, data, paper):
    fingerprint = "b" * 64
    doc = copy.deepcopy(data["documents"][0])
    doc.update(document_id="doc_" + fingerprint, content_sha256=fingerprint,
               display_name="SECOND.pdf", source_alias="synthetic/SECOND.pdf", input_ids=["input_2"],
               result_file="documents/second.json", individual_report=None)
    inp = copy.deepcopy(data["inputs"][0])
    inp.update(input_id="input_2", document_id=doc["document_id"], content_sha256=fingerprint,
               display_name=doc["display_name"], source_alias=doc["source_alias"])
    second = copy.deepcopy(paper)
    second.update(document_id=doc["document_id"], content_sha256=fingerprint,
                  file_name=doc["display_name"], source_alias=doc["source_alias"])
    second["pages"][0]["source_file"] = doc["display_name"]
    second["facts"][0]["source_file"] = doc["display_name"]
    data["documents"].append(doc)
    data["inputs"].append(inp)
    for k in ("document_count", "input_count", "completed_count"):
        data[k] += 1
    write_json(manifest, data)
    status = manifest.parent / "status.json"
    old = json.loads(status.read_text(encoding="utf8"))
    write_json(status, {k: data[k] for k in old})
    write_json(manifest.parent / doc["result_file"], second)


def test_bound_document_and_evidence_are_read_only_strict_json(tmp_path):
    manifest, m, path, _ = reader_fixture(tmp_path)
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    summary = inspect_literature_evidence(manifest)
    doc, = summary.documents
    evidence, = summary.evidence
    assert doc.title_candidate == "SYNTHETIC title <script>inert</script>"
    assert doc.title_source == "pdf_metadata" and doc.doi == "10.0000/SYNTHETIC"
    assert doc.physical_pages == (2,) and doc.evidence_count == 1
    assert evidence.document_id == doc.document_id == m["documents"][0]["document_id"]
    assert evidence.batch_id == m["task_id"] and evidence.quote == QUOTE
    assert evidence.location_status == "RESULT_TEXT_MATCH"
    assert evidence.page_start == evidence.page_end == 2
    artifact = next(a for a in summary.artifacts if a.role == "paper_result")
    assert artifact.observed_sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
    assert artifact.hash_status == "OBSERVED_HASH_ONLY"  # v2 has no independent result digest.
    assert "PDF_DECLARED_NOT_VERIFIED" in summary.declared_sources[0]
    json.dumps(summary.as_dict(), allow_nan=False)
    with pytest.raises(FrozenInstanceError):
        doc.document_id = "changed"
    assert before == {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}


def test_two_documents_remain_separate(tmp_path):
    manifest, data, _, paper = reader_fixture(tmp_path)
    add_second(manifest, data, paper)
    summary = inspect_literature_evidence(manifest)
    assert len(summary.documents) == len(summary.evidence) == 2
    assert summary.documents[0].title_candidate == summary.documents[1].title_candidate
    assert len({e.document_id for e in summary.evidence}) == 2


@pytest.mark.parametrize("field,value", [
    ("document_id", "doc_" + "b" * 64), ("content_sha256", "b" * 64),
    ("source_alias", "other/paper.pdf"), ("task_id", "other_batch"), ("file_name", "OTHER.pdf"),
])
def test_result_source_or_hash_mismatch_is_rejected(tmp_path, field, value):
    manifest, _, path, paper = reader_fixture(tmp_path)
    paper[field] = value
    write_json(path, paper)
    with pytest.raises(IntegrationError, match="MISMATCH"):
        inspect_literature_evidence(manifest)


@pytest.mark.parametrize("field,value", [
    ("source_file", None), ("source_file", "SECOND.pdf"), ("document_id", "doc_other"),
    ("task_id", "other"), ("content_sha256", "b" * 64), ("source_alias", "other/paper.pdf"),
])
def test_citation_binding_cannot_be_inferred_or_cross_documents(tmp_path, field, value):
    manifest, _, path, paper = reader_fixture(tmp_path)
    paper["facts"][0][field] = value
    write_json(path, paper)
    with pytest.raises(IntegrationError, match="CITATION_SOURCE_MISMATCH"):
        inspect_literature_evidence(manifest)


@pytest.mark.parametrize("start,end", [(0, 2), (-1, -1), (True, 2), (2, 1), (2, None),
                                        (None, 2), (3, 3), (2, 10**100)])
def test_invalid_or_out_of_inventory_physical_pages(tmp_path, start, end):
    manifest, _, path, paper = reader_fixture(tmp_path)
    paper["facts"][0].update(pdf_page_start=start, pdf_page_end=end)
    write_json(path, paper)
    with pytest.raises(IntegrationError):
        inspect_literature_evidence(manifest)


@pytest.mark.parametrize("case,status", [
    ("no_pages", "INSUFFICIENT_LOCATION"), ("no_match", "LOCATION_NOT_REPRODUCED"),
    ("unverified", "UPSTREAM_UNVERIFIED"), ("no_location", "INSUFFICIENT_LOCATION"),
])
def test_insufficient_evidence_is_never_upgraded(tmp_path, case, status):
    manifest, _, path, paper = reader_fixture(tmp_path)
    if case == "no_pages":
        paper.pop("pages")
    elif case == "no_match":
        paper["pages"][0]["raw_text"] = "SYNTHETIC different raw text"
    elif case == "unverified":
        paper["facts"][0]["verified"] = False
    else:
        paper["facts"][0].update(verified=False, pdf_page_start=None, pdf_page_end=None)
    write_json(path, paper)
    evidence, = inspect_literature_evidence(manifest).evidence
    assert evidence.location_status == status
    assert evidence.upstream_verified is paper["facts"][0]["verified"]


@pytest.mark.parametrize("number", [0, -1, True, "2", 1.5])
def test_bad_inventory_pages(tmp_path, number):
    manifest, _, path, paper = reader_fixture(tmp_path)
    paper["pages"][0]["page_number"] = number
    write_json(path, paper)
    with pytest.raises(IntegrationError, match="INVALID_PAGE"):
        inspect_literature_evidence(manifest)


def test_duplicate_inventory_pages_and_wrong_page_source_rejected(tmp_path):
    manifest, _, path, paper = reader_fixture(tmp_path)
    original = copy.deepcopy(paper)
    paper["pages"].append(copy.deepcopy(paper["pages"][0]))
    write_json(path, paper)
    with pytest.raises(IntegrationError, match="INVALID_PAGE"):
        inspect_literature_evidence(manifest)
    original["pages"][0]["source_file"] = "OTHER.pdf"
    write_json(path, original)
    with pytest.raises(IntegrationError, match="CITATION_SOURCE_MISMATCH"):
        inspect_literature_evidence(manifest)


def test_missing_evidence_and_title_are_not_invented(tmp_path):
    manifest, _, path, paper = reader_fixture(tmp_path)
    for key in ("title_candidate", "title_source", "doi", "facts"):
        paper.pop(key)
    write_json(path, paper)
    result = inspect_literature_evidence(manifest)
    assert result.documents[0].title_candidate is None
    assert result.documents[0].evidence_count == 0 and not result.evidence


def test_missing_completed_result_is_a_failed_import(tmp_path):
    manifest, _, path, _ = reader_fixture(tmp_path)
    path.unlink()
    with pytest.raises(IntegrationError, match="MISSING_RESULT"):
        inspect_literature_evidence(manifest)


@pytest.mark.parametrize("status,expected", [("completed", "COMPLETED_SOURCE_REPORTED"),
    ("completed_with_errors", "PARTIAL"), ("running", "INCOMPLETE"), ("paused", "INCOMPLETE")])
def test_partial_failed_and_paused_batches_do_not_claim_success(tmp_path, status, expected):
    manifest, _, _, _ = reader_fixture(tmp_path, status=status)
    result = inspect_literature_evidence(manifest)
    assert result.state == expected and result.source_state == status
    if status != "completed":
        assert not result.evidence


@pytest.mark.parametrize("value", [1, "2", 3, True, None])
def test_manifest_version_is_exact_integer_two(tmp_path, value):
    manifest, data, _, _ = reader_fixture(tmp_path)
    data["schema_version"] = value
    write_json(manifest, data)
    with pytest.raises(IntegrationError, match="UNSUPPORTED_VERSION"):
        inspect_literature_evidence(manifest)


@pytest.mark.parametrize("location", ["../outside.json", "documents/../../outside.json", "C:/unauthorized.json",
                                      "//server/share/x.json", "documents/synthetic.json:ads", "documents/./x.json"])
def test_unauthorized_result_paths(tmp_path, location):
    manifest, data, _, _ = reader_fixture(tmp_path)
    data["documents"][0]["result_file"] = location
    write_json(manifest, data)
    with pytest.raises(IntegrationError, match="UNSAFE_PATH"):
        inspect_literature_evidence(manifest)


def test_pdf_never_opened_even_inside_authorized_directory(tmp_path, monkeypatch):
    manifest, data, _, _ = reader_fixture(tmp_path)
    pdf = tmp_path / "blocked.pdf"
    pdf.write_bytes(b"SYNTHETIC PDF must remain unread")
    data["documents"][0]["result_file"] = pdf.name
    write_json(manifest, data)
    import desktop.integrations.common as common
    from contextlib import contextmanager
    original = common._pinned_file
    @contextmanager
    def trap(path):
        assert Path(path) != pdf, "PDF must be rejected before opening"
        with original(path) as handle:
            yield handle
    monkeypatch.setattr(common, "_pinned_file", trap)
    with pytest.raises(IntegrationError, match="UNSUPPORTED_ARTIFACT_FORMAT"):
        inspect_literature_evidence(manifest)


@pytest.mark.parametrize("payload,code", [(b"{broken", "INVALID_JSON"), (b'{"x":1,"x":2}', "DUPLICATE_JSON_KEY"),
    (b'{"x":NaN}', "NONFINITE_JSON"), (b" " * (MAX_JSON + 1), "FILE_TOO_LARGE")],
    ids=["malformed", "duplicate_key", "nonfinite", "oversized"])
def test_invalid_or_oversized_json(tmp_path, payload, code):
    manifest = tmp_path / "batch_manifest.json"
    manifest.write_bytes(payload)
    with pytest.raises(IntegrationError, match=code):
        inspect_literature_evidence(manifest)


def test_change_between_result_read_and_snapshot_acceptance_is_rejected(tmp_path, monkeypatch):
    manifest, _, path, paper = reader_fixture(tmp_path)
    native = ResultDirectory.finish
    def changed(self):
        paper["title_candidate"] = "SYNTHETIC changed after initial read"
        write_json(path, paper)
        return native(self)
    monkeypatch.setattr(ResultDirectory, "finish", changed)
    with pytest.raises(IntegrationError, match="SOURCE_CHANGED"):
        inspect_literature_evidence(manifest)


def test_result_symlink_not_followed(tmp_path):
    manifest, _, path, _ = reader_fixture(tmp_path / "batch")
    other = tmp_path / "outside.json"
    path.rename(other)
    try:
        path.symlink_to(other)
    except OSError:
        pytest.skip("Windows environment lacks symlink privilege; actual Linux/privileged Windows validation required")
    with pytest.raises(IntegrationError, match="UNSAFE_LINK"):
        inspect_literature_evidence(manifest)


@pytest.mark.skipif(os.name != "nt", reason="Real Windows NTFS junction test")
def test_literature_parent_junction_does_not_open_external_result(tmp_path, monkeypatch):
    manifest, data, path, _ = reader_fixture(tmp_path / "authorized")
    outside = tmp_path / "outside"
    outside.mkdir()
    path.rename(outside / "result.json")
    before = (outside / "result.json").read_bytes()
    junction = manifest.parent / "junction"
    process = subprocess.run(["cmd", "/c", "mklink", "/J", str(junction), str(outside)], capture_output=True)
    assert process.returncode == 0, process.stderr
    data["documents"][0]["result_file"] = "junction/result.json"
    write_json(manifest, data)
    import desktop.integrations.common as common
    # artifact() opens through the safe reader, whose parent checks reject the link.
    # Observe the actual open calls instead of intercepting its entire traversal.
    original_audit = common.sys.audit
    opened = []
    def observe(event, *args):
        if event == "open":
            opened.append(str(args[0]))
        return original_audit(event, *args)
    monkeypatch.setattr(common.sys, "audit", observe)
    with pytest.raises(IntegrationError, match="UNSAFE_LINK"):
        inspect_literature_evidence(manifest)
    assert not any(p.endswith("result.json") for p in opened)
    assert (outside / "result.json").read_bytes() == before


# MERGE-02B-FIX: preserve legacy degradation while the reader rejects missing deliveries.
@pytest.mark.parametrize("missing,code", [
    ("status.json", "MISSING_STATUS"), ("individual/SYNTHETIC.docx", "MISSING_REPORT"),
])
def test_strict_reader_rejects_missing_delivery_and_legacy_still_degrades(tmp_path, missing, code):
    from desktop.integrations.adapters import inspect_literature
    manifest, _, _, _ = reader_fixture(tmp_path)
    (tmp_path / missing).unlink()
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    with pytest.raises(IntegrationError, match=code) as error:
        inspect_literature_evidence(manifest)
    assert missing in str(error.value)
    legacy = inspect_literature(manifest)
    assert legacy.state == "INCOMPLETE_ARTIFACTS"
    assert len(legacy.evidence) == 1
    assert legacy.evidence[0].location_status == "UPSTREAM_CLAIM_ONLY"
    assert before == {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}


@pytest.mark.parametrize("declaration", ["absent", "null"])
def test_reader_does_not_require_undeclared_optional_report(tmp_path, declaration):
    manifest, data, _, _ = reader_fixture(tmp_path)
    (tmp_path / "individual/SYNTHETIC.docx").unlink()
    if declaration == "absent":
        data["documents"][0].pop("individual_report")
    else:
        data["documents"][0]["individual_report"] = None
    write_json(manifest, data)
    result = inspect_literature_evidence(manifest)
    assert result.state == "COMPLETED_SOURCE_REPORTED"
    assert len(result.documents) == len(result.evidence) == 1
    assert all(a.role != "individual_report" for a in result.artifacts)


@pytest.mark.parametrize("status", ["completed_with_errors", "running", "paused"])
def test_reader_keeps_noncompleted_result_optional(tmp_path, status):
    manifest, _, result, _ = reader_fixture(tmp_path, status=status)
    result.unlink()
    summary = inspect_literature_evidence(manifest)
    assert len(summary.documents) == 1 and not summary.evidence
    assert summary.documents[0].state in {"failed", "pending"}


@pytest.mark.parametrize("field,value", [("task_id", "FOREIGN_BATCH"), ("source_alias", "foreign/OTHER.pdf")])
@pytest.mark.parametrize("shape", ["empty_facts", "empty_both", "absent_both"])
def test_zero_evidence_cannot_bypass_result_identity(tmp_path, field, value, shape):
    manifest, _, path, paper = reader_fixture(tmp_path)
    paper["facts"] = []
    if shape == "empty_both":
        paper["evidence"] = []
    elif shape == "absent_both":
        paper.pop("facts")
    paper[field] = value
    write_json(path, paper)
    with pytest.raises(IntegrationError, match="CITATION_SOURCE_MISMATCH"):
        inspect_literature_evidence(manifest)


@pytest.mark.parametrize("omitted", [(), ("task_id",), ("source_alias",), ("task_id", "source_alias")],
                         ids=["declared", "no_task_id", "no_alias", "neither"])
def test_valid_zero_evidence_preserves_optional_identity_contract(tmp_path, omitted):
    manifest, data, path, paper = reader_fixture(tmp_path)
    paper["facts"] = []
    paper["evidence"] = []
    for field in omitted:
        paper.pop(field)
    write_json(path, paper)
    summary = inspect_literature_evidence(manifest)
    assert summary.state == "COMPLETED_SOURCE_REPORTED"
    assert len(summary.documents) == 1 and not summary.evidence
    document, = summary.documents
    assert document.document_id == data["documents"][0]["document_id"]
    assert document.evidence_count == 0 and document.title_candidate == paper["title_candidate"]
