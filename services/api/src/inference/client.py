"""Inference client — wraps httpx calls to any OpenAI-compatible endpoint.

Hardened for AMD Token Factory:
- Auth header injection (Bearer token from LLM_API_KEY)
- Startup model probe (GET /models)
- Model fallback chain
- Supported-params-only filtering
- System message enforcement (exactly one, first position, role='system')
- Response validation with Pydantic + regex fallback
- Retry on validation failure (once)
- Rate limiting (global RPM + per-guest session)
- Privacy: API key never logged, never in error payloads
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

import httpx

from src.config import settings
from src.inference.rate_limit import check_global_rate_limit
from src.inference.validation import validate_response

if TYPE_CHECKING:
    from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Parameters the AMD Token Factory API actually accepts
_SUPPORTED_PARAMS = frozenset({
    "model", "messages", "max_tokens", "temperature", "top_p",
    "stream", "tools", "tool_choice", "response_format",
    "reasoning_effort", "stream_options",
})


def _build_headers() -> dict[str, str]:
    """Build auth headers. Key is NEVER logged."""
    headers: dict[str, str] = {}
    if settings.llm_api_key:
        headers["Authorization"] = f"Bearer {settings.llm_api_key}"
    return headers


def _sanitize_error(exc: httpx.HTTPStatusError) -> httpx.HTTPStatusError:
    """Strip Authorization header from error response to prevent key leakage."""
    if exc.request and exc.request.headers.get("Authorization"):
        exc.request.headers["Authorization"] = "Bearer [REDACTED]"
    return exc


def _enforce_system_message(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Ensure exactly one system message at position 0.

    Rules:
    - If no system message: prepend a default one
    - If system message exists but not first: move it to position 0
    - Replace any 'developer' role with 'system'
    - If multiple system messages: keep only the first
    """
    cleaned: list[dict[str, Any]] = []
    system_msg: dict[str, Any] | None = None

    for msg in messages:
        role = msg.get("role", "")
        if role in ("system", "developer"):
            if system_msg is None:
                system_msg = {**msg, "role": "system"}
            # Skip duplicates
        else:
            cleaned.append(msg)

    if system_msg is None:
        system_msg = {"role": "system", "content": "You are a helpful restaurant assistant."}

    return [system_msg, *cleaned]


