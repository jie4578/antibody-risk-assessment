"""Render verified ELISA report projections without reopening any file."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QGridLayout, QLabel, QPlainTextEdit, QTabWidget, QVBoxLayout, QWidget)

from desktop.widgets.research_workflow import ResultImportPanel


def _value(value):
    if value is None:
        return "未提供"
    return format(value, ".8g") if type(value) is float else str(value)


class BioLabSummaryPanel(ResultImportPanel):
    def __init__(self, parent=None):
        super().__init__("biolab", parent)
        self.layout().removeWidget(self.details)
        tabs = QTabWidget()
        summary_view = QWidget()
        layout = QVBoxLayout(summary_view)
        self.summary_notice = QLabel()
        self.summary_notice.setWordWrap(True)
        self.summary_notice.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.summary_notice)
        metrics = QGridLayout()
        self.metrics = {}
        for n, (key, label) in enumerate((
            ("lower_asymptote", "低渐近线"), ("upper_asymptote", "高渐近线"),
            ("midpoint_concentration", "标准曲线中点"), ("slope_magnitude", "斜率幅度"),
            ("direction", "方向"), ("n_fit_levels", "拟合水平数"),
            ("r_squared", "R²"), ("rmse", "RMSE"),
            ("convergence_status", "收敛状态"), ("units", "单位（浓度 / 响应）"),
        )):
            row, col = divmod(n, 2)
            value = QLabel()
            value.setTextFormat(Qt.TextFormat.PlainText)
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            value.setWordWrap(True)
            metrics.addWidget(QLabel(label), row, 2 * col)
            metrics.addWidget(value, row, 2 * col + 1)
            self.metrics[key] = value
        layout.addLayout(metrics)
        self.qc = QPlainTextEdit()
        self.qc.setReadOnly(True)
        layout.addWidget(self.qc, 1)
        tabs.addTab(summary_view, "结果概览")
        tabs.addTab(self.details, "安全摘要 JSON")
        self.layout().addWidget(tabs, 1)
        self.snapshot_changed.connect(self._render)
        self._render(None)

    def _render(self, summary):
        elisa = summary.elisa if summary else None
        if elisa:
            self.summary_notice.setText(
                "ELISA 4PL 标准曲线｜上游报告已接入。\n"
                "curve_validated=false · validated_quantification_enabled=false")
        else:
            self.summary_notice.setText(
                "当前没有可展示的已校验 ELISA 4PL 报告指标。其他结果可在安全摘要 JSON 中查看。")
        for key, label in self.metrics.items():
            if key == "units":
                value = f"{_value(elisa.concentration_unit)} / {_value(elisa.response_unit)}" if elisa else None
            else:
                value = getattr(elisa, key) if elisa else None
            label.setText(_value(value))
        if summary:
            lines = [f"{summary.identifier} · {summary.state}",
                     "manifest SHA256: " + summary.manifest_sha256]
            if elisa:
                lines.append("report_data SHA256: " + elisa.report_data_sha256)
            lines.extend(["", "QC", *summary.warnings, "", "研究限制", *summary.limitations])
            self.qc.setPlainText("\n".join(lines))
        else:
            self.qc.clear()
