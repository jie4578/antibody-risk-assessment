# tests/conftest.py
# 确保 pytest 能导入项目根目录下的 core / batch_analysis 模块
import os
import sys
import gc
import importlib.util

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(scope="session", autouse=True)
def qt_application():
    """Keep Qt alive until workers and deferred widget destruction finish."""
    if importlib.util.find_spec("PySide6") is None:
        yield None
        return
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QCoreApplication, QEvent, QThreadPool
    from PySide6.QtWidgets import QApplication

    application = QApplication.instance() or QApplication([])
    application.setQuitOnLastWindowClosed(False)
    yield application
    assert QThreadPool.globalInstance().waitForDone(5000), "Qt test worker did not finish"
    application.processEvents()
    gc.collect()
    for widget in application.topLevelWidgets():
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    application.processEvents()
    gc.collect()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


@pytest.fixture(autouse=True)
def drain_qt_deferred_deletes(qt_application):
    yield
    if qt_application is not None:
        from PySide6.QtCore import QCoreApplication, QEvent
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        qt_application.processEvents()
