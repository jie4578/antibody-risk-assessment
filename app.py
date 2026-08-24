# app.py (v4.0 - 新增 ML / RAG / Agent 三个 Tab,接入四层 AIDD 能力)
import os

import gradio as gr
import pandas as pd

from core import scan_sequence, mutate_and_rescan
from batch_analysis import batch_analysis, write_result_csv
from input_parser import load_batch_input

# 默认序列
default_seq = "EVQLVESGGGLVQPGGSLRLSCAASGFNIKDTYIHWVRQAPGKGLEWVARIYPTNGYTRYADSVKGRFTISADTSKNTAYLQMNSLRAEDTAVYYCSRWGGDGFYAMDYWGQGTLVTVSS"

RISK_HEADERS = ["类别", "基序", "位置", "区域", "描述"]

_ROOT = os.path.dirname(os.path.abspath(__file__))


# ---------- 模块级缓存(避免每次请求重复初始化) ----------
_ML_BUNDLE = None  # (model, encoder)
_RAG_PIPE = None


def _ensure_ml_model():
    """若 ML 模型尚未训练,则现场用合成数据快速训练一个并缓存。"""
    global _ML_BUNDLE
    if _ML_BUNDLE is not None:
        return _ML_BUNDLE
    from ml.train import load_bundle, train_pipeline
    from ml.data import build_dataset

    cls_path = os.path.join(_ROOT, "ml", "artifacts", "cls.joblib")
    if os.path.exists(cls_path):
        _ML_BUNDLE = load_bundle(cls_path)
        return _ML_BUNDLE
    # 未训练 → 现场训练(合成数据,速度快),保证 Tab 开箱即用
    print("[app] 现场训练 ML 模型(合成数据)...")
    df = build_dataset(n=500, seed=42)
    train_pipeline(df, task="classification", model_name="logistic", save_path=cls_path)
    _ML_BUNDLE = load_bundle(cls_path)
    return _ML_BUNDLE


def _rag_pipeline():
    global _RAG_PIPE
    if _RAG_PIPE is None:
        from rag import RagPipeline
        from rag.knowledge_base import KNOWLEDGE_BASE

        pipe = RagPipeline(embedder="tfidf", strategy="hybrid", top_k=4)
        pipe.index(KNOWLEDGE_BASE)
        _RAG_PIPE = pipe
    return _RAG_PIPE


# ---------- 三个新 Tab 的 handler ----------
def ml_predict_wrapper(seq):
    if not seq or not str(seq).strip():
        return "请先输入抗体序列。", "等待输入"
    try:
        model, encoder = _ensure_ml_model()
    except Exception as e:
        return f"模型初始化失败: {e}", "N/A"
    proba = model.predict_proba(encoder.transform([str(seq)]))[:, 1][0]
    level = "High Risk" if proba >= 0.5 else "Low Risk"
    return f"ML 预测高风险概率: {proba:.4f}", level


def rag_query_wrapper(question):
    if not question or not str(question).strip():
        return "请先输入问题。", "（未检索）"
    try:
        result = _rag_pipeline().query(str(question))
    except Exception as e:
        return f"检索失败: {e}", "（错误）"
    return result["context"], result["prompt"]


def agent_ask_wrapper(question):
    if not question or not str(question).strip():
        return "请先输入问题。", "（无回答）", ""
    from agent import Agent

    r = Agent().run(str(question))
    log = "\n".join(f"[{s['tool']}] {s['result'][:220]}" for s in r["steps"]) or "（未调用工具）"
    return log, r["answer"], r["steps"][0]["tool"] if r["steps"] else "（无）"


def agent_orchestrate_wrapper(question):
    if not question or not str(question).strip():
        return "请先输入问题。", "（无回答）"
    from agent import Orchestrator

    res = Orchestrator().run(str(question))
    parts = [f"选择专家: {res['agents']}"]
    for r in res["results"]:
        parts.append(f"=== {r['agent']} ===")
        for s in r["steps"]:
            parts.append(f"[{s['tool']}] {s['result'][:200]}")
    return "\n".join(parts), res["answer"]


