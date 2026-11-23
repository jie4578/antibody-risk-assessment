"""Offscreen, synthetic-only acceptance of the actual new Desktop entry."""
import json
from threading import Event, get_ident
import time

import pytest
from PySide6.QtCore import QThreadPool

from desktop.integrations import inspect_biolab, inspect_literature
from desktop.widgets.research_workflow import ResultImportPanel
from integration_result_fixtures import biolab_fixture, literature_fixture


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    from desktop.settings import RuntimeLLMConfig
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))
    monkeypatch.setattr("desktop.main_window.load_settings", RuntimeLLMConfig)
    monkeypatch.setattr("desktop.widgets.settings_page.load_settings", RuntimeLLMConfig)
    monkeypatch.setattr("desktop.credentials.CredentialStore.get", lambda *a: "")


def pump(qt, predicate):
    deadline = time.monotonic() + 8
    while not predicate() and time.monotonic() < deadline:
        qt.processEvents()
    qt.processEvents()
    assert predicate()


def test_eighth_entry_preserves_all_seven_original_pages(qt_application, tmp_path):
    from desktop.main_window import MainWindow
    window = MainWindow()
    assert [window.nav.item(i).text() for i in range(8)] == ["单条分析", "批量分析", "突变", "文献", "AI 助手", "设置", "蛋白质工程", "科研工作流"]
    assert window.nav.count() == window.stack.count() == 8
    originals = tuple(window.stack.widget(i) for i in range(7))
    assert window.stack.widget(6) is window.protein_engineering
    assert window.research_workflow.biolab.summary is None
    assert window.research_workflow.literature.summary is None
    assert window.protein_engineering.store is None
    assert not list(tmp_path.rglob("*.sqlite3"))
    for i in range(7):
        window.nav.setCurrentRow(i)
        assert window.stack.currentWidget() is originals[i]
    window.nav.setCurrentRow(7)
    assert window.stack.currentWidget() is window.research_workflow
    for index, button in window.research_workflow.entry_buttons.items():
        button.click()
        assert window.stack.currentWidget() is originals[index]
    window.deleteLater()


@pytest.mark.parametrize("kind", ["biolab", "literature"])
def test_actual_choose_import_display_clear(qt_application, tmp_path, monkeypatch, kind):
    path, _ = (biolab_fixture if kind == "biolab" else literature_fixture)(tmp_path / "SYNTHETIC")
    before = {p.relative_to(path.parent):p.read_bytes() for p in path.parent.rglob("*") if p.is_file()}
    panel = ResultImportPanel(kind)
    monkeypatch.setattr("desktop.widgets.research_workflow.QFileDialog.getOpenFileName", lambda *a:(str(path), ""))
    panel.select_button.click()
    pump(qt_application, lambda:not panel._busy)
    assert panel.summary is not None
    assert panel.summary.source_state in {"COMPLETED", "completed"}
    shown = json.loads(panel.details.toPlainText())
    assert shown["manifest_sha256"] == panel.summary.manifest_sha256
    assert shown["limitations"] and shown["artifacts"]
    if kind == "literature":
        assert "完成文档 1，失败文档 0" in panel.status.text()
        assert "<b>&quote</b>" in panel.details.toPlainText()
        assert "原文匹配/定位" in panel.details.toPlainText()
    assert before == {p.relative_to(path.parent):p.read_bytes() for p in path.parent.rglob("*") if p.is_file()}
    panel.clear_button.click()
    assert panel.summary is None and not panel.details.toPlainText() and not panel.path.text()
    panel.deleteLater()


def test_canceled_dialog_preserves_current_snapshot(qt_application, tmp_path, monkeypatch):
    path, _ = biolab_fixture(tmp_path / "SYNTHETIC")
    panel = ResultImportPanel("biolab"); panel.import_manifest(path)
    pump(qt_application, lambda:not panel._busy)
    previous = panel.summary
    monkeypatch.setattr("desktop.widgets.research_workflow.QFileDialog.getOpenFileName", lambda *a:("", ""))
    panel.select_button.click()
    assert panel.summary is previous
    panel.deleteLater()


def test_invalid_import_drops_old_result(qt_application, tmp_path):
    path, _ = biolab_fixture(tmp_path / "valid")
    panel = ResultImportPanel("biolab"); panel.import_manifest(path)
    pump(qt_application, lambda:not panel._busy)
    bad = tmp_path / "run_manifest.json"; bad.write_bytes(b"broken")
    panel.import_manifest(bad); pump(qt_application, lambda:not panel._busy)
    assert panel.summary is None and not panel.details.toPlainText()
    assert "INVALID_JSON" in panel.status.text()
    panel.deleteLater()


@pytest.mark.parametrize("old_first", [False, True])
def test_old_worker_cannot_replace_new_selection(qt_application, tmp_path, old_first):
    a, _ = biolab_fixture(tmp_path / "A")
    b, _ = biolab_fixture(tmp_path / "B", status="FAILED")
    panel = ResultImportPanel("biolab")
    entered, release, returned = Event(), Event(), Event()
    def delayed(path):
        if str(path) == str(a):
            entered.set()
            assert release.wait(8)
            try:
                return inspect_biolab(path)
            finally:
                returned.set()
        return inspect_biolab(path)
    panel.loaders["biolab"] = delayed
    try:
        panel.import_manifest(a); pump(qt_application, entered.is_set)
        panel.import_manifest(b)
        if old_first:
            release.set(); pump(qt_application, returned.is_set)
        pump(qt_application, lambda:not panel._busy)
        assert panel.summary.state == "FAILED" and panel.path.text() == str(b)
        release.set(); pump(qt_application, returned.is_set)
        assert panel.summary.state == "FAILED"
    finally:
        release.set(); QThreadPool.globalInstance().waitForDone(8000)
    panel.deleteLater()


def test_close_suppresses_late_result(qt_application, tmp_path):
    path, _ = literature_fixture(tmp_path / "SYNTHETIC")
    panel = ResultImportPanel("literature")
    entered, release, returned = Event(), Event(), Event()
    def delayed(p):
        entered.set(); assert release.wait(8)
        try:
            return inspect_literature(p)
        finally:
            returned.set()
    panel.loaders["literature"] = delayed
    try:
        panel.import_manifest(path); pump(qt_application, entered.is_set)
        panel.close(); release.set(); pump(qt_application, returned.is_set)
        assert panel.summary is None and not panel._busy and panel._closed
    finally:
        release.set(); QThreadPool.globalInstance().waitForDone(8000)
    panel.deleteLater()


def test_delivery_runs_on_gui_thread(qt_application, tmp_path):
    path, _ = biolab_fixture(tmp_path / "SYNTHETIC")
    panel = ResultImportPanel("biolab")
    gui = get_ident(); threads = []
    native = panel.status.setText
    panel.status.setText = lambda value:(threads.append(get_ident()), native(value))[-1]
    panel.import_manifest(path); pump(qt_application, lambda:not panel._busy)
    assert panel.summary is not None and threads and set(threads) == {gui}
    panel.deleteLater()
