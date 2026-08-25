# literature/query_generator.py
# Query Generator：把用户自然语言问题转换成适合 Europe PMC / PubMed 的检索词。
#
# 铁律：只生成"检索词"，绝对禁止生成论文标题 / PMID / DOI / 作者 / 引用。
#   - 有 LLM(key)：用 LLM 生成专业检索式(AND/OR/引号)，并做轻量校验，异常则回退规则。
#   - 无 LLM：简单关键词抽取 + 小型中英术语映射兜底（仍只出词）。

from __future__ import annotations

import re
from typing import Tuple

# 常见抗体/PTM 术语中→英映射（离线兜底用，覆盖演示常见问题）
TERM_MAP = {
    "脱酰胺化": "deamidation", "脱酰胺": "deamidation",
    "糖基化": "glycosylation", "氧化": "oxidation", "异构化": "isomerization",
    "异天冬氨酸": "isoaspartate", "琥珀酰亚胺": "succinimide",
    "抗体": "antibody", "单克隆抗体": "monoclonal antibody",
    "免疫原性": "immunogenicity", "聚集": "aggregation", "稳定性": "stability",
    "可开发性": "developability", "天冬酰胺": "asparagine", "天冬氨酸": "aspartate",
    "甲硫氨酸": "methionine", "丝氨酸": "serine", "半胱氨酸": "cysteine",
    "蛋白": "protein", "结构": "structure", "序列": "sequence",
}

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9-]*")
_LLM_FORBIDDEN = ("PMID", "DOI", "Title", "作者", "标题", "期刊", "引用", "Reference", "https://")

_QUERY_PROMPT = (
    "你是生物医学文献检索专家。把下面的用户问题转换成适合 Europe PMC / PubMed 的检索式。\n"
    "规则：只输出检索词/检索式（可用 AND、OR、双引号），不要任何解释、编号、冒号前缀；\n"
    "绝对禁止输出论文标题、PMID、DOI、作者、期刊名或引用。\n"
    "问题: {question}\n检索式:"
)


def _rule_query(question: str) -> str:
    q = question or ""
    terms: list = []
    for cn, en in TERM_MAP.items():
        if cn in q:
            if en not in terms:
                terms.append(en)
    terms += [w.lower() for w in _WORD_RE.findall(q) if len(w) > 2 and w.lower() not in terms]
    # 去掉过于通用的英文词
    noisy = {"what", "why", "how", "which", "some", "any", "about", "with", "the", "are", "is"}
    terms = [t for t in terms if t not in noisy]
    return " ".join(terms) or "antibody"


def _llm_query(question: str, backend: str) -> Tuple[str, bool]:
    from agent.llm import get_llm

    llm = get_llm(backend)
    raw = llm.complete(_QUERY_PROMPT.format(question=question)).strip()
    if not raw:
        return "", False
    # 轻量校验：出现论文/引文特征 → 拒绝（回退规则）
    upper = raw.upper()
    if any(f in upper for f in _LLM_FORBIDDEN) or re.search(r"\b\d{6,9}\b", raw):
        return "", False
    return raw, True


def generate_query(question: str, backend: str = "auto") -> Tuple[str, str]:
    """生成检索词。返回 (query, mode)，mode ∈ {"llm", "rule"}。

    - backend="auto" 时按 .env 自动选择；mock/无 key 走 rule。
    - 本函数只产出检索词，绝不产出论文元数据。
    """
    if backend == "auto":
        from config import auto_llm_backend

        backend = auto_llm_backend()

    if backend in ("deepseek", "openai"):
        try:
            q, ok = _llm_query(question, backend)
            if ok and q:
                return q, "llm"
        except Exception:
            pass  # LLM 异常 → 规则兜底

    return _rule_query(question), "rule"
