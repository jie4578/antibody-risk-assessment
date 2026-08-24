# tests/test_integration.py
# A4：端到端集成测试 —— 完整链路：
#   输入文件 → input_parser → DataFrame → batch_analysis → risk_score / risk_level
# 不调用 Gradio UI、不调用 LLM、不需要网络，完全确定性。
from pathlib import Path

import pandas as pd
import pytest

from batch_analysis import batch_analysis, OUTPUT_COLUMNS
from input_parser import load_batch_input

BASE_DIR = Path(__file__).resolve().parent.parent

ALL_IDS = {"AB001", "AB002", "AB003", "AB004", "AB005", "AB006_RISK", "AB007_BAD"}


def _all_format_inputs(tmp_path):
    """把 example_antibodies.csv 分别序列化为 CSV / XLSX / FASTA 三个文件，返回路径。"""
    src = pd.read_csv(BASE_DIR / "example_antibodies.csv")

    csv_p = tmp_path / "data.csv"
    src.to_csv(csv_p, index=False)

    xlsx_p = tmp_path / "data.xlsx"
    src.to_excel(xlsx_p, index=False)

    lines = []
    for _, r in src.iterrows():
        lines.append(f">{r['antibody_id']}_VH\n{r['VH']}\n")
        lines.append(f">{r['antibody_id']}_VL\n{r['VL']}\n")
    fasta_p = tmp_path / "data.fasta"
    fasta_p.write_text("".join(lines), encoding="utf-8")

    return csv_p, xlsx_p, fasta_p


class TestPipeline:
    def test_csv_full_pipeline(self, tmp_path):
        csv_p, _, _ = _all_format_inputs(tmp_path)
        result = batch_analysis(load_batch_input(csv_p))
        assert list(result.columns) == OUTPUT_COLUMNS
        assert len(result) == len(ALL_IDS)
        assert set(result["antibody_id"]) == ALL_IDS

    def test_all_formats_full_output_identical(self, tmp_path):
        """三种输入格式产出的完整 14 列结果必须逐列一致（含 warnings / 长度）。"""
        csv_p, xlsx_p, fasta_p = _all_format_inputs(tmp_path)
        ref = batch_analysis(load_batch_input(csv_p)).sort_values("antibody_id").reset_index(drop=True)
        for p in (xlsx_p, fasta_p):
            got = batch_analysis(load_batch_input(p)).sort_values("antibody_id").reset_index(drop=True)
            pd.testing.assert_frame_equal(ref, got)

    def test_expected_scores_and_status(self, tmp_path):
        csv_p, _, _ = _all_format_inputs(tmp_path)
        result = batch_analysis(load_batch_input(csv_p))
        expected = {
            "AB001": (64.30, "Medium Risk", "success"),
            "AB002": (74.00, "Medium Risk", "success"),
            "AB006_RISK": (48.95, "High Risk", "success"),
            "AB007_BAD": (96.00, "Low Risk", "partial_error"),
        }
        for aid, (score, level, status) in expected.items():
            row = result[result["antibody_id"] == aid].iloc[0]
            assert row["risk_score"] == pytest.approx(score, abs=0.02)
            assert row["risk_level"] == level
            assert row["analysis_status"] == status
