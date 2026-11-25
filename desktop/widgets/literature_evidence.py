"""Atomic read-only literature intake; no PDF or external engine execution."""
import json
from pathlib import Path
import uuid

from PySide6.QtCore import QThreadPool, Qt, Slot
from PySide6.QtWidgets import (QAbstractItemView, QFileDialog, QHeaderView,
                               QLabel, QPlainTextEdit, QSplitter, QTableWidget,
                               QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)

from desktop.integrations.adapters import inspect_literature_evidence
from desktop.integrations.common import IntegrationError, ResultSummary
from desktop.widgets.research_workflow import ResultImportPanel, _read_operation
from desktop.workers import Worker


LOCATION_LABELS = {
    "RESULT_TEXT_MATCH": "结果页文本匹配（未核对 PDF）",
    "LOCATION_NOT_REPRODUCED": "上游声称定位；结果页文本未匹配",
    "INSUFFICIENT_LOCATION": "定位来源不足；未核验",
    "UPSTREAM_UNVERIFIED": "上游未验证",
    "UPSTREAM_CLAIM_ONLY": "仅上游声明；未核验",
}


def _table(headers):
    table = QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setSelectionBehavior(QAbstractItemView.SelectRows)
    table.setSelectionMode(QAbstractItemView.SingleSelection)
    table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
    table.horizontalHeader().setStretchLastSection(True)
    return table


