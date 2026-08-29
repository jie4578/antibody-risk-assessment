# agent/literature_relevance.py
# v7 文献相关性判断（确定性，供文献证据层使用）。
#
# 问题：literature_search 返回多篇文献后，不得"因为有文献返回"就强行引用。
# 本模块按用户问题主题对每篇文献做相关性分类，并生成注记喂给 Final Agent：
#   direct      直接相关（如含脱酰胺主题且涉及抗体/CDR）
#   general     一般相关（仅脱酰胺一般机制，未涉及本序列/本抗体）
#   irrelevant  无关（其他主题，如 N-糖基化，不得用于支持 NG 脱酰胺风险）
# 同时明确：相关性按主题判定，不等于"已验证本抗体/本 N55 位点"。

from __future__ import annotations

import re
from typing import Dict, List, Optional

_DEAMIDATION_TERMS = (
    "deamidat", "脱酰胺", "asn-gly", "asparagine", "succinimide",
    "isoaspart", "iso-asp", "asn-gln", "desamidation",
)
_ISOMERIZATION_TERMS = ("isomeriz", "异构化", "isoaspart", "iso-asp", "asp-gly")
_OXIDATION_TERMS = ("oxid", "氧化", "methionine", "reactive oxygen")
_GLYCO_TERMS = ("glycosylation", "糖基化", "glycan", "fucosylation", "galactosylation", "glyco-")
_ANTIBODY_TERMS = (
    "antibody", "antibodies", "immunoglobulin", "mab", "therapeutic protein",
    "biologic", "cdr", "抗体",
)

# 主题表：主题名 -> (主题词, 显示名)。标题主题优先于摘要偶然关键词。
_TOPICS = {
    "deamidation": (_DEAMIDATION_TERMS, "脱酰胺"),
    "isomerization": (_ISOMERIZATION_TERMS, "异构化"),
    "oxidation": (_OXIDATION_TERMS, "氧化"),
    "glycosylation": (_GLYCO_TERMS, "糖基化"),
}


def _question_topic(question: str) -> str:
    q = (question or "").lower()
    # 位点形如 ng@55-56 / ng55 → 脱酰胺主题；dg@ → 异构化
    if re.search(r"\bng@\d|\bng\d", q) or any(t in q for t in _DEAMIDATION_TERMS):
        return "deamidation"
    if re.search(r"\bdg@\d|\bdg\d", q) or any(t in q for t in _ISOMERIZATION_TERMS):
        return "isomerization"
    if any(t in q for t in _OXIDATION_TERMS):
        return "oxidation"
    if any(t in q for t in _GLYCO_TERMS):
        return "glycosylation"
    return "general"


def _parse_entries(result_text: str) -> List[Dict]:
    """解析 literature_search 返回文本为条目列表。"""
    txt = str(result_text or "")
    head = txt.strip()[:20]
    if not txt.strip() or head.startswith(("未检索到", "错误", "检索失败")):
        return []
    entries = []
    for block in re.split(r"\n\s*\n", txt.strip()):
        m = re.match(r"\[(\d+)\]\s*Title:\s*(.+?)(?:\n|$)", block)
        if not m:
            continue
        pmid = re.search(r"PMID:\s*([0-9A-Za-z]+)", block)
        doi = re.search(r"DOI:\s*([^\s]+)", block)
        year = re.search(r"Journal:\s*.+?\((\d{4})\)", block)
        abstract = ""
        am = re.search(r"Abstract:\s*(.*)", block, re.S)
        if am:
            abstract = am.group(1).strip()
        entries.append({
            "index": int(m.group(1)),
            "title": m.group(2).strip(),
            "pmid": pmid.group(1) if pmid else "",
            "doi": doi.group(1) if doi else "",
            "year": year.group(1) if year else "",
            "abstract": abstract,
        })
    return entries


def _classify_for_topic(topic: str, title: str, abstract: str):
    """标题主题优先：标题命中主题 → direct/general；标题命中其他明确主题 → irrelevant；
    摘要只作辅助，不能凭单个关键词覆盖明显冲突的标题主题。"""
    # 主题未识别（general）或未知主题 → 不抛异常，统一按一般处理
    if topic not in _TOPICS:
        return "general", "主题未明确"
    terms, name = _TOPICS[topic]
    title_hit = any(t in title for t in terms)
    abstract_hit = any(t in abstract for t in terms)
    if title_hit:
        if any(t in title for t in _ANTIBODY_TERMS) or any(t in abstract for t in _ANTIBODY_TERMS):
            return "direct", f"{name}主题且涉及抗体/CDR"
        return "general", f"{name}一般机制（未涉及本抗体）"
    # 标题未命中主题 → 其他明确主题优先于摘要偶然关键词
    for other, (oterms, oname) in _TOPICS.items():
        if other == topic:
            continue
        if any(t in title for t in oterms):
            return "irrelevant", f"标题主题为{oname}，与{topic}问题无关"
    if abstract_hit:
        return "general", f"摘要涉及{name}一般机制（标题主题不同，仅作一般参考）"
    return "irrelevant", f"未涉及{name}主题"


def classify_literature_relevance(question: str, result_text: str) -> List[Dict]:
    """对 literature_search 返回的每篇文献做相关性分类（标题主题优先）。"""
    topic = _question_topic(question)
    out = []
    for e in _parse_entries(result_text):
        rel, reason = _classify_for_topic(topic, e["title"].lower(), e["abstract"].lower())
        out.append({**e, "relevance": rel, "reason": reason})
    return out


def build_user_assertion_note(question: str, observations) -> Optional[str]:
    """用户问题中出现的位点串，若工具未返回，生成「用户给定」注记。

    防止 Final Agent 把"用户问题中写到的位点"冒充为"工具识别/rule_based 检测"。
    只有工具实际返回的位点才能称为工具事实。
    """
    q = str(question or "")
    positions = set(re.findall(r"[A-Z]{1,3}@\d+(?:-\d+)?", q))
    positions |= set(re.findall(r"\b[A-Z]\d{2,3}\b", q))
    if not positions:
        return None
    tool_text = " ".join(str(o.result) for o in observations or [])
    unconfirmed = sorted(p for p in positions if p not in tool_text)
    if not unconfirmed:
        return None
    return (
        "事实来源注记:用户问题中出现的位点(" + "、".join(unconfirmed) +
        ")在本次工具返回中未被确认，属于「用户给定/未经工具验证」。"
        "不得将其描述为「工具识别/工具检测/rule_based 检测/工具结果显示」。"
        "如需判断其真实性，应调用 scan_antibody 等工具。"
    )


def build_literature_note(question: str, observations) -> Optional[str]:
    """从 literature_search 观察生成相关性注记（无 direct 时明确"未找到直接相关文献"）。

    注记仅供最终回答参考；按主题判定，不等于对当前序列/位点的实验验证。
    """
    notes = []
    for obs in observations or []:
        if getattr(obs, "tool", None) != "literature_search":
            continue
        if str(obs.result).strip()[:20].startswith(("未检索到", "错误", "检索失败")):
            continue
        for a in classify_literature_relevance(question, obs.result):
            notes.append(
                f"第{a['index']}篇《{a['title'][:60]}》(PMID {a['pmid'] or '-'}): "
                f"相关性={a['relevance']}({a['reason']})"
            )
    if not notes:
        return None
    if not any("相关性=direct" in n for n in notes):
        notes.append("本次检索未找到直接相关文献。")
    return (
        "文献相关性判断（按主题判定，未验证是否针对本抗体/本位点）:\n" + "\n".join(notes)
    )
