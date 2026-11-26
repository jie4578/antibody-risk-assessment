"""Synthetic case persistence, current/history boundaries and report contracts."""
from dataclasses import replace
from io import BytesIO
import json
from pathlib import Path
from threading import Event
import time
from zipfile import ZipFile

import pytest
from PySide6.QtCore import QThreadPool, Qt
from PySide6.QtWidgets import QFileDialog, QMessageBox

from desktop.integrations.case_context import CaseContext, CaseSource
from desktop.integrations import case_record as storage
from desktop.integrations.case_report import export_report
from desktop.integrations.adapters import inspect_biolab, inspect_literature_evidence
from integration_result_fixtures import biolab_fixture, literature_fixture, write_json
from test_desktop_research_workflow import isolated_settings
from test_merge03b_workflow import populate_elisa, update_report


def pump(app, predicate):
    deadline = time.monotonic() + 12
    while not predicate() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.005)
    app.processEvents()
    assert predicate()


@pytest.fixture
def case():
    context = CaseContext(case_id="SYNTHETIC-CASE", material="合成演示", topic="Research demo",
                          notes="Synthetic only", findings="User hypothesis", recommendations="Further tests")
    snapshot = storage.canonical(dict(rule_version="overlap_v2", score=91.0, risk_level="Low Risk",
                                      sequence_length=8, risks=[]))
    context.set_source("sequence", CaseSource("synthetic", "a"*64, "8 aa synthetic", "local analysis", snapshot))
    context.set_source("biolab", CaseSource("synthetic report", "b"*64, "synthetic", "C:/unread/report_manifest.json"))
    context.associate("仅同属研究案例", "No shared molecule or sample.")
    return context


@pytest.fixture
def window(qt_application):
    from desktop.main_window import MainWindow
    win = MainWindow()
    yield win
    assert QThreadPool.globalInstance().waitForDone(12000)
    qt_application.processEvents()
    win.deleteLater()


def populate(app, win, tmp_path):
    flow = win.research_workflow
    view = flow.case
    view.case_id.setText("SYNTHETIC")
    view.material.setCurrentIndex(1)
    win.single.set_input("DEMO", "NNST")
    view.attach_sequence.click()
    path, meta = biolab_fixture(tmp_path/"bio", report=True)
    update_report(path, meta, populate_elisa)
    flow.biolab.import_manifest(path)
    pump(app, lambda: not flow.biolab._busy)
    view.relationship.setCurrentIndex(1)
    view.basis.setText("Synthetic sources share only a case.")
    view.apply_button.click()
    view.findings.setPlainText("USER FINDING")
    view.recommendations.setPlainText("USER RECOMMENDATION")
    return view, path


def test_roundtrip_restores_only_history(tmp_path, case):
    path = tmp_path/"demo.biocase.json"
    saved = storage.save_case(path, case, "4.1.0rc2")
    restored = storage.load_case(path)
    assert not restored.sources and restored.association is None
    assert restored.historical_association.kind == "仅同属研究案例"
    assert restored.historical_sources == case.sources
    assert restored.findings == case.findings and restored.recommendations == case.recommendations
    assert restored.source_status("sequence") == "未重新核验"
    assert saved["created_at"].endswith("+00:00")
    assert "sequence" not in json.loads(case.sources["sequence"].snapshot_json)


@pytest.mark.parametrize("mutation", [
    lambda d: d.update(schema_version=2),
    lambda d: d.update(schema_version="2.0"),
    lambda d: d.pop("case_id"),
    lambda d: d.update(extra="unexpected"),
    lambda d: d.update(notes=[]),
    lambda d: d.update(material=[]),
    lambda d: d.update(created_at="2026-11-26"),
    lambda d: d.update(notes="x"*20001),
    lambda d: d.update(sources={"unknown": {}}),
    lambda d: d["sources"]["sequence"].update(sha256="bad"),
    lambda d: d["sources"]["sequence"].update(snapshot_json='{"unexpected":true}'),
    lambda d: d["association"].update(kind="SYSTEM_VERIFIED"),
])
def test_strict_case_structure(tmp_path, case, mutation):
    data = storage.document(case, "4.1.0rc2")
    mutation(data)
    path = tmp_path/"bad.biocase.json"
    path.write_text(json.dumps(data), encoding="utf8")
    with pytest.raises(ValueError):
        storage.load_case(path)


