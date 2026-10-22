from __future__ import annotations

from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget

from agent.agent import Agent
from desktop.settings import RuntimeLLMConfig, build_backend
from desktop.workers import Worker
from desktop.zh_cn import evidence_context_zh, notice_zh


class AIAssistantPage(QWidget):
    def __init__(self, config_getter, parent=None):
        super().__init__(parent); self.config_getter = config_getter; self.pool = QThreadPool.globalInstance(); self._evidence_context = None; self.question = QPlainTextEdit(); self.question.setPlaceholderText("输入科研问题…"); self.answer = QPlainTextEdit(); self.answer.setReadOnly(True); self.status = QLabel(); self.evidence_panel = QPlainTextEdit(); self.evidence_panel.setReadOnly(True); self.clear_evidence_button = QPushButton("清除证据"); self.clear_evidence_button.setEnabled(False); self.clear_evidence_button.clicked.connect(self.clear_evidence); button = QPushButton("提问"); button.clicked.connect(self.ask); layout = QVBoxLayout(self); layout.addWidget(QLabel("AI 助手")); layout.addWidget(QLabel("已附加的文献证据")); layout.addWidget(self.evidence_panel); layout.addWidget(self.clear_evidence_button); layout.addWidget(self.question); layout.addWidget(button); layout.addWidget(self.status); layout.addWidget(self.answer)
    def ask(self):
        config: RuntimeLLMConfig = self.config_getter();
        if config.provider in {"deepseek", "openai"} and not config.api_key:
            self.status.setText("未配置 API 密钥，请先到“设置”中配置"); return
        self.status.setText("处理中…"); worker = Worker(self._run, config, self.question.toPlainText(), self._evidence_context); worker.signals.finished.connect(self._done); worker.signals.error.connect(self._error); self.pool.start(worker)
    @staticmethod
    def _run(config, question, evidence_context=None):
        if evidence_context:
            question = ("CURRENT ANALYSIS CONTEXT:\n" + (evidence_context.originating_analysis_context_summary or "None") + "\n\n" + evidence_context.prompt_block() + "\n\nUSER QUESTION:\n" + question)
        return Agent(backend=build_backend(config)).ask("请使用简体中文回答，保留原始数值及引用标识。\n\n" + question)
    def _done(self, text): self.answer.setPlainText(text); self.status.setText("完成")
    def _error(self, text): self.status.setText(notice_zh(text))

    def load_evidence_context(self, context):
        self._evidence_context = context; self.evidence_panel.setPlainText(evidence_context_zh(context)); self.clear_evidence_button.setEnabled(True)

    def clear_evidence(self):
        self._evidence_context = None; self.evidence_panel.clear(); self.clear_evidence_button.setEnabled(False)
