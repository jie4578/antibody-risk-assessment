from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import QComboBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QInputDialog, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from desktop.batch_adapter import BatchResult, analyze_file, fasta_requires_chain, input_mapping
from desktop.column_mapping import infer_smart_mapping
import pandas as pd
from desktop.widgets.column_mapping_dialog import ColumnMappingDialog
from desktop.batch_export import write_summary_csv, write_summary_xlsx, write_template
from desktop.workers import Worker, sanitize_error
from core import validate_sequence


class BatchAnalysisPage(QWidget):
    COLUMNS = ["Antibody ID", "VH Len", "VL Len", "Risk Score", "Risk Level", "Total Sites", "CDR Sites", "PTM Sites", "Liability Sites", "Status"]

    def __init__(self, parent=None, open_single=None, open_mutation=None):
        super().__init__(parent); self.pool = QThreadPool.globalInstance(); self.records = []; self._active_worker = None; self._open_single = open_single; self._open_mutation = open_mutation; self.source = QLabel("No file selected"); self.risk_filter = QComboBox(); self.risk_filter.addItems(["All", "Low", "Medium", "High"]); self.search = QLineEdit(); self.search.setPlaceholderText("Antibody ID")
        self.mutation_chain = QComboBox(); self.mutation_chain.addItems(["VH", "VL"]); self.send_mutation_button = QPushButton("Send to Mutation"); self.import_button = QPushButton("Import File"); self.template_button = QPushButton("Download Template"); self.export_csv_button = QPushButton("Export CSV"); self.export_xlsx_button = QPushButton("Export XLSX"); self.open_single_button = QPushButton("Open in Single Analysis"); self.analyze_button = QPushButton("Analyze"); self.import_button.clicked.connect(self.import_file); self.template_button.clicked.connect(self.download_template); self.export_csv_button.clicked.connect(self.export_csv); self.export_xlsx_button.clicked.connect(self.export_xlsx); self.open_single_button.clicked.connect(self.open_in_single); self.send_mutation_button.clicked.connect(self.send_to_mutation); self.mutation_chain.currentTextChanged.connect(self.refresh_transfer_actions); self.analyze_button.clicked.connect(self.analyze); self.analyze_button.setEnabled(False); self.export_csv_button.setEnabled(False); self.export_xlsx_button.setEnabled(False); self.open_single_button.setEnabled(False); self.send_mutation_button.setEnabled(False); self.risk_filter.currentTextChanged.connect(self.refresh); self.search.textChanged.connect(self.refresh)
        self.summary = QLabel("Loaded: 0 | Success: 0 | Partial: 0 | Invalid: 0"); self.table = QTableWidget(0, len(self.COLUMNS)); self.table.setHorizontalHeaderLabels(self.COLUMNS); self.table.itemSelectionChanged.connect(self.show_detail)
        self.detail = QLabel("Select an antibody to inspect details."); self.detail_table = QTableWidget(0, 5); self.detail_table.setHorizontalHeaderLabels(["Chain", "Position", "Motif", "Category", "Region"])
        top = QHBoxLayout(); top.addWidget(self.import_button); top.addWidget(self.template_button); top.addWidget(self.analyze_button); top.addWidget(self.export_csv_button); top.addWidget(self.export_xlsx_button); top.addWidget(self.open_single_button); top.addWidget(self.mutation_chain); top.addWidget(self.send_mutation_button); top.addWidget(self.source); top.addStretch(); filters = QFormLayout(); filters.addRow("Risk Level", self.risk_filter); filters.addRow("Search", self.search); layout = QVBoxLayout(self); layout.addLayout(top); layout.addWidget(self.summary); layout.addLayout(filters); layout.addWidget(self.table); layout.addWidget(self.detail); layout.addWidget(self.detail_table)

    def import_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import antibody file", "", "Antibody files (*.csv *.xlsx *.fasta *.fa *.faa)")
        if path: self.set_source(path)

    def set_source(self, path): self._path = str(path); self.source.setText(Path(path).name); self.analyze_button.setEnabled(True)
    def download_template(self):
        path, _ = QFileDialog.getSaveFileName(self, "Download template", "antibody_batch_template.xlsx", "Excel files (*.xlsx)")
        if path: write_template(path); self.summary.setText(f"Template saved: {Path(path).name}")
    def _result_path(self, caption, default, filter_text): return QFileDialog.getSaveFileName(self, caption, default, filter_text)[0]
    def export_csv(self):
        if self.records:
            path = self._result_path("Export CSV", "antibody_batch_results.csv", "CSV files (*.csv)")
            if path: write_summary_csv(self._result, path); self.summary.setText(f"CSV saved: {Path(path).name}")
    def export_xlsx(self):
        if self.records:
            path = self._result_path("Export XLSX", "antibody_batch_results.xlsx", "Excel files (*.xlsx)")
            if path: write_summary_xlsx(self._result, path); self.summary.setText(f"XLSX saved: {Path(path).name}")
    def open_in_single(self):
        row = self.table.currentRow()
        record = self._selected_record(row)
        chain = self.get_preferred_transfer_chain(record)
        if record and chain and self._open_single:
            sequence = getattr(record, f"{chain.lower()}_sequence")
            self._open_single(record.antibody_id, sequence)

    def is_chain_transferable(self, record, chain):
        if record is None or chain not in {"VH", "VL"}: return False
        sequence = getattr(record, f"{chain.lower()}_sequence", "")
        return validate_sequence(sequence, allow_empty=False)[0]

    def get_preferred_transfer_chain(self, record):
        for chain in ("VH", "VL"):
            if self.is_chain_transferable(record, chain): return chain
        return None

    def refresh_transfer_actions(self):
        record = self._selected_record(self.table.currentRow())
        preferred = self.get_preferred_transfer_chain(record)
        selected = self.mutation_chain.currentText()
        self.open_single_button.setEnabled(bool(preferred and self._open_single))
        self.send_mutation_button.setEnabled(bool(self.is_chain_transferable(record, selected) and self._open_mutation))
    def send_to_mutation(self):
        record = self._selected_record(self.table.currentRow())
        if not record or not self._open_mutation: return
        chain = self.mutation_chain.currentText(); sequence = getattr(record, f"{chain.lower()}_sequence") if self.is_chain_transferable(record, chain) else ""
        if sequence: self._open_mutation(record.antibody_id, sequence, chain)
    def _selected_record(self, row):
        if row < 0 or row >= self.table.rowCount(): return None
        return next((r for r in self.records if r.antibody_id == self.table.item(row, 0).text()), None)
    def analyze(self):
        if not getattr(self, "_path", None) or self._active_worker: return
        mapping, chain = self._resolve_input()
        if mapping is False or chain is False: return
        self.import_button.setEnabled(False); self.analyze_button.setEnabled(False); self.summary.setText("Analyzing…")
        worker = Worker(analyze_file, self._path, mapping, chain); self._active_worker = worker; worker.signals.finished.connect(self._done); worker.signals.error.connect(self._error); self.pool.start(worker)

    def _resolve_input(self):
        path = Path(self._path); mapping = input_mapping(path)
        if path.suffix.lower() in {".csv", ".xlsx"} and mapping is None:
            frame = pd.read_csv(path, nrows=100) if path.suffix.lower() == ".csv" else pd.read_excel(path, nrows=100)
            suggested_mapping, _ = infer_smart_mapping(frame)
            dialog = ColumnMappingDialog(frame.columns, self, suggested_mapping)
            return (dialog.mapping(), None) if dialog.exec() else (False, None)
        if fasta_requires_chain(path):
            choice, ok = QInputDialog.getItem(self, "FASTA chain selection", "Sequences without chain labels should be treated as:", ["VH", "VL"], 0, False)
            return (None, choice) if ok else (None, False)
        return mapping, None
    def _done(self, result: BatchResult):
        self._active_worker = None; self.import_button.setEnabled(True); self.analyze_button.setEnabled(True); self._result = result; self.records = result.records; self.export_csv_button.setEnabled(True); self.export_xlsx_button.setEnabled(True); self.summary.setText(f"Loaded: {result.loaded} | Success: {result.success} | Partial: {result.partial} | Invalid: {result.invalid}"); self.refresh()
    def _error(self, message): self._active_worker = None; self.import_button.setEnabled(True); self.analyze_button.setEnabled(True); self.summary.setText(sanitize_error(message))
    def refresh(self):
        needle = self.search.text().lower(); level = self.risk_filter.currentText().lower(); rows = [r for r in self.records if (not needle or needle in r.antibody_id.lower()) and (level == "all" or r.risk_level.lower().startswith(level))]; self.table.setRowCount(0)
        for r in rows:
            row = self.table.rowCount(); self.table.insertRow(row); values = [r.antibody_id, r.vh_length, r.vl_length, "N/A" if r.risk_score != r.risk_score else f"{r.risk_score:.2f}", r.risk_level, r.total_sites, r.cdr_sites, r.ptm_sites, r.liability_sites, r.status]
            for col, value in enumerate(values): self.table.setItem(row, col, QTableWidgetItem(str(value)))
    def show_detail(self):
        row = self.table.currentRow()
        if row < 0 or row >= self.table.rowCount(): return
        record = next((r for r in self.records if r.antibody_id == self.table.item(row, 0).text()), None)
        if not record: return
        self.refresh_transfer_actions()
        categories = {category: sum(risk.category == category for _, risk in record.risks) for category in ("脱酰胺", "异构化", "氧化", "N-糖基化", "O-糖基化")}
        category_text = " | ".join(f"{category}: {count}" for category, count in categories.items())
        self.detail.setText(f"{record.antibody_id} | VH {record.vh_length} | VL {record.vl_length} | Score {record.risk_score} | {record.risk_level} | {record.status}\nCategories: {category_text}\nWarnings: {'; '.join(record.warnings) or 'None'}")
        self.detail_table.setRowCount(0)
        for chain, risk in record.risks:
            rr = self.detail_table.rowCount(); self.detail_table.insertRow(rr); values = [chain, risk.position, risk.motif, risk.category, risk.region]
            for col, value in enumerate(values): self.detail_table.setItem(rr, col, QTableWidgetItem(str(value)))
