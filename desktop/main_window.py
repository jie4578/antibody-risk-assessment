from __future__ import annotations

from PySide6.QtWidgets import QLabel, QListWidget, QMainWindow, QStackedWidget, QHBoxLayout, QWidget

from desktop.settings import RuntimeLLMConfig, load_settings
from desktop.widgets.ai_assistant import AIAssistantPage
from desktop.widgets.batch_analysis import BatchAnalysisPage
from desktop.widgets.settings_page import SettingsPage
from desktop.widgets.single_analysis import SingleAnalysisPage
from desktop.widgets.mutation import MutationPage
from desktop.widgets.literature import LiteraturePage


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__(); self.setWindowTitle("Antibody AI Research Assistant — Desktop Workbench"); self.resize(1100, 750); self._config = load_settings()
        self.nav = QListWidget(); self.nav.addItems(["Single Analysis", "Batch Analysis", "Mutation", "Literature", "AI Assistant", "Settings"]); self.stack = QStackedWidget(); self.single = SingleAnalysisPage(open_mutation=self._open_mutation, open_literature=self._open_literature, research_state_getter=self._research_state_for_single, config_getter=lambda: self._config); self.mutation = MutationPage(open_literature=self._open_literature, on_state_changed=self.single.notify_external_evidence_changed); self.stack.addWidget(self.single); self.stack.addWidget(BatchAnalysisPage(open_single=self._open_single, open_mutation=self._open_mutation)); self.stack.addWidget(self.mutation)
        self.literature = LiteraturePage(); self.literature.set_open_ai(self._open_ai_evidence); self.literature.set_summary_changed_callback(self.single.notify_external_evidence_changed); self.stack.addWidget(self.literature)
        self.settings = SettingsPage(); self._config = self.settings.config(); self.ai = AIAssistantPage(lambda: self._config); self.stack.addWidget(self.ai); self.stack.addWidget(self.settings); self.settings.config_applied.connect(self._set_config); self.settings.config_applied.connect(self.single.notify_config_changed); self.nav.currentRowChanged.connect(self.stack.setCurrentIndex); self.nav.setCurrentRow(0)
        root = QWidget(); layout = QHBoxLayout(root); layout.addWidget(self.nav, 1); layout.addWidget(self.stack, 4); self.setCentralWidget(root)
    def _set_config(self, config: RuntimeLLMConfig): self._config = config
    def _research_state_for_single(self):
        state = dict(self.mutation.get_research_summary_state())
        selected = getattr(self.literature, "_selected", None)
        state["literature_evidence"] = [selected] if selected is not None else []
        return state
    def _open_single(self, antibody_id, sequence):
        self.single.set_input(antibody_id, sequence, analyze=True)
        self.nav.setCurrentRow(0)
    def _open_mutation(self, antibody_id, sequence, chain="Unspecified"):
        self.mutation.load_sequence(antibody_id, sequence, chain); self.nav.setCurrentRow(2)
    def _open_literature(self, context):
        self.literature.load_context(context); self.nav.setCurrentRow(3)
    def _open_ai_evidence(self, context):
        self.ai.load_evidence_context(context); self.nav.setCurrentRow(4)
