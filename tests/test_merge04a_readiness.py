"""Release preparation tests: no training, providers, installers or scientific changes."""
import ast
from dataclasses import replace
import errno
from pathlib import Path
import re
import subprocess
from types import SimpleNamespace

import pytest
import yaml
from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QMessageBox

from desktop.integrations import case_record as storage
from desktop.integrations.adapters import inspect_literature_evidence
from desktop.integrations.case_report import export_report
from integration_result_fixtures import literature_fixture
from test_research_case_persistence import case, window
from tools import build_windows
from tools.check_docx_support import check_docx_support

ROOT = Path(__file__).resolve().parents[1]


def test_docx_resources_and_chinese_roundtrip_are_required():
    result = check_docx_support()
    assert result["status"] == "PASS"
    assert result["chinese_roundtrip"] and result["external_relationships"] == 0
    assert len(result["template_sha256"]) == 64


def test_docx_probe_rejects_missing_template(tmp_path, monkeypatch):
    from tools import check_docx_support as probe
    monkeypatch.setattr(probe.resources, "files", lambda name: tmp_path)
    with pytest.raises(RuntimeError, match="DOCX_DEFAULT_TEMPLATE_MISSING"):
        probe.check_docx_support()


@pytest.mark.parametrize("failure", [errno.EXDEV, errno.ENOSYS, errno.ENOTSUP, "windows-50"])
def test_no_hardlink_filesystem_fails_actionably_without_fallback(tmp_path, monkeypatch, failure):
    target = tmp_path / "new.biocase.json"
    def unsupported(*args):
        error = OSError(None if isinstance(failure, str) else failure, "synthetic unsupported")
        if isinstance(failure, str):
            error.winerror = 50
        raise error
    monkeypatch.setattr(storage.os, "link", unsupported)
    with pytest.raises(OSError, match="OUTPUT_HARDLINK_UNSUPPORTED") as caught:
        storage.atomic_write(target, b"synthetic case")
    assert caught.value.errno == errno.ENOTSUP
    assert "支持硬链接的本地目录" in str(caught.value)
    assert not target.exists() and not list(tmp_path.glob(".biocase-*"))


@pytest.mark.parametrize("failure", [errno.EACCES, errno.ENOSPC])
def test_permission_or_disk_full_is_not_mislabeled(tmp_path, monkeypatch, failure):
    def blocked(*args):
        raise OSError(failure, "synthetic failure")
    monkeypatch.setattr(storage.os, "link", blocked)
    with pytest.raises(OSError) as caught:
        storage.atomic_write(tmp_path/"new", b"synthetic")
    assert caught.value.errno == failure
    assert "HARDLINK_UNSUPPORTED" not in str(caught.value)
    assert not list(tmp_path.glob(".biocase-*"))


def test_unsupported_save_preserves_dirty_and_report_uses_same_error(window, tmp_path, monkeypatch):
    view = window.research_workflow.case
    view.case_id.setText("SYNTHETIC-READINESS")
    view.material.setCurrentIndex(1)
    previous = view.context
    def unsupported(*args):
        raise OSError(errno.ENOTSUP, "synthetic")
    monkeypatch.setattr(storage.os, "link", unsupported)
    assert not view.files._save_to(tmp_path/"case.biocase.json")
    assert view.context is previous and view.files.dirty()
    assert "OUTPUT_HARDLINK_UNSUPPORTED" in view.status.text()
    for kind in ("md", "docx"):
        with pytest.raises(OSError, match="OUTPUT_HARDLINK_UNSUPPORTED"):
            export_report(tmp_path/("report."+kind), kind, previous, "4.1.0rc2")
    assert not list(tmp_path.glob(".biocase-*"))
    assert not list(tmp_path.glob("report.*"))


def test_real_local_hardlink_save_and_no_clobber(tmp_path, case):
    path = tmp_path/"local.biocase.json"
    storage.save_case(path, case, "4.1.0rc2")
    original = path.read_bytes()
    with pytest.raises(FileExistsError):
        storage.atomic_write(path, b"must not replace")
    assert path.read_bytes() == original
    assert storage.load_case(path).case_id == case.case_id


