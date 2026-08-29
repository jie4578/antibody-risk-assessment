# app.py (v4.0 - 新增 ML / RAG / Agent 三个 Tab,接入四层 AIDD 能力)
import os
import re
import traceback

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
def _llm_backend():
    """自动选择 LLM 后端：.env 有 key → 真实(deepseek/openai)；否则 → mock(离线)。"""
    from config import auto_llm_backend

    return auto_llm_backend()


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
    """RAG Tab：Biomedical Literature RAG（真实文献检索 → 证据 → LLM 回答）。

    返回 4 个输出: context / prompt / answer / sources。
    """
    if not question or not str(question).strip():
        return "", "请先输入问题。", "（未检索）", "（未生成）"
    from literature.context import build_sources
    from literature.pipeline import answer_question

    backend = _llm_backend()
    res = answer_question(str(question), max_results=5, source="auto", backend=backend)
    if res.status == "api_unavailable":
        return "", "", res.error, "（检索服务不可用）"
    if res.status == "no_evidence":
        return "", "", res.answer, "（未检索到文献证据）"
    sources_txt = "\n\n".join(
        f"[{i}] {s['title']}\n    PMID: {s['pmid']} | DOI: {s['doi'] or '-'} | "
        f"{s['journal']} ({s['year']}) | {s['source']}"
        for i, s in enumerate(build_sources(res.evidence), 1)
    ) or "（无）"
    answer = res.answer
    if res.status == "citation_failed":
        answer += "\n\n[提示] 模型生成的引用无法通过证据校验。"
    return res.context, res.prompt, answer, sources_txt


def _redact_sensitive(text) -> str:
    """脱敏 API key / token（避免错误信息泄露 sk-... 等敏感串）。"""
    t = str(text)
    t = re.sub(r"sk-[A-Za-z0-9]{4,}", "sk-****", t)
    return t


def _error_block(title: str, err: Exception) -> str:
    """把异常转成开发友好的单块文本（类型 + 已脱敏信息），供 Gradio 输出。"""
    return f"❌ {title}\n错误类型: {type(err).__name__}\n错误信息: {_redact_sensitive(err)}"


def _is_tool_error(result) -> bool:
    """工具结果是否属于失败（用于日志显示"工具调用失败"）。"""
    t = str(result or "").strip()
    return t.startswith(("工具 ", "错误", "突变失败", "执行异常", "请提供"))


def _summarize_tool_result(tool: str, result: str) -> str:
    """从工具返回文本提取 1-3 行关键信息（简洁科研风格，不展示完整 arguments/长序列）。"""
    t = str(result or "").strip()
    if not t:
        return "（无返回）"
    if tool in ("scan_antibody", "risk_score"):
        m = re.search(r"风险评分 ([0-9.]+)（(.+?)）", t)
        if m:
            lines = [f"风险评分：{m.group(1)}", f"风险等级：{m.group(2)}"]
            if tool == "scan_antibody":
                hits = re.search(r"命中风险基序: (.*)$", t)
                if hits and hits.group(1).strip() != "无":
                    lines.append(f"发现 {hits.group(1).count(';') + 1} 个风险位点")
            return "\n".join(lines)
        return t[:120]
    if tool == "mutate_scan":
        first = t.splitlines()[0] if t.splitlines() else t
        return first[:120]
    if tool == "batch_analysis":
        m = re.search(r"批量分析 (\d+) 条记录", t)
        return f"批量分析 {m.group(1)} 条记录" if m else t[:120]
    if tool == "literature_search":
        n = len(re.findall(r"PMID:", t))
        return f"检索文献证据 {n} 条" if n else t[:120]
    if tool == "rag_search":
        return "检索知识库相关知识"
    return t[:120]


def format_agent_steps(steps) -> str:
    """把 Agent.run() 的 steps 格式化为简洁的科研软件风格日志。

    - final 条目跳过（最终回答单独展示）
    - 不展示完整 arguments（避免长序列刷屏）
    - 工具失败显示：工具调用失败：<tool> / 原因：<脱敏信息>
    - 保留 [重试] 标记
    """
    blocks = []
    for s in steps or []:
        if not isinstance(s, dict):
            continue
        if s.get("type") == "final":
            continue  # 最终回答不进工具日志
        tool = s.get("tool", "?")
        retried = " [重试]" if s.get("retried") else ""
        result = _redact_sensitive(s.get("result", ""))  # 统一先脱敏，任何分支都不泄露 key
        if _is_tool_error(result):
            blocks.append(f"{tool}{retried}\n工具调用失败：{tool}\n原因：{result[:200]}")
        else:
            blocks.append(f"{tool}{retried}\n{_summarize_tool_result(tool, result)}")
    if not blocks:
        return "（未调用工具）"
    return "工具调用\n\n" + "\n\n".join(blocks)


