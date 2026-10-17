"""Privacy tests — API key must NEVER appear in logs, responses, or error payloads."""

import httpx
import pytest

from src.inference.client import InferenceClient, _build_headers, _sanitize_error


def test_build_headers_uses_bearer_format(monkeypatch):
    """_build_headers produces a Bearer token when LLM_API_KEY is set."""
    monkeypatch.setattr("src.inference.client.settings.llm_api_key", "sk-test-secret-key-123")
    headers = _build_headers()
    assert headers["Authorization"] == "Bearer sk-test-secret-key-123"


def test_build_headers_empty_when_no_key(monkeypatch):
    """_build_headers produces empty dict when LLM_API_KEY is blank."""
    monkeypatch.setattr("src.inference.client.settings.llm_api_key", "")
    headers = _build_headers()
    assert "Authorization" not in headers


def test_sanitize_error_redacts_auth_header():
    """Authorization header is redacted in error exceptions."""
    request = httpx.Request(
        "POST",
        "http://test/v1/chat/completions",
        headers={"Authorization": "Bearer sk-real-secret"},
    )
    response = httpx.Response(500, request=request, json={"error": "fail"})
    exc = httpx.HTTPStatusError("fail", request=request, response=response)

    sanitized = _sanitize_error(exc)
    assert "sk-real-secret" not in str(sanitized.request.headers.get("Authorization", ""))
    assert "REDACTED" in str(sanitized.request.headers.get("Authorization", ""))


@pytest.mark.asyncio
async def test_error_response_never_contains_api_key(monkeypatch):
    """When the LLM returns an error, the raised exception never contains the API key."""
    secret_key = "sk-super-secret-never-leak"
    monkeypatch.setattr("src.inference.client.settings.llm_api_key", secret_key)

    def error_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "server error"})

    llm_mock = httpx.AsyncClient(
        transport=httpx.MockTransport(error_handler),
        base_url="http://mock:8080/v1",
        headers={"Authorization": f"Bearer {secret_key}"},
    )
    client = InferenceClient(llm_client=llm_mock)

    try:
        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            await client.chat([{"role": "user", "content": "test"}])

        error_str = str(exc_info.value)
        request_str = str(exc_info.value.request.headers)
        assert secret_key not in error_str, "API key leaked in exception message"
        assert secret_key not in request_str, "API key leaked in request headers"
    finally:
        await client.close()


def test_config_strips_whitespace_from_api_key():
    """Settings._strip_api_key removes all whitespace from the key."""
    from src.config import Settings

    # field_validator runs during construction
    s = Settings(llm_api_key="  sk-test  key\n\twith  spaces  ")
    assert s.llm_api_key == "sk-testkeywithspaces"
    assert " " not in s.llm_api_key
    assert "\n" not in s.llm_api_key
    assert "\t" not in s.llm_api_key
