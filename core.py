# core.py
# 核心分析逻辑模块

import re

# 风险基序数据库
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

def scan_sequence(sequence, cdr1_s, cdr1_e, cdr2_s, cdr2_e, cdr3_s, cdr3_e):
    """核心扫描函数，返回报告文本和风险列表"""
    if not sequence or not sequence.isalpha():
        return "错误：请输入有效的氨基酸序列", [], ""
    
    sequence = sequence.upper()
    cdr_map = annotate_cdr(sequence, cdr1_s, cdr1_e, cdr2_s, cdr2_e, cdr3_s, cdr3_e)
    
    report_lines = []
    report_lines.append("=" * 60)
    report_lines.append("抗体序列化学稳定性风险基序扫描报告")
    report_lines.append(f"序列长度: {len(sequence)} aa")
    report_lines.append(f"CDR定义: CDR1={cdr1_s}-{cdr1_e}, CDR2={cdr2_s}-{cdr2_e}, CDR3={cdr3_s}-{cdr3_e}")
    report_lines.append("=" * 60)
    
    risks_found = []
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
                    line = f"[{category}] {motif} -> 位置{pos+1} | 区域:{region} | {description}"
                    report_lines.append(line)
                    risks_found.append({"类别": category, "基序": motif, "位置": pos+1, "区域": region, "描述": description})
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
                    line = f"[{category}] {motif} -> 位置{pos+1}-{pos+2} | 区域:{region} | {description}"
                    report_lines.append(line)
                    risks_found.append({"类别": category, "基序": motif, "位置": f"{pos+1}-{pos+2}", "区域": region, "描述": description})
                    if region in stats:
                        stats[region].append(f"{motif}({pos+1}-{pos+2})")
                    base = pos + 1
    
    # N-糖基化扫描
    glyco_pattern = r"N[^P][ST]"
    for match in re.finditer(glyco_pattern, sequence):
        start = match.start()
        end = match.end()
        region = cdr_map.get(start, "?")
        line = f"[N-糖基化] {match.group()} -> 位置{start+1}-{end} | 区域:{region} | 潜在的N-连接糖基化位点"
        report_lines.append(line)
        risks_found.append({"类别": "N-糖基化", "基序": match.group(), "位置": f"{start+1}-{end}", "区域": region, "描述": "潜在的N-连接糖基化位点"})
        if region in stats:
            stats[region].append(f"{match.group()}({start+1}-{end})")
    
    if not risks_found:
        report_lines.append("未发现已知的常见风险基序")
    
    report_lines.append("=" * 60)
    
    cdr_risk_count = len(stats.get("CDR1",[])) + len(stats.get("CDR2",[])) + len(stats.get("CDR3",[]))
    summary = f"CDR区高危基序总数: {cdr_risk_count} (CDR1:{len(stats.get('CDR1',[]))}, CDR2:{len(stats.get('CDR2',[]))}, CDR3:{len(stats.get('CDR3',[]))})"
    
    return "\n".join(report_lines), risks_found, summary

def mutate_sequence(sequence, mutation_str):
    """执行单点突变，返回突变后的序列"""
    match = re.match(r"([A-Za-z])(\d+)([A-Za-z])", mutation_str)
    if not match:
        raise ValueError(f"突变格式无效: {mutation_str}，请使用如 N55Q 的格式")
    old_aa = match.group(1).upper()
    pos = int(match.group(2)) - 1
    new_aa = match.group(3).upper()
    seq = sequence.upper()
    if pos < 0 or pos >= len(seq):
        raise ValueError(f"突变位置 {pos+1} 超出序列长度 {len(seq)}")
    return seq[:pos] + new_aa + seq[pos+1:]