def _clean_answer(text) -> str:
    """展示层强制纯文本：去掉全部 Markdown 痕迹与模板语（v6）。

    仅影响展示，不改变 Agent 内部 answer 数据。
    清除：**、*、__、`、#、---、___、>、表格竖线、列表符号、链接等。
    """
    t = str(text or "")
    # 1) 模板语 / 寒暄
    for phrase in (
        "我协调了多个专家智能体，汇总如下：",
        "我协调了多个专家智能体",
        "以上为多专家协同的离线演示回复",
        "以上为基于离线规则/Mock 的演示性回复",
        "接入真实 LLM 后可生成更连贯的结论",
        "让我仔细检查",
        "如果您有具体序列",
    ):
        t = t.replace(phrase, "")
    t = re.sub(r"^(您好[，,。\s]*|请问有什么可以帮您[？?]?\s*)", "", t)  # 开头寒暄
    # 2) 行级结构：标题 / 引用块 / 分隔线 / 表格分隔行
    t = re.sub(r"(?m)^#{1,6}\s*", "", t)                        # # ## ###
    t = re.sub(r"(?m)^\s*(?:>+\s?)+", "", t)                    # > 引用块
    t = re.sub(r"(?m)^\s*(?:[-—–_]{3,}|[*]{3,})\s*$", "", t)    # --- ___ ***
    t = re.sub(r"(?m)^\s*\|[:\s\-]*\|[:\s\-]*\|?\s*$", "", t)   # 表格分隔行 |---|---| / |---|
    # 3) 行首列表符号（- / * / + / •）
    t = re.sub(r"(?m)^\s*(?:[-*+]\s+|•\s+)", "", t)
    # 4) 行内 Markdown
    t = re.sub(r"\*\*([^*]+)\*\*", r"\1", t)     # **x** → x
    t = re.sub(r"\*([^*\n]+)\*", r"\1", t)       # *x* → x
    t = re.sub(r"__([^_\n]+)__", r"\1", t)       # __x__ → x
    t = re.sub(r"`([^`\n]+)`", r"\1", t)         # `x` → x
    t = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", t)  # ![alt](url) → alt
    t = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", t)   # [text](url) → text
    t = re.sub(r"(?m)^\s*\|(.*)\|\s*$", r"\1", t)    # 表格行去首尾竖线
    t = t.replace("|", " ")                        # 残余竖线 → 空格
    # 5) 折叠多余空行
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def agent_ask_wrapper(question):
    if not question or not str(question).strip():
        return "请先输入问题。", "（无回答）", ""
    from agent import Agent

    try:
        r = Agent().run(str(question))
        steps = r.get("steps", []) or []
        first_tool = next((s.get("tool") for s in steps if s.get("type") != "final"), "（无）")
        return format_agent_steps(steps), _clean_answer(r.get("answer", "")), first_tool
    except Exception as e:
        traceback.print_exc()
        err = _error_block("Agent 执行失败", e)
        return err, err, "（无）"


def agent_orchestrate_wrapper(question):
    if not question or not str(question).strip():
        return "请先输入问题。", "（无回答）"
    from agent import Orchestrator

    backend = _llm_backend()
    note = ""
    try:
        res = Orchestrator(lead_backend=backend, worker_backend=backend).run(str(question))
        # 开发调试信息保留在控制台，不进页面
        print(f"[Agent][debug] backend={backend} agents={res.get('agents')}")
    except Exception as e:
        # 真实 LLM 失败 → 尝试离线 mock；mock 也失败 → 开发友好错误（控制台打印完整 traceback）
        traceback.print_exc()
        backend = "mock"
        note = f"\n[提示] 真实 LLM 调用失败，已回退离线 mock: {_redact_sensitive(e)}"
        try:
            res = Orchestrator().run(str(question))
        except Exception as e2:
            traceback.print_exc()
            err = _error_block("Agent 执行失败", e2)
            return err, err
    try:
        # 合并所有专家步骤 → 统一简洁日志（不显示 === agent === 分隔符/参数长串）
        all_steps = []
        for r in res.get("results", []):
            all_steps.extend(r.get("steps") or [])
        log = format_agent_steps(all_steps)
        answer = _clean_answer(res.get("answer", "")) + note
        return log, answer
    except Exception as e:
        traceback.print_exc()
        err = _error_block("结果格式化失败", e)
        return err, err


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
            gr.Markdown("**Biomedical Literature RAG**：在线检索真实文献（Europe PMC / PubMed）→ 证据 → LLM 基于证据回答（配置 API key 后自动用真实 LLM；回答只引用本次检索返回的真实文献）。")
            rag_q = gr.Textbox(label="你的问题", placeholder="例如：什么是抗体脱酰胺化？最近关于抗体脱酰胺化的研究有哪些？")
            rag_btn = gr.Button("检索并回答", variant="primary")
            rag_answer = gr.Textbox(label="💬 回答（LLM 生成，引用真实文献）", lines=8)
            rag_sources = gr.Textbox(label="📚 证据 / Sources（本次检索返回）", lines=8)
            rag_context = gr.Textbox(label="📄 Evidence Context（喂给 LLM）", lines=8)
            rag_prompt = gr.Textbox(label="🪄 组装好的 prompt（可交给 LLM）", lines=5)
            rag_btn.click(fn=rag_query_wrapper, inputs=[rag_q], outputs=[rag_context, rag_prompt, rag_answer, rag_sources])

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
