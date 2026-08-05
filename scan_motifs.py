# scan_motifs.py (v2.1 - 手动Kabat注释，即刻生效)
import re

# 我们的明星抗体序列（曲妥珠单抗重链可变区）
sequence = "EVQLVESGGGLVQPGGSLRLSCAASGFNIKDTYIHWVRQAPGKGLEWVARIYPTQGYTRYADSVKGRFTISADTSKNTAYLQMNSLRAEDTAVYYCSRWGGDGFYAMDYWGQGTLVTVSS"
#  VH_N55Q_Mutant

# 风险基序数据库
risk_motifs = {
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

def get_manual_cdr_annotation(seq):
    """
    手动根据Kabat定义，硬编码曲妥珠单抗重链可变区的区域划分。
    这完全是生物信息学软件在做的事情：将序列比对到标准编号。
    0-based 索引 -> 区域标签
    """
    # 如果你要分析的是其他序列，这里需要按Kabat规则重新划分。
    # 此处我们精确标注这条120aa序列的CDR边界（基于IMGT/Kabat组合经验）：
    cdr1_start = 31 - 1   # 0-based
    cdr1_end = 35         # 半开区间，取35不包含
    cdr2_start = 50 - 1
    cdr2_end = 65
    cdr3_start = 99 - 1
    cdr3_end = 110

    pos_map = {}
    for i in range(len(seq)):
        if cdr1_start <= i < cdr1_end:
            pos_map[i] = "CDR1"
        elif cdr2_start <= i < cdr2_end:
            pos_map[i] = "CDR2"
        elif cdr3_start <= i < cdr3_end:
            pos_map[i] = "CDR3"
        else:
            pos_map[i] = "FW"
    return pos_map

# 获取手动注释
cdr_map = get_manual_cdr_annotation(sequence)

print("=" * 60)
print("抗体序列化学稳定性风险基序扫描报告 (v2.1 - 手动Kabat注释)")
print("序列: 曲妥珠单抗 VH (120aa)")
print("区域: CDR1=31-35, CDR2=50-65, CDR3=99-110 (Kabat规则)")
print("=" * 60)

found_any = False

# 扫描所有双字母基序
for category, motifs in risk_motifs.items():
    for motif, description in motifs.items():
        if len(motif) == 1:  # 氧化M单独处理
            base_index = 0
            while True:
                pos = sequence.find(motif, base_index)
                if pos == -1:
                    break
                region = cdr_map.get(pos, "?")
                print(f"[{category}] {motif} -> 位置{pos+1} | 区域: {region} | {description}")
                found_any = True
                base_index = pos + 1
        else:
            base_index = 0
            while True:
                pos = sequence.find(motif, base_index)
                if pos == -1:
                    break
                region = cdr_map.get(pos, "?")
                print(f"[{category}] {motif} -> 位置{pos+1}-{pos+2} | 区域: {region} | {description}")
                found_any = True
                base_index = pos + 1

# N-糖基化
glyco_pattern = r"N[^P][ST]"
for match in re.finditer(glyco_pattern, sequence):
    start = match.start()
    end = match.end()
    motif_str = match.group()
    region = cdr_map.get(start, "?")
    print(f"[N-糖基化] {motif_str} -> 位置{start+1}-{end} | 区域: {region} | 潜在的N-连接糖基化位点")
    found_any = True

if not found_any:
    print("未发现已知的常见风险基序。")

print("=" * 60)
print("扫描完毕。")
print("提示：高风险基序若位于CDR区，特别是CDR2/CDR3，需优先进行突变改造。")