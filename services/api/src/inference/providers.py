"""Provider presets for OpenAI-compatible LLM endpoints."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderPreset:
    name: str
    base_url: str
    allowed_params: list[str]
    supports_response_format: bool
    default_rpm: int
    default_concurrency: int
    setup_note: str
    requires_free_suffix: bool = False
    is_local: bool = False


PRESETS: dict[str, ProviderPreset] = {
    "gemini": ProviderPreset(
        name="gemini",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        allowed_params=["model", "messages", "max_tokens", "temperature", "response_format"],
        supports_response_format=True,
        default_rpm=10,
        default_concurrency=4,
        setup_note=(
            "Get a free Gemini API key at Google AI Studio (aistudio.google.com). "
            "Free tier has generous RPM limits."
        ),
    ),
    "groq": ProviderPreset(
        name="groq",
        base_url="https://api.groq.com/openai/v1",
        allowed_params=["model", "messages", "max_tokens", "temperature", "response_format"],
        supports_response_format=True,
        default_rpm=20,
        default_concurrency=4,
        setup_note="Get a free Groq API key at console.groq.com. Fast inference on dedicated LPUs.",
    ),
    "openrouter": ProviderPreset(
        name="openrouter",
        base_url="https://openrouter.ai/api/v1",
        allowed_params=["model", "messages", "max_tokens", "temperature", "response_format"],
        supports_response_format=True,
        default_rpm=15,
        default_concurrency=4,
        setup_note=(
            "Get an API key at openrouter.ai. Model must end with ':free' under "
            "LLM_FREE_ONLY policy."
        ),
        requires_free_suffix=True,
    ),
    "ollama": ProviderPreset(
        name="ollama",
        base_url="http://localhost:11434/v1",
        allowed_params=["model", "messages", "max_tokens", "temperature", "response_format"],
        supports_response_format=True,
        default_rpm=0,  # no per-minute cap
        default_concurrency=2,
        setup_note=(
            "Run locally via 'ollama serve'. Pull models with 'ollama run <model>'. "
            "Completely private and local."
        ),
        is_local=True,
    ),
    "custom": ProviderPreset(
        name="custom",
        base_url="http://inference:8080/v1",
        allowed_params=["model", "messages", "max_tokens", "temperature", "response_format"],
        supports_response_format=True,
        default_rpm=15,
        default_concurrency=6,
        setup_note=(
            "Custom OpenAI-compatible endpoint. Base URL and limits configured via environment."
        ),
    ),
}


def get_preset(name: str) -> ProviderPreset:
    """Return preset configuration for the given preset name."""
    preset_key = name.lower().strip()
    return PRESETS.get(preset_key, PRESETS["custom"])
