from __future__ import annotations

from PySide6.QtCore import Signal, QThreadPool
from PySide6.QtWidgets import QCheckBox, QComboBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QDoubleSpinBox, QVBoxLayout, QWidget

from desktop.credentials import CredentialError, CredentialStore
from desktop.errors import normalize_error
from desktop.providers import model_display_name, provider_spec, resolve_model
from desktop.settings import DEFAULTS, RuntimeLLMConfig, config_from_environment, load_settings, save_settings
from desktop.workers import Worker, classify_connection_error, test_connection
from desktop.zh_cn import notice_zh


class SettingsPage(QWidget):
    config_applied = Signal(object)
    def __init__(self, parent=None):
        super().__init__(parent); self.store = CredentialStore(); self.pool = QThreadPool.globalInstance(); self._config = load_settings(); self._provider_state = {}
        self.provider = QComboBox()
        for label, value in (("DeepSeek", "deepseek"), ("OpenAI", "openai"), ("兼容 OpenAI 的服务", "openai-compatible"), ("Ollama（本地）", "ollama"), ("离线模拟（Mock）", "mock")):
            self.provider.addItem(label, value)
        self.base_url = QLineEdit(); self.model = QComboBox(); self.model.setEditable(True); self.api_key = QLineEdit(); self.api_key.setEchoMode(QLineEdit.Password); self.timeout = QDoubleSpinBox(); self.timeout.setRange(1, 300); self.timeout.setValue(30)
        self.secure = QCheckBox("使用系统凭据库安全保存 API 密钥"); self.status = QLabel(); self.show_key = QPushButton("显示密钥"); self.show_key.setCheckable(True); self.show_key.toggled.connect(lambda on: self.api_key.setEchoMode(QLineEdit.Normal if on else QLineEdit.Password))
        self.provider.currentIndexChanged.connect(lambda _: self._switch_provider(self.provider.currentData())); self._load()
        form = QFormLayout(); form.addRow("服务提供方", self.provider); form.addRow("服务基础 URL", self.base_url)
        keyrow = QHBoxLayout(); keyrow.addWidget(self.api_key); keyrow.addWidget(self.show_key); form.addRow("API 密钥", keyrow)
        form.addRow("模型", self.model); form.addRow("超时（秒）", self.timeout)
        save = QPushButton("保存并应用"); self.test_button = QPushButton("测试连接"); clear = QPushButton("清除凭据"); save.clicked.connect(self.save); self.test_button.clicked.connect(self.test); clear.clicked.connect(self.clear_credentials)
        buttons = QHBoxLayout(); buttons.addWidget(self.test_button); buttons.addWidget(save); buttons.addWidget(clear); buttons.addStretch()
        layout = QVBoxLayout(self); layout.addLayout(form); layout.addWidget(self.secure); layout.addLayout(buttons); layout.addWidget(self.status); layout.addStretch()

    def _load_provider(self, provider, base_url="", model=""):
        spec = provider_spec(provider); self.base_url.setText(base_url or (spec.default_base_url or "")); self.model.clear()
        self.model.addItems([m.display_name for m in spec.models]); self.model.setCurrentText(model_display_name(provider, model) if model else (spec.models[0].display_name if spec.models else ""))
        self.base_url.setEnabled(provider != "mock"); self.model.setEnabled(provider != "mock"); self.api_key.setEnabled(provider not in {"ollama", "mock"})

    def _load(self):
        provider = self._config.provider if self._config.provider in {"deepseek", "openai", "openai-compatible", "ollama", "mock"} else "mock"
        self.provider.setCurrentIndex(self.provider.findData(provider)); self._current_provider = provider; self._load_provider(provider, self._config.base_url, self._config.model); self.timeout.setValue(self._config.timeout)
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
        provider = self.provider.currentData()
        return RuntimeLLMConfig(provider, self.api_key.text().strip(), self.base_url.text().strip(), resolve_model(provider, self.model.currentText()), self.timeout.value())
    def save(self):
        config = self.config()
        try:
            if self.secure.isChecked() and config.api_key: self.store.save_secure(config.provider, config.api_key)
            elif config.api_key: self.store.set_session(config.provider, config.api_key)
            save_settings(config); self._config = config; self.config_applied.emit(config); self.status.setText("已保存并应用（API 密钥不写入配置文件）")
        except (CredentialError, OSError) as exc: self.status.setText(str(exc))
    def test(self):
        if not self.test_button.isEnabled(): return
        config = self.config(); self.test_button.setEnabled(False); self.status.setText("正在测试连接…")
        worker = Worker(test_connection, config, secrets=[config.api_key]); self._active_worker = worker
        worker.signals.finished.connect(self._test_success); worker.signals.error.connect(self._test_error); self.pool.start(worker)
    def _test_success(self, message):
        self.test_button.setEnabled(True); self.status.setText(message); self._active_worker = None
    def _test_error(self, message):
        self.test_button.setEnabled(True); normalized = normalize_error(message); self.status.setText(f"{notice_zh(normalized.message)} {message}"); self._active_worker = None
    def clear_credentials(self):
        try: self.store.delete(self.provider.currentData()); self.api_key.clear(); self.status.setText("已清除当前服务提供方的凭据")
        except CredentialError as exc: self.status.setText(str(exc))
