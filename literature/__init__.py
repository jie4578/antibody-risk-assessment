# literature/__init__.py
# Biomedical Literature RAG：真实文献检索与证据约束回答。
#
# 目标：把"用户问题 → 内置知识 → LLM"升级为
#   "用户问题 → Query Generator → 真实在线文献检索(Europe PMC/PubMed)
#    → Evidence → Rerank → Context → LLM → 引用可追溯到本次检索结果"。
#
# 核心原则：
#   - 严禁 LLM 编造论文(title/authors/journal/PMID/PMCID/DOI/year 必须来自 API)
#   - Evidence 是唯一可信来源；无证据时明确回答"未检索到足够相关的文献证据。"
#   - 第一阶段不引入 Vector DB / Embedding；API Search + 确定性 relevance score + Top-K
#   - 主源 Europe PMC，备源 PubMed；API 失败 ≠ 无结果（错误必须明确区分）

from .evidence import Evidence
from .errors import LiteratureSearchError
from .search import search_literature, fetch_full_text
from .reranker import rerank
from .context import build_context, EVIDENCE_SYSTEM_PROMPT
from .validator import validate_citations
from .query_generator import generate_query
from .pipeline import answer_question, LiteratureAnswer

__all__ = [
    "Evidence",
    "LiteratureSearchError",
    "search_literature",
    "fetch_full_text",
    "rerank",
    "build_context",
    "EVIDENCE_SYSTEM_PROMPT",
    "validate_citations",
    "generate_query",
    "answer_question",
    "LiteratureAnswer",
]

__version__ = "0.1.0"
