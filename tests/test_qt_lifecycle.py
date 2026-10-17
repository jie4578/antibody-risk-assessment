"""Qt test cleanup is explicit, rather than deferred to interpreter shutdown."""
import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import QCoreApplication, QEvent, QObject
from PySide6.QtWidgets import QApplication


def test_qapplication_has_a_session_owner(qt_application):
    assert qt_application is QApplication.instance()
    assert not qt_application.quitOnLastWindowClosed()


def test_deferred_qobject_deletion_finishes_while_application_is_alive(qt_application):
    deleted = []
    obj = QObject()
    obj.destroyed.connect(lambda *_: deleted.append(True))
    obj.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    assert deleted == [True]
    assert QApplication.instance() is qt_application
