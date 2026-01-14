"""Run routes for managing program execution."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from mellea_api.core.deps import CurrentUser
from mellea_api.models.common import RunExecutionStatus
from mellea_api.models.run import Run
from mellea_api.services.assets import AssetService, get_asset_service
from mellea_api.services.credentials import CredentialService, get_credential_service
from mellea_api.services.environment import (
    EnvironmentService,
    get_environment_service,
)
from mellea_api.services.run import (
    InvalidRunStateTransitionError,
    RunNotFoundError,
    RunService,
    get_run_service,
)

RunServiceDep = Annotated[RunService, Depends(get_run_service)]
EnvironmentServiceDep = Annotated[EnvironmentService, Depends(get_environment_service)]
AssetServiceDep = Annotated[AssetService, Depends(get_asset_service)]
CredentialServiceDep = Annotated[CredentialService, Depends(get_credential_service)]

router = APIRouter(prefix="/api/v1/runs", tags=["runs"])


class CreateRunRequest(BaseModel):
    """Request body for creating a new run."""

    program_id: str = Field(alias="programId", description="ID of the program to run")
    credential_ids: list[str] = Field(
        default_factory=list,
        alias="credentialIds",
        description="List of credential IDs to inject as secrets",
    )

    class Config:
        populate_by_name = True


class RunResponse(BaseModel):
    """Response wrapper for run operations."""

    run: Run


class RunsListResponse(BaseModel):
    """Response for list runs operation."""

    runs: list[Run]
    total: int


@router.post("", response_model=RunResponse, status_code=status.HTTP_201_CREATED)
async def create_run(
    request: CreateRunRequest,
    current_user: CurrentUser,
    run_service: RunServiceDep,
    asset_service: AssetServiceDep,
    env_service: EnvironmentServiceDep,
    credential_service: CredentialServiceDep,
) -> RunResponse:
    """Create a new run for a program.

    This creates a run in QUEUED status. The program must exist and have a
    built container image. An environment is automatically created or reused
    for the run.

    Optionally, credential IDs can be provided to inject secrets into the
    run container. All credentials must exist and be accessible.

    The run will be executed asynchronously by the run executor.
    """
    # Verify the program exists
    program = asset_service.get_program(request.program_id)
    if program is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Program not found: {request.program_id}",
        )

    # Check if program has a built image
    if program.image_tag is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Program does not have a built container image. Build the image first.",
        )

    # Validate all credentials exist and are not expired
    for cred_id in request.credential_ids:
        credential = credential_service.get_credential(cred_id)
        if credential is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Credential not found: {cred_id}",
            )
        if credential.is_expired:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Credential has expired: {cred_id}",
            )

    # Find or create an environment for this program
    environments = env_service.list_environments(program_id=request.program_id)
    ready_envs = [e for e in environments if e.status.value == "ready"]

    if ready_envs:
        environment = ready_envs[0]
    else:
        # Create a new environment
        environment = env_service.create_environment(
            program_id=request.program_id,
            image_tag=program.image_tag,
        )
        # Mark as ready (in real impl, this would happen after image is verified)
        environment = env_service.mark_ready(environment.id)

    # Create the run
    run = run_service.create_run(
        environment_id=environment.id,
        program_id=request.program_id,
        credential_ids=request.credential_ids,
    )

    return RunResponse(run=run)


@router.get("", response_model=RunsListResponse)
async def list_runs(
    current_user: CurrentUser,
    run_service: RunServiceDep,
    program_id: str | None = Query(None, alias="programId", description="Filter by program ID"),
    status: RunExecutionStatus | None = Query(None, description="Filter by status"),
) -> RunsListResponse:
    """List runs with optional filters.

    Supports filtering by:
    - programId: Filter by program ID
    - status: Filter by execution status (queued, running, succeeded, failed, cancelled)

    Returns runs visible to the authenticated user.
    """
    runs = run_service.list_runs(
        program_id=program_id,
        status=status,
    )

    return RunsListResponse(runs=runs, total=len(runs))


@router.get("/{run_id}", response_model=RunResponse)
async def get_run(
    run_id: str,
    current_user: CurrentUser,
    run_service: RunServiceDep,
) -> RunResponse:
    """Get a run by ID.

    Returns the run details including current status, timestamps, and
    any error information.
    """
    run = run_service.get_run(run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run not found: {run_id}",
        )

    return RunResponse(run=run)


@router.post("/{run_id}/cancel", response_model=RunResponse)
async def cancel_run(
    run_id: str,
    current_user: CurrentUser,
    run_service: RunServiceDep,
) -> RunResponse:
    """Cancel a run.

    Can only cancel runs that are in QUEUED or RUNNING status.
    Cancellation is asynchronous - the run may take some time to
    actually stop.
    """
    try:
        run = run_service.cancel_run(run_id)
        return RunResponse(run=run)
    except RunNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run not found: {run_id}",
        ) from e
    except InvalidRunStateTransitionError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
