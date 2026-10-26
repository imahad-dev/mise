"""Floor view and service-call schemas."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

from src.models.service_call import ServiceCall
from src.services.floor import reason_label

Reason = Literal["help", "water", "extra"]


class FloorTile(BaseModel):
    table_id: uuid.UUID
    label: str
    state: str
    level: str
    since: datetime | None
    reason: str | None
    reason_label: str | None
    running_total: Decimal | None
    bill_id: uuid.UUID | None
    call_id: uuid.UUID | None


class FloorResponse(BaseModel):
    tiles: list[FloorTile]
    counts: dict[str, int]
    thresholds: dict[str, list[int]]  # state -> [amber, red] in seconds
    server_time: datetime
    service_extra_label: str | None


class TableClearedResponse(BaseModel):
    table_id: uuid.UUID
    cleared_at: datetime


class ServiceCallRequest(BaseModel):
    reason: Reason


class ServiceCallResponse(BaseModel):
    id: uuid.UUID
    reason: str
    reason_label: str
    created_at: datetime
    resolved_at: datetime | None


class CurrentCallResponse(BaseModel):
    call: ServiceCallResponse | None
    available: bool  # the session sits at a normal table, so a waiter can be called
    extra_label: str | None
    server_time: datetime


def call_response(call: ServiceCall, extra_label: str | None) -> ServiceCallResponse:
    return ServiceCallResponse(
        id=call.id,
        reason=call.reason,
        reason_label=reason_label(call.reason, extra_label),
        created_at=call.created_at,
        resolved_at=call.resolved_at,
    )
