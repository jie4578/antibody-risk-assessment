# cli.py
# 命令行入口：单条扫描 / 批量分析 / ML 训练 / ML 预测。
#
# 例：
#   python cli.py scan --seq "EVQLVESGGGLVQPGGSLRLSCAASGFNIKDTYIHWVRQAPGKGLEWVARIYPTNGYTRYADSVKGRFTISADTSKNTAYLQMNSLRAEDTAVYYCSRWGGDGFYAMDYWGQGTLVTVSS"
#   python cli.py ml-train --n 800 --task classification --model logistic --save ml/artifacts/cls.joblib
#   python cli.py ml-predict --model ml/artifacts/cls.joblib --seq "<seq>"

from __future__ import annotations

import argparse
import sys

from core import scan_sequence


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="antibody-risk", description="Antibody risk analysis CLI")
    sub = p.add_subparsers(dest="command", required=True)

    # scan
    sp = sub.add_parser("scan", help="单条抗体序列风险扫描")
    sp.add_argument("--seq", required=True, help="抗体可变区序列")
    sp.add_argument("--cdr1s", type=int, default=31)
    sp.add_argument("--cdr1e", type=int, default=35)
    sp.add_argument("--cdr2s", type=int, default=50)
    sp.add_argument("--cdr2e", type=int, default=65)
    sp.add_argument("--cdr3s", type=int, default=99)
    sp.add_argument("--cdr3e", type=int, default=110)

    # ml-train
    mt = sub.add_parser("ml-train", help="训练属性预测模型")
    mt.add_argument("--n", type=int, default=800, help="合成样本数")
    mt.add_argument("--seed", type=int, default=42)
    mt.add_argument("--task", choices=["classification", "regression"], default="classification")
    mt.add_argument("--model", default="logistic", help="logistic/random_forest/gbdt/lightgbm")
    mt.add_argument("--save", default="ml/artifacts/model.joblib", help="模型保存路径")
    mt.add_argument("--cv", action="store_true", help="启用交叉验证")

    # ml-predict
    mp = sub.add_parser("ml-predict", help="用训练好的模型预测")
    mp.add_argument("--model", required=True, help="模型路径(.joblib)")
    mp.add_argument("--seq", required=True, help="待预测序列")

    # rag-query
    rq = sub.add_parser("rag-query", help="基于内置知识库做 RAG 检索并生成上下文/prompt")
    rq.add_argument("--q", required=True, help="问题")
    rq.add_argument("--top-k", type=int, default=3)
    rq.add_argument("--strategy", choices=["vector", "keyword", "hybrid"], default="hybrid")
    rq.add_argument("--embedder", choices=["tfidf", "hashing"], default="tfidf")
    rq.add_argument("--show-prompt", action="store_true", help="额外显示组装好的 prompt")

    # agent-ask
    aa = sub.add_parser("agent-ask", help="用智能体(工具调用)回答一个问题")
    aa.add_argument("--q", required=True, help="问题（含抗体序列可触发扫描/突变）")
    aa.add_argument("--backend", default="mock", help="mock / openai / deepseek")

    # agent-orchestrate
    ao = sub.add_parser("agent-orchestrate", help="多智能体编排：分解任务并协同回答")
    ao.add_argument("--q", required=True, help="问题")
    ao.add_argument("--backend", default="mock", help="mock / openai / deepseek")

    return p


def cmd_scan(args) -> int:
    report, risks, summary = scan_sequence(args.seq, args.cdr1s, args.cdr1e, args.cdr2s, args.cdr2e, args.cdr3s, args.cdr3e)
    print(report)
    print("\n[摘要]", summary)
    return 0


def cmd_ml_train(args) -> int:
    from ml.data import build_dataset
    from ml.train import train_pipeline

    print(f"构造数据集(n={args.n}, seed={args.seed})...")
    df = build_dataset(n=args.n, seed=args.seed)
    print(f"  样本数: {len(df)}")
    print(f"  风险分布:\n{df['risk_level'].value_counts().to_string()}")

    print(f"训练 {args.task} ({args.model})...")
    result = train_pipeline(df, task=args.task, model_name=args.model, use_cv=args.cv, save_path=args.save)
    print(result.report)
    print(f"\n模型已保存: {args.save}")
    return 0


def cmd_ml_predict(args) -> int:
    from ml.train import load_bundle

    model, encoder = load_bundle(args.model)
    x = encoder.transform([args.seq])
    if hasattr(model, "predict_proba"):
        proba = model.predict_proba(x)[:, 1][0]
        pred = model.predict(x)[0]
        print(f"高风险概率: {proba:.4f} | 预测类别: {int(pred)}")
    else:
        pred = model.predict(x)[0]
        print(f"预测风险分数: {float(pred):.2f}")
    return 0


def cmd_rag_query(args) -> int:
    from rag import RagPipeline
    from rag.knowledge_base import KNOWLEDGE_BASE

    pipe = RagPipeline(embedder=args.embedder, strategy=args.strategy, top_k=args.top_k)
    pipe.index(KNOWLEDGE_BASE)
    result = pipe.query(args.q)
    print(f"Q: {args.q}\n")
    print("== 检索命中 ==")
    for h in result["hits"]:
        source = h["metadata"].get("source") or h["metadata"].get("title")
        print(f"- [{h['id']}] 来源={source}  得分={h['score']:.4f}")
    print("\n== 上下文 ==")
    print(result["context"])
    if args.show_prompt:
        print("\n== Prompt ==")
        print(result["prompt"])
    return 0


def cmd_agent_ask(args) -> int:
    from agent import Agent

    a = Agent(backend=args.backend)
    r = a.run(args.q)
    print(f"Q: {args.q}\n")
    for s in r["steps"]:
        print(f"  -> 调用工具 [{s['tool']}]")
        print(f"     {s['result'][:200]}")
    print("\n== 回答 ==")
    print(r["answer"])
    return 0


def cmd_agent_orchestrate(args) -> int:
    from agent import Orchestrator

    o = Orchestrator(lead_backend=args.backend, worker_backend=args.backend)
    res = o.run(args.q)
    print(f"Q: {args.q}\n选出专家: {res['agents']}\n")
    for r in res["results"]:
        print(f"=== {r['agent']} ===")
        for s in r["steps"]:
            print(f"  -> [{s['tool']}] {s['result'][:160]}")
    print("\n== 汇总回答 ==")
    print(res["answer"])
    return 0


def main(argv=None) -> int:
    args = _build_parser().parse_args(argv)
    handlers = {
        "scan": cmd_scan,
        "ml-train": cmd_ml_train,
        "ml-predict": cmd_ml_predict,
        "rag-query": cmd_rag_query,
        "agent-ask": cmd_agent_ask,
        "agent-orchestrate": cmd_agent_orchestrate,
    }
    return handlers[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
