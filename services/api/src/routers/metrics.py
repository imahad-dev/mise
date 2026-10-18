"""Inference metrics endpoint — cost tracking and daily budget."""

import contextlib
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.models.metrics import MetricsSample
from src.schemas.metrics import InferenceMetricsResponse

router = APIRouter(prefix="/api/metrics", tags=["metrics"])


@router.get("/inference", response_model=InferenceMetricsResponse)
async def inference_metrics(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> InferenceMetricsResponse:
    """Aggregated inference metrics with AMD-metered cost tracking.

    - cost_usd comes from usage.cost in the AMD response
    - daily_budget_remaining_usd from the most recent rate-limit header
    """
    result = await db.execute(
        select(
            func.count(MetricsSample.id).label("total_calls"),
            func.sum(MetricsSample.tokens_in).label("total_tokens_in"),
            func.sum(MetricsSample.tokens_out).label("total_tokens_out"),
            func.avg(MetricsSample.latency_ms).label("avg_latency_ms"),
            func.min(MetricsSample.latency_ms).label("min_latency_ms"),
            func.max(MetricsSample.latency_ms).label("max_latency_ms"),
            func.sum(MetricsSample.cost_usd).label("total_cost_usd"),
        )
    )
    row = result.one()

    # Get the most recent daily budget remaining from rate_limit_info JSONB
    latest_budget_row = await db.execute(
        select(MetricsSample.rate_limit_info)
        .where(MetricsSample.rate_limit_info.isnot(None))
        .order_by(MetricsSample.created_at.desc())
        .limit(1)
    )
    latest_budget = latest_budget_row.scalar_one_or_none()
    daily_budget_remaining: float | None = None
    if latest_budget and isinstance(latest_budget, dict):
        raw = latest_budget.get("remaining_daily_usd")
        if raw is not None:
            with contextlib.suppress(ValueError, TypeError):
                daily_budget_remaining = float(raw)

    return InferenceMetricsResponse(
        total_calls=row.total_calls or 0,
        total_tokens_in=row.total_tokens_in or 0,
        total_tokens_out=row.total_tokens_out or 0,
        avg_latency_ms=round(row.avg_latency_ms, 1) if row.avg_latency_ms is not None else None,
        min_latency_ms=row.min_latency_ms,
        max_latency_ms=row.max_latency_ms,
        total_cost_usd=round(row.total_cost_usd, 6) if row.total_cost_usd else None,
        daily_budget_remaining_usd=daily_budget_remaining,
    )
