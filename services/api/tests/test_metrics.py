"""Tests for inference metrics endpoint."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from tests.helpers import make_user, sign_in

from src.models.metrics import MetricsSample


@pytest.mark.asyncio
async def test_metrics_requires_sign_in(client: AsyncClient):
    """Inference metrics are not public."""
    assert (await client.get("/api/metrics/inference")).status_code == 401


@pytest.mark.asyncio
async def test_metrics_empty_returns_zeros(client: AsyncClient, db_session: AsyncSession):
    """Metrics endpoint returns zeros when no data exists."""
    sign_in(client, await make_user(db_session, []))
    resp = await client.get("/api/metrics/inference")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_calls"] == 0
    assert body["total_tokens_in"] == 0
    assert body["total_tokens_out"] == 0
    assert body["avg_latency_ms"] is None


@pytest.mark.asyncio
async def test_metrics_with_samples(client: AsyncClient, db_session: AsyncSession):
    """Metrics endpoint aggregates inserted samples correctly."""
    sample1 = MetricsSample(
        model="mock-llm",
        endpoint="chat",
        tokens_in=100,
        tokens_out=50,
        latency_ms=200,
    )
    sample2 = MetricsSample(
        model="mock-vlm",
        endpoint="vision",
        tokens_in=200,
        tokens_out=80,
        latency_ms=400,
    )
    db_session.add_all([sample1, sample2])
    await db_session.commit()

    sign_in(client, await make_user(db_session, []))
    resp = await client.get("/api/metrics/inference")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_calls"] == 2
    assert body["total_tokens_in"] == 300
    assert body["total_tokens_out"] == 130
    assert body["avg_latency_ms"] == 300.0
    assert body["min_latency_ms"] == 200
    assert body["max_latency_ms"] == 400
