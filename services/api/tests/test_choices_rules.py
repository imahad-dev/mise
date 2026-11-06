"""Choice rules: resolving picks, availability, allergens, save checks."""

import uuid
from decimal import Decimal

import pytest
from fastapi import HTTPException

from src.models.menu import MenuChoice, MenuChoiceGroup, MenuItem
from src.services.choices import (
    can_be_ordered,
    check_choice,
    check_label,
    line_allergens,
    resolve_choices,
    snapshot_choices,
)


def choice(label, price="0", allergens=(), verified=True, available=True, default=False):
    return MenuChoice(
        id=uuid.uuid4(),
        label=label,
        price_delta=Decimal(price),
        cost_delta=Decimal("0"),
        allergens=list(allergens),
        allergen_verified=verified,
        available=available,
        is_default=default,
    )


def group(label, kind, lo, hi, *choices):
    return MenuChoiceGroup(
        id=uuid.uuid4(), label=label, kind=kind, min_select=lo, max_select=hi, choices=list(choices)
    )


def dish(*groups, allergens=(), verified=True):
    return MenuItem(
        id=uuid.uuid4(),
        allergens=list(allergens),
        allergen_verified=verified,
        choice_groups=list(groups),
    )


def error(exc):
    return exc.value.status_code, exc.value.detail


def test_resolve_keeps_only_this_dishes_choices():
    mild = choice("Mild")
    item = dish(group("Spice", "pick", 1, 1, mild))
    assert resolve_choices(item, [mild.id]) == [mild]
    with pytest.raises(HTTPException) as e:
        resolve_choices(item, [mild.id, uuid.uuid4()])
    assert e.value.status_code == 422


def test_sold_out_choice_is_409_naming_it():
    milk = choice("Extra milk", available=False)
    item = dish(group("Extras", "add", 0, 2, milk))
    with pytest.raises(HTTPException) as e:
        resolve_choices(item, [milk.id])
    code, detail = error(e)
    assert code == 409
    assert detail["error"] == "unavailable_choices"
    assert detail["unavailable_choices"][0]["label"] == "Extra milk"


@pytest.mark.parametrize("picked", [0, 2])
def test_wrong_count_is_choices_changed(picked):
    a, b = choice("Mild"), choice("Hot")
    item = dish(group("Spice", "pick", 1, 1, a, b))
    with pytest.raises(HTTPException) as e:
        resolve_choices(item, [a.id, b.id][:picked])
    code, detail = error(e)
    assert code == 422
    assert detail["error"] == "choices_changed"
    assert detail["menu_item_id"] == str(item.id)


def test_required_group_with_nothing_left_stops_the_dish():
    assert not can_be_ordered(dish(group("Spice", "pick", 1, 1, choice("Mild", available=False))))
    assert can_be_ordered(dish(group("Extras", "add", 0, 1, choice("Milk", available=False))))
    assert can_be_ordered(dish())


def test_a_choice_adds_allergens():
    milk = choice("Extra milk", allergens=["milk"])
    item = dish(group("Extras", "add", 0, 1, milk), allergens=["gluten"])
    allergens, verified = line_allergens(item, [milk])
    assert sorted(allergens) == ["gluten", "milk"]
    assert verified is True


def test_an_unconfirmed_choice_makes_the_line_unverified():
    honey = choice("Honey", verified=False)
    item = dish(group("Extras", "add", 0, 1, honey))
    assert line_allergens(item, [honey])[1] is False


def test_leave_out_never_removes_an_allergen():
    nuts = choice("Nuts")
    item = dish(group("Leave out", "leave_out", 0, 1, nuts), allergens=["tree_nuts"])
    assert line_allergens(item, [nuts]) == (["tree_nuts"], True)


def test_snapshot_keeps_group_kind_and_money_as_strings():
    milk = choice("Extra milk", "0.50", ["milk"])
    item = dish(group("Extras", "add", 0, 1, milk))
    assert snapshot_choices(item, [milk]) == [
        {
            "choice_id": str(milk.id),
            "group": "Extras",
            "kind": "add",
            "label": "Extra milk",
            "price_delta": "0.50",
            "cost_delta": "0",
            "allergens": ["milk"],
        }
    ]


@pytest.mark.parametrize(
    "label", ["Nut free", "Sugar-free", "ALLERGY safe", "allergen check", "Safe for kids"]
)
def test_labels_cannot_promise_safety(label):
    with pytest.raises(HTTPException) as e:
        check_label(label)
    assert e.value.status_code == 422


@pytest.mark.parametrize("label", ["No sugar", "Saffron", "Freekeh", "Extra milk"])
def test_ordinary_labels_pass(label):
    check_label(label)


def test_leave_out_choices_are_free_and_carry_no_allergens():
    for bad in (
        {"price_delta": Decimal("1")},
        {"cost_delta": Decimal("1")},
        {"allergens": ["milk"]},
    ):
        fields = {"price_delta": Decimal("0"), "cost_delta": Decimal("0"), "allergens": [], **bad}
        with pytest.raises(HTTPException):
            check_choice("leave_out", **fields)
    check_choice("add", price_delta=Decimal("1"), cost_delta=Decimal("1"), allergens=["milk"])