class LiteratureEvidencePanel(ResultImportPanel):
    """Keep the last accepted immutable snapshot until a whole new read succeeds.

    Pending selection is separate from the accepted path and displayed evidence.
    Each worker returns its original request ID through a queued QObject slot.
    """
    def __init__(self, parent=None):
        super().__init__("literature", parent)
        self.loaders["literature"] = inspect_literature_evidence
        self.pending_path = None
        self.select_button.setText("导入文献批次与已有证据")
        self.layout().removeWidget(self.details)
        self.document_table = _table(["标题候选 / 文件名", "来源标签", "处理状态", "证据数"])
        self.evidence_table = _table(["PDF 物理页码", "定位状态", "质量警示", "原文片段"])
        self.document_details = QPlainTextEdit()
        self.document_details.setReadOnly(True)
        self.document_details.setMaximumHeight(125)
        self.quote = QPlainTextEdit()
        self.quote.setReadOnly(True)
        self.quote.setPlaceholderText("选择文献及证据后阅读已有原文；不会打开或解析 PDF。")
        reader = QWidget()
        layout = QVBoxLayout(reader)
        note = QLabel("verified 仅是上游原文定位声明，不代表科学事实真实。物理页码不是期刊印刷页码。"
                      "本页只比对已有 JSON 页文本，未独立读取 PDF 或验证其来源哈希。")
        note.setTextFormat(Qt.PlainText)
        note.setWordWrap(True)
        layout.addWidget(note)
        splitter = QSplitter(Qt.Vertical)
        for widget in (self.document_table, self.document_details, self.evidence_table, self.quote):
            splitter.addWidget(widget)
        layout.addWidget(splitter)
        self.reader_tabs = QTabWidget()
        self.reader_tabs.addTab(reader, "文献与证据")
        self.reader_tabs.addTab(self.details, "来源、报告位置与安全摘要")
        self.layout().addWidget(self.reader_tabs, 1)
        self.document_table.currentCellChanged.connect(self._document_selected)
        self.evidence_table.currentCellChanged.connect(self._evidence_selected)
        self._visible_evidence = ()

    @Slot()
    def choose(self):
        filename, _ = QFileDialog.getOpenFileName(
            self, "导入已有批次（仅授权该结果目录；不读取 PDF）", "", "文献批次 (batch_manifest.json)")
        if filename:
            self.import_manifest(filename)

    def import_manifest(self, filename):
        if not filename or self._closed:
            return
        if self._worker is not None:
            self._worker.cancel()
        self._token = uuid.uuid4().hex
        self.pending_path = str(filename)
        self._busy = True
        self.status.setText("正在核验新批次 " + Path(filename).name + "；已有接入保持不变。")
        worker = Worker(_read_operation, self._token, self.loaders["literature"], str(filename))
        self._worker = worker
        worker.signals.finished.connect(self._received)
        QThreadPool.globalInstance().start(worker)

    @Slot(object)
    def _received(self, payload):
        token, summary, error = payload
        if self._closed or token != self._token:
            return
        self._busy = False
        self._worker = None
        attempted = self.pending_path
        self.pending_path = None
        if not error:
            try:
                if not isinstance(summary, ResultSummary) or summary.project != "Literature Evidence Assistant":
                    raise IntegrationError("INVALID_RESULT", "不是已审核的文献批次摘要")
                details = json.dumps(summary.as_dict(), ensure_ascii=False, allow_nan=False, indent=2)
            except Exception:
                error = "INVALID_RESULT: 文献结果无法安全展示"
        if error:
            self.status.setText("新批次拒绝接入：" + error + "。此前成功接入的数据保持不变。")
            return
        self.summary = summary
        self.path.setText(attempted)
        self.details.setPlainText(details)
        counts = dict(summary.counts)
        self.status.setText(f"已接入批次 {summary.identifier}；上游状态={summary.source_state}；"
                            f"接入状态={summary.state}；完成文档 {counts['completed_count']}，"
                            f"失败文档 {counts['failed_count']}。不代表科学结论有效。")
        self._populate_documents()

    def _populate_documents(self):
        self.document_table.setRowCount(0)
        self.evidence_table.setRowCount(0)
        self.document_details.clear()
        self.quote.clear()
        self._visible_evidence = ()
        for document in self.summary.documents:
            row = self.document_table.rowCount()
            self.document_table.insertRow(row)
            title = document.title_candidate or document.display_name + "（缺少标题候选）"
            for col, value in enumerate((title, document.source_alias, document.state, str(document.evidence_count))):
                item = QTableWidgetItem(value)
                item.setData(Qt.UserRole, document.document_id)
                self.document_table.setItem(row, col, item)
        if self.document_table.rowCount():
            self.document_table.setCurrentCell(0, 0)

    @Slot(int, int, int, int)
    def _document_selected(self, row, column, previous_row, previous_column):
        self.evidence_table.setRowCount(0)
        self.quote.clear()
        self.document_details.clear()
        self._visible_evidence = ()
        if self.summary is None or row < 0:
            return
        item = self.document_table.item(row, column)
        if item is None:
            return
        document_id = item.data(Qt.UserRole)
        document = next(d for d in self.summary.documents if d.document_id == document_id)
        self.document_details.setPlainText(
            f"标题候选来源（上游声明）：{document.title_source or '未提供'}\n"
            f"文件标签：{document.display_name}；来源标签：{document.source_alias}\n"
            f"DOI（上游声明）：{document.doi or '未提供'}\n"
            f"document_id：{document.document_id}\n"
            f"PDF SHA256（未独立核验）：{document.source_content_sha256 or '缺失'}\n"
            f"结构化结果位置（不自动打开）：{document.result_file}")
        self._visible_evidence = tuple(e for e in self.summary.evidence if e.document_id == document_id)
        for evidence in self._visible_evidence:
            n = self.evidence_table.rowCount()
            self.evidence_table.insertRow(n)
            pages = (f"{evidence.page_start}–{evidence.page_end}" if evidence.page_start is not None else "未提供")
            values = (pages, LOCATION_LABELS[evidence.location_status],
                      "；".join(evidence.quality_flags) or "无上游质量标记", evidence.quote[:160])
            for col, value in enumerate(values):
                self.evidence_table.setItem(n, col, QTableWidgetItem(value))
        if self.evidence_table.rowCount():
            self.evidence_table.setCurrentCell(0, 0)
        else:
            self.quote.setPlainText("该文献没有可接入的既有证据；未生成或补写证据。")

    @Slot(int, int, int, int)
    def _evidence_selected(self, row, column, previous_row, previous_column):
        if row < 0 or row >= len(self._visible_evidence):
            return
        evidence = self._visible_evidence[row]
        self.quote.setPlainText(
            evidence.quote + "\n\n" + LOCATION_LABELS[evidence.location_status] +
            f"\n批次：{evidence.batch_id}\n文献：{evidence.document_id}\n来源：{evidence.source_file}"
            f"\n上游 verified 声明：{str(evidence.upstream_verified).lower()}"
            "\n以上均不证明科学事实真实；未重新读取 PDF。")

    @Slot()
    def clear(self):
        super().clear()
        self.pending_path = None
        self.document_table.setRowCount(0)
        self.evidence_table.setRowCount(0)
        self.document_details.clear()
        self.quote.clear()
        self._visible_evidence = ()
