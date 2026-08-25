# literature/validator.py
# Citation Validator：检查最终 LLM 回答中的 PMID / DOI 是否都存在于本次 Evidence。
# 回答中出现证据之外的 PMID/DOI → FAIL；绝不 silent accept。

from __future__ import annotations

import re
from typing import Dict, List, Sequence

from .evidence import Evidence

_PMID_RE = re.compile(r"PMID\s*[:：]?\s*(\d{6,9})", re.IGNORECASE)
_DOI_RE = re.compile(r"10\.\d{4,9}/[^\s，。；、,;()（）\[\]{}'\"<>]+")


def extract_references(answer: str) -> Dict[str, List[str]]:
    """从回答中提取 PMID 与 DOI（去重、保序）。"""
    pmids = list(dict.fromkeys(_PMID_RE.findall(answer or "")))
    dois = list(dict.fromkeys(_DOI_RE.findall(answer or "")))
    return {"pmids": pmids, "dois": dois}


def _evidence_ids(evidence: Sequence[Evidence]) -> Dict[str, List[str]]:
    pmids = {e.pmid for e in evidence if e.pmid}
    dois = {e.doi for e in evidence if e.doi}
    return {"pmids": pmids, "dois": dois}


def validate_citations(answer: str, evidence: Sequence[Evidence]) -> Dict[str, object]:
    """校验回答中的 PMID/DOI 是否都在本次 Evidence 内。

    返回:
        valid:              bool（无非法引用即为 True）
        invalid_references: [{"type": "pmid"|"doi", "value": "..."}, ...]
        warnings:           [str, ...]（如"回答未包含可识别的引用"）
    """
    refs = extract_references(answer)
    pool = _evidence_ids(evidence)
    invalid = []
    for pmid in refs["pmids"]:
        if pmid not in pool["pmids"]:
            invalid.append({"type": "pmid", "value": pmid})
    for doi in refs["dois"]:
        if doi not in pool["dois"]:
            invalid.append({"type": "doi", "value": doi})

    warnings: List[str] = []
    if not refs["pmids"] and not refs["dois"]:
        warnings.append("回答未包含可识别的 PMID/DOI 引用（可能是证据不足的明确回答）。")

    return {
        "valid": len(invalid) == 0,
        "invalid_references": invalid,
        "warnings": warnings,
    }
