from __future__ import annotations

from PySide6.QtCore import QThreadPool, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from desktop.errors import normalize_error
from desktop.literature_adapter import DesktopEvidence, search_desktop_literature, visible_results
from desktop.literature_context import LiteratureContext
from desktop.evidence_context import from_desktop_evidence
from desktop.workers import Worker
from desktop.zh_cn import display_value, notice_zh


class LiteraturePage(QWidget):
    COLUMNS = ["标题", "年份", "期刊", "PMID", "DOI", "相关性", "来源"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pool = QThreadPool.globalInstance()
        self._worker = None
        self._selected = None
        self._search_generation = 0
        self._results = []; self._context = None; self._summary_changed_callback = None
        self.query = QLineEdit(); self.query.setPlaceholderText("输入主题关键词，例如 antibody deamidation NG motif CDR")
        self.source = QComboBox(); self.source.addItem("自动", "auto"); self.source.addItem("Europe PMC", "europepmc"); self.source.addItem("PubMed", "pubmed")
        self.max_results = QSpinBox(); self.max_results.setRange(1, 50); self.max_results.setValue(10)
        self.filter = QComboBox()
        for label, value in (("直接相关 + 一般参考", "Direct + General"), ("全部", "All"), ("仅直接相关", "Direct"), ("仅一般参考", "General")):
            self.filter.addItem(label, value)
        self.search_button = QPushButton("搜索"); self.search_button.clicked.connect(self.search)
        self.status = QLabel()
        self.context_banner = QLabel(); self.context_banner.setWordWrap(True); self.context_banner.hide()
        self.external_query = QLabel(); self.external_query.setWordWrap(True); self.external_query.hide()
        self.privacy = QLabel("搜索词会发送给外部文献服务，并可能在本地缓存最多 7 天；默认仅发送主题词，不包含完整抗体序列。")
        self.privacy.setWordWrap(True)
        self.results_table = QTableWidget(0, len(self.COLUMNS)); self.results_table.setHorizontalHeaderLabels(self.COLUMNS); self.results_table.setSelectionBehavior(QTableWidget.SelectRows); self.results_table.setEditTriggers(QTableWidget.NoEditTriggers); self.results_table.itemSelectionChanged.connect(self._select_result)
        self.title = QLabel(); self.title.setWordWrap(True)
        self.authors = QLabel(); self.authors.setWordWrap(True)
        self.journal = QLabel(); self.pmid = QLabel(); self.doi = QLabel(); self.pmcid = QLabel(); self.source_label = QLabel(); self.relevance = QLabel(); self.abstract = QLabel(); self.abstract.setWordWrap(True); self.explanation = QLabel(); self.explanation.setWordWrap(True)
        self.open_source_button = QPushButton("打开原文"); self.open_source_button.setEnabled(False); self.open_source_button.clicked.connect(self.open_source)
        self.send_evidence_button = QPushButton("发送证据至 AI 助手"); self.send_evidence_button.setEnabled(False); self.send_evidence_button.clicked.connect(self.send_evidence)
        form = QFormLayout(); form.addRow("检索词", self.query); form.addRow("来源", self.source); form.addRow("最多结果数", self.max_results); form.addRow("筛选", self.filter)
        self.filter.currentTextChanged.connect(self._refresh_table)
        detail = QFormLayout(); detail.addRow("标题", self.title); detail.addRow("作者", self.authors); detail.addRow("期刊 / 年份", self.journal); detail.addRow("PMID", self.pmid); detail.addRow("DOI", self.doi); detail.addRow("PMCID", self.pmcid); detail.addRow("来源", self.source_label); detail.addRow("相关性", self.relevance); detail.addRow("摘要", self.abstract); detail.addRow("证据 / 相关性说明", self.explanation)
        buttons = QHBoxLayout(); buttons.addWidget(self.search_button); buttons.addStretch(); buttons.addWidget(self.send_evidence_button); buttons.addWidget(self.open_source_button)
        layout = QVBoxLayout(self); layout.addWidget(QLabel("文献检索")); layout.addWidget(self.context_banner); layout.addWidget(self.external_query); layout.addLayout(form); layout.addLayout(buttons); layout.addWidget(self.status); layout.addWidget(self.privacy); layout.addWidget(QLabel("检索结果")); layout.addWidget(self.results_table); layout.addWidget(QLabel("所选文献")); layout.addLayout(detail)
        self.results_table.currentCellChanged.connect(lambda *_: self._select_result())
        self.query.textChanged.connect(self._query_changed)
        self.source.currentIndexChanged.connect(self._query_changed)
        self.max_results.valueChanged.connect(self._query_changed)

    def _query_changed(self, *_):
        self._search_generation += 1
        self._results = []
        self._refresh_table()
        self.status.setText(
            "检索条件已变化，请点击“搜索”刷新结果。"
            if self.query.text().strip() else "请输入检索词，然后点击“搜索”。"
        )

    def load_context(self, context: LiteratureContext):
        self._search_generation += 1
        self._context = context
        source = {"single": "单条分析", "mutation": "突变分析"}.get(context.source, context.source)
        details = f"类别：{context.risk_category} | 基序：{context.motif} | 区域：{display_value(context.region)} | 位置：{context.position}"
        if context.mutation:
            details = f"突变：{context.mutation} | " + details
        self.context_banner.setText(f"上下文来自{source}\n{details}"); self.external_query.setText(f"对外检索词：{context.safe_query}"); self.context_banner.show(); self.external_query.show(); self.query.setText(context.safe_query); self._results = []; self._refresh_table(); self.status.setText("请核对将对外发送的检索词，再点击“搜索”。")

    def clear_context(self):
        self._search_generation += 1
        self._context = None; self.context_banner.clear(); self.external_query.clear(); self.context_banner.hide(); self.external_query.hide(); self._results = []; self._refresh_table(); self.status.clear()

    def _clear_detail(self):
        had_selection = self._selected is not None
        self._selected = None
        for widget in (self.title, self.authors, self.journal, self.pmid, self.doi, self.pmcid, self.source_label, self.relevance, self.abstract, self.explanation): widget.clear()
        self.open_source_button.setEnabled(False); self.send_evidence_button.setEnabled(False)
        if had_selection and callable(self._summary_changed_callback):
            self._summary_changed_callback()

    def search(self):
        if self._worker is not None:
            return
        if not self.query.text().strip():
            self.status.setText("请输入文献检索词。")
            return
        self.search_button.setEnabled(False); self.status.setText("正在搜索…")
        self._worker = Worker(search_desktop_literature, self.query.text(), source=self.source.currentData(), max_results=self.max_results.value())
        worker, token = self._worker, self._search_generation
        worker.signals.finished.connect(lambda result, w=worker, t=token: self._search_finished(w, t, result=result))
        worker.signals.error.connect(lambda error, w=worker, t=token: self._search_finished(w, t, error=error))
        self.pool.start(worker)

    def _search_finished(self, worker, token, result=None, error=None):
        if self._worker is worker:
            self._worker = None
            self.search_button.setEnabled(True)
        if token != self._search_generation:
            return
        if error is not None:
            self._error(error)
        else:
            self._done(result)

    def _done(self, results):
        self._worker = None; self.search_button.setEnabled(True); self._results = list(results or []); self._refresh_table(); self.status.setText("未找到文献结果。" if not self._results else f"找到 {len(self._results)} 条结果。")

    def _error(self, message):
        self._worker = None; self.search_button.setEnabled(True); self.status.setText(self._friendly_error(message)); self._results = []; self._refresh_table()

    @staticmethod
    def _friendly_error(message):
        text = str(message or "")
        if text.startswith("Please enter") or text.startswith("Invalid literature"):
            return notice_zh(text)
        lower = text.lower()
        if "parse" in lower or "解析" in text:
            return "无法解析文献服务返回的内容。"
        if "429" in lower or "rate limit" in lower or "限速" in text or "频繁" in text:
            return "文献服务请求频率已达上限。"
        if "timeout" in lower or "timed out" in lower or "超时" in text:
            return "文献服务请求超时。"
        if "http " in lower or "不可用" in text or "网络错误" in text:
            return "Europe PMC / PubMed 暂时不可用。"
        normalized = normalize_error(text)
        mapping = {"TIMEOUT": "文献服务请求超时。", "RATE_LIMITED": "文献服务请求频率已达上限。", "CONNECTION_FAILED": "Europe PMC / PubMed 暂时不可用。", "PROVIDER_API_ERROR": "文献服务返回 API 错误。", "INVALID_BASE_URL": "文献服务 URL 无效。"}
        return mapping.get(normalized.code, "文献搜索失败。")

    def _refresh_table(self):
        self._clear_detail()
        self.results_table.blockSignals(True)
        rows = visible_results(self._results, self.filter.currentData()); self.results_table.setRowCount(0)
        for result in rows:
            row = self.results_table.rowCount(); self.results_table.insertRow(row)
            for col, value in enumerate((result.title, result.year or "", result.journal, result.pmid, result.doi, display_value(result.relevance), result.source)):
                self.results_table.setItem(row, col, QTableWidgetItem(str(value)))
            self.results_table.item(row, 0).setData(32, result)
        self.open_source_button.setEnabled(False); self.send_evidence_button.setEnabled(False)
        self.results_table.blockSignals(False)

    def _select_result(self):
        row = self.results_table.currentRow()
        item = self.results_table.item(row, 0) if row >= 0 else None
        result = item.data(32) if item else None
        if not isinstance(result, DesktopEvidence):
            self._clear_detail()
            return
        changed = self._selected is not result
        self.title.setText(result.title or "-"); self.authors.setText(", ".join(result.authors) or "-"); self.journal.setText(f"{result.journal or '-'} / {result.year or '-'}"); self.pmid.setText(result.pmid or "-"); self.doi.setText(result.doi or "-"); self.pmcid.setText(result.pmcid or "-"); self.source_label.setText(result.source or "-"); self.relevance.setText(display_value(result.relevance or "-")); self.abstract.setText(result.abstract or "-"); self.explanation.setText(result.relevance_reason or "-"); self.open_source_button.setEnabled(bool(result.source_url)); self.send_evidence_button.setEnabled(True); self._selected = result
        if changed and callable(self._summary_changed_callback):
            self._summary_changed_callback()

    def set_open_ai(self, callback):
        self._open_ai = callback

    def set_summary_changed_callback(self, callback):
        self._summary_changed_callback = callback

    def send_evidence(self):
        result = getattr(self, "_selected", None)
        callback = getattr(self, "_open_ai", None)
        if result and callback:
            summary = self._context.display_summary if self._context else ""
            callback(from_desktop_evidence(result, self.query.text(), summary))

    def open_source(self):
        result = getattr(self, "_selected", None)
        if result and result.source_url:
            QDesktopServices.openUrl(QUrl(result.source_url))
