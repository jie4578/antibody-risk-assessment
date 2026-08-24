# tests/test_rag.py
# RAG 模块测试：分块 / Embedding / 向量存储 / 检索 / 上下文 / 端到端管线。

import numpy as np
import pytest

from rag.chunking import chunk_by_heading, chunk_by_length, chunk_document
from rag.context import assemble_prompt, build_context
from rag.embeddings import HashingEmbedder, TfidfEmbedder, get_embedder
from rag.knowledge_base import KNOWLEDGE_BASE
from rag.pipeline import RagPipeline
from rag.retrieval import retrieve
from rag.store import VectorStore, cosine_similarity


# ---------- chunking ----------
def test_chunk_by_length_overlap():
    text = "A" * 500 + "B" * 500
    chunks = chunk_by_length(text, max_len=300, overlap=50)
    assert len(chunks) > 2
    # 相邻块应有重叠
    joined_texts = [c.text for c in chunks]
    assert any(joined_texts[i] in joined_texts[i + 1] or joined_texts[i + 1] in joined_texts[i] for i in range(len(chunks) - 1))


def test_chunk_by_length_invalid():
    with pytest.raises(ValueError):
        chunk_by_length("abc", max_len=10, overlap=100)


def test_chunk_by_heading():
    md = "# 标题一\n正文一\n正文一\n## 标题二\n正文二"
    chunks = chunk_by_heading(md)
    assert len(chunks) == 2
    assert "标题一" in chunks[0].text


def test_chunk_document_strategies():
    md = "## A\n内容\n## B\n更多内容"
    assert len(chunk_document(md, strategy="heading")) == 2
    assert len(chunk_document(md, strategy="length")) >= 1
    with pytest.raises(ValueError):
        chunk_document(md, strategy="nope")


# ---------- embeddings ----------
def test_tfidf_embedder_requires_fit():
    e = TfidfEmbedder()
    with pytest.raises(RuntimeError):
        e.embed_query("hello")


def test_tfidf_embedder_roundtrip():
    e = TfidfEmbedder().fit(["脱酰胺化主要发生在 Asn-Gly", "甲硫氨酸易被氧化"])
    Q = e.embed_query("脱酰胺化")
    assert Q.dtype == np.float32
    assert Q.ndim == 1


def test_hashing_embedder_deterministic():
    e = HashingEmbedder(dim=64)
    a = e.embed_documents(["hello world"])
    b = e.embed_documents(["hello world"])
    np.testing.assert_array_equal(a, b)
    assert a.shape[1] == 64


def test_get_embedder_unknown():
    with pytest.raises(ValueError):
        get_embedder("nope")


# ---------- store ----------
def test_vector_store_search():
    store = VectorStore(dim=3)
    store.add(
        ids=["a", "b"],
        texts=["alpha", "beta"],
        vectors=np.array([[1.0, 0, 0], [0, 1.0, 0]], dtype=np.float32),
        metadata=[{"source": "s1"}, {"source": "s2"}],
    )
    hits = store.search(np.array([1.0, 0, 0]), top_k=2)
    assert hits[0]["id"] == "a"
    assert hits[0]["score"] > 0.9


def test_vector_store_empty():
    store = VectorStore(dim=3)
    assert store.search(np.array([1.0, 0, 0])) == []


def test_cosine_similarity():
    a = np.array([[1.0, 0, 0]], dtype=np.float32)
    b = np.array([[1.0, 0, 0], [0, 1.0, 0]], dtype=np.float32)
    sims = cosine_similarity(a, b)
    assert abs(sims[0] - 1.0) < 1e-4
    assert abs(sims[1]) < 1e-4


# ---------- retrieval ----------
def test_retrieve_vector_requires_embedder():
    store = VectorStore(dim=4)
    store.add(ids=["x"], texts=["some text"], vectors=np.array([[1, 0, 0, 0]], dtype=np.float32))
    with pytest.raises(ValueError):
        retrieve("q", store, None, strategy="vector")


def test_retrieve_hybrid():
    pipe = RagPipeline(embedder="tfidf", strategy="hybrid", top_k=2)
    pipe.index(KNOWLEDGE_BASE)
    hits = retrieve("抗体脱酰胺化", pipe.store, pipe._embedder, top_k=3, strategy="hybrid")
    assert len(hits) > 0
    # 脱酰胺化相关文档应出现在结果中
    assert any("脱酰胺" in h["text"] for h in hits)


# ---------- context ----------
def test_build_context_and_prompt():
    hits = [{"id": "1", "text": "甲硫氨酸易被氧化", "metadata": {"source": "ptm"}, "score": 0.9}]
    ctx = build_context(hits)
    assert "甲硫氨酸" in ctx
    prompt = assemble_prompt("甲硫氨酸会怎样？", ctx)
    assert "甲硫氨酸" in prompt
    assert "甲硫氨酸会怎样" in prompt


# ---------- pipeline ----------
def test_pipeline_requires_index():
    pipe = RagPipeline(embedder="tfidf", strategy="hybrid")
    with pytest.raises(RuntimeError):
        pipe.query("hello")


def test_pipeline_end_to_end():
    pipe = RagPipeline(embedder="tfidf", strategy="hybrid", top_k=3)
    pipe.index(KNOWLEDGE_BASE)
    result = pipe.query("抗体的脱酰胺化主要发生在哪里？有什么影响？")
    assert result["hits"]
    assert result["context"]
    assert result["prompt"]
    top = result["hits"][0]
    assert "脱酰胺" in top["text"]


def test_pipeline_ids_unique():
    pipe = RagPipeline(embedder="tfidf", strategy="hybrid")
    pipe.index(KNOWLEDGE_BASE)
    ids = [c.chunk_id for c in pipe.chunk_documents(KNOWLEDGE_BASE)]
    assert len(set(ids)) == len(ids)
