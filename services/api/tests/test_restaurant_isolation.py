"""Every /api/restaurants/{slug} route refuses members of another restaurant with 404."""

import importlib
import pkgutil
import re

import pytest
from fastapi.routing import APIRoute
from tests.helpers import as_member

import src.routers
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
    # list every schema route, and test_every_slug_route_is_in_the_schema covers the rest.
    for path, operations in app.openapi()["paths"].items():
        if "{slug}" in path:
            for method in operations:
                yield method.upper(), path


def _module_slug_routes() -> list[APIRoute]:
    """Every {slug} APIRoute declared by any router module in src/routers/."""
    routes = []
    for info in pkgutil.iter_modules(src.routers.__path__):
        module = importlib.import_module(f"src.routers.{info.name}")
        router = getattr(module, "router", None)
        for route in getattr(router, "routes", []):
            if isinstance(route, APIRoute) and "{slug}" in route.path:
                routes.append(route)
    return routes


def test_there_are_slug_routes():
    assert len(list(_slug_routes())) >= 10


def test_every_slug_route_is_in_the_schema():
    """A route hidden from OpenAPI would escape the parametrized check below."""
    routes = _module_slug_routes()
    hidden = [r.path for r in routes if not r.include_in_schema]
    assert hidden == [], f"{{slug}} routes with include_in_schema=False: {hidden}"
    declared = {(m, r.path) for r in routes for m in r.methods - {"HEAD", "OPTIONS"}}
    assert declared == set(_slug_routes())


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
