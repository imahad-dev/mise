"""Every guest-visible menu word at the Pakistani venues has an Urdu version (phase 1b)."""

import json
import re

import pytest

ARABIC_SCRIPT = re.compile(r"[؀-ۿ]")
MEASURE = re.compile(r"[\d½¼¾.]+\s*(kg|g|ml|l)?")
FILES = ["data/seed/angeethi_house.json", "data/seed/kehwa_and_crumb.json"]


def _load(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


@pytest.mark.parametrize("path", FILES)
def test_venue_offers_english_and_urdu(path):
    r = _load(path)["restaurant"]
    assert r["languages"] == ["en", "ur"]
    assert r["default_language"] == "en"


@pytest.mark.parametrize("path", FILES)
def test_every_dish_size_and_choice_has_urdu(path):
    missing = []
    for item in _load(path)["items"]:
        ur = item["translations"].get("ur") or {}
        if not ARABIC_SCRIPT.search(ur.get("name", "")):
            missing.append(f"{item['key']}: name")
        has_en_description = item["translations"]["en"].get("description")
        if has_en_description and not ARABIC_SCRIPT.search(ur.get("description") or ""):
            missing.append(f"{item['key']}: description")
        for o in item.get("options", []):
            ur_label = o.get("translations", {}).get("ur", "")
            if not ARABIC_SCRIPT.search(ur_label) and not MEASURE.fullmatch(o["label"]):
                missing.append(f"{item['key']}: option {o['label']}")
        for g in item.get("choice_groups", []):
            if not ARABIC_SCRIPT.search(g.get("translations", {}).get("ur", "")):
                missing.append(f"{item['key']}: group {g['label']}")
            for c in g["choices"]:
                if not ARABIC_SCRIPT.search(c.get("translations", {}).get("ur", "")):
                    missing.append(f"{item['key']}: choice {c['label']}")
    assert missing == []


@pytest.mark.parametrize("path", FILES)
def test_urdu_never_names_the_platform(path):
    assert "Mise" not in json.dumps(_load(path), ensure_ascii=False).replace("_note", "")
