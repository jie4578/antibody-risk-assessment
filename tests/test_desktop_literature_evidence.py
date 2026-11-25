"""Actual Qt reader, atomic import and deterministic stale-worker checks."""
import json
from threading import Event, get_ident
import time

import pytest
from PySide6.QtCore import QThreadPool, Qt

from desktop.integrations.adapters import inspect_literature_evidence
from desktop.widgets.literature_evidence import LiteratureEvidencePanel
from test_literature_evidence_reader import add_second, reader_fixture, QUOTE
from integration_result_fixtures import write_json


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    from desktop.settings import RuntimeLLMConfig
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))
    monkeypatch.setattr("desktop.main_window.load_settings", RuntimeLLMConfig)
    monkeypatch.setattr("desktop.widgets.settings_page.load_settings", RuntimeLLMConfig)
    monkeypatch.setattr("desktop.credentials.CredentialStore.get", lambda *a: "")


def pump(qt, predicate):
    deadline = time.monotonic() + 10
    while not predicate() and time.monotonic() < deadline:
        qt.processEvents()
    qt.processEvents()
    assert predicate()


def import_now(qt, panel, path):
    panel.import_manifest(path)
    pump(qt, lambda: not panel._busy)


def view(panel):
    return (panel.summary, panel.path.text(), panel.details.toPlainText(),
            panel.document_details.toPlainText(), panel.quote.toPlainText(),
            panel.document_table.rowCount(), panel.evidence_table.rowCount())


def test_eighth_page_contains_real_reader_and_original_eight_navigation(qt_application):
    from desktop.main_window import MainWindow
    window = MainWindow()
    assert window.stack.count() == window.nav.count() == 8
    assert [window.nav.item(i).text() for i in range(8)] == [
        "单条分析", "批量分析", "突变", "文献", "AI 助手", "设置", "蛋白质工程", "科研工作流"]
    for i in range(8):
        window.nav.setCurrentRow(i)
        assert window.stack.currentIndex() == i
    assert isinstance(window.research_workflow.literature, LiteratureEvidencePanel)
    assert window.research_workflow.biolab.kind == "biolab"
    assert window.research_workflow.literature.summary is None
    assert not hasattr(window.research_workflow, "elisa")  # No MERGE-02A executor is enabled.
    window.deleteLater()


def test_user_dialog_import_plain_text_reading_and_explicit_clear(qt_application, tmp_path, monkeypatch):
    path, _, _, _ = reader_fixture(tmp_path / "synthetic")
    panel = LiteratureEvidencePanel()
    monkeypatch.setattr("desktop.widgets.literature_evidence.QFileDialog.getOpenFileName", lambda *a: (str(path), ""))
    panel.select_button.click()
    pump(qt_application, lambda: not panel._busy)
    assert panel.document_table.rowCount() == panel.evidence_table.rowCount() == 1
    assert "<script>inert</script>" in panel.document_table.item(0, 0).text()
    assert QUOTE in panel.quote.toPlainText()  # No rich text interpretation.
    assert panel.evidence_table.item(0, 0).text() == "2–2"
    assert "未核对 PDF" in panel.evidence_table.item(0, 1).text()
    assert "不证明科学事实真实" in panel.quote.toPlainText()
    assert "未独立核验" in panel.document_details.toPlainText()
    assert json.loads(panel.details.toPlainText())["manifest_sha256"] == panel.summary.manifest_sha256
    assert panel.status.textFormat() == Qt.PlainText
    panel.clear_button.click()
    assert panel.summary is None and not panel.path.text() and not panel.quote.toPlainText()
    assert panel.document_table.rowCount() == panel.evidence_table.rowCount() == 0
    panel.deleteLater()


@pytest.mark.parametrize("bad_case", ["json", "missing", "hash", "cross_document", "page", "escape", "source", "version"])
def test_failed_import_preserves_entire_accepted_snapshot(qt_application, tmp_path, bad_case):
    good, _, _, _ = reader_fixture(tmp_path / "accepted")
    bad, data, result, paper = reader_fixture(tmp_path / "rejected")
    if bad_case == "json":
        bad.write_bytes(b"{broken")
    elif bad_case == "missing":
        result.unlink()
    elif bad_case == "hash":
        paper["content_sha256"] = "b" * 64
        write_json(result, paper)
    elif bad_case == "cross_document":
        paper["facts"][0]["document_id"] = "other"
        write_json(result, paper)
    elif bad_case == "page":
        paper["facts"][0]["pdf_page_end"] = 999
        write_json(result, paper)
    elif bad_case == "escape":
        data["documents"][0]["result_file"] = "../unauthorized.json"
        write_json(bad, data)
    elif bad_case == "source":
        paper["facts"][0].pop("source_file")
        write_json(result, paper)
    else:
        data["schema_version"] = 1
        write_json(bad, data)
    panel = LiteratureEvidencePanel()
    import_now(qt_application, panel, good)
    before = view(panel)
    assert before[0] is not None
    import_now(qt_application, panel, bad)
    assert view(panel) == before
    assert "拒绝接入" in panel.status.text() and "保持不变" in panel.status.text()
    assert panel.pending_path is None and not panel._busy
    panel.deleteLater()


