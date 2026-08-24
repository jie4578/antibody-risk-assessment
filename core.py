# core.py
# 核心分析逻辑模块（单条序列分析）

import re

from models import AnalysisResult, RiskItem

# 风险基序数据库（不变）
RISK_MOTIFS = {
    "脱酰胺化": {
        "NG": "天冬酰胺(N)后接甘氨酸(G)，柔性最高，极易脱酰胺",
        "NS": "天冬酰胺后接丝氨酸(S)，中度风险",
        "NN": "两个天冬酰胺相连，也存在风险"
    },
    "异构化": {
        "DG": "天冬氨酸(D)后接甘氨酸(G)，极易形成异构天冬氨酸",
        "DS": "天冬氨酸后接丝氨酸(S)，中度风险",
        "DA": "天冬氨酸后接丙氨酸(A)，低风险但值得关注"
    },
    "氧化": {
        "M": "甲硫氨酸(M)，侧链硫醚易被氧化，影响活性与稳定性"
    }
}

# 标准 20 种氨基酸（统一校验白名单，单条与批量共用，禁止复制）
VALID_AMINO_ACIDS = frozenset("ACDEFGHIKLMNPQRSTVWY")


def normalize_sequence(sequence):
    """规范化序列：None → 空串；否则 strip 首尾空白并转大写。"""
    if sequence is None:
        return ""
    return str(sequence).strip().upper()


def validate_sequence(sequence, *, allow_empty=False):
    """
    统一氨基酸序列校验。返回 (是否合法, 错误信息)。
    - 自动 strip 首尾空白并转大写
    - 空 / 纯空白 → 非法（allow_empty=True 时视为合法）
    - 含非 ASCII 字符（如 é、中文）→ 非法
    - 含非字母字符（数字、标点、内部空白）→ 非法
    - 含非标准 20 种氨基酸（如 B/Z/X）→ 非法
    """
    seq = normalize_sequence(sequence)
    if not seq:
        if allow_empty:
            return True, ""
        return False, "序列为空"
    if not seq.isascii():
        return False, "序列包含非 ASCII 字符（如 Unicode 字母）"
    if not seq.isalpha():
        return False, "序列包含非字母字符"
    invalid = set(seq) - VALID_AMINO_ACIDS
    if invalid:
        return False, "序列包含非标准氨基酸: " + "".join(sorted(invalid))
    return True, ""


def annotate_cdr(seq, cdr1_s, cdr1_e, cdr2_s, cdr2_e, cdr3_s, cdr3_e):
    """根据Kabat边界手动注释CDR区域"""
    cdr_map = {}
    for i in range(len(seq)):
        if cdr1_s - 1 <= i < cdr1_e:
            cdr_map[i] = "CDR1"
        elif cdr2_s - 1 <= i < cdr2_e:
            cdr_map[i] = "CDR2"
        elif cdr3_s - 1 <= i < cdr3_e:
            cdr_map[i] = "CDR3"
        else:
            cdr_map[i] = "FW"
    return cdr_map

