"""Controller routes for idle timeout and warmup management."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from mellea_api.core.config import get_settings
from mellea_api.services.idle_timeout import get_idle_timeout_service
from mellea_api.services.warmup import get_warmup_service

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


# -------------------------------------------------------------------------
# Warmup Endpoints
# -------------------------------------------------------------------------


class WarmupMetricsResponse(BaseModel):
    """Response model for warmup metrics."""

    timestamp: str
    warm_pool_size: int = Field(alias="warmPoolSize")
    environments_created: int = Field(alias="environmentsCreated")
    environments_recycled: int = Field(alias="environmentsRecycled")
    layers_pre_built: int = Field(alias="layersPreBuilt")
    errors: list[str]
    duration_seconds: float = Field(alias="durationSeconds")

    class Config:
        populate_by_name = True


class WarmupConfigResponse(BaseModel):
    """Response model for warmup configuration."""

    enabled: bool
    interval_seconds: int = Field(alias="intervalSeconds")
    pool_size: int = Field(alias="poolSize")
    max_age_minutes: int = Field(alias="maxAgeMinutes")
    popular_deps_count: int = Field(alias="popularDepsCount")

    class Config:
        populate_by_name = True


@router.get("/warmup/status")
async def get_warmup_status() -> dict:
    """Get current status of the warm pool.

    Returns pool size, warm environments, and configuration thresholds.
    """
    service = get_warmup_service()
    return service.get_pool_status()


@router.post("/warmup/cycle", response_model=WarmupMetricsResponse)
async def trigger_warmup_cycle() -> dict:
    """Manually trigger a warmup cycle.

    Runs the warmup process immediately instead of waiting
    for the next scheduled run. Creates new warm environments
    and recycles stale ones.
    """
    service = get_warmup_service()
    metrics = await service.run_warmup_cycle()

    return {
        "timestamp": metrics.timestamp.isoformat(),
        "warmPoolSize": metrics.warm_pool_size,
        "environmentsCreated": metrics.environments_created,
        "environmentsRecycled": metrics.environments_recycled,
        "layersPreBuilt": metrics.layers_pre_built,
        "errors": metrics.errors,
        "durationSeconds": metrics.duration_seconds,
    }


@router.get("/warmup/metrics", response_model=WarmupMetricsResponse | None)
async def get_warmup_metrics() -> dict | None:
    """Get metrics from the last warmup cycle.

    Returns metrics from the most recent warmup run, or null if
    no warmup has run yet.
    """
    service = get_warmup_service()
    metrics = service.get_last_metrics()

    if metrics is None:
        return None

    return {
        "timestamp": metrics.timestamp.isoformat(),
        "warmPoolSize": metrics.warm_pool_size,
        "environmentsCreated": metrics.environments_created,
        "environmentsRecycled": metrics.environments_recycled,
        "layersPreBuilt": metrics.layers_pre_built,
        "errors": metrics.errors,
        "durationSeconds": metrics.duration_seconds,
    }


@router.get("/warmup/config", response_model=WarmupConfigResponse)
async def get_warmup_config() -> dict:
    """Get current warmup configuration.

    Returns the current warmup pool settings and thresholds.
    """
    settings = get_settings()

    return {
        "enabled": settings.warmup_enabled,
        "intervalSeconds": settings.warmup_interval_seconds,
        "poolSize": settings.warmup_pool_size,
        "maxAgeMinutes": settings.warmup_max_age_minutes,
        "popularDepsCount": settings.warmup_popular_deps_count,
    }


@router.get("/warmup/popular-deps")
async def get_popular_dependencies() -> dict:
    """Get the most popular dependency sets.

    Returns dependency layers sorted by usage count, which are
    candidates for pre-building.
    """
    service = get_warmup_service()
    popular = service.get_popular_dependencies()

    return {
        "count": len(popular),
        "dependencies": [
            {
                "cacheKey": dep.cache_key,
                "imageTag": dep.image_tag,
                "useCount": dep.use_count,
                "lastUsedAt": dep.last_used_at.isoformat(),
            }
            for dep in popular
        ],
    }


@router.post("/warmup/create/{program_id}")
async def create_warm_environment(program_id: str) -> dict:
    """Manually create a warm environment for a specific program.

    Args:
        program_id: ID of the program to create warm environment for

    Returns:
        Created environment details or error
    """
    service = get_warmup_service()
    env = service.create_warm_environment(program_id)

    if env is None:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to create warm environment for program {program_id}",
        )

    return {
        "success": True,
        "environment": {
            "id": env.id,
            "programId": env.program_id,
            "imageTag": env.image_tag,
            "status": env.status.value,
            "createdAt": env.created_at.isoformat(),
        },
    }
