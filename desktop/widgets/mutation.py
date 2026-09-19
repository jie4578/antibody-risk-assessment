from __future__ import annotations

from datetime import datetime, timezone

from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import QComboBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from core import normalize_sequence, validate_sequence
from desktop.mutation_adapter import MutationComparison, compare_mutation
from desktop.literature_context import mutation_risk_context
from desktop.ml_adapter import DesktopMLService, STATUS_READY, build_mutation_pairs, compare_mutation_ml, sequence_hash, status_code, status_message
from desktop.ml_metadata import BENCHMARK_SCOPE, LIMITATION, NO_CATEGORICAL_DECISION_NOTICE, RESEARCH_SUPPORT_NOTICE, evidence_text
from desktop.workers import Worker, sanitize_error


class MutationPage(QWidget):
    RISK_COLUMNS = ["Chain", "Position", "Motif", "Category", "Region"]
    CANDIDATE_COLUMNS = ["Mutation", "Chain", "Original Score", "Mutant Score", "ΔScore", "Removed Sites", "Added Sites"]

    def __init__(self, parent=None, open_literature=None, ml_service=None):
        super().__init__(parent)
        self.pool = QThreadPool.globalInstance(); self._worker = None; self._ml_worker = None; self._comparison = None; self._selected_candidate = None; self._candidates = []; self._open_literature = open_literature; self._ml_service = ml_service or DesktopMLService(); self._ml_generation = 0; self._ml_snapshot = None; self.ml_provenance = None; self._last_ml_status = {}
        self.antibody_id = QLineEdit(); self.chain = QComboBox(); self.chain.addItems(["VH", "VL", "Unspecified"])
        self.sequence = QPlainTextEdit(); self.sequence.setPlaceholderText("Paste VH sequence"); self.vh_sequence = self.sequence; self.vl_sequence = QPlainTextEdit(); self.vl_sequence.setPlaceholderText("Paste VL sequence (required for ML comparison)")
        self.mutation = QLineEdit(); self.mutation.setPlaceholderText("N55Q")
        self.simulate_button = QPushButton("Simulate Mutation"); self.clear_button = QPushButton("Clear"); self.add_candidate_button = QPushButton("Add Candidate")
        self.simulate_button.clicked.connect(self.simulate); self.clear_button.clicked.connect(self.clear); self.add_candidate_button.clicked.connect(self.add_candidate)
        self.sequence.textChanged.connect(self._baseline_edited); self.vl_sequence.textChanged.connect(self._baseline_edited); self.antibody_id.textChanged.connect(self._baseline_edited); self.chain.currentTextChanged.connect(self._chain_changed); self.mutation.textChanged.connect(self._mutation_edited)
        self.message = QLabel(); self.warning = QLabel("This is rule-based in-silico mutation simulation. Score/risk changes do not demonstrate preserved binding, affinity, structure, expression, developability, or experimental success.")
        self.original_summary = QLabel("Length: - | Calculated Score: - | Risk Level: - | Total Sites: - | CDR Sites: -")
        self.mutant_summary = QLabel("Mutation: - | Length: - | Calculated Score: - | Risk Level: - | Total Sites: - | CDR Sites: -")
        self.comparison = QLabel("Calculated Score: - → - (Δ -) | Total Sites: - → - (Δ -) | CDR Sites: - → - (Δ -)")
        self.removed_table = self._risk_table(); self.added_table = self._risk_table(); self.unchanged_table = self._risk_table()
        self.find_removed_button = QPushButton("Find Evidence for Removed Risk"); self.find_added_button = QPushButton("Find Evidence for Added Risk"); self.find_removed_button.setEnabled(False); self.find_added_button.setEnabled(False)
        self.removed_table.itemSelectionChanged.connect(lambda: self._risk_table_selected(self.removed_table, self.find_removed_button)); self.added_table.itemSelectionChanged.connect(lambda: self._risk_table_selected(self.added_table, self.find_added_button)); self.find_removed_button.clicked.connect(lambda: self.find_literature(self.removed_table, "removed")); self.find_added_button.clicked.connect(lambda: self.find_literature(self.added_table, "added"))
        self.candidates = QTableWidget(0, len(self.CANDIDATE_COLUMNS)); self.candidates.setHorizontalHeaderLabels(self.CANDIDATE_COLUMNS)
        self.candidates.itemSelectionChanged.connect(self._candidate_selected)
        self._build_ml_section()
        form = QFormLayout(); form.addRow("Antibody ID", self.antibody_id); form.addRow("Chain", self.chain); form.addRow("VH Sequence", self.vh_sequence); form.addRow("VL Sequence", self.vl_sequence); form.addRow("Mutation", self.mutation)
        buttons = QHBoxLayout(); buttons.addWidget(self.simulate_button); buttons.addWidget(self.clear_button); buttons.addWidget(self.add_candidate_button)
        layout = QVBoxLayout(self); layout.addLayout(form); layout.addLayout(buttons); layout.addWidget(self.message); layout.addWidget(QLabel("Original")); layout.addWidget(self.original_summary); layout.addWidget(QLabel("Mutant")); layout.addWidget(self.mutant_summary); layout.addWidget(QLabel("Comparison")); layout.addWidget(self.comparison); layout.addWidget(self.warning); layout.addWidget(QLabel("Removed Risks")); layout.addWidget(self.removed_table); layout.addWidget(self.find_removed_button); layout.addWidget(QLabel("Added Risks")); layout.addWidget(self.added_table); layout.addWidget(self.find_added_button); layout.addWidget(QLabel("Unchanged Risks")); layout.addWidget(self.unchanged_table); layout.addWidget(self.ml_section); layout.addWidget(QLabel("Candidates")); layout.addWidget(self.candidates)
        self._set_result_controls(False); self._reset_ml_result()

    def _build_ml_section(self):
        self.ml_section = QGroupBox("Experimental ML Comparison")
        self.ml_status = QLabel("Both VH and VL are required for Experimental ML comparison.")
        self.ml_status.setWordWrap(True)
        self.ml_run_button = QPushButton("Run ML Comparison")
        self.ml_details_button = QPushButton("Model details")
        self.ml_details_button.setEnabled(False)
        self.ml_hic_baseline = QLabel("-"); self.ml_hic_mutant = QLabel("-"); self.ml_hic_delta = QLabel("-")
        self.ml_probability_baseline = QLabel("-"); self.ml_probability_mutant = QLabel("-"); self.ml_probability_delta = QLabel("-")
        self.ml_warning = QLabel("ML Δ values are model-estimated differences and are not validated experimental mutation-effect measurements.")
        self.ml_warning.setWordWrap(True); self.ml_warning.setVisible(False)
        self.ml_details = QPlainTextEdit(); self.ml_details.setReadOnly(True); self.ml_details.setVisible(False)
        self.ml_run_button.clicked.connect(self.run_ml_comparison)
        self.ml_details_button.clicked.connect(lambda: self.ml_details.setVisible(not self.ml_details.isVisible()))
        grid = QFormLayout()
        grid.addRow("", QLabel("Baseline | Mutant | Δ"))
        grid.addRow("HIC model estimate", self._ml_values_row(self.ml_hic_baseline, self.ml_hic_mutant, self.ml_hic_delta))
        grid.addRow("P(NOT_DEVELOPABLE)", self._ml_values_row(self.ml_probability_baseline, self.ml_probability_mutant, self.ml_probability_delta))
        actions = QHBoxLayout(); actions.addWidget(self.ml_run_button); actions.addWidget(self.ml_details_button); actions.addStretch()
        layout = QVBoxLayout(self.ml_section)
        layout.addLayout(grid); layout.addWidget(QLabel(RESEARCH_SUPPORT_NOTICE)); layout.addWidget(self.ml_status); layout.addWidget(self.ml_warning); layout.addLayout(actions); layout.addWidget(self.ml_details)

    @staticmethod
    def _ml_values_row(baseline, mutant, delta):
        row = QHBoxLayout(); row.addWidget(baseline); row.addWidget(QLabel(" | ")); row.addWidget(mutant); row.addWidget(QLabel(" | ")); row.addWidget(delta); row.addStretch()
        widget = QWidget(); widget.setLayout(row); return widget

    def _set_active_sequence_alias(self):
        self.sequence = self.vl_sequence if self.chain.currentText() == "VL" else self.vh_sequence

    def _chain_changed(self, _value):
        self._set_active_sequence_alias()
        self._baseline_edited()

    def _mutation_edited(self):
        self._invalidate_ml()

    def _active_comparison(self):
        return self._selected_candidate or self._comparison

    def _invalidate_ml(self):
        self._ml_generation += 1
        self._ml_snapshot = None
        self._reset_ml_result()

    def _reset_ml_result(self):
        for label in (self.ml_hic_baseline, self.ml_hic_mutant, self.ml_hic_delta, self.ml_probability_baseline, self.ml_probability_mutant, self.ml_probability_delta):
            label.setText("-")
        self.ml_warning.setVisible(False)
        self.ml_details.clear(); self.ml_details.setVisible(False); self.ml_details_button.setEnabled(False)
        self.ml_status.setText("Ready for explicit local ML comparison." if self._active_comparison() and self._valid_ml_pair_available() else "Both VH and VL are required for Experimental ML comparison.")
        self.ml_run_button.setEnabled(False if self._ml_worker else bool(self._active_comparison() and self._valid_ml_pair_available()))

    def _valid_ml_pair_available(self):
        if self.chain.currentText() not in {"VH", "VL"}:
            return False
        for value in (self.vh_sequence.toPlainText(), self.vl_sequence.toPlainText()):
            valid, _ = validate_sequence(normalize_sequence(value))
            if not valid:
                return False
        return True

    def _candidate_selected(self):
        row = self.candidates.currentRow()
        self._selected_candidate = self._candidates[row] if 0 <= row < len(self._candidates) else None
        self._invalidate_ml()

    @staticmethod
    def _format_delta(value, suffix):
        return f"{value:+.2f} {suffix}"

    def run_ml_comparison(self):
        if self._ml_worker is not None:
            return
        comparison = self._active_comparison()
        if not comparison:
            self.ml_status.setText("Run a valid rule-based mutation comparison before ML comparison.")
            return
        try:
            pairs = build_mutation_pairs(self.chain.currentText(), self.vh_sequence.toPlainText(), self.vl_sequence.toPlainText(), comparison.original_sequence, comparison.mutant_sequence)
        except ValueError as error:
            self.ml_status.setText(str(error))
            return
        try:
            status = self._ml_service.status()
        except Exception as error:
            self.ml_status.setText("Local ML comparison status unavailable. See Model details.")
            self.ml_details.setPlainText(sanitize_error(str(error))); self.ml_details_button.setEnabled(True)
            return
        if status_code(status) != STATUS_READY:
            self.ml_status.setText(status_message(status))
            self.ml_details.setPlainText(str(status.get("error", "")) if isinstance(status, dict) else "")
            self.ml_details_button.setEnabled(bool(self.ml_details.toPlainText()))
            return
        self._last_ml_status = dict(status) if isinstance(status, dict) else {}
        self._ml_snapshot = (sequence_hash(pairs[0]), sequence_hash(pairs[1]), sequence_hash(pairs[2]), sequence_hash(pairs[3]), comparison.mutation)
        token = self._ml_generation
        self.ml_run_button.setEnabled(False); self.ml_status.setText("Running local ML comparison…")
        self._ml_worker = Worker(compare_mutation_ml, self._ml_service, *pairs)
        self._ml_worker.signals.finished.connect(lambda result, t=token, s=self._ml_snapshot: self._ml_done(result, t, s))
        self._ml_worker.signals.error.connect(lambda message, t=token: self._ml_error(message, t))
        self.pool.start(self._ml_worker)

    def _current_ml_snapshot(self):
        comparison = self._active_comparison()
        if not comparison:
            return None
        try:
            pairs = build_mutation_pairs(self.chain.currentText(), self.vh_sequence.toPlainText(), self.vl_sequence.toPlainText(), comparison.original_sequence, comparison.mutant_sequence)
        except ValueError:
            return None
        return (sequence_hash(pairs[0]), sequence_hash(pairs[1]), sequence_hash(pairs[2]), sequence_hash(pairs[3]), comparison.mutation)

    def _ml_done(self, result, token, snapshot):
        self._ml_worker = None
        if token != self._ml_generation or snapshot != self._current_ml_snapshot():
            self._reset_ml_result(); return
        self._ml_comparison = result
        self.ml_hic_baseline.setText(f"{result.baseline_hic:.2f} min")
        self.ml_hic_mutant.setText(f"{result.mutant_hic:.2f} min")
        self.ml_hic_delta.setText(self._format_delta(result.delta_hic, "min"))
        self.ml_probability_baseline.setText(f"{result.baseline_probability:.1%}")
        self.ml_probability_mutant.setText(f"{result.mutant_probability:.1%}")
        self.ml_probability_delta.setText(f"{result.delta_probability * 100:+.1f} pp")
        self.ml_warning.setVisible(True)
        self.ml_provenance = dict(result.metadata)
        self.ml_provenance["timestamp_utc"] = datetime.now(timezone.utc).isoformat()
        self.ml_provenance["device"] = self._last_ml_status.get("device", "unknown")
        self.ml_details.setPlainText(
            "HIC: " + evidence_text("hic") + "\n"
            "Composite: " + evidence_text("developability") + "\n"
            f"Benchmark scope: {BENCHMARK_SCOPE}.\n{LIMITATION}\n"
            f"Model IDs: {self.ml_provenance['model_ids']}\n"
            f"Model version: {self.ml_provenance['model_version']}\n"
            f"Model manifest: {self.ml_provenance['model_manifest']}\n"
            f"Device: {self.ml_provenance['device']}\n"
            f"Run UTC: {self.ml_provenance['timestamp_utc']}\n"
            "The models were benchmarked on antibody-level experimental properties. "
            "Single-mutation effect-size accuracy has not been independently validated.\n"
            f"{NO_CATEGORICAL_DECISION_NOTICE}\n{RESEARCH_SUPPORT_NOTICE}"
        )
        self.ml_details_button.setEnabled(True); self.ml_status.setText("ML comparison complete; values are research-support model estimates."); self.ml_run_button.setEnabled(True)

    def _ml_error(self, message, token):
        self._ml_worker = None
        if token != self._ml_generation:
            self._reset_ml_result(); return
        self.ml_status.setText("ML comparison failed. Existing rule-based mutation results are preserved.")
        self.ml_details.setPlainText(sanitize_error(message)); self.ml_details_button.setEnabled(True); self.ml_run_button.setEnabled(True)

    def _risk_table(self):
        table = QTableWidget(0, len(self.RISK_COLUMNS)); table.setHorizontalHeaderLabels(self.RISK_COLUMNS); return table

    def _set_result_controls(self, enabled):
        self.add_candidate_button.setEnabled(enabled); self.simulate_button.setEnabled(not bool(self._worker))

    def load_sequence(self, antibody_id, sequence, chain="Unspecified", vh_sequence=None, vl_sequence=None):
        self._worker = None; self._comparison = None; self._selected_candidate = None; self._candidates.clear(); self.candidates.setRowCount(0)
        canonical_chain = chain if chain in {"VH", "VL", "Unspecified"} else "Unspecified"
        baseline_vh = sequence if vh_sequence is None and canonical_chain != "VL" else (vh_sequence or "")
        baseline_vl = sequence if vl_sequence is None and canonical_chain == "VL" else (vl_sequence or "")
        self.antibody_id.blockSignals(True); self.vh_sequence.blockSignals(True); self.vl_sequence.blockSignals(True); self.chain.blockSignals(True)
        self.antibody_id.setText(str(antibody_id or "")); self.vh_sequence.setPlainText(str(baseline_vh or "")); self.vl_sequence.setPlainText(str(baseline_vl or "")); self.chain.setCurrentText(canonical_chain); self._set_active_sequence_alias()
        self.antibody_id.blockSignals(False); self.vh_sequence.blockSignals(False); self.vl_sequence.blockSignals(False); self.chain.blockSignals(False); self._invalidate_ml(); self._reset_results(); self.simulate_button.setEnabled(True)

    def _baseline_edited(self):
        self._invalidate_ml()
        if self._worker is None:
            self._comparison = None; self._selected_candidate = None; self._candidates.clear(); self.candidates.setRowCount(0); self._reset_results()

    def _reset_results(self):
        self.original_summary.setText("Length: - | Calculated Score: - | Risk Level: - | Total Sites: - | CDR Sites: -")
        self.mutant_summary.setText("Mutation: - | Length: - | Calculated Score: - | Risk Level: - | Total Sites: - | CDR Sites: -")
        self.comparison.setText("Calculated Score: - → - (Δ -) | Total Sites: - → - (Δ -) | CDR Sites: - → - (Δ -)")
        self.message.clear(); self._set_result_controls(False)
        self._reset_ml_result()
        self.find_removed_button.setEnabled(False); self.find_added_button.setEnabled(False)
        for table in (self.removed_table, self.added_table, self.unchanged_table): table.setRowCount(0)

    def simulate(self):
        if self._worker: return
        self._invalidate_ml(); self._selected_candidate = None; self.message.clear(); self.simulate_button.setEnabled(False)
        mutation = self.mutation.text().strip().upper()
        self.mutation.setText(mutation)
        self._worker = Worker(compare_mutation, self.sequence.toPlainText(), mutation, self.antibody_id.text(), self.chain.currentText())
        self._worker.signals.finished.connect(self._done); self._worker.signals.error.connect(self._error); self.pool.start(self._worker)

    def _done(self, result: MutationComparison):
        self._worker = None; self._comparison = result; self._selected_candidate = None; self.simulate_button.setEnabled(True); self._render(result); self.add_candidate_button.setEnabled(True); self._reset_ml_result()

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
        self.candidates.selectRow(row); self._selected_candidate = result; self._invalidate_ml()

    def clear(self):
        self.load_sequence("", "", "Unspecified"); self.mutation.clear()