@pytest.mark.parametrize("raw", [b"{broken", b'{"schema_version":"1.0","schema_version":"2.0"}',
                                   b'{"x":NaN}', b" "*(storage.MAX_CASE_BYTES+1)],
                         ids=["broken", "duplicate", "nonfinite", "oversized"])
def test_bad_bytes(tmp_path, raw):
    path=tmp_path/"bad.biocase.json"
    path.write_bytes(raw)
    with pytest.raises(ValueError):
        storage.load_case(path)


def test_load_never_reads_referenced_paths(tmp_path, case, monkeypatch):
    path=tmp_path/"safe.biocase.json"
    storage.save_case(path, case, "4.1.0rc2")
    from contextlib import contextmanager
    native=storage._pinned_file
    opened=[]
    @contextmanager
    def observed(target):
        opened.append(target)
        with native(target) as stream:
            yield stream
    monkeypatch.setattr(storage, "_pinned_file", observed)
    restored=storage.load_case(path)
    assert opened == [path] and not restored.sources


def test_unconfirmed_overwrite_preserves_old_file(tmp_path, case):
    path=tmp_path/"case.biocase.json"
    storage.save_case(path,case,"4.1.0rc2")
    old=path.read_bytes()
    case.notes="changed"
    with pytest.raises(FileExistsError):
        storage.save_case(path,case,"4.1.0rc2")
    assert path.read_bytes()==old
    storage.save_case(path,case,"4.1.0rc2",overwrite=True)
    assert storage.load_case(path).notes=="changed"


def test_commit_failure_preserves_existing_case(tmp_path, case, monkeypatch):
    path=tmp_path/"old.biocase.json"
    storage.save_case(path,case,"4.1.0rc2")
    original=path.read_bytes()
    class BrokenSave:
        def __init__(self,*args): pass
        def setDirectWriteFallback(self,*args): pass
        def open(self,*args): return True
        def write(self,value): return len(value)
        def commit(self): return False
    monkeypatch.setattr(storage,"QSaveFile",BrokenSave)
    with pytest.raises(OSError,match="OUTPUT_COMMIT_FAILED"):
        storage.save_case(path,case,"4.1.0rc2",overwrite=True)
    assert path.read_bytes()==original and not list(tmp_path.glob(".biocase-*"))


def test_new_file_publish_is_no_clobber(tmp_path,case,monkeypatch):
    path=tmp_path/"selected.biocase.json"
    native=storage.os.link
    def competing_writer(staged,target):
        target.write_bytes(b"Competing user file")
        native(staged,target)
    monkeypatch.setattr(storage.os,"link",competing_writer)
    with pytest.raises(FileExistsError):
        storage.save_case(path,case,"4.1.0rc2")
    assert path.read_bytes()==b"Competing user file"
    assert not list(tmp_path.glob(".biocase-*"))


def test_source_artifact_and_status_revalidation(tmp_path,case):
    saved=storage.document(case,"4.1.0rc2")
    restored=storage.restore(saved)
    original=case.sources["sequence"]
    restored.set_source("sequence",original)
    assert restored.source_status("sequence")=="当前来源与保存记录匹配"
    assert restored.association is None
    restored.set_source("sequence",replace(original,snapshot_json=original.snapshot_json.replace("91.0","90.0")))
    assert restored.source_status("sequence")=="来源发生变化"
    restored.unavailable_sources.add("biolab")
    assert restored.source_status("biolab")=="来源缺失或不可用"


