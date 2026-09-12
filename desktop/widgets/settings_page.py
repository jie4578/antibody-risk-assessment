from __future__ import annotations

from PySide6.QtCore import Signal, QThreadPool
from PySide6.QtWidgets import QCheckBox, QComboBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QDoubleSpinBox, QVBoxLayout, QWidget

from desktop.credentials import CredentialError, CredentialStore
from desktop.settings import DEFAULTS, RuntimeLLMConfig, config_from_environment, load_settings, save_settings
from desktop.workers import Worker, classify_connection_error, test_connection


class SettingsPage(QWidget):
    config_applied = Signal(object)
    def __init__(self, parent=None):
        super().__init__(parent); self.store = CredentialStore(); self.pool = QThreadPool.globalInstance(); self._config = load_settings()
        self.provider = QComboBox(); self.provider.addItems(["mock", "deepseek", "openai", "openai-compatible", "ollama"])
        self.base_url = QLineEdit(); self.model = QLineEdit(); self.api_key = QLineEdit(); self.api_key.setEchoMode(QLineEdit.Password); self.timeout = QDoubleSpinBox(); self.timeout.setRange(1, 300); self.timeout.setValue(30)
        self.secure = QCheckBox("Save API key securely with OS keyring"); self.status = QLabel(); self.show_key = QPushButton("Show"); self.show_key.setCheckable(True); self.show_key.toggled.connect(lambda on: self.api_key.setEchoMode(QLineEdit.Normal if on else QLineEdit.Password))
        self.provider.currentTextChanged.connect(self._defaults); self._load()
        form = QFormLayout(); form.addRow("Provider", self.provider); form.addRow("Base URL", self.base_url)
        keyrow = QHBoxLayout(); keyrow.addWidget(self.api_key); keyrow.addWidget(self.show_key); form.addRow("API key", keyrow)
        form.addRow("Model", self.model); form.addRow("Timeout (s)", self.timeout)
        save = QPushButton("Save / Apply"); self.test_button = QPushButton("Test Connection"); clear = QPushButton("Clear Credentials"); save.clicked.connect(self.save); self.test_button.clicked.connect(self.test); clear.clicked.connect(self.clear_credentials)
        buttons = QHBoxLayout(); buttons.addWidget(self.test_button); buttons.addWidget(save); buttons.addWidget(clear); buttons.addStretch()
        layout = QVBoxLayout(self); layout.addLayout(form); layout.addWidget(self.secure); layout.addLayout(buttons); layout.addWidget(self.status); layout.addStretch()

    def _defaults(self, provider):
        base, model = DEFAULTS.get(provider, ("", ""));
        if not self.base_url.text(): self.base_url.setText(base)
        if not self.model.text(): self.model.setText(model)

    def _load(self):
        self.provider.setCurrentText(self._config.provider); self.base_url.setText(self._config.base_url); self.model.setText(self._config.model); self.timeout.setValue(self._config.timeout)
        try: self.api_key.setText(self.store.get(self._config.provider))
        except CredentialError: pass
        if self._config.provider == "mock" and not load_settings().base_url:
            env_config = config_from_environment()
            if env_config.provider != "mock": self.provider.setCurrentText(env_config.provider); self.base_url.setText(env_config.base_url); self.model.setText(env_config.model); self.api_key.setText(env_config.api_key)
        self._defaults(self._config.provider)

    def config(self): return RuntimeLLMConfig(self.provider.currentText(), self.api_key.text().strip(), self.base_url.text().strip(), self.model.text().strip(), self.timeout.value())
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
        self.test_button.setEnabled(True); self.status.setText(f"连接失败（{classify_connection_error(message)}）：{message}"); self._active_worker = None
    def clear_credentials(self):
        try: self.store.delete(self.provider.currentText()); self.api_key.clear(); self.status.setText("已清除当前 provider 凭据")
        except CredentialError as exc: self.status.setText(str(exc))
