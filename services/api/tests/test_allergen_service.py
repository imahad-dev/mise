"""Test allergen service against shared test vectors."""

import json
import os
from pathlib import Path

import pytest

from src.services.allergen_service import compute_allergen_status


def find_test_vectors_path() -> Path:
    """Find data/test-vectors/allergen-filter.json with TEST_VECTORS_PATH override."""
    env_override = os.environ.get("TEST_VECTORS_PATH")
    if env_override:
        p = Path(env_override).resolve()
        if p.is_file():
            return p
        raise FileNotFoundError(
            f"TEST_VECTORS_PATH={env_override!r} does not exist or is not a file."
        )

    target_rel = Path("data") / "test-vectors" / "allergen-filter.json"
    searched: list[Path] = []

    # 1. Walk up from test file directory
    current = Path(__file__).resolve().parent
    for parent in [current, *current.parents]:
        candidate = parent / target_rel
        searched.append(candidate)
        if candidate.is_file():
            return candidate

    # 2. Walk up from current working directory
    cwd = Path.cwd().resolve()
    for parent in [cwd, *cwd.parents]:
        candidate = parent / target_rel
        if candidate not in searched:
            searched.append(candidate)
        if candidate.is_file():
            return candidate

    msg = "Could not find 'data/test-vectors/allergen-filter.json'.\nSearched paths:\n" + "\n".join(
        f" - {p}" for p in searched
    )
    raise FileNotFoundError(msg)


def load_test_vectors() -> list[dict]:
    vectors_file = find_test_vectors_path()
    with open(vectors_file, encoding="utf-8") as f:
        data = json.load(f)
    return data["vectors"]


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
