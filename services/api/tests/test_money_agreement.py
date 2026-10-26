"""Money agreement: the guest's per-method preview, the tax function and the staff preview
give the same tax and total for every bill; the shared UI vectors match the server."""

import json
import random
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from src.services.bills import method_previews, previews
from src.services.tax import PAYMENT_METHODS, payment_class, tax_for

CASES = 2000


def _vectors_file() -> Path:
    # /app/data in the container, <repo>/data in a checkout.
    for base in Path(__file__).resolve().parents:
        candidate = base / "data" / "test-vectors" / "tax_vectors.json"
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("data/test-vectors/tax_vectors.json")


def test_guest_preview_tax_function_and_staff_preview_agree():
    rng = random.Random(1234)
    for _ in range(CASES):
        subtotal = Decimal(rng.randint(0, 200_000)).quantize(Decimal("0.01"))
        method = rng.choice(PAYMENT_METHODS)
        jurisdiction = rng.choice(["PB", "ICT"])
        on = date(2026, 6, 25) + timedelta(days=rng.randint(0, 10))
        case = (jurisdiction, method, on, subtotal)

        guest = {p.method: p for p in method_previews(jurisdiction, subtotal, on)}[method]
        rate, tax = tax_for(jurisdiction, method, on, subtotal)
        standard, digital = previews(jurisdiction, subtotal, on)
        staff = digital if payment_class(method) == "digital" else standard

        assert guest.tax_rate == rate == staff.tax_rate, case
        assert guest.tax_amount == tax == staff.tax_amount, case
        assert guest.total == subtotal + tax == staff.total, case
        assert guest.payment_class == staff.payment_class == payment_class(method), case
        assert tax == tax.to_integral_value(), case  # whole rupees


def test_exact_edges():
    card, cash = "card", "cash"
    # Half a rupee rounds up.
    assert tax_for("ICT", card, date(2026, 7, 1), Decimal("10.00"))[1] == Decimal("1")
    assert tax_for("ICT", cash, date(2026, 7, 1), Decimal("30.00"))[1] == Decimal("5")
    # Punjab card tax moves from 5% to 8% on 1 July 2026; cash stays 16%.
    assert tax_for("PB", card, date(2026, 6, 30), Decimal("2340.00")) == (
        Decimal("0.05"),
        Decimal("117"),
    )
    assert tax_for("PB", card, date(2026, 7, 1), Decimal("2340.00")) == (
        Decimal("0.08"),
        Decimal("187"),
    )
    assert tax_for("PB", cash, date(2026, 6, 30), Decimal("2340.00"))[1] == Decimal("374")


def test_shared_ui_vectors_match_the_server():
    doc = json.loads(_vectors_file().read_text(encoding="utf-8"))
    vectors = doc["vectors"]
    assert len(vectors) == 50
    for v in vectors:
        expected = next(
            p
            for p in method_previews(
                v["jurisdiction"], Decimal(v["subtotal"]), date.fromisoformat(v["date"])
            )
            if p.method == v["method"]
        )
        got = {k: v[k] for k in expected.model_dump(mode="json")}
        assert got == expected.model_dump(mode="json"), v
