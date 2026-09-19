from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget, QPlainTextEdit

from core import analyze_sequence, normalize_sequence, validate_sequence
from scoring import compute_risk_score
from desktop.literature_context import single_risk_context
from desktop.ml_adapter import DesktopMLService, STATUS_READY, status_code, status_message
from desktop.ml_metadata import BENCHMARK_ID, BENCHMARK_SCOPE, DEVELOPABILITY_MODEL_ID, ESM_MODEL_NAME, ESM_MODEL_REVISION, HIC_MODEL_ID, LIMITATION, LOCAL_INFERENCE_NOTICE, NO_CATEGORICAL_DECISION_NOTICE, RESEARCH_SUPPORT_NOTICE, evidence_text
from desktop.workers import Worker, sanitize_error


class SingleAnalysisPage(QWidget):
    def __init__(self, parent=None, open_mutation=None, open_literature=None, ml_service=None):
        super().__init__(parent)
        self._open_mutation = open_mutation
        self._open_literature = open_literature
        self._ml_service = ml_service or DesktopMLService()
        self._ml_pool = QThreadPool.globalInstance()
        self._ml_worker = None
        self._ml_generation = 0
        self._ml_snapshot = None
        self._last_ml_status = {}
        self.ml_provenance = None
        self._analysis_ready = False
        self.antibody_id = QLineEdit()
        self.sequence = QPlainTextEdit()
        self.sequence.setPlaceholderText("粘贴 VH 或 VL 氨基酸序列")
        self.vh_sequence = self.sequence
        self.vl_sequence = QPlainTextEdit()
        self.vl_sequence.setPlaceholderText("粘贴 VL 氨基酸序列（实验性 ML 估计需要 VH + VL）")
        self.length = QLabel("-")
        self.score = QLabel("-")
        self.level = QLabel("-")
        self.message = QLabel()
        self.analyze_button = QPushButton("Analyze")
        self.clear_button = QPushButton("Clear")
        self.send_mutation_button = QPushButton("Send to Mutation")
        self.find_literature_button = QPushButton("Find Literature")
        self.find_literature_button.setEnabled(False)
        self._build_ml_section()
        self.analyze_button.clicked.connect(self.analyze)
        self.clear_button.clicked.connect(self.clear)
        self.send_mutation_button.clicked.connect(self.send_to_mutation)
        self.find_literature_button.clicked.connect(self.find_literature)
        self.ml_run_button.clicked.connect(self.run_ml_estimates)
        self.ml_details_button.clicked.connect(lambda: self.ml_details.setVisible(not self.ml_details.isVisible()))
        self.sequence.textChanged.connect(self._input_changed)
        self.vl_sequence.textChanged.connect(self._input_changed)
        form = QFormLayout(); form.addRow("Antibody ID", self.antibody_id); form.addRow("VH Sequence", self.sequence); form.addRow("VL Sequence", self.vl_sequence)
        buttons = QHBoxLayout(); buttons.addWidget(self.analyze_button); buttons.addWidget(self.clear_button); buttons.addWidget(self.send_mutation_button); buttons.addWidget(self.find_literature_button); buttons.addStretch()
        summary = QFormLayout(); summary.addRow("Sequence length", self.length); summary.addRow("Risk Score", self.score); summary.addRow("Risk Level", self.level)
        self.table = QTableWidget(0, 4); self.table.setHorizontalHeaderLabels(["Position", "Motif", "Category", "Region"])
        self.table.itemSelectionChanged.connect(self._risk_selected)
        layout = QVBoxLayout(self); layout.addLayout(form); layout.addLayout(buttons); layout.addWidget(self.message); layout.addLayout(summary); layout.addWidget(self.table); layout.addWidget(self.ml_section)
        self._update_ml_controls()

    def _build_ml_section(self):
        self.ml_section = QGroupBox("Experimental ML Estimates")
        self.ml_status = QLabel()
        self.ml_status.setWordWrap(True)
        self.ml_local_notice = QLabel(LOCAL_INFERENCE_NOTICE)
        self.ml_local_notice.setWordWrap(True)
        self.ml_hic_value = QLabel("-")
        self.ml_probability_value = QLabel("-")
        self.ml_probability_value.setToolTip(
            "P(NOT_DEVELOPABLE) is the model probability for the benchmark-defined "
            "NOT_DEVELOPABLE class. It is not a clinical failure probability."
        )
        self.ml_hic = self.ml_hic_value
        self.ml_probability = self.ml_probability_value
        self.ml_not_developable_probability = self.ml_probability_value
        self.ml_run_button = QPushButton("Run Experimental ML Estimates")
        self.ml_button = self.ml_run_button
        self.ml_details_button = QPushButton("Details")
        self.ml_details_button.setEnabled(False)
        self.ml_details = QPlainTextEdit()
        self.ml_details.setReadOnly(True)
        self.ml_details.setVisible(False)
        form = QFormLayout()
        form.addRow("HIC estimate", self.ml_hic_value)
        form.addRow("NOT_DEVELOPABLE probability", self.ml_probability_value)
        actions = QHBoxLayout()
        actions.addWidget(self.ml_run_button)
        actions.addWidget(self.ml_details_button)
        actions.addStretch()
        layout = QVBoxLayout(self.ml_section)
        layout.addWidget(QLabel("Local research-support estimates derived from frozen sequence ML models."))
        layout.addWidget(QLabel("Model estimate based on sequence representation. No categorical decision threshold is defined."))
        layout.addWidget(QLabel("Models: HIC ESM2 + Ridge · Composite ESM2 + Logistic Regression"))
        layout.addWidget(QLabel("Internal benchmark: " + evidence_text("hic") + " " + evidence_text("developability")))
        layout.addLayout(form)
        layout.addWidget(self.ml_status)
        layout.addWidget(self.ml_local_notice)
        layout.addWidget(QLabel(RESEARCH_SUPPORT_NOTICE))
        layout.addLayout(actions)
        layout.addWidget(self.ml_details)

    @staticmethod
    def _valid_chain(value: str) -> tuple[bool, str]:
        sequence = normalize_sequence(value)
        if not sequence:
            return False, "empty"
        valid, error = validate_sequence(sequence)
        return bool(valid), str(error or "invalid")

    def _current_chains(self):
        return normalize_sequence(self.sequence.toPlainText()), normalize_sequence(self.vl_sequence.toPlainText())

    def _input_changed(self):
        self._analysis_ready = False
        self._ml_generation += 1
        self._ml_snapshot = None
        self._clear_ml_output()
        self.find_literature_button.setEnabled(False)
        self._update_ml_controls()

    def _clear_ml_output(self):
        self.ml_hic_value.setText("-")
        self.ml_probability_value.setText("-")
        self.ml_details.clear()
        self.ml_details.setVisible(False)
        self.ml_details_button.setEnabled(False)
        self.ml_status.setText(self._ml_requirement_message())

    def _ml_requirement_message(self):
        vh_valid, _ = self._valid_chain(self.sequence.toPlainText())
        vl_valid, _ = self._valid_chain(self.vl_sequence.toPlainText())
        if not vh_valid or not vl_valid:
            return "Both VH and VL are required for experimental ML estimates."
        if not self._analysis_ready:
            return "Analyze the current VH and VL before running experimental ML estimates."
        return "Ready for explicit local ML inference."

    def _update_ml_controls(self):
        if self._ml_worker is not None:
            self.ml_run_button.setEnabled(False)
            self.ml_status.setText("Loading local sequence model… Generating research-support estimates…")
            return
        vh_valid, _ = self._valid_chain(self.sequence.toPlainText())
        vl_valid, _ = self._valid_chain(self.vl_sequence.toPlainText())
        enabled = bool(self._analysis_ready and vh_valid and vl_valid)
        self.ml_run_button.setEnabled(enabled)
        if not enabled and not self.ml_details_button.isEnabled():
            self.ml_status.setText(self._ml_requirement_message())

    def analyze(self):
        self._analysis_ready = False
        self._ml_generation += 1
        self._ml_snapshot = None
        self._clear_ml_output()
        result = analyze_sequence(self.sequence.toPlainText(), 31, 35, 50, 65, 99, 110)
        self.table.setRowCount(0); self.length.setText(str(result.sequence_length) if not result.errors else "-")
        if result.errors:
            self.score.setText("-"); self.level.setText("-"); self.message.setText("错误：" + "; ".join(result.errors)); self.send_mutation_button.setEnabled(False); self._update_ml_controls(); return
        risk = compute_risk_score([(self.antibody_id.text() or "sequence", result)])
        self.score.setText(f"{risk.overall_score:.2f}"); self.level.setText(risk.risk_level); self.message.setText(""); self.send_mutation_button.setEnabled(bool(self._open_mutation and result.sequence))
        for item in result.risks:
            row = self.table.rowCount(); self.table.insertRow(row)
            for col, value in enumerate((item.position, item.motif, item.category, item.region)):
                self.table.setItem(row, col, QTableWidgetItem(str(value)))
            self.table.item(row, 0).setData(32, item)
        self._analysis_ready = True
        self._risk_selected()
        self._update_ml_controls()

    def run_ml_estimates(self):
        if self._ml_worker is not None:
            return
        vh, vl = self._current_chains()
        if not self._analysis_ready or not self._valid_chain(vh)[0] or not self._valid_chain(vl)[0]:
            self._update_ml_controls()
            return
        try:
            status = self._ml_service.status()
        except Exception as error:
            self._show_ml_error(sanitize_error(str(error)))
            return
        if status_code(status) != STATUS_READY:
            self.ml_status.setText(status_message(status))
            self.ml_details.setPlainText(str(status.get("error", "")) if isinstance(status, dict) else "")
            self.ml_details_button.setEnabled(bool(self.ml_details.toPlainText()))
            return
        self._last_ml_status = dict(status) if isinstance(status, dict) else {}
        token = self._ml_generation
        self._ml_snapshot = (vh, vl)
        worker = Worker(self._ml_service.predict, vh, vl)
        self._ml_worker = worker
        worker.signals.finished.connect(lambda result, t=token, s=(vh, vl): self._ml_done(result, t, s))
        worker.signals.error.connect(lambda message, t=token: self._ml_error(message, t))
        self._update_ml_controls()
        self._ml_pool.start(worker)

    def _same_current_input(self, snapshot):
        return self._current_chains() == snapshot

    @staticmethod
    def _prediction_value(payload: Any, *keys: str):
        if isinstance(payload, dict):
            for key in keys:
                if key in payload:
                    return payload[key]
        return None

    @staticmethod
    def _short_sequence_hash(sequence: str) -> str:
        return hashlib.sha256(sequence.encode("utf-8")).hexdigest()[:16]

    def _ml_done(self, result, token, snapshot):
        self._ml_worker = None
        if token != self._ml_generation or not self._same_current_input(snapshot):
            self._update_ml_controls()
            return
        try:
            hic_payload = result.get("hic")
            composite_payload = result.get("developability")
            hic = self._prediction_value(hic_payload, "predicted_hic", "predicted_value")
            probability = self._prediction_value(composite_payload, "probability_not_developable")
            if hic is None or probability is None:
                raise ValueError("Local ML runtime returned incomplete task results")
            self.ml_hic_value.setText(f"{float(hic):.2f} min")
            self.ml_probability_value.setText(f"{float(probability):.2%}")
            self.ml_provenance = {
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "benchmark": (hic_payload or {}).get("benchmark", BENCHMARK_ID),
                "esm_model": ESM_MODEL_NAME,
                "esm_revision": ESM_MODEL_REVISION,
                "hic_model_id": (hic_payload or {}).get("model_id", HIC_MODEL_ID),
                "hic_model_version": (hic_payload or {}).get("model_version", "phase5-frozen-v1"),
                "developability_model_id": (composite_payload or {}).get("model_id", DEVELOPABILITY_MODEL_ID),
                "developability_model_version": (composite_payload or {}).get("model_version", "phase5-frozen-v1"),
                "vh_sha256_prefix": self._short_sequence_hash(snapshot[0]),
                "vl_sha256_prefix": self._short_sequence_hash(snapshot[1]),
                "device": self._last_ml_status.get("device", "unknown"),
            }
            self.ml_details.setPlainText(
                "HIC model: ESM2 + Ridge\n"
                f"HIC model ID: {self.ml_provenance['hic_model_id']} ({self.ml_provenance['hic_model_version']})\n"
                "HIC: " + evidence_text("hic") + "\n"
                "Composite model: ESM2 + Logistic Regression\n"
                f"Composite model ID: {self.ml_provenance['developability_model_id']} ({self.ml_provenance['developability_model_version']})\n"
                "Composite: " + evidence_text("developability") + "\n"
                f"Benchmark scope: {BENCHMARK_SCOPE}.\n"
                f"Benchmark: {self.ml_provenance['benchmark']}\n"
                f"ESM2: {ESM_MODEL_NAME}, revision {ESM_MODEL_REVISION}\n"
                f"Device: {self.ml_provenance['device']}\n"
                f"Run UTC: {self.ml_provenance['timestamp_utc']}\n"
                f"VH input hash prefix: {self.ml_provenance['vh_sha256_prefix']}\n"
                f"VL input hash prefix: {self.ml_provenance['vl_sha256_prefix']}\n"
                f"{LIMITATION}\n"
                f"{NO_CATEGORICAL_DECISION_NOTICE}\n"
                f"{RESEARCH_SUPPORT_NOTICE}"
            )
            self.ml_details_button.setEnabled(True)
            self.ml_status.setText("Local ML estimates complete. Experimental verification remains required.")
        except Exception as error:
            self._show_ml_error(str(error))
            return
        self._update_ml_controls()

    def _ml_error(self, message: str, token: int):
        self._ml_worker = None
        if token != self._ml_generation:
            self._update_ml_controls()
            return
        self._show_ml_error(message)

    def _show_ml_error(self, message: str):
        self.ml_status.setText("Local ML estimates failed. See Details for diagnostics.")
        self.ml_details.setPlainText(sanitize_error(message))
        self.ml_details_button.setEnabled(True)
        self._update_ml_controls()

    def _risk_selected(self):
        self.find_literature_button.setEnabled(bool(self._open_literature and self.table.currentRow() >= 0))

    def find_literature(self):
        item = self.table.item(self.table.currentRow(), 0) if self.table.currentRow() >= 0 else None
        risk = item.data(32) if item else None
        if risk and self._open_literature:
            self._open_literature(single_risk_context(risk))

    def set_input(self, antibody_id, sequence, analyze=True, vl_sequence=None):
        self.antibody_id.setText(str(antibody_id or ""))
        self.sequence.setPlainText(str(sequence or ""))
        self.vl_sequence.setPlainText(str(vl_sequence or ""))
        if analyze:
            self.analyze()
        else:
            self._update_ml_controls()

    def analyze_current_input(self):
        self.analyze()

    def clear(self):
        self.antibody_id.clear(); self.sequence.clear(); self.vl_sequence.clear(); self.length.setText("-"); self.score.setText("-"); self.level.setText("-"); self.message.clear(); self.table.setRowCount(0); self.send_mutation_button.setEnabled(False); self.find_literature_button.setEnabled(False)
        self._analysis_ready = False
        self._clear_ml_output()
        self._update_ml_controls()

    def send_to_mutation(self):
        if self._open_mutation and self.sequence.toPlainText().strip(): self._open_mutation(self.antibody_id.text(), self.sequence.toPlainText(), "Unspecified")