def test_initial_failure_does_not_create_fake_data(qt_application, tmp_path):
    panel = LiteratureEvidencePanel()
    import_now(qt_application, panel, tmp_path / "batch_manifest.json")
    assert panel.summary is None and panel.document_table.rowCount() == 0
    assert not panel.path.text() and "拒绝接入" in panel.status.text()
    panel.deleteLater()


def test_missing_upstream_evidence_is_visible_and_not_invented(qt_application, tmp_path):
    path, _, result, paper = reader_fixture(tmp_path)
    paper.pop("facts")
    paper.pop("title_candidate")
    write_json(result, paper)
    panel = LiteratureEvidencePanel()
    import_now(qt_application, panel, path)
    assert "缺少标题候选" in panel.document_table.item(0, 0).text()
    assert panel.evidence_table.rowCount() == 0 and "没有可接入的既有证据" in panel.quote.toPlainText()
    panel.deleteLater()


def test_same_title_documents_selected_by_id_from_any_column(qt_application, tmp_path):
    path, data, _, paper = reader_fixture(tmp_path)
    add_second(path, data, paper)
    panel = LiteratureEvidencePanel()
    import_now(qt_application, panel, path)
    panel.document_table.setCurrentCell(1, 2)
    assert "doc_" + "b" * 64 in panel.document_details.toPlainText()
    assert "SECOND.pdf" in panel.quote.toPlainText()
    panel.document_table.setCurrentCell(0, 1)
    assert "doc_" + "a" * 64 in panel.quote.toPlainText()
    panel.deleteLater()


@pytest.mark.parametrize("old_first", [False, True])
def test_old_request_never_overwrites_new_snapshot(qt_application, tmp_path, old_first):
    a, _, _, _ = reader_fixture(tmp_path / "A")
    b, _, _, _ = reader_fixture(tmp_path / "B", status="paused")
    panel = LiteratureEvidencePanel()
    entered_a, entered_b, release_a, release_b = Event(), Event(), Event(), Event()
    returned_a, returned_b = Event(), Event()
    def delayed(path):
        is_a = str(path) == str(a)
        (entered_a if is_a else entered_b).set()
        assert (release_a if is_a else release_b).wait(10)
        try:
            return inspect_literature_evidence(path)
        finally:
            (returned_a if is_a else returned_b).set()
    panel.loaders["literature"] = delayed
    try:
        panel.import_manifest(a)
        pump(qt_application, entered_a.is_set)
        panel.import_manifest(b)
        pump(qt_application, entered_b.is_set)
        if old_first:
            release_a.set()
            pump(qt_application, returned_a.is_set)
            assert panel._busy and panel.summary is None
        release_b.set()
        pump(qt_application, lambda: returned_b.is_set() and not panel._busy)
        assert panel.path.text() == str(b) and panel.summary.source_state == "paused"
        accepted = view(panel)
        release_a.set()
        pump(qt_application, returned_a.is_set)
        assert view(panel) == accepted and not panel._busy
    finally:
        release_a.set(); release_b.set()
        QThreadPool.globalInstance().waitForDone(10000)
    panel.deleteLater()


def test_pending_import_does_not_clear_accepted_data_and_close_suppresses_callback(qt_application, tmp_path):
    a, _, _, _ = reader_fixture(tmp_path / "A")
    b, _, _, _ = reader_fixture(tmp_path / "B")
    panel = LiteratureEvidencePanel()
    import_now(qt_application, panel, a)
    before = view(panel)
    entered, release, returned = Event(), Event(), Event()
    def delayed(path):
        entered.set()
        assert release.wait(10)
        try:
            return inspect_literature_evidence(path)
        finally:
            returned.set()
    panel.loaders["literature"] = delayed
    try:
        panel.import_manifest(b)
        pump(qt_application, entered.is_set)
        assert view(panel) == before and panel.pending_path == str(b)
        panel.close()
        release.set()
        pump(qt_application, returned.is_set)
        assert panel.summary is None and panel._closed and not panel._busy
    finally:
        release.set(); QThreadPool.globalInstance().waitForDone(10000)
    panel.deleteLater()


def test_dialog_cancel_preserves_snapshot(qt_application, tmp_path, monkeypatch):
    path, _, _, _ = reader_fixture(tmp_path)
    panel = LiteratureEvidencePanel()
    import_now(qt_application, panel, path)
    before = view(panel)
    monkeypatch.setattr("desktop.widgets.literature_evidence.QFileDialog.getOpenFileName", lambda *a: ("", ""))
    panel.select_button.click()
    assert view(panel) == before and not panel._busy
    panel.deleteLater()


