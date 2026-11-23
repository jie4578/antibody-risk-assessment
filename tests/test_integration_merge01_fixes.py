"""MERGE-01 P1/P2 regressions; synthetic fixtures, no external engines or PDFs."""
from contextlib import contextmanager
import copy
import hashlib
import json

import pytest

from desktop.integrations import IntegrationError, inspect_biolab, inspect_literature
from desktop.integrations import common
from integration_result_fixtures import biolab_fixture, literature_fixture, write_json


@pytest.mark.parametrize("reader", [inspect_biolab, inspect_literature])
def test_selected_pdf_is_rejected_without_opening_it(tmp_path, monkeypatch, reader):
    selected = tmp_path / "NOT_A_MANIFEST.pdf"
    selected.write_bytes(b"SYNTHETIC excluded PDF selection")
    @contextmanager
    def forbidden_open(target):
        pytest.fail("Application opened a PDF selected as a manifest")
        yield  # A context manager must never reach this branch.
    monkeypatch.setattr(common, "_pinned_file", forbidden_open)
    with pytest.raises(IntegrationError, match="UNSUPPORTED_FORMAT"):
        reader(selected)


@pytest.mark.parametrize("role", ["analysis_issues", "validation_issues", "report_data", "curve_fit_result",
                                 "imported_data", "paper_result", "individual_report"])
@pytest.mark.parametrize("extension", [".pdf", ".PDF"])
def test_pdf_rejected_before_any_artifact_handle_or_content_read(tmp_path, monkeypatch, role, extension):
    if role in {"paper_result", "individual_report"}:
        path, manifest = literature_fixture(tmp_path)
        manifest["documents"][0]["result_file" if role == "paper_result" else "individual_report"] = "excluded" + extension
        reader = inspect_literature
    else:
        path, manifest = biolab_fixture(tmp_path, report=role == "report_data")
        manifest["output_files"][0].update(path="excluded" + extension, artifact_type=role)
        reader = inspect_biolab
    raw = tmp_path / ("excluded" + extension)
    # The test setup may write/hash its synthetic sentinel. Only application access
    # after the guards are installed is being measured.
    payload = b"%PDF-1.7\nSYNTHETIC EXCLUDED BY CONTRACT\n"
    raw.write_bytes(payload)
    if reader is inspect_biolab:
        manifest["output_files"][0].update(size_bytes=len(payload), sha256=hashlib.sha256(payload).hexdigest())
    write_json(path, manifest)
    opened = []
    read = []
    native_open, native_read = common._pinned_file, common.ResultDirectory.read

    @contextmanager
    def checked_open(target):
        if target == raw:
            opened.append(str(target))
            pytest.fail("Application opened an excluded PDF handle")
        with native_open(target) as stream:
            yield stream

    def checked_read(self, target, *args, **kwargs):
        if target == raw:
            read.append(str(target))
            pytest.fail("Application consumed/hash-read an excluded PDF")
        return native_read(self, target, *args, **kwargs)

    monkeypatch.setattr(common, "_pinned_file", checked_open)
    monkeypatch.setattr(common.ResultDirectory, "read", checked_read)
    with pytest.raises(IntegrationError, match="UNSUPPORTED_ARTIFACT_FORMAT"):
        reader(path)
    assert opened == read == []


@pytest.mark.parametrize("role,suffix", [("analysis_issues", ".csv"), ("validation_issues", ".docx"),
                                        ("report_data", ".html"), ("unknown_role", ".json")])
def test_role_format_mismatch_rejected_before_open(tmp_path, monkeypatch, role, suffix):
    path, manifest = biolab_fixture(tmp_path)
    forbidden = tmp_path / ("excluded" + suffix)
    manifest["output_files"][0].update(artifact_type=role, path=forbidden.name)
    write_json(path, manifest)
    native = common._pinned_file

    @contextmanager
    def checked(target):
        assert target != forbidden
        with native(target) as stream:
            yield stream

    monkeypatch.setattr(common, "_pinned_file", checked)
    with pytest.raises(IntegrationError, match="UNSUPPORTED_ARTIFACT_FORMAT"):
        inspect_biolab(path)


@pytest.mark.parametrize("source", [None, "", "OTHER.pdf", "C:/UNAUTHORIZED/SYNTHETIC.pdf"])
@pytest.mark.parametrize("verified", [False, True])
def test_missing_or_cross_document_citation_is_rejected(tmp_path, source, verified):
    path, manifest = literature_fixture(tmp_path)
    paper = tmp_path / manifest["documents"][0]["result_file"]
    result = json.loads(paper.read_text(encoding="utf8"))
    fact = result["facts"][0]
    if source is None:
        del fact["source_file"]
    else:
        fact["source_file"] = source
    fact["verified"] = verified
    write_json(paper, result)
    with pytest.raises(IntegrationError, match="CITATION_SOURCE_MISMATCH"):
        inspect_literature(path)


@pytest.mark.parametrize("target,field,value", [
    ("fact", "document_id", "doc_" + "b" * 64), ("fact", "content_sha256", "b" * 64),
    ("fact", "task_id", "local_OTHER"), ("fact", "source_alias", "other/SYNTHETIC.pdf"),
    ("result", "document_id", "doc_" + "b" * 64), ("result", "content_sha256", "b" * 64),
    ("result", "task_id", "local_OTHER"), ("result", "source_alias", "other/SYNTHETIC.pdf"),
    ("result", "file_name", "OTHER.pdf"),
])
def test_citation_and_result_identity_tampering_rejected(tmp_path, target, field, value):
    path, manifest = literature_fixture(tmp_path)
    paper = tmp_path / manifest["documents"][0]["result_file"]
    result = json.loads(paper.read_text(encoding="utf8"))
    (result["facts"][0] if target == "fact" else result)[field] = value
    write_json(paper, result)
    with pytest.raises(IntegrationError, match="INTEGRITY_MISMATCH|CITATION_SOURCE_MISMATCH"):
        inspect_literature(path)


