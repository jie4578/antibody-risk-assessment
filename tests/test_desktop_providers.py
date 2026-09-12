import os

from desktop.providers import PROVIDERS, all_provider_ids, provider_spec, resolve_config, resolve_model
from desktop.settings import RuntimeLLMConfig


def test_registry_contains_all_providers_with_unique_ids():
    assert set(all_provider_ids()) == {"deepseek", "openai", "openai-compatible", "ollama", "mock"}
    assert len(all_provider_ids()) == len(PROVIDERS)
    assert provider_spec("ollama").requires_api_key is False
    assert provider_spec("openai-compatible").requires_api_key is False
    assert provider_spec("deepseek").default_base_url == "https://api.deepseek.com"


def test_model_resolution_is_explicit_and_preserves_custom_ids():
    assert resolve_model("deepseek", "DeepSeek V4.1 Flash") == "deepseek-flash"
    assert resolve_model("deepseek", "Deepseek-V4.1-Flash") == "deepseek-flash"
    assert resolve_model("deepseek", "deepseek-flash") == "deepseek-flash"
    assert resolve_model("deepseek", "DeepSeek V4 Pro") == "deepseek-v4-pro"
    assert resolve_model("deepseek", "  My-New_Model  ") == "My-New_Model"
    assert resolve_model("openai-compatible", "Vendor Model/7") == "Vendor Model/7"


def test_runtime_values_beat_environment_and_defaults(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "env-key")
    monkeypatch.setenv("ANTIBODY_AI_BASE_URL", "https://env.example/v1")
    monkeypatch.setenv("ANTIBODY_AI_MODEL", "env-model")
    monkeypatch.setenv("ANTIBODY_AI_TIMEOUT", "99")
    config = resolve_config(RuntimeLLMConfig("deepseek", "runtime-key", "https://runtime/v1", "runtime-model", 7))
    assert (config.provider, config.api_key, config.base_url, config.model, config.timeout) == ("deepseek", "runtime-key", "https://runtime/v1", "runtime-model", 7.0)


def test_environment_beats_provider_defaults_and_empty_values_fall_through():
    env = {"DEEPSEEK_API_KEY": "env-key", "ANTIBODY_AI_BASE_URL": "https://env/v1", "ANTIBODY_AI_MODEL": "env-model", "ANTIBODY_AI_TIMEOUT": "12"}
    config = resolve_config(RuntimeLLMConfig("deepseek", "", "", "", 0), env)
    assert (config.api_key, config.base_url, config.model, config.timeout) == ("env-key", "https://env/v1", "env-model", 12.0)
    defaults = resolve_config(RuntimeLLMConfig("deepseek", "", "", "", 30), {})
    assert (defaults.base_url, defaults.model, defaults.timeout) == ("https://api.deepseek.com", "deepseek-flash", 30.0)


def test_legacy_deepseek_settings_value_resolves_to_api_id(tmp_path):
    from desktop.settings import load_settings
    path = tmp_path / "settings.json"
    path.write_text('{"provider":"deepseek","model":"Deepseek-V4.1-Flash"}', encoding="utf-8")
    assert load_settings(path).model == "deepseek-flash"


def test_legacy_model_reaches_backend_as_api_id(monkeypatch):
    import sys
    import types
    class FakeClient:
        def __init__(self, **kwargs): self.kwargs = kwargs
    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=FakeClient))
    from desktop.settings import build_backend
    backend = build_backend(RuntimeLLMConfig("deepseek", "key", "https://api.deepseek.com", "Deepseek-V4.1-Flash", 5))
    assert backend._model == "deepseek-flash"
    assert backend._extra_body == {"thinking": {"type": "disabled"}}


def test_deepseek_alias_does_not_leak_to_other_providers():
    assert resolve_model("openai", "Deepseek-V4.1-Flash") == "Deepseek-V4.1-Flash"


def test_provider_defaults_and_mock_are_deterministic():
    assert resolve_config(RuntimeLLMConfig("ollama", "", "", "", 30), {}).model == "qwen2.5:7b"
    assert resolve_config(RuntimeLLMConfig("mock", "", "", "", 30), {}).provider == "mock"
