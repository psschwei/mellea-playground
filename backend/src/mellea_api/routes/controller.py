"""Controller routes for idle timeout management."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from mellea_api.core.config import get_settings
from mellea_api.services.idle_timeout import get_idle_timeout_service

router = APIRouter(prefix="/api/v1/controller", tags=["Controller"])


class IdleResourceResponse(BaseModel):
    """Response model for an idle resource."""

    id: str
    idle_since: str = Field(alias="idleSince")
    idle_minutes: float = Field(alias="idleMinutes")

    class Config:
        populate_by_name = True


class StaleRunResponse(BaseModel):
    """Response model for a stale run."""

    id: str
    completed_at: str = Field(alias="completedAt")
    age_days: float = Field(alias="ageDays")

    class Config:
        populate_by_name = True


class IdleSummaryResponse(BaseModel):
    """Response model for idle resources summary."""

    idle_environments: dict = Field(alias="idleEnvironments")
    stale_runs: dict = Field(alias="staleRuns")
    thresholds: dict

    class Config:
        populate_by_name = True


class CleanupResultResponse(BaseModel):
    """Response model for cleanup results."""

    success: bool
    resource_type: str = Field(alias="resourceType")
    resource_id: str = Field(alias="resourceId")
    action: str
    error: str | None = None

    class Config:
        populate_by_name = True


class ControllerMetricsResponse(BaseModel):
    """Response model for controller metrics."""

    timestamp: str
    environments_checked: int = Field(alias="environmentsChecked")
    environments_stopped: int = Field(alias="environmentsStopped")
    runs_checked: int = Field(alias="runsChecked")
    runs_deleted: int = Field(alias="runsDeleted")
    jobs_checked: int = Field(alias="jobsChecked")
    jobs_cleaned: int = Field(alias="jobsCleaned")
    errors: list[str]
    duration_seconds: float = Field(alias="durationSeconds")

    class Config:
        populate_by_name = True


class ControllerConfigResponse(BaseModel):
    """Response model for controller configuration."""

    enabled: bool
    interval_seconds: int = Field(alias="intervalSeconds")
    environment_idle_timeout_minutes: int = Field(alias="environmentIdleTimeoutMinutes")
    run_retention_days: int = Field(alias="runRetentionDays")
    stale_job_timeout_minutes: int = Field(alias="staleJobTimeoutMinutes")

    class Config:
        populate_by_name = True


@router.get("/idle", response_model=IdleSummaryResponse)
async def get_idle_resources() -> dict:
    """Get summary of current idle resources.

    Returns a summary of environments and runs that are currently
    considered idle and would be cleaned up in the next cycle.
    """
    service = get_idle_timeout_service()
    return service.get_idle_summary()


@router.post("/cleanup", response_model=ControllerMetricsResponse)
async def trigger_cleanup() -> dict:
    """Manually trigger a cleanup cycle.

    Runs the idle timeout cleanup immediately instead of waiting
    for the next scheduled run. Useful for testing or manual intervention.
    """
    service = get_idle_timeout_service()
    metrics = await service.run_cleanup_cycle()

    return {
        "timestamp": metrics.timestamp.isoformat(),
        "environmentsChecked": metrics.environments_checked,
        "environmentsStopped": metrics.environments_stopped,
        "runsChecked": metrics.runs_checked,
        "runsDeleted": metrics.runs_deleted,
        "jobsChecked": metrics.jobs_checked,
        "jobsCleaned": metrics.jobs_cleaned,
        "errors": metrics.errors,
        "durationSeconds": metrics.duration_seconds,
    }


@router.get("/metrics", response_model=ControllerMetricsResponse | None)
async def get_controller_metrics() -> dict | None:
    """Get metrics from the last cleanup cycle.

    Returns metrics from the most recent cleanup run, or null if
    no cleanup has run yet.
    """
    service = get_idle_timeout_service()
    metrics = service.get_last_metrics()

    if metrics is None:
        return None

    return {
        "timestamp": metrics.timestamp.isoformat(),
        "environmentsChecked": metrics.environments_checked,
        "environmentsStopped": metrics.environments_stopped,
        "runsChecked": metrics.runs_checked,
        "runsDeleted": metrics.runs_deleted,
        "jobsChecked": metrics.jobs_checked,
        "jobsCleaned": metrics.jobs_cleaned,
        "errors": metrics.errors,
        "durationSeconds": metrics.duration_seconds,
    }


@router.get("/config", response_model=ControllerConfigResponse)
async def get_controller_config() -> dict:
    """Get current controller configuration.

    Returns the current timeout thresholds and controller settings.
    """
    settings = get_settings()

    return {
        "enabled": settings.idle_controller_enabled,
        "intervalSeconds": settings.idle_controller_interval_seconds,
        "environmentIdleTimeoutMinutes": settings.environment_idle_timeout_minutes,
        "runRetentionDays": settings.run_retention_days,
        "staleJobTimeoutMinutes": settings.stale_job_timeout_minutes,
    }


@router.post("/stop/{environment_id}", response_model=CleanupResultResponse)
async def stop_environment(environment_id: str) -> dict:
    """Manually stop a specific idle environment.

    Args:
        environment_id: ID of the environment to stop

    Returns:
        Result of the stop operation
    """
    service = get_idle_timeout_service()
    result = service.stop_idle_environment(environment_id)

    if not result.success:
        raise HTTPException(
            status_code=400,
            detail=result.error or "Failed to stop environment",
        )

    return {
        "success": result.success,
        "resourceType": result.resource_type,
        "resourceId": result.resource_id,
        "action": result.action,
        "error": result.error,
    }