def analyze_sequence(sequence, cdr1_s, cdr1_e, cdr2_s, cdr2_e, cdr3_s, cdr3_e):
    """统一分析入口：扫描序列并返回 AnalysisResult。逻辑与 scan_sequence 完全一致。"""
    sequence = normalize_sequence(sequence)
    ok, err = validate_sequence(sequence, allow_empty=False)
    if not ok:
        return AnalysisResult(
            sequence=sequence,
            sequence_length=0,
            report=f"错误：{err}",
            summary="",
            risks=[],
            errors=[err],
            metadata={"cdr": _cdr_metadata(cdr1_s, cdr1_e, cdr2_s, cdr2_e, cdr3_s, cdr3_e)},
        )

    cdr_map = annotate_cdr(sequence, cdr1_s, cdr1_e, cdr2_s, cdr2_e, cdr3_s, cdr3_e)

    report_lines = []
    report_lines.append("=" * 60)
    report_lines.append("抗体序列化学稳定性风险基序扫描报告")
    report_lines.append(f"序列长度: {len(sequence)} aa")
    report_lines.append(f"CDR定义: CDR1={cdr1_s}-{cdr1_e}, CDR2={cdr2_s}-{cdr2_e}, CDR3={cdr3_s}-{cdr3_e}")
    report_lines.append("=" * 60)

    risk_items = []
    stats = {"CDR1": [], "CDR2": [], "CDR3": [], "FW": []}

    for category, motifs in RISK_MOTIFS.items():
        for motif, description in motifs.items():
            if len(motif) == 1:
                base = 0
                while True:
                    pos = sequence.find(motif, base)
                    if pos == -1:
                        break
                    region = cdr_map.get(pos, "?")
                    report_lines.append(f"[{category}] {motif} -> 位置{pos+1} | 区域:{region} | {description}")
                    risk_items.append(RiskItem(category=category, motif=motif, position=pos+1, region=region, description=description))
                    if region in stats:
                        stats[region].append(f"{motif}({pos+1})")
                    base = pos + 1
            else:
                base = 0
                while True:
                    pos = sequence.find(motif, base)
                    if pos == -1:
                        break
                    region = cdr_map.get(pos, "?")
                    report_lines.append(f"[{category}] {motif} -> 位置{pos+1}-{pos+2} | 区域:{region} | {description}")
                    risk_items.append(RiskItem(category=category, motif=motif, position=f"{pos+1}-{pos+2}", region=region, description=description))
                    if region in stats:
                        stats[region].append(f"{motif}({pos+1}-{pos+2})")
                    base = pos + 1

    # N-糖基化扫描
    glyco_pattern = r"N[^P][ST]"
    for match in re.finditer(glyco_pattern, sequence):
        start = match.start()
        end = match.end()
        region = cdr_map.get(start, "?")
        report_lines.append(f"[N-糖基化] {match.group()} -> 位置{start+1}-{end} | 区域:{region} | 潜在的N-连接糖基化位点")
        risk_items.append(RiskItem(category="N-糖基化", motif=match.group(), position=f"{start+1}-{end}", region=region, description="潜在的N-连接糖基化位点"))
        if region in stats:
            stats[region].append(f"{match.group()}({start+1}-{end})")

    if not risk_items:
        report_lines.append("未发现已知的常见风险基序")

    report_lines.append("=" * 60)

    cdr_risk_count = len(stats.get("CDR1",[])) + len(stats.get("CDR2",[])) + len(stats.get("CDR3",[]))
    summary = f"CDR区高危基序总数: {cdr_risk_count} (CDR1:{len(stats.get('CDR1',[]))}, CDR2:{len(stats.get('CDR2',[]))}, CDR3:{len(stats.get('CDR3',[]))})"

    return AnalysisResult(
        sequence=sequence,
        sequence_length=len(sequence),
        risks=risk_items,
        summary=summary,
        report="\n".join(report_lines),
        metadata={"cdr": _cdr_metadata(cdr1_s, cdr1_e, cdr2_s, cdr2_e, cdr3_s, cdr3_e)},
    )


def _cdr_metadata(cdr1_s, cdr1_e, cdr2_s, cdr2_e, cdr3_s, cdr3_e):
    return {
        "cdr1_s": cdr1_s, "cdr1_e": cdr1_e,
        "cdr2_s": cdr2_s, "cdr2_e": cdr2_e,
        "cdr3_s": cdr3_s, "cdr3_e": cdr3_e,
    }


def scan_sequence(sequence, cdr1_s, cdr1_e, cdr2_s, cdr2_e, cdr3_s, cdr3_e):
    """核心扫描函数（旧 API）。返回 (report, risks, summary)。
    risks 为 dict 列表（UI 兼容）；内部构建并转换 AnalysisResult。"""
    return analyze_sequence(sequence, cdr1_s, cdr1_e, cdr2_s, cdr2_e, cdr3_s, cdr3_e).to_legacy_tuple()

def mutate_sequence(sequence, mutation_str):
    """执行单点突变，返回突变后的序列"""
    match = re.match(r"([A-Za-z])(\d+)([A-Za-z])", mutation_str)
    if not match:
        raise ValueError(f"突变格式无效: {mutation_str}，请使用如 N55Q 的格式")
    old_aa = match.group(1).upper()
    pos = int(match.group(2)) - 1
    new_aa = match.group(3).upper()
    if old_aa not in VALID_AMINO_ACIDS:
        raise ValueError(f"突变原残基无效: {old_aa}，必须是标准 20 种氨基酸之一")
    if new_aa not in VALID_AMINO_ACIDS:
        raise ValueError(f"突变目标残基无效: {new_aa}，必须是标准 20 种氨基酸之一")
    seq = sequence.upper()
    if pos < 0 or pos >= len(seq):
        raise ValueError(f"突变位置 {pos+1} 超出序列长度 {len(seq)}")
    if seq[pos] != old_aa:
        raise ValueError(f"Expected residue {old_aa} at position {pos+1}, but found {seq[pos]}.")
    return seq[:pos] + new_aa + seq[pos+1:]

def mutate_and_rescan(sequence, mutation_str, cdr1_s, cdr1_e, cdr2_s, cdr2_e, cdr3_s, cdr3_e):
    """执行点突变并重新扫描，返回 (报告, 风险列表, 摘要, 突变后序列)"""
    try:
        mutated = mutate_sequence(sequence, mutation_str)
    except ValueError as e:
        return f"突变失败：{e}", [], "突变失败", sequence
    report, risks, summary = scan_sequence(mutated, cdr1_s, cdr1_e, cdr2_s, cdr2_e, cdr3_s, cdr3_e)
    return report, risks, summary, mutated
