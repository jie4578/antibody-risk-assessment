# app.py (v3.0 - 优化布局，专业交互)
import re
import gradio as gr
from datetime import datetime

# ---------- 核心分析函数 ----------
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

def annotate_cdr(seq, cdr1_s, cdr1_e, cdr2_s, cdr2_e, cdr3_s, cdr3_e):
    """根据Kabat边界手动注释CDR区域，返回位置->区域映射"""
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
    """核心扫描，返回报告、风险列表、统计信息"""
    # 基本验证
    if not sequence or not sequence.isalpha():
        return "错误：请输入有效的氨基酸序列（只包含字母）", [], "", "⚠️ 序列无效"
    
    sequence = sequence.upper()
    cdr_map = annotate_cdr(sequence, cdr1_s, cdr1_e, cdr2_s, cdr2_e, cdr3_s, cdr3_e)
    
    report_lines = []
    report_lines.append("=" * 60)
    report_lines.append(f"抗体序列化学稳定性风险基序扫描报告")
    report_lines.append(f"序列长度: {len(sequence)} aa")
    report_lines.append(f"CDR定义: CDR1={cdr1_s}-{cdr1_e}, CDR2={cdr2_s}-{cdr2_e}, CDR3={cdr3_s}-{cdr3_e}")
    report_lines.append("=" * 60)
    
    risks_found = []
    stats = {"CDR1": [], "CDR2": [], "CDR3": [], "FW": []}
    
    for category, motifs in risk_motifs.items():
        for motif, description in motifs.items():
            if len(motif) == 1:  # 单字母基序
                base = 0
                while True:
                    pos = sequence.find(motif, base)
                    if pos == -1: break
                    region = cdr_map.get(pos, "?")
                    line = f"[{category}] {motif} -> 位置{pos+1} | 区域:{region} | {description}"
                    report_lines.append(line)
                    risks_found.append({"类别": category, "基序": motif, "位置": pos+1, "区域": region, "描述": description})
                    if region in stats:
                        stats[region].append(f"{motif}({pos+1})")
                    base = pos + 1
            else:  # 双字母基序
                base = 0
                while True:
                    pos = sequence.find(motif, base)
                    if pos == -1: break
                    region = cdr_map.get(pos, "?")
                    line = f"[{category}] {motif} -> 位置{pos+1}-{pos+2} | 区域:{region} | {description}"
                    report_lines.append(line)
                    risks_found.append({"类别": category, "基序": motif, "位置": f"{pos+1}-{pos+2}", "区域": region, "描述": description})
                    if region in stats:
                        stats[region].append(f"{motif}({pos+1}-{pos+2})")
                    base = pos + 1
    
    # N-糖基化
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
        report_lines.append("未发现已知的常见风险基序，该序列化学稳定性较好。")
    
    report_lines.append("=" * 60)
    
    # 生成风险统计摘要
    cdr_risk_count = len(stats.get("CDR1",[])) + len(stats.get("CDR2",[])) + len(stats.get("CDR3",[]))
    summary = f"📊 CDR区高危基序总数: {cdr_risk_count} (CDR1:{len(stats.get('CDR1',[]))}, CDR2:{len(stats.get('CDR2',[]))}, CDR3:{len(stats.get('CDR3',[]))})"
    
    return "\n".join(report_lines), risks_found, summary, None

def mutate_and_rescan(sequence, mutation, cdr1_s, cdr1_e, cdr2_s, cdr2_e, cdr3_s, cdr3_e):
    """执行虚拟突变后重新扫描"""
    # 解析突变格式，如 "N55Q" 或 "D102E"
    try:
        import re
        match = re.match(r"([A-Za-z])(\d+)([A-Za-z])", mutation)
        if not match:
            return "错误：突变格式无效。请使用如 N55Q 的格式。", [], "", "❌ 突变格式错误"
        old_aa = match.group(1).upper()
        pos = int(match.group(2)) - 1  # 转为0-based
        new_aa = match.group(3).upper()
        
        seq = sequence.upper()
        if pos < 0 or pos >= len(seq):
            return "错误：突变位置超出序列长度。", [], "", "❌ 位置无效"
        if seq[pos] != old_aa:
            return f"警告：位置 {pos+1} 的氨基酸是 {seq[pos]}，不是 {old_aa}，但仍将执行突变。", [], "", "⚠️ 氨基酸不匹配"
        
        mutated_seq = seq[:pos] + new_aa + seq[pos+1:]
        report, risks, summary, _ = scan_sequence(mutated_seq, cdr1_s, cdr1_e, cdr2_s, cdr2_e, cdr3_s, cdr3_e)
        return report, risks, f"🧬 突变 {old_aa}{pos+1}{new_aa} 后的分析结果\n{summary}", mutated_seq
    except Exception as e:
        return f"突变解析错误: {str(e)}", [], "", "❌ 未知错误"

