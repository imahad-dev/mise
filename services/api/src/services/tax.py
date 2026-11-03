"""Restaurant sales tax: rates are data (data/tax_rates.json), the calculation is pure."""

import json
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from functools import lru_cache
from pathlib import Path
from typing import Literal

from src.config import settings

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


def _default_path() -> Path:
    if settings.tax_rates_path:
        return Path(settings.tax_rates_path)
    here = Path(__file__).resolve()
    # /app/data in the container (parents[2]), <repo>/data in a checkout (parents[4]);
    # slicing never raises when the path is shorter than expected.
    for base in here.parents[2:5:2]:
        candidate = base / "data" / "tax_rates.json"
        if candidate.is_file():
            return candidate
    raise TaxRateError("data/tax_rates.json not found")


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
        if r.payment_class not in ("standard", "digital"):
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


def jurisdictions(rates: tuple[TaxRate, ...] | list[TaxRate] | None = None) -> set[str]:
    return {r.jurisdiction for r in (rates if rates is not None else default_rates())}


def tax_for(
    jurisdiction: str,
    method: str,
    on_date: date,
    subtotal: Decimal,
    rates: tuple[TaxRate, ...] | list[TaxRate] | None = None,
) -> tuple[Decimal, Decimal]:
    """(rate, tax amount rounded half-up to whole rupees) for a bill settled on on_date."""
    cls = payment_class(method)
    candidates = [
        r
        for r in (rates if rates is not None else default_rates())
        if r.jurisdiction == jurisdiction and r.payment_class == cls and r.effective_from <= on_date
    ]
    if not candidates:
        raise TaxRateError(f"No tax rate configured for {jurisdiction}/{cls} on {on_date}")
    rate = max(candidates, key=lambda r: r.effective_from).rate
    return rate, (subtotal * rate).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
