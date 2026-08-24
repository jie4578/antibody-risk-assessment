# tests/test_scoring.py
# A2.2：Rule-based Computational Risk Score
import math
from pathlib import Path

import pandas as pd
import pytest

from core import analyze_sequence
from models import AnalysisResult, RiskItem
from scoring import compute_risk_score, RiskScore
from batch_analysis import batch_analysis, OUTPUT_COLUMNS

BASE_DIR = Path(__file__).resolve().parent.parent
CDR = (31, 35, 50, 65, 99, 110)


def _chain_result(seq, *cdr):
    return ("VH", analyze_sequence(seq, *cdr))


def _res(items, errors=None):
    return AnalysisResult(sequence="ACD", sequence_length=3, risks=items, errors=errors or [])


def _item(category="脱酰胺化", motif="DA", position=1, region="FW", description="d"):
    return RiskItem(category=category, motif=motif, position=position, region=region, description=description)


class TestCleanSequence:
    def test_clean(self):
        s = compute_risk_score([_chain_result("EVQL", *CDR)])
        assert s.overall_score == pytest.approx(100.0)
        assert s.risk_level == "Low Risk"
        assert s.total_penalty == pytest.approx(0.0)


class TestSingleRisk:
    def test_da_framework_penalty_3(self):
        s = compute_risk_score([("VH", _res([_item(motif="DA", region="FW")]))])
        assert s.total_penalty == pytest.approx(3.0)
        assert s.overall_score == pytest.approx(97.0)


class TestRegionWeighting:
    def test_cdr_equals_fw_times_13(self):
        cdr = compute_risk_score([("VH", _res([_item(motif="DA", region="CDR2")]))])
        fw = compute_risk_score([("VH", _res([_item(motif="DA", region="FW")]))])
        assert cdr.total_penalty == pytest.approx(fw.total_penalty * 1.3)


class TestDiminishing:
    def test_five_same_motifs_sublinear(self):
        items = [_item(motif="M", position=i) for i in range(1, 6)]
        s = compute_risk_score([("VH", _res(items))])
        assert s.total_penalty == pytest.approx(4.0 + 2.0 * 4)  # 12
        assert s.total_penalty < 5 * 4.0


class TestInvariants:
    def _mixed(self):
        items = [
            _item(category="N-糖基化", motif="NGS", position="1-3", region="CDR2"),
            _item(motif="NG", position=10, region="CDR1"),
            _item(motif="M", position=20, region="FW"),
            _item(motif="M", position=21, region="FW"),
        ]
        return compute_risk_score([("VH", _res(items))])

    def test_category_invariant(self):
        s = self._mixed()
        assert sum(s.category_breakdown.values()) == pytest.approx(s.total_penalty)

    def test_region_invariant(self):
        s = self._mixed()
        assert sum(s.region_breakdown.values()) == pytest.approx(s.total_penalty)

    def test_score_invariant(self):
        s = self._mixed()
        assert s.overall_score == pytest.approx(100 - s.total_penalty)


class TestNGlycosylation:
    def test_ptm_and_cdr_both_hold_penalty_once(self):
        s = compute_risk_score([("VH", _res([_item(category="N-糖基化", motif="NGS", position="1-3", region="CDR2")]))])
        pen = 9.0 * 1.3
        assert s.category_breakdown["PTM"] == pytest.approx(pen)
        assert s.region_breakdown["CDR"] == pytest.approx(pen)
        assert s.total_penalty == pytest.approx(pen)  # total 只加一次


class TestOverlappingMotifs:
    def test_nns_counts_three_events(self):
        s = compute_risk_score([_chain_result("NNS", *CDR)])
        assert len(s.contributing_factors) == 3
        assert s.total_penalty == pytest.approx(4.0 + 5.0 + 9.0)  # NN + NS + N-糖基化


class TestClamp:
    def test_score_never_below_zero(self):
        items = [_item(motif="M", position=i) for i in range(1, 61)]
        s = compute_risk_score([("VH", _res(items))])
        assert s.total_penalty > 100
        assert s.overall_score == pytest.approx(0.0)
        assert s.overall_score >= 0


class TestInvalidChains:
    def test_both_invalid_nan(self):
        s = compute_risk_score([("VH", None), ("VL", _res([], errors=["序列为空"]))])
        assert math.isnan(s.overall_score)
        assert s.risk_level == "N/A"

    def test_single_invalid_uses_valid_chain(self):
        s = compute_risk_score([("VH", None), ("VL", _res([_item(motif="DA")]))])
        assert s.overall_score == pytest.approx(97.0)
        assert "VH sequence invalid" in s.contributing_factors


