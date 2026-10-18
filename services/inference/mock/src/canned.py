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

GUEST_CHAT = {
    "reply": "The Margherita Pizza is a great choice! It's vegetarian and made with fresh mozzarella and basil. Would you like to add it to your order?",
    "suggested_items": [
        {"name": "Margherita Pizza", "reason": "Matches your preferences"},
        {"name": "Bruschetta", "reason": "Popular starter"},
    ],
}

MENU_INGEST = {
    "items": [
        {
            "name": "Margherita Pizza",
            "description": "Classic pizza with tomato, mozzarella and fresh basil",
            "category": "primi",
            "price": 12.00,
            "unit_cost": 3.50,
            "ingredients": ["flour", "tomato", "mozzarella", "basil", "olive oil"],
            "allergens": ["gluten", "milk"],
            "is_vegetarian": True,
            "is_vegan": False,
            "is_gluten_free": False,
        }
    ],
}

SIMULATE = {
    "scenario": "weekend_rush",
    "predicted_covers": 85,
    "predicted_revenue_eur": 2550.00,
    "recommendations": [
        {"action": "increase_prep", "item": "Tiramisu", "quantity": 20},
        {"action": "staff_up", "shift": "evening", "extra_staff": 1},
    ],
}


def get_canned_response(model: str, messages: list | None = None) -> dict:
    """Return a canned response based on model name and message content.

    Routes by inspecting the system prompt or last user message for keywords.
    """
    # Check message content for more specific routing
    if messages:
        all_text = " ".join(
            m.get("content", "") if isinstance(m.get("content"), str) else "" for m in messages
        ).lower()

        if "chat" in all_text or "recommend" in all_text or "suggest" in all_text:
            return GUEST_CHAT
        if "ingest" in all_text or "menu photo" in all_text or "analyze" in all_text:
            return MENU_INGEST
        if "simulate" in all_text or "forecast" in all_text:
            return SIMULATE
        if "brief" in all_text or "daily" in all_text:
            return DAILY_BRIEF

    # Fallback: route by model name
    if "vlm" in model or "vision" in model:
        return MENU_ANALYSIS
    if "translate" in model:
        return TRANSLATION
    return DAILY_BRIEF
