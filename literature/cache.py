# literature/cache.py
# 文献检索结果缓存：SQLite，key = normalized_query + source + max_results，TTL 默认 7 天。
# 缓存目录 literature_cache/ 已在 .gitignore 排除，真实缓存绝不提交 Git。

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from typing import Any, Optional

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DEFAULT_DB = os.path.join(_ROOT, "literature_cache", "lit_cache.db")


def normalize_query(query: str) -> str:
    """规范化检索词：小写 + 折叠空白（用于缓存 key 与稳定排序）。"""
    return " ".join(str(query or "").lower().split())


def cache_key(query: str, source: str, max_results: int) -> str:
    return f"{normalize_query(query)}|{source}|{max_results}"


class LiteratureCache:
    """SQLite 缓存（线程安全）。只缓存成功检索结果，不缓存错误。"""

    def __init__(self, db_path: Optional[str] = None, ttl_seconds: int = 7 * 24 * 3600):
        if db_path is None:
            from config import get_env

            db_path = get_env("LITERATURE_CACHE_PATH", _DEFAULT_DB)
        self.db_path = db_path
        self.ttl_seconds = ttl_seconds
        os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS searches ("
            "cache_key TEXT PRIMARY KEY, payload TEXT, created_at REAL)"
        )
        self._conn.commit()

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            row = self._conn.execute(
                "SELECT payload, created_at FROM searches WHERE cache_key=?", (key,)
            ).fetchone()
            if not row:
                return None
            payload, created = row
            if time.time() - created > self.ttl_seconds:
                self._conn.execute("DELETE FROM searches WHERE cache_key=?", (key,))
                self._conn.commit()
                return None
            return json.loads(payload)

    def set(self, key: str, payload: Any) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO searches (cache_key, payload, created_at) VALUES (?,?,?)",
                (key, json.dumps(payload, ensure_ascii=False), time.time()),
            )
            self._conn.commit()

    def clear(self) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM searches")
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()


_default: Optional[LiteratureCache] = None
_default_lock = threading.Lock()


def get_cache() -> LiteratureCache:
    """进程级默认缓存实例（惰性创建）。"""
    global _default
    if _default is None:
        with _default_lock:
            if _default is None:
                _default = LiteratureCache()
    return _default