with gr.Blocks(title="抗体序列风险评估工具") as demo:
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
            seq_input = gr.Textbox(label="抗体可变区序列（单字母）", value=default_seq, lines=3, placeholder="输入重链或轻链可变区序列...")
            scan_btn = gr.Button("开始扫描", variant="primary", size="lg")

            with gr.Row():
                report_output = gr.Textbox(label="📋 详细报告", lines=12)
                risk_table = gr.Dataframe(headers=RISK_HEADERS, label="📊 风险列表")

            summary_text = gr.Textbox(label="📈 风险统计", interactive=False)

            scan_btn.click(
                fn=scan_sequence,
                inputs=[seq_input, cdr1_s, cdr1_e, cdr2_s, cdr2_e, cdr3_s, cdr3_e],
                outputs=[report_output, risk_table, summary_text],
            )

        with gr.TabItem("🧪 虚拟突变"):
            gr.Markdown("输入突变（如 `N55Q`），模拟点突变后重新扫描序列，验证风险是否被消除。")
            with gr.Row():
                mut_seq_input = gr.Textbox(label="原始序列", value=default_seq, lines=2)
                mutation_input = gr.Textbox(label="突变（格式：原氨基酸+位置+新氨基酸，如 N55Q）", placeholder="例: N55Q")
            mut_btn = gr.Button("执行突变并扫描", variant="primary")

            with gr.Row():
                mut_report = gr.Textbox(label="突变后报告", lines=10)
                mut_risks = gr.Dataframe(headers=RISK_HEADERS, label="突变后风险列表")
            mut_summary = gr.Textbox(label="突变结果摘要", interactive=False)
            mutated_seq_out = gr.State()

            mut_btn.click(
                fn=mutate_and_rescan,
                inputs=[mut_seq_input, mutation_input, cdr1_s, cdr1_e, cdr2_s, cdr2_e, cdr3_s, cdr3_e],
                outputs=[mut_report, mut_risks, mut_summary, mutated_seq_out],
            )

        with gr.TabItem("📊 批量分析"):
            gr.Markdown("上传 CSV / Excel（.xlsx）/ FASTA 文件，逐条分析所有抗体。CSV / Excel 需包含 `antibody_id`、`VH`、`VL` 三列；FASTA 使用 `>抗体ID_VH` / `>抗体ID_VL`（或 `|` 分隔）的 header。")
            input_file = gr.File(label="上传 CSV / Excel / FASTA 文件", file_types=[".csv", ".xlsx", ".fasta", ".fa", ".faa"])
            batch_btn = gr.Button("开始批量分析", variant="primary", size="lg")

            batch_result_df = gr.Dataframe(label="📋 批量分析结果", interactive=False)
            download_btn = gr.File(label="📥 下载结果 CSV", interactive=False)

            def batch_analysis_wrapper(file_obj, c1s, c1e, c2s, c2e, c3s, c3e):
                if file_obj is None:
                    gr.Warning("请先上传 CSV / Excel / FASTA 文件。")
                    return pd.DataFrame(), None
                try:
                    df = load_batch_input(file_obj.name)
                except ValueError as e:
                    gr.Warning(str(e))
                    return pd.DataFrame(), None
                except Exception as e:
                    gr.Warning(f"读取文件失败: {e}")
                    return pd.DataFrame(), None

                try:
                    result_df = batch_analysis(df, c1s, c1e, c2s, c2e, c3s, c3e)
                except ValueError as e:
                    gr.Warning(str(e))
                    return pd.DataFrame(), None
                except Exception as e:
                    gr.Warning(f"批量分析出错: {e}")
                    return pd.DataFrame(), None

                if result_df.empty:
                    gr.Warning("输入为空，未分析到任何记录。")
                    return result_df, None

                path = write_result_csv(result_df)
                return result_df, path

            batch_btn.click(
                fn=batch_analysis_wrapper,
                inputs=[input_file, cdr1_s, cdr1_e, cdr2_s, cdr2_e, cdr3_s, cdr3_e],
                outputs=[batch_result_df, download_btn],
            )

        with gr.TabItem("🔮 ML 风险预测"):
            gr.Markdown("用机器学习模型预测抗体序列的**高风险概率**（模型基于规则弱标签训练，首次运行会自动训练）。")
            ml_seq = gr.Textbox(label="抗体序列", value=default_seq, lines=2)
            ml_btn = gr.Button("预测", variant="primary")
            ml_out = gr.Textbox(label="预测结果", interactive=False)
            ml_level = gr.Textbox(label="风险等级", interactive=False)
            ml_btn.click(fn=ml_predict_wrapper, inputs=[ml_seq], outputs=[ml_out, ml_level])

        with gr.TabItem("📚 RAG 知识问答"):
            gr.Markdown("基于内置抗体可开发性 / PTM 知识库做**检索增强生成**：先检索最相关的知识片段，再生成带引用的上下文与 prompt。")
            rag_q = gr.Textbox(label="你的问题", placeholder="例如：什么是脱酰胺化？抗体的 N-糖基化位点有什么风险？")
            rag_btn = gr.Button("检索", variant="primary")
            rag_context = gr.Textbox(label="📄 检索上下文（带 [n] 引用）", lines=10)
            rag_prompt = gr.Textbox(label="🪄 组装好的 prompt（可交给 LLM）", lines=6)
            rag_btn.click(fn=rag_query_wrapper, inputs=[rag_q], outputs=[rag_context, rag_prompt])

        with gr.TabItem("🤖 智能体 Agent"):
            gr.Markdown("**多智能体**：自动识别问题，调度专家智能体（规则扫描 / ML / 知识检索）协同回答。")
            agent_q = gr.Textbox(label="你的问题", value="什么是脱酰胺化？", lines=2)
            agent_btn = gr.Button("运行 Agent", variant="primary")
            agent_log = gr.Textbox(label="🧩 工具调用日志", lines=8)
            agent_answer = gr.Textbox(label="💬 回答", lines=8)
            agent_btn.click(fn=agent_orchestrate_wrapper, inputs=[agent_q], outputs=[agent_log, agent_answer])

    gr.Markdown("---")
    gr.Markdown("💡 本工具为概念演示，CDR 边界需根据具体抗体序列手动调整。批量分析逐条复用单条扫描逻辑，单条失败不影响整批。")

if __name__ == "__main__":
    demo.launch(theme=gr.themes.Soft(), share=True)