def test_same_manifest_changed_literature_result_is_changed(tmp_path):
    path,m=literature_fixture(tmp_path/"lit")
    old=storage.external_source("literature",inspect_literature_evidence(path))
    context=CaseContext(historical_sources={"literature":old})
    result=path.parent/m["documents"][0]["result_file"]
    data=json.loads(result.read_text())
    data["title_candidate"]="Changed title while manifest bytes stay equal"
    write_json(result,data)
    new=storage.external_source("literature",inspect_literature_evidence(path))
    assert old.sha256==new.sha256 and old.snapshot_json!=new.snapshot_json
    context.set_source("literature",new)
    assert context.source_status("literature")=="来源发生变化"


def test_edited_history_values_never_become_current(tmp_path,case):
    data=storage.document(case,"4.1.0rc2")
    data["sources"]["sequence"]["snapshot_json"]=case.sources["sequence"].snapshot_json.replace("91.0","99.0")
    restored=storage.restore(data)
    assert not restored.sources
    sections=storage_report(restored)
    assert "99.0" not in sections and "未重新核验" in sections


def storage_report(context):
    from desktop.integrations.case_report import report_sections
    return "\n".join(t+"\n"+"\n".join(v) for t,v in report_sections(context,"4.1.0rc2"))


def test_open_error_keeps_current_case(qt_application,window,tmp_path,monkeypatch):
    view,_=populate(qt_application,window,tmp_path)
    old=view.context
    path=tmp_path/"broken.biocase.json"
    path.write_text("{broken")
    monkeypatch.setattr(QFileDialog,"getOpenFileName",lambda *a:(str(path),""))
    assert not view.files.open_case()
    assert view.context is old and view.context.association is not None


@pytest.mark.parametrize("answer", [QMessageBox.StandardButton.Save,QMessageBox.StandardButton.Discard,
                                    QMessageBox.StandardButton.Cancel])
def test_unsaved_new_save_discard_cancel(qt_application,window,tmp_path,monkeypatch,answer):
    view,_=populate(qt_application,window,tmp_path)
    old=view.context
    dest=tmp_path/"saved.biocase.json"
    monkeypatch.setattr(QMessageBox,"question",lambda *a:answer)
    monkeypatch.setattr(QFileDialog,"getSaveFileName",lambda *a:(str(dest),""))
    view.files.new_case()
    if answer==QMessageBox.StandardButton.Cancel:
        assert view.context is old and not dest.exists()
    else:
        assert view.context is not old and not view.context.sources
        assert dest.exists()==(answer==QMessageBox.StandardButton.Save)


def test_unsaved_close_cancel_then_discard(qt_application,window,monkeypatch):
    view=window.research_workflow.case
    view.case_id.setText("SYNTHETIC")
    window.show()
    qt_application.processEvents()
    monkeypatch.setattr(QMessageBox,"question",lambda *a:QMessageBox.StandardButton.Cancel)
    assert not window.close() and window.isVisible()
    monkeypatch.setattr(QMessageBox,"question",lambda *a:QMessageBox.StandardButton.Discard)
    assert window.close()


def test_ui_restore_revalidation_reconfirmation(qt_application,window,tmp_path,monkeypatch):
    view,source=populate(qt_application,window,tmp_path)
    path=tmp_path/"demo.biocase.json"
    assert view.files._save_to(path)
    monkeypatch.setattr(QFileDialog,"getOpenFileName",lambda *a:(str(path),""))
    assert view.files.open_case()
    assert not view.context.sources and view.context.association is None
    assert view.context.historical_association and "未重新核验" in view.files.history.toPlainText()
    window.single.set_input("DEMO","NNST")
    view.attach_sequence.click()
    flow=window.research_workflow
    flow.biolab.import_manifest(source)
    pump(qt_application,lambda:not flow.biolab._busy)
    assert all(view.context.source_status(k)=="当前来源与保存记录匹配" for k in view.context.sources)
    assert view.context.association is None
    view.relationship.setCurrentIndex(1)
    view.basis.setText("Explicit fresh user confirmation.")
    view.apply_button.click()
    assert view.context.association and "用户已重新确认关联" in view.files.history.toPlainText()
    flow.biolab.clear()
    assert view.context.association is None