def test_worker_error_isolated_and_all_ui_updates_on_gui_thread(qt_application, tmp_path):
    path, _, _, _ = reader_fixture(tmp_path)
    panel = LiteratureEvidencePanel()
    gui = get_ident()
    calls = []
    original = panel.status.setText
    panel.status.setText = lambda value: (calls.append(get_ident()), original(value))[-1]
    import_now(qt_application, panel, path)
    before = view(panel)
    def failing(path):
        raise RuntimeError("Synthetic failure details must not reach UI")
    panel.loaders["literature"] = failing
    import_now(qt_application, panel, path)
    assert view(panel) == before and "Synthetic failure details" not in panel.status.text()
    assert calls and set(calls) == {gui}
    panel.deleteLater()


@pytest.mark.parametrize("missing,code", [
    ("status.json", "MISSING_STATUS"), ("individual/SYNTHETIC.docx", "MISSING_REPORT"),
])
def test_missing_delivery_preserves_selected_document_and_full_snapshot(qt_application, tmp_path, missing, code):
    accepted, data, _, paper = reader_fixture(tmp_path / "accepted")
    add_second(accepted, data, paper)
    rejected, _, _, _ = reader_fixture(tmp_path / "incomplete")
    (rejected.parent / missing).unlink()
    panel = LiteratureEvidencePanel()
    import_now(qt_application, panel, accepted)
    panel.document_table.setCurrentCell(1, 2)
    panel.evidence_table.setCurrentCell(0, 3)
    before = (view(panel), panel.document_table.currentRow(), panel.document_table.currentColumn(),
              panel.evidence_table.currentRow(), panel.evidence_table.currentColumn(), panel._visible_evidence)
    assert panel.summary is not None and "SECOND.pdf" in panel.quote.toPlainText()
    import_now(qt_application, panel, rejected)
    after = (view(panel), panel.document_table.currentRow(), panel.document_table.currentColumn(),
             panel.evidence_table.currentRow(), panel.evidence_table.currentColumn(), panel._visible_evidence)
    assert after == before
    assert "拒绝接入" in panel.status.text() and code in panel.status.text() and missing in panel.status.text()
    assert panel.pending_path is None and not panel._busy
    panel.deleteLater()


@pytest.mark.parametrize("missing", ["status.json", "individual/SYNTHETIC.docx"])
def test_first_incomplete_import_keeps_unimported_state(qt_application, tmp_path, missing):
    manifest, _, _, _ = reader_fixture(tmp_path)
    (tmp_path / missing).unlink()
    panel = LiteratureEvidencePanel()
    before = view(panel)
    import_now(qt_application, panel, manifest)
    assert view(panel) == before
    assert panel.summary is None and not panel.path.text()
    assert panel.document_table.rowCount() == panel.evidence_table.rowCount() == 0
    assert missing in panel.status.text() and "拒绝接入" in panel.status.text()
    panel.deleteLater()


@pytest.mark.parametrize("field,value", [("task_id", "FOREIGN_BATCH"), ("source_alias", "foreign/OTHER.pdf")])
def test_zero_evidence_identity_failure_preserves_previous_import(qt_application, tmp_path, field, value):
    accepted, _, _, _ = reader_fixture(tmp_path / "accepted")
    rejected, _, result, paper = reader_fixture(tmp_path / "wrong_identity")
    paper["facts"] = []
    paper[field] = value
    write_json(result, paper)
    panel = LiteratureEvidencePanel()
    import_now(qt_application, panel, accepted)
    before = view(panel)
    assert panel.summary is not None
    import_now(qt_application, panel, rejected)
    assert view(panel) == before and "CITATION_SOURCE_MISMATCH" in panel.status.text()
    panel.deleteLater()


def test_valid_zero_evidence_and_undeclared_report_replaces_old_snapshot(qt_application, tmp_path):
    accepted, _, _, _ = reader_fixture(tmp_path / "accepted")
    empty, data, result, paper = reader_fixture(tmp_path / "empty")
    (empty.parent / data["documents"][0].pop("individual_report")).unlink()
    paper["facts"] = []
    paper.pop("task_id")
    paper.pop("source_alias")
    write_json(empty, data)
    write_json(result, paper)
    panel = LiteratureEvidencePanel()
    import_now(qt_application, panel, accepted)
    assert panel.evidence_table.rowCount() == 1
    import_now(qt_application, panel, empty)
    assert panel.path.text() == str(empty) and panel.summary.state == "COMPLETED_SOURCE_REPORTED"
    assert panel.document_table.rowCount() == 1 and panel.evidence_table.rowCount() == 0
    assert "没有可接入的既有证据" in panel.quote.toPlainText()
    assert "已接入批次" in panel.status.text()
    panel.deleteLater()
