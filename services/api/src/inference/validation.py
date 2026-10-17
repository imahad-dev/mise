"""Validate and extract structured JSON from LLM responses.

Strategy:
1. Parse content as JSON → validate with Pydantic model (if provided)
2. If JSON parse fails → regex fallback to find JSON object in text
3. If validation fails → return raw dict with _validation_error flag
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# Matches the first {...} block in text (greedy, handles nested braces)
_JSON_OBJECT_RE = re.compile(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", re.DOTALL)


def extract_content(response_body: dict[str, Any]) -> str:
    """Extract the assistant's text content from an OpenAI-style response."""
    try:
        return response_body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError(f"Malformed response structure: {exc}") from exc


def parse_json_content(content: str) -> dict[str, Any]:
    """Parse JSON from content string with regex fallback.

    Returns the parsed dict or raises ValueError if no valid JSON found.
    """
    # Attempt 1: direct parse
    try:
        result = json.loads(content)
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError:
        pass

    # Attempt 2: regex fallback — find first JSON object in text
    match = _JSON_OBJECT_RE.search(content)
    if match:
        try:
            result = json.loads(match.group())
            if isinstance(result, dict):
                logger.info("JSON extracted via regex fallback")
                return result
        except json.JSONDecodeError:
            pass

    raise ValueError(f"No valid JSON object found in response: {content[:200]}")


def validate_response(
    response_body: dict[str, Any],
    schema: type[T] | None = None,
) -> T | dict[str, Any]:
    """Extract, parse, and optionally validate a structured LLM response.

    Returns:
        Pydantic model instance if schema is provided and validation passes,
        otherwise returns the raw parsed dict.
    """
    content = extract_content(response_body)
    parsed = parse_json_content(content)

    if schema is None:
        return parsed

    try:
        return schema.model_validate(parsed)
    except ValidationError as exc:
        logger.warning(
            "Pydantic validation failed for %s: %s — returning raw dict",
            schema.__name__,
            exc.error_count(),
        )
        parsed["_validation_error"] = str(exc)
        return parsed
