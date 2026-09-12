from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict


@dataclass
class RuntimeLLMConfig:
    provider: str = "mock"
    api_key: str = field(default="", repr=False)
    base_url: str = ""
    model: str = ""
    timeout: float = 30.0


DEFAULTS = {"deepseek": ("https://api.deepseek.com", "deepseek-chat"),
            "openai": ("https://api.openai.com/v1", "gpt-4o-mini"),
            "openai-compatible": ("", ""), "ollama": ("http://localhost:11434/v1", "qwen2.5:7b"),
            "mock": ("", "")}


def config_from_environment() -> RuntimeLLMConfig:
    """Resolve the existing environment configuration without mutating os.environ."""
    provider = os.environ.get("ANTIBODY_AI_PROVIDER", "").strip().lower()
    if not provider:
        provider = "deepseek" if os.environ.get("DEEPSEEK_API_KEY") else (
            "openai" if os.environ.get("OPENAI_API_KEY") else "mock")
    base_url, model = DEFAULTS.get(provider, ("", ""))
    return RuntimeLLMConfig(
        provider=provider,
        api_key=os.environ.get("DEEPSEEK_API_KEY" if provider == "deepseek" else "OPENAI_API_KEY", "")
        if provider in {"deepseek", "openai"} else "",
        base_url=os.environ.get("ANTIBODY_AI_BASE_URL", base_url),
        model=os.environ.get("ANTIBODY_AI_MODEL", model),
        timeout=float(os.environ.get("ANTIBODY_AI_TIMEOUT", "30")),
    )


def settings_path() -> Path:
    root = os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming")
    return Path(root) / "AntibodyAI" / "settings.json"


def load_settings(path: Path | None = None) -> RuntimeLLMConfig:
    path = path or settings_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return RuntimeLLMConfig()
        provider = data.get("provider", "mock")
        if not isinstance(provider, str) or provider not in DEFAULTS:
            provider = "mock"
        default_base, default_model = DEFAULTS[provider]
        base_url = data.get("base_url", default_base)
        model = data.get("model", default_model)
        timeout = data.get("timeout", 30.0)
        if not isinstance(base_url, str): base_url = default_base
        if not isinstance(model, str): model = default_model
        if isinstance(timeout, bool): timeout = 30.0
        try: timeout = float(timeout)
        except (TypeError, ValueError): timeout = 30.0
        if not 1 <= timeout <= 300: timeout = 30.0
        return RuntimeLLMConfig(provider, "", base_url, model, timeout)
    except (OSError, ValueError, TypeError, OverflowError):
        return RuntimeLLMConfig()


def save_settings(config: RuntimeLLMConfig, path: Path | None = None) -> Path:
    path = path or settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data: Dict[str, Any] = asdict(config)
    data.pop("api_key", None)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def build_backend(config: RuntimeLLMConfig):
    from agent.llm import get_llm

    provider = (config.provider or "mock").lower()
    if provider == "openai-compatible":
        provider = "openai"
    kwargs = {"model": config.model, "timeout": config.timeout}
    if config.api_key:
        kwargs["api_key"] = config.api_key
    if config.base_url:
        kwargs["base_url"] = config.base_url
    if provider == "mock":
        return get_llm("mock")
    if provider == "ollama":
        return get_llm("ollama", **{k: v for k, v in kwargs.items() if k != "api_key"})
    if provider in {"deepseek", "openai"}:
        return get_llm(provider, **kwargs)
    raise ValueError(f"未知 provider: {config.provider}")
