"""Smoke test for any OpenAI-compatible inference endpoint.

Validates structured JSON output, prints latency and end-to-end output tokens/s.
Supports optional --stream mode for measuring TTFT and decode tokens/s.
Run: docker compose exec -T api python scripts/smoke_inference.py
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time

import httpx


async def run_streaming_test(
    client: httpx.AsyncClient, model: str, prompt: str
) -> None:
    """Run streaming chat completion, reporting TTFT and decode tokens/s."""
    print(f"\n=== Testing /v1/chat/completions (Stream: {model}) ===")
    start = time.monotonic()
    ttft: float | None = None
    chunks_received = 0
    collected_content: list[str] = []

    async with client.stream(
        "POST",
        "/chat/completions",
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 512,
            "stream": True,
        },
    ) as response:
        response.raise_for_status()
        async for line in response.aiter_lines():
            line = line.strip()
            if not line or not line.startswith("data: "):
                continue
            data_str = line[6:]
            if data_str == "[DONE]":
                break
            try:
                data = json.loads(data_str)
                delta = data.get("choices", [{}])[0].get("delta", {})
                content = delta.get("content")
                if content:
                    if ttft is None:
                        ttft = time.monotonic() - start
                    chunks_received += 1
                    collected_content.append(content)
            except json.JSONDecodeError:
                continue

    total_latency = time.monotonic() - start
    full_text = "".join(collected_content)
    decode_tokens = max(1, len(full_text.split()) * 2)

    ttft_ms = (ttft * 1000) if ttft is not None else 0.0
    decode_time = total_latency - (ttft if ttft is not None else 0.0)
    decode_speed = decode_tokens / decode_time if decode_time > 0 else 0.0

    print(f"  Model: {model}")
    print(f"  Time to first token (TTFT): {ttft_ms:.0f} ms")
    print(f"  Decode tokens (approx): {decode_tokens}")
    print(f"  Decode time: {decode_time * 1000:.0f} ms")
    print(f"  Decode tokens/s: {decode_speed:.1f} tokens/s")
    print(f"  Total latency: {total_latency * 1000:.0f} ms")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Inference endpoint smoke tester")
    parser.add_argument(
        "url",
        nargs="?",
        default=os.getenv("LLM_BASE_URL", "http://inference:8080/v1"),
        help="Base URL for inference API",
    )
    parser.add_argument(
        "--stream",
        action="store_true",
        help="Run streaming benchmark measuring TTFT and decode throughput",
    )
    args = parser.parse_args()

    async with httpx.AsyncClient(base_url=args.url, timeout=30) as client:
        # 1. Check /v1/models
        print("=== Testing /v1/models ===")
        resp = await client.get("/models")
        resp.raise_for_status()
        models = resp.json()
        print(f"Available models: {[m['id'] for m in models.get('data', [])]}")

        if args.stream:
            await run_streaming_test(
                client, "mock-llm", "Analyze today's menu performance"
            )
            print("\n[OK] Streaming smoke test passed")
            return

        # 2. Chat completion (LLM)
        print("\n=== Testing /v1/chat/completions (LLM) ===")
        start = time.monotonic()
        resp = await client.post(
            "/chat/completions",
            json={
                "model": "mock-llm",
                "messages": [
                    {"role": "user", "content": "Analyze today's menu performance"}
                ],
                "max_tokens": 512,
            },
        )
        latency = time.monotonic() - start
        resp.raise_for_status()
        body = resp.json()

        content = body["choices"][0]["message"]["content"]
        usage = body.get("usage", {})

        # Validate structured JSON
        try:
            parsed = json.loads(content)
            print(f"  Structured JSON: valid ({len(parsed)} keys)")
        except json.JSONDecodeError:
            print(f"  WARNING: Response is not valid JSON: {content[:100]}")
            sys.exit(1)

        output_tokens = usage.get("completion_tokens", 0)
        e2e_output_speed = output_tokens / latency if latency > 0 else 0.0

        print(f"  Model: {body['model']}")
        print(f"  Prompt tokens: {usage.get('prompt_tokens', 0)}")
        print(f"  Completion tokens: {output_tokens}")
        print(f"  Latency: {latency * 1000:.0f} ms")
        print(f"  end-to-end output tokens/s: {e2e_output_speed:.1f}")

        # 3. Vision completion (VLM)
        print("\n=== Testing /v1/chat/completions (VLM) ===")
        start = time.monotonic()
        resp = await client.post(
            "/chat/completions",
            json={
                "model": "mock-vlm",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "What dish is this?"},
                            {
                                "type": "image_url",
                                "image_url": {"url": "data:image/jpeg;base64,/9j/fake"},
                            },
                        ],
                    }
                ],
                "max_tokens": 256,
            },
        )
        latency = time.monotonic() - start
        resp.raise_for_status()
        body = resp.json()

        content = body["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        usage = body.get("usage", {})
        output_tokens = usage.get("completion_tokens", 0)
        e2e_output_speed = output_tokens / latency if latency > 0 else 0.0

        print(f"  Model: {body['model']}")
        print(f"  Structured JSON: valid ({len(parsed)} keys)")
        print(f"  Latency: {latency * 1000:.0f} ms")
        print(f"  end-to-end output tokens/s: {e2e_output_speed:.1f}")

        print("\n[OK] Smoke test passed")


if __name__ == "__main__":
    asyncio.run(main())