@pytest.mark.parametrize("size", [(1280, 720), (1920, 1080)])
def test_same_prefix_titles_are_complete_safe_and_do_not_move_quote(window, tmp_path, size):
    path, _ = literature_fixture(tmp_path)
    summary = inspect_literature_evidence(path)
    first = summary.documents[0]
    prefix = "SYNTHETIC 同前缀教学标题 " * 7
    titles = (prefix+"ENDING-A <img src='https://example.invalid/a'>",
              prefix+"ENDING-B <b>literal</b>")
    reader = window.research_workflow.literature
    reader.summary = replace(summary, documents=(replace(first,title_candidate=titles[0]),
        replace(first,document_id="SYNTHETIC-SECOND",title_candidate=titles[1],evidence_count=0)))
    reader._populate_documents()
    window.resize(*size)
    window.show()
    window.nav.setCurrentRow(7)
    window.research_workflow.tabs.setCurrentIndex(1)
    from PySide6.QtWidgets import QApplication
    QApplication.processEvents()
    for row, title in enumerate(titles):
        reader.document_table.setCurrentCell(row,0)
        tip = reader.document_table.item(row,0).toolTip()
        assert title in reader.document_details.toPlainText()
        assert "<img src=" not in tip and "&lt;" in tip
    reader.document_table.setCurrentCell(0,0)
    window.content_scroll.verticalScrollBar().setValue(0)
    QApplication.processEvents()
    viewport = window.content_scroll.viewport()
    assert viewport.rect().contains(reader.quote.mapTo(viewport,QPoint(10,36)))
    assert reader.document_details.isHidden()
    reader.reader_tabs.setCurrentWidget(reader.document_details)
    assert titles[0] in reader.document_details.toPlainText()
    assert reader.document_details.isReadOnly()
    reader.clear()
    assert not reader.document_details.toPlainText()


def test_preflight_never_builds_and_reports_missing_dependencies(monkeypatch):
    def absent(name):
        raise build_windows.metadata.PackageNotFoundError(name)
    monkeypatch.setattr(build_windows.metadata,"version",absent)
    monkeypatch.setattr(build_windows.subprocess,"run",lambda *a,**k:pytest.fail("must not build"))
    result = build_windows.preflight()
    assert result["status"] == "NOT_READY"
    assert "DEPENDENCY_VERSION_MISMATCH:python-docx" in result["issues"]
    assert not result["built_executable"] and not result["public_distribution_allowed"]


def test_preflight_supported_interpreter_and_exact_metadata_are_explicit_mocks(monkeypatch):
    import sysconfig
    import tools.check_docx_support as probe
    pins = dict(line.split("==") for line in (ROOT/"packaging/windows/requirements-build.txt").read_text().splitlines()
                if line and not line.startswith("#"))
    native = build_windows.metadata.version
    monkeypatch.setattr(build_windows.metadata,"version",lambda name:pins[name] if name in pins else native(name))
    monkeypatch.setattr(build_windows,"platform",SimpleNamespace(python_version=lambda:"3.14.8",machine=lambda:"AMD64"))
    monkeypatch.setattr(build_windows,"sys",SimpleNamespace(platform="win32",_is_gil_enabled=lambda:True))
    config_var = sysconfig.get_config_var
    monkeypatch.setattr(sysconfig,"get_config_var",lambda name:0 if name=="Py_GIL_DISABLED" else config_var(name))
    monkeypatch.setattr(probe,"check_docx_support",lambda:dict(status="PASS"))
    result = build_windows.preflight()
    assert result["status"] == "PASS" and not result["issues"]
    assert not result["built_executable"]


def test_docx_extra_and_base_dependency_contract():
    text = (ROOT/"pyproject.toml").read_text(encoding="utf8")
    # Only inspect these existing string arrays; no new TOML dependency on Python 3.10.
    array = lambda name: ast.literal_eval(re.search(r"^"+name+r" = (\[.*?\])",text,re.M|re.S)[1])
    assert not any("docx" in x for x in array("dependencies"))
    assert all("python-docx>=1.2.0,<2" in array(extra)
               for extra in ("desktop","all"))
    assert "python-docx" not in (ROOT/"requirements.txt").read_text(encoding="utf-8")
    assert re.search(r'^version = "4.1.0rc2"$',text,re.M)


