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


from desktop.providers import PROVIDERS, resolve_model

DEFAULTS = {spec.id: (spec.default_base_url or "", spec.models[0].model_id if spec.models else "")
            for spec in PROVIDERS}


def config_from_environment() -> RuntimeLLMConfig:
    """Resolve existing environment settings without mutating os.environ."""
    from desktop.providers import resolve_config
    return resolve_config(RuntimeLLMConfig(provider=""))


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
        return RuntimeLLMConfig(provider, "", base_url, resolve_model(provider, model), timeout)
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
    from desktop.providers import resolve_config

    config = resolve_config(config)
    provider = (config.provider or "mock").lower()
    kwargs = {"model": config.model, "timeout": config.timeout}
    if config.api_key:
        kwargs["api_key"] = config.api_key
    if config.base_url:
        kwargs["base_url"] = config.base_url
    if provider == "openai-compatible":
        if not config.api_key:
            kwargs["api_key"] = "not-needed"
        provider = "openai"
    if provider == "mock":
        return get_llm("mock")
    if provider == "ollama":
        return get_llm("ollama", **{k: v for k, v in kwargs.items() if k != "api_key"})
    if provider in {"deepseek", "openai"}:
        return get_llm(provider, **kwargs)
    raise ValueError(f"未知 provider: {config.provider}")
