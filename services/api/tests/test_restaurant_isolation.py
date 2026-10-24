"""Every /api/restaurants/{slug} route refuses members of another restaurant with 404."""

import re

import pytest
from tests.helpers import as_member

from src.main import app
from src.models.restaurant import Restaurant

PLACEHOLDER = re.compile(r"\{(\w+)\}")
DUMMY = {
    "id": "00000000-0000-0000-0000-000000000000",
    "order_id": "00000000-0000-0000-0000-000000000000",
    "bill_id": "00000000-0000-0000-0000-000000000000",
}


def _slug_routes():
    # FastAPI 0.143 wraps included routers, so app.routes has no APIRoutes; the OpenAPI paths
    # list every route (none sets include_in_schema=False).
    for path, operations in app.openapi()["paths"].items():
        if "{slug}" in path:
            for method in operations:
                yield method.upper(), path


def test_there_are_slug_routes():
    assert len(list(_slug_routes())) >= 10


@pytest.mark.parametrize(("method", "path"), sorted(_slug_routes()))
async def test_other_venue_member_gets_404(client, db_session, method, path):
    mine = Restaurant(
        name="Mine",
        slug="iso-mine",
        currency="PKR",
        timezone="Asia/Karachi",
        languages=["en"],
        default_language="en",
    )
    theirs = Restaurant(
        name="Theirs",
        slug="iso-theirs",
        currency="PKR",
        timezone="Asia/Karachi",
        languages=["en"],
        default_language="en",
    )
    db_session.add_all([mine, theirs])
    await db_session.flush()
    await as_member(client, db_session, mine.id, "owner")
    url = PLACEHOLDER.sub(lambda m: "iso-theirs" if m[1] == "slug" else DUMMY.get(m[1], "x"), path)
    resp = await client.request(method, url, json={})
    assert resp.status_code == 404, f"{method} {path} -> {resp.status_code}"
    assert resp.json()["detail"] == "Restaurant not found"
