"""Order item snapshot — shared by live order placement and the demo order simulator."""

from decimal import Decimal

from src.models.menu import MenuItem
from src.models.order import OrderItem
from src.services.allergen_service import compute_allergen_status


def snapshot_order_item(
    item: MenuItem,
    quantity: int,
    notes: str | None,
    guest_language: str,
    default_language: str,
    guest_allergens_to_avoid: list[str],
) -> OrderItem:
    """Build an immutable OrderItem snapshot (price, cost, names, allergens) from a menu item.

    `item.translations` must be eager-loaded.
    """
    trans_map = {t.language: t for t in item.translations}
    guest_trans = trans_map.get(guest_language) or trans_map.get(default_language)
    default_trans = trans_map.get(default_language) or next(iter(trans_map.values()), None)

    return OrderItem(
        menu_item_id=item.id,
        quantity=quantity,
        unit_price=item.price,
        unit_cost=item.unit_cost,
        item_name=guest_trans.name if guest_trans else "",
        kitchen_name=default_trans.name if default_trans else "",
        allergens=list(item.allergens),
        allergen_verified=item.allergen_verified,
        allergen_status=compute_allergen_status(
            item_allergens=item.allergens,
            allergen_verified=item.allergen_verified,
            guest_allergens_to_avoid=guest_allergens_to_avoid,
        ),
        notes=notes,
    )


def line_total(item: OrderItem) -> Decimal:
    return item.unit_price * Decimal(item.quantity)
