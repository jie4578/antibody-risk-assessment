# rag/context.py
# 上下文构建：把检索到的文档块组装成"可供 LLM 理解的上下文 + 带引用的 prompt"。

from __future__ import annotations

from typing import List, Optional


def build_context(hits: List[dict], *, max_chars: int = 2000, include_metadata: bool = True) -> str:
    """
    把检索命中列表拼成上下文文本。每条带 [n] 引用编号，便于溯源。

    hits: retrieve() 返回的 [{id, text, metadata, score}] 列表。
    """
    if not hits:
        return ""
    parts: List[str] = []
    total = 0
    for i, hit in enumerate(hits, start=1):
        text = hit.get("text", "").strip()
        if not text:
            continue
        head = text if len(text) <= max_chars else text[:max_chars]
        meta = hit.get("metadata", {})
        src = meta.get("source", "") or meta.get("title", "")
        prefix = f"[{i}] " + (f"({src}) " if include_metadata and src else "")
        block = f"{prefix}{head}"
        if total + len(block) > max_chars and parts:
            break
        parts.append(block)
        total += len(block)
    return "\n\n".join(parts)


def assemble_prompt(
    query: str,
    context: str,
    *,
    system_prompt: str = "",
    template: Optional[str] = None,
) -> str:
    """
    组装最终 prompt。默认模板把上下文放在问题前，并引导模型基于上下文回答。
    """
    if template is None:
        template = (
            "你是一个抗体可开发性领域专家。请基于以下参考资料回答用户问题。\n"
            "若参考资料不足，请明确说明，不要编造。\n\n"
            "【参考资料】\n{context}\n\n"
            "【用户问题】\n{question}\n"
        )
    if system_prompt:
        template = f"{system_prompt}\n\n" + template
    return template.format(context=context.strip() or "（无）", question=query)
