import json
import os
import sys
import types
from pathlib import Path

import pytest

from desktop.credentials import CredentialStore
from desktop.settings import RuntimeLLMConfig, build_backend, load_settings, save_settings
from desktop.workers import sanitize_error


def test_runtime_config_repr_hides_api_key():
    config = RuntimeLLMConfig(provider="deepseek", api_key="sk-test-super-secret-value")
    assert "sk-test-super-secret-value" not in repr(config)


def test_settings_round_trip_never_persists_api_key(tmp_path):
    path = tmp_path / "settings.json"
    config = RuntimeLLMConfig("openai", "SECRET-DO-NOT-PERSIST", "https://example.test/v1", "model-x", 12)
    save_settings(config, path)
    raw = path.read_text(encoding="utf-8")
    assert "SECRET-DO-NOT-PERSIST" not in raw
    assert "api_key" not in json.loads(raw)
    loaded = load_settings(path)
    assert loaded.provider == "openai"
    assert loaded.api_key == ""
    assert loaded.timeout == 12


class FakeKeyring:
    values = {}
    def get_password(self, service, username): return self.values.get((service, username))
    def set_password(self, service, username, password): self.values[(service, username)] = password
    def delete_password(self, service, username): self.values.pop((service, username), None)


def test_credentials_use_session_and_keyring_without_plaintext_fallback():
    store = CredentialStore(FakeKeyring())
    store.set_session("openai", "session-secret")
    assert store.get("openai") == "session-secret"
    store.save_secure("deepseek", "secure-secret")
    assert store.get("deepseek") == "secure-secret"
    store.delete("deepseek")
    assert store.get("deepseek") == ""


@pytest.mark.parametrize("payload", ["{bad json", [], "abc", 123, None,
                                      {"timeout": "abc"}, {"timeout": None},
                                      {"timeout": -1}, {"timeout": 0},
                                      {"provider": [], "model": 1, "base_url": None}])
def test_corrupt_settings_fall_back_to_valid_config(tmp_path, payload):
    path = tmp_path / "settings.json"
    path.write_text(payload if isinstance(payload, str) else json.dumps(payload), encoding="utf-8")
    config = load_settings(path)
    assert isinstance(config, RuntimeLLMConfig)
    assert isinstance(config.timeout, float)
    assert 1 <= config.timeout <= 300
    assert isinstance(config.provider, str)
    assert isinstance(config.model, str)
    assert isinstance(config.base_url, str)


@pytest.mark.parametrize("text", [
    "API key sk-test-super-secret-value",
    "Bearer sk-test-super-secret-value",
    "Authorization: Bearer sk-test-super-secret-value",
    "api_key=sk-test-super-secret-value",
    "request failed: sk-test-super-secret-value",
    "sk-test-super-secret-value",
])
def test_secret_sanitizer_removes_known_secret(text):
    result = sanitize_error(text, secrets=["sk-test-super-secret-value"])
    assert "sk-test-super-secret-value" not in result
    assert "[REDACTED]" in result


@pytest.mark.parametrize("method", ["save_secure", "get", "delete"])
def test_keyring_failures_raise_explicit_error_without_plaintext_fallback(method, tmp_path):
    class BrokenKeyring:
        def __getattr__(self, name):
            raise RuntimeError("keyring unavailable")
    store = CredentialStore(BrokenKeyring())
    with pytest.raises(Exception):
        if method == "save_secure": store.save_secure("openai", "sk-test-super-secret-value")
        elif method == "get": store.get("openai")
        else: store.delete("openai")
    assert not list(tmp_path.iterdir())


def test_runtime_parameters_override_environment(monkeypatch):
    class FakeClient:
        def __init__(self, **kwargs): self.kwargs = kwargs
        class Chat:
            pass
    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=FakeClient))
    monkeypatch.setenv("DEEPSEEK_API_KEY", "old-key")
    from agent.llm import DeepSeekLLM, OpenAILLM
    deepseek = DeepSeekLLM(model="runtime-model", api_key="new-key", base_url="https://runtime/v1", timeout=7)
    assert deepseek._model == "runtime-model"
    assert deepseek._client.kwargs == {"api_key": "new-key", "base_url": "https://runtime/v1", "timeout": 7}
    compatible = OpenAILLM(model="compatible-model", api_key="compatible-key", base_url="https://custom/v1", timeout=9)
    assert compatible._model == "compatible-model"
    assert compatible._client.kwargs["base_url"] == "https://custom/v1"


def test_ollama_runtime_does_not_require_api_key(monkeypatch):
    class FakeClient:
        def __init__(self, **kwargs): self.kwargs = kwargs
    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=FakeClient))
    from agent.llm import LocalOllamaLLM
    backend = LocalOllamaLLM(model="qwen-test", base_url="http://localhost:1234/v1", timeout=5)
    assert backend._model == "qwen-test"
    assert backend._client.kwargs["api_key"] == "ollama"


def test_settings_connection_button_disables_and_recovers(monkeypatch):
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from desktop.widgets.settings_page import SettingsPage
    app = QApplication.instance() or QApplication([])
    page = SettingsPage(); started = []
    monkeypatch.setattr(page.pool, "start", lambda worker: started.append(worker))
    page.test(); assert not page.test_button.isEnabled(); assert len(started) == 1
    page.test(); assert len(started) == 1
    started[0].signals.finished.emit("连接成功"); assert page.test_button.isEnabled()
    page.test(); started[0].signals.error.emit("request failed: [REDACTED]"); assert page.test_button.isEnabled()
    page.deleteLater(); app.processEvents()


