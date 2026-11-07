"""User-selected deployment directories; no installer, loader or model execution."""
from PySide6.QtCore import QThreadPool, Signal
from PySide6.QtWidgets import QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout

from desktop.ml_deployment import inspect_deployment, load_config, save_config, MESSAGES
from desktop.workers import Worker


class MLDeploymentPanel(QGroupBox):
    deployment_changed = Signal()

    def __init__(self, parent=None):
        super().__init__("可选 ML 部署检查（基础功能不需要）", parent)
        saved = load_config()
        self.artifact_dir = QLineEdit(saved.get("artifact_dir", ""))
        self.hf_home = QLineEdit(saved.get("hf_home", ""))
        self.trust = QLineEdit(saved.get("trusted_manifest_sha256", ""))
        self.trust.setPlaceholderText("维护者通过独立可信渠道确认的 manifest SHA256；不是文件自带的摘要")
        self.status = QLabel(MESSAGES["NOT_INSTALLED"] if not saved else "已保存部署位置。请点击检查；不会加载模型、推理或下载。")
        self.status.setWordWrap(True)
        form = QFormLayout()
        for label, editor in (("冻结模型目录", self.artifact_dir), ("Hugging Face 缓存根目录", self.hf_home)):
            row = QHBoxLayout(); row.addWidget(editor)
            button = QPushButton("选择目录")
            button.clicked.connect(lambda checked=False, field=editor: self._choose(field))
            row.addWidget(button); form.addRow(label, row)
        form.addRow("独立可信 manifest SHA256", self.trust)
        self.check_button = QPushButton("检查并保存部署配置")
        self.check_button.clicked.connect(self.check)
        self._worker = None
        layout = QVBoxLayout(self); layout.addLayout(form)
        notice = QLabel("基础安装包不含 PyTorch、ESM2 或冻结模型，不能通过导入模型包补齐依赖。高级 ML 需单独验收的源码环境。\n"
                        "joblib/pickle 可能执行代码，来源不明的文件不可使用；检查只验证静态前提，不证明模型有效性。\n"
                        "没有公开授权的模型包时，请保留 ML 为可选功能。不要运行模型构建器，不会自动训练或下载。")
        notice.setWordWrap(True); layout.addWidget(notice); layout.addWidget(self.check_button); layout.addWidget(self.status)
        for editor in (self.artifact_dir, self.hf_home, self.trust):
            editor.textChanged.connect(self._invalidate)

    def _choose(self, field):
        value = QFileDialog.getExistingDirectory(self, "选择本地可信目录", field.text())
        if value: field.setText(value)

    def values(self):
        return {"artifact_dir": self.artifact_dir.text().strip(), "hf_home": self.hf_home.text().strip(), "trusted_manifest_sha256": self.trust.text().strip()}

    def _invalidate(self):
        self.status.setText("配置已编辑，先前检查已失效。请重新检查并保存。")

    def check(self):
        if self._worker is not None: return
        snapshot = self.values()
        self.status.setText("正在离线检查文件和部署前提…（不加载模型）")
        self.check_button.setEnabled(False)
        self._worker = Worker(inspect_deployment, snapshot)
        self._worker.signals.finished.connect(lambda report: self._done(snapshot, report))
        self._worker.signals.error.connect(lambda _: self._done(snapshot, {"status": "ERROR", "message": MESSAGES["ERROR"]}))
        QThreadPool.globalInstance().start(self._worker)

    def _done(self, snapshot, report):
        self._worker = None; self.check_button.setEnabled(True)
        if snapshot != self.values():
            self._invalidate(); return
        try:
            save_config(snapshot)
        except OSError:
            self.status.setText("无法保存部署配置，请检查用户目录权限。"); return
        missing = [name for name, value in report.get("dependencies", {}).items() if not value]
        self.status.setText(f"{report['status']}：{report['message']}" + ("\n缺少依赖：" + ", ".join(missing) if missing else ""))
        self.deployment_changed.emit()
