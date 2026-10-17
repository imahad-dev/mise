"""Inference metrics endpoint."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.database import get_db
from src.models.metrics import MetricsSample
from src.schemas.metrics import InferenceMetricsResponse

router = APIRouter(prefix="/api/metrics", tags=["metrics"])


@router.get("/inference", response_model=InferenceMetricsResponse)
async def inference_metrics(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> InferenceMetricsResponse:
    """Aggregated inference metrics with GPU cost estimation.

    TODO: Require owner auth (mise_owner cookie) when M1.3 lands.
    """
    result = await db.execute(
        select(
            func.count(MetricsSample.id).label("total_calls"),
            func.sum(MetricsSample.tokens_in).label("total_tokens_in"),
            func.sum(MetricsSample.tokens_out).label("total_tokens_out"),
            func.avg(MetricsSample.latency_ms).label("avg_latency_ms"),
            func.min(MetricsSample.latency_ms).label("min_latency_ms"),
            func.max(MetricsSample.latency_ms).label("max_latency_ms"),
            func.sum(MetricsSample.gpu_seconds).label("total_gpu_seconds"),
        )
    )
    row = result.one()

    total_gpu = row.total_gpu_seconds or 0.0
    estimated_cost = (
        round(total_gpu * settings.gpu_hourly_rate_usd / 3600, 4)
        if settings.gpu_hourly_rate_usd > 0
        else None
    )

    return InferenceMetricsResponse(
        total_calls=row.total_calls or 0,
        total_tokens_in=row.total_tokens_in or 0,
        total_tokens_out=row.total_tokens_out or 0,
        avg_latency_ms=round(row.avg_latency_ms, 1) if row.avg_latency_ms is not None else None,
        min_latency_ms=row.min_latency_ms,
        max_latency_ms=row.max_latency_ms,
        total_gpu_seconds=round(total_gpu, 2) if total_gpu else None,
        estimated_cost_usd=estimated_cost,
    )
