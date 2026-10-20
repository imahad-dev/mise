"""Owner schemas for menu items and table management."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class OwnerMenuTranslation(BaseModel):
    language: str
    name: str
    description: str | None = None

    model_config = ConfigDict(from_attributes=True)


class OwnerMenuItemResponse(BaseModel):
    id: uuid.UUID
    restaurant_id: uuid.UUID
    category: str
    price: Decimal
    unit_cost: Decimal
    ingredients: list[str]
    allergens: list[str]
    allergen_verified: bool
    dietary_verified: bool
    is_vegetarian: bool
    is_vegan: bool
    is_gluten_free: bool
    available: bool
    featured: bool
    sort_order: int
    image_url: str | None = None
    translations: list[OwnerMenuTranslation]
    deleted_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class PatchMenuItemRequest(BaseModel):
    price: Decimal | None = Field(default=None, ge=Decimal("0.00"), allow_inf_nan=False)
    unit_cost: Decimal | None = Field(default=None, ge=Decimal("0.00"), allow_inf_nan=False)
    available: bool | None = None
    featured: bool | None = None
    sort_order: int | None = None
    ingredients: list[str] | None = None
    allergens: list[str] | None = None
    is_vegetarian: bool | None = None
    is_vegan: bool | None = None
    is_gluten_free: bool | None = None


class OwnerTableResponse(BaseModel):
    id: uuid.UUID
    restaurant_id: uuid.UUID
    label: str
    qr_token: str
    guest_url: str

    model_config = ConfigDict(from_attributes=True)


class StatusOkResponse(BaseModel):
    status: Literal["ok"]


# --- Checkpoint D: AI schemas ---


class MenuIngestRequest(BaseModel):
    """Request to analyze a menu photo or text via AI."""

    image_url: str
    language: str = "it"


class AIMenuItemParsed(BaseModel):
    """Structured output expected from VLM menu analysis."""

    name: str
    description: str | None = None
    category: str = "other"
    price: float = 0.0
    unit_cost: float = 0.0
    ingredients: list[str] = []
    allergens: list[str] = []
    is_vegetarian: bool = False
    is_vegan: bool = False
    is_gluten_free: bool = False


class AIMenuIngestResult(BaseModel):
    """Top-level wrapper for VLM ingest response."""

    items: list[AIMenuItemParsed]


class MenuIngestResponse(BaseModel):
    """Response after AI menu ingest — created item IDs."""

    created_count: int
    items: list[OwnerMenuItemResponse]


# --- Analytics: brief, forecast, what-if, demo order simulation ---


class DataSources(BaseModel):
    live: int
    simulated: int


class Kpis(BaseModel):
    orders: int
    revenue_eur: float
    aov_eur: float
    contribution_margin_eur: float
    margin_pct: float


class MenuEngineeringItem(BaseModel):
    item_id: str
    name: str
    units: int
    weekly_units: float
    revenue_eur: float
    unit_margin_eur: float
    contribution_eur: float
    menu_class: Literal["star", "plowhorse", "puzzle", "dog"]


class MenuThresholds(BaseModel):
    median_units: float
    median_unit_margin_eur: float


class Pairing(BaseModel):
    a: str
    b: str
    a_name: str
    b_name: str
    orders_together: int
    lift: float


class PeakHour(BaseModel):
    hour: int
    avg_orders_per_day: float
    avg_revenue_per_day_eur: float


class BacktestMetric(BaseModel):
    method: str
    wape: float | None
    mae: float | None
    n_points: int


class ForecastPoint(BaseModel):
    date: str
    item_id: str
    name: str
    daypart: Literal["lunch", "dinner"]
    forecast: float
    lo: float
    hi: float


class ForecastSummary(BaseModel):
    run_id: uuid.UUID
    method: str | None
    model_name: str | None
    history_days: int
    low_confidence: bool
    backtest: list[BacktestMetric]
    points: list[ForecastPoint]


class BriefAction(BaseModel):
    rank: int
    type: Literal["promote_puzzle", "reprice_plowhorse", "review_dog", "prep_target"]
    item_id: str | None
    item: str
    title: str
    evidence: dict[str, float | int | str]
    estimated_impact_eur_per_week: float | None
    formula: str


class DailyBriefResponse(BaseModel):
    date: str
    window_start: str
    window_end: str
    data_sources: DataSources
    kpis: Kpis
    menu_engineering: list[MenuEngineeringItem]
    thresholds: MenuThresholds
    pairings: list[Pairing]
    peak_hours: list[PeakHour]
    forecast: ForecastSummary
    actions: list[BriefAction]
    summary: str
    summary_source: Literal["llm", "template"]


class WhatIfRequest(BaseModel):
    scenario: Literal["price_change", "promotion", "demand_surge"]
    item_id: uuid.UUID | None = None
    change_pct: float | None = Field(default=None, ge=-90, le=100)
    discount_pct: float | None = Field(default=None, gt=0, le=90)
    multiplier: float | None = Field(default=None, gt=0, le=5)
    elasticity: float | None = Field(default=None, ge=-10, le=0)


class WhatIfTotals(BaseModel):
    revenue_eur: float
    margin_eur: float


class WhatIfResponse(BaseModel):
    scenario: str
    item: str | None
    window_start: str
    window_end: str
    data_sources: DataSources
    baseline: WhatIfTotals
    result: WhatIfTotals
    delta: WhatIfTotals
    assumptions: list[str]
    explanation: str
    explanation_source: Literal["llm", "template"]


class SimulateOrdersRequest(BaseModel):
    days: int = Field(default=56, ge=7, le=120)
    seed: int = 42
    promotion: bool = True


class SimulateOrdersResponse(BaseModel):
    orders_created: int
    start_date: str
    end_date: str
    assumptions: dict
