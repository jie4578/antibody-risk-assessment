"""Targeted regression for MERGE-03C Fix-01; original review assertions stay external."""
from dataclasses import replace
from io import BytesIO
import json

import pytest
from PySide6.QtWidgets import QFileDialog, QMessageBox

from desktop.integrations import case_record as storage
from desktop.integrations.case_report import report_sections, markdown_bytes, docx_bytes, plain
from desktop.integrations.adapters import inspect_biolab
from test_research_case_persistence import case, window, pump
from test_desktop_research_workflow import isolated_settings
from integration_result_fixtures import biolab_fixture


def body(context):
    return "\n".join(title+"\n"+"\n".join(lines) for title,lines in report_sections(context,"4.1.0rc2"))


@pytest.mark.parametrize("declared", [
    ["CUSTOM_LIMIT_MUST_SURVIVE"],
    ["合成样例仅用于界面验收。","批次存在尚未量化的稀释误差。"],
    [*storage.LIMITATIONS,"用户补充限制，尚需实验核查。"],
    ["用户记录 "+str(i) for i in range(30)],
],ids=["single","multiple_chinese","defaults_and_custom","maximum_declared_count"])
def test_declared_limits_roundtrip_and_reports(tmp_path,case,declared):
    value=storage.document(case,"4.1.0rc2")
    value["scientific_limitations"]=declared
    loaded=storage.restore(value)
    for number in range(3):
        path=tmp_path/f"roundtrip-{number}.biocase.json"
        storage.save_case(path,loaded,"4.1.0rc2")
        raw=json.loads(path.read_text(encoding="utf8"))
        assert raw["scientific_limitations"]==declared
        loaded=storage.load_case(path)
    text=body(loaded)
    for item in declared:
        assert item in text
    assert all(item in text for item in storage.LIMITATIONS)
    if any(item not in storage.LIMITATIONS for item in declared):
        assert "用户可编辑的研究记录，未经系统独立核验" in text
    md=markdown_bytes(report_sections(loaded,"4.1.0rc2")).decode("utf8")
    for item in declared:
        assert plain(item) in md
    pytest.importorskip("docx")
    from docx import Document
    doc=Document(BytesIO(docx_bytes(report_sections(loaded,"4.1.0rc2"))))
    rendered="\n".join(p.text for p in doc.paragraphs)
    assert all(item in rendered for item in declared)


@pytest.mark.parametrize("declared",[[],["用户删除内置条目后留下的研究记录。"]])
def test_file_edits_cannot_remove_mandatory_ui_or_report_limits(window,case,declared):
    data=storage.document(case,"4.1.0rc2")
    data["scientific_limitations"]=declared
    loaded=storage.restore(data)
    window.research_workflow.case.files._activate(loaded,None)
    history=window.research_workflow.case.files.history.toPlainText()
    exported=body(loaded)
    assert "软件强制科学限制" in history
    assert all(item in history and item in exported for item in storage.LIMITATIONS)
    # User-editable record retains its declared array; application requirements remain independent.
    assert storage.document(loaded,"4.1.0rc2")["scientific_limitations"]==declared
    assert loaded.sources=={} and loaded.association is None


@pytest.mark.parametrize("invalid",[[True],["x"*20001],["x"]*31,"not an array"])
def test_scientific_limits_validation_not_relaxed(case,invalid):
    data=storage.document(case,"4.1.0rc2")
    data["scientific_limitations"]=invalid
    with pytest.raises(ValueError):
        storage.restore(data)


def test_current_history_and_case_declared_limits_are_distinct(tmp_path,case):
    path,_=biolab_fixture(tmp_path/"bio",report=True)
    summary=inspect_biolab(path)
    previous=storage.external_source("biolab",replace(summary,limitations=("HISTORICAL_ONLY",)))
    current=storage.external_source("biolab",replace(summary,limitations=("CURRENT_ONLY",)))
    case.historical_sources={"biolab":previous}
    case.sources={"biolab":current}
    case.association=None
    case.scientific_limitations=("CASE_USER_DECLARATION",)
    text=body(case)
    assert text.index("CURRENT_ONLY") < text.index("历史来源限制") < text.index("HISTORICAL_ONLY")
    assert "CASE_USER_DECLARATION" in text and "未经系统独立核验" in text
    assert case.source_status("biolab")=="来源发生变化"


