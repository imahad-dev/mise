#!/usr/bin/env python3
"""Smoke test against the real AMD Token Factory API.

Reads from environment:
  LLM_API_KEY      – Bearer token (whitespace stripped, NEVER printed)
  LLM_BASE_URL     – e.g. https://developer.amd.com.cn/radeon/api/v1
  LLM_MODEL        – e.g. DeepSeek-V4-Flash
  VLM_MODEL        – e.g. DeepSeek-V4.1-Flash

Prints: available model ids, latency, x-ratelimit-* headers, usage.cost,
one JSON chat call result, and one image (VLM) call result.
"""

from __future__ import annotations

import base64
import os
import struct
import sys
import time
import zlib

import httpx

# ── Config ──────────────────────────────────────────────────────────
API_KEY = "".join(os.environ.get("LLM_API_KEY", "").split())
BASE_URL = os.environ.get("LLM_BASE_URL", "http://inference:8080/v1").rstrip("/")
LLM_MODEL = os.environ.get("LLM_MODEL", "mock-llm")
VLM_MODEL = os.environ.get("VLM_MODEL", "mock-vlm")

if not API_KEY:
    print("ERROR: LLM_API_KEY is not set", file=sys.stderr)
    sys.exit(1)

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}


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


def main() -> None:
    print("=== AMD Token Factory Smoke Test ===")
    print(f"Base URL: {BASE_URL}")
    print(f"LLM Model: {LLM_MODEL}")
    print(f"VLM Model: {VLM_MODEL}")
    print(f"API Key: {'*' * 8}...{'*' * 4} (redacted)")
    print()

    client = httpx.Client(base_url=BASE_URL, timeout=30.0, headers=HEADERS)

    # ── 1. List models ──────────────────────────────────────────────
    print("── GET /models ──")
    t0 = time.monotonic()
    resp = client.get("/models")
    latency = int((time.monotonic() - t0) * 1000)
    resp.raise_for_status()
    models = resp.json().get("data", [])
    model_ids = [m["id"] for m in models]
    print(f"  Available models ({len(model_ids)}): {model_ids}")
    print(f"  Latency: {latency} ms")
    _print_ratelimit_headers(resp)
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
