from __future__ import annotations

from PySide6.QtCore import Signal, QThreadPool
from PySide6.QtWidgets import QCheckBox, QComboBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QDoubleSpinBox, QVBoxLayout, QWidget

from desktop.credentials import CredentialError, CredentialStore
from desktop.errors import normalize_error
from desktop.providers import model_display_name, provider_spec, resolve_model
from desktop.settings import DEFAULTS, RuntimeLLMConfig, config_from_environment, load_settings, save_settings
from desktop.workers import Worker, classify_connection_error, test_connection


class SettingsPage(QWidget):
    config_applied = Signal(object)
    def __init__(self, parent=None):
        super().__init__(parent); self.store = CredentialStore(); self.pool = QThreadPool.globalInstance(); self._config = load_settings(); self._provider_state = {}
        self.provider = QComboBox(); self.provider.addItems(["deepseek", "openai", "openai-compatible", "ollama", "mock"])
        self.base_url = QLineEdit(); self.model = QComboBox(); self.model.setEditable(True); self.api_key = QLineEdit(); self.api_key.setEchoMode(QLineEdit.Password); self.timeout = QDoubleSpinBox(); self.timeout.setRange(1, 300); self.timeout.setValue(30)
        self.secure = QCheckBox("Save API key securely with OS keyring"); self.status = QLabel(); self.show_key = QPushButton("Show"); self.show_key.setCheckable(True); self.show_key.toggled.connect(lambda on: self.api_key.setEchoMode(QLineEdit.Normal if on else QLineEdit.Password))
        self.provider.currentTextChanged.connect(self._switch_provider); self._load()
        form = QFormLayout(); form.addRow("Provider", self.provider); form.addRow("Base URL", self.base_url)
        keyrow = QHBoxLayout(); keyrow.addWidget(self.api_key); keyrow.addWidget(self.show_key); form.addRow("API key", keyrow)
        form.addRow("Model", self.model); form.addRow("Timeout (s)", self.timeout)
        save = QPushButton("Save / Apply"); self.test_button = QPushButton("Test Connection"); clear = QPushButton("Clear Credentials"); save.clicked.connect(self.save); self.test_button.clicked.connect(self.test); clear.clicked.connect(self.clear_credentials)
        buttons = QHBoxLayout(); buttons.addWidget(self.test_button); buttons.addWidget(save); buttons.addWidget(clear); buttons.addStretch()
        layout = QVBoxLayout(self); layout.addLayout(form); layout.addWidget(self.secure); layout.addLayout(buttons); layout.addWidget(self.status); layout.addStretch()

    def _load_provider(self, provider, base_url="", model=""):
        spec = provider_spec(provider); self.base_url.setText(base_url or (spec.default_base_url or "")); self.model.clear()
        self.model.addItems([m.display_name for m in spec.models]); self.model.setCurrentText(model_display_name(provider, model) if model else (spec.models[0].display_name if spec.models else ""))
        self.base_url.setEnabled(provider != "mock"); self.model.setEnabled(provider != "mock"); self.api_key.setEnabled(provider not in {"ollama", "mock"})

    def _load(self):
        provider = self._config.provider if self._config.provider in {"deepseek", "openai", "openai-compatible", "ollama", "mock"} else "mock"
        self.provider.setCurrentText(provider); self._current_provider = provider; self._load_provider(provider, self._config.base_url, self._config.model); self.timeout.setValue(self._config.timeout)
        try: self.api_key.setText(self.store.get(provider))
        except CredentialError: self.api_key.clear()

    def _switch_provider(self, provider):
        previous = getattr(self, "_current_provider", None)
        if previous:
            self._provider_state[previous] = (self.base_url.text(), self.model.currentText())
        self._current_provider = provider; base, model = self._provider_state.get(provider, ("", "")); self._load_provider(provider, base, model); self.api_key.clear()
        try: self.api_key.setText(self.store.get(provider))
        except CredentialError: self.api_key.clear()

    def config(self):
        provider = self.provider.currentText()
        return RuntimeLLMConfig(provider, self.api_key.text().strip(), self.base_url.text().strip(), resolve_model(provider, self.model.currentText()), self.timeout.value())
    def save(self):
        config = self.config()
        try:
            if self.secure.isChecked() and config.api_key: self.store.save_secure(config.provider, config.api_key)
            elif config.api_key: self.store.set_session(config.provider, config.api_key)
            save_settings(config); self._config = config; self.config_applied.emit(config); self.status.setText("已保存并应用（API key 不写入配置文件）")
        except (CredentialError, OSError) as exc: self.status.setText(str(exc))
    def test(self):
        if not self.test_button.isEnabled(): return
        config = self.config(); self.test_button.setEnabled(False); self.status.setText("Testing…")
        worker = Worker(test_connection, config, secrets=[config.api_key]); self._active_worker = worker
        worker.signals.finished.connect(self._test_success); worker.signals.error.connect(self._test_error); self.pool.start(worker)
    def _test_success(self, message):
        self.test_button.setEnabled(True); self.status.setText(message); self._active_worker = None
    def _test_error(self, message):
        self.test_button.setEnabled(True); normalized = normalize_error(message); self.status.setText(f"{normalized.message} {message}"); self._active_worker = None
    def clear_credentials(self):
        try: self.store.delete(self.provider.currentText()); self.api_key.clear(); self.status.setText("已清除当前 provider 凭据")
        except CredentialError as exc: self.status.setText(str(exc))
