from __future__ import annotations

from datetime import datetime, timezone

from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import QComboBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from core import CURRENT_RULE_VERSION, normalize_sequence, validate_sequence
from desktop.mutation_adapter import MutationComparison, compare_mutation
from desktop.literature_context import mutation_risk_context
from desktop.ml_adapter import DesktopMLService, STATUS_READY, build_mutation_pairs, compare_mutation_ml, sequence_hash, status_code, status_message
from desktop.ml_metadata import BENCHMARK_SCOPE, LIMITATION, NO_CATEGORICAL_DECISION_NOTICE, RESEARCH_SUPPORT_NOTICE, evidence_text
from desktop.workers import Worker, sanitize_error
from desktop.zh_cn import display_value, model_details_zh, notice_zh


class MutationPage(QWidget):
    RISK_COLUMNS = ["链", "位置", "基序", "类别", "区域"]
    CANDIDATE_COLUMNS = ["突变", "链", "基线分数", "突变体分数", "分数差 Δ", "移除位点数", "新增位点数"]

    def __init__(self, parent=None, open_literature=None, ml_service=None, on_state_changed=None):
        super().__init__(parent)
        self._on_state_changed = on_state_changed
        self._rule_generation = 0
        self.pool = QThreadPool.globalInstance(); self._worker = None; self._ml_worker = None; self._comparison = None; self._ml_comparison = None; self._selected_candidate = None; self._candidates = []; self._open_literature = open_literature; self._ml_service = ml_service or DesktopMLService(); self._ml_generation = 0; self._ml_snapshot = None; self.ml_provenance = None; self._last_ml_status = {}
        self.antibody_id = QLineEdit(); self.chain = QComboBox()
        for label, value in (("VH", "VH"), ("VL", "VL"), ("未指定", "Unspecified")):
            self.chain.addItem(label, value)
        self.sequence = QPlainTextEdit(); self.sequence.setPlaceholderText("粘贴 VH 序列"); self.vh_sequence = self.sequence; self.vl_sequence = QPlainTextEdit(); self.vl_sequence.setPlaceholderText("粘贴 VL 序列（ML 比较必需）")
        self.mutation = QLineEdit(); self.mutation.setPlaceholderText("N55Q")
        self.simulate_button = QPushButton("模拟突变"); self.clear_button = QPushButton("清空"); self.add_candidate_button = QPushButton("添加候选")
        self.simulate_button.clicked.connect(self.simulate); self.clear_button.clicked.connect(self.clear); self.add_candidate_button.clicked.connect(self.add_candidate)
        self.sequence.textChanged.connect(self._baseline_edited); self.vl_sequence.textChanged.connect(self._baseline_edited); self.antibody_id.textChanged.connect(self._baseline_edited); self.chain.currentTextChanged.connect(self._chain_changed); self.mutation.textChanged.connect(self._mutation_edited)
        self.message = QLabel(); self.warning = QLabel(f"科学规则版本：{CURRENT_RULE_VERSION}。这是基于规则的计算机突变模拟；分数或风险的变化不能证明结合、亲和力、结构、表达或可开发性得到保留，也不能证明实验成功。")
        self.warning.setWordWrap(True)
        self.original_summary = QLabel("长度：- | 规则计算分数：- | 规则风险等级：- | 总位点数：- | CDR 位点数：-")
        self.mutant_summary = QLabel("突变：- | 长度：- | 规则计算分数：- | 规则风险等级：- | 总位点数：- | CDR 位点数：-")
        self.comparison = QLabel("规则计算分数：- → - (Δ -) | 总位点数：- → - (Δ -) | CDR 位点数：- → - (Δ -)")
        for label in (self.original_summary, self.mutant_summary, self.comparison):
            label.setWordWrap(True)
        self.removed_table = self._risk_table(); self.added_table = self._risk_table(); self.unchanged_table = self._risk_table()
        self.find_removed_button = QPushButton("查找已移除风险的文献"); self.find_added_button = QPushButton("查找新增风险的文献"); self.find_removed_button.setEnabled(False); self.find_added_button.setEnabled(False)
        self.removed_table.itemSelectionChanged.connect(lambda: self._risk_table_selected(self.removed_table, self.find_removed_button)); self.added_table.itemSelectionChanged.connect(lambda: self._risk_table_selected(self.added_table, self.find_added_button)); self.find_removed_button.clicked.connect(lambda: self.find_literature(self.removed_table, "removed")); self.find_added_button.clicked.connect(lambda: self.find_literature(self.added_table, "added"))
        self.candidates = QTableWidget(0, len(self.CANDIDATE_COLUMNS)); self.candidates.setHorizontalHeaderLabels(self.CANDIDATE_COLUMNS)
        self.candidates.itemSelectionChanged.connect(self._candidate_selected)
        self._build_ml_section()
        form = QFormLayout(); form.addRow("抗体 ID", self.antibody_id); form.addRow("链", self.chain); form.addRow("VH 序列", self.vh_sequence); form.addRow("VL 序列", self.vl_sequence); form.addRow("突变", self.mutation)
        buttons = QHBoxLayout(); buttons.addWidget(self.simulate_button); buttons.addWidget(self.clear_button); buttons.addWidget(self.add_candidate_button)
        layout = QVBoxLayout(self); layout.addLayout(form); layout.addLayout(buttons); layout.addWidget(self.message); layout.addWidget(QLabel("基线")); layout.addWidget(self.original_summary); layout.addWidget(QLabel("突变体")); layout.addWidget(self.mutant_summary); layout.addWidget(QLabel("比较")); layout.addWidget(self.comparison); layout.addWidget(self.warning); layout.addWidget(QLabel("已移除风险")); layout.addWidget(self.removed_table); layout.addWidget(self.find_removed_button); layout.addWidget(QLabel("新增风险")); layout.addWidget(self.added_table); layout.addWidget(self.find_added_button); layout.addWidget(QLabel("未变化风险")); layout.addWidget(self.unchanged_table); layout.addWidget(self.ml_section); layout.addWidget(QLabel("候选列表")); layout.addWidget(self.candidates)
        self._set_result_controls(False); self._reset_ml_result()

    def _build_ml_section(self):
        self.ml_section = QGroupBox("实验性 ML 比较")
        self.ml_status = QLabel("实验性 ML 比较需要同时提供 VH 和 VL 序列。")
        self.ml_status.setWordWrap(True)
        self.ml_run_button = QPushButton("运行 ML 比较")
        self.ml_details_button = QPushButton("模型详情")
        self.ml_details_button.setEnabled(False)
        self.ml_hic_baseline = QLabel("-"); self.ml_hic_mutant = QLabel("-"); self.ml_hic_delta = QLabel("-")
        self.ml_probability_baseline = QLabel("-"); self.ml_probability_mutant = QLabel("-"); self.ml_probability_delta = QLabel("-")
        self.ml_warning = QLabel("ML 差值仅是模型估计值之差，不是经过实验验证的突变效应测量。")
        self.ml_warning.setWordWrap(True); self.ml_warning.setVisible(False)
        self.ml_details = QPlainTextEdit(); self.ml_details.setReadOnly(True); self.ml_details.setVisible(False)
        self.ml_run_button.clicked.connect(self.run_ml_comparison)
        self.ml_details_button.clicked.connect(lambda: self.ml_details.setVisible(not self.ml_details.isVisible()))
        grid = QFormLayout()
        grid.addRow("", QLabel("基线 | 突变体 | 差值 Δ"))
        grid.addRow("HIC 模型估计值", self._ml_values_row(self.ml_hic_baseline, self.ml_hic_mutant, self.ml_hic_delta))
        grid.addRow("不可开发类别概率 P(NOT_DEVELOPABLE)", self._ml_values_row(self.ml_probability_baseline, self.ml_probability_mutant, self.ml_probability_delta))
        actions = QHBoxLayout(); actions.addWidget(self.ml_run_button); actions.addWidget(self.ml_details_button); actions.addStretch()
        layout = QVBoxLayout(self.ml_section)
        layout.addLayout(grid); layout.addWidget(QLabel(notice_zh(RESEARCH_SUPPORT_NOTICE))); layout.addWidget(self.ml_status); layout.addWidget(self.ml_warning); layout.addLayout(actions); layout.addWidget(self.ml_details)

    @staticmethod
    def _ml_values_row(baseline, mutant, delta):
        row = QHBoxLayout(); row.addWidget(baseline); row.addWidget(QLabel(" | ")); row.addWidget(mutant); row.addWidget(QLabel(" | ")); row.addWidget(delta); row.addStretch()
        widget = QWidget(); widget.setLayout(row); return widget

    def _set_active_sequence_alias(self):
        self.sequence = self.vl_sequence if self.chain.currentData() == "VL" else self.vh_sequence

    def _chain_changed(self, _value):
        self._set_active_sequence_alias()
        self._baseline_edited()

    def _mutation_edited(self):
        self._rule_generation += 1
        self._comparison = None
        self._selected_candidate = None
        self._reset_results()
        self._invalidate_ml()

    def _rule_input_snapshot(self):
        return (self.antibody_id.text().strip(), self.chain.currentData(),
                normalize_sequence(self.vh_sequence.toPlainText()),
                normalize_sequence(self.vl_sequence.toPlainText()),
                self.mutation.text().strip().upper())

    def _rule_finished(self, worker, token, snapshot, result=None, error=None):
        if self._worker is worker:
            self._worker = None
            self.simulate_button.setEnabled(True)
        if token != self._rule_generation or snapshot != self._rule_input_snapshot():
            return
        if error is not None:
            self._error(error)
        else:
            self._done(result)

    def _active_comparison(self):
        return self._selected_candidate or self._comparison

    def _invalidate_ml(self):
        self._ml_generation += 1
        self._ml_snapshot = None
        self._reset_ml_result()
        if callable(self._on_state_changed):
            self._on_state_changed()

    def _reset_ml_result(self):
        self._ml_comparison = None
        self.ml_provenance = None
        for label in (self.ml_hic_baseline, self.ml_hic_mutant, self.ml_hic_delta, self.ml_probability_baseline, self.ml_probability_mutant, self.ml_probability_delta):
            label.setText("-")
        self.ml_warning.setVisible(False)
        self.ml_details.clear(); self.ml_details.setVisible(False); self.ml_details_button.setEnabled(False)
        self.ml_status.setText("已就绪，点击按钮运行本地 ML 比较。" if self._active_comparison() and self._valid_ml_pair_available() else "实验性 ML 比较需要同时提供 VH 和 VL 序列。")
        self.ml_run_button.setEnabled(False if self._ml_worker else bool(self._active_comparison() and self._valid_ml_pair_available()))

    def _valid_ml_pair_available(self):
        if self.chain.currentData() not in {"VH", "VL"}:
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
            self.ml_status.setText("请先完成有效的规则突变比较，再运行 ML 比较。")
            return
        try:
            pairs = build_mutation_pairs(self.chain.currentData(), self.vh_sequence.toPlainText(), self.vl_sequence.toPlainText(), comparison.original_sequence, comparison.mutant_sequence)
        except ValueError as error:
            self.ml_status.setText(notice_zh(error))
            return
        try:
            status = self._ml_service.status()
        except Exception as error:
            self.ml_status.setText("本地 ML 比较状态不可用，请查看“模型详情”。")
            self.ml_details.setPlainText(sanitize_error(str(error))); self.ml_details_button.setEnabled(True)
            return
        if status_code(status) != STATUS_READY:
            self.ml_status.setText(notice_zh(status_message(status)))
            self.ml_details.setPlainText(str(status.get("error", "")) if isinstance(status, dict) else "")
            self.ml_details_button.setEnabled(bool(self.ml_details.toPlainText()))
            return
        self._last_ml_status = dict(status) if isinstance(status, dict) else {}
        self._ml_snapshot = (sequence_hash(pairs[0]), sequence_hash(pairs[1]), sequence_hash(pairs[2]), sequence_hash(pairs[3]), comparison.mutation)
        token = self._ml_generation
        self.ml_run_button.setEnabled(False); self.ml_status.setText("正在运行本地 ML 比较…")
        self._ml_worker = Worker(compare_mutation_ml, self._ml_service, *pairs)
        self._ml_worker.signals.finished.connect(lambda result, t=token, s=self._ml_snapshot: self._ml_done(result, t, s))
        self._ml_worker.signals.error.connect(lambda message, t=token: self._ml_error(message, t))
        self.pool.start(self._ml_worker)

    def _current_ml_snapshot(self):
        comparison = self._active_comparison()
        if not comparison:
            return None
        try:
            pairs = build_mutation_pairs(self.chain.currentData(), self.vh_sequence.toPlainText(), self.vl_sequence.toPlainText(), comparison.original_sequence, comparison.mutant_sequence)
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
        self.ml_probability_delta.setText(f"{result.delta_probability * 100:+.1f} 个百分点")
        self.ml_warning.setVisible(True)
        self.ml_provenance = dict(result.metadata)
        self.ml_provenance["timestamp_utc"] = datetime.now(timezone.utc).isoformat()
        self.ml_provenance["device"] = self._last_ml_status.get("device", "unknown")
        self.ml_details.setPlainText(model_details_zh(
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
        ))
        self.ml_details_button.setEnabled(True); self.ml_status.setText("ML 比较已完成，数值仅供科研辅助参考。"); self.ml_run_button.setEnabled(True)

    def _ml_error(self, message, token):
        self._ml_worker = None
        if token != self._ml_generation:
            self._reset_ml_result(); return
        self.ml_status.setText("ML 比较失败，已有规则突变结果已保留。")
        self.ml_details.setPlainText(sanitize_error(message)); self.ml_details_button.setEnabled(True); self.ml_run_button.setEnabled(True)

    def get_research_summary_state(self):
        """Expose existing mutation evidence without running any calculation."""

        return {
            "mutation_analysis": self._selected_candidate or self._comparison,
            "mutation_ml": self._ml_comparison,
            "provenance": dict(self.ml_provenance or {}),
        }

    def _risk_table(self):
        table = QTableWidget(0, len(self.RISK_COLUMNS)); table.setHorizontalHeaderLabels(self.RISK_COLUMNS); return table

    def _set_result_controls(self, enabled):
        self.add_candidate_button.setEnabled(enabled); self.simulate_button.setEnabled(not bool(self._worker))

    def load_sequence(self, antibody_id, sequence, chain="Unspecified", vh_sequence=None, vl_sequence=None):
        self._rule_generation += 1
        self._worker = None; self._comparison = None; self._selected_candidate = None; self._candidates.clear(); self.candidates.setRowCount(0)
        canonical_chain = chain if chain in {"VH", "VL", "Unspecified"} else "Unspecified"
        baseline_vh = sequence if vh_sequence is None and canonical_chain != "VL" else (vh_sequence or "")
        baseline_vl = sequence if vl_sequence is None and canonical_chain == "VL" else (vl_sequence or "")
        self.antibody_id.blockSignals(True); self.vh_sequence.blockSignals(True); self.vl_sequence.blockSignals(True); self.chain.blockSignals(True)
        self.antibody_id.setText(str(antibody_id or "")); self.vh_sequence.setPlainText(str(baseline_vh or "")); self.vl_sequence.setPlainText(str(baseline_vl or "")); self.chain.setCurrentIndex(self.chain.findData(canonical_chain)); self._set_active_sequence_alias()
        self.antibody_id.blockSignals(False); self.vh_sequence.blockSignals(False); self.vl_sequence.blockSignals(False); self.chain.blockSignals(False); self._invalidate_ml(); self._reset_results(); self.simulate_button.setEnabled(True)

    def _baseline_edited(self):
        self._rule_generation += 1
        self._comparison = None; self._selected_candidate = None; self._candidates.clear(); self.candidates.setRowCount(0); self._reset_results()
        self._invalidate_ml()

    def _reset_results(self):
        self.original_summary.setText("长度：- | 规则计算分数：- | 规则风险等级：- | 总位点数：- | CDR 位点数：-")
        self.mutant_summary.setText("突变：- | 长度：- | 规则计算分数：- | 规则风险等级：- | 总位点数：- | CDR 位点数：-")
        self.comparison.setText("规则计算分数：- → - (Δ -) | 总位点数：- → - (Δ -) | CDR 位点数：- → - (Δ -)")
        self.message.clear(); self._set_result_controls(False)
        self._reset_ml_result()
        self.find_removed_button.setEnabled(False); self.find_added_button.setEnabled(False)
        for table in (self.removed_table, self.added_table, self.unchanged_table): table.setRowCount(0)

    def simulate(self):
        if self._worker: return
        self._invalidate_ml(); self._selected_candidate = None; self.message.clear(); self.simulate_button.setEnabled(False)
        mutation = self.mutation.text().strip().upper()
        self.mutation.setText(mutation)
        worker = Worker(compare_mutation, self.sequence.toPlainText(), mutation, self.antibody_id.text(), self.chain.currentData())
        self._worker = worker
        token, snapshot = self._rule_generation, self._rule_input_snapshot()
        worker.signals.finished.connect(lambda result, w=worker, t=token, s=snapshot: self._rule_finished(w, t, s, result=result))
        worker.signals.error.connect(lambda error, w=worker, t=token, s=snapshot: self._rule_finished(w, t, s, error=error))
        self.pool.start(worker)

    def _done(self, result: MutationComparison):
        self._worker = None; self._comparison = result; self._selected_candidate = None; self.simulate_button.setEnabled(True); self._render(result); self.add_candidate_button.setEnabled(True); self._reset_ml_result()

    def _error(self, message):
        self._worker = None; self.simulate_button.setEnabled(True); self._comparison = None; self._ml_comparison = None; self.add_candidate_button.setEnabled(False); self.message.setText(notice_zh(sanitize_error(message)))

    def _render(self, result):
        self.original_summary.setText(f"长度：{len(result.original_sequence)} | 规则计算分数：{result.original_score:.2f} | 规则风险等级：{display_value(result.original_level)} | 总位点数：{result.original_total_sites} | CDR 位点数：{result.original_cdr_sites}")
        self.mutant_summary.setText(f"突变：{result.mutation} | 长度：{len(result.mutant_sequence)} | 规则计算分数：{result.mutant_score:.2f} | 规则风险等级：{display_value(result.mutant_level)} | 总位点数：{result.mutant_total_sites} | CDR 位点数：{result.mutant_cdr_sites}")
        self.comparison.setText(f"规则计算分数：{result.original_score:.2f} → {result.mutant_score:.2f} (Δ {result.delta_score:+.2f}) | 总位点数：{result.original_total_sites} → {result.mutant_total_sites} (Δ {result.delta_total_sites:+d}) | CDR 位点数：{result.original_cdr_sites} → {result.mutant_cdr_sites} (Δ {result.delta_cdr_sites:+d})")
        self._fill_risks(self.removed_table, result.removed_risks); self._fill_risks(self.added_table, result.added_risks); self._fill_risks(self.unchanged_table, result.unchanged_risks)

    def _fill_risks(self, table, risks):
        table.setRowCount(0)
        for risk in risks:
            row = table.rowCount(); table.insertRow(row)
            for col, value in enumerate((display_value(risk.chain), risk.position, risk.motif, risk.category, display_value(risk.region))): table.setItem(row, col, QTableWidgetItem(str(value)))
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
        values = [result.mutation, display_value(result.chain), f"{result.original_score:.2f}", f"{result.mutant_score:.2f}", f"{result.delta_score:+.2f}", len(result.removed_risks), len(result.added_risks)]
        for col, value in enumerate(values): self.candidates.setItem(row, col, QTableWidgetItem(str(value)))
        self.candidates.selectRow(row); self._selected_candidate = result; self._invalidate_ml()

    def clear(self):
        self.load_sequence("", "", "Unspecified"); self.mutation.clear()
