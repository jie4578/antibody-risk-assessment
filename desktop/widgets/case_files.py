"""Explicit case file actions within the existing workflow page."""
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QFileDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
                               QMessageBox, QPlainTextEdit, QPushButton)
from desktop.integrations.case_context import CaseContext, MATERIALS, SOURCE_LABELS
from desktop.integrations.case_record import LIMITATIONS, canonical, document, load_case, save_case
from desktop.integrations.case_report import export_report
from desktop.version import project_version


class CaseFileActions:
    def __init__(self, view):
        self.view = view
        self.path = None
        self.reset_intake = lambda: None
        self.literature = None
        self._quotes = ()
        self._loading = False
        row = QHBoxLayout()
        self.buttons = {}
        for key, label, action in (
            ("new", "新建案例", self.new_case), ("open", "打开案例", self.open_case),
            ("save", "保存案例", self.save), ("save_as", "另存为", self.save_as),
            ("markdown", "导出 Markdown", lambda: self.export("md")),
            ("docx", "导出 Word DOCX", lambda: self.export("docx")),
        ):
            button = QPushButton(label)
            button.clicked.connect(action)
            row.addWidget(button)
            self.buttons[key] = button
        view.layout().insertLayout(0, row)
        self.file_status = QLabel()
        self.file_status.setTextFormat(Qt.TextFormat.PlainText)
        self.file_status.setWordWrap(True)
        view.layout().insertWidget(1, self.file_status)
        self.history = QPlainTextEdit()
        self.history.setReadOnly(True)
        self.history.setMaximumHeight(110)
        view.layout().addWidget(self.history)
        view.findings = QPlainTextEdit()
        view.findings.setPlaceholderText("用户研究发现，尚待验证")
        view.findings.setMaximumHeight(70)
        view.recommendations = QPlainTextEdit()
        view.recommendations.setPlaceholderText("后续实验建议")
        view.recommendations.setMaximumHeight(70)
        for label, editor in (("研究发现", view.findings), ("后续实验建议", view.recommendations)):
            view.layout().addWidget(QLabel(label))
            view.layout().addWidget(editor)
        view.findings.textChanged.connect(self._research_changed)
        view.recommendations.textChanged.connect(self._research_changed)
        self.quote_list = QListWidget()
        self.quote_list.setMaximumHeight(95)
        view.layout().addWidget(QLabel("本次报告引文（默认不选；选中才导出原文，本选择不写入案例文件）"))
        view.layout().addWidget(self.quote_list)
        for editor in (view.case_id, view.topic, view.basis):
            editor.textChanged.connect(self.refresh)
        for editor in (view.notes,):
            editor.textChanged.connect(self.refresh)
        view.material.currentIndexChanged.connect(self.refresh)
        view.relationship.currentIndexChanged.connect(self.refresh)
        self._clean_signature = self.signature()
        self.refresh()

    def signature(self):
        value = document(self.view.context, project_version())
        value.pop("created_at")
        value.pop("updated_at")
        value["association_draft"] = [self.view.relationship.currentText(), self.view.basis.text()]
        return canonical(value)

    def dirty(self):
        return self.signature() != self._clean_signature

    def _research_changed(self):
        if self._loading:
            return
        self.view.context.findings = self.view.findings.toPlainText()
        self.view.context.recommendations = self.view.recommendations.toPlainText()
        self.refresh()

    def refresh(self, *_):
        if self._loading:
            return
        self.file_status.setText(("有未保存修改" if self.dirty() else "已保存或尚无修改") +
                                (" · " + self.path.name if self.path else " · 未选择案例文件"))
        context = self.view.context
        lines = ["历史记录与当前核验"]
        for kind, label in SOURCE_LABELS.items():
            old = context.historical_sources.get(kind)
            lines.append(label + " · " + context.source_status(kind))
            if old:
                lines.extend(["历史身份  " + old.identifier, "历史 SHA256  " + old.sha256,
                              "待用户确认的路径提示（未自动读取）  " + old.origin,
                              "历史摘要（用户可编辑）  " + old.summary])
        link = context.historical_association
        if link:
            lines.extend(["历史人工关联  " + link.kind, "历史依据  " + link.basis,
                          "历史关联未自动恢复；当前来源仍需明确接入并由用户再次确认。"])
        if context.association:
            lines.append("用户已重新确认关联；身份关系仍为用户声明。")
        lines.extend(["软件强制科学限制", *LIMITATIONS])
        declared = [item for item in (context.scientific_limitations or ()) if item not in LIMITATIONS]
        if declared:
            lines.extend(["案例文件科学限制记录（用户可编辑研究记录，未经独立核验）", *declared])
        self.history.setPlainText("\n".join(lines))

    def source_changed(self, kind, summary=None):
        if kind == "literature":
            self.quote_list.clear()
            self._quotes = summary.evidence if summary else ()
            for quote in self._quotes:
                item = QListWidgetItem(f"{quote.document_id} · PDF {quote.page_start}–{quote.page_end} · {quote.quote[:80]}")
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Unchecked)
                self.quote_list.addItem(item)
        self.refresh()

    def source_unavailable(self, kind):
        if kind not in self.view.context.sources and kind in self.view.context.historical_sources:
            self.view.context.unavailable_sources.add(kind)
            self.refresh()

    def _overwrite(self, destination):
        if not Path(destination).exists():
            return False
        answer = QMessageBox.question(self.view, "确认覆盖用户选择的文件",
                                      "文件已存在。确认用当前内容替换？",
                                      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                      QMessageBox.StandardButton.No)
        return answer == QMessageBox.StandardButton.Yes

    def save(self, *_):
        return self._save_to(self.path) if self.path else self.save_as()

    def save_as(self, *_):
        selected, _ = QFileDialog.getSaveFileName(self.view, "保存本地案例（摘要与用户研究记录）",
                                                 "", "BioResearch Case (*.biocase.json)")
        return self._save_to(Path(selected)) if selected else False

    def _save_to(self, destination):
        exists = Path(destination).exists()
        overwrite = self._overwrite(destination) if exists else False
        if exists and not overwrite:
            return False
        case = self.view.context
        selected = (self.view.relationship.currentText(), self.view.basis.text())
        actual = (case.association.kind, case.association.basis) if case.association else ("未关联", "")
        if selected != actual:
            self.view.status.setText("请先确认当前关联草稿，或解除关联后再保存。")
            return False
        try:
            saved = save_case(destination, case, project_version(), overwrite=overwrite)
        except (OSError, ValueError) as exc:
            self.view.status.setText("案例保存失败，先前文件保留。 " + str(exc))
            return False
        self.path = Path(destination)
        case.created_at, case.updated_at = saved["created_at"], saved["updated_at"]
        self._clean_signature = self.signature()
        self.view.status.setText("本地案例已保存；内容摘要不提供生产者认证。")
        self.refresh()
        return True

    def confirm_discard(self):
        if not self.dirty():
            return True
        answer = QMessageBox.question(self.view, "案例有未保存修改", "保存当前案例后继续？",
                                      QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard |
                                      QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel)
        if answer == QMessageBox.StandardButton.Save:
            return self.save()
        return answer == QMessageBox.StandardButton.Discard

    def _activate(self, context, path):
        self._loading = True
        try:
            self.reset_intake()  # Invalidates all in-flight import request IDs before new state is accepted.
            self.view.context = context
            for widget, text in ((self.view.case_id, context.case_id), (self.view.topic, context.topic)):
                widget.blockSignals(True)
                widget.setText(text)
                widget.blockSignals(False)
            self.view.material.blockSignals(True)
            self.view.material.setCurrentIndex(MATERIALS.index(context.material) + 1 if context.material else 0)
            self.view.material.blockSignals(False)
            for widget, text in ((self.view.notes, context.notes), (self.view.findings, context.findings),
                                 (self.view.recommendations, context.recommendations)):
                widget.blockSignals(True)
                widget.setPlainText(text)
                widget.blockSignals(False)
            self.view._invalidate("已恢复历史记录。" if path else "已新建案例。")
            self.view._refresh_sources()
            self.path = path
            self._quotes = ()
            self.quote_list.clear()
            self._clean_signature = self.signature()
        finally:
            self._loading = False
        self.refresh()

    def new_case(self, *_):
        if self.confirm_discard():
            self._activate(CaseContext(), None)

    def open_case(self, *_):
        selected, _ = QFileDialog.getOpenFileName(self.view, "打开案例（只恢复历史记录）", "",
                                                 "BioResearch Case (*.biocase.json)")
        if not selected:
            return False
        try:
            context = load_case(selected)
        except (OSError, ValueError) as exc:
            self.view.status.setText("拒绝打开案例，当前案例保留。 " + str(exc))
            return False
        if not self.confirm_discard():
            return False
        self._activate(context, Path(selected))
        return True

    def export(self, kind):
        destination, _ = QFileDialog.getSaveFileName(self.view, "导出综合科研报告", "",
                                                    "Markdown (*.md)" if kind == "md" else "Word (*.docx)")
        if not destination:
            return False
        exists = Path(destination).exists()
        overwrite = self._overwrite(destination) if exists else False
        if exists and not overwrite:
            return False
        quotes = tuple(quote for i, quote in enumerate(self._quotes)
                       if self.quote_list.item(i).checkState() == Qt.CheckState.Checked)
        try:
            export_report(destination, kind, self.view.context, project_version(), quotes, overwrite=overwrite)
        except (OSError, ValueError, RuntimeError) as exc:
            self.view.status.setText("报告导出失败；案例和当前计算快照仍保留。 " + str(exc))
            return False
        self.view.status.setText("综合报告已导出至用户选择的本地文件。")
        return True
