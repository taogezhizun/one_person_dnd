from __future__ import annotations

from dataclasses import dataclass, replace

from one_person_dnd.config import LLMConfig


@dataclass(frozen=True)
class ProviderPreset:
    id: str
    label: str
    provider: str
    base_url: str
    default_model: str
    allows_empty_api_key: bool = True
    help_text: str = ""


_PRESETS: tuple[ProviderPreset, ...] = (
    ProviderPreset(
        id="openai_compat",
        label="OpenAI-compatible custom",
        provider="openai_compat",
        base_url="",
        default_model="",
        allows_empty_api_key=True,
        help_text="Use any server that exposes /v1/chat/completions.",
    ),
    ProviderPreset(
        id="deepseek",
        label="DeepSeek",
        provider="deepseek",
        base_url="https://api.deepseek.com/v1",
        default_model="deepseek-chat",
        allows_empty_api_key=False,
        help_text="DeepSeek uses an OpenAI-compatible chat completions API.",
    ),
)


def list_provider_presets() -> list[ProviderPreset]:
    return list(_PRESETS)


def get_provider_preset(provider_id: str) -> ProviderPreset:
    normalized = (provider_id or "openai_compat").strip().lower()
    aliases = {
        "openai": "openai_compat",
        "openai-compatible": "openai_compat",
        "openai_compatible": "openai_compat",
    }
    normalized = aliases.get(normalized, normalized)
    for preset in _PRESETS:
        if preset.id == normalized or preset.provider == normalized:
            return preset
    return _PRESETS[0]


def apply_provider_defaults(cfg: LLMConfig) -> LLMConfig:
    preset = get_provider_preset(cfg.provider)
    base_url = (cfg.base_url or "").strip() or preset.base_url
    model = (cfg.model or "").strip() or preset.default_model
    provider = (cfg.provider or preset.provider).strip() or preset.provider
    return replace(cfg, provider=provider, base_url=base_url, model=model)


def transport_provider(provider: str) -> str:
    preset = get_provider_preset(provider)
    if preset.id == "deepseek":
        return "openai_compat"
    return preset.provider
