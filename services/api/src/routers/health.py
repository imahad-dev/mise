"""Health check and debug SSE endpoints."""

import asyncio
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy import text

from src.config import settings
from src.database import async_session_factory
from src.redis_client import check_redis
from src.schemas.health import HealthResponse

router = APIRouter()


@router.get(
    "/health",
    response_model=HealthResponse,
    responses={503: {"model": HealthResponse}},
)
async def health_check(response: Response) -> HealthResponse:
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
    is_healthy = db_ok and redis_ok

    if not is_healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return HealthResponse(
        status="ok" if is_healthy else "degraded",
        db="ok" if db_ok else "error",
        redis="ok" if redis_ok else "error",
    )


async def _debug_sse_generator() -> AsyncGenerator[str, None]:
    """Stream a counter every 15 seconds — tests that the proxy doesn't buffer SSE."""
    counter = 0
    try:
        while True:
            yield f'data: {{"count": {counter}, "msg": "debug heartbeat"}}\n\n'
            counter += 1
            await asyncio.sleep(15)
    except asyncio.CancelledError:
        raise
    finally:
        pass


# Register debug SSE endpoint ONLY when APP_ENV=dev
if settings.app_env == "dev":

    @router.get("/debug/sse")
    async def debug_sse() -> StreamingResponse:
        """Debug SSE endpoint — streams counter to test proxy streaming (dev only)."""
        return StreamingResponse(
            _debug_sse_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
