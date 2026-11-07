"""Frozen GUI entry. No credentials, labels or model files are bundled."""
import json
import os
from pathlib import Path
import sys


def configure_paths():
    local = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local"))) / "AntibodyResearchWorkbench"
    local.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("LITERATURE_CACHE_PATH", str(local / "cache/literature.db"))
    # The installed application never writes into Program Files or inherits a
    # terminal's working directory for exports. Dialogs still choose export paths.
    return local


def main():
    local = configure_paths()
    if "--installation-smoke" in sys.argv:
        from desktop.installation_smoke import run
        report = run()
        (local / "installation-smoke.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return 0
    from desktop.main import main as desktop_main
    try:
        return desktop_main()
    except Exception as error:
        # Exception values can contain sequences/credentials; record type only.
        (local / "startup-error.txt").write_text(type(error).__name__, encoding="utf-8")
        from PySide6.QtWidgets import QApplication, QMessageBox
        app = QApplication.instance() or QApplication(sys.argv)
        QMessageBox.critical(None, "无法启动桌面工作台", "软件无法启动。请重新安装或联系维护者。错误类型：" + type(error).__name__)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
