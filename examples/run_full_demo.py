# examples/run_full_demo.py
# 端到端一键演示：规则引擎 → 深度学习 → RAG → Agent 四层全跑一遍，
# 产出 demo/DEMO_REPORT.md（汇总报告）与 demo/dashboard.png（ML 仪表盘图）。
#
# 运行：
#   python examples/run_full_demo.py
#
# 产物（写入 demo/，已 gitignore）：
#   demo/DEMO_REPORT.md   四层输出汇总
#   demo/dashboard.png    ML 仪表盘（ROC / 混淆矩阵 / 特征重要性）
#   demo/roc.png, demo/cm.png, demo/feature_importance.png

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

OUT = os.path.join(_ROOT, "demo")
SEQ = (
    "EVQLVESGGGLVQPGGSLRLSCAASGFNIKDTYIHWVRQAPGKGLEWVARIYPTNGYTRYADSVKG"
    "RFTISADTSKNTAYLQMNSLRAEDTAVYYCSRWGGDGFYAMDYWGQGTLVTVSS"
)


def layer0_rules() -> str:
    """层0 规则引擎：扫描 + 规则风险评分。"""
    from core import analyze_sequence
    from scoring import compute_risk_score

    result = analyze_sequence(SEQ, 31, 35, 50, 65, 99, 110)
    score = compute_risk_score([("VH", result)])
    hits = "；".join(f"{r.motif}@{r.position}({r.region})" for r in result.risks) or "无"
    return (
        "### 层0 · 规则引擎\n\n"
        f"- 序列长度: {result.sequence_length} aa\n"
        f"- 规则风险评分: **{score.overall_score}（{score.risk_level}）**\n"
        f"- 命中风险基序: {hits}\n\n"
        "```\n" + result.report[:900] + "\n```\n"
    )


def layer1_ml() -> str:
    """层1 深度学习：训练 + 指标 + 出图 + 仪表盘。"""
    from ml.data import build_dataset
    from ml.features import SequenceEncoder
    from ml.train import train_pipeline

    print("  [ML] 构造数据集并训练...")
    df = build_dataset(n=800, seed=42)
    cls = train_pipeline(df, task="classification", model_name="logistic", seed=42,
                         save_path=os.path.join(_ROOT, "ml", "artifacts", "cls.joblib"))
    reg = train_pipeline(df, task="regression", model_name="ridge", seed=42,
                         save_path=os.path.join(_ROOT, "ml", "artifacts", "reg.joblib"))

    # 出图（用全量数据绘制，便于展示；测试集指标以 train_pipeline 报告为准）
    from ml.evaluate import confusion_matrix_plot, feature_importance_plot, roc_curve_plot

    enc = SequenceEncoder()
    X = enc.transform(df["sequence"].tolist())
    y = df["high_risk"].astype(int).to_numpy()
    model = cls.model
    y_pred = model.predict(X)
    proba = model.predict_proba(X)[:, 1]
    cm = confusion_matrix_plot(y, y_pred, ["Low", "High"], os.path.join(OUT, "cm.png"))
    roc = roc_curve_plot(y, proba, os.path.join(OUT, "roc.png"))
    fi = feature_importance_plot(cls.feature_importance, top_n=12, save_path=os.path.join(OUT, "feature_importance.png"))

    _compose_dashboard(roc, cm, fi)

    m = cls.metrics
    rm = reg.metrics
    return (
        "### 层1 · 深度学习（ML 属性预测）\n\n"
        f"- 数据集: {len(df)} 条合成抗体序列（规则弱标签），高风险占比 {y.mean():.2f}\n"
        f"- 特征: 长度 + AAindex 理化性质 + k-mer 哈希（{enc.n_features} 维）\n"
        f"- 分类模型 logistic: accuracy={m.get('accuracy')}, roc_auc={m.get('roc_auc')}\n"
        f"- 回归模型 ridge: R²={rm.get('r2')}, MAE={rm.get('mae')}\n"
        f"- 图: `demo/dashboard.png`（ROC / 混淆矩阵 / 特征重要性）\n\n"
        "> 标签来自规则引擎（weak label），用于相对排序，非实验结论。\n"
    )


