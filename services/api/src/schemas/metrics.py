"""Inference metrics schemas."""

from pydantic import BaseModel


class InferenceMetricsResponse(BaseModel):
    total_calls: int
    total_tokens_in: int
    total_tokens_out: int
    avg_latency_ms: float | None = None
    min_latency_ms: int | None = None
    max_latency_ms: int | None = None
