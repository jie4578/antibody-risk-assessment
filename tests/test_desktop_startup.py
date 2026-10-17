"""Isolate Qt/application startup from pytest's own Qt process and credentials."""

import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.parametrize("mode", ["qt_only", "project"])
def test_isolated_startup_event_loop_and_clean_exit(mode):
    code = r'''
import faulthandler
import json
import sys
from contextlib import ExitStack
from unittest.mock import patch
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QWidget

assert faulthandler.is_enabled()
app = QApplication([])
mode = sys.argv[1]
with ExitStack() as patches:
    if mode == "project":
        from desktop.main_window import MainWindow
        from desktop.settings import RuntimeLLMConfig
        patches.enter_context(patch("desktop.credentials.CredentialStore.get", return_value=""))
        patches.enter_context(patch("desktop.main_window.load_settings", RuntimeLLMConfig))
        patches.enter_context(patch("desktop.widgets.settings_page.load_settings", RuntimeLLMConfig))
        window = MainWindow()
    else:
        window = QWidget()
    window.setWindowTitle("Antibody acceptance - isolated startup")
    ticks = []
    heartbeat = QTimer()
    heartbeat.setInterval(10)
    heartbeat.timeout.connect(lambda: ticks.append(True))
    window.show()
    heartbeat.start()
    QTimer.singleShot(200, window.close)
    QTimer.singleShot(5000, lambda: app.exit(91))
    result = app.exec()
    print(json.dumps({"mode": mode, "result": result, "heartbeat": bool(ticks),
                      "closed": not window.isVisible(), "fault_handler": faulthandler.is_enabled()}))
    assert result == 0 and ticks and not window.isVisible()
'''
    environment = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    environment.setdefault("QT_QPA_PLATFORM", "offscreen")
    result = subprocess.run(
        [sys.executable, "-X", "faulthandler", "-c", code, mode],
        cwd=Path(__file__).resolve().parents[1], env=environment,
        capture_output=True, text=True, timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert '"heartbeat": true' in result.stdout
    assert '"closed": true' in result.stdout
    assert '"fault_handler": true' in result.stdout
    assert "Windows fatal exception" not in result.stderr, result.stderr
    assert "Traceback" not in result.stderr, result.stderr
    print(result.stdout.strip())
