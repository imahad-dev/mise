"""LLM narration with a numbers guard: the model may only restate numbers present in the facts.

Facts contain aggregate business data only (no guest, allergen or personal data). If the
model is unavailable, errors, or writes any number not found in the facts, the caller's
template text is used instead.
"""

from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING, Any

from src.inference.metrics import record_metrics
from src.inference.validation import extract_content, parse_json_content

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from src.inference.client import InferenceClient

logger = logging.getLogger(__name__)

# "1,234.50", "12.5", "7" — thousands separators allowed, sign ignored.
_NUMBER_RE = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?")


def numbers_in_text(text: str) -> list[tuple[float, int]]:
    """Every number in `text` as (value, decimals)."""
    out = []
    for tok in _NUMBER_RE.findall(text):
        tok = tok.replace(",", "")
        decimals = len(tok.split(".")[1]) if "." in tok else 0
        out.append((float(tok), decimals))
    return out


def numbers_in_facts(facts: Any) -> list[float]:
    """Every number in a JSON-like structure, including numbers inside strings."""
    if isinstance(facts, bool) or facts is None:
        return []
    if isinstance(facts, int | float):
        return [abs(float(facts))]
    if isinstance(facts, str):
        return [v for v, _ in numbers_in_text(facts)]
    if isinstance(facts, dict):
        return [n for v in facts.values() for n in numbers_in_facts(v)]
    if isinstance(facts, list | tuple):
        return [n for v in facts for n in numbers_in_facts(v)]
    return []


def numbers_grounded(text: str, facts: Any) -> bool:
    """True when every number in `text` equals a fact rounded to the text's precision."""
    allowed = numbers_in_facts(facts)
    return all(any(round(f, d) == v for f in allowed) for v, d in numbers_in_text(text))


async def narrate(
    inference: InferenceClient | None,
    db: AsyncSession,
    facts: dict,
    template: str,
    task: str,
) -> tuple[str, str]:
    """Return (text, source) where source is 'llm' or 'template'."""
    if inference is None:
        return template, "template"
    messages = [
        {
            "role": "system",
            "content": (
                f"You write the {task} for a restaurant owner in plain English, 2-4 sentences. "
                "Use only the facts in the user's JSON. Do not compute, estimate or invent "
                "any number; only repeat numbers exactly as written in the facts. "
                'Return JSON: {"summary": "<text>"}.'
            ),
        },
        {"role": "user", "content": json.dumps(facts, default=str)},
    ]
    try:
        body, metrics = await inference.chat(messages, response_format={"type": "json_object"})
        await record_metrics(db, metrics)
        text = parse_json_content(extract_content(body)).get("summary")
    except Exception as exc:  # LLM down, capped, rate-limited or malformed: use the template
        logger.info("Narration unavailable, using template: %s", type(exc).__name__)
        return template, "template"
    if not isinstance(text, str) or not text.strip():
        return template, "template"
    if not numbers_grounded(text, facts):
        logger.info("Narration rejected: contains numbers not present in the facts")
        return template, "template"
    return text.strip(), "llm"
