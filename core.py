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

# ---------- v2.0 PTM / Glycosylation 常量 ----------
# O-糖基化（启发式候选，未经实验验证）
O_GLYCO_CATEGORY = "O-糖基化"
O_GLYCO_WINDOW = 7
O_GLYCO_MIN_ST_FRACTION = 6 / 7
# N-糖基化上下文侧翼长度（命中位点前后 ±3 aa）
N_GLYCO_CONTEXT_FLANK = 3
# 证据级别
EV_RULE_BASED = "rule_based"
EV_HEURISTIC = "heuristic"


def find_o_glycosylation_hotspots(
    sequence,
    window=O_GLYCO_WINDOW,
    min_st_fraction=O_GLYCO_MIN_ST_FRACTION,
):
    """
    启发式 O-糖基化热点检测（heuristic candidate，未经实验验证）。

    规则：
      - 滑动"完整 window aa 窗口"（默认 7 aa）
      - 窗口内 S/T 占比 >= min_st_fraction（默认 6/7）→ 视为 S/T 富集区
      - 富集区内的 S/T 残基标记为候选热点
      - SP / TP 抑制：S/T 后紧跟 P 的位点被排除（GalNAc-T 抑制）
      - 同一位点落在多个窗口时去重

    返回:
        list[dict]，每个元素:
          position      1-based 位置
          residue       'S' 或 'T'
          st_fraction   该位点所在窗口的 S/T 占比
          window_start  窗口起点(1-based)
          window_end    窗口终点(1-based，含)
          segment       窗口内 7 aa 片段
    """
    seq = str(sequence or "").upper()
    n = len(seq)
    if n < window:
        return []
    found = {}
    for start in range(0, n - window + 1):
        segment = seq[start:start + window]
        st_count = sum(1 for c in segment if c in ("S", "T"))
        if st_count / window < min_st_fraction:
            continue
        for offset, aa in enumerate(segment):
            pos = start + offset
            if aa not in ("S", "T"):
                continue
            # SP / TP 抑制：S/T 后紧跟 P
            if pos + 1 < n and seq[pos + 1] == "P":
                continue
            found[pos] = {
                "position": pos + 1,
                "residue": aa,
                "st_fraction": round(st_count / window, 3),
                "window_start": start + 1,
                "window_end": start + window,
                "segment": segment,
            }
    return [found[k] for k in sorted(found)]


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
    report_lines.append("抗体序列化学稳定性风险基序扫描报告")
    report_lines.append(f"序列长度: {len(sequence)} aa")
    report_lines.append(f"CDR定义: CDR1={cdr1_s}-{cdr1_e}, CDR2={cdr2_s}-{cdr2_e}, CDR3={cdr3_s}-{cdr3_e}")
    report_lines.append("")

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

    # N-糖基化扫描（规则：N-X-S/T，X != P；context = 命中位点前后 ±3 aa）
    glyco_pattern = r"N[^P][ST]"
    for match in re.finditer(glyco_pattern, sequence):
        start = match.start()
        end = match.end()
        region = cdr_map.get(start, "?")
        context = sequence[max(0, start - N_GLYCO_CONTEXT_FLANK): min(len(sequence), end + N_GLYCO_CONTEXT_FLANK)]
        report_lines.append(f"[N-糖基化] {match.group()} -> 位置{start+1}-{end} | 区域:{region} | 潜在的N-连接糖基化位点")
        risk_items.append(RiskItem(
            category="N-糖基化", motif=match.group(), position=f"{start+1}-{end}", region=region,
            description="潜在的N-连接糖基化位点", context=context, evidence_level=EV_RULE_BASED,
        ))
        if region in stats:
            stats[region].append(f"{match.group()}({start+1}-{end})")

    # O-糖基化热点扫描（heuristic candidate，未经实验验证）
    for hot in find_o_glycosylation_hotspots(sequence):
        pos = hot["position"]
        region = cdr_map.get(pos - 1, "?")
        context = sequence[max(0, pos - 1 - N_GLYCO_CONTEXT_FLANK): min(len(sequence), pos + N_GLYCO_CONTEXT_FLANK)]
        report_lines.append(
            f"[O-糖基化] {hot['residue']} -> 位置{pos} | 区域:{region} | S/T富集区域候选(heuristic,未经实验验证)"
        )
        risk_items.append(RiskItem(
            category=O_GLYCO_CATEGORY, motif=hot["residue"], position=pos, region=region,
            description="S/T 富集区域候选 O-糖基化位点（heuristic，未经实验验证）",
            context=context, evidence_level=EV_HEURISTIC,
        ))
        if region in stats:
            stats[region].append(f"{hot['residue']}({pos})")

    if not risk_items:
        report_lines.append("未发现已知的常见风险基序")

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
