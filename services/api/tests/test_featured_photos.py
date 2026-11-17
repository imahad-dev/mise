"""Phase 3: each venue features 6 to 8 dishes, each with its own photo, and no other dish
has one (spec 2026-11-09, phase 3). Files and credits are checked in
apps/guest-web/src/lib/photos.test.ts."""

import json

import pytest

SEEDS = {
    "tikka-town": "data/seed/tikka_town.json",
    "noor-and-zaatar": "data/seed/noor_and_zaatar.json",
}


@pytest.mark.parametrize("slug", SEEDS)
def test_six_to_eight_featured_each_with_its_photo(slug):
    with open(SEEDS[slug], encoding="utf-8") as f:
        items = json.load(f)["items"]
    assert 6 <= sum(i["featured"] for i in items) <= 8
    for i in items:
        expected = f"/venues/{slug}/dishes/{i['key']}.webp" if i["featured"] else None
        assert i.get("image_url") == expected, i["key"]
