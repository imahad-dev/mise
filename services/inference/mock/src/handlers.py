"""OpenAI-compatible API handlers for mock inference."""

import asyncio
import json
import os
import random
import time
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.canned import get_canned_response

router = APIRouter()

MOCK_LATENCY_MS = int(os.getenv("MOCK_LATENCY_MS", "100"))
MOCK_ERROR_RATE = float(os.getenv("MOCK_ERROR_RATE", "0.0"))
MOCK_TIMEOUT_MS = int(os.getenv("MOCK_TIMEOUT_MS", "0"))


class Message(BaseModel):
    role: str
    content: str | list | None = None


from fastapi.responses import StreamingResponse


class ChatRequest(BaseModel):
    model: str
    messages: list[Message]
    max_tokens: int = 1024
    temperature: float = 0.7
    response_format: dict | None = None
    stream: bool = False
    stream_options: dict | None = None


@router.post("/v1/chat/completions")
async def chat_completions(request: ChatRequest):
    """Mock /v1/chat/completions — returns canned structured output (or streams chunks)."""
    # Simulate error rate
    if random.random() < MOCK_ERROR_RATE:
        raise HTTPException(status_code=500, detail="Mock inference error (simulated)")

    # Simulate timeout
    if MOCK_TIMEOUT_MS > 0:
        await asyncio.sleep(MOCK_TIMEOUT_MS / 1000)
        raise HTTPException(status_code=504, detail="Mock inference timeout (simulated)")

    # Simulate TTFT / initial latency
    await asyncio.sleep(MOCK_LATENCY_MS / 1000)

    canned = get_canned_response(request.model)
    content = json.dumps(canned)

    # Approximate token counts
    prompt_text = " ".join(
        m.content if isinstance(m.content, str) else str(m.content) for m in request.messages
    )
    prompt_tokens = max(1, len(prompt_text.split()) * 2)
    completion_tokens = max(1, len(content.split()) * 2)
    request_id = f"chatcmpl-mock-{uuid.uuid4().hex[:8]}"

    if request.stream:

        async def event_generator():
            words = content.split(" ")
            for i, word in enumerate(words):
                chunk = word + (" " if i < len(words) - 1 else "")
                data = {
                    "id": request_id,
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": request.model,
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"content": chunk},
                            "finish_reason": None if i < len(words) - 1 else "stop",
                        }
                    ],
                }
                yield f"data: {json.dumps(data)}\n\n"
                await asyncio.sleep(0.01)

            if request.stream_options and request.stream_options.get("include_usage"):
                usage_data = {
                    "id": request_id,
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": request.model,
                    "choices": [],
                    "usage": {
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                        "total_tokens": prompt_tokens + completion_tokens,
                    },
                }
                yield f"data: {json.dumps(usage_data)}\n\n"

            yield "data: [DONE]\n\n"

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    return {
        "id": f"chatcmpl-mock-{uuid.uuid4().hex[:8]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": request.model,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": content,
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }


@router.get("/v1/models")
async def list_models() -> dict:
    """Mock /v1/models — returns available mock models."""
    return {
        "object": "list",
        "data": [
            {
                "id": "mock-llm",
                "object": "model",
                "created": int(time.time()),
                "owned_by": "mise-mock",
            },
            {
                "id": "mock-vlm",
                "object": "model",
                "created": int(time.time()),
                "owned_by": "mise-mock",
            },
        ],
    }
