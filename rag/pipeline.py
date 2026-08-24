# rag/pipeline.py
# RAG 端到端管线：文档 → 分块 → 向量化 → 存储 → 检索 → 上下文构建 → prompt 组装。

from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np

from .chunking import chunk_document
from .context import assemble_prompt, build_context
from .embeddings import get_embedder
from .retrieval import retrieve
from .store import VectorStore


class RagPipeline:
    """一站式 RAG 管线，离线可跑。

    用法：
        pipe = RagPipeline(embedder="tfidf", strategy="hybrid")
        pipe.index(documents)          # documents: [{title, source, text}, ...]
        result = pipe.query("脱酰胺化主要发生在哪里？")
        print(result["context"]); print(result["prompt"])
    """

    def __init__(
        self,
        *,
        embedder: str = "tfidf",
        strategy: str = "hybrid",
        top_k: int = 4,
        chunk_strategy: str = "heading",
        chunk_max_len: int = 800,
        chunk_overlap: int = 100,
        on_embed_query: str = "translate",
    ):
        self._embedder_name = embedder
        self._embedder = get_embedder(embedder) if embedder != "tfidf" else None  # tfidf 需在 index 后 fit
        self.strategy = strategy
        self.top_k = top_k
        self.chunk_strategy = chunk_strategy
        self.chunk_max_len = chunk_max_len
        self.chunk_overlap = chunk_overlap
        self.store = VectorStore()
        self._indexed = False

    # ---------- 索引 ----------
    def index(self, documents: List[Dict[str, str]]) -> "RagPipeline":
        chunks = self.chunk_documents(documents)
        # tfidf 需先 fit 全部文本
        if self._embedder is None:
            from .embeddings import TfidfEmbedder

            self._embedder = TfidfEmbedder()
            self._embedder.fit([c.text for c in chunks])
        vectors = self._embedder.embed_documents([c.text for c in chunks])
        ids = [c.chunk_id for c in chunks]
        meta = [{"title": c.metadata.get("title", ""), "source": c.source, "index": c.index} for c in chunks]
        self.store.add(ids, [c.text for c in chunks], vectors, meta)
        self._indexed = True
        return self

    def chunk_documents(self, documents: List[Dict[str, str]]):
        from .chunking import Chunk

        out: List[Chunk] = []
        for doc_i, d in enumerate(documents):
            text = d.get("text", "")
            title = d.get("title", "")
            source = d.get("source", title)
            for c in chunk_document(
                text,
                strategy=self.chunk_strategy,
                source=source,
                max_len=self.chunk_max_len,
                overlap=self.chunk_overlap,
            ):
                c.metadata["title"] = title
                # 关键：chunk_id 必须全局唯一（source + 文档序号 + 块序号），否则 store 内 id 冲突
                c.chunk_id = f"{doc_i}--{c.chunk_id}"
                out.append(c)
        return out

    # ---------- 查询 ----------
    def query(self, question: str, *, top_k: Optional[int] = None, assemble: bool = True) -> Dict[str, object]:
        if not self._indexed:
            raise RuntimeError("请先调用 index() 建立索引")
        k = top_k or self.top_k
        hits = retrieve(question, self.store, self._embedder, top_k=k, strategy=self.strategy)
        context = build_context(hits, max_chars=2000)
        result = {
            "question": question,
            "hits": hits,
            "context": context,
            "prompt": "",
        }
        if assemble:
            result["prompt"] = assemble_prompt(question, context)
        return result
