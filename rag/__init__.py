# rag/__init__.py
# 检索增强生成 (Retrieval-Augmented Generation) 模块。
#
# 目标（对应岗位要求 #3）：理解并具备 RAG 基础实现经验——
#   向量化 / 检索策略 / 上下文构建。
#
# 设计要点：
#   - 可离线：默认 Embedding 用 TF-IDF(稀疏) + n-gram 哈希(稠密)，无需外部模型/网络；
#   - 可选重型：装 sentence-transformers / faiss 可升级为真实向量检索；
#   - 模块职责单一：chunking / embeddings / store / retrieval / context / pipeline。

from .chunking import chunk_by_heading, chunk_by_length, chunk_document
from .embeddings import HashingEmbedder, TfidfEmbedder, get_embedder
from .store import VectorStore
from .retrieval import retrieve
from .pipeline import RagPipeline

__all__ = [
    "chunk_by_heading",
    "chunk_by_length",
    "chunk_document",
    "HashingEmbedder",
    "TfidfEmbedder",
    "get_embedder",
    "VectorStore",
    "retrieve",
    "RagPipeline",
]

__version__ = "0.1.0"
