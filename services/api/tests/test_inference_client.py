"""Tests for inference client."""

import httpx
import pytest

from src.inference.client import InferenceClient


@pytest.mark.asyncio
async def test_inference_client_chat_success():
    fake_response = {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "Hello!"},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 12, "completion_tokens": 5, "total_tokens": 17},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=fake_response)

    transport = httpx.MockTransport(handler)
    client = InferenceClient()
    client._llm_client = httpx.AsyncClient(transport=transport, base_url="http://mock-llm:8080/v1")

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
    fake_response = {
        "id": "chatcmpl-vision",
        "object": "chat.completion",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "A pizza image."},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 50, "completion_tokens": 10, "total_tokens": 60},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=fake_response)

    transport = httpx.MockTransport(handler)
    client = InferenceClient()
    client._vlm_client = httpx.AsyncClient(transport=transport, base_url="http://mock-vlm:8080/v1")

    try:
        body, metrics = await client.vision([{"role": "user", "content": "describe"}])
        assert body["choices"][0]["message"]["content"] == "A pizza image."
        assert metrics["tokens_in"] == 50
        assert metrics["tokens_out"] == 10
        assert metrics["endpoint"] == "vision"
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_inference_client_error_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "inference failure"})

    transport = httpx.MockTransport(handler)
    client = InferenceClient()
    client._llm_client = httpx.AsyncClient(transport=transport, base_url="http://mock-llm:8080/v1")

    try:
        with pytest.raises(httpx.HTTPStatusError):
            await client.chat([{"role": "user", "content": "fail"}])
    finally:
        await client.close()
