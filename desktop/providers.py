"""Small immutable provider/model registry for the Desktop runtime layer."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping, Optional, Tuple


@dataclass(frozen=True)
class ModelSpec:
    display_name: str
    model_id: str
    legacy_aliases: Tuple[str, ...] = ()


@dataclass(frozen=True)
class ProviderSpec:
    id: str
    display_name: str
    default_base_url: Optional[str]
    requires_api_key: bool
    supports_tools: bool
    supports_custom_model: bool
    thinking_policy: str
    models: Tuple[ModelSpec, ...] = ()


PROVIDERS: Tuple[ProviderSpec, ...] = (
    ProviderSpec("deepseek", "DeepSeek", "https://api.deepseek.com", True, True, True, "disabled",
                 (ModelSpec("DeepSeek V4.1 Flash", "deepseek-flash", ("Deepseek-V4.1-Flash", "DeepSeek-V4.1-Flash", "DeepSeek V4.1 Flash", "Deepseek V4.1 Flash")),
                  ModelSpec("DeepSeek V4 Pro", "deepseek-v4-pro"),)),
    ProviderSpec("openai", "OpenAI", "https://api.openai.com/v1", True, True, True, "provider-native",
                 (ModelSpec("GPT-4o mini", "gpt-4o-mini"),)),
    ProviderSpec("openai-compatible", "OpenAI-compatible", None, False, True, True, "none"),
    ProviderSpec("ollama", "Ollama", "http://localhost:11434/v1", False, True, True, "none",
                 (ModelSpec("Qwen 2.5 7B", "qwen2.5:7b"),)),
    ProviderSpec("mock", "Mock", None, False, False, False, "none"),
)

_BY_ID = {spec.id: spec for spec in PROVIDERS}


def provider_spec(provider: str) -> ProviderSpec:
    key = (provider or "mock").strip().lower()
    try:
        return _BY_ID[key]
    except KeyError as exc:
        raise ValueError(f"未知 provider: {provider}") from exc


def resolve_model(provider: str, value: str = "") -> str:
    """Resolve a known display name, known ID, or preserve a custom ID literally."""
    spec = provider_spec(provider)
    value = (value or "").strip()
    if not value:
        return spec.models[0].model_id if spec.models else ""
    for model in spec.models:
        if value == model.display_name or value == model.model_id or value in model.legacy_aliases:
            return model.model_id
    if not spec.supports_custom_model:
        return spec.models[0].model_id if spec.models else ""
    return value


def model_display_name(provider: str, value: str = "") -> str:
    resolved = resolve_model(provider, value)
    for model in provider_spec(provider).models:
        if resolved == model.model_id:
            return model.display_name
    return (value or "").strip()


def _nonempty(value):
    return value.strip() if isinstance(value, str) and value.strip() else ""


def resolve_config(config, environ: Optional[Mapping[str, str]] = None):
    """Resolve runtime values deterministically without mutating environment state."""
    from desktop.settings import RuntimeLLMConfig

    env = environ if environ is not None else os.environ
    raw_provider = _nonempty(getattr(config, "provider", "")) if config is not None else ""
    provider = raw_provider.lower() or _nonempty(env.get("ANTIBODY_AI_PROVIDER", "")).lower() or "mock"
    spec = provider_spec(provider)
    base_env = "ANTIBODY_AI_BASE_URL"
    model_env = "ANTIBODY_AI_MODEL"
    key_env = {"deepseek": "DEEPSEEK_API_KEY", "openai": "OPENAI_API_KEY", "ollama": "OLLAMA_API_KEY"}.get(provider, "ANTIBODY_AI_API_KEY")
    base_url = _nonempty(getattr(config, "base_url", "")) if config is not None else ""
    model_value = _nonempty(getattr(config, "model", "")) if config is not None else ""
    api_key = _nonempty(getattr(config, "api_key", "")) if config is not None else ""
    base_url = base_url or _nonempty(env.get(base_env, "")) or (spec.default_base_url or "")
    model_value = model_value or _nonempty(env.get(model_env, ""))
    if not model_value and provider == "ollama": model_value = _nonempty(env.get("OLLAMA_MODEL", ""))
    model = resolve_model(provider, model_value)
    if not api_key: api_key = _nonempty(env.get(key_env, ""))
    timeout = getattr(config, "timeout", None) if config is not None else None
    if timeout is None or timeout == 30.0:
        timeout = env.get("ANTIBODY_AI_TIMEOUT", 30.0)
    try: timeout = float(timeout)
    except (TypeError, ValueError, OverflowError): timeout = 0.0
    if not 1 <= timeout <= 300:
        try: timeout = float(env.get("ANTIBODY_AI_TIMEOUT", 30.0))
        except (TypeError, ValueError, OverflowError): timeout = 30.0
        if not 1 <= timeout <= 300: timeout = 30.0
    return RuntimeLLMConfig(provider, api_key, base_url, model, timeout)


def all_provider_ids():
    return tuple(spec.id for spec in PROVIDERS)