def test_old_import_cannot_pollute_opened_case(qt_application,window,tmp_path,monkeypatch,case):
    flow=window.research_workflow
    path,_=biolab_fixture(tmp_path/"bio",report=True)
    started,release=Event(),Event()
    loader=flow.biolab.loaders["biolab"]
    def delayed(filename):
        result=loader(filename)
        started.set()
        assert release.wait(10)
        return result
    flow.biolab.loaders["biolab"]=delayed
    flow.biolab.import_manifest(path)
    try:
        pump(qt_application,started.is_set)
        old_token=flow.biolab._token
        doc=tmp_path/"restored.biocase.json"
        storage.save_case(doc,case,"4.1.0rc2")
        monkeypatch.setattr(QFileDialog,"getOpenFileName",lambda *a:(str(doc),""))
        assert flow.case.files.open_case()
    finally:
        release.set()
    assert QThreadPool.globalInstance().waitForDone(12000)
    qt_application.processEvents()
    flow.biolab._received((old_token,loader(path),None))
    assert flow.biolab.summary is None and not flow.case.context.sources


def test_missing_source_failure_has_explicit_status(qt_application,window,tmp_path,case):
    view=window.research_workflow.case
    view.files._activate(storage.restore(storage.document(case,"4.1.0rc2")),None)
    window.research_workflow.biolab.import_manifest(tmp_path/"missing/report_manifest.json")
    pump(qt_application,lambda:not window.research_workflow.biolab._busy)
    assert view.context.source_status("biolab")=="来源缺失或不可用"


def test_markdown_and_docx_text_no_external_relationships(tmp_path,case):
    case.notes="<b>literal text</b> ![image](https://example.invalid/image)"
    md=tmp_path/"report.md"
    export_report(md,"md",case,"4.1.0rc2")
    body=md.read_text(encoding="utf8")
    assert "91.0" in body and "\\<b\\>" in body and "C:/unread" not in body
    assert "未完成方法学验证" in body and "USER" not in body
    pytest.importorskip("docx")
    from docx import Document
    path=tmp_path/"report.docx"
    export_report(path,"docx",case,"4.1.0rc2")
    doc=Document(path)
    text="\n".join(p.text for p in doc.paragraphs)
    assert "91.0" in text and case.notes in text and "C:/unread" not in text
    with ZipFile(path) as archive:
        assert all(b'TargetMode="External"' not in archive.read(n) for n in archive.namelist() if n.endswith(".rels"))


def test_default_no_quotes_or_raw_sequences(qt_application,window,tmp_path):
    view,_=populate(qt_application,window,tmp_path)
    path,_=literature_fixture(tmp_path/"lit")
    flow=window.research_workflow
    flow.literature.import_manifest(path)
    pump(qt_application,lambda:not flow.literature._busy)
    assert view.files.quote_list.count()==1
    assert view.files.quote_list.item(0).checkState()==Qt.CheckState.Unchecked
    data=storage.document(view.context,"4.1.0rc2")
    raw=json.dumps(data,ensure_ascii=False)
    assert "SYNTHETIC location only" not in raw
    assert '"sequence":' not in view.context.sources["sequence"].snapshot_json


def test_export_cancel_failure_keep_case(qt_application,window,tmp_path,monkeypatch):
    view,_=populate(qt_application,window,tmp_path)
    old=view.context
    monkeypatch.setattr(QFileDialog,"getSaveFileName",lambda *a:("",""))
    assert not view.files.export("md")
    monkeypatch.setattr(QFileDialog,"getSaveFileName",lambda *a:(str(tmp_path/"missing/report.md"),""))
    assert not view.files.export("md")
    assert view.context is old and view.context.association

@pytest.mark.parametrize("replacement", [True, "high", [], 10**320])
def test_bad_historical_scientific_field_is_structurally_rejected(case,replacement):
    value=storage.document(case,"4.1.0rc2")
    snapshot=json.loads(value["sources"]["sequence"]["snapshot_json"])
    snapshot["score"]=replacement
    value["sources"]["sequence"]["snapshot_json"]=json.dumps(snapshot)
    with pytest.raises(ValueError,match="CASE_INVALID_NUMBER"):
        storage.restore(value)


