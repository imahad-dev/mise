"""Every guest-visible menu word has a version in the venue's local language (phase 1b, phase 2)."""

import json
import re

import pytest

SCRIPT = re.compile(r"[؀-ۿ]")
MEASURE = re.compile(r"[\d½¼¾.]+\s*(kg|g|ml|l)?")
CASES = [
    ("data/seed/angeethi_house.json", "ur"),
    ("data/seed/kehwa_and_crumb.json", "ur"),
    ("data/seed/noor_and_zaatar.json", "ar"),
]
URDU_ONLY = re.compile("[کیہھے]")  # keheh, Farsi yeh, heh goal, do-chashmi heh, bari yeh
ARABIC_ONLY = re.compile("[كي]")  # Arabic kaf, Arabic yeh


def _load(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _translated_strings(path: str, lang: str):
    for item in _load(path)["items"]:
        yield from (item["translations"].get(lang) or {}).values()
        for o in item.get("options", []):
            yield o.get("translations", {}).get(lang, "")
        for g in item.get("choice_groups", []):
            yield g.get("translations", {}).get(lang, "")
            for c in g["choices"]:
                yield c.get("translations", {}).get(lang, "")


@pytest.mark.parametrize(("path", "lang"), CASES)
def test_venue_offers_english_and_its_language(path, lang):
    r = _load(path)["restaurant"]
    assert r["languages"] == ["en", lang]
    assert r["default_language"] == "en"


@pytest.mark.parametrize(("path", "lang"), CASES)
def test_every_dish_size_and_choice_has_its_language(path, lang):
    missing = []
    for item in _load(path)["items"]:
        tr = item["translations"].get(lang) or {}
        if not SCRIPT.search(tr.get("name", "")):
            missing.append(f"{item['key']}: name")
        has_en_description = item["translations"]["en"].get("description")
        if has_en_description and not SCRIPT.search(tr.get("description") or ""):
            missing.append(f"{item['key']}: description")
        for o in item.get("options", []):
            label = o.get("translations", {}).get(lang, "")
            if not SCRIPT.search(label) and not MEASURE.fullmatch(o["label"]):
                missing.append(f"{item['key']}: option {o['label']}")
        for g in item.get("choice_groups", []):
            if not SCRIPT.search(g.get("translations", {}).get(lang, "")):
                missing.append(f"{item['key']}: group {g['label']}")
            for c in g["choices"]:
                if not SCRIPT.search(c.get("translations", {}).get(lang, "")):
                    missing.append(f"{item['key']}: choice {c['label']}")
    assert missing == []


@pytest.mark.parametrize(("path", "lang"), CASES)
def test_translation_never_names_the_platform(path, lang):
    assert "Mise" not in json.dumps(_load(path), ensure_ascii=False).replace("_note", "")


@pytest.mark.parametrize(("path", "lang"), CASES)
def test_uses_only_its_own_scripts_letters(path, lang):
    other = URDU_ONLY if lang == "ar" else ARABIC_ONLY
    wrong = [s for s in _translated_strings(path, lang) if other.search(s)]
    assert wrong == []
