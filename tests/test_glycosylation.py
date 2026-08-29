# tests/test_glycosylation.py
# v2.0 PTM / Glycosylation 升级测试：N/O-糖基化、context、evidence_level、打分、mutation、batch。

import pandas as pd
import pytest

from core import analyze_sequence, mutate_sequence
from models import RiskItem
from scoring import compute_risk_score

# 默认 CDR 边界（与 app/batch 一致）
CDR = (31, 35, 50, 65, 99, 110)


def _analyze(seq):
    return analyze_sequence(seq, *CDR)


# ---------- 1. N-X-S/T 正常命中 ----------
def test_n_glycosylation_hit():
    result = _analyze("ACDEFGNSTACDEF")  # NST 在 7-9
    glyco = [r for r in result.risks if r.category == "N-糖基化"]
    assert len(glyco) == 1
    assert glyco[0].motif == "NST"
    assert glyco[0].position == "7-9"


# ---------- 2. X=P 不命中 ----------
def test_n_glycosylation_x_is_proline_not_hit():
    result = _analyze("ACDEFGNPSTACDE")  # NPS: X=P → 不命中
    glyco = [r for r in result.risks if r.category == "N-糖基化"]
    assert len(glyco) == 0


# ---------- 3. N-glycosylation context 正确 ----------
def test_n_glycosylation_context():
    result = _analyze("ACDEFGNSTACDEF")  # NST 在 7-9，context = ±3
    glyco = [r for r in result.risks if r.category == "N-糖基化"][0]
    assert glyco.context == "EFGNSTACD"  # 0-based 3..11


# ---------- 4. O-glycosylation hotspot 命中 ----------
def test_o_glycosylation_hotspot_hit():
    result = _analyze("AAASSSSSSAAA")  # 6 个连续 S
    ogly = [r for r in result.risks if r.category == "O-糖基化"]
    assert len(ogly) == 6
    positions = sorted(r.position for r in ogly)
    assert positions == [4, 5, 6, 7, 8, 9]
    assert all(r.motif == "S" for r in ogly)


# ---------- 5. 普通低 S/T 区域不命中 ----------
def test_o_glycosylation_low_st_not_hit():
    result = _analyze("ACDEFGHIKLMNPQRSTVWYACDE")  # S/T 稀疏
    ogly = [r for r in result.risks if r.category == "O-糖基化"]
    assert len(ogly) == 0


# ---------- 6. SP/TP 抑制 ----------
def test_o_glycosylation_sp_tp_suppression():
    result = _analyze("SSSPSSS")  # 第 3 位 S 后接 P → 抑制
    ogly = [r for r in result.risks if r.category == "O-糖基化"]
    positions = sorted(r.position for r in ogly)
    assert positions == [1, 2, 5, 6, 7]  # S@3 后接 P 被抑制，其余命中


# ---------- 7. RiskItem.context ----------
def test_riskitem_context_field():
    result = _analyze("ACDEFGNSTACDEF")
    glyco = [r for r in result.risks if r.category == "N-糖基化"][0]
    assert isinstance(glyco.context, str)
    assert "NST" in glyco.context


# ---------- 8. evidence_level ----------
def test_evidence_level_rule_and_heuristic():
    result = _analyze("ACDEFGNSTACDEFAAASSSSSSAAA")
    n_glyco = [r for r in result.risks if r.category == "N-糖基化"]
    o_glyco = [r for r in result.risks if r.category == "O-糖基化"]
    assert n_glyco and all(r.evidence_level == "rule_based" for r in n_glyco)
    assert o_glyco and all(r.evidence_level == "heuristic" for r in o_glyco)


# ---------- 9. O-glycosylation scoring ----------
def test_o_glycosylation_scoring():
    result = _analyze("AAASSSSSSAAA")  # 6 个 O-糖基化(S)，base 2.0，递减惩罚
    score = compute_risk_score([("VH", result)])
    # 第 1 个 S 全额 2.0，后续 5 个 ×0.5 = 1.0 → total = 2.0 + 5.0 = 7.0
    assert score.overall_score == pytest.approx(93.0)
    assert score.category_breakdown["PTM"] == pytest.approx(7.0)


# ---------- 10. mutation 消除 N-glycosylation ----------
def test_mutation_eliminates_n_glycosylation():
    orig = _analyze("ACDEFGNSTACDEF")
    assert any(r.category == "N-糖基化" for r in orig.risks)
    mutated = mutate_sequence("ACDEFGNSTACDEF", "N7Q")  # N→Q 破坏 sequon
    after = _analyze(mutated)
    assert not any(r.category == "N-糖基化" for r in after.risks)


# ---------- 11. mutation 新增 N-glycosylation ----------
def test_mutation_creates_n_glycosylation():
    orig = _analyze("ACDEFGAASTACDEF")
    assert not any(r.category == "N-糖基化" for r in orig.risks)
    mutated = mutate_sequence("ACDEFGAASTACDEF", "A7N")  # 位置 7 → N，形成 N-A-S
    after = _analyze(mutated)
    assert any(r.category == "N-糖基化" for r in after.risks)


# ---------- 12. batch 将 O-glycosylation 计入 PTM_risk_count ----------
def test_batch_counts_o_glycosylation_as_ptm():
    from batch_analysis import batch_analysis

    df = pd.DataFrame([{
        "antibody_id": "OG01",
        "VH": "AAASSSSSSAAA",
        "VL": "ACDEFGHIKLNPQRSTVWY",  # 无 M/无已知 liability 基序
    }])
    out = batch_analysis(df)
    row = out.iloc[0]
    assert row["PTM_risk_count"] == 6  # 6 个 O-糖基化计入 PTM
    assert row["liability_risk_count"] == 0


# ---------- 13. 旧 to_dict() 仍然只有 5 个键 ----------
def test_to_dict_still_five_keys():
    item = RiskItem(category="N-糖基化", motif="NST", position="7-9", region="FW", description="d")
    d = item.to_dict()
    assert set(d.keys()) == {"类别", "基序", "位置", "区域", "描述"}


# ---------- 14. to_detail_dict() 包含 context 和 evidence_level ----------
def test_to_detail_dict_includes_new_fields():
    item = RiskItem(category="O-糖基化", motif="S", position=4, region="FW",
                    description="d", context="ASSSSS", evidence_level="heuristic")
    d = item.to_detail_dict()
    assert set(d.keys()) == {"类别", "基序", "位置", "区域", "描述", "上下文", "证据级别"}
    assert d["上下文"] == "ASSSSS"
    assert d["证据级别"] == "heuristic"
