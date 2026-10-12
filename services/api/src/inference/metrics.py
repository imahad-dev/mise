"""Record inference metrics to DB — call AFTER commit."""

from sqlalchemy.ext.asyncio import AsyncSession

from src.models.metrics import MetricsSample


async def record_metrics(db: AsyncSession, metrics: dict) -> None:
    """Insert a metrics_sample row. Must be called after the main transaction commits."""
    sample = MetricsSample(
        model=metrics["model"],
        endpoint=metrics["endpoint"],
        tokens_in=metrics["tokens_in"],
        tokens_out=metrics["tokens_out"],
        latency_ms=metrics["latency_ms"],
        gpu_seconds=metrics.get("gpu_seconds"),
        cached_prefix_tokens=metrics.get("cached_prefix_tokens"),
    )
    db.add(sample)
    await db.commit()
