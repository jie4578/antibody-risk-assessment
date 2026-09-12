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


class LiteraturePage(QWidget):
    COLUMNS = ["Title", "Year", "Journal", "PMID", "DOI", "Relevance", "Source"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pool = QThreadPool.globalInstance()
        self._worker = None
        self._results = []; self._context = None
        self.query = QLineEdit(); self.query.setPlaceholderText("antibody deamidation NG motif CDR")
        self.source = QComboBox(); self.source.addItem("Auto", "auto"); self.source.addItem("Europe PMC", "europepmc"); self.source.addItem("PubMed", "pubmed")
        self.max_results = QSpinBox(); self.max_results.setRange(1, 50); self.max_results.setValue(10)
        self.filter = QComboBox(); self.filter.addItems(["Direct + General", "All", "Direct", "General"])
        self.search_button = QPushButton("Search"); self.search_button.clicked.connect(self.search)
        self.status = QLabel()
        self.context_banner = QLabel(); self.context_banner.setWordWrap(True); self.context_banner.hide()
        self.external_query = QLabel(); self.external_query.setWordWrap(True); self.external_query.hide()
        self.privacy = QLabel("Search terms are sent to external providers and may be cached locally for up to 7 days. Only topic-level terms are sent by default; full antibody sequences are not included.")
        self.privacy.setWordWrap(True)
        self.results_table = QTableWidget(0, len(self.COLUMNS)); self.results_table.setHorizontalHeaderLabels(self.COLUMNS); self.results_table.setSelectionBehavior(QTableWidget.SelectRows); self.results_table.setEditTriggers(QTableWidget.NoEditTriggers); self.results_table.itemSelectionChanged.connect(self._select_result)
        self.title = QLabel(); self.title.setWordWrap(True)
        self.authors = QLabel(); self.authors.setWordWrap(True)
        self.journal = QLabel(); self.pmid = QLabel(); self.doi = QLabel(); self.pmcid = QLabel(); self.source_label = QLabel(); self.relevance = QLabel(); self.abstract = QLabel(); self.abstract.setWordWrap(True); self.explanation = QLabel(); self.explanation.setWordWrap(True)
        self.open_source_button = QPushButton("Open Source"); self.open_source_button.setEnabled(False); self.open_source_button.clicked.connect(self.open_source)
        self.send_evidence_button = QPushButton("Send Evidence to AI Assistant"); self.send_evidence_button.setEnabled(False); self.send_evidence_button.clicked.connect(self.send_evidence)
        form = QFormLayout(); form.addRow("Query", self.query); form.addRow("Source", self.source); form.addRow("Max Results", self.max_results); form.addRow("Filter", self.filter)
        self.filter.currentTextChanged.connect(self._refresh_table)
        detail = QFormLayout(); detail.addRow("Title", self.title); detail.addRow("Authors", self.authors); detail.addRow("Journal / Year", self.journal); detail.addRow("PMID", self.pmid); detail.addRow("DOI", self.doi); detail.addRow("PMCID", self.pmcid); detail.addRow("Source", self.source_label); detail.addRow("Relevance", self.relevance); detail.addRow("Abstract", self.abstract); detail.addRow("Evidence / relevance", self.explanation)
        buttons = QHBoxLayout(); buttons.addWidget(self.search_button); buttons.addStretch(); buttons.addWidget(self.send_evidence_button); buttons.addWidget(self.open_source_button)
        layout = QVBoxLayout(self); layout.addWidget(QLabel("Literature Search")); layout.addWidget(self.context_banner); layout.addWidget(self.external_query); layout.addLayout(form); layout.addLayout(buttons); layout.addWidget(self.status); layout.addWidget(self.privacy); layout.addWidget(QLabel("Results")); layout.addWidget(self.results_table); layout.addWidget(QLabel("Selected Paper")); layout.addLayout(detail)

    def load_context(self, context: LiteratureContext):
        self._context = context; self.context_banner.setText(f"Context from {context.source.title()} Analysis\n{context.display_summary}"); self.external_query.setText(f"External query: {context.safe_query}"); self.context_banner.show(); self.external_query.show(); self.query.setText(context.safe_query); self._results = []; self._selected = None; self._refresh_table(); self._clear_detail(); self.status.setText("Review the external query, then click Search.")

    def clear_context(self):
        self._context = None; self.context_banner.clear(); self.external_query.clear(); self.context_banner.hide(); self.external_query.hide(); self._results = []; self._selected = None; self._refresh_table(); self._clear_detail(); self.status.clear()

    def _clear_detail(self):
        for widget in (self.title, self.authors, self.journal, self.pmid, self.doi, self.pmcid, self.source_label, self.relevance, self.abstract, self.explanation): widget.clear()
        self.open_source_button.setEnabled(False); self.send_evidence_button.setEnabled(False)

    def search(self):
        if self._worker is not None:
            return
        if not self.query.text().strip():
            self.status.setText("Please enter a literature query.")
            return
        self.search_button.setEnabled(False); self.status.setText("Searching…")
        self._worker = Worker(search_desktop_literature, self.query.text(), source=self.source.currentData(), max_results=self.max_results.value())
        self._worker.signals.finished.connect(self._done); self._worker.signals.error.connect(self._error); self.pool.start(self._worker)

    def _done(self, results):
        self._worker = None; self.search_button.setEnabled(True); self._results = list(results or []); self._refresh_table(); self.status.setText("No literature results found." if not self._results else f"Found {len(self._results)} result(s).")

    def _error(self, message):
        self._worker = None; self.search_button.setEnabled(True); self.status.setText(self._friendly_error(message)); self._results = []; self._refresh_table()

    @staticmethod
    def _friendly_error(message):
        text = str(message or "")
        if text.startswith("Please enter") or text.startswith("Invalid literature"):
            return text
        lower = text.lower()
        if "parse" in lower or "解析" in text:
            return "Literature provider response could not be parsed."
        if "429" in lower or "rate limit" in lower or "限速" in text or "频繁" in text:
            return "Literature provider rate limit reached."
        if "timeout" in lower or "timed out" in lower or "超时" in text:
            return "Literature provider request timed out."
        if "http " in lower or "不可用" in text or "网络错误" in text:
            return "Europe PMC / PubMed is temporarily unavailable."
        normalized = normalize_error(text)
        mapping = {"TIMEOUT": "Literature provider request timed out.", "RATE_LIMITED": "Literature provider rate limit reached.", "CONNECTION_FAILED": "Europe PMC / PubMed is temporarily unavailable.", "PROVIDER_API_ERROR": "Literature provider returned an API error.", "INVALID_BASE_URL": "Literature provider URL is invalid."}
        return mapping.get(normalized.code, "Literature search failed.")

    def _refresh_table(self):
        rows = visible_results(self._results, self.filter.currentText()); self.results_table.setRowCount(0)
        for result in rows:
            row = self.results_table.rowCount(); self.results_table.insertRow(row)
            for col, value in enumerate((result.title, result.year or "", result.journal, result.pmid, result.doi, result.relevance, result.source)):
                self.results_table.setItem(row, col, QTableWidgetItem(str(value)))
            self.results_table.item(row, 0).setData(32, result)
        self.open_source_button.setEnabled(False); self.send_evidence_button.setEnabled(False)

    def _select_result(self):
        item = self.results_table.currentItem()
        result = item.data(32) if item else None
        if not isinstance(result, DesktopEvidence):
            return
        self.title.setText(result.title or "-"); self.authors.setText(", ".join(result.authors) or "-"); self.journal.setText(f"{result.journal or '-'} / {result.year or '-'}"); self.pmid.setText(result.pmid or "-"); self.doi.setText(result.doi or "-"); self.pmcid.setText(result.pmcid or "-"); self.source_label.setText(result.source or "-"); self.relevance.setText(result.relevance or "-"); self.abstract.setText(result.abstract or "-"); self.explanation.setText(result.relevance_reason or "-"); self.open_source_button.setEnabled(bool(result.source_url)); self.send_evidence_button.setEnabled(True); self._selected = result

    def set_open_ai(self, callback):
        self._open_ai = callback

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