@pytest.mark.parametrize("verified", [False, True])
def test_same_document_citation_preserves_source_chain_and_flag(tmp_path, verified):
    path, manifest = literature_fixture(tmp_path, duplicate=True)
    doc = manifest["documents"][0]
    paper = tmp_path / doc["result_file"]
    result = json.loads(paper.read_text(encoding="utf8"))
    for obj in (result, result["facts"][0]):
        obj.update(document_id=doc["document_id"], content_sha256=doc["content_sha256"],
                   task_id=manifest["task_id"], source_alias=doc["source_alias"])
    result["facts"][0]["verified"] = verified
    write_json(paper, result)
    summary = inspect_literature(path)
    fact = summary.evidence[0]
    assert fact.source_file == doc["display_name"]
    assert fact.source_alias == doc["source_alias"] and fact.batch_id == manifest["task_id"]
    assert fact.document_id == doc["document_id"] and fact.source_content_sha256 == doc["content_sha256"]
    assert fact.upstream_verified is verified
    assert "不代表科学结论真实" in " ".join(summary.limitations)
    assert "PDF_DECLARED_NOT_VERIFIED" in " ".join(summary.declared_sources)
    json.dumps(summary.as_dict(), allow_nan=False)


@pytest.mark.parametrize("same_name", [False, True])
def test_multiple_document_citation_requires_unambiguous_identity(tmp_path, same_name):
    path, manifest = literature_fixture(tmp_path)
    other = copy.deepcopy(manifest["documents"][0])
    other.update(document_id="doc_" + "b" * 64, content_sha256="b" * 64,
                 source_alias="different/SYNTHETIC.pdf", input_ids=["input_OTHER"], result_file="documents/other.json")
    other["display_name"] = "SYNTHETIC.pdf" if same_name else "OTHER.pdf"
    manifest["documents"].append(other)
    item = copy.deepcopy(manifest["inputs"][0])
    item.update(input_id="input_OTHER", document_id=other["document_id"],
                content_sha256=other["content_sha256"], source_alias=other["source_alias"], display_name=other["display_name"])
    manifest["inputs"].append(item)
    other_result = json.loads((tmp_path / "documents/synthetic.json").read_text(encoding="utf8"))
    other_result.update(document_id=other["document_id"], content_sha256=other["content_sha256"], file_name=other["display_name"])
    other_result["facts"][0]["source_file"] = other["display_name"]
    write_json(tmp_path / other["result_file"], other_result)
    manifest.update(input_count=2, document_count=2, completed_count=2)
    status_path = tmp_path / "status.json"
    status = json.loads(status_path.read_text(encoding="utf8"))
    status.update(input_count=2, document_count=2, completed_count=2)
    write_json(status_path, status)
    write_json(path, manifest)
    if same_name:
        # Coherent outer identities cannot disambiguate per-fact filenames.
        with pytest.raises(IntegrationError, match="AMBIGUOUS_CITATION_SOURCE"):
            inspect_literature(path)
    else:
        result = inspect_literature(path)
        assert len(result.evidence) == 2
        assert {e.source_content_sha256 for e in result.evidence} == {"a" * 64, "b" * 64}


def test_input_alias_mismatch_does_not_allow_citation_binding(tmp_path):
    path, manifest = literature_fixture(tmp_path)
    manifest["inputs"][0]["source_alias"] = "different/SYNTHETIC.pdf"
    write_json(path, manifest)
    with pytest.raises(IntegrationError, match="CITATION_SOURCE_MISMATCH"):
        inspect_literature(path)


def install_qc(root, manifest, site, issues):
    if site == "manifest":
        manifest["warnings"] = issues
    else:
        target = root / ("report_data.json" if site == "report" else "analysis_issues.json")
        if site == "report":
            data = json.loads(target.read_text(encoding="utf8"))
            data["qc"]["issues"] = issues
        else:
            data = issues
        write_json(target, data)
        entry = dict(path=target.name, artifact_type="report_data" if site == "report" else "analysis_issues",
                     size_bytes=target.stat().st_size, sha256=hashlib.sha256(target.read_bytes()).hexdigest())
        if site == "report":
            manifest["output_files"][0] = entry
        else:
            manifest["output_files"].append(entry)


@pytest.mark.parametrize("site", ["manifest", "issues", "report"])
@pytest.mark.parametrize("severity", ["BLOCKING", "critical", "Warning", "unknown", "", None, 42])
def test_invalid_qc_severity_is_never_silently_accepted(tmp_path, site, severity):
    path, manifest = biolab_fixture(tmp_path, report=site == "report")
    install_qc(tmp_path, manifest, site, [dict(severity=severity, code="SYNTHETIC", message="Synthetic only")])
    write_json(path, manifest)
    with pytest.raises(IntegrationError):
        inspect_biolab(path)


@pytest.mark.parametrize("site", ["manifest", "issues", "report"])
@pytest.mark.parametrize("severity", ["info", "warning", "error", "blocking"])
def test_legal_qc_severity_retains_message_and_conservative_state(tmp_path, site, severity):
    path, manifest = biolab_fixture(tmp_path, report=site == "report")
    install_qc(tmp_path, manifest, site, [dict(severity=severity, code="SYNTHETIC", message="Original synthetic QC")])
    write_json(path, manifest)
    result = inspect_biolab(path)
    assert f"{severity} / SYNTHETIC: Original synthetic QC" in result.warnings
    assert result.state == ("NEEDS_REVIEW" if severity in {"error", "blocking"} else "COMPLETED_SOURCE_REPORTED")
