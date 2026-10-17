"""Qt integration acceptance; real workers, not a native mouse/Provider test."""

import threading
import time

import pytest
from PySide6.QtCore import QThreadPool, QTimer, Qt
from PySide6.QtTest import QTest

from desktop.main_window import MainWindow
from desktop.settings import RuntimeLLMConfig
from desktop.workers import Worker


def wait_until(app, condition, timeout=5):
    deadline = time.monotonic() + timeout
    while not condition() and time.monotonic() < deadline:
        app.processEvents()
        QTest.qWait(5)
    assert condition(), "Qt acceptance operation did not complete"


@pytest.fixture
def window(qt_application, monkeypatch):
    # Offline tests must not consult a real credential store or run a Provider.
    monkeypatch.setattr("desktop.credentials.CredentialStore.get", lambda *args: "")
    monkeypatch.setattr("desktop.main_window.load_settings", RuntimeLLMConfig)
    monkeypatch.setattr("desktop.widgets.settings_page.load_settings", RuntimeLLMConfig)
    widget = MainWindow()
    widget.resize(1400, 1000)
    widget.show()
    qt_application.processEvents()
    yield widget
    widget.close()
    widget.deleteLater()


@pytest.mark.parametrize("row", [0, 1])
@pytest.mark.parametrize("target", ["single", "VH", "VL"])
def test_duplicate_csv_rows_transfer_the_actual_selected_record(window, qt_application, tmp_path, row, target):
    path = tmp_path / "synthetic_duplicate_ids.csv"
    path.write_text("antibody_id,VH,VL\nDUP,NNST,ACD\nDUP,AAANVSTT,MMM\n", encoding="utf-8")
    batch = window.stack.widget(1)
    window.nav.setCurrentRow(1)
    batch.set_source(path)
    QTest.mouseClick(batch.analyze_button, Qt.LeftButton)
    wait_until(qt_application, lambda: batch._active_worker is None)
    assert len(batch.records) == 2
    assert [record.antibody_id for record in batch.records] == ["DUP", "DUP"]
    assert {(record.vh_sequence, record.vl_sequence) for record in batch.records} == {
        ("NNST", "ACD"), ("AAANVSTT", "MMM"),
    }
    expected = batch.records[row]
    batch.search.setText("DUP")
    batch.table.setCurrentCell(row, 1)
    if target == "single":
        assert batch.open_single_button.isEnabled()
        QTest.mouseClick(batch.open_single_button, Qt.LeftButton)
        assert window.single.sequence.toPlainText() == expected.vh_sequence
        assert window.single.antibody_id.text() == "DUP"
    else:
        batch.mutation_chain.setCurrentText(target)
        assert batch.send_mutation_button.isEnabled()
        QTest.mouseClick(batch.send_mutation_button, Qt.LeftButton)
        target_input = getattr(window.mutation, target.lower() + "_sequence")
        assert target_input.toPlainText() == getattr(expected, target.lower() + "_sequence")
        assert window.mutation.chain.currentText() == target


def test_single_nnst_renders_both_overlapping_sequons_and_summary_version(window, qt_application):
    page = window.single
    page.set_input("SYNTHETIC-NNST", "NNST", analyze=False)
    QTest.mouseClick(page.analyze_button, Qt.LeftButton)
    qt_application.processEvents()
    glyco = [
        (page.table.item(row, 0).text(), page.table.item(row, 1).text())
        for row in range(page.table.rowCount())
        if page.table.item(row, 2).text() == "N-糖基化"
    ]
    assert glyco == [("1-3", "NNS"), ("2-4", "NST")]
    QTest.mouseClick(page.build_summary_button, Qt.LeftButton)
    assert page.research_summary.sequence_analysis["rule_version"] == "overlap_v2"
    assert "NNS@1-3" in page.summary_view.toPlainText()
    assert "NST@2-4" in page.summary_view.toPlainText()


def test_full_window_close_waits_for_active_worker_and_cancels_queued_work(window, qt_application):
    pool = QThreadPool()
    pool.setMaxThreadCount(1)
    window._shutdown_pool = pool
    started, release = threading.Event(), threading.Event()
    completed, queued_calls, heartbeat = [], [], []

    def active_operation():
        started.set()
        release.wait(5)
        return "must not be published after close"

    active = Worker(active_operation)
    active.signals.finished.connect(completed.append)
    queued = Worker(lambda: queued_calls.append(True))
    timer = QTimer(window)
    timer.setInterval(5)
    timer.timeout.connect(lambda: heartbeat.append(True))
    pool.start(active)
    try:
        assert started.wait(1)
        pool.start(queued)
        timer.start()
        window.close()
        assert window.isVisible() and not window.isEnabled()
        wait_until(qt_application, lambda: bool(heartbeat), timeout=1)
        release.set()
        wait_until(qt_application, lambda: not window.isVisible())
        assert completed == queued_calls == []
        assert not window._shutdown_timer.isActive()
    finally:
        release.set()
        assert pool.waitForDone(1000)
