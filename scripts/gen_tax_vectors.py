"""Write data/test-vectors/tax_vectors.json: API per-method tax previews for 50 bills.

The owner-web Vitest suite checks the UI shows these numbers verbatim; the API's
tests/test_money_agreement.py checks the file still matches the server's tax code.

Usage: uv run --project services/api python scripts/gen_tax_vectors.py
"""

import json
import random
import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "services" / "api"))

from src.services.bills import method_previews
from src.services.tax import PAYMENT_METHODS

OUT = REPO / "data" / "test-vectors" / "tax_vectors.json"
# Fixed edge cases first: zero, half-rupee rounding, and both sides of 1 July 2026.
FIXED = [
    ("PB", "cash", "2026-06-30", 0),
    ("ICT", "card", "2026-07-02", 10),  # 0.50 tax rounds half up to 1
    ("ICT", "cash", "2026-06-28", 30),  # 4.50 -> 5
    ("PB", "card", "2026-06-30", 2340),  # 5%
    ("PB", "card", "2026-07-01", 2340),  # 8%
]


def vector(jurisdiction: str, method: str, on: str, subtotal: int) -> dict:
    sub = Decimal(subtotal).quantize(Decimal("0.01"))
    preview = next(
        p
        for p in method_previews(jurisdiction, sub, date.fromisoformat(on))
        if p.method == method
    )
    return {
        "jurisdiction": jurisdiction,
        "date": on,
        "subtotal": f"{sub:.2f}",
        "currency": "PKR",
        **preview.model_dump(mode="json"),
    }


def vectors() -> list[dict]:
    rng = random.Random(1234)
    out = [vector(*case) for case in FIXED]
    while len(out) < 50:
        on = date(2026, 6, 25) + timedelta(days=rng.randint(0, 10))
        out.append(
            vector(
                rng.choice(["PB", "ICT"]),
                rng.choice(PAYMENT_METHODS),
                on.isoformat(),
                rng.randint(0, 200_000),
            )
        )
    return out


if __name__ == "__main__":
    doc = {
        "description": "API tax previews (MethodPreview) per bill; the UI must show them verbatim",
        "generator": "scripts/gen_tax_vectors.py",
        "vectors": vectors(),
    }
    OUT.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(doc['vectors'])} vectors to {OUT.relative_to(REPO)}")
