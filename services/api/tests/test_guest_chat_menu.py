"""The chat lists only dishes the menu would let a guest order."""

from decimal import Decimal

from tests.test_choices_rules import choice, dish, group

from src.models.menu import MenuTranslation
from src.services.guest_chat import _build_menu_context


def _named(name, *groups):
    item = dish(*groups)
    item.price = Decimal("3.00")
    item.available = True
    item.is_vegetarian = item.is_vegan = item.is_gluten_free = False
    item.translations = [MenuTranslation(language="en", name=name)]
    return item


def test_chat_skips_a_dish_whose_required_choices_are_sold_out():
    ok = _named("Tea", group("Spice", "pick", 1, 1, choice("Mild")))
    gone = _named("Soup", group("Spice", "pick", 1, 1, choice("Mild", available=False)))
    context = _build_menu_context([ok, gone], "en")
    assert "Tea" in context
    assert "Soup" not in context


def test_chat_says_which_allergens_the_available_choices_may_add():
    milk = choice("Milk", allergens=["milk", "gluten"])
    gone = choice("Nuts", allergens=["nuts"], available=False)
    tea = _named("Tea", group("Extras", "add", 0, 2, milk, gone, choice("Plain")))
    tea.allergens = ["gluten"]
    context = _build_menu_context([tea], "en")
    assert "allergens: gluten, choices may add: milk" in context
    assert "nuts" not in context


def test_chat_omits_the_note_when_no_choice_adds_an_allergen():
    tea = _named("Tea", group("Extras", "add", 0, 1, choice("Plain")))
    context = _build_menu_context([tea], "en")
    assert "choices may add" not in context
