from __future__ import annotations

from PySide6.QtWidgets import QLabel, QListWidget, QMainWindow, QStackedWidget, QHBoxLayout, QWidget

from desktop.settings import RuntimeLLMConfig, load_settings
from desktop.widgets.ai_assistant import AIAssistantPage
from desktop.widgets.settings_page import SettingsPage
from desktop.widgets.single_analysis import SingleAnalysisPage


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__(); self.setWindowTitle("Antibody AI Research Assistant — Desktop Workbench"); self.resize(1100, 750); self._config = load_settings()
        self.nav = QListWidget(); self.nav.addItems(["Single Analysis", "Batch Analysis", "Mutation", "Literature", "AI Assistant", "Settings"]); self.stack = QStackedWidget(); self.stack.addWidget(SingleAnalysisPage());
        for name in ("Batch Analysis", "Mutation", "Literature"): self.stack.addWidget(QLabel(f"{name}\nComing in v10 Phase 2"))
        self.settings = SettingsPage(); self._config = self.settings.config(); self.ai = AIAssistantPage(lambda: self._config); self.stack.addWidget(self.ai); self.stack.addWidget(self.settings); self.settings.config_applied.connect(self._set_config); self.nav.currentRowChanged.connect(self.stack.setCurrentIndex); self.nav.setCurrentRow(0)
        root = QWidget(); layout = QHBoxLayout(root); layout.addWidget(self.nav, 1); layout.addWidget(self.stack, 4); self.setCentralWidget(root)
    def _set_config(self, config: RuntimeLLMConfig): self._config = config
