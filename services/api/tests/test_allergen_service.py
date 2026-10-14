"""Test allergen service against shared test vectors."""

import json
from pathlib import Path

import pytest

from src.services.allergen_service import compute_allergen_status


def load_test_vectors() -> list[dict]:
    candidates = [
        Path(__file__).resolve().parents[3] / "data" / "test-vectors" / "allergen-filter.json",
        Path.cwd() / "data" / "test-vectors" / "allergen-filter.json",
        Path("/app/data/test-vectors/allergen-filter.json"),
    ]
    for p in candidates:
        if p.exists():
            with open(p, encoding="utf-8") as f:
                data = json.load(f)
            return data["vectors"]
    raise FileNotFoundError(f"allergen-filter.json not found in {candidates}")


VECTORS = load_test_vectors()


@pytest.mark.parametrize(
    "vector",
    VECTORS,
    ids=[v["id"] for v in VECTORS],
)
def test_allergen_service_vectors(vector: dict):
    result = compute_allergen_status(
        item_allergens=vector["item_allergens"],
        allergen_verified=vector["allergen_verified"],
        guest_allergens_to_avoid=vector["guest_allergens_to_avoid"],
    )
    assert result == vector["expected_status"], (
        f"Vector '{vector['id']}' failed: expected {vector['expected_status']!r}, got {result!r}. "
        f"Description: {vector.get('description')}"
    )
