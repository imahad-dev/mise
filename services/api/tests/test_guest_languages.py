"""A venue offers only its own languages (spec 2026-11-09, phase 1b)."""

import pytest
from httpx import AsyncClient
from scripts.seed import load_seed_data, seed_data
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import GUEST_COOKIE_NAME
from src.models.dining_table import DiningTable
from src.models.restaurant import Restaurant


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