def test_bad_historical_document_hash_has_safe_error(tmp_path,case):
    path,_=literature_fixture(tmp_path/"lit")
    source=storage.external_source("literature",inspect_literature_evidence(path))
    case.set_source("literature",source)
    value=storage.document(case,"4.1.0rc2")
    snapshot=json.loads(value["sources"]["literature"]["snapshot_json"])
    snapshot["documents"][0]["source_content_sha256"]=True
    value["sources"]["literature"]["snapshot_json"]=json.dumps(snapshot)
    with pytest.raises(ValueError,match="CASE_INVALID_HASH"):
        storage.restore(value)


def test_deep_json_is_rejected(tmp_path):
    path=tmp_path/"deep.biocase.json"
    path.write_text("["*100+"null"+"]"*100,encoding="utf8")
    with pytest.raises(ValueError,match="COMPLEXITY"):
        storage.load_case(path)


def test_incidental_absolute_paths_redacted_in_both_formats(tmp_path,case):
    case.notes="Research note C:/private/company/data.csv and /private/research/results.json"
    from desktop.integrations.case_report import report_sections,markdown_bytes,docx_bytes
    sections=report_sections(case,"4.1.0rc2")
    text=markdown_bytes(sections).decode()
    assert "company/data.csv" not in text and "research/results.json" not in text
    assert "本地路径已省略" in text
    pytest.importorskip("docx")
    from docx import Document
    doc=Document(BytesIO(docx_bytes(sections)))
    assert all("company/data.csv" not in p.text for p in doc.paragraphs)


def test_docx_missing_dependency_is_explicit_and_md_still_works(tmp_path,case,monkeypatch):
    import builtins
    native=builtins.__import__
    def without_docx(name,*args,**kwargs):
        if name=="docx" or name.startswith("docx."):
            raise ImportError("intentionally absent optional dependency")
        return native(name,*args,**kwargs)
    monkeypatch.setattr(builtins,"__import__",without_docx)
    with pytest.raises(RuntimeError,match="DOCX_DEPENDENCY_UNAVAILABLE"):
        export_report(tmp_path/"unavailable.docx","docx",case,"4.1.0rc2")
    assert not (tmp_path/"unavailable.docx").exists()
    export_report(tmp_path/"available.md","md",case,"4.1.0rc2")
    assert (tmp_path/"available.md").is_file()


def test_overwrite_decline_and_save_failure_keep_dirty_case(qt_application,window,tmp_path,monkeypatch):
    view,_=populate(qt_application,window,tmp_path)
    path=tmp_path/"chosen.biocase.json"
    path.write_bytes(b"Existing user file")
    monkeypatch.setattr(QMessageBox,"question",lambda *a:QMessageBox.StandardButton.No)
    assert not view.files._save_to(path)
    assert path.read_bytes()==b"Existing user file" and view.files.dirty()
    missing=tmp_path/"missing/out.biocase.json"
    assert not view.files._save_to(missing) and view.files.dirty()


def test_open_cancel_and_failed_save_dont_discard(qt_application,window,tmp_path,monkeypatch,case):
    view,_=populate(qt_application,window,tmp_path)
    old=view.context
    path=tmp_path/"other.biocase.json"
    storage.save_case(path,case,"4.1.0rc2")
    monkeypatch.setattr(QFileDialog,"getOpenFileName",lambda *a:(str(path),""))
    monkeypatch.setattr(QMessageBox,"question",lambda *a:QMessageBox.StandardButton.Cancel)
    assert not view.files.open_case() and view.context is old
    monkeypatch.setattr(QMessageBox,"question",lambda *a:QMessageBox.StandardButton.Save)
    monkeypatch.setattr(QFileDialog,"getSaveFileName",lambda *a:("",""))
    assert not view.files.open_case() and view.context is old
