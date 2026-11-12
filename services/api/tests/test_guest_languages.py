"""A venue offers only its own languages (spec 2026-11-09, phase 1b)."""

import pytest
from httpx import AsyncClient
from scripts.seed import load_seed_data, seed_data
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from tests.choices_setup import line, order, tea_setup  # noqa: F401 - fixture

from src.auth import GUEST_COOKIE_NAME
from src.models.dining_table import DiningTable
from src.models.menu import MenuChoiceGroup, MenuItem
from src.models.order import OrderItem
from src.models.restaurant import Restaurant
from src.models.session import GuestSession


@pytest.fixture
async def angeethi(db_session: AsyncSession) -> tuple[Restaurant, str]:
    await seed_data(load_seed_data("data/seed/angeethi_house.json"), db_session, rotate_qr=False)
    r = (
        await db_session.execute(select(Restaurant).where(Restaurant.slug == "angeethi-house"))
    ).scalar_one()
    qr = (
        (
            await db_session.execute(
                select(DiningTable.qr_token).where(DiningTable.restaurant_id == r.id)
            )
        )
        .scalars()
        .first()
    )
    return r, qr


async def _session(client: AsyncClient, qr: str, **body):
    return await client.post("/api/guest/sessions", json={"qr_token": qr, **body})


async def test_venue_lists_its_languages(client: AsyncClient, angeethi):
    _, qr = angeethi
    v = (await client.get(f"/api/guest/venues/{qr}")).json()
    assert v == {
        "slug": "angeethi-house",
        "name": "Angeethi House",
        "languages": ["en", "ur"],
        "default_language": "en",
    }
    s = (await _session(client, qr, language="ur")).json()
    assert s["language"] == "ur"
    assert s["venue"]["languages"] == ["en", "ur"]


@pytest.mark.parametrize("lang", ["it", "UR", "ur-PK", "", "fr"])
async def test_unknown_language_refused(client: AsyncClient, angeethi, lang):
    _, qr = angeethi
    assert (await _session(client, qr, language=lang)).status_code == 422


async def test_language_the_venue_does_not_offer_is_refused(client: AsyncClient, angeethi):
    _, qr = angeethi
    resp = await _session(client, qr, language="ar")
    assert resp.status_code == 422
    assert "language" in resp.json()["detail"].lower()


async def test_missing_language_is_the_venue_default(
    client: AsyncClient, angeethi, db_session: AsyncSession
):
    r, qr = angeethi
    r.languages, r.default_language = ["ur"], "ur"  # a venue without English
    await db_session.flush()
    assert (await _session(client, qr)).json()["language"] == "ur"
    assert (await _session(client, qr, language="en")).status_code == 422


async def test_patch_refuses_unoffered_language_and_keeps_the_old_one(
    client: AsyncClient, angeethi
):
    _, qr = angeethi
    created = await _session(client, qr, language="ur")
    client.cookies.set(GUEST_COOKIE_NAME, created.cookies[GUEST_COOKIE_NAME])
    assert (await client.patch("/api/guest/session", json={"language": "ar"})).status_code == 422
    assert (await client.patch("/api/guest/session", json={"language": "it"})).status_code == 422
    assert (await client.get("/api/guest/session")).json()["language"] == "ur"
    assert (await client.patch("/api/guest/session", json={"language": "en"})).json()[
        "language"
    ] == "en"


async def test_refused_language_patch_changes_nothing_else(client: AsyncClient, angeethi):
    _, qr = angeethi
    created = await _session(client, qr, language="ur", dietary_preferences=["vegan"])
    client.cookies.set(GUEST_COOKIE_NAME, created.cookies[GUEST_COOKIE_NAME])
    resp = await client.patch(
        "/api/guest/session", json={"language": "ar", "dietary_preferences": ["vegetarian"]}
    )
    assert resp.status_code == 422
    kept = (await client.get("/api/guest/session")).json()
    assert kept["dietary_preferences"] == ["vegan"]
    assert kept["language"] == "ur"


async def _menu(client: AsyncClient, qr: str, lang: str) -> list[dict]:
    created = await _session(client, qr, language=lang)
    client.cookies.set(GUEST_COOKIE_NAME, created.cookies[GUEST_COOKIE_NAME])
    return (await client.get("/api/guest/menu")).json()["items"]


async def _translate_karahi(db: AsyncSession) -> MenuItem:
    item = (
        (
            await db.execute(
                select(MenuItem)
                .options(
                    selectinload(MenuItem.options),
                    selectinload(MenuItem.choice_groups).selectinload(MenuChoiceGroup.choices),
                )
                .join(Restaurant)
                .where(
                    Restaurant.slug == "angeethi-house",
                    MenuItem.category == "Karahi",
                    MenuItem.options.any(),
                    MenuItem.choice_groups.any(),
                )
            )
        )
        .scalars()
        .first()
    )
    item.options[0].translations = {"ur": "آدھا کلو"}
    item.choice_groups[0].translations = {"ur": "مرچ"}
    item.choice_groups[0].choices[0].translations = {"ur": "ہلکی"}
    item.choice_groups[0].choices[1].translations = {}  # untranslated: falls back to English
    await db.flush()
    return item


async def test_urdu_labels_reach_the_guest_and_fall_back_to_english(
    client: AsyncClient, angeethi, db_session: AsyncSession
):
    _, qr = angeethi
    item = await _translate_karahi(db_session)
    dish = next(i for i in await _menu(client, qr, "ur") if i["id"] == str(item.id))
    assert dish["options"][0]["label"] == "آدھا کلو"
    group = dish["choice_groups"][0]
    assert group["label"] == "مرچ"
    assert group["choices"][0]["label"] == "ہلکی"
    assert group["choices"][1]["label"] == item.choice_groups[0].choices[1].label


async def test_english_guest_sees_english_labels(
    client: AsyncClient, angeethi, db_session: AsyncSession
):
    _, qr = angeethi
    item = await _translate_karahi(db_session)
    dish = next(i for i in await _menu(client, qr, "en") if i["id"] == str(item.id))
    assert dish["options"][0]["label"] == item.options[0].label
    assert dish["choice_groups"][0]["label"] == item.choice_groups[0].label
    assert dish["choice_groups"][0]["choices"][0]["label"] == (
        item.choice_groups[0].choices[0].label
    )


async def test_translations_never_leak_raw_to_the_guest(
    client: AsyncClient, angeethi, db_session: AsyncSession
):
    _, qr = angeethi
    await _translate_karahi(db_session)
    for dish in await _menu(client, qr, "ur"):
        assert "translations" not in dish
        for o in dish.get("options", []):
            assert "translations" not in o
        for g in dish.get("choice_groups", []):
            assert "translations" not in g
            assert all("translations" not in c for c in g["choices"])


async def test_urdu_guest_order_snapshots_english_choice_labels(
    client: AsyncClient,
    tea_setup,  # noqa: F811
    db_session: AsyncSession,
):
    s = tea_setup
    s.mild.translations = {"ur": "ہلکی"}
    session = (
        await db_session.execute(
            select(GuestSession).where(GuestSession.restaurant_id == s.restaurant.id)
        )
    ).scalar_one()
    session.language = "ur"
    await db_session.flush()
    resp = await order(client, "ur-1", [line(s, s.mild)], ack=True)
    assert resp.status_code == 201
    assert [c["label"] for c in resp.json()["items"][0]["choices"]] == ["Mild"]
    row = (
        await db_session.execute(select(OrderItem).where(OrderItem.order_id == resp.json()["id"]))
    ).scalar_one()
    assert "ہلکی" not in str(row.choices)
    assert "Mild" in str(row.choices)
