"""Tests for inference client — isolated per-test clients with no shared loops."""

import json

import httpx
import pytest
from pydantic import BaseModel

from src.inference.client import (
    InferenceClient,
    _enforce_system_message,
    _filter_payload,
)


class MockChatResponse(BaseModel):
    """Schema for testing Pydantic validation."""

    reply: str
    confidence: float = 1.0


@pytest.fixture(autouse=True)
def mock_redis_for_client(monkeypatch):
    """Mock Redis client calls during unit tests of InferenceClient."""
    from src.redis_client import redis_client

    async def fake_incr(key):
        return 1

    async def fake_expire(key, ttl):
        return True

    async def fake_get(key):
        return None

    monkeypatch.setattr(redis_client, "incr", fake_incr)
    monkeypatch.setattr(redis_client, "expire", fake_expire)
    monkeypatch.setattr(redis_client, "get", fake_get)


def _make_fake_response(content: str | dict, model: str = "mock-llm") -> dict:
    """Build a fake OpenAI-style chat completion response."""
    if isinstance(content, dict):
        content = json.dumps(content)
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 12, "completion_tokens": 5, "total_tokens": 17},
    }


@pytest.mark.asyncio
async def test_inference_client_chat_success():
    fake_response = _make_fake_response("Hello!")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=fake_response)

    llm_mock = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://mock-llm:8080/v1"
    )
    client = InferenceClient(llm_client=llm_mock)

    try:
        body, metrics = await client.chat([{"role": "user", "content": "hi"}])
        assert body["choices"][0]["message"]["content"] == "Hello!"
        assert metrics["tokens_in"] == 12
        assert metrics["tokens_out"] == 5
        assert metrics["endpoint"] == "chat"
        assert metrics["latency_ms"] >= 0
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_inference_client_vision_success():
    fake_response = _make_fake_response("A pizza image.")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=fake_response)

    vlm_mock = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://mock-vlm:8080/v1"
    )
    client = InferenceClient(vlm_client=vlm_mock)

    try:
        body, metrics = await client.vision([{"role": "user", "content": "describe"}])
        assert body["choices"][0]["message"]["content"] == "A pizza image."
        assert metrics["tokens_in"] == 12
        assert metrics["tokens_out"] == 5
        assert metrics["endpoint"] == "vision"
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_inference_client_error_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "inference failure"})

    llm_mock = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://mock-llm:8080/v1"
    )
    client = InferenceClient(llm_client=llm_mock)

    try:
        with pytest.raises(httpx.HTTPStatusError):
            await client.chat([{"role": "user", "content": "fail"}])
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_inference_client_with_pydantic_validation():
    """Chat call with a Pydantic schema validates the structured response."""
    content = {"reply": "Try the pasta!", "confidence": 0.95}
    fake_response = _make_fake_response(content)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=fake_response)

    llm_mock = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://mock-llm:8080/v1"
    )
    client = InferenceClient(llm_client=llm_mock)

    try:
        result, _metrics = await client.chat(
            [{"role": "user", "content": "recommend"}],
            schema=MockChatResponse,
        )
        assert result["reply"] == "Try the pasta!"
        assert result["confidence"] == 0.95
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_inference_client_validation_fallback():
    """If JSON is embedded in text, regex fallback extracts it."""
    content = 'Here is the answer: {"reply": "Pizza!", "confidence": 0.8} Hope that helps.'
    fake_response = _make_fake_response(content)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=fake_response)

    llm_mock = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://mock-llm:8080/v1"
    )
    client = InferenceClient(llm_client=llm_mock)

    try:
        result, _metrics = await client.chat(
            [{"role": "user", "content": "chat recommend"}],
            schema=MockChatResponse,
        )
        assert result["reply"] == "Pizza!"
    finally:
        await client.close()


# --- Unit tests for helper functions ---


def test_enforce_system_message_adds_default():
    """If no system message present, a default is prepended."""
    msgs = [{"role": "user", "content": "hello"}]
    result = _enforce_system_message(msgs)
    assert len(result) == 2
    assert result[0]["role"] == "system"
    assert result[1]["role"] == "user"


