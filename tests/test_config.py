# tests/test_config.py
# config.py 测试：.env 解析 / 环境变量读取 / 必填变量报错。

import pytest

from config import get_env, load_dotenv, require_env


def test_load_dotenv_parses_file(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        '# 注释\nDEEPSEEK_API_KEY=sk-test123\nOPENAI_API_KEY="sk-quoted"\nEMPTY=\n',
        encoding="utf-8",
    )
    load_dotenv(str(env_file))
    assert get_env("DEEPSEEK_API_KEY") == "sk-test123"
    assert get_env("OPENAI_API_KEY") == "sk-quoted"


def test_get_env_default():
    assert get_env("NON_EXISTENT_KEY_XYZ", "fallback") == "fallback"
    assert get_env("NON_EXISTENT_KEY_XYZ") is None


def test_require_env_missing_raises():
    with pytest.raises(RuntimeError, match="NON_EXISTENT_KEY_XYZ"):
        require_env("NON_EXISTENT_KEY_XYZ")
