"""Health check endpoints for Kubernetes probes and monitoring."""

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from mellea_api.core.config import Settings, get_settings

SettingsDep = Annotated[Settings, Depends(get_settings)]

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    timestamp: datetime
    version: str
    environment: str


class ReadinessResponse(BaseModel):
    """Readiness check response with component status."""

    status: str
    timestamp: datetime
    checks: dict[str, Any]


@router.get("/health", response_model=HealthResponse)
async def health_check(settings: SettingsDep) -> HealthResponse:
    """Basic health check for liveness probe.

    Returns minimal information to confirm the service is running.
    """
    return HealthResponse(
        status="healthy",
        timestamp=datetime.utcnow(),
        version="0.1.0",
        environment=settings.environment,
    )


@router.get("/ready", response_model=ReadinessResponse)
async def readiness_check(settings: SettingsDep) -> ReadinessResponse:
    """Readiness check for Kubernetes readiness probe.

    Verifies that all required dependencies are available.
    """
    checks: dict[str, Any] = {}

    # Check data directory exists
    data_dir_ok = settings.data_dir.exists()
    checks["data_directory"] = {
        "status": "ok" if data_dir_ok else "error",
        "path": str(settings.data_dir),
    }

    # Check metadata subdirectories
    metadata_dir = settings.data_dir / "metadata"
    metadata_ok = metadata_dir.exists()
    checks["metadata_directory"] = {
        "status": "ok" if metadata_ok else "error",
        "path": str(metadata_dir),
    }

    # Overall status
    all_ok = all(
        check.get("status") == "ok" for check in checks.values() if isinstance(check, dict)
    )

    return ReadinessResponse(
        status="ready" if all_ok else "not_ready",
        timestamp=datetime.utcnow(),
        checks=checks,
    )


@router.get("/startup")
async def startup_check() -> dict[str, str]:
    """Startup check for Kubernetes startup probe.

    Simple endpoint that returns once the application has started.
    """
    return {"status": "started"}
