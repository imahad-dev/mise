"""Restaurant sales tax: rates are data (data/tax_rates.json), the calculation is pure."""

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType
from typing import Literal

from src.config import settings

CENTS = Decimal("0.01")
PaymentMethod = Literal["cash", "card", "wallet", "raast", "bank_transfer"]
PaymentClass = Literal["standard", "digital"]
PAYMENT_METHODS: tuple[str, ...] = ("cash", "card", "wallet", "raast", "bank_transfer")
# The reduced rate covers only debit/credit card, mobile wallet and QR scanning (Raast QR).
_DIGITAL = {"card", "wallet", "raast"}


class TaxRateError(ValueError):
    pass


@dataclass(frozen=True)
class TaxRate:
    jurisdiction: str
    payment_class: str
    rate: Decimal
    effective_from: date
    source: str


def payment_class(method: str) -> PaymentClass:
    if method not in PAYMENT_METHODS:
        raise TaxRateError(f"Unknown payment method {method!r}")
    return "digital" if method in _DIGITAL else "standard"


def _data_path(name: str, override: str | None) -> Path:
    if override:
        return Path(override)
    here = Path(__file__).resolve()
    # /app/data in the container (parents[2]), <repo>/data in a checkout (parents[4]);
    # slicing never raises when the path is shorter than expected.
    for base in here.parents[2:5:2]:
        candidate = base / "data" / name
        if candidate.is_file():
            return candidate
    raise TaxRateError(f"data/{name} not found")


def _default_path() -> Path:
    return _data_path("tax_rates.json", settings.tax_rates_path)


