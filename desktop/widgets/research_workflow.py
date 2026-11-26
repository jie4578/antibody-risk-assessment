"""MERGE-01: explicit, read-only external result intake in the existing desktop."""
import json
import uuid

from PySide6.QtCore import QThreadPool, Qt, Signal, Slot
from PySide6.QtWidgets import (QFileDialog, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
                               QPlainTextEdit, QPushButton, QTabWidget, QVBoxLayout, QWidget)

from desktop.integrations import IntegrationError, ResultSummary, inspect_biolab, inspect_literature
from desktop.workers import Worker


def _read_operation(token, loader, filename):
    try:
        result = loader(filename)
        if not isinstance(result, ResultSummary):
            raise IntegrationError("INVALID_RESULT", "只读适配器返回值不完整")
        return token, result, None
    except IntegrationError as exc:
        return token, None, str(exc)
    except Exception:
        return token, None, "INTERNAL_INTEGRITY_FAILURE: 结果读取失败，未接受任何科学结论"


class ResultImportPanel(QWidget):
    snapshot_changed = Signal(object)

    def __init__(self, kind, parent=None):
        super().__init__(parent)
        self.kind = kind
        self.summary = None
        self._token = None
        self._worker = None
        self._busy = False
        self._closed = False
        self.loaders = {"biolab": inspect_biolab, "literature": inspect_literature}
        layout = QVBoxLayout(self)
        note = QLabel("显式选择 manifest 即授权只读检查其所在结果目录；不启动外部引擎，不读原始输入/PDF，不自动上传。")
        note.setTextFormat(Qt.PlainText)
        note.setWordWrap(True)
        layout.addWidget(note)
        row = QHBoxLayout()
        self.select_button = QPushButton("选择 BioLab 结果 manifest" if kind == "biolab" else "选择文献批次 manifest")
        self.clear_button = QPushButton("清除当前接入")
        row.addWidget(self.select_button)
        row.addWidget(self.clear_button)
        layout.addLayout(row)
        self.path = QLineEdit()
        self.path.setReadOnly(True)
        self.path.setPlaceholderText("尚未选择文件；启动页面不会扫描磁盘")
        layout.addWidget(self.path)
        self.status = QLabel("未接入；未执行外部项目。")
        self.status.setTextFormat(Qt.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        layout.addWidget(self.details, 1)
        self.select_button.clicked.connect(self.choose)
        self.clear_button.clicked.connect(self.clear)

    @Slot()
    def choose(self):
        filters = "BioLab manifest (run_manifest.json report_manifest.json)" if self.kind == "biolab" else "文献批次 (batch_manifest.json)"
        filename, _ = QFileDialog.getOpenFileName(self, "选择本地结果（只读；限定该目录）", "", filters)
        if filename:
            self.import_manifest(filename)

    def import_manifest(self, filename):
        self.clear()
        if not filename or self._closed:
            return
        self.path.setText(str(filename))
        self._token = uuid.uuid4().hex
        self._busy = True
        self.status.setText("正在只读核验；尚未接受结果。可重新选择，旧任务不会覆盖新选择。")
        worker = Worker(_read_operation, self._token, self.loaders[self.kind], str(filename))
        self._worker = worker
        # Bound QObject slot gives queued GUI-thread delivery, not a mutable callback closure.
        worker.signals.finished.connect(self._received)
        QThreadPool.globalInstance().start(worker)

    @Slot(object)
    def _received(self, payload):
        token, summary, error = payload
        if self._closed or token != self._token:
            return
        self._busy = False
        self._worker = None
        if error:
            self.summary = None
            self.details.clear()
            self.status.setText("拒绝接入：" + error)
            return
        self.summary = summary
        counts = dict(summary.counts)
        count_text = (f"；完成文档 {counts['completed_count']}，失败文档 {counts['failed_count']}，"
                      f"唯一文档 {counts['document_count']}，上传输入 {counts['input_count']}") if counts else ""
        self.status.setText(f"只读接入完成；上游状态={summary.source_state}；接入状态={summary.state}{count_text}。"
                            "内容哈希匹配不等于科学有效性。")
        self.details.setPlainText(json.dumps(summary.as_dict(), ensure_ascii=False, allow_nan=False, indent=2))
        self.snapshot_changed.emit(summary)

    @Slot()
    def clear(self):
        self._token = None
        if self._worker is not None:
            self._worker.cancel()
        self._worker = None
        self._busy = False
        self.summary = None
        self.path.clear()
        self.details.clear()
        self.status.setText("未接入；旧结果已清除，未修改来源文件。")
        self.snapshot_changed.emit(None)

    def closeEvent(self, event):
        self._closed = True
        self.clear()
        super().closeEvent(event)


class ResearchWorkflowPage(QWidget):
    def __init__(self, open_existing, parent=None, *, sequence_getter=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        title = QLabel("BioResearch Workbench｜科研工作流")
        title.setTextFormat(Qt.PlainText)
        layout.addWidget(title)
        local = QGroupBox("A. 抗体与蛋白质工程（现有功能）")
        row = QHBoxLayout(local)
        self.entry_buttons = {}
        for name, index in (("单条分析", 0), ("批量分析", 1), ("突变工作区", 2), ("文献检索", 3), ("蛋白质工程 / C.1 / C.2A", 6)):
            button = QPushButton(name)
            button.clicked.connect(lambda checked=False, target=index: open_existing(target))
            row.addWidget(button)
            self.entry_buttons[index] = button
        layout.addWidget(local)
        self.tabs = QTabWidget()
        from desktop.widgets.biolab_summary import BioLabSummaryPanel
        from desktop.widgets.case_overview import CaseOverview
        from desktop.widgets.literature_evidence import LiteratureEvidencePanel
        self.biolab = BioLabSummaryPanel()
        self.literature = LiteratureEvidencePanel()
        self.case = CaseOverview(sequence_getter or (lambda: None))
        self.biolab.snapshot_changed.connect(lambda summary: self.case.accept_external("biolab", summary))
        self.literature.snapshot_changed.connect(lambda summary: self.case.accept_external("literature", summary))
        self.tabs.addTab(self.biolab, "B. 实验数据分析｜只读结果")
        self.tabs.addTab(self.literature, "C. 论文与科研证据｜只读结果")
        self.tabs.addTab(self.case, "案例概览与关联")
        layout.addWidget(self.tabs, 1)
