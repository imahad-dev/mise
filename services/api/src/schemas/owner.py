"""Owner schemas for menu items and table management."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from src.schemas.guest import EU14Allergen


class OwnerMenuTranslation(BaseModel):
    language: str
    name: str
    description: str | None = None

    model_config = ConfigDict(from_attributes=True)


class OwnerChoice(BaseModel):
    id: uuid.UUID
    label: str
    price_delta: Decimal
    cost_delta: Decimal
    allergens: list[str]
    allergen_verified: bool
    is_vegetarian: bool
    is_vegan: bool
    available: bool
    is_default: bool
    sort_order: int

    model_config = ConfigDict(from_attributes=True)


class OwnerChoiceGroup(BaseModel):
    id: uuid.UUID
    label: str
    kind: Literal["pick", "add", "leave_out"]
    min_select: int
    max_select: int
    sort_order: int
    choices: list[OwnerChoice] = []

    model_config = ConfigDict(from_attributes=True)


class CreateChoiceGroup(BaseModel):
    label: str = Field(..., min_length=1, max_length=60)
    kind: Literal["pick", "add", "leave_out"]
    min_select: int = Field(0, ge=0, le=20)
    max_select: int = Field(1, ge=1, le=20)
    sort_order: int = 0

    @model_validator(mode="after")
    def _range(self) -> "CreateChoiceGroup":
        if self.min_select > self.max_select:
            raise ValueError("The minimum can't be above the maximum")
        return self


class PatchChoiceGroup(BaseModel):
    """`kind` is fixed once created: it decides which save rules its choices passed."""

    label: str | None = Field(None, min_length=1, max_length=60)
    min_select: int | None = Field(None, ge=0, le=20)
    max_select: int | None = Field(None, ge=1, le=20)
    sort_order: int | None = None


class CreateChoice(BaseModel):
    label: str = Field(..., min_length=1, max_length=60)
    price_delta: Decimal = Field(Decimal("0"), ge=0, max_digits=10, decimal_places=2)
    cost_delta: Decimal = Field(Decimal("0"), ge=0, max_digits=10, decimal_places=2)
    allergens: list[EU14Allergen] = []
    allergen_verified: bool = False
    is_vegetarian: bool = False
    is_vegan: bool = False
    available: bool = True
    is_default: bool = False
    sort_order: int = 0


class PatchChoice(BaseModel):
    label: str | None = Field(None, min_length=1, max_length=60)
    price_delta: Decimal | None = Field(None, ge=0, max_digits=10, decimal_places=2)
    cost_delta: Decimal | None = Field(None, ge=0, max_digits=10, decimal_places=2)
    allergens: list[EU14Allergen] | None = None
    allergen_verified: bool | None = None
    is_vegetarian: bool | None = None
    is_vegan: bool | None = None
    available: bool | None = None
    is_default: bool | None = None
    sort_order: int | None = None


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
    is_pay_forward: bool = False
    sort_order: int
    image_url: str | None = None
    translations: list[OwnerMenuTranslation]
    choice_groups: list[OwnerChoiceGroup] = []
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
    # The venue's pay-it-forward chai (at most one live item per venue).
    is_pay_forward: bool | None = None


class OwnerTableResponse(BaseModel):
    id: uuid.UUID
    restaurant_id: uuid.UUID
    label: str
    qr_token: str
    guest_url: str
    # "counter" is the counter / pickup QR.
    kind: Literal["table", "counter"]

    model_config = ConfigDict(from_attributes=True)


class PatchSettingsRequest(BaseModel):
    payment_details: dict[str, Any] | None = None
    service_extra_label: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)] | None
    ) = None
    # Pickup numbers print as "<prefix>-042": 1-3 uppercase ASCII letters.
    pickup_prefix: Annotated[str, StringConstraints(pattern=r"^[A-Z]{1,3}$")] | None = None
    # Ask guests for a 4-digit table number before their first order (tables opened from now on).
    sitting_code_required: bool | None = None
    # Optional service charge; the router refuses a non-zero rate where it is not offered.
    service_charge_rate: Decimal | None = Field(
        default=None, ge=0, le=Decimal("0.20"), decimal_places=4
    )

    @field_validator("service_extra_label", mode="before")
    @classmethod
    def _blank_label_clears(cls, v: Any) -> Any:
        # null or a blank label clears it (omit the field to keep it).
        return None if isinstance(v, str) and not v.strip() else v


class TaxRule(BaseModel):
    name: str
    rate: Decimal
    pricing: Literal["on_top", "included"]


class SettingsResponse(BaseModel):
    payment_details: dict[str, Any]
    service_extra_label: str | None
    pickup_prefix: str | None
    sitting_code_required: bool
    service_charge_rate: Decimal
    service_charge_allowed: bool
    tax_rule: TaxRule | None


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


class PayForwardTotals(BaseModel):
    bought: int
    given: int


class Kpis(BaseModel):
    orders: int
    revenue: float
    aov: float
    contribution_margin: float
    margin_pct: float


class MenuEngineeringItem(BaseModel):
    item_id: str
    option_id: str | None
    name: str
    units: int
    weekly_units: float
    revenue: float
    unit_margin: float
    contribution: float
    menu_class: Literal["star", "plowhorse", "puzzle", "dog"]


class MenuThresholds(BaseModel):
    median_units: float
    median_unit_margin: float


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
    avg_revenue_per_day: float


class PaymentClassCounts(BaseModel):
    standard: int
    digital: int


class PaymentClassShares(BaseModel):
    standard: float
    digital: float


class TaxByRate(BaseModel):
    rate: Decimal
    tax: Decimal


class PaymentMix(BaseModel):
    """Settled bills in the window: standard (cash, bank transfer) vs digital payments."""

    bills: PaymentClassCounts
    revenue_share: PaymentClassShares
    digital_revenue_pct: float  # revenue_share.digital as a percentage, as the summary states it
    tax_by_rate: list[TaxByRate]
    digital_tax_saving: Decimal


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
    item_id: str | None  # menu item id, like menu_engineering[].item_id
    option_id: str | None = None  # set on a portion/size row
    item: str
    title: str
    evidence: dict[str, float | int | str]
    estimated_impact_per_week: float | None
    formula: str


class DailyBriefResponse(BaseModel):
    date: str
    currency: str
    window_start: str
    window_end: str
    data_sources: DataSources
    kpis: Kpis
    menu_engineering: list[MenuEngineeringItem]
    thresholds: MenuThresholds
    pairings: list[Pairing]
    peak_hours: list[PeakHour]
    payment_mix: PaymentMix
    prices_include_tax: bool
    tax_split_by_method: bool
    service_charge_collected: Decimal
    pay_forward: PayForwardTotals
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
    revenue: float
    margin: float


class WhatIfResponse(BaseModel):
    scenario: str
    currency: str
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
    bills_created: int
    start_date: str
    end_date: str
    assumptions: dict
