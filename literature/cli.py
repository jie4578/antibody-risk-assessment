# literature/cli.py
# 命令行入口：python -m literature.cli --query "antibody deamidation"
#
# 输出：检索到的 Evidence 列表 + 最终 LLM 回答 + Citation Validator 结果。

from __future__ import annotations

import argparse
import sys

SOURCE_LABEL = {"europepmc": "Europe PMC", "pubmed": "PubMed"}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="literature.cli", description="Biomedical Literature RAG")
    p.add_argument("--query", "-q", required=True, help="用户问题")
    p.add_argument("--max-results", type=int, default=5, help="最多返回文献数(1-10)")
    p.add_argument("--source", default="auto", choices=["auto", "europepmc", "pubmed"])
    p.add_argument("--backend", default="auto", help="LLM 后端: auto/deepseek/openai/mock")
    p.add_argument("--fulltext", action="store_true", help="(增强)对 Open Access 论文尝试获取全文")
    args = p.parse_args(argv)

    from .pipeline import answer_question

    res = answer_question(
        args.query,
        max_results=args.max_results,
        source=args.source,
        backend=args.backend,
    )
    print(f"问题: {res.question}")
    print(f"检索词: {res.query}  (生成方式: {res.query_mode})  LLM 后端: {res.used_backend}")
    print(f"状态: {res.status}")

    if res.status == "api_unavailable":
        print(f"\n[错误] {res.error}")
        return 1
    if res.status == "no_evidence":
        print(f"\n{res.answer}")
        return 0

    print(f"\n=== 检索到的文献证据 ({len(res.evidence)}) ===")
    for i, ev in enumerate(res.evidence, 1):
        print(f"[{i}]")
        print(f"  Title:   {ev.title}")
        print(f"  Authors: {', '.join(ev.authors) if ev.authors else '-'}")
        print(f"  Journal: {ev.journal} ({ev.year})")
        print(f"  PMID:    {ev.pmid}")
        print(f"  PMCID:   {ev.pmcid or '-'}")
        print(f"  DOI:     {ev.doi or '-'}")
        print(f"  OA:      {'Y' if ev.is_open_access else 'N'}")
        print(f"  Source:  {SOURCE_LABEL.get(ev.source, ev.source)}")
        print(f"  Abstract: {ev.abstract[:200]}{'...' if len(ev.abstract) > 200 else ''}")

    print(f"\n=== 最终回答 ===")
    print(res.answer)
    print(f"\n=== Citation Validator ===")
    print(f"valid: {res.validation.get('valid')}")
    print(f"invalid_references: {res.validation.get('invalid_references')}")
    print(f"warnings: {res.validation.get('warnings')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
