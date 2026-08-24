# config.py
# 轻量配置：读取仓库根目录 .env（若存在）并合并进环境变量，供 LLM API key 等使用。
#
# .env 已被 .gitignore 排除，不会上传；格式见 .env.example。
#
# 用法：
#   from config import get_env
#   key = get_env("DEEPSEEK_API_KEY")

from __future__ import annotations

import os
from typing import Optional

_ROOT = os.path.dirname(os.path.abspath(__file__))
_DOTENV_PATHS = [
    os.path.join(_ROOT, ".env"),
    os.path.join(os.getcwd(), ".env"),
]

_loaded = False


def load_dotenv(path: Optional[str] = None) -> None:
    """把指定（或默认候选）路径下的 .env 解析进 os.environ（已有变量不覆盖）。"""
    global _loaded
    if path is None:
        if _loaded:
            return
        _loaded = True
        for p in _DOTENV_PATHS:
            _parse_file(p)
    else:
        _parse_file(path)


def _parse_file(path: str) -> None:
    if not os.path.isfile(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
    except OSError:
        pass


def get_env(key: str, default: Optional[str] = None) -> Optional[str]:
    """读取环境变量（自动加载 .env）。"""
    load_dotenv()
    return os.environ.get(key, default)


def require_env(key: str) -> str:
    """读取必填环境变量，缺失时抛出带指引的 RuntimeError。"""
    value = get_env(key)
    if not value:
        raise RuntimeError(
            f"缺少环境变量 {key}。请在仓库根目录创建 .env 并写入（参考 .env.example），"
            f"例如: {key}=<your-key>"
        )
    return value
