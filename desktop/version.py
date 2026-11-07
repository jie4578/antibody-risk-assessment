"""Read package/build metadata without changing scientific/model versions."""
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
import re
import sys


def project_version():
    if getattr(sys, "frozen", False):
        return (Path(sys._MEIPASS) / "VERSION.txt").read_text(encoding="ascii").strip()
    try:
        return version("antibody-risk")
    except PackageNotFoundError:
        metadata = (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(encoding="utf-8")
        return re.search(r'^version\s*=\s*"([^"]+)"', metadata, re.MULTILINE).group(1)
