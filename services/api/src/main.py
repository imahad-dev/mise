"""Mise API — FastAPI application entry point."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from src.config import settings
from src.inference.client import InferenceClient
from src.routers.auth import router as auth_router
from src.routers.guest import router as guest_router
from src.routers.health import router as health_router
from src.routers.kitchen import router as kitchen_router
from src.routers.metrics import router as metrics_router
from src.routers.orders import router as orders_router
from src.routers.owner import router as owner_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Startup: instantiate clients attached to current event loop on app.state
    llm_client = httpx.AsyncClient(
        base_url=settings.llm_base_url,
        timeout=settings.llm_timeout_seconds,
    )
    vlm_client = httpx.AsyncClient(
        base_url=settings.vlm_base_url,
        timeout=settings.llm_timeout_seconds,
    )
    app.state.inference_client = InferenceClient(
        llm_client=llm_client,
        vlm_client=vlm_client,
    )
    try:
        yield
    finally:
        # Shutdown
        await app.state.inference_client.close()


app = FastAPI(
    title="Mise API",
    version="0.1.0",
    description="Revenue copilot for independent restaurants",
    lifespan=lifespan,
)

# Mount routers
app.include_router(health_router)
app.include_router(metrics_router)
app.include_router(auth_router)
app.include_router(guest_router)
app.include_router(orders_router)
app.include_router(kitchen_router)
app.include_router(owner_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.app_env == "dev",
    )
