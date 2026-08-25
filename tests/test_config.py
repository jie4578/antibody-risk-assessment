# tests/test_config.py
# config.py 测试：.env 解析 / 环境变量读取 / 必填变量报错。

import pytest

from config import get_env, load_dotenv, require_env


def test_load_dotenv_parses_file(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        '# 注释\nDEEPSEEK_API_KEY=test-value-123\nOPENAI_API_KEY="test-value-quoted"\nEMPTY=\n',
        encoding="utf-8",
    )
    # 隔离：清掉可能已从真实 .env 载入的 key，保证本测试用测试值
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    load_dotenv(str(env_file))
    assert get_env("DEEPSEEK_API_KEY") == "test-value-123"
    assert get_env("OPENAI_API_KEY") == "test-value-quoted"


def test_get_env_default():
    assert get_env("NON_EXISTENT_KEY_XYZ", "fallback") == "fallback"
    assert get_env("NON_EXISTENT_KEY_XYZ") is None


def test_require_env_missing_raises():
    with pytest.raises(RuntimeError, match="NON_EXISTENT_KEY_XYZ"):
        require_env("NON_EXISTENT_KEY_XYZ")


def test_auto_llm_backend_mock_without_key(monkeypatch):
    import config

    monkeypatch.setattr(config, "_DOTENV_PATHS", [])
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert config.auto_llm_backend() == "mock"


def test_auto_llm_backend_deepseek_with_key(monkeypatch):
    import config

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    assert config.auto_llm_backend() == "deepseek"
