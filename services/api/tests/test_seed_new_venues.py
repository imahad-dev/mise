"""The phase 2 venues seed as the spec says (2026-11-09, phase 2)."""

import json
from decimal import Decimal

import pytest
from scripts.seed import DEFAULT_SEED_FILES, load_seed_data, seed_data
from sqlalchemy import func, select

from src.config import settings
from src.models import DiningTable, MenuItem, Restaurant

EU14 = {
    "gluten",
    "milk",
    "eggs",
    "fish",
    "crustaceans",
    "molluscs",
    "tree_nuts",
    "peanuts",
    "soy",
    "celery",
    "mustard",
    "sesame",
    "sulphites",
    "lupin",
}

VENUES = {
    "tikka-town": dict(
        file="data/seed/tikka_town.json",
        name="Tikka Town",
        city="Manchester",
        currency="GBP",
        jurisdiction="GB",
        service="0.10",
        tables=12,
        languages=["en"],
        items=(26, 30),
        tz="Europe/London",
    ),
}


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


@pytest.mark.parametrize("slug", VENUES)
def test_registered_everywhere(slug):
    v = VENUES[slug]
    assert v["file"] in DEFAULT_SEED_FILES
    assert slug in settings.demo_restaurant_slugs
    users = _load("data/seed/demo_users.json")
    assert slug in users["owner"]["venues"]
    assert [s for s in users["staff"] if s["venue"] == slug], "one staff user per venue"


@pytest.mark.parametrize("slug", VENUES)
def test_seed_file_is_well_formed(slug):
    v = VENUES[slug]
    data = _load(v["file"])
    r = data["restaurant"]
    assert (r["slug"], r["name"], r["city"], r["currency"], r["tax_jurisdiction"]) == (
        slug,
        v["name"],
        v["city"],
        v["currency"],
        v["jurisdiction"],
    )
    assert r["languages"] == v["languages"] and r["default_language"] == "en"
    assert r["timezone"] == v["tz"]
    assert len([t for t in data["tables"] if t.get("kind", "table") == "table"]) == v["tables"]
    assert not [t for t in data["tables"] if t.get("kind") == "counter"]
    lo, hi = v["items"]
    assert lo <= len(data["items"]) <= hi
    keys = [i["key"] for i in data["items"]]
    assert len(keys) == len(set(keys)), "keys are unique"
    assert {m for m, _ in data["simulation"]["payment_mix"]} <= {"cash", "card"}
    for item in data["items"]:
        assert set(item["allergens"]) <= EU14, item["key"]
        assert item["allergen_verified"] is False, item["key"]
        assert item["ingredients"], item["key"]
        assert 0 < item["unit_cost"] < item["price"], item["key"]
        for g in item.get("choice_groups", []):
            for c in g["choices"]:
                assert set(c.get("allergens", [])) <= EU14, f"{item['key']}: {c['label']}"


@pytest.mark.parametrize("slug", VENUES)
async def test_seeds_into_the_database(slug, db_session):
    v = VENUES[slug]
    await seed_data(load_seed_data(v["file"]), db_session)
    r = (await db_session.execute(select(Restaurant).where(Restaurant.slug == slug))).scalar_one()
    assert r.service_charge_rate == Decimal(v["service"])
    tables = await db_session.scalar(
        select(func.count()).select_from(DiningTable).where(DiningTable.restaurant_id == r.id)
    )
    assert tables == v["tables"]
    items = await db_session.scalar(
        select(func.count()).select_from(MenuItem).where(MenuItem.restaurant_id == r.id)
    )
    assert items == len(_load(v["file"])["items"])


def test_tikka_town_has_the_spec_dishes():
    names = {
        i["translations"]["en"]["name"].lower() for i in _load("data/seed/tikka_town.json")["items"]
    }
    for dish in [
        "lamb chops",
        "seekh kebab",
        "chicken tikka",
        "chicken tikka masala",
        "masala fish and chips",
        "chicken tikka pie",
        "lancashire hotpot",
        "chips and curry sauce",
        "bombay potatoes",
        "manchester tart",
        "eccles cake",
        "sticky toffee pudding",
        "gulab jamun",
        "mango lassi",
        "masala chai",
        "nihari",
        "keema naan",
        "samosa chaat",
        "karahi",
        "balti",
        "sunday roast",
    ]:
        assert any(dish in n for n in names), dish
