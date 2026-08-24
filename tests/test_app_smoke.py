# tests/test_app_smoke.py
# A4：app 模块导入 smoke + 批量 wrapper 端到端。
# 只 import app（构建 Gradio Blocks），不启动服务、不联网、不调用 LLM。
import os
from pathlib import Path

import pandas as pd
import pytest

from batch_analysis import cleanup_result_csv

BASE_DIR = Path(__file__).resolve().parent.parent


class _FakeFile:
    """模拟 Gradio File 组件传入的 file_obj（wrapper 只用到 .name）。"""

    def __init__(self, name):
        self.name = name


def test_app_import_builds_demo():
    import app

    assert hasattr(app, "demo")
    assert hasattr(app, "batch_analysis_wrapper")
    assert hasattr(app, "RISK_HEADERS")


def test_batch_wrapper_fasta_end_to_end(tmp_path):
    import app

    src = pd.read_csv(BASE_DIR / "example_antibodies.csv")
    ab1 = src[src["antibody_id"] == "AB001"].iloc[0]
    fasta = tmp_path / "ab.fasta"
    fasta.write_text(
        f">AB001_VH\n{ab1['VH']}\n>AB001_VL\n{ab1['VL']}\n",
        encoding="utf-8",
    )

    df, path = app.batch_analysis_wrapper(_FakeFile(str(fasta)), 31, 35, 50, 65, 99, 110)
    try:
        assert len(df) == 1
        row = df.iloc[0]
        assert row["risk_score"] == pytest.approx(64.30, abs=0.02)
        assert row["risk_level"] == "Medium Risk"
        assert row["analysis_status"] == "success"
        assert os.path.isfile(path)
        saved = pd.read_csv(path)
        assert list(saved.columns) == list(df.columns)
        assert len(saved.columns) == 14
    finally:
        cleanup_result_csv(path)


def test_batch_wrapper_no_file_returns_empty():
    import app

    df, path = app.batch_analysis_wrapper(None, 31, 35, 50, 65, 99, 110)
    assert df.empty
    assert path is None


def test_batch_wrapper_unsupported_format_warns(tmp_path):
    import app

    bad = tmp_path / "data.txt"
    bad.write_text("not a supported format", encoding="utf-8")

    df, path = app.batch_analysis_wrapper(_FakeFile(str(bad)), 31, 35, 50, 65, 99, 110)
    assert df.empty
    assert path is None
