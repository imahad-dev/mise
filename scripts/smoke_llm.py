#!/usr/bin/env python3
"""Smoke test against any OpenAI-compatible inference endpoint.

Reads from environment:
  LLM_API_KEY      – Bearer token (whitespace stripped, NEVER printed)
  LLM_BASE_URL     – OpenAI-compatible base URL (default: http://inference:8080/v1)
  LLM_MODEL        – e.g. mock-llm or llama-3.3-70b-versatile
  VLM_MODEL        – e.g. mock-vlm or llama-3.2-11b-vision-preview
  LLM_PRESET       – gemini | groq | openrouter | ollama | custom
  LLM_GLOBAL_RPM   – RPM limit
  LLM_DAILY_REQUEST_CAP – Daily request ceiling

Prints: preset, effective limits, daily cap remaining, available model ids,
latency, x-ratelimit-* headers, usage.cost, one JSON chat call result, and
one image (VLM) call result.
"""

from __future__ import annotations

import base64
import os
import struct
import time
import zlib
from datetime import UTC, datetime

import httpx

# ── Config ──────────────────────────────────────────────────────────
API_KEY = "".join(os.environ.get("LLM_API_KEY", "").split())
BASE_URL = os.environ.get("LLM_BASE_URL", "http://inference:8080/v1").rstrip("/")
LLM_MODEL = os.environ.get("LLM_MODEL", "mock-llm")
VLM_MODEL = os.environ.get("VLM_MODEL", "mock-vlm")
LLM_PRESET = os.environ.get("LLM_PRESET", "custom")
LLM_GLOBAL_RPM = os.environ.get("LLM_GLOBAL_RPM", "15")
LLM_CONCURRENCY_LIMIT = os.environ.get("LLM_CONCURRENCY_LIMIT", "6")
LLM_DAILY_REQUEST_CAP = int(os.environ.get("LLM_DAILY_REQUEST_CAP", "200"))
REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")

HEADERS: dict[str, str] = {
    "Content-Type": "application/json",
}
if API_KEY:
    HEADERS["Authorization"] = f"Bearer {API_KEY}"


def _make_tiny_png() -> bytes:
    """Generate a 1x1 red PNG entirely in-memory (no PIL needed)."""

    def _chunk(chunk_type: bytes, data: bytes) -> bytes:
        c = chunk_type + data
        return (
            struct.pack(">I", len(data))
            + c
            + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)
        )

    header = b"\x89PNG\r\n\x1a\n"
    ihdr = _chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    raw = b"\x00\xff\x00\x00"  # filter-byte + R G B
    idat = _chunk(b"IDAT", zlib.compress(raw))
    iend = _chunk(b"IEND", b"")
    return header + ihdr + idat + iend


def _print_ratelimit_headers(resp: httpx.Response) -> None:
    """Print all x-ratelimit-* headers."""
    for key, val in resp.headers.items():
        if key.lower().startswith("x-ratelimit"):
            print(f"  {key}: {val}")


def _get_daily_cap_remaining() -> str:
    """Query Redis for daily cap usage or calculate based on local status."""
    if LLM_PRESET == "ollama" or "localhost" in BASE_URL or "127.0.0.1" in BASE_URL:
        return "unlimited (local endpoint)"
    try:
        import redis  # sync redis client for cli script

        r = redis.from_url(REDIS_URL, decode_responses=True)
        today_str = datetime.now(UTC).strftime("%Y-%m-%d")
        val = r.get(f"mise:llm:daily_cap:{today_str}")
        count = int(val) if val else 0
        rem = max(0, LLM_DAILY_REQUEST_CAP - count)
        return f"{rem} / {LLM_DAILY_REQUEST_CAP} requests remaining"
    except Exception:  # noqa: BLE001
        return f"Cap: {LLM_DAILY_REQUEST_CAP} (Redis counter not reachable offline)"


def main() -> None:
    print("=== OpenAI-Compatible Inference Smoke Test ===")
    print(f"Preset: {LLM_PRESET}")
    print(
        f"Effective Limits: Global RPM={LLM_GLOBAL_RPM}, Concurrency={LLM_CONCURRENCY_LIMIT}"
    )
    print(f"Daily Cap Remaining: {_get_daily_cap_remaining()}")
    print(f"Base URL: {BASE_URL}")
    print(f"LLM Model: {LLM_MODEL}")
    print(f"VLM Model: {VLM_MODEL}")
    masked_key = f"{'*' * 8}...{'*' * 4} (redacted)" if API_KEY else "(none configured)"
    print(f"API Key: {masked_key}")
    print()

    client = httpx.Client(base_url=BASE_URL, timeout=30.0, headers=HEADERS)

    # ── 1. List models ──────────────────────────────────────────────
    print("── GET /models ──")
    t0 = time.monotonic()
    try:
        resp = client.get("/models")
        latency = int((time.monotonic() - t0) * 1000)
        resp.raise_for_status()
        models = resp.json().get("data", [])
        model_ids = [m["id"] for m in models if "id" in m]
        print(f"  Available models ({len(model_ids)}): {model_ids}")
        print(f"  Latency: {latency} ms")
        _print_ratelimit_headers(resp)
    except Exception as exc:  # noqa: BLE001
        print(f"  GET /models failed or not supported: {exc}")
    print()

    # ── 2. JSON chat call (LLM) ─────────────────────────────────────
    print("── POST /chat/completions (LLM, JSON) ──")
    payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": "You are a helpful restaurant assistant."},
            {
                "role": "user",
                "content": "Recommend one Italian pasta dish. Reply as JSON: "
                '{"dish": "...", "reason": "..."}',
            },
        ],
        "max_tokens": 256,
        "temperature": 0.3,
        "response_format": {"type": "json_object"},
    }
    t0 = time.monotonic()
    resp = client.post("/chat/completions", json=payload)
    latency = int((time.monotonic() - t0) * 1000)
    resp.raise_for_status()
    body = resp.json()
    content = body["choices"][0]["message"]["content"]
    usage = body.get("usage", {})
    print(f"  Content: {content[:200]}")
    print(f"  usage.cost: {usage.get('cost', 'N/A')}")
    print(
        f"  Tokens in/out: {usage.get('prompt_tokens')}/{usage.get('completion_tokens')}"
    )
    print(f"  Latency: {latency} ms")
    _print_ratelimit_headers(resp)
    print()

    # ── 3. Image call (VLM) ─────────────────────────────────────────
    print("── POST /chat/completions (VLM, image) ──")
    png_bytes = _make_tiny_png()
    b64_png = base64.b64encode(png_bytes).decode()
    payload = {
        "model": VLM_MODEL,
        "messages": [
            {"role": "system", "content": "Describe the image briefly."},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "What is in this image?"},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{b64_png}"},
                    },
                ],
            },
        ],
        "max_tokens": 128,
    }
    t0 = time.monotonic()
    resp = client.post("/chat/completions", json=payload)
    latency = int((time.monotonic() - t0) * 1000)
    resp.raise_for_status()
    body = resp.json()
    content = body["choices"][0]["message"]["content"]
    usage = body.get("usage", {})
    print(f"  Content: {content[:200]}")
    print(f"  usage.cost: {usage.get('cost', 'N/A')}")
    print(
        f"  Tokens in/out: {usage.get('prompt_tokens')}/{usage.get('completion_tokens')}"
    )
    print(f"  Latency: {latency} ms")
    _print_ratelimit_headers(resp)
    print()

    client.close()
    print("=== SMOKE TEST COMPLETE ===")


if __name__ == "__main__":
    main()