def test_enforce_system_message_moves_to_front():
    """System message not at position 0 is moved there."""
    msgs = [
        {"role": "user", "content": "hello"},
        {"role": "system", "content": "You are a chef."},
    ]
    result = _enforce_system_message(msgs)
    assert result[0]["role"] == "system"
    assert result[0]["content"] == "You are a chef."
    assert len(result) == 2


def test_enforce_system_message_replaces_developer_role():
    """'developer' role is replaced with 'system'."""
    msgs = [
        {"role": "developer", "content": "Be a chef"},
        {"role": "user", "content": "hello"},
    ]
    result = _enforce_system_message(msgs)
    assert result[0]["role"] == "system"
    assert result[0]["content"] == "Be a chef"


def test_enforce_system_message_deduplicates():
    """Multiple system messages are deduplicated; only first kept."""
    msgs = [
        {"role": "system", "content": "First"},
        {"role": "system", "content": "Second"},
        {"role": "user", "content": "hello"},
    ]
    result = _enforce_system_message(msgs)
    assert len(result) == 2
    assert result[0]["content"] == "First"


def test_filter_payload_strips_unsupported_params():
    payload = {
        "model": "gpt-4",
        "messages": [],
        "max_tokens": 100,
        "unsupported_param": True,
        "foo": "bar",
    }
    result = _filter_payload(payload)
    assert "unsupported_param" not in result
    assert "foo" not in result
    assert result["model"] == "gpt-4"


def test_filter_payload_converts_json_schema_to_json_object():
    """json_schema response_format is downgraded to json_object."""
    payload = {
        "model": "test",
        "messages": [],
        "response_format": {"type": "json_schema", "schema": {}},
    }
    result = _filter_payload(payload)
    assert result["response_format"] == {"type": "json_object"}


def test_openrouter_free_model_guard():
    """Settings validation fails if OpenRouter model lacks :free when llm_free_only=True."""
    from pydantic import ValidationError

    from src.config import Settings

    with pytest.raises(ValidationError, match="LLM_FREE_ONLY guard"):
        Settings(
            llm_provider="openai_compatible",
            llm_preset="openrouter",
            llm_model="meta-llama/llama-3-8b",
            llm_free_only=True,
        )

    # Passes if ends with :free
    s = Settings(
        llm_provider="openai_compatible",
        llm_preset="openrouter",
        llm_model="meta-llama/llama-3-8b:free",
        llm_free_only=True,
    )
    assert s.llm_model.endswith(":free")


@pytest.mark.asyncio
async def test_daily_request_cap_guard(monkeypatch):
    """When daily request cap is exceeded, check_daily_request_cap raises 503 ai_unavailable."""
    from fastapi import HTTPException

    from src.config import settings
    from src.inference.rate_limit import check_daily_request_cap
    from src.redis_client import redis_client

    monkeypatch.setattr(settings, "llm_provider", "openai_compatible")
    monkeypatch.setattr(settings, "llm_preset", "groq")
    monkeypatch.setattr(settings, "llm_base_url", "https://api.groq.com/openai/v1")
    monkeypatch.setattr(settings, "llm_daily_request_cap", 2)

    async def fake_incr(key):
        return 3

    async def fake_expire(key, ttl):
        return True

    monkeypatch.setattr(redis_client, "incr", fake_incr)
    monkeypatch.setattr(redis_client, "expire", fake_expire)

    with pytest.raises(HTTPException) as exc_info:
        await check_daily_request_cap()
    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "ai_unavailable"


@pytest.mark.asyncio
async def test_provider_429_returns_503_ai_unavailable():
    """When provider persistently returns 429, inference client raises 503 ai_unavailable."""
    from fastapi import HTTPException

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": "0"})

    llm_mock = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://mock-llm:8080/v1"
    )
    client = InferenceClient(llm_client=llm_mock)

    try:
        with pytest.raises(HTTPException) as exc_info:
            await client.chat([{"role": "user", "content": "hello"}])
        assert exc_info.value.status_code == 503
        assert exc_info.value.detail == "ai_unavailable"
    finally:
        await client.close()
