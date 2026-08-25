# literature/pipeline.py
# Literature RAG 端到端管线：
#   User Question → Query Generator → search_literature() → Evidence[]
#   → rerank → Top-K → Context Builder → LLM(DeepSeek) → Citation Validator → Final Answer
#
# 反幻觉：
#   - 回答只能引用本次检索返回的 Evidence
#   - 无证据 → 明确"未检索到足够相关的文献证据。"
#   - 引用校验失败 → 触发 1 次 regenerate；仍失败 → status="citation_failed" 明确提示

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from .context import EVIDENCE_SYSTEM_PROMPT, build_context
from .errors import LiteratureSearchError
from .evidence import Evidence
from .query_generator import generate_query
from .reranker import rerank
from .search import search_literature
from .validator import validate_citations

NO_EVIDENCE_ANSWER = "未检索到足够相关的文献证据，无法基于当前检索结果可靠回答。"

_REGENERATE_HINT = (
    "Your previous answer contained a citation not present in the provided evidence. "
    "Rewrite the answer using only the provided evidence.\n"
    "中文：你上一版回答包含了本次证据之外的引用，请只使用提供的证据重写回答。"
)


@dataclass
class LiteratureAnswer:
    question: str = ""
    query: str = ""
    query_mode: str = ""  # "llm" | "rule"
    used_backend: str = ""
    evidence: List[Evidence] = field(default_factory=list)
    context: str = ""
    prompt: str = ""
    answer: str = ""
    validation: dict = field(default_factory=dict)
    status: str = "ok"  # ok | no_evidence | api_unavailable | citation_failed
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "question": self.question,
            "query": self.query,
            "query_mode": self.query_mode,
            "used_backend": self.used_backend,
            "evidence": [e.to_dict() for e in self.evidence],
            "context": self.context,
            "prompt": self.prompt,
            "answer": self.answer,
            "validation": self.validation,
            "status": self.status,
            "error": self.error,
        }


def _llm_answer(question: str, context: str, backend: str, *, fix_citation: bool = False) -> str:
    from agent.llm import generate_answer

    q = question
    if fix_citation:
        q = _REGENERATE_HINT + "\n\n" + question
    q = q + "\n\n请在你引用的每篇文献后标注 (PMID: 编号) 或 DOI，不要编造。"
    return generate_answer(q, context, backend=backend, system_prompt=EVIDENCE_SYSTEM_PROMPT)


def answer_question(
    question: str,
    *,
    max_results: int = 5,
    source: str = "auto",
    backend: str = "auto",
    max_citation_retry: int = 1,
) -> LiteratureAnswer:
    """端到端 Literature RAG 回答。"""
    if backend == "auto":
        from config import auto_llm_backend

        backend = auto_llm_backend()

    query, query_mode = generate_query(question, backend)

    try:
        evidence = search_literature(query, max_results=max_results, source=source)
    except LiteratureSearchError as e:
        return LiteratureAnswer(
            question=question, query=query, query_mode=query_mode, used_backend=backend,
            status="api_unavailable", error=e.to_user_message(),
        )

    ranked = rerank(query, evidence, top_k=max_results)
    if not ranked:
        return LiteratureAnswer(
            question=question, query=query, query_mode=query_mode, used_backend=backend,
            status="no_evidence", answer=NO_EVIDENCE_ANSWER,
            validation=validate_citations("", []),
        )

    context = build_context(ranked)
    prompt = f"{EVIDENCE_SYSTEM_PROMPT}\n\n{context}\n\n问题: {question}"

    answer = _llm_answer(question, context, backend)
    validation = validate_citations(answer, ranked)
    status = "ok"

    if not validation["valid"] and max_citation_retry > 0:
        answer = _llm_answer(question, context, backend, fix_citation=True)
        validation = validate_citations(answer, ranked)
        if not validation["valid"]:
            status = "citation_failed"

    return LiteratureAnswer(
        question=question, query=query, query_mode=query_mode, used_backend=backend,
        evidence=ranked, context=context, prompt=prompt,
        answer=answer, validation=validation, status=status,
    )