@pytest.mark.parametrize("field",["case_id","topic","material","notes","findings","recommendations","basis","relationship"])
def test_dirty_tracks_every_editor_and_reversion(window,field):
    view=window.research_workflow.case
    assert not view.files.dirty()
    editor=getattr(view,field)
    if field in ("material","relationship"):
        editor.setCurrentIndex(1)
        assert view.files.dirty()
        editor.setCurrentIndex(0)
    elif field in ("notes","findings","recommendations"):
        editor.setPlainText("仅修改这个字段。")
        assert view.files.dirty()
        editor.clear()
    else:
        editor.setText("Only this field")
        assert view.files.dirty()
        editor.clear()
    assert not view.files.dirty()


@pytest.mark.parametrize("action",["new","open","close"])
@pytest.mark.parametrize("answer",["save","discard","cancel"])
def test_unsaved_action_contract(qt_application,window,tmp_path,monkeypatch,case,action,answer):
    view=window.research_workflow.case
    view.case_id.setText("SYNTHETIC-FIX01")
    view.material.setCurrentIndex(1)
    view.notes.setPlainText("Keep this change unless explicitly discarded.")
    window.show()
    qt_application.processEvents()
    previous=view.context
    destination=tmp_path/"saved.biocase.json"
    other=tmp_path/"other.biocase.json"
    storage.save_case(other,case,"4.1.0rc2")
    answers={"save":QMessageBox.StandardButton.Save,"discard":QMessageBox.StandardButton.Discard,
             "cancel":QMessageBox.StandardButton.Cancel}
    asked=[]
    def question(*args):
        asked.append(True)
        return answers[answer]
    monkeypatch.setattr(QMessageBox,"question",question)
    monkeypatch.setattr(QFileDialog,"getSaveFileName",lambda *args:(str(destination),""))
    monkeypatch.setattr(QFileDialog,"getOpenFileName",lambda *args:(str(other),""))
    if action=="new":
        view.files.new_case()
    elif action=="open":
        view.files.open_case()
    else:
        window.close()
    assert asked
    assert destination.exists()==(answer=="save")
    if answer=="cancel":
        assert view.context is previous and view.context.notes.startswith("Keep this")
        assert window.isVisible()
    elif action=="close":
        assert not window.isVisible()
    else:
        assert view.context is not previous
        assert not view.files.dirty()
    if answer=="save":
        assert storage.load_case(destination).notes.startswith("Keep this")


def test_material_only_save_failure_does_not_continue(window,monkeypatch):
    view=window.research_workflow.case
    view.material.setCurrentIndex(1)
    previous=view.context
    monkeypatch.setattr(QMessageBox,"question",lambda *args:QMessageBox.StandardButton.Save)
    monkeypatch.setattr(QFileDialog,"getSaveFileName",lambda *args:("",""))
    view.files.new_case()
    assert view.context is previous and view.material.currentIndex()==1 and view.files.dirty()


def test_successful_save_and_failed_save_dirty_state(window,tmp_path):
    view=window.research_workflow.case
    view.case_id.setText("SYNTHETIC")
    view.material.setCurrentIndex(1)
    assert view.files._save_to(tmp_path/"saved.biocase.json")
    assert not view.files.dirty()
    view.findings.setPlainText("New finding")
    assert not view.files._save_to(tmp_path/"missing/failed.biocase.json")
    assert view.files.dirty()


def test_activation_is_clean_and_exposes_declared_limits(window,case,tmp_path):
    value=storage.document(case,"4.1.0rc2")
    value["scientific_limitations"].append("Historical declaration <b>plain</b>")
    loaded=storage.restore(value)
    window.research_workflow.case.files._activate(loaded,tmp_path/"selected.biocase.json")
    assert not window.research_workflow.case.files.dirty()
    assert "Historical declaration <b>plain</b>" in window.research_workflow.case.files.history.toPlainText()
    assert not loaded.sources and loaded.association is None


def test_markdown_intraword_underscore_is_literal_but_markup_remains_escaped():
    assert plain("CUSTOM_LIMIT_MUST_SURVIVE")=="CUSTOM_LIMIT_MUST_SURVIVE"
    assert plain("_emphasis_")=="\\_emphasis\\_"
    assert plain("<b>text</b>")=="\\<b\\>text\\</b\\>"
    assert "\\[" in plain("![text](https://example.invalid/image)")
