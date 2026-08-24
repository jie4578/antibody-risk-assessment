# tests/test_models.py
# A2.1：统一分析结果模型（AnalysisResult / RiskItem）与旧 API 兼容性
import pandas as pd

from core import analyze_sequence, scan_sequence, mutate_and_rescan
from batch_analysis import batch_analysis, OUTPUT_COLUMNS
from models import AnalysisResult, RiskItem

VH = "EVQLVESGGGLVQPGGSLRLSCAASGFNIKDTYIHWVRQAPGKGLEWVARIYPTNGYTRYADSVKGRFTISADTSKNTAYLQMNSLRAEDTAVYYCSRWGGDGFYAMDYWGQGTLVTVSS"


def _cdr_defaults():
    return (31, 35, 50, 65, 99, 110)


class TestRiskItem:
    def test_construct(self):
        item = RiskItem(category="氧化", motif="M", position=55, region="CDR2", description="d")
        assert item.category == "氧化"
        assert item.motif == "M"
        assert item.position == 55
        assert item.region == "CDR2"

    def test_to_dict_uses_chinese_keys(self):
        item = RiskItem(category="氧化", motif="M", position=55, region="CDR2", description="d")
        d = item.to_dict()
        assert set(d.keys()) == {"类别", "基序", "位置", "区域", "描述"}
        assert d["类别"] == "氧化"
        assert d["位置"] == 55

    def test_from_dict_roundtrip(self):
        d = {"类别": "脱酰胺化", "基序": "NG", "位置": "31-32", "区域": "CDR1", "描述": "x"}
        assert RiskItem.from_dict(d).to_dict() == d


class TestAnalysisResult:
    def test_defaults(self):
        r = AnalysisResult()
        assert r.sequence == ""
        assert r.sequence_length == 0
        assert r.risks == []
        assert r.summary == ""
        assert r.report == ""
        assert r.warnings == []
        assert r.errors == []
        assert r.metadata == {}

    def test_construct(self):
        r = AnalysisResult(sequence="ACD", sequence_length=3, summary="s", report="r")
        assert r.sequence_length == 3
        assert r.summary == "s"

    def test_to_legacy_tuple(self):
        r = AnalysisResult(
            report="rep",
            risks=[RiskItem(category="氧化", motif="M", position=1, region="FW", description="d")],
            summary="sum",
        )
        report, risks, summary = r.to_legacy_tuple()
        assert report == "rep"
        assert summary == "sum"
        assert risks == [{"类别": "氧化", "基序": "M", "位置": 1, "区域": "FW", "描述": "d"}]

    def test_empty_risks_representable(self):
        result = analyze_sequence("EVQL", *_cdr_defaults())
        assert result.risks == []
        assert "未发现" in result.report
        assert result.sequence_length == 4
        assert result.errors == []

    def test_errors_representable(self):
        result = analyze_sequence("ACDé", *_cdr_defaults())
        assert result.errors
        assert result.risks == []
        assert result.summary == ""
        assert result.sequence_length == 0

    def test_warnings_representable(self):
        result = AnalysisResult(sequence="ACD", warnings=["VH 序列为空"])
        assert result.warnings == ["VH 序列为空"]


class TestLegacyCompatibility:
    def test_scan_sequence_behavior_unchanged(self):
        report, risks, summary = scan_sequence(VH, *_cdr_defaults())
        assert isinstance(report, str)
        assert isinstance(risks, list)
        assert isinstance(summary, str)
        assert all(isinstance(r, dict) for r in risks)
        assert "序列长度" in report

    def test_scan_sequence_matches_model_legacy_tuple(self):
        assert analyze_sequence(VH, *_cdr_defaults()).to_legacy_tuple() == scan_sequence(VH, *_cdr_defaults())

    def test_invalid_scan_sequence_unchanged(self):
        assert scan_sequence("", *_cdr_defaults()) == ("错误：序列为空", [], "")

    def test_mutation_behavior_unchanged(self):
        out = mutate_and_rescan(VH, "N55Q", *_cdr_defaults())
        assert isinstance(out, tuple) and len(out) == 4
        report, risks, summary, mutated = out
        assert mutated[54] == "Q"
        assert isinstance(risks, list)
        assert isinstance(report, str)
        assert isinstance(summary, str)

    def test_batch_schema_unchanged(self):
        df = pd.DataFrame([{"antibody_id": "A", "VH": VH, "VL": VH}])
        result = batch_analysis(df)
        assert list(result.columns) == OUTPUT_COLUMNS
        assert result.iloc[0]["analysis_status"] == "success"
        assert result.iloc[0]["total_risk_count"] > 0

    def test_batch_still_handles_invalid(self):
        df = pd.DataFrame([{"antibody_id": "A", "VH": "ACDX", "VL": VH}])
        result = batch_analysis(df)
        assert result.iloc[0]["analysis_status"] == "partial_error"
        assert "非标准氨基酸" in result.iloc[0]["warnings"]
