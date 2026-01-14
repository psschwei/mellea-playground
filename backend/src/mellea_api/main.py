"""Main FastAPI application entry point."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from mellea_api.core.config import get_settings
from mellea_api.core.telemetry import setup_telemetry
from mellea_api.routes import (
    assets_router,
    auth_router,
    controller_router,
    credentials_router,
    health_router,
    runs_router,
)
from mellea_api.services.auth import get_auth_service
from mellea_api.services.idle_timeout import get_idle_timeout_controller
from mellea_api.services.warmup import get_warmup_controller

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan manager for startup and shutdown events."""
    settings = get_settings()
    idle_controller = get_idle_timeout_controller()
    warmup_controller = get_warmup_controller()

    # Startup
    logger.info(f"Starting {settings.app_name} in {settings.environment} mode")

    # Ensure data directories exist
    settings.ensure_data_dirs()
    logger.info(f"Data directory: {settings.data_dir}")

    # Seed default users in development mode
    if settings.environment == "development":
        auth_service = get_auth_service()
        auth_service.seed_default_users()
        logger.info("Default users seeded")

    # Start background controllers
    await idle_controller.start()
    await warmup_controller.start()

    yield

    # Shutdown
    logger.info("Shutting down...")

    # Stop background controllers
    await warmup_controller.stop()
    await idle_controller.stop()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        description="Backend API for Mellea Playground - orchestrate and run LLM programs",
        version="0.1.0",
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
        lifespan=lifespan,
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"] if settings.debug else [],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Setup OpenTelemetry
    setup_telemetry(app, settings)

    # Include routers
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(assets_router)
    app.include_router(credentials_router)
    app.include_router(runs_router)
    app.include_router(controller_router)

    return app


# Create app instance
app = create_app()


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "mellea_api.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
