"""Smoke test for any OpenAI-compatible inference endpoint.

Validates structured JSON output, prints tokens/s and latency.
Run: docker compose exec -T api python scripts/smoke_inference.py
"""

import asyncio
import json
import os
import sys
import time

import httpx


async def main() -> None:
    base_url = (
        sys.argv[1]
        if len(sys.argv) > 1
        else os.getenv("LLM_BASE_URL", "http://inference:8080/v1")
    )

    async with httpx.AsyncClient(base_url=base_url, timeout=30) as client:
        # 1. Check /v1/models
        print("=== Testing /v1/models ===")
        resp = await client.get("/models")
        resp.raise_for_status()
        models = resp.json()
        print(f"Available models: {[m['id'] for m in models['data']]}")

        # 2. Chat completion
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
        usage = body["usage"]

        # Validate structured JSON
        try:
            parsed = json.loads(content)
            print(f"  Structured JSON: valid ({len(parsed)} keys)")
        except json.JSONDecodeError:
            print(f"  WARNING: Response is not valid JSON: {content[:100]}")
            sys.exit(1)

        tokens_total = usage["total_tokens"]
        tokens_per_sec = tokens_total / latency if latency > 0 else 0

        print(f"  Model: {body['model']}")
        print(f"  Prompt tokens: {usage['prompt_tokens']}")
        print(f"  Completion tokens: {usage['completion_tokens']}")
        print(f"  Latency: {latency * 1000:.0f} ms")
        print(f"  Throughput: {tokens_per_sec:.1f} tokens/s")

        # 3. Vision completion
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
        usage = body["usage"]
        tokens_per_sec = usage["total_tokens"] / latency if latency > 0 else 0

        print(f"  Model: {body['model']}")
        print(f"  Structured JSON: valid ({len(parsed)} keys)")
        print(f"  Latency: {latency * 1000:.0f} ms")
        print(f"  Throughput: {tokens_per_sec:.1f} tokens/s")

        print("\n[OK] Smoke test passed")


if __name__ == "__main__":
    asyncio.run(main())
