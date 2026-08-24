# rag/chunking.py
# 文档分块：把长文档切成适合检索的片段。
#
# 策略：
#   - chunk_by_heading: 按 Markdown 标题(##/###)切,每个标题+正文作为一块；
#   - chunk_by_length:  按字符长度滑动窗口切,带重叠,避免切断语义；
#   - chunk_document:   'auto' 优先标题切分,再对超长块按长度二次切分。

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List


@dataclass
class Chunk:
    text: str
    chunk_id: str
    source: str = ""
    index: int = 0
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "chunk_id": self.chunk_id,
            "source": self.source,
            "index": self.index,
            "text": self.text,
            "metadata": dict(self.metadata),
        }


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$", re.MULTILINE)


def chunk_by_heading(text: str, *, source: str = "", max_chunk_len: int = 1200) -> List[Chunk]:
    """
    按 Markdown 标题切分文档。每级标题(含其后续层级标题之前的正文)形成一块。
    超长的块再用 chunk_by_length 二次切分。
    """
    if not text or not text.strip():
        return []
    matches = list(_HEADING_RE.finditer(text))
    if not matches:
        return chunk_by_length(text, max_len=max_chunk_len, source=source)

    chunks: List[Chunk] = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        heading = m.group(2).strip()
        body = text[start:end].strip()
        if not body:
            continue
        # 用 heading 作为一个"线索"，拼接进 text 便于检索到语义
        block_text = heading + "\n" + body if heading else body
        if len(block_text) <= max_chunk_len:
            chunks.append(Chunk(text=block_text, chunk_id=f"{source}-h{i}", source=source, index=i))
        else:
            sub = chunk_by_length(block_text, max_len=max_chunk_len, source=source)
            for j, c in enumerate(sub):
                c.chunk_id = f"{source}-h{i}-s{j}"
                c.index = i * 1000 + j
                chunks.append(c)
    return chunks


def chunk_by_length(text: str, *, max_len: int = 800, overlap: int = 100, source: str = "") -> List[Chunk]:
    """按字符长度滑动窗口切分，块与块之间有 overlap 重叠。"""
    text = (text or "").strip()
    if not text:
        return []
    if max_len <= overlap or max_len <= 0:
        raise ValueError("max_len 必须大于 overlap 且为正")
    chunks: List[Chunk] = []
    start = 0
    idx = 0
    n = len(text)
    while start < n:
        end = min(start + max_len, n)
        chunk_text = text[start:end].strip()
        if chunk_text:
            chunks.append(Chunk(text=chunk_text, chunk_id=f"{source}-c{idx}", source=source, index=idx))
            idx += 1
        if end >= n:
            break
        start = end - overlap
        if start >= end:
            start = end
    return chunks


def chunk_document(text: str, *, strategy: str = "auto", source: str = "", max_len: int = 800, overlap: int = 100) -> List[Chunk]:
    """统一分块入口。strategy ∈ {auto, heading, length}。"""
    if strategy == "heading":
        return chunk_by_heading(text, source=source, max_chunk_len=max_len)
    if strategy == "length":
        return chunk_by_length(text, max_len=max_len, overlap=overlap, source=source)
    if strategy == "auto":
        return chunk_by_heading(text, source=source, max_chunk_len=max_len)
    raise ValueError(f"未知分块策略: {strategy}（可选 auto / heading / length）")
