"""Test that get_inference_client dependency resolves correctly via FastAPI."""

import json

import httpx
import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from src.inference.client import InferenceClient, get_inference_client


def _build_app() -> FastAPI:
    app = FastAPI()

    @app.get("/probe")
    async def probe_route(
        inference: InferenceClient = Depends(get_inference_client),
    ):
        return {"has_client": inference is not None}

    return app


@pytest.fixture
def mock_inference_app():
    """FastAPI app with a mock InferenceClient attached to state.

    httpx ASGITransport does not run startup events, so state is set directly.
    """
    app = _build_app()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": json.dumps({"reply": "test"})}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            },
        )

    mock_client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://mock:8080/v1",
    )
    app.state.inference_client = InferenceClient(llm_client=mock_client, vlm_client=mock_client)
    return app


@pytest.mark.asyncio
async def test_get_inference_client_resolves(mock_inference_app):
    """The get_inference_client dependency resolves without error and returns the client."""
    transport = ASGITransport(app=mock_inference_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/probe")
    assert resp.status_code == 200
    assert resp.json() == {"has_client": True}


@pytest.mark.asyncio
async def test_get_inference_client_missing_returns_503():
    """Without a client on app.state the dependency returns 503 ai_unavailable."""
    transport = ASGITransport(app=_build_app())
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/probe")
    assert resp.status_code == 503
    assert resp.json() == {"detail": {"error": "ai_unavailable"}}
