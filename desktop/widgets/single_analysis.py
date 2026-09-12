from __future__ import annotations

from PySide6.QtWidgets import QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget, QPlainTextEdit

from core import analyze_sequence
from scoring import compute_risk_score
from desktop.literature_context import single_risk_context


class SingleAnalysisPage(QWidget):
    def __init__(self, parent=None, open_mutation=None, open_literature=None):
        super().__init__(parent)
        self.antibody_id = QLineEdit()
        self.sequence = QPlainTextEdit()
        self.sequence.setPlaceholderText("粘贴 VH 或 VL 氨基酸序列")
        self.length = QLabel("-")
        self.score = QLabel("-")
        self.level = QLabel("-")
        self.message = QLabel()
        analyze = QPushButton("Analyze")
        clear = QPushButton("Clear")
        self.send_mutation_button = QPushButton("Send to Mutation"); self._open_mutation = open_mutation; self.find_literature_button = QPushButton("Find Literature"); self._open_literature = open_literature; self.find_literature_button.setEnabled(False)
        analyze.clicked.connect(self.analyze)
        clear.clicked.connect(self.clear); self.send_mutation_button.clicked.connect(self.send_to_mutation); self.find_literature_button.clicked.connect(self.find_literature)
        form = QFormLayout(); form.addRow("Antibody ID", self.antibody_id); form.addRow("Sequence", self.sequence)
        buttons = QHBoxLayout(); buttons.addWidget(analyze); buttons.addWidget(clear); buttons.addWidget(self.send_mutation_button); buttons.addWidget(self.find_literature_button); buttons.addStretch()
        summary = QFormLayout(); summary.addRow("Sequence length", self.length); summary.addRow("Risk Score", self.score); summary.addRow("Risk Level", self.level)
        self.table = QTableWidget(0, 4); self.table.setHorizontalHeaderLabels(["Position", "Motif", "Category", "Region"])
        self.table.itemSelectionChanged.connect(self._risk_selected)
        layout = QVBoxLayout(self); layout.addLayout(form); layout.addLayout(buttons); layout.addWidget(self.message); layout.addLayout(summary); layout.addWidget(self.table)

    def analyze(self):
        result = analyze_sequence(self.sequence.toPlainText(), 31, 35, 50, 65, 99, 110)
        self.table.setRowCount(0); self.length.setText(str(result.sequence_length) if not result.errors else "-")
        if result.errors:
            self.score.setText("-"); self.level.setText("-"); self.message.setText("错误：" + "; ".join(result.errors)); return
        risk = compute_risk_score([(self.antibody_id.text() or "sequence", result)])
        self.score.setText(f"{risk.overall_score:.2f}"); self.level.setText(risk.risk_level); self.message.setText(""); self.send_mutation_button.setEnabled(bool(self._open_mutation and result.sequence))
        for item in result.risks:
            row = self.table.rowCount(); self.table.insertRow(row)
            for col, value in enumerate((item.position, item.motif, item.category, item.region)):
                self.table.setItem(row, col, QTableWidgetItem(str(value)))
            self.table.item(row, 0).setData(32, item)
        self._risk_selected()

    def _risk_selected(self):
        self.find_literature_button.setEnabled(bool(self._open_literature and self.table.currentRow() >= 0))

    def find_literature(self):
        item = self.table.item(self.table.currentRow(), 0) if self.table.currentRow() >= 0 else None
        risk = item.data(32) if item else None
        if risk and self._open_literature:
            self._open_literature(single_risk_context(risk))

    def set_input(self, antibody_id, sequence, analyze=True):
        self.antibody_id.setText(str(antibody_id or ""))
        self.sequence.setPlainText(str(sequence or ""))
        if analyze:
            self.analyze()

    def analyze_current_input(self):
        self.analyze()

    def clear(self):
        self.antibody_id.clear(); self.sequence.clear(); self.length.setText("-"); self.score.setText("-"); self.level.setText("-"); self.message.clear(); self.table.setRowCount(0); self.send_mutation_button.setEnabled(False); self.find_literature_button.setEnabled(False)

    def send_to_mutation(self):
        if self._open_mutation and self.sequence.toPlainText().strip(): self._open_mutation(self.antibody_id.text(), self.sequence.toPlainText(), "Unspecified")
