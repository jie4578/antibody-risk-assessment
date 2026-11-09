"""Independent Protein Engineering workspace. Data management only in A/B."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile

from PySide6.QtCore import QThreadPool, Qt, QUrl, Slot
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QComboBox, QDialog, QFileDialog, QFormLayout, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton, QTableWidget,
    QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)

from desktop.workers import Worker
from protein_engineering.importer import preview_file, sheet_names
from protein_engineering.resources import DOCUMENTS, TABLE_LABELS, document_text, save_template
from protein_engineering.schema import SPECS
from protein_engineering.storage import ProteinStore, default_database_path
from .protein_initial_rate import InitialRatePanel

PLANNED = (
    ("AI 预测验证", "规划中：可保存原始预测记录；尚无预测评价、性能计算、训练或自动推荐。"),
    ("结构分析", "规划中：仅提供结构元数据模板；不解析结构、不映射突变、不生成机制结论。"),
    ("DBTL 记录", "规划中：尚无多轮 Design–Build–Test–Learn 工作流或自动实验建议。"),
)
MANUAL_FIELDS = {
    "enzyme_targets": ("target_id", "target_name", "organism", "source_accession", "notes"),
    "protein_variants": ("variant_id", "target_id", "variant_name", "variant_role", "sequence",
                         "parent_variant_id", "reference_variant_id", "mutation_notation_as_reported", "numbering_reference", "notes"),
    "samples": ("sample_id", "variant_id", "sample_lot_id", "biological_replicate", "notes"),
    "experiment_batches": ("batch_id", "assay_id", "assay_type", "protocol_id", "protocol_version", "wt_control_sample_id", "notes"),
}


def _label(text):
    result = QLabel(text)
    result.setWordWrap(True)
    result.setTextFormat(Qt.TextFormat.PlainText)
    return result


class RecordForm(QGroupBox):
    def __init__(self, kind, submit):
        super().__init__("新增" + TABLE_LABELS[kind] + "（仅追加，不覆盖旧 ID）")
        self.kind, self.inputs = kind, {}
        layout = QFormLayout(self)
        for name in MANUAL_FIELDS[kind]:
            if name == "sequence":
                editor = QPlainTextEdit()
                editor.setPlaceholderText("原始蛋白序列；只去空白/规范 ASCII 大小写，不增删残基")
                editor.setMaximumHeight(90)
            elif name == "variant_role":
                editor = QComboBox()
                editor.addItem("请选择角色（必填）", "")
                for role in ("WT", "DESIGNED", "CONTROL", "REFERENCE", "OTHER"):
                    editor.addItem(role, role)
            else:
                editor = QLineEdit()
            self.inputs[name] = editor
            layout.addRow(name + (" *" if name in SPECS[kind].required else ""), editor)
        self.save_button = QPushButton("保存建档记录")
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(lambda: submit(kind, self.values()))
        layout.addRow(self.save_button)

    def values(self):
        result = {}
        for name, editor in self.inputs.items():
            if isinstance(editor, QPlainTextEdit):
                result[name] = editor.toPlainText()
            elif isinstance(editor, QComboBox):
                result[name] = editor.currentData()
            else:
                result[name] = editor.text()
        return result


class ProteinEngineeringPage(QWidget):
    def __init__(self):
        super().__init__()
        self.store = None
        self.preview = None
        self._busy = False
        self._worker = None
        self._records = []
        self._preview_controls = []
        root = QVBoxLayout(self)
        root.addWidget(_label("蛋白质工程（Protein Engineering）— 独立研究模块"))
        root.addWidget(_label("可用：Phase A/B 数据基础、B.1 审计与 C.1 显式区间初始速率基础。Phase 0 真实数据尚未验收；未实现阶段不标完成。"))
        root.addWidget(_label("不使用抗体风险分数或 ESM2/HIC 模型评估酶；原始、校正与派生结果分离。不训练、不联网、不自动调用 Provider。Km/Vmax、AI 验证、结构映射、DBTL 仍为规划中。"))
        path_row = QHBoxLayout()
        self.database_path = QLineEdit(str(default_database_path()))
        self.database_path.setToolTip("默认位于用户数据目录。打开页面不会创建数据库；点击打开后才初始化/迁移。")
        self.open_database_button = QPushButton("打开 / 初始化本地数据库")
        self.choose_database_button = QPushButton("选择现有库")
        path_row.addWidget(self.database_path, 1)
        path_row.addWidget(self.choose_database_button)
        path_row.addWidget(self.open_database_button)
        root.addLayout(path_row)
        self.status = _label("尚未打开数据库。请先确认本地路径，再点击打开。首次使用数据库为空，不预置虚构实验。")
        root.addWidget(self.status)
        self.tabs = QTabWidget()
        root.addWidget(self.tabs)
        self.forms = {}
        self._build_intake()
        self._build_sequences()
        self._build_experiments()
        self.rate_panel = InitialRatePanel(self)
        self.tabs.addTab(self.rate_panel, "酶学分析（C.1）")
        for name, message in PLANNED:
            page = QWidget()
            layout = QVBoxLayout(page)
            layout.addWidget(_label(message))
            layout.addStretch()
            self.tabs.addTab(page, name + "（规划中）")
        viewer = QGroupBox("已保存记录 / 溯源（只读）")
        layout = QVBoxLayout(viewer)
        top = QHBoxLayout()
        self.view_kind = QComboBox()
        for kind, text in TABLE_LABELS.items():
            self.view_kind.addItem(text, kind)
        self.refresh_button = QPushButton("刷新记录")
        self.export_button = QPushButton("导出私有数据快照（含原件）")
        self.refresh_button.setEnabled(False)
        self.count_label = _label("记录数：尚未读取")
        top.addWidget(self.view_kind)
        top.addWidget(self.refresh_button)
        top.addWidget(self.export_button)
        top.addWidget(self.count_label, 1)
        layout.addLayout(top)
        self.record_table = QTableWidget(0, 5)
        self.record_table.setHorizontalHeaderLabels(["记录 ID", "身份 / 指标", "序列 SHA256", "来源文件", "原工作表 / 行"])
        self.record_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.record_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.record_table.setMaximumHeight(190)
        layout.addWidget(self.record_table)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setPlaceholderText("选中记录可查看规范字段、原始字段和计算的文件 SHA256；预测不会当作实测值。")
        self.details.setMaximumHeight(180)
        layout.addWidget(self.details)
        root.addWidget(viewer)
        root.addStretch()
        self.choose_database_button.clicked.connect(self.choose_database)
        self.open_database_button.clicked.connect(self.open_database)
        self.database_path.textEdited.connect(self._database_changed)
        self.refresh_button.clicked.connect(self.refresh)
        self.export_button.clicked.connect(self.export_snapshot)
        self.view_kind.currentIndexChanged.connect(lambda _: self.refresh() if self.store and not self._busy else None)
        self.record_table.itemSelectionChanged.connect(self._show_selected)
        self.tabs.currentChanged.connect(self._fit_current_tab)
        self._fit_current_tab()
        self._set_busy(False)

    def _fit_current_tab(self, *_):
        # QTabWidget otherwise allocates every tab the tallest form's height,
        # hiding the intake controls/record browser behind large empty regions.
        if not hasattr(self, "tabs") or self.tabs.currentWidget() is None:
            return
        layout = self.tabs.currentWidget().layout()
        width = max(250, self.tabs.width() - 12)
        height = layout.heightForWidth(width) if layout.hasHeightForWidth() else layout.sizeHint().height()
        target = max(160, height + self.tabs.tabBar().sizeHint().height() + 16)
        if self.tabs.height() != target:
            self.tabs.setFixedHeight(target)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_current_tab()

    def _build_intake(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(_label("数据接入：先导入靶标 → 变体 → 样品 → 批次，再导入实测/预测记录。导入前预览；失败整批回滚，原件不改写。仅支持规范 UTF-8 CSV/.xlsx；每文件 ≤25 MiB、每表 ≤10,000 行。"))
        row = QHBoxLayout()
        self.template_kind = QComboBox()
        for kind, text in TABLE_LABELS.items():
            self.template_kind.addItem(text, kind)
        self.save_template_button = QPushButton("保存空白 CSV 模板")
        self.open_template_button = QPushButton("打开模板副本")
        row.addWidget(self.template_kind, 1)
        row.addWidget(self.save_template_button)
        row.addWidget(self.open_template_button)
        layout.addLayout(row)
        row = QHBoxLayout()
        self.document_kind = QComboBox()
        self.document_kind.addItems(DOCUMENTS)
        self.document_button = QPushButton("阅读接入文档 / 实现状态")
        row.addWidget(self.document_kind, 1)
        row.addWidget(self.document_button)
        layout.addLayout(row)
        row = QHBoxLayout()
        self.import_kind = QComboBox()
        for kind, text in TABLE_LABELS.items():
            self.import_kind.addItem(text, kind)
        self.input_path = QLineEdit()
        self.input_path.setReadOnly(True)
        self.choose_input_button = QPushButton("选择 CSV / XLSX")
        self.sheet = QComboBox()
        row.addWidget(self.import_kind)
        row.addWidget(self.input_path, 1)
        row.addWidget(self.choose_input_button)
        row.addWidget(self.sheet)
        layout.addLayout(row)
        row = QHBoxLayout()
        self.preview_button = QPushButton("校验并预览")
        self.import_button = QPushButton("确认整批导入")
        self.import_button.setEnabled(False)
        row.addWidget(self.preview_button)
        row.addWidget(self.import_button)
        layout.addLayout(row)
        self.preview_text = QPlainTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_text.setMaximumHeight(180)
        layout.addWidget(self.preview_text)
        layout.addStretch()
        self._preview_controls = [self.import_kind, self.choose_input_button, self.sheet, self.preview_button]
        self.save_template_button.clicked.connect(self.export_template)
        self.open_template_button.clicked.connect(self.open_template_copy)
        self.document_button.clicked.connect(self.show_document)
        self.choose_input_button.clicked.connect(self.choose_input)
        self.preview_button.clicked.connect(self.validate_input)
        self.import_button.clicked.connect(self.commit_import)
        self.import_kind.currentIndexChanged.connect(self._invalidate_preview)
        self.sheet.currentIndexChanged.connect(self._invalidate_preview)
        self.input_path.textChanged.connect(self._invalidate_preview)
        self.tabs.addTab(page, "数据接入")

    def _build_sequences(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(_label("建档保存原始序列及独立规范序列哈希；相同序列的不同 ID 保留。尚未实现参考序列比对、突变编号核实或功能预测。"))
        for kind in ("enzyme_targets", "protein_variants"):
            form = RecordForm(kind, self.save_manual)
            self.forms[kind] = form
            layout.addWidget(form)
        self.tabs.addTab(page, "蛋白序列管理")

    def _build_experiments(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(_label("样品与实验批次建档。原始时间序列、实验报告值和预测可分别导入；缺失值保持缺失，不自动校准、补零或拟合。更多条件字段使用完整模板导入。"))
        for kind in ("samples", "experiment_batches"):
            form = RecordForm(kind, self.save_manual)
            self.forms[kind] = form
            layout.addWidget(form)
        self.tabs.addTab(page, "实验数据管理")

    def _set_busy(self, busy):
        self._busy = busy
        for control in [self.database_path, self.open_database_button, self.choose_database_button, self.view_kind, *self._preview_controls]:
            control.setEnabled(not busy)
        for form in self.forms.values():
            form.save_button.setEnabled(not busy and self.store is not None)
        self.refresh_button.setEnabled(not busy and self.store is not None)
        self.export_button.setEnabled(not busy and self.store is not None)
        self.import_button.setEnabled(not busy and self.store is not None and self.preview is not None and self.preview.valid)
        if hasattr(self, "rate_panel"):
            self.rate_panel.set_busy(busy)

    def _run(self, function, done):
        if self._busy:
            return
        self._set_busy(True)
        worker = Worker(function)
        self._worker = worker
        self._on_done = done
        worker.signals.finished.connect(self._worker_done)
        worker.signals.error.connect(self._worker_failed)
        QThreadPool.globalInstance().start(worker)

    @Slot(object)
    def _worker_done(self, result):
        done = self._on_done
        self._on_done = None
        self._worker = None
        self._set_busy(False)
        done(result)

    @Slot(str)
    def _worker_failed(self, message):
        self._worker = None
        self._on_done = None
        self._set_busy(False)
        self.status.setText("操作未完成：" + message)

    def _database_changed(self):
        self.store = None
        self.rate_panel.reset()
        self._records = []
        self._invalidate_preview()
        self.record_table.setRowCount(0)
        self.details.clear()
        self.count_label.setText("记录数：尚未读取")
        self.status.setText("数据库路径已改变，请重新打开；不会自动连接或创建。")
        self._set_busy(False)

    def choose_database(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择本模块现有数据库", "", "Protein Engineering SQLite (*.sqlite3 *.db)")
        if path:
            self.database_path.setText(path)
            self._database_changed()

    def open_database(self):
        path = self.database_path.text().strip()
        if not path:
            self.status.setText("请输入本地数据库路径")
            return
        def opened(store):
            self.store = store
            self.rate_panel.reset()
            self._invalidate_preview()
            self.status.setText("本地数据库已打开；原件保留。C.1 分析需显式选择序列、区间和校正，不自动计算。")
            self._set_busy(False)
            self.refresh()
        self._run(lambda: ProteinStore(path), opened)

    def _invalidate_preview(self, *_):
        self.preview = None
        self.import_button.setEnabled(False)
        self.preview_text.clear()

    def choose_input(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择原始数据文件（只读）", "", "CSV / XLSX (*.csv *.xlsx)")
        if not path:
            return
        self.input_path.setText(path)
        self.sheet.clear()
        self._run(lambda: sheet_names(path), lambda names: self.sheet.addItems(names))

    def validate_input(self):
        self._invalidate_preview()
        if not self.input_path.text():
            self.status.setText("请先选择输入文件")
            return
        kind, path, sheet = self.import_kind.currentData(), self.input_path.text(), self.sheet.currentText() or None
        self._run(lambda: preview_file(kind, path, sheet), self._preview_done)

    def _preview_done(self, preview):
        self.preview = preview
        lines = [f"原件 SHA256: {preview.sha256}", f"工作表: {preview.sheet}；记录: {len(preview.rows)}；完全空行: {preview.blank_rows}",
                 "仅已选工作表会导入；其他工作表未被合并。", "列: " + ", ".join(preview.headers)]
        lines += [f"{i.severity} row {i.row} [{i.field}] {i.code}: {i.message}" for i in preview.issues[:100]]
        if len(preview.issues) > 100:
            lines.append(f"显示前 100 项；完整 {len(preview.issues)} 项随来源记录保存。")
        self.preview_text.setPlainText("\n".join(lines))
        self.status.setText("本文件字段校验通过；确认导入时还将检查数据库关联。" if preview.valid else "校验失败，不能导入；原件未修改。")
        self._set_busy(False)

    def commit_import(self):
        if not self.store or not self.preview or not self.preview.valid:
            return
        store, preview = self.store, self.preview
        self._run(lambda: store.commit_preview(preview), self._saved)

    def save_manual(self, kind, fields):
        if self.store is None:
            self.status.setText("请先打开本地数据库")
            return
        store = self.store
        self._run(lambda: store.add_fields(kind, fields), self._saved)

    def _saved(self, result):
        self._invalidate_preview()
        self.rate_panel.reset()
        self.view_kind.blockSignals(True)
        self.view_kind.setCurrentIndex(self.view_kind.findData(result["kind"]))
        self.view_kind.blockSignals(False)
        self.status.setText(f"已追加 {result['rows']} 条记录；原件 SHA256: {result['source_sha256']}。未覆盖旧 ID、未补值。")
        self.refresh()

    def refresh(self):
        if self.store is None or self._busy:
            return
        store, kind = self.store, self.view_kind.currentData()
        self._run(lambda: (kind, store.counts(), store.records(kind), store.sequence_audit(), store.unresolved_target_references()), self._records_done)

    def _records_done(self, result):
        kind, counts, records, sequence_audit, unresolved = result
        self._records = records
        self.count_label.setText(f"{TABLE_LABELS[kind]}: 总计 {counts[kind]}，显示 {len(records)}（最多 500）；序列 {sequence_audit['records']} / 唯一序列 {sequence_audit['unique_sequences']}；待解决靶标参考 {len(unresolved)}")
        self.record_table.setRowCount(0)
        self.details.clear()
        for record in records:
            fields, provenance = record["fields"], record["provenance"]
            values = [fields[SPECS[kind].id_field], fields.get("variant_name") or fields.get("target_name") or fields.get("metric_name") or fields.get("predicted_metric") or "",
                      fields.get("sequence_sha256") or "", provenance["filename"], f"{provenance['sheet']} / {provenance['source_row']}"]
            row = self.record_table.rowCount()
            self.record_table.insertRow(row)
            for column, value in enumerate(values):
                self.record_table.setItem(row, column, QTableWidgetItem(str(value)))

    def _show_selected(self):
        row = self.record_table.currentRow()
        self.details.setPlainText(json.dumps(self._records[row], ensure_ascii=False, indent=2) if 0 <= row < len(self._records) else "")

    def export_template(self):
        kind = self.template_kind.currentData()
        path, _ = QFileDialog.getSaveFileName(self, "保存空白模板（只创建新文件）", kind + "_template.csv", "CSV (*.csv)")
        if path:
            try:
                save_template(kind, path)
                self.status.setText("空白模板已保存；不包含实验数据。")
            except (OSError, ValueError) as exc:
                self.status.setText("无法保存模板，请选择不存在的新文件：" + str(exc))

    def open_template_copy(self):
        try:
            kind = self.template_kind.currentData()
            folder = Path(tempfile.mkdtemp(prefix="protein-template-"))
            path = save_template(kind, folder / (kind + "_template.csv"))
            opened = QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
            self.status.setText("已打开临时模板副本；原始模板保持不变。" if opened else "系统未能打开副本，请使用保存模板功能。")
        except (OSError, ValueError) as exc:
            self.status.setText("无法打开模板副本：" + str(exc))

    def show_document(self):
        dialog = QDialog(self)
        dialog.setWindowTitle(self.document_kind.currentText())
        dialog.resize(850, 650)
        layout = QVBoxLayout(dialog)
        text = QPlainTextEdit()
        text.setReadOnly(True)
        text.setPlainText(document_text(self.document_kind.currentText()))
        layout.addWidget(text)
        dialog.exec()

    def export_snapshot(self):
        if self.store is None or self._busy:
            return
        path, _ = QFileDialog.getSaveFileName(self, "导出私有实验/序列及原件快照（仅新文件，不自动上传）", "protein-private-snapshot.json", "JSON (*.json)")
        if path:
            store = self.store
            self._run(lambda: store.export_snapshot(path), lambda result: self.status.setText("本地私有快照已导出；请妥善保管，不自动提交或上传。SHA256: " + result["payload_sha256"]))
