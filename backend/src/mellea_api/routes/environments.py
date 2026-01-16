"""Environment routes for managing environment lifecycle."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from mellea_api.core.deps import CurrentUser
from mellea_api.models.common import EnvironmentStatus
from mellea_api.models.environment import Environment, ResourceLimits
from mellea_api.services.environment import (
    EnvironmentNotFoundError,
    EnvironmentService,
    InvalidStateTransitionError,
    get_environment_service,
)
from mellea_api.services.warmup import WarmupService, get_warmup_service

logger = logging.getLogger(__name__)

EnvironmentServiceDep = Annotated[EnvironmentService, Depends(get_environment_service)]
WarmupServiceDep = Annotated[WarmupService, Depends(get_warmup_service)]

router = APIRouter(prefix="/api/v1/environments", tags=["environments"])


# -----------------------------------------------------------------------------
# Request/Response Models
# -----------------------------------------------------------------------------


class CreateEnvironmentRequest(BaseModel):
    """Request body for creating a new environment."""

    program_id: str = Field(alias="programId", description="ID of the program")
    image_tag: str = Field(alias="imageTag", description="Docker image tag")
    resource_limits: ResourceLimits | None = Field(
        default=None,
        alias="resourceLimits",
        description="Optional resource constraints",
    )

    class Config:
        populate_by_name = True


class EnvironmentResponse(BaseModel):
    """Response wrapper for environment operations."""

    environment: Environment


class EnvironmentsListResponse(BaseModel):
    """Response for list environments operation."""

    environments: list[Environment]
    total: int


class EnvironmentStatsResponse(BaseModel):
    """Response for environment statistics."""

    total: int
    by_status: dict[str, int] = Field(alias="byStatus")
    warm_pool_size: int = Field(alias="warmPoolSize")
    warm_pool_target: int = Field(alias="warmPoolTarget")

    class Config:
        populate_by_name = True


class WarmPoolStatusResponse(BaseModel):
    """Response for warm pool status."""

    enabled: bool
    target_pool_size: int = Field(alias="targetPoolSize")
    current_pool_size: int = Field(alias="currentPoolSize")
    stale_count: int = Field(alias="staleCount")
    popular_dependencies_count: int = Field(alias="popularDependenciesCount")
    warm_environments: list[dict] = Field(alias="warmEnvironments")
    thresholds: dict[str, int | float]

    class Config:
        populate_by_name = True


class BulkDeleteRequest(BaseModel):
    """Request body for bulk delete operation."""

    environment_ids: list[str] = Field(
        alias="environmentIds", description="List of environment IDs to delete"
    )

    class Config:
        populate_by_name = True


class BulkDeleteResponse(BaseModel):
    """Response for bulk delete operation."""

    results: dict[str, bool | str] = Field(
        description="Map of env_id to result (True for success, error message for failure)"
    )
    deleted_count: int = Field(alias="deletedCount")
    failed_count: int = Field(alias="failedCount")

    class Config:
        populate_by_name = True


# -----------------------------------------------------------------------------
# CRUD Endpoints
# -----------------------------------------------------------------------------


@router.get("", response_model=EnvironmentsListResponse)
async def list_environments(
    current_user: CurrentUser,
    env_service: EnvironmentServiceDep,
    program_id: str | None = Query(None, alias="programId", description="Filter by program ID"),
    env_status: EnvironmentStatus | None = Query(None, alias="status", description="Filter by status"),
) -> EnvironmentsListResponse:
    """List environments with optional filters.

    Supports filtering by:
    - programId: Filter by program ID
    - status: Filter by environment status

    Returns environments visible to the authenticated user.
    """
    environments = env_service.list_environments(
        program_id=program_id,
        status=env_status,
    )

    return EnvironmentsListResponse(environments=environments, total=len(environments))


@router.post("", response_model=EnvironmentResponse, status_code=status.HTTP_201_CREATED)
async def create_environment(
    request: CreateEnvironmentRequest,
    current_user: CurrentUser,
    env_service: EnvironmentServiceDep,
) -> EnvironmentResponse:
    """Create a new environment.

    Creates an environment in CREATING status. The caller must then mark it
    as READY once the image is verified, or FAILED if there's an issue.
    """
    environment = env_service.create_environment(
        program_id=request.program_id,
        image_tag=request.image_tag,
        resource_limits=request.resource_limits,
    )

    return EnvironmentResponse(environment=environment)


@router.get("/stats", response_model=EnvironmentStatsResponse)
async def get_environment_stats(
    current_user: CurrentUser,
    env_service: EnvironmentServiceDep,
    warmup_service: WarmupServiceDep,
) -> EnvironmentStatsResponse:
    """Get environment statistics.

    Returns aggregate statistics about environments including counts by status
    and warm pool information.
    """
    environments = env_service.list_environments()

    # Count by status
    by_status: dict[str, int] = {}
    for env in environments:
        status_value = env.status.value
        by_status[status_value] = by_status.get(status_value, 0) + 1

    pool_status = warmup_service.get_pool_status()

    return EnvironmentStatsResponse(
        total=len(environments),
        byStatus=by_status,
        warmPoolSize=pool_status["current_pool_size"],
        warmPoolTarget=pool_status["target_pool_size"],
    )


@router.get("/warm-pool", response_model=WarmPoolStatusResponse)
async def get_warm_pool_status(
    current_user: CurrentUser,
    warmup_service: WarmupServiceDep,
) -> WarmPoolStatusResponse:
    """Get warm pool status.

    Returns detailed information about the environment warmup pool including
    currently warm environments and configuration thresholds.
    """
    pool_status = warmup_service.get_pool_status()

    return WarmPoolStatusResponse(
        enabled=pool_status["enabled"],
        targetPoolSize=pool_status["target_pool_size"],
        currentPoolSize=pool_status["current_pool_size"],
        staleCount=pool_status["stale_count"],
        popularDependenciesCount=pool_status["popular_dependencies_count"],
        warmEnvironments=pool_status["warm_environments"],
        thresholds=pool_status["thresholds"],
    )


@router.get("/{env_id}", response_model=EnvironmentResponse)
async def get_environment(
    env_id: str,
    current_user: CurrentUser,
    env_service: EnvironmentServiceDep,
) -> EnvironmentResponse:
    """Get an environment by ID.

    Returns the environment details including current status, timestamps,
    and any error information.
    """
    environment = env_service.get_environment(env_id)
    if environment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Environment not found: {env_id}",
        )

    return EnvironmentResponse(environment=environment)


@router.delete("/{env_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_environment(
    env_id: str,
    current_user: CurrentUser,
    env_service: EnvironmentServiceDep,
) -> None:
    """Delete an environment by ID.

    Only environments in READY, STOPPED, or FAILED status can be deleted.
    Running environments must be stopped first.
    """
    try:
        env_service.delete_environment(env_id)
    except EnvironmentNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Environment not found: {env_id}",
        ) from e
    except InvalidStateTransitionError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e


@router.post("/bulk-delete", response_model=BulkDeleteResponse)
async def bulk_delete_environments(
    request: BulkDeleteRequest,
    current_user: CurrentUser,
    env_service: EnvironmentServiceDep,
) -> BulkDeleteResponse:
    """Delete multiple environments at once.

    Only environments in READY, STOPPED, or FAILED status can be deleted.
    The operation continues even if some deletions fail.
    """
    results: dict[str, bool | str] = {}

    for env_id in request.environment_ids:
        try:
            env_service.delete_environment(env_id)
            results[env_id] = True
        except EnvironmentNotFoundError:
            results[env_id] = f"Not found: {env_id}"
        except InvalidStateTransitionError as e:
            results[env_id] = str(e)
        except Exception as e:
            results[env_id] = f"Error: {e}"

    deleted_count = sum(1 for v in results.values() if v is True)
    failed_count = len(results) - deleted_count

    return BulkDeleteResponse(
        results=results,
        deletedCount=deleted_count,
        failedCount=failed_count,
    )


# -----------------------------------------------------------------------------
# Lifecycle Endpoints
# -----------------------------------------------------------------------------


@router.post("/{env_id}/start", response_model=EnvironmentResponse)
async def start_environment(
    env_id: str,
    current_user: CurrentUser,
    env_service: EnvironmentServiceDep,
) -> EnvironmentResponse:
    """Start an environment.

    Transitions the environment from READY to STARTING status.
    The actual container start is handled by the run executor.

    Can only start environments that are in READY status.
    """
    try:
        environment = env_service.start_environment(env_id)
        return EnvironmentResponse(environment=environment)
    except EnvironmentNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Environment not found: {env_id}",
        ) from e
    except InvalidStateTransitionError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e


@router.post("/{env_id}/stop", response_model=EnvironmentResponse)
async def stop_environment(
    env_id: str,
    current_user: CurrentUser,
    env_service: EnvironmentServiceDep,
) -> EnvironmentResponse:
    """Stop an environment.

    Transitions the environment from RUNNING to STOPPING status.
    The actual container stop is handled by the idle timeout controller
    or explicitly by the system.

    Can only stop environments that are in RUNNING status.
    """
    try:
        environment = env_service.stop_environment(env_id)
        return EnvironmentResponse(environment=environment)
    except EnvironmentNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Environment not found: {env_id}",
        ) from e
    except InvalidStateTransitionError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e


@router.post("/{env_id}/mark-ready", response_model=EnvironmentResponse)
async def mark_environment_ready(
    env_id: str,
    current_user: CurrentUser,
    env_service: EnvironmentServiceDep,
) -> EnvironmentResponse:
    """Mark an environment as ready.

    Transitions the environment from CREATING to READY status.
    This is typically called after the container image has been verified.
    """
    try:
        environment = env_service.mark_ready(env_id)
        return EnvironmentResponse(environment=environment)
    except EnvironmentNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Environment not found: {env_id}",
        ) from e
    except InvalidStateTransitionError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e


class MarkFailedRequest(BaseModel):
    """Request body for marking an environment as failed."""

    error: str = Field(description="Error message describing the failure")


@router.post("/{env_id}/mark-failed", response_model=EnvironmentResponse)
async def mark_environment_failed(
    env_id: str,
    request: MarkFailedRequest,
    current_user: CurrentUser,
    env_service: EnvironmentServiceDep,
) -> EnvironmentResponse:
    """Mark an environment as failed.

    Transitions the environment to FAILED status with an error message.
    Can be called from CREATING, STARTING, or RUNNING states.
    """
    try:
        environment = env_service.mark_failed(env_id, error=request.error)
        return EnvironmentResponse(environment=environment)
    except EnvironmentNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Environment not found: {env_id}",
        ) from e
    except InvalidStateTransitionError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e


# -----------------------------------------------------------------------------
# Warmup Endpoints
# -----------------------------------------------------------------------------


@router.post("/warm-pool/trigger-cycle", status_code=status.HTTP_202_ACCEPTED)
async def trigger_warmup_cycle(
    current_user: CurrentUser,
    warmup_service: WarmupServiceDep,
) -> dict[str, str]:
    """Trigger a warmup cycle manually.

    Runs a warmup cycle that:
    1. Recycles stale warm environments
    2. Creates new warm environments to maintain pool size
    3. Pre-builds popular dependency layers

    The cycle runs asynchronously and returns immediately.
    """
    # Run the cycle (async but we await it for now)
    metrics = await warmup_service.run_warmup_cycle()

    return {
        "status": "completed",
        "message": (
            f"Warmup cycle completed: pool_size={metrics.warm_pool_size}, "
            f"created={metrics.environments_created}, "
            f"recycled={metrics.environments_recycled}"
        ),
    }
