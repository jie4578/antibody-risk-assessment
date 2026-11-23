"""MERGE-01: upstream-shaped synthetic contracts and hostile local-result boundaries."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import subprocess

import pytest

from desktop.integrations import IntegrationError, inspect_biolab, inspect_literature
from desktop.integrations import common
from integration_result_fixtures import HASH, biolab_fixture, literature_fixture, write_json


@pytest.mark.parametrize("report,absolute", [(False, False), (False, True), (True, False)])
def test_real_biolab_path_dialects_and_hashes(tmp_path, report, absolute):
    path, _ = biolab_fixture(tmp_path, report=report, absolute=absolute)
    before = {p.name:p.read_bytes() for p in tmp_path.iterdir()}
    result = inspect_biolab(path)
    assert result.source_state == "COMPLETED" and result.state == "COMPLETED_SOURCE_REPORTED"
    assert result.artifacts[0].hash_status == "CONTENT_HASH_MATCH"
    assert result.manifest_sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
    assert result.contract_revision == "dcc7ac4a9accae4a03ad7857950169e0f2ed640c"
    assert any("curve_validated=false" in x for x in result.limitations)
    assert all("NOT_VERIFIED" in x for x in result.declared_sources)
    assert before == {p.name:p.read_bytes() for p in tmp_path.iterdir()}
    json.dumps(result.as_dict(), allow_nan=False)


@pytest.mark.parametrize("status,expected", [("FAILED", "FAILED"), ("PARTIAL", "PARTIAL"), ("ANALYZING", "INCOMPLETE"), ("NEEDS_CONFIRMATION", "INCOMPLETE")])
def test_biolab_failed_and_incomplete_never_success(tmp_path, status, expected):
    path, _ = biolab_fixture(tmp_path, status)
    assert inspect_biolab(path).state == expected


@pytest.mark.parametrize("kind", ["biolab", "literature"])
@pytest.mark.parametrize("mutation,code", [("version", "UNSUPPORTED_VERSION"), ("missing", "INVALID_STRUCTURE"), ("broken", "INVALID_JSON"), ("duplicate", "DUPLICATE_JSON_KEY"), ("nonfinite", "NONFINITE_JSON")])
def test_invalid_manifest_contracts(tmp_path, kind, mutation, code):
    path, m = (biolab_fixture if kind == "biolab" else literature_fixture)(tmp_path)
    if mutation == "version":
        m["schema_version"] = "9.0" if kind == "biolab" else 3
        write_json(path, m)
    elif mutation == "missing":
        del m["run_id" if kind == "biolab" else "documents"]
        write_json(path, m)
    elif mutation == "broken":
        path.write_bytes(b'{"broken":')
    elif mutation == "duplicate":
        path.write_bytes(b'{"schema_version":2,"schema_version":2}')
    else:
        path.write_bytes(b'{"x": NaN}')
    with pytest.raises(IntegrationError, match=code):
        (inspect_biolab if kind == "biolab" else inspect_literature)(path)


@pytest.mark.parametrize("bad", ["../outside.json", "sub/../../outside.json", "\\\\server\\share\\secret", "C:relative.json", "artifact.json:stream", "NUL", "file. ", "./file.json", "file\n.json"])
def test_dangerous_artifact_paths_rejected(tmp_path, bad):
    path, m = biolab_fixture(tmp_path)
    m["output_files"][0]["path"] = bad
    write_json(path, m)
    with pytest.raises(IntegrationError, match="UNSAFE_PATH"):
        inspect_biolab(path)


def test_outside_absolute_path_never_read(tmp_path, monkeypatch):
    path, m = biolab_fixture(tmp_path / "authorized")
    outside = tmp_path / "private.json"
    outside.write_bytes(b"PRIVATE SYNTHETIC SENTINEL")
    m["output_files"][0]["path"] = str(outside)
    write_json(path, m)
    native = common._pinned_file
    @contextmanager
    def guard(p):
        assert p != outside
        with native(p) as stream:
            yield stream
    monkeypatch.setattr(common, "_pinned_file", guard)
    with pytest.raises(IntegrationError, match="UNSAFE_PATH"):
        inspect_biolab(path)


@pytest.mark.parametrize("target", ["file", "directory", "manifest"])
def test_actual_symlinks_rejected(tmp_path, target):
    root = tmp_path / "authorized"
    path, m = biolab_fixture(root)
    outside = tmp_path / "outside"
    outside.mkdir(); (outside / "secret.json").write_bytes(b"SYNTHETIC")
    link = root / ("linked" if target == "directory" else "linked.json")
    try:
        link.symlink_to(outside if target == "directory" else outside / "secret.json", target_is_directory=target == "directory")
    except OSError:
        pytest.skip("OS does not grant symlink creation; Linux CI exercises O_NOFOLLOW")
    if target == "manifest":
        with pytest.raises(IntegrationError):
            inspect_biolab(link)
    else:
        m["output_files"][0]["path"] = "linked/secret.json" if target == "directory" else "linked.json"
        write_json(path, m)
        with pytest.raises(IntegrationError):
            inspect_biolab(path)


@pytest.mark.skipif(os.name != "nt", reason="Windows junction reparse-point check")
def test_windows_junction_cannot_escape_authorized_directory(tmp_path):
    root = tmp_path / "authorized"
    path, m = biolab_fixture(root)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.json").write_bytes(b"SYNTHETIC sentinel")
    junction = root / "junction"
    created = subprocess.run(["cmd", "/c", "mklink", "/J", str(junction), str(outside)], capture_output=True)
    assert created.returncode == 0, created.stderr
    m["output_files"][0]["path"] = "junction/secret.json"
    write_json(path, m)
    with pytest.raises(IntegrationError, match="UNSAFE_LINK"):
        inspect_biolab(path)


@pytest.mark.parametrize("change", ["hash", "size"])
def test_output_hash_mismatch_fail_closed(tmp_path, change):
    path, m = biolab_fixture(tmp_path)
    m["output_files"][0]["sha256" if change == "hash" else "size_bytes"] = HASH if change == "hash" else 1
    write_json(path, m)
    with pytest.raises(IntegrationError, match="HASH_MISMATCH"):
        inspect_biolab(path)


def test_missing_artifact_is_not_completed(tmp_path):
    path, m = biolab_fixture(tmp_path)
    m["output_files"][0]["path"] = "missing.json"
    write_json(path, m)
    result = inspect_biolab(path)
    assert result.state == "INCOMPLETE_ARTIFACTS" and result.artifacts[0].hash_status == "MISSING"


def test_raw_source_is_inventory_only(tmp_path, monkeypatch):
    path, m = biolab_fixture(tmp_path)
    output = m["output_files"][0]
    output["artifact_type"] = "imported_data"
    write_json(path, m)
    native = common.ResultDirectory.read
    def guarded(self, p, *args, **kwargs):
        assert p.name != "report_data.json"
        return native(self, p, *args, **kwargs)
    monkeypatch.setattr(common.ResultDirectory, "read", guarded)
    result = inspect_biolab(path)
    assert result.artifacts[0].hash_status == "NOT_READ_SOURCE_DATA"
    assert result.artifacts[0].observed_sha256 is None


def test_report_qc_flags_and_upstream_limits_are_preserved(tmp_path):
    path, _ = biolab_fixture(tmp_path, report=True)
    result = inspect_biolab(path)
    assert "Synthetic QC only" in " ".join(result.warnings)
    assert "SYNTHETIC upstream research-only limitation" in result.limitations
    assert ("biolab_copilot", "0.1.0") in result.producer_versions


def test_report_data_identity_cannot_be_substituted_even_after_rehash(tmp_path):
    path, m = biolab_fixture(tmp_path, report=True)
    data_path = tmp_path / "report_data.json"
    data = json.loads(data_path.read_text(encoding="utf8"))
    data["report_id"] = "DIFFERENT"
    write_json(data_path, data)
    m["output_files"][0].update(sha256=hashlib.sha256(data_path.read_bytes()).hexdigest(),size_bytes=data_path.stat().st_size)
    write_json(path, m)
    with pytest.raises(IntegrationError, match="INTEGRITY_MISMATCH"):
        inspect_biolab(path)


def test_separately_recorded_blocking_qc_prevents_success(tmp_path):
    path, m = biolab_fixture(tmp_path)
    issues = tmp_path / "analysis_issues.json"
    write_json(issues, [dict(severity="blocking",code="SYNTHETIC_BLOCK",message="Not estimable")])
    m["output_files"].append(dict(path=issues.name,artifact_type="analysis_issues",size_bytes=issues.stat().st_size,
                                  sha256=hashlib.sha256(issues.read_bytes()).hexdigest()))
    write_json(path,m)
    result = inspect_biolab(path)
    assert result.state == "NEEDS_REVIEW" and "Not estimable" in " ".join(result.warnings)


@pytest.mark.parametrize("field,value", [("curve_validated", True), ("quantification_enabled", True), ("intended_use", "clinical")])
def test_elisa_contract_cannot_be_upgraded(tmp_path, field, value):
    path, m = biolab_fixture(tmp_path)
    m[field] = value
    write_json(path, m)
    with pytest.raises(IntegrationError, match="SCIENTIFIC_CONTRACT_MISMATCH"):
        inspect_biolab(path)


def test_missing_elisa_qualification_is_not_invented(tmp_path):
    path, m = biolab_fixture(tmp_path)
    del m["curve_validated"]
    write_json(path, m)
    with pytest.raises(IntegrationError, match="SCIENTIFIC_CONTRACT_MISMATCH"):
        inspect_biolab(path)


@pytest.mark.parametrize("duplicate", [False, True])
def test_literature_v2_identity_counts_and_evidence(tmp_path, duplicate):
    path, _ = literature_fixture(tmp_path, duplicate=duplicate)
    result = inspect_literature(path)
    assert result.state == "COMPLETED_SOURCE_REPORTED"
    assert dict(result.counts) == dict(input_count=1 + duplicate, document_count=1, duplicate_count=int(duplicate), completed_count=1, failed_count=0, skipped_count=0)
    assert result.evidence[0].upstream_verified is True
    assert result.evidence[0].page_start == result.evidence[0].page_end == 2
    assert "原文匹配/定位" in " ".join(result.limitations)
    assert all(a.hash_status == "OBSERVED_HASH_ONLY" for a in result.artifacts)
    assert "original text not copied" not in json.dumps(result.as_dict())
    assert all("PDF_DECLARED_NOT_VERIFIED" in x for x in result.declared_sources)


def test_multiline_original_quote_is_preserved_as_plain_text(tmp_path):
    path, _ = literature_fixture(tmp_path)
    paper = tmp_path / "documents/synthetic.json"
    value = json.loads(paper.read_text(encoding="utf8"))
    quote = "SYNTHETIC original line\nwrapped on next line\twith a tab"
    value["facts"][0]["evidence_quote_raw"] = quote
    write_json(paper,value)
    result = inspect_literature(path)
    assert result.evidence[0].quote == quote
    json.dumps(result.as_dict(),allow_nan=False)


@pytest.mark.parametrize("status,expected", [("completed_with_errors", "PARTIAL"), ("running", "INCOMPLETE"), ("paused", "INCOMPLETE")])
def test_literature_partial_never_gives_success_or_failed_evidence(tmp_path, status, expected):
    path, _ = literature_fixture(tmp_path, status)
    result = inspect_literature(path)
    assert result.state == expected and not result.evidence


@pytest.mark.parametrize("mutation,code", [("identity", "INTEGRITY_MISMATCH"), ("count", "INCONSISTENT_COUNTS"), ("status", "INCONSISTENT_STATUS"), ("escape", "UNSAFE_PATH"), ("result_error", "INTEGRITY_MISMATCH")])
def test_literature_tampering(tmp_path, mutation, code):
    path, m = literature_fixture(tmp_path)
    if mutation in {"identity", "result_error"}:
        result_path = tmp_path / "documents/synthetic.json"
        r = json.loads(result_path.read_text(encoding="utf8"))
        r["content_sha256" if mutation == "identity" else "errors"] = "b" * 64 if mutation == "identity" else ["SYNTHETIC fault"]
        write_json(result_path, r)
    elif mutation == "count":
        m["completed_count"] = 2; write_json(path, m)
    elif mutation == "status":
        s = json.loads((tmp_path / "status.json").read_text(encoding="utf8")); s["status"] = "running"
        write_json(tmp_path / "status.json", s)
    else:
        m["documents"][0]["individual_report"] = "../outside.docx"; write_json(path, m)
    with pytest.raises(IntegrationError, match=code):
        inspect_literature(path)


def test_large_file_and_malformed_types_are_structured_errors(tmp_path, monkeypatch):
    path, _ = biolab_fixture(tmp_path)
    monkeypatch.setattr(common, "MAX_TOTAL", 20)
    with pytest.raises(IntegrationError, match="FILE_TOO_LARGE"):
        inspect_biolab(path)


def test_per_file_limit(tmp_path):
    path = tmp_path / "run_manifest.json"
    with path.open("wb") as stream:
        stream.truncate(common.MAX_JSON + 1)
    with pytest.raises(IntegrationError, match="FILE_TOO_LARGE"):
        inspect_biolab(path)


def test_json_float_overflow_is_rejected(tmp_path):
    path = tmp_path / "run_manifest.json"; path.write_bytes(b'{"number":1e999}')
    with pytest.raises(IntegrationError, match="NONFINITE_JSON"):
        inspect_biolab(path)


def test_source_change_during_snapshot_fails(tmp_path, monkeypatch):
    path, _ = biolab_fixture(tmp_path)
    native = common.ResultDirectory.finish
    def changed(self):
        path.write_bytes(path.read_bytes() + b" ")
        return native(self)
    monkeypatch.setattr(common.ResultDirectory, "finish", changed)
    with pytest.raises(IntegrationError, match="SOURCE_CHANGED"):
        inspect_biolab(path)


def test_no_selection_reads_nothing():
    with pytest.raises(IntegrationError, match="NO_SELECTION"):
        inspect_biolab(None)


def test_pinned_handle_and_path_identity_agree(tmp_path):
    path, _ = biolab_fixture(tmp_path)
    with common._pinned_file(path) as stream:
        assert common._identity(os.fstat(stream.fileno())) == common._identity(path.lstat())


@pytest.mark.parametrize("field,value", [("status", []), ("output_files", {}), ("input_files", None)])
def test_malformed_biolab_types_fail_safely(tmp_path, field, value):
    path, m = biolab_fixture(tmp_path); m[field] = value; write_json(path, m)
    with pytest.raises(IntegrationError):
        inspect_biolab(path)


def test_unrelated_provider_status_is_not_local_batch_schema(tmp_path):
    write_json(tmp_path / "status.json", {"status":"completed", "provider":"SYNTHETIC"})
    with pytest.raises(IntegrationError, match="UNSUPPORTED_FORMAT"):
        inspect_literature(tmp_path / "status.json")
