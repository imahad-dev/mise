"""Inference metrics endpoint."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.models.metrics import MetricsSample

router = APIRouter(prefix="/api/metrics", tags=["metrics"])


@router.get("/inference")
async def inference_metrics(db: Annotated[AsyncSession, Depends(get_db)]) -> dict:
    """Aggregated inference metrics. Owner auth enforced in M1."""
    result = await db.execute(
        select(
            func.count(MetricsSample.id).label("total_calls"),
            func.sum(MetricsSample.tokens_in).label("total_tokens_in"),
            func.sum(MetricsSample.tokens_out).label("total_tokens_out"),
            func.avg(MetricsSample.latency_ms).label("avg_latency_ms"),
            func.min(MetricsSample.latency_ms).label("min_latency_ms"),
            func.max(MetricsSample.latency_ms).label("max_latency_ms"),
        )
    )
    row = result.one()

    return {
        "total_calls": row.total_calls or 0,
        "total_tokens_in": row.total_tokens_in or 0,
        "total_tokens_out": row.total_tokens_out or 0,
        "avg_latency_ms": round(row.avg_latency_ms, 1) if row.avg_latency_ms else 0,
        "min_latency_ms": row.min_latency_ms or 0,
        "max_latency_ms": row.max_latency_ms or 0,
    }