def test_provider_switch_loads_only_provider_scoped_key(monkeypatch):
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from desktop.widgets.settings_page import SettingsPage
    app = QApplication.instance() or QApplication([])
    page = SettingsPage(); page.store = CredentialStore(FakeKeyring()); page.store.save_secure("deepseek", "deep-key"); page.store.save_secure("openai", "openai-key")
    page.provider.setCurrentText("mock")
    page.provider.setCurrentText("openai"); assert page.api_key.text() == "openai-key"
    page.provider.setCurrentText("openai-compatible"); assert page.api_key.text() == ""
    page.provider.setCurrentText("deepseek"); assert page.api_key.text() == "deep-key"
    page.deleteLater(); app.processEvents()


def test_openai_compatible_allows_empty_key_with_custom_endpoint(monkeypatch):
    class FakeClient:
        def __init__(self, **kwargs): self.kwargs = kwargs
    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=FakeClient))
    backend = build_backend(RuntimeLLMConfig("openai-compatible", "", "https://custom/v1", "custom-model", 8))
    assert backend._client.kwargs["base_url"] == "https://custom/v1"
    assert backend._model == "custom-model"


def test_ai_assistant_does_not_block_optional_compatible_key(monkeypatch):
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from desktop.widgets.ai_assistant import AIAssistantPage
    app = QApplication.instance() or QApplication([])
    page = AIAssistantPage(lambda: RuntimeLLMConfig("openai-compatible", "", "https://custom/v1", "model", 5))
    monkeypatch.setattr(page.pool, "start", lambda worker: None)
    page.question.setPlainText("hello"); page.ask()
    assert page.status.text() == "处理中…"
    page.deleteLater(); app.processEvents()


def test_single_analysis_page_uses_existing_core_and_scoring(monkeypatch):
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from desktop.widgets.single_analysis import SingleAnalysisPage
    app = QApplication.instance() or QApplication([])
    page = SingleAnalysisPage()
    page.sequence.setPlainText("A" * 120)
    page.analyze()
    assert page.length.text() == "120"
    assert page.score.text() != "-"
    page.sequence.setPlainText("not-a-sequence")
    page.analyze()
    assert page.score.text() == "-"
    page.deleteLater(); app.processEvents()


def test_ai_assistant_rejects_missing_remote_key():
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from desktop.widgets.ai_assistant import AIAssistantPage
    app = QApplication.instance() or QApplication([])
    page = AIAssistantPage(lambda: RuntimeLLMConfig(provider="deepseek"))
    page.question.setPlainText("hello")
    page.ask()
    assert "API key" in page.status.text()
    page.deleteLater(); app.processEvents()


def test_main_window_headless_navigation():
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from desktop.main_window import MainWindow
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    assert window.nav.count() == window.stack.count() == 6
    from desktop.widgets.literature import LiteraturePage
    assert isinstance(window.stack.widget(3), LiteraturePage)
    for row in (0, 4, 5): window.nav.setCurrentRow(row); assert window.stack.currentIndex() == row
    window.deleteLater(); app.processEvents()


def test_mock_connection_backend_is_available():
    assert build_backend(RuntimeLLMConfig(provider="mock")).complete("x")


def test_deepseek_only_adds_non_thinking_request_option(monkeypatch):
    class FakeCompletions:
        def __init__(self): self.kwargs = None
        def create(self, **kwargs):
            self.kwargs = kwargs
            return types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(tool_calls=[], content="ok"))])
    class FakeClient:
        last = None
        def __init__(self, **kwargs):
            self.kwargs = kwargs; self.chat = types.SimpleNamespace(completions=FakeCompletions()); FakeClient.last = self
    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=FakeClient))
    from agent.llm import DeepSeekLLM, OpenAILLM
    deepseek = DeepSeekLLM(api_key="key", model="m")
    deepseek.plan("hello", [])
    assert deepseek._client.chat.completions.kwargs["extra_body"] == {"thinking": {"type": "disabled"}}
    openai = OpenAILLM(api_key="key", model="m")
    openai.plan("hello", [])
    assert "extra_body" not in openai._client.chat.completions.kwargs


def test_mock_agent_tool_loop_completes_without_reasoning_replay():
    from agent.agent import Agent
    from agent.llm import ReActStep, ToolCall
    from agent.tools import Tool, ToolRegistry
    class ToolBackend:
        def __init__(self): self.calls = 0
        def plan(self, question, tools): return [ToolCall("echo", {"value": "ok"})]
        def step(self, question, observations, tools):
            self.calls += 1
            return ReActStep(tool_call=ToolCall("echo", {"value": "ok"})) if not observations else ReActStep(final_answer="done")
        def answer(self, question, observations): return "done"
    registry = ToolRegistry().register(Tool("echo", "echo", lambda value: value, [{"name": "value", "required": True}]))
    result = Agent(backend=ToolBackend(), tools=registry).ask("use tool")
    assert result == "done"
