"""Inference metrics schemas."""

from pydantic import BaseModel


class InferenceMetricsResponse(BaseModel):
    total_calls: int
    total_tokens_in: int
    total_tokens_out: int
    avg_latency_ms: float | None = None
    min_latency_ms: int | None = None
    max_latency_ms: int | None = None
    total_cost_usd: float | None = None
    daily_budget_remaining_usd: float | None = None
    provider_label: str = "OpenAI-compatible endpoint"