class TestUnknownCategory:
    def test_unknown_penalty_zero(self):
        s = compute_risk_score([("VH", _res([_item(category="未知", motif="XX")]))])
        assert s.total_penalty == pytest.approx(0.0)
        assert s.overall_score == pytest.approx(100.0)
        assert any("penalty 0" in f for f in s.contributing_factors)


class TestToDict:
    def test_to_dict_flat(self):
        s = compute_risk_score([("VH", _res([_item(motif="DA")]))])
        d = s.to_dict()
        assert d["overall_score"] == s.overall_score
        assert d["risk_level"] == s.risk_level
        assert set(d.keys()) == {
            "overall_score", "risk_level", "total_penalty",
            "category_breakdown", "region_breakdown", "contributing_factors",
        }


class TestBatchColumns:
    def test_new_columns_present_and_old_kept(self):
        df = pd.DataFrame([{"antibody_id": "A", "VH": "ACD", "VL": "ACD"}])
        result = batch_analysis(df)
        assert "risk_score" in result.columns
        assert "risk_level" in result.columns
        assert list(result.columns) == OUTPUT_COLUMNS
        assert len(OUTPUT_COLUMNS) == 14
        assert result.iloc[0]["risk_score"] == pytest.approx(100.0)
        assert result.iloc[0]["risk_level"] == "Low Risk"

    def test_batch_rows_have_expected_scores(self):
        result = batch_analysis(pd.read_csv(BASE_DIR / "example_antibodies.csv"))
        ab1 = result[result["antibody_id"] == "AB001"].iloc[0]
        ab2 = result[result["antibody_id"] == "AB002"].iloc[0]
        ab6 = result[result["antibody_id"] == "AB006_RISK"].iloc[0]
        bad = result[result["antibody_id"] == "AB007_BAD"].iloc[0]
        assert ab1["risk_score"] == pytest.approx(64.3, abs=0.02)
        assert ab1["risk_level"] == "Medium Risk"
        assert ab2["risk_score"] == pytest.approx(74.0, abs=0.02)
        assert ab2["risk_level"] == "Medium Risk"
        assert ab6["risk_score"] == pytest.approx(48.95, abs=0.05)
        assert ab6["risk_level"] == "High Risk"
        assert bad["risk_score"] == pytest.approx(96.0, abs=0.02)  # 仅 VL 合法链计分
        assert bad["risk_level"] == "Low Risk"


class TestRealExamples:
    def _load(self):
        return pd.read_csv(BASE_DIR / "example_antibodies.csv")

    def test_ab001(self):
        row = self._load()[self._load()["antibody_id"] == "AB001"].iloc[0]
        s = compute_risk_score([("VH", analyze_sequence(row["VH"], *CDR)), ("VL", analyze_sequence(row["VL"], *CDR))])
        assert s.overall_score == pytest.approx(64.3, abs=0.02)
        assert s.risk_level == "Medium Risk"
        assert s.total_penalty == pytest.approx(35.7, abs=0.02)
        assert s.category_breakdown["PTM"] == pytest.approx(0.0, abs=0.02)
        assert s.category_breakdown["Chemical Liability"] == pytest.approx(35.7, abs=0.02)
        assert s.region_breakdown["CDR"] == pytest.approx(24.7, abs=0.02)
        assert s.region_breakdown["Framework"] == pytest.approx(11.0, abs=0.02)

    def test_ab002(self):
        df = self._load()
        row = df[df["antibody_id"] == "AB002"].iloc[0]
        s = compute_risk_score([("VH", analyze_sequence(row["VH"], *CDR)), ("VL", analyze_sequence(row["VL"], *CDR))])
        assert s.overall_score == pytest.approx(74.0, abs=0.02)
        assert s.risk_level == "Medium Risk"
        assert s.total_penalty == pytest.approx(26.0, abs=0.02)
        assert s.region_breakdown["CDR"] == pytest.approx(13.0, abs=0.02)
        assert s.region_breakdown["Framework"] == pytest.approx(13.0, abs=0.02)

    def test_ab006_risk(self):
        df = self._load()
        row = df[df["antibody_id"] == "AB006_RISK"].iloc[0]
        s = compute_risk_score([("VH", analyze_sequence(row["VH"], *CDR)), ("VL", analyze_sequence(row["VL"], *CDR))])
        assert s.overall_score == pytest.approx(48.95, abs=0.05)
        assert s.risk_level == "High Risk"
        assert s.total_penalty == pytest.approx(51.05, abs=0.05)
        assert s.region_breakdown["CDR"] == pytest.approx(37.05, abs=0.05)
        assert s.region_breakdown["Framework"] == pytest.approx(14.0, abs=0.05)
