import os
import threading
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import QThreadPool, QTimer
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QApplication, QMainWindow
from desktop.workers import Worker
from desktop.main_window import MainWindow
from desktop.widgets.literature import LiteraturePage
from desktop.widgets.single_analysis import SingleAnalysisPage
from desktop.widgets.batch_analysis import BatchAnalysisPage
from desktop.literature_adapter import DesktopEvidence
from desktop.literature_context import LiteratureContext
from desktop.batch_adapter import BatchRecord, BatchResult
from core import analyze_sequence


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize("column", range(7))
def test_literature_selection_from_every_column(app, column):
    page = LiteraturePage()
    paper = DesktopEvidence(title="Synthetic paper", year=2024)
    page._done([paper]); page.results_table.setCurrentCell(0, column)
    assert page._selected is paper
    assert page.title.text() == paper.title
    page.deleteLater()


@pytest.mark.parametrize("change", ["results", "query", "filter", "context", "clear"])
def test_literature_changes_clear_evidence_and_notify_summary(app, change):
    page = LiteraturePage(); notifications = []
    page.set_summary_changed_callback(lambda: notifications.append(True))
    page._done([DesktopEvidence(title="Old")]); page.results_table.setCurrentCell(0, 0)
    notifications.clear()
    if change == "results": page._done([DesktopEvidence(title="New")])
    elif change == "query": page.query.setText("new query")
    elif change == "filter": page.filter.setCurrentText("全部")
    elif change == "context": page.load_context(LiteratureContext("single", safe_query="new query"))
    else: page.clear_context()
    assert page._selected is None
    assert page.title.text() == ""
    assert not page.send_evidence_button.isEnabled()
    assert notifications
    page.deleteLater()


def test_literature_discards_old_search_after_context_change(app):
    page = LiteraturePage(); started = []
    page.pool = type("Pool", (), {"start": lambda self, w: started.append(w)})()
    page.query.setText("old query"); page.search()
    page.load_context(LiteratureContext("mutation", safe_query="new query"))
    started[0].signals.finished.emit([DesktopEvidence(title="Old response")])
    assert page._results == [] and page._selected is None
    assert page.search_button.isEnabled()
    page.deleteLater()


def test_single_scope_and_identity_staleness_are_explicit(app):
    page = SingleAnalysisPage(); page.set_input("A", "NGNST")
    page.vl_sequence.setPlainText("MMMM"); page.analyze()
    summary = page.build_research_summary()
    assert "第一个序列输入框" in page.rule_scope_notice.text()
    assert "固定序列位置" in page.rule_scope_notice.text()
    assert "VL partner is not rule-scanned" in summary.sequence_analysis["chain_context"]
    assert summary.sequence_analysis["rule_version"] == "overlap_v2"
    page.antibody_id.setText("B")
    assert page.research_summary.is_stale
    page.deleteLater()


def test_batch_deamidation_detail_count_uses_core_category(app):
    page = BatchAnalysisPage()
    result = analyze_sequence("NG", 31, 35, 50, 65, 99, 110)
    row = BatchRecord("A", status="SUCCESS", risks=[("VH", r) for r in result.risks])
    page._done(BatchResult([row], "synthetic")); page.table.setCurrentCell(0, 0)
    assert "脱酰胺化: 1" in page.detail.text()
    page.deleteLater()


def test_cancelled_worker_does_not_start_or_publish(app):
    calls, output = [], []
    queued = Worker(lambda: calls.append(True))
    queued.signals.finished.connect(output.append)
    queued.cancel(); queued.run()
    assert calls == output == []
    running = Worker(lambda: (running.cancel(), 42)[1])
    running.signals.finished.connect(output.append); running.run()
    assert output == []


def test_cancelled_worker_error_is_not_published(app):
    errors = []
    def operation():
        worker.cancel()
        raise RuntimeError("synthetic error")
    worker = Worker(operation); worker.signals.error.connect(errors.append); worker.run()
    assert errors == []


def test_shutdown_waits_without_blocking_and_accepts_after_completion(app, monkeypatch):
    window = MainWindow.__new__(MainWindow); QMainWindow.__init__(window)
    class Pool:
        active = 1
        cleared = False
        def clear(self): self.cleared = True
        def activeThreadCount(self): return self.active
    pool = Pool(); window._shutdown_pool = pool
    window._shutdown_requested = False; window._shutdown_timer = QTimer(window)
    cancelled = []; monkeypatch.setattr(Worker, "cancel_all", lambda: cancelled.append(True))
    event = QCloseEvent(); window.closeEvent(event)
    assert not event.isAccepted() and pool.cleared and cancelled
    assert not window.isEnabled() and window._shutdown_timer.isActive()
    pool.active = 0
    event = QCloseEvent(); window.closeEvent(event)
    assert event.isAccepted() and not window._shutdown_timer.isActive()
    window.deleteLater()


def test_shutdown_completes_after_a_real_background_worker(app):
    window = MainWindow.__new__(MainWindow); QMainWindow.__init__(window)
    pool = QThreadPool()
    window._shutdown_pool = pool; window._shutdown_requested = False
    window._shutdown_timer = QTimer(window); window._shutdown_timer.setInterval(10)
    window._shutdown_timer.timeout.connect(window._check_shutdown)
    started, release, output = threading.Event(), threading.Event(), []
    def operation():
        started.set()
        release.wait(2)
        return "cancelled result"
    worker = Worker(operation); worker.signals.finished.connect(output.append)
    window.show(); pool.start(worker)
    try:
        assert started.wait(1)
        window.close()
        assert window.isVisible() and not window.isEnabled()
        release.set()
        deadline = time.monotonic() + 2
        while window.isVisible() and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.005)
        assert not window.isVisible()
        assert output == []
    finally:
        release.set(); pool.waitForDone(1000); window.deleteLater()
