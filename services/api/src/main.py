"""Mise API — FastAPI application entry point."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.config import settings
from src.inference.client import inference_client
from src.routers.health import router as health_router
from src.routers.metrics import router as metrics_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Startup
    yield
    # Shutdown
    await inference_client.close()


app = FastAPI(
    title="Mise API",
    version="0.1.0",
    description="Revenue copilot for independent restaurants",
    lifespan=lifespan,
)

# Mount routers
app.include_router(health_router)
app.include_router(metrics_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.app_env == "dev",
    )