def _compose_dashboard(roc: str, cm: str, fi: str) -> str:
    """把三张图合成一张 2x2 仪表盘（含四层架构说明面板）。"""
    import matplotlib

    matplotlib.use("Agg")
    # 中文字体支持（Windows 常见字体；找不到时回退默认）
    matplotlib.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
    matplotlib.rcParams["axes.unicode_minus"] = False
    import matplotlib.pyplot as plt
    import matplotlib.image as mpimg

    fig, axes = plt.subplots(2, 2, figsize=(13, 11))
    for ax, path, title in [
        (axes[0, 0], roc, "ROC Curve"),
        (axes[0, 1], cm, "Confusion Matrix"),
        (axes[1, 0], fi, "Feature Importance (top)"),
    ]:
        ax.imshow(mpimg.imread(path))
        ax.axis("off")
        ax.set_title(title, fontsize=13)
    ax = axes[1, 1]
    ax.axis("off")
    ax.text(0.02, 0.9, "Antibody AIDD 四层流水线", fontsize=14, weight="bold", va="top")
    ax.text(0.02, 0.62, "层0 规则引擎\n  风险基序扫描 / CDR / 虚拟突变\n层1 深度学习\n  序列表示 + 属性预测\n层2 RAG\n  知识检索 + 上下文构建\n层3 Agent\n  工具调用 + 多智能体编排", fontsize=11, va="top", linespacing=1.5)
    fig.suptitle("antibody_risk · 四层 AIDD 演示仪表盘", fontsize=15, weight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    path = os.path.join(OUT, "dashboard.png")
    fig.savefig(path, dpi=130)
    plt.close(fig)
    return path


def layer2_rag() -> str:
    """层2 RAG：知识检索 + 上下文。"""
    from rag import RagPipeline
    from rag.knowledge_base import KNOWLEDGE_BASE

    print("  [RAG] 索引知识库并检索...")
    pipe = RagPipeline(embedder="tfidf", strategy="hybrid", top_k=3)
    pipe.index(KNOWLEDGE_BASE)
    result = pipe.query("抗体的脱酰胺化主要发生在哪里？")
    hits = "\n".join(f"- [{h['id']}] 来源={h['metadata'].get('source')} 得分={h['score']:.4f}" for h in result["hits"])
    return (
        "### 层2 · RAG（检索增强生成）\n\n"
        "问题: 抗体的脱酰胺化主要发生在哪里？\n\n"
        f"检索命中:\n{hits}\n\n"
        "上下文（节选）:\n\n"
        "```\n" + result["context"][:700] + "\n```\n"
    )


def layer3_agent() -> str:
    """层3 Agent：多智能体编排。"""
    from agent import Orchestrator

    print("  [Agent] 多智能体编排...")
    res = Orchestrator().run(f"评估这条序列的风险，并告诉我脱酰胺化为什么重要：{SEQ}")
    log = "\n".join(f"- {r['agent']}: " + "; ".join(f"[{s['tool']}]" for s in r["steps"]) for r in res["results"])
    return (
        "### 层3 · Agent（多智能体编排）\n\n"
        f"问题: 评估这条序列的风险，并告诉我脱酰胺化为什么重要\n\n"
        f"主管选择专家: {res['agents']}\n\n"
        f"工具调用:\n{log}\n\n"
        "汇总回答（节选）:\n\n"
        "```\n" + res["answer"][:900] + "\n```\n"
    )


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    print("== 端到端演示：四层全跑 ==")
    sections = []
    sections.append("# Antibody Risk · 四层 AIDD 端到端演示报告\n")
    sections.append("> 由 `examples/run_full_demo.py` 生成（可离线运行，无外部 API）。\n")
    sections.append(layer0_rules())
    sections.append(layer1_ml())
    sections.append(layer2_rag())
    sections.append(layer3_agent())
    sections.append("---\n\n> 说明：ML 标签为规则弱标签，结果仅用于技术演示与相对排序，未经实验验证。")

    report = "\n".join(sections)
    report_path = os.path.join(OUT, "DEMO_REPORT.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\n完成! 报告: {report_path}")
    print(f"仪表盘: {os.path.join(OUT, 'dashboard.png')}")


if __name__ == "__main__":
    main()
