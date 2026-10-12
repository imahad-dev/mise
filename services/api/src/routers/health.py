"""Health check and debug SSE endpoints."""

import asyncio
from collections.abc import AsyncGenerator

from fastapi import APIRouter
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import text

from src.database import async_session_factory
from src.redis_client import check_redis

router = APIRouter()


@router.get("/health")
async def health_check() -> JSONResponse:
    """Check database and Redis connectivity."""
    db_ok = False
    redis_ok = False

    try:
        async with async_session_factory() as session:
            await session.execute(text("SELECT 1"))
            db_ok = True
    except Exception:
        pass

    redis_ok = await check_redis()

    status = "ok" if (db_ok and redis_ok) else "degraded"
    code = 200 if status == "ok" else 503

    return JSONResponse(
        status_code=code,
        content={
            "status": status,
            "db": "ok" if db_ok else "error",
            "redis": "ok" if redis_ok else "error",
        },
    )


async def _debug_sse_generator() -> AsyncGenerator[str, None]:
    """Stream a counter every second — tests that the proxy doesn't buffer SSE."""
    counter = 0
    while True:
        yield f'data: {{"count": {counter}, "msg": "debug heartbeat"}}\n\n'
        counter += 1
        await asyncio.sleep(1)


@router.get("/debug/sse")
async def debug_sse() -> StreamingResponse:
    """Debug SSE endpoint — streams a counter to test proxy streaming."""
    return StreamingResponse(
        _debug_sse_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
