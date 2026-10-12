"""Inference client — wraps httpx calls to any OpenAI-compatible endpoint."""

from __future__ import annotations

import time
from typing import Any

import httpx

from src.config import settings


class InferenceClient:
    """Async client for LLM/VLM inference via OpenAI-compatible API."""

    def __init__(self) -> None:
        self._llm_client = httpx.AsyncClient(
            base_url=settings.llm_base_url,
            timeout=settings.llm_timeout_seconds,
        )
        self._vlm_client = httpx.AsyncClient(
            base_url=settings.vlm_base_url,
            timeout=settings.llm_timeout_seconds,
        )

    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str | None = None,
        max_tokens: int | None = None,
        response_format: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Send a chat completion request. Returns (response_body, metrics)."""
        model = model or settings.llm_model
        max_tokens = max_tokens or settings.llm_max_tokens

        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
        }
        if response_format:
            payload["response_format"] = response_format

        start = time.monotonic()
        resp = await self._llm_client.post("/chat/completions", json=payload)
        latency_ms = int((time.monotonic() - start) * 1000)
        resp.raise_for_status()
        body = resp.json()

        usage = body.get("usage", {})
        metrics = {
            "model": model,
            "endpoint": "chat",
            "tokens_in": usage.get("prompt_tokens", 0),
            "tokens_out": usage.get("completion_tokens", 0),
            "latency_ms": latency_ms,
        }

        return body, metrics

    async def vision(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str | None = None,
        max_tokens: int | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Send a vision request with image parts. Returns (response_body, metrics)."""
        model = model or settings.vlm_model
        max_tokens = max_tokens or settings.llm_max_tokens

        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
        }

        start = time.monotonic()
        resp = await self._vlm_client.post("/chat/completions", json=payload)
        latency_ms = int((time.monotonic() - start) * 1000)
        resp.raise_for_status()
        body = resp.json()

        usage = body.get("usage", {})
        metrics = {
            "model": model,
            "endpoint": "vision",
            "tokens_in": usage.get("prompt_tokens", 0),
            "tokens_out": usage.get("completion_tokens", 0),
            "latency_ms": latency_ms,
        }

        return body, metrics

    async def close(self) -> None:
        await self._llm_client.aclose()
        await self._vlm_client.aclose()


inference_client = InferenceClient()
