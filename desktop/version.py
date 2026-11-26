"""Read package/build metadata without changing scientific/model versions."""
from importlib.metadata import version
from pathlib import Path
import re
import sys


def project_version():
    if getattr(sys, "frozen", False):
        return (Path(sys._MEIPASS) / "VERSION.txt").read_text(encoding="ascii").strip()
    source = Path(__file__).resolve().parents[1] / "pyproject.toml"
    if source.is_file():
        metadata = source.read_text(encoding="utf-8")
        project = re.search(r"^\[project\][ \t]*\n(.*?)(?=^\[|\Z)", metadata, re.MULTILINE | re.DOTALL)
        if project and re.search(r'^name\s*=\s*"antibody-risk"\s*$', project[1], re.MULTILINE):
            match = re.search(r'^version\s*=\s*"([^"]+)"', project[1], re.MULTILINE)
            if match:
                return match[1]
    return version("antibody-risk")
