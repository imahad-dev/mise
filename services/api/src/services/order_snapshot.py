"""Order item snapshot — shared by live order placement and the demo order simulator."""

from collections.abc import Sequence
from decimal import Decimal

from src.models.menu import MenuChoice, MenuItem, MenuItemOption
from src.models.order import OrderItem
from src.services.allergen_service import compute_allergen_status
from src.services.choices import line_allergens, snapshot_choices


def snapshot_order_item(
    item: MenuItem,
    quantity: int,
    notes: str | None,
    guest_language: str,
    default_language: str,
    guest_allergens_to_avoid: list[str],
    option: MenuItemOption | None = None,
    choices: Sequence[MenuChoice] = (),
) -> OrderItem:
    """Build an immutable OrderItem snapshot (price, cost, names, allergens) from a menu item.

    `item.translations` must be eager-loaded.
    """
    trans_map = {t.language: t for t in item.translations}
    guest_trans = trans_map.get(guest_language) or trans_map.get(default_language)
    default_trans = trans_map.get(default_language) or next(iter(trans_map.values()), None)

    chosen = list(choices)
    base_price = option.price if option else item.price
    base_cost = option.unit_cost if option else item.unit_cost
    allergens, verified = line_allergens(item, chosen)

    return OrderItem(
        menu_item_id=item.id,
        quantity=quantity,
        unit_price=base_price + sum((c.price_delta for c in chosen), Decimal("0")),
        unit_cost=base_cost + sum((c.cost_delta for c in chosen), Decimal("0")),
        option_id=option.id if option else None,
        option_label=option.label if option else None,
        choices=snapshot_choices(item, chosen) if chosen else [],
        item_name=guest_trans.name if guest_trans else "",
        kitchen_name=default_trans.name if default_trans else "",
        allergens=allergens,
        allergen_verified=verified,
        allergen_status=compute_allergen_status(
            item_allergens=allergens,
            allergen_verified=verified,
            guest_allergens_to_avoid=guest_allergens_to_avoid,
        ),
        notes=notes,
        is_pay_forward=item.is_pay_forward,
    )


def line_total(item: OrderItem) -> Decimal:
    return item.unit_price * Decimal(item.quantity)