# ---------- Gradio 界面 ----------
default_seq = "EVQLVESGGGLVQPGGSLRLSCAASGFNIKDTYIHWVRQAPGKGLEWVARIYPTNGYTRYADSVKGRFTISADTSKNTAYLQMNSLRAEDTAVYYCSRWGGDGFYAMDYWGQGTLVTVSS"

with gr.Blocks(title="抗体序列风险评估工具", theme=gr.themes.Soft()) as demo:
    gr.Markdown("# 🧬 抗体序列化学稳定性风险评估工具")
    gr.Markdown("基于 Kabat 规则与已知 PTM 基序，快速扫描抗体可变区序列的脱酰胺、异构化、氧化及糖基化风险。")
    
    # 全局参数区
    with gr.Accordion("⚙️ CDR 边界设置（Kabat编号）", open=False):
        with gr.Row():
            cdr1_s = gr.Number(label="CDR1 起始", value=31, precision=0)
            cdr1_e = gr.Number(label="CDR1 结束", value=35, precision=0)
            cdr2_s = gr.Number(label="CDR2 起始", value=50, precision=0)
            cdr2_e = gr.Number(label="CDR2 结束", value=65, precision=0)
            cdr3_s = gr.Number(label="CDR3 起始", value=99, precision=0)
            cdr3_e = gr.Number(label="CDR3 结束", value=110, precision=0)
    
    with gr.Tabs():
        with gr.TabItem("🔍 序列扫描"):
            seq_input = gr.Textbox(label="抗体可变区序列（单字母大写）", value=default_seq, lines=3, placeholder="输入重链或轻链可变区序列...")
            scan_btn = gr.Button("开始扫描", variant="primary", size="lg")
            
            with gr.Row():
                report_output = gr.Textbox(label="📋 详细报告", lines=12)
                risk_table = gr.Dataframe(headers=["类别", "基序", "位置", "区域", "描述"], label="📊 风险列表")
            
            summary_text = gr.Textbox(label="📈 风险统计", interactive=False)
            
            scan_btn.click(
                fn=scan_sequence,
                inputs=[seq_input, cdr1_s, cdr1_e, cdr2_s, cdr2_e, cdr3_s, cdr3_e],
                outputs=[report_output, risk_table, summary_text]
            )
        
        with gr.TabItem("🧪 虚拟突变"):
            gr.Markdown("输入突变（如 `N55Q`），模拟点突变后重新扫描序列，验证风险是否被消除。")
            with gr.Row():
                mut_seq_input = gr.Textbox(label="原始序列", value=default_seq, lines=2)
                mutation_input = gr.Textbox(label="突变（格式：原氨基酸+位置+新氨基酸，如 N55Q）", placeholder="例: N55Q")
            mut_btn = gr.Button("执行突变并扫描", variant="primary")
            
            with gr.Row():
                mut_report = gr.Textbox(label="突变后报告", lines=10)
                mut_risks = gr.Dataframe(headers=["类别", "基序", "位置", "区域", "描述"], label="突变后风险列表")
            mut_summary = gr.Textbox(label="突变结果摘要", interactive=False)
            mutated_seq_out = gr.State()  # 存储突变后的序列，以备后用
            
            mut_btn.click(
                fn=mutate_and_rescan,
                inputs=[mut_seq_input, mutation_input, cdr1_s, cdr1_e, cdr2_s, cdr2_e, cdr3_s, cdr3_e],
                outputs=[mut_report, mut_risks, mut_summary, mutated_seq_out]
            )
    
    gr.Markdown("---")
    gr.Markdown("💡 本工具为概念演示，CDR 边界需根据具体抗体序列手动调整。后续计划接入 ANARCI 自动编号和 AlphaFold 结构预测。")

if __name__ == "__main__":
    demo.launch(share=True)