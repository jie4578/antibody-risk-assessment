from __future__ import annotations

from PySide6.QtCore import QThreadPool, QTimer
from PySide6.QtWidgets import QLabel, QListWidget, QMainWindow, QStackedWidget, QHBoxLayout, QScrollArea, QWidget

from desktop.workers import Worker
from desktop.zh_cn import install_qt_chinese

from desktop.settings import RuntimeLLMConfig, load_settings
from desktop.widgets.ai_assistant import AIAssistantPage
from desktop.widgets.batch_analysis import BatchAnalysisPage
from desktop.widgets.settings_page import SettingsPage
from desktop.widgets.single_analysis import SingleAnalysisPage
from desktop.widgets.mutation import MutationPage
from desktop.widgets.literature import LiteraturePage


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        from PySide6.QtWidgets import QApplication
        install_qt_chinese(QApplication.instance())
        self.setWindowTitle("抗体 AI 科研助手 — 桌面工作台"); self.resize(1100, 750); self._config = load_settings()
        self.nav = QListWidget(); self.nav.addItems(["单条分析", "批量分析", "突变", "文献", "AI 助手", "设置"]); self.stack = QStackedWidget(); self.single = SingleAnalysisPage(open_mutation=self._open_mutation, open_literature=self._open_literature, research_state_getter=self._research_state_for_single, config_getter=lambda: self._config); self.mutation = MutationPage(open_literature=self._open_literature, on_state_changed=self.single.notify_external_evidence_changed); self.stack.addWidget(self.single); self.stack.addWidget(BatchAnalysisPage(open_single=self._open_single, open_mutation=self._open_mutation)); self.stack.addWidget(self.mutation)
        self.literature = LiteraturePage(); self.literature.set_open_ai(self._open_ai_evidence); self.literature.set_summary_changed_callback(self.single.notify_external_evidence_changed); self.stack.addWidget(self.literature)
        self.settings = SettingsPage(); self._config = self.settings.config(); self.ai = AIAssistantPage(lambda: self._config); self.stack.addWidget(self.ai); self.stack.addWidget(self.settings); self.settings.config_applied.connect(self._set_config); self.settings.config_applied.connect(self.single.notify_config_changed); self.nav.currentRowChanged.connect(self.stack.setCurrentIndex); self.nav.setCurrentRow(0)
        self.nav.setFixedWidth(136)
        self.content_scroll = QScrollArea()
        self.content_scroll.setWidgetResizable(True)
        self.content_scroll.setWidget(self.stack)
        self.nav.currentRowChanged.connect(lambda _: self.content_scroll.verticalScrollBar().setValue(0))
        root = QWidget(); layout = QHBoxLayout(root); layout.addWidget(self.nav); layout.addWidget(self.content_scroll, 1); self.setCentralWidget(root)
        self._shutdown_pool = QThreadPool.globalInstance()
        self._shutdown_requested = False
        self._shutdown_timer = QTimer(self)
        self._shutdown_timer.setInterval(100)
        self._shutdown_timer.timeout.connect(self._check_shutdown)

    def closeEvent(self, event):
        if not self._shutdown_requested:
            self._shutdown_requested = True
            Worker.cancel_all()
            self._shutdown_pool.clear()
        if self._shutdown_pool.activeThreadCount():
            event.ignore()
            self.setEnabled(False)
            self.statusBar().showMessage("正在关闭：已取消排队任务，等待正在运行的操作完成…")
            self._shutdown_timer.start()
        else:
            self._shutdown_timer.stop()
            event.accept()

    def _check_shutdown(self):
        if self._shutdown_pool.activeThreadCount() == 0:
            self._shutdown_timer.stop()
            self.close()
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
