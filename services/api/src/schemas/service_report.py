"""Daily service report response. Durations are whole seconds; null when there is no data."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class StageWaits(BaseModel):
    first_order: int | None  # sitting opened -> first order placed
    approval: int | None  # first order placed -> approved
    kitchen: int | None  # kitchen saw the order (approval, else placement) -> bumped
    bill: int | None  # bill requested -> settled


class SlowestHour(BaseModel):
    hour: int  # local hour of opening, 0-23
    average_table_seconds: int
    slowest_stage: Literal["first_order", "approval", "kitchen", "bill"] | None


class RedAlerts(BaseModel):
    seated_no_order: int
    approval_needed: int
    order_no_bump: int
    bill_not_settled: int


class ServiceReportResponse(BaseModel):
    day: date
    tables_served: int
    closed_without_bill: int
    simulated_sittings: int = Field(
        description="Sittings with simulated orders; 0 until the simulator seats tables."
    )
    average_table_seconds: int | None
    average_wait_seconds: StageWaits
    busiest_hour: int | None
    slowest_hour: SlowestHour | None
    alerts: RedAlerts
    summary: str
    summary_source: Literal["llm", "template"]
