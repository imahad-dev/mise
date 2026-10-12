"""Canned responses for the mock inference server."""

MENU_ANALYSIS = {
    "dish": "Margherita Pizza",
    "category": "primi",
    "allergens": ["gluten", "milk"],
    "is_vegetarian": True,
    "is_vegan": False,
    "is_gluten_free": False,
    "estimated_cost_eur": 3.50,
    "suggested_price_eur": 12.00,
}

TRANSLATION = {
    "language": "it",
    "name": "Pizza Margherita",
    "description": "Pizza classica con pomodoro, mozzarella e basilico fresco",
}

DAILY_BRIEF = {
    "date": "2026-10-11",
    "summary": "Expected busy Saturday. Consider featuring pasta specials.",
    "actions": [
        {"type": "prep", "item": "Tiramisu", "reason": "High demand predicted"},
        {"type": "promote", "item": "House Wine", "reason": "Low margin, needs push"},
    ],
}


def get_canned_response(model: str) -> dict:
    """Return a canned response based on the model name."""
    if "vlm" in model or "vision" in model:
        return MENU_ANALYSIS
    if "translate" in model:
        return TRANSLATION
    return DAILY_BRIEF
