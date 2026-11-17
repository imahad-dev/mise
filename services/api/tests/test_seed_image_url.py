"""The seed writes a dish's image_url and clears it when the seed drops it (phase 3)."""

import copy

from scripts.seed import load_seed_data, seed_data
from sqlalchemy import select

from src.models import MenuItem, Restaurant

PHOTO = "/venues/tikka-town/dishes/lamb_chops.webp"


async def _urls(db_session) -> list[str | None]:
    r = (
        await db_session.execute(select(Restaurant).where(Restaurant.slug == "tikka-town"))
    ).scalar_one()
    rows = await db_session.execute(
        select(MenuItem.image_url).where(
            MenuItem.restaurant_id == r.id, MenuItem.image_url.is_not(None)
        )
    )
    return list(rows.scalars().all())


async def test_seed_sets_then_clears_image_url(db_session):
    base = load_seed_data("data/seed/tikka_town.json")
    for item in base["items"]:
        item.pop("image_url", None)

    with_photo = copy.deepcopy(base)
    with_photo["items"][0]["image_url"] = PHOTO
    await seed_data(with_photo, db_session)  # create path
    assert await _urls(db_session) == [PHOTO]

    await seed_data(copy.deepcopy(base), db_session)  # update path
    assert await _urls(db_session) == []
