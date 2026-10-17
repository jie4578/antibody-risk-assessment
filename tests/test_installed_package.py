"""Build and import a wheel outside the source checkout, without network access."""
import importlib.util
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_installed_wheel_has_no_validation_runtime_dependency(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    for path in [ROOT / "pyproject.toml", ROOT / "README.md", *ROOT.glob("*.py")]:
        shutil.copy2(path, source / path.name)
    for package in ("desktop", "agent", "literature", "ml", "ml_inference", "rag"):
        shutil.copytree(ROOT / package, source / package, ignore=shutil.ignore_patterns("__pycache__", "artifacts"))
    result = subprocess.run([sys.executable, "-m", "pip", "wheel", "--no-deps", "--no-build-isolation", "--no-index", "--wheel-dir", str(tmp_path / "wheel"), str(source)], cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    wheel = next((tmp_path / "wheel").glob("*.whl"))
    with zipfile.ZipFile(wheel) as archive:
        assert "config.py" in archive.namelist()
        assert not any(name.startswith("validation/") for name in archive.namelist())
    smoke = "import sys; sys.path.insert(0, sys.argv[1]); import config, ml_inference, agent.llm; "
    if importlib.util.find_spec("PySide6"):
        smoke += "import desktop.main; "
    smoke += "assert not any(n == 'validation' or n.startswith('validation.') for n in sys.modules)"
    result = subprocess.run([sys.executable, "-I", "-c", smoke, str(wheel)], cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