def load_rates(path: Path | None = None) -> list[TaxRate]:
    try:
        raw = json.loads((path or _default_path()).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise TaxRateError(f"Cannot read tax rates: {e}") from e
    if not isinstance(raw, list) or not raw:
        raise TaxRateError("Tax rates file must be a non-empty list")
    rates: list[TaxRate] = []
    seen: set[tuple[str, str, date]] = set()
    for entry in raw:
        try:
            r = TaxRate(
                jurisdiction=str(entry["jurisdiction"]),
                payment_class=str(entry["payment_class"]),
                rate=Decimal(str(entry["rate"])),
                effective_from=date.fromisoformat(entry["effective_from"]),
                source=str(entry["source"]),
            )
        except (KeyError, TypeError, ValueError, ArithmeticError) as e:
            raise TaxRateError(f"Bad tax rate entry {entry!r}: {e}") from e
        if not r.jurisdiction.strip() or not isinstance(entry["source"], str):
            raise TaxRateError(f"Bad tax rate entry {entry!r}: jurisdiction/source required")
        if not r.source.strip():
            raise TaxRateError(f"Bad tax rate entry {entry!r}: empty source")
        if not r.rate.is_finite():
            raise TaxRateError(f"Rate must be finite: {r.rate}")
        if r.payment_class not in ("standard", "digital", "any"):
            raise TaxRateError(f"Unknown payment class {r.payment_class!r}")
        if not Decimal("0") <= r.rate <= Decimal("1"):
            raise TaxRateError(f"Rate out of range: {r.rate}")
        key = (r.jurisdiction, r.payment_class, r.effective_from)
        if key in seen:
            raise TaxRateError(f"Duplicate tax rate {key}")
        seen.add(key)
        rates.append(r)
    return rates


@lru_cache(maxsize=1)
def default_rates() -> tuple[TaxRate, ...]:
    return tuple(load_rates())


Pricing = Literal["on_top", "included"]


@dataclass(frozen=True)
class Jurisdiction:
    code: str
    name: str
    currency: str
    pricing: Pricing
    rounding: Decimal  # every tax, service and total amount rounds half up to this unit
    methods: tuple[str, ...]
    service_charge: Literal["optional_outside_tax"] | None


def load_jurisdictions(path: Path | None = None) -> dict[str, Jurisdiction]:
    try:
        path = path or _data_path("tax_jurisdictions.json", settings.tax_jurisdictions_path)
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise TaxRateError(f"Cannot read tax jurisdictions: {e}") from e
    if not isinstance(raw, dict) or not raw:
        raise TaxRateError("Tax jurisdictions file must be a non-empty object")
    out: dict[str, Jurisdiction] = {}
    for code, e in raw.items():
        try:
            if not isinstance(e["name"], str) or not isinstance(e["currency"], str):
                raise TypeError("name and currency must be strings")
            if not isinstance(e["methods"], list):
                raise TypeError("methods must be a list")
            j = Jurisdiction(
                code=str(code),
                name=e["name"],
                currency=e["currency"],
                pricing=e["pricing"],
                rounding=Decimal(str(e["rounding"])),
                methods=tuple(e["methods"]),
                service_charge=e["service_charge"],
            )
        except (KeyError, TypeError, ValueError, ArithmeticError) as err:
            raise TaxRateError(f"Bad jurisdiction {code!r}: {err}") from err
        if not j.code.strip() or j.code != j.code.strip():
            raise TaxRateError(f"Bad jurisdiction {code!r}: bad code")
        if not j.name.strip():
            raise TaxRateError(f"Bad jurisdiction {code!r}: name required")
        if not re.fullmatch(r"[A-Z]{3}", j.currency):
            raise TaxRateError(f"Bad jurisdiction {code!r}: currency {j.currency!r}")
        if j.pricing not in ("on_top", "included"):
            raise TaxRateError(f"Bad jurisdiction {code!r}: unknown pricing {j.pricing!r}")
        if not (
            j.rounding.is_finite()
            and CENTS <= j.rounding <= Decimal("1000")  # bounds keep % from overflowing
            and j.rounding % CENTS == 0
        ):
            raise TaxRateError(f"Bad jurisdiction {code!r}: rounding must be whole cents")
        if (
            not j.methods
            or len(set(j.methods)) != len(j.methods)
            or any(m not in PAYMENT_METHODS for m in j.methods)
        ):
            raise TaxRateError(f"Bad jurisdiction {code!r}: methods {j.methods!r}")
        if j.service_charge not in (None, "optional_outside_tax"):
            raise TaxRateError(f"Bad jurisdiction {code!r}: service_charge {j.service_charge!r}")
        out[j.code] = j
    return out


def check_rates_against(
    rates: tuple[TaxRate, ...] | list[TaxRate], jurisdictions: dict[str, Jurisdiction]
) -> None:
    """Rates name known jurisdictions, never mix "any" with a split, and cover the methods."""
    classes: dict[str, set[str]] = {}
    for r in rates:
        if r.jurisdiction not in jurisdictions:
            raise TaxRateError(f"Rate for unknown jurisdiction {r.jurisdiction!r}")
        classes.setdefault(r.jurisdiction, set()).add(r.payment_class)
    for code, cls in classes.items():
        if "any" in cls and len(cls) > 1:
            raise TaxRateError(f"Jurisdiction {code!r} mixes 'any' with standard/digital rates")
    for code, j in jurisdictions.items():
        have = classes.get(code, set())
        if "any" in have:
            continue
        for needed in {payment_class(m) for m in j.methods}:
            if needed not in have:
                raise TaxRateError(f"Jurisdiction {code!r} has no {needed} rate")


@lru_cache(maxsize=1)
def default_jurisdictions() -> Mapping[str, Jurisdiction]:
    js = load_jurisdictions()
    check_rates_against(default_rates(), js)
    return MappingProxyType(js)


def jurisdictions(rates: tuple[TaxRate, ...] | list[TaxRate] | None = None) -> set[str]:
    return {r.jurisdiction for r in (rates if rates is not None else default_rates())}


def round_money(amount: Decimal, unit: Decimal) -> Decimal:
    """Half up to the jurisdiction's money unit, stored with two decimals."""
    return ((amount / unit).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * unit).quantize(CENTS)


@dataclass(frozen=True)
class Charge:
    rate: Decimal
    tax: Decimal  # on_top: added to the subtotal; included: the part of the total that is tax
    total: Decimal  # what the guest pays before any optional service charge
    pricing: Pricing


def jurisdiction_of(code: str | None) -> Jurisdiction | None:
    return default_jurisdictions().get(code or "")


def check_venue_tax(jurisdiction: str | None, currency: str) -> None:
    """A venue's jurisdiction must exist and use the venue's currency."""
    if jurisdiction is None:
        return
    j = jurisdiction_of(jurisdiction)
    if j is None:
        raise TaxRateError(f"Unknown tax jurisdiction {jurisdiction!r}")
    if j.currency != currency:
        raise TaxRateError(
            f"{jurisdiction} bills in {j.currency}; the venue's currency is {currency}"
        )


def charge_for(
    jurisdiction: str,
    method: str,
    on_date: date,
    subtotal: Decimal,
    rates: tuple[TaxRate, ...] | list[TaxRate] | None = None,
) -> Charge:
    """Rate, tax and total for a bill of menu-price lines settled on on_date.

    The jurisdiction and its methods always come from the shipped jurisdictions, even when
    `rates` is passed.
    """
    j = jurisdiction_of(jurisdiction)
    if j is None:
        raise TaxRateError(f"Unknown tax jurisdiction {jurisdiction!r}")
    if method not in j.methods:
        raise TaxRateError(f"Payment method {method!r} is not accepted in {jurisdiction}")
    cls = payment_class(method)
    candidates = [
        r
        for r in (rates if rates is not None else default_rates())
        if r.jurisdiction == jurisdiction
        and r.payment_class in (cls, "any")
        and r.effective_from <= on_date
    ]
    if not candidates:
        raise TaxRateError(f"No tax rate configured for {jurisdiction}/{cls} on {on_date}")
    rate = max(candidates, key=lambda r: r.effective_from).rate
    if j.pricing == "on_top":
        tax = round_money(subtotal * rate, j.rounding)
        return Charge(rate, tax, subtotal + tax, "on_top")
    tax = round_money(subtotal * rate / (1 + rate), j.rounding)
    # shortcut: total is the raw menu-price subtotal; round it if an inclusive jurisdiction
    # ever uses a unit coarser than 0.01
    return Charge(rate, tax, subtotal, "included")


def tax_for(
    jurisdiction: str,
    method: str,
    on_date: date,
    subtotal: Decimal,
    rates: tuple[TaxRate, ...] | list[TaxRate] | None = None,
) -> tuple[Decimal, Decimal]:
    """(rate, tax amount) for tax-on-top jurisdictions only; use charge_for for the total."""
    c = charge_for(jurisdiction, method, on_date, subtotal, rates)
    if c.pricing != "on_top":
        raise TaxRateError("tax_for is for tax-on-top jurisdictions; use charge_for")
    return c.rate, c.tax


def service_charge_for(
    jurisdiction: str | None, rate: Decimal, subtotal: Decimal, is_table: bool
) -> tuple[Decimal, Decimal]:
    """(rate, amount) of the optional service charge; (0, 0) where it does not apply."""
    j = jurisdiction_of(jurisdiction)
    if j is None or j.service_charge is None or not is_table or rate <= 0:
        return Decimal("0.0000"), Decimal("0.00")  # same scale as the stored columns
    return rate.quantize(Decimal("0.0001")), round_money(subtotal * rate, j.rounding)


def methods_for(jurisdiction: str | None) -> tuple[str, ...]:
    """Methods a venue may settle with; all of them when it has no jurisdiction (no tax)."""
    j = jurisdiction_of(jurisdiction)
    return j.methods if j else PAYMENT_METHODS


def splits_by_method(jurisdiction: str | None) -> bool:
    """True where cash and digital payments carry different rates (Pakistan)."""
    return any(r.jurisdiction == jurisdiction and r.payment_class != "any" for r in default_rates())


def price_tax_factor(jurisdiction: str | None, on_date: date) -> Decimal:
    """Menu price / factor = price excluding VAT; 1 where tax sits on top or is unknown."""
    j = jurisdiction_of(jurisdiction)
    if j is None or j.pricing != "included":
        return Decimal(1)
    try:
        # included pricing implies an "any" rate, so methods[0] gives the one rate
        return 1 + charge_for(j.code, j.methods[0], on_date, Decimal(0)).rate
    except TaxRateError:
        return Decimal(1)