def _filter_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Keep only AMD-supported parameters."""
    filtered = {k: v for k, v in payload.items() if k in _SUPPORTED_PARAMS}

    # response_format: only json_object is supported (never json_schema)
    rf = filtered.get("response_format")
    if isinstance(rf, dict) and rf.get("type") == "json_schema":
        filtered["response_format"] = {"type": "json_object"}

    return filtered


class InferenceClient:
    """Async client for LLM/VLM inference via OpenAI-compatible API."""

    def __init__(
        self,
        llm_client: httpx.AsyncClient | None = None,
        vlm_client: httpx.AsyncClient | None = None,
    ) -> None:
        headers = _build_headers()
        self._llm_client = llm_client or httpx.AsyncClient(
            base_url=settings.llm_base_url,
            timeout=settings.llm_timeout_seconds,
            headers=headers,
        )
        self._vlm_client = vlm_client or httpx.AsyncClient(
            base_url=settings.vlm_base_url,
            timeout=settings.llm_timeout_seconds,
            headers=headers,
        )
        self._available_models: set[str] = set()

    async def probe_models(self) -> set[str]:
        """GET /models at startup; log availability; populate fallback info."""
        available: set[str] = set()
        for label, client in [("LLM", self._llm_client), ("VLM", self._vlm_client)]:
            try:
                resp = await client.get("/models")
                resp.raise_for_status()
                data = resp.json().get("data", [])
                ids = {m["id"] for m in data if "id" in m}
                available.update(ids)
                logger.info("[%s] Available models: %s", label, sorted(ids))
            except Exception:
                logger.warning("[%s] Model probe failed — will use mock defaults", label)

        self._available_models = available

        # Check configured models
        for model_name, fallbacks in [
            (settings.llm_model, settings.llm_model_fallbacks),
            (settings.vlm_model, settings.vlm_model_fallbacks),
        ]:
            if model_name not in available and available:
                for fb in fallbacks:
                    if fb in available:
                        logger.warning(
                            "Configured model %r not found; falling back to %r",
                            model_name, fb,
                        )
                        break
                else:
                    logger.warning(
                        "Configured model %r not found; no fallback available either",
                        model_name,
                    )

        return available

    def _resolve_model(self, model: str, fallbacks: list[str]) -> str:
        """Return model if available, otherwise first available fallback."""
        if not self._available_models or model in self._available_models:
            return model
        for fb in fallbacks:
            if fb in self._available_models:
                return fb
        return model  # use configured even if not probed (mock mode)

    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str | None = None,
        max_tokens: int | None = None,
        response_format: dict[str, Any] | None = None,
        temperature: float | None = None,
        schema: type[BaseModel] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Send a chat completion request. Returns (parsed_or_body, metrics).

        If `schema` is provided, validates the response with Pydantic.
        Retries once on validation failure.
        """
        await check_global_rate_limit()

        resolved_model = self._resolve_model(
            model or settings.llm_model,
            settings.llm_model_fallbacks,
        )
        max_tokens = max_tokens or settings.llm_max_tokens

        safe_messages = _enforce_system_message(messages)

        payload: dict[str, Any] = {
            "model": resolved_model,
            "messages": safe_messages,
            "max_tokens": max_tokens,
        }
        if response_format:
            payload["response_format"] = response_format
        if temperature is not None:
            payload["temperature"] = temperature

        payload = _filter_payload(payload)

        body, metrics = await self._post_chat(self._llm_client, payload, resolved_model)

        # Validate if schema provided; retry once on failure
        if schema is not None:
            result = validate_response(body, schema)
            if isinstance(result, dict) and "_validation_error" in result:
                logger.info("Retrying chat call after validation failure")
                body, retry_metrics = await self._post_chat(
                    self._llm_client, payload, resolved_model,
                )
                metrics["tokens_in"] += retry_metrics["tokens_in"]
                metrics["tokens_out"] += retry_metrics["tokens_out"]
                metrics["latency_ms"] += retry_metrics["latency_ms"]
                result = validate_response(body, schema)
            return (
                result.model_dump() if hasattr(result, "model_dump") else result,
                metrics,
            )

        return body, metrics

    async def vision(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str | None = None,
        max_tokens: int | None = None,
        schema: type[BaseModel] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Send a vision request with image parts. Returns (parsed_or_body, metrics)."""
        await check_global_rate_limit()

        resolved_model = self._resolve_model(
            model or settings.vlm_model,
            settings.vlm_model_fallbacks,
        )
        max_tokens = max_tokens or settings.llm_max_tokens

        safe_messages = _enforce_system_message(messages)

        payload = _filter_payload({
            "model": resolved_model,
            "messages": safe_messages,
            "max_tokens": max_tokens,
        })

        body, metrics = await self._post_chat(self._vlm_client, payload, resolved_model)
        metrics["endpoint"] = "vision"

        if schema is not None:
            result = validate_response(body, schema)
            if isinstance(result, dict) and "_validation_error" in result:
                body, retry_metrics = await self._post_chat(
                    self._vlm_client, payload, resolved_model,
                )
                metrics["tokens_in"] += retry_metrics["tokens_in"]
                metrics["tokens_out"] += retry_metrics["tokens_out"]
                metrics["latency_ms"] += retry_metrics["latency_ms"]
                result = validate_response(body, schema)
            return (
                result.model_dump() if hasattr(result, "model_dump") else result,
                metrics,
            )

        return body, metrics

    async def _post_chat(
        self,
        client: httpx.AsyncClient,
        payload: dict[str, Any],
        model: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Low-level POST to /chat/completions with timing + usage extraction."""
        start = time.monotonic()
        try:
            resp = await client.post("/chat/completions", json=payload)
            latency_ms = int((time.monotonic() - start) * 1000)
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise _sanitize_error(exc) from None

        body = resp.json()
        usage = body.get("usage", {})
        metrics = {
            "model": model,
            "endpoint": "chat",
            "tokens_in": usage.get("prompt_tokens", 0),
            "tokens_out": usage.get("completion_tokens", 0),
            "latency_ms": latency_ms,
            "cached_prefix_tokens": usage.get("prompt_tokens_details", {}).get(
                "cached_tokens", None
            ),
        }

        return body, metrics

    async def close(self) -> None:
        await self._llm_client.aclose()
        await self._vlm_client.aclose()


def get_inference_client(request: "Request") -> InferenceClient:
    """Dependency to retrieve InferenceClient instance from app state."""
    return request.app.state.inference_client
