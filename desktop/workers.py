from __future__ import annotations

import re
from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from desktop.errors import normalize_error


class WorkerSignals(QObject):
    finished = Signal(object)
    error = Signal(str)


class Worker(QRunnable):
    def __init__(self, function, *args, secrets=None, **kwargs):
        super().__init__()
        self.function, self.args, self.kwargs = function, args, kwargs
        self.secrets = [s for s in (secrets or []) if s]
        self.signals = WorkerSignals()

    @Slot()
    def run(self):
        try:
            self.signals.finished.emit(self.function(*self.args, **self.kwargs))
        except Exception as exc:
            self.signals.error.emit(sanitize_error(str(exc), self.secrets))


def sanitize_error(message: str, secrets=None) -> str:
    for secret in secrets or []:
        if secret:
            message = message.replace(secret, "[REDACTED]")
    message = re.sub(r"(?i)(authorization\s*:\s*bearer\s+|bearer\s+)[^\s,;]+", r"\1[REDACTED]", message)
    message = re.sub(r"(?i)(api[_ -]?key\s*[:=]\s*)[^\s,;]+", r"\1[REDACTED]", message)
    return message


def classify_connection_error(message: str) -> str:
    return normalize_error(message).code


def test_connection(config):
    from desktop.settings import build_backend
    if config.provider in {"deepseek", "openai"} and not config.api_key:
        raise RuntimeError("配置错误：请提供 API key")
    backend = build_backend(config)
    if hasattr(backend, "complete"):
        backend.complete("Reply with exactly OK.", system_prompt="Reply with exactly OK.")
    return "连接成功"
