"""Session overview and explicit relationship editor for imported snapshots."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
                               QPlainTextEdit, QPushButton, QVBoxLayout, QWidget)

from desktop.integrations.case_context import CaseContext, CaseSource, MATERIALS, RELATIONSHIPS, SOURCE_LABELS
from desktop.integrations.citation_groups import count_citations


def plain_label(text=""):
    label = QLabel(text)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    return label


class CaseOverview(QWidget):
    def __init__(self, sequence_getter, parent=None):
        super().__init__(parent)
        self.context = CaseContext()
        self._get_sequence = sequence_getter
        self.case_id = QLineEdit()
        self.topic = QLineEdit()
        self.material = QComboBox()
        self.material.addItems(["请选择", *MATERIALS])
        self.sources = QPlainTextEdit()
        self.sources.setReadOnly(True)
        self.sources.setMinimumHeight(88)
        self.attach_sequence = QPushButton("接入当前单条分析")
        self.clear_sequence = QPushButton("解除序列接入")
        self.relationship = QComboBox()
        self.relationship.addItems(RELATIONSHIPS)
        self.basis = QLineEdit()
        self.notes = QPlainTextEdit()
        self.notes.setPlaceholderText("本次会话的研究备注")
        self.notes.setMaximumHeight(64)
        self.apply_button = QPushButton("确认当前来源关联")
        self.unlink_button = QPushButton("解除关联")
        self.status = plain_label()
        self.status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        for editor in (self.case_id, self.topic, self.basis):
            editor.setMaxLength(500)

        layout = QVBoxLayout(self)
        layout.addWidget(plain_label("案例只保存在本次会话。关联由用户填写，分子及样品身份均未经系统验证。"))
        form = QFormLayout()
        form.addRow("案例编号", self.case_id)
        form.addRow("研究主题", self.topic)
        form.addRow("材料类型", self.material)
        layout.addLayout(form)
        actions = QHBoxLayout()
        actions.addWidget(self.attach_sequence)
        actions.addWidget(self.clear_sequence)
        actions.addStretch()
        layout.addLayout(actions)
        layout.addWidget(self.sources, 1)
        form = QFormLayout()
        form.addRow("关联全部当前接入来源", self.relationship)
        form.addRow("关联依据", self.basis)
        form.addRow("研究备注", self.notes)
        layout.addLayout(form)
        actions = QHBoxLayout()
        actions.addWidget(self.apply_button)
        actions.addWidget(self.unlink_button)
        actions.addStretch()
        layout.addLayout(actions)
        layout.addWidget(self.status)
        self.case_id.textChanged.connect(self._context_changed)
        self.topic.textChanged.connect(self._context_changed)
        self.material.currentIndexChanged.connect(self._context_changed)
        self.notes.textChanged.connect(self._notes_changed)
        self.attach_sequence.clicked.connect(self._attach_sequence)
        self.clear_sequence.clicked.connect(self.invalidate_sequence)
        self.apply_button.clicked.connect(self._apply)
        self.unlink_button.clicked.connect(self._unlink)
        self._refresh_sources()
        self.status.setText("未关联。尚无同一分子或同一样品声明。")

    def _context_changed(self, *_):
        case_id = self.case_id.text().strip()
        material = self.material.currentText() if self.material.currentIndex() else ""
        if self.context.association and (case_id, material) != (self.context.case_id, self.context.material):
            self._invalidate("案例编号或材料类型已变更，关联需重新确认。")
        self.context.case_id = case_id
        self.context.topic = self.topic.text().strip()
        self.context.material = material

    def _notes_changed(self):
        self.context.notes = self.notes.toPlainText()

    def _attach_sequence(self):
        source = self._get_sequence()
        if source is None:
            self.status.setText("请先在单条分析中完成当前序列的规则分析。")
            return
        self._set_source("sequence", source)

    def invalidate_sequence(self):
        self._set_source("sequence", None)

    def accept_external(self, kind, summary):
        source = None
        if summary is not None:
            detail = f"{summary.experiment} · {summary.state}"
            if kind == "literature":
                counts = count_citations(summary.evidence)
                detail += f" · {counts.records} 条记录，{counts.groups} 个引文组，{counts.unresolved} 条未归组"
            elif summary.elisa:
                value = summary.elisa.n_fit_levels
                detail += f" · 4PL 标准水平数 {value if value is not None else '未提供'}"
            source = CaseSource(summary.identifier, summary.manifest_sha256, detail, summary.manifest_path)
        self._set_source(kind, source)

    def _set_source(self, kind, source):
        had_link = self.context.association is not None
        if self.context.set_source(kind, source):
            self._refresh_sources()
            self._invalidate("来源已变更，请重新确认关联。" if had_link else "已更新当前来源。")

    def _refresh_sources(self):
        lines = []
        for kind, title in SOURCE_LABELS.items():
            source = self.context.sources.get(kind)
            if source is None:
                lines.append(f"{title}：未接入")
                continue
            lines.append(f"{title}：{source.identifier} · {source.summary}\n"
                         f"来源：{source.origin}\nSHA256：{source.sha256}")
        self.sources.setPlainText("\n\n".join(lines))

    def _invalidate(self, reason):
        self.context.association = None
        self.relationship.setCurrentIndex(0)
        self.basis.clear()
        self.status.setText(reason + " 当前未关联，尚无同一分子或同一样品声明。")

    def _unlink(self):
        self._invalidate("已解除关联。")

    def _apply(self):
        try:
            self.context.associate(self.relationship.currentText(), self.basis.text())
        except ValueError as exc:
            saved = self.context.association
            previous = f" 已保存关联仍为「{saved.kind}」。" if saved else " 当前未关联。"
            self.status.setText(str(exc) + previous)
            return
        link = self.context.association
        boundary = ("当前来源只同属案例，未建立共同分子或样品身份。" if link.kind == RELATIONSHIPS[1]
                    else "此身份关系为用户声明，未经系统验证。")
        self.status.setText(f"已保存：{link.kind}。{boundary} 依据：{link.basis}")
