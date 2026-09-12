from __future__ import annotations

from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import QComboBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from desktop.mutation_adapter import MutationComparison, compare_mutation
from desktop.literature_context import mutation_risk_context
from desktop.workers import Worker, sanitize_error


class MutationPage(QWidget):
    RISK_COLUMNS = ["Chain", "Position", "Motif", "Category", "Region"]
    CANDIDATE_COLUMNS = ["Mutation", "Chain", "Original Score", "Mutant Score", "ΔScore", "Removed Sites", "Added Sites"]

    def __init__(self, parent=None, open_literature=None):
        super().__init__(parent)
        self.pool = QThreadPool.globalInstance(); self._worker = None; self._comparison = None; self._candidates = []; self._open_literature = open_literature
        self.antibody_id = QLineEdit(); self.chain = QComboBox(); self.chain.addItems(["VH", "VL", "Unspecified"])
        self.sequence = QPlainTextEdit(); self.sequence.setPlaceholderText("Paste one VH or VL sequence")
        self.mutation = QLineEdit(); self.mutation.setPlaceholderText("N55Q")
        self.simulate_button = QPushButton("Simulate Mutation"); self.clear_button = QPushButton("Clear"); self.add_candidate_button = QPushButton("Add Candidate")
        self.simulate_button.clicked.connect(self.simulate); self.clear_button.clicked.connect(self.clear); self.add_candidate_button.clicked.connect(self.add_candidate)
        self.sequence.textChanged.connect(self._baseline_edited); self.antibody_id.textChanged.connect(self._baseline_edited); self.chain.currentTextChanged.connect(self._baseline_edited)
        self.message = QLabel(); self.warning = QLabel("This is rule-based in-silico mutation simulation. Score/risk changes do not demonstrate preserved binding, affinity, structure, expression, developability, or experimental success.")
        self.original_summary = QLabel("Length: - | Calculated Score: - | Risk Level: - | Total Sites: - | CDR Sites: -")
        self.mutant_summary = QLabel("Mutation: - | Length: - | Calculated Score: - | Risk Level: - | Total Sites: - | CDR Sites: -")
        self.comparison = QLabel("Calculated Score: - → - (Δ -) | Total Sites: - → - (Δ -) | CDR Sites: - → - (Δ -)")
        self.removed_table = self._risk_table(); self.added_table = self._risk_table(); self.unchanged_table = self._risk_table()
        self.find_removed_button = QPushButton("Find Evidence for Removed Risk"); self.find_added_button = QPushButton("Find Evidence for Added Risk"); self.find_removed_button.setEnabled(False); self.find_added_button.setEnabled(False)
        self.removed_table.itemSelectionChanged.connect(lambda: self._risk_table_selected(self.removed_table, self.find_removed_button)); self.added_table.itemSelectionChanged.connect(lambda: self._risk_table_selected(self.added_table, self.find_added_button)); self.find_removed_button.clicked.connect(lambda: self.find_literature(self.removed_table, "removed")); self.find_added_button.clicked.connect(lambda: self.find_literature(self.added_table, "added"))
        self.candidates = QTableWidget(0, len(self.CANDIDATE_COLUMNS)); self.candidates.setHorizontalHeaderLabels(self.CANDIDATE_COLUMNS)
        form = QFormLayout(); form.addRow("Antibody ID", self.antibody_id); form.addRow("Chain", self.chain); form.addRow("Sequence", self.sequence); form.addRow("Mutation", self.mutation)
        buttons = QHBoxLayout(); buttons.addWidget(self.simulate_button); buttons.addWidget(self.clear_button); buttons.addWidget(self.add_candidate_button)
        layout = QVBoxLayout(self); layout.addLayout(form); layout.addLayout(buttons); layout.addWidget(self.message); layout.addWidget(QLabel("Original")); layout.addWidget(self.original_summary); layout.addWidget(QLabel("Mutant")); layout.addWidget(self.mutant_summary); layout.addWidget(QLabel("Comparison")); layout.addWidget(self.comparison); layout.addWidget(self.warning); layout.addWidget(QLabel("Removed Risks")); layout.addWidget(self.removed_table); layout.addWidget(self.find_removed_button); layout.addWidget(QLabel("Added Risks")); layout.addWidget(self.added_table); layout.addWidget(self.find_added_button); layout.addWidget(QLabel("Unchanged Risks")); layout.addWidget(self.unchanged_table); layout.addWidget(QLabel("Candidates")); layout.addWidget(self.candidates)
        self._set_result_controls(False)

    def _risk_table(self):
        table = QTableWidget(0, len(self.RISK_COLUMNS)); table.setHorizontalHeaderLabels(self.RISK_COLUMNS); return table

    def _set_result_controls(self, enabled):
        self.add_candidate_button.setEnabled(enabled); self.simulate_button.setEnabled(not bool(self._worker))

    def load_sequence(self, antibody_id, sequence, chain="Unspecified"):
        self._worker = None; self._comparison = None; self._candidates.clear(); self.candidates.setRowCount(0)
        self.antibody_id.blockSignals(True); self.sequence.blockSignals(True); self.chain.blockSignals(True)
        self.antibody_id.setText(str(antibody_id or "")); self.sequence.setPlainText(str(sequence or "")); self.chain.setCurrentText(chain if chain in {"VH", "VL", "Unspecified"} else "Unspecified")
        self.antibody_id.blockSignals(False); self.sequence.blockSignals(False); self.chain.blockSignals(False); self._reset_results(); self.simulate_button.setEnabled(True)

    def _baseline_edited(self):
        if self._worker is None:
            self._comparison = None; self._candidates.clear(); self.candidates.setRowCount(0); self._reset_results()

    def _reset_results(self):
        self.original_summary.setText("Length: - | Calculated Score: - | Risk Level: - | Total Sites: - | CDR Sites: -")
        self.mutant_summary.setText("Mutation: - | Length: - | Calculated Score: - | Risk Level: - | Total Sites: - | CDR Sites: -")
        self.comparison.setText("Calculated Score: - → - (Δ -) | Total Sites: - → - (Δ -) | CDR Sites: - → - (Δ -)")
        self.message.clear(); self._set_result_controls(False)
        self.find_removed_button.setEnabled(False); self.find_added_button.setEnabled(False)
        for table in (self.removed_table, self.added_table, self.unchanged_table): table.setRowCount(0)

    def simulate(self):
        if self._worker: return
        self.message.clear(); self.simulate_button.setEnabled(False)
        mutation = self.mutation.text().strip().upper()
        self.mutation.setText(mutation)
        self._worker = Worker(compare_mutation, self.sequence.toPlainText(), mutation, self.antibody_id.text(), self.chain.currentText())
        self._worker.signals.finished.connect(self._done); self._worker.signals.error.connect(self._error); self.pool.start(self._worker)

    def _done(self, result: MutationComparison):
        self._worker = None; self._comparison = result; self.simulate_button.setEnabled(True); self._render(result); self.add_candidate_button.setEnabled(True)

    def _error(self, message):
        self._worker = None; self.simulate_button.setEnabled(True); self._comparison = None; self.add_candidate_button.setEnabled(False); self.message.setText(sanitize_error(message))

    def _render(self, result):
        self.original_summary.setText(f"Length: {len(result.original_sequence)} | Calculated Score: {result.original_score:.2f} | Risk Level: {result.original_level} | Total Sites: {result.original_total_sites} | CDR Sites: {result.original_cdr_sites}")
        self.mutant_summary.setText(f"Mutation: {result.mutation} | Length: {len(result.mutant_sequence)} | Calculated Score: {result.mutant_score:.2f} | Risk Level: {result.mutant_level} | Total Sites: {result.mutant_total_sites} | CDR Sites: {result.mutant_cdr_sites}")
        self.comparison.setText(f"Calculated Score: {result.original_score:.2f} → {result.mutant_score:.2f} (Δ {result.delta_score:+.2f}) | Total Sites: {result.original_total_sites} → {result.mutant_total_sites} (Δ {result.delta_total_sites:+d}) | CDR Sites: {result.original_cdr_sites} → {result.mutant_cdr_sites} (Δ {result.delta_cdr_sites:+d})")
        self._fill_risks(self.removed_table, result.removed_risks); self._fill_risks(self.added_table, result.added_risks); self._fill_risks(self.unchanged_table, result.unchanged_risks)

    def _fill_risks(self, table, risks):
        table.setRowCount(0)
        for risk in risks:
            row = table.rowCount(); table.insertRow(row)
            for col, value in enumerate((risk.chain, risk.position, risk.motif, risk.category, risk.region)): table.setItem(row, col, QTableWidgetItem(str(value)))
            table.item(row, 0).setData(32, risk)

    def _risk_table_selected(self, table, button):
        button.setEnabled(bool(self._open_literature and table.currentRow() >= 0))

    def find_literature(self, table, change_type):
        item = table.item(table.currentRow(), 0) if table.currentRow() >= 0 else None
        risk = item.data(32) if item else None
        if risk and self._open_literature and self._comparison:
            self._open_literature(mutation_risk_context(self._comparison.mutation, risk, change_type, risk.chain))

    def add_candidate(self):
        if not self._comparison: return
        if any(candidate.mutation == self._comparison.mutation and candidate.chain == self._comparison.chain for candidate in self._candidates): return
        self._candidates.append(self._comparison); row = self.candidates.rowCount(); self.candidates.insertRow(row); result = self._comparison
        values = [result.mutation, result.chain, f"{result.original_score:.2f}", f"{result.mutant_score:.2f}", f"{result.delta_score:+.2f}", len(result.removed_risks), len(result.added_risks)]
        for col, value in enumerate(values): self.candidates.setItem(row, col, QTableWidgetItem(str(value)))

    def clear(self):
        self.load_sequence("", "", "Unspecified"); self.mutation.clear()