def test_ci_scientific_scope_and_permissions_are_unchanged():
    old = yaml.load(subprocess.check_output(["git","show",
        "1aeed020546f86aee1f83942220d423175028b6e:.github/workflows/ci.yml"],cwd=ROOT).decode(),
        Loader=yaml.BaseLoader)
    new = yaml.load((ROOT/".github/workflows/ci.yml").read_text(encoding="utf8"),Loader=yaml.BaseLoader)
    assert old["permissions"] == new["permissions"] == {"contents":"read"}
    assert old["on"] == new["on"] and old["env"] == new["env"]
    assert old["jobs"]["test"]["strategy"] == new["jobs"]["test"]["strategy"]
    assert old["jobs"]["desktop-integrity"]["strategy"] == new["jobs"]["desktop-integrity"]["strategy"]
    for name in ("training-opt-in","live-opt-in"):
        assert old["jobs"][name]["if"] == new["jobs"][name]["if"]
    old_runner = old["jobs"]["test"]["steps"][-1]["run"]
    new_runner = new["jobs"]["test"]["steps"][-1]["run"]
    for scope in ("application","integrity","optional-compatibility"):
        def bodies(code):
            return [ast.dump(ast.Module(body=n.body,type_ignores=[]),include_attributes=False)
                    for n in ast.walk(ast.parse(code)) if isinstance(n,ast.If)
                    and ast.unparse(n.test) == "scope == "+repr(scope)]
        assert bodies(old_runner) == bodies(new_runner)
    steps=new["jobs"]["desktop-integrity"]["steps"]
    assert any(s.get("env",{}).get("SAFE_CI_SCOPE")=="docx" and s["run"]==new_runner for s in steps)
    assert "required DOCX regression was skipped" in new_runner
    assert "len(docx_passed) != 6" in new_runner


def test_packaging_keeps_exclusions_and_collects_docx_template():
    spec=(ROOT/"packaging/windows/workbench.spec").read_text()
    tree=ast.parse(spec)
    excluded=next(ast.literal_eval(k.value) for n in ast.walk(tree) if isinstance(n,ast.Call)
                  and isinstance(n.func,ast.Name) and n.func.id=="Analysis"
                  for k in n.keywords if k.arg=="excludes")
    assert "scipy" not in excluded
    assert "lxml.isoschematron" in excluded
    assert {"torch","transformers","sklearn","gradio","ml","validation"} <= set(excluded)
    assert "collect_data_files('docx', includes=['templates/*'])" in spec
    assert "lxml.etree" in spec and "python-docx" in spec


@pytest.mark.parametrize("event", ["skip", "missing_collection", "six_passes"])
def test_actual_docx_gate_rejects_skip_and_incomplete_collection(event):
    workflow = yaml.load((ROOT/".github/workflows/ci.yml").read_text(encoding="utf8"),
                         Loader=yaml.BaseLoader)
    runner = workflow["jobs"]["test"]["steps"][-1]["run"]
    node = next(n for n in ast.parse(runner).body if isinstance(n,ast.ClassDef)
                and n.name=="CollectionBoundary")
    passed = set()
    def blocked(reason):
        raise RuntimeError(reason)
    namespace = dict(pytest=pytest,scope="docx",docx_passed=passed,
                     training_nodes=[],blocked=blocked)
    exec(compile(ast.Module(body=[node],type_ignores=[]),"<actual-ci-gate>","exec"),namespace)
    gate = namespace["CollectionBoundary"]()
    if event=="skip":
        with pytest.raises(RuntimeError,match="required DOCX regression was skipped"):
            gate.pytest_runtest_logreport(SimpleNamespace(skipped=True))
    elif event=="missing_collection":
        item=SimpleNamespace(nodeid="only-one",get_closest_marker=lambda name:None)
        with pytest.raises(RuntimeError,match="six original report cases"):
            gate.pytest_collection_modifyitems([item])
    else:
        for index in range(6):
            gate.pytest_runtest_logreport(SimpleNamespace(skipped=False,when="call",
                                                         passed=True,nodeid=str(index)))
        assert len(passed)==6
