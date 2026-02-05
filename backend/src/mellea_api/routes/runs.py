"""Run routes for managing program execution."""

import contextlib
import json
from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from mellea_api.core.deps import CurrentUser, CurrentUserSSE
from mellea_api.models.common import ImageBuildStatus, Permission, RunExecutionStatus, SharingMode
from mellea_api.models.run import Run
from mellea_api.services.assets import AssetService, get_asset_service
from mellea_api.services.credentials import CredentialService, get_credential_service
from mellea_api.services.environment import (
    EnvironmentService,
    get_environment_service,
)
from mellea_api.services.environment_builder import (
    EnvironmentBuilderService,
    get_environment_builder_service,
)
from mellea_api.services.log import LogService, get_log_service
from mellea_api.services.quota import QuotaExceededError, QuotaService, get_quota_service
from mellea_api.services.run import (
    InvalidRunStateTransitionError,
    RunNotDeletableError,
    RunNotFoundError,
    RunService,
    get_run_service,
)
from mellea_api.services.run_executor import RunExecutor, get_run_executor

RunServiceDep = Annotated[RunService, Depends(get_run_service)]
QuotaServiceDep = Annotated[QuotaService, Depends(get_quota_service)]
RunExecutorDep = Annotated[RunExecutor, Depends(get_run_executor)]
EnvironmentServiceDep = Annotated[EnvironmentService, Depends(get_environment_service)]
AssetServiceDep = Annotated[AssetService, Depends(get_asset_service)]
CredentialServiceDep = Annotated[CredentialService, Depends(get_credential_service)]
EnvironmentBuilderServiceDep = Annotated[
    EnvironmentBuilderService, Depends(get_environment_builder_service)
]
LogServiceDep = Annotated[LogService, Depends(get_log_service)]

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


class BulkDeleteRequest(BaseModel):
    """Request body for bulk delete operation."""

    run_ids: list[str] = Field(alias="runIds", description="List of run IDs to delete")

    class Config:
        populate_by_name = True


class BulkDeleteResponse(BaseModel):
    """Response for bulk delete operation."""

    results: dict[str, bool | str] = Field(
        description="Map of run_id to result (True for success, error message for failure)"
    )
    deleted_count: int = Field(alias="deletedCount", description="Number of runs successfully deleted")
    failed_count: int = Field(alias="failedCount", description="Number of runs that failed to delete")

    class Config:
        populate_by_name = True


class UpdateVisibilityRequest(BaseModel):
    """Request body for updating run visibility."""

    visibility: SharingMode = Field(description="New visibility mode (private, shared, public)")

    class Config:
        populate_by_name = True


class ShareRunRequest(BaseModel):
    """Request body for sharing a run with a user."""

    user_id: str = Field(alias="userId", description="User ID to share with")
    permission: Permission = Field(default=Permission.VIEW, description="Permission level")

    class Config:
        populate_by_name = True


class SharedUserResponse(BaseModel):
    """Response containing shared user info."""

    user_id: str = Field(alias="userId")
    permission: Permission

    class Config:
        populate_by_name = True


class SharedUsersListResponse(BaseModel):
    """Response containing list of shared users."""

    users: list[SharedUserResponse]
    total: int

    class Config:
        populate_by_name = True


@router.post("", response_model=RunResponse, status_code=status.HTTP_201_CREATED)
async def create_run(
    request: CreateRunRequest,
    current_user: CurrentUser,
    run_service: RunServiceDep,
    quota_service: QuotaServiceDep,
    asset_service: AssetServiceDep,
    env_service: EnvironmentServiceDep,
    credential_service: CredentialServiceDep,
    builder_service: EnvironmentBuilderServiceDep,
) -> RunResponse:
    """Create a new run for a program.

    This creates a run in QUEUED status. If the program does not have a built
    container image, a build is automatically triggered and the run will start
    once the build completes.

    Optionally, credential IDs can be provided to inject secrets into the
    run container. All credentials must exist and be accessible.

    The run will be executed asynchronously by the run executor.
    """
    # Check user quotas before creating run
    try:
        quota_service.check_can_create_run(
            user_id=current_user.id,
            user_quotas=current_user.quotas,
            run_service=run_service,
        )
    except QuotaExceededError as e:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(e),
        ) from e

    # Verify the program exists
    program = asset_service.get_program(request.program_id)
    if program is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Program not found: {request.program_id}",
        )

    # Auto-trigger build if needed (no image, failed build, or pending)
    needs_build = (
        program.image_tag is None
        or program.image_build_status == ImageBuildStatus.FAILED
        or program.image_build_status == ImageBuildStatus.PENDING
    )

    if needs_build and program.image_build_status != ImageBuildStatus.BUILDING:
        # Trigger a build
        workspace_path = asset_service.settings.data_dir / "workspaces" / request.program_id

        # Update status to building
        program.image_build_status = ImageBuildStatus.BUILDING
        program.image_build_error = None
        asset_service.update_program(request.program_id, program)

        # Start the build (runs asynchronously for Kaniko)
        result = builder_service.build_image(
            program=program,
            workspace_path=workspace_path,
            force_rebuild=False,
            push=False,
        )

        # Update program with build result (image_tag is set even for async builds)
        if result.build_job_name:
            # Async Kaniko build - update expected image tag
            program.image_tag = result.image_tag
            asset_service.update_program(request.program_id, program)
        elif result.success:
            # Sync Docker build completed
            program.image_tag = result.image_tag
            program.image_build_status = ImageBuildStatus.READY
            asset_service.update_program(request.program_id, program)
        else:
            # Sync Docker build failed
            program.image_build_status = ImageBuildStatus.FAILED
            program.image_build_error = result.error_message
            asset_service.update_program(request.program_id, program)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to build program image: {result.error_message}",
            )

        # Re-fetch program to get latest state
        program = asset_service.get_program(request.program_id)
        if program is None:
            # This shouldn't happen, but handle gracefully
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Program not found after build: {request.program_id}",
            )

    # Run will be queued even if build is still in progress
    # The executor will wait for the build to complete before submitting

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
        # image_tag may be empty string if build is async and hasn't set it yet
        # The executor will update the environment when the build completes
        environment = env_service.create_environment(
            program_id=request.program_id,
            image_tag=program.image_tag or "",
        )
        # Mark as ready (in real impl, this would happen after image is verified)
        environment = env_service.mark_ready(environment.id)

    # Create the run
    run = run_service.create_run(
        owner_id=current_user.id,
        environment_id=environment.id,
        program_id=request.program_id,
        credential_ids=request.credential_ids,
    )

    # Record run created for quota tracking
    quota_service.record_run_created(current_user.id)

    return RunResponse(run=run)


@router.get("", response_model=RunsListResponse)
async def list_runs(
    current_user: CurrentUser,
    run_service: RunServiceDep,
    program_id: str | None = Query(None, alias="programId", description="Filter by program ID"),
    status: RunExecutionStatus | None = Query(None, description="Filter by status"),
    visibility: SharingMode | None = Query(None, description="Filter by visibility mode"),
    include_shared: bool = Query(
        True,
        alias="includeShared",
        description="Include runs shared with the user (when False, only shows owned runs)",
    ),
) -> RunsListResponse:
    """List runs with optional filters.

    Supports filtering by:
    - programId: Filter by program ID
    - status: Filter by execution status (queued, running, succeeded, failed, cancelled)
    - visibility: Filter by visibility mode (private, shared, public)
    - includeShared: When True (default), includes runs shared with the user.
                     When False, only shows runs owned by the user.

    Returns runs visible to the authenticated user based on ownership and sharing settings.
    """
    if include_shared:
        # Show all runs the user can view (owns, shared with, or public)
        runs = run_service.list_runs(
            program_id=program_id,
            status=status,
            visibility=visibility,
            viewer_id=current_user.id,
        )
    else:
        # Show only runs owned by the user
        runs = run_service.list_runs(
            owner_id=current_user.id,
            program_id=program_id,
            status=status,
            visibility=visibility,
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


@router.delete("/{run_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_run(
    run_id: str,
    current_user: CurrentUser,
    run_service: RunServiceDep,
) -> None:
    """Delete a run by ID.

    Only runs in terminal states (succeeded, failed, cancelled) can be deleted.
    This will permanently remove the run record and any associated logs.
    """
    try:
        run_service.delete_run(run_id)
    except RunNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run not found: {run_id}",
        ) from e
    except RunNotDeletableError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e


@router.post("/bulk-delete", response_model=BulkDeleteResponse)
async def bulk_delete_runs(
    request: BulkDeleteRequest,
    current_user: CurrentUser,
    run_service: RunServiceDep,
) -> BulkDeleteResponse:
    """Delete multiple runs at once.

    Only runs in terminal states (succeeded, failed, cancelled) can be deleted.
    The operation continues even if some deletions fail.

    Returns detailed results for each run ID, indicating success or the reason for failure.
    """
    results = run_service.delete_runs(request.run_ids)
    deleted_count = sum(1 for v in results.values() if v is True)
    failed_count = len(results) - deleted_count

    return BulkDeleteResponse(
        results=results,
        deletedCount=deleted_count,
        failedCount=failed_count,
    )


@router.patch("/{run_id}/visibility", response_model=RunResponse)
async def update_run_visibility(
    run_id: str,
    request: UpdateVisibilityRequest,
    current_user: CurrentUser,
    run_service: RunServiceDep,
) -> RunResponse:
    """Update a run's visibility mode.

    Visibility modes:
    - private: Only the owner can view the run
    - shared: Owner and explicitly shared users can view
    - public: All authenticated users can view

    Only the run owner can change visibility.
    """
    run = run_service.get_run(run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run not found: {run_id}",
        )

    # Only owner can change visibility
    if run.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the run owner can change visibility",
        )

    updated_run = run_service.update_visibility(run_id, request.visibility)
    return RunResponse(run=updated_run)


@router.post("/{run_id}/share", response_model=RunResponse)
async def share_run_with_user(
    run_id: str,
    request: ShareRunRequest,
    current_user: CurrentUser,
    run_service: RunServiceDep,
) -> RunResponse:
    """Share a run with a specific user.

    Grants the specified user access to view the run. Only the run owner
    can share runs.
    """
    run = run_service.get_run(run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run not found: {run_id}",
        )

    # Only owner can share
    if run.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the run owner can share runs",
        )

    # Cannot share with yourself
    if request.user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot share a run with yourself",
        )

    updated_run = run_service.share_run_with_user(run_id, request.user_id, request.permission)
    return RunResponse(run=updated_run)


@router.delete("/{run_id}/share/{user_id}", response_model=RunResponse)
async def revoke_run_access(
    run_id: str,
    user_id: str,
    current_user: CurrentUser,
    run_service: RunServiceDep,
) -> RunResponse:
    """Revoke a user's access to a run.

    Removes the specified user's access to view the run. Only the run owner
    can revoke access.
    """
    run = run_service.get_run(run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run not found: {run_id}",
        )

    # Only owner can revoke access
    if run.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the run owner can revoke access",
        )

    updated_run = run_service.revoke_run_access(run_id, user_id)
    return RunResponse(run=updated_run)


@router.get("/{run_id}/shared-users", response_model=SharedUsersListResponse)
async def get_shared_users(
    run_id: str,
    current_user: CurrentUser,
    run_service: RunServiceDep,
) -> SharedUsersListResponse:
    """Get list of users a run is shared with.

    Returns the users who have explicit access to the run.
    Only the run owner can view this list.
    """
    run = run_service.get_run(run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run not found: {run_id}",
        )

    # Only owner can view shared users
    if run.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the run owner can view shared users",
        )

    shared_accesses = run_service.get_shared_users(run_id)
    users = [
        SharedUserResponse(userId=access.id, permission=access.permission)
        for access in shared_accesses
    ]
    return SharedUsersListResponse(users=users, total=len(users))


@router.post("/{run_id}/cancel", response_model=RunResponse)
async def cancel_run(
    run_id: str,
    current_user: CurrentUser,
    run_executor: RunExecutorDep,
    force: bool = Query(
        default=False,
        description=(
            "If True, immediately terminates without grace period (SIGKILL). "
            "If False (default), allows graceful shutdown with SIGTERM first."
        ),
    ),
) -> RunResponse:
    """Cancel a run with graceful shutdown.

    By default, sends SIGTERM to allow the process to clean up gracefully,
    waiting up to 30 seconds before forcefully terminating.

    Can only cancel runs that are in QUEUED or RUNNING status.

    Args:
        force: If True, immediately terminates without grace period (SIGKILL).
               If False (default), allows graceful shutdown with SIGTERM first.
    """
    try:
        run = run_executor.cancel_run(run_id, force=force)
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


@router.websocket("/{run_id}/logs")
async def stream_run_logs(
    websocket: WebSocket,
    run_id: str,
    run_service: RunServiceDep,
    log_service: LogServiceDep,
) -> None:
    """Stream run logs in real-time via WebSocket.

    Connects to the Redis pub/sub channel for the specified run and streams
    log updates to the WebSocket client as they arrive.

    The WebSocket connection will:
    - First send any existing output from the run
    - Then stream new log entries as they are published
    - Close when the run completes (receives is_complete=True)

    Message format (JSON):
    ```json
    {
        "type": "log",
        "run_id": "run-123",
        "content": "Hello, World!",
        "timestamp": "2024-01-01T12:00:00Z",
        "is_complete": false
    }
    ```
    """
    # Verify the run exists before accepting connection
    run = run_service.get_run(run_id)
    if run is None:
        await websocket.close(code=4004, reason=f"Run not found: {run_id}")
        return

    await websocket.accept()

    try:
        # Send existing output first if available
        if run.output:
            # Use the most recent timestamp available
            timestamp = run.completed_at or run.started_at or run.created_at
            await websocket.send_json(
                {
                    "type": "log",
                    "run_id": run_id,
                    "content": run.output,
                    "timestamp": timestamp.isoformat() if timestamp else None,
                    "is_complete": run.is_terminal(),
                }
            )

        # If run is already terminal, close the connection
        if run.is_terminal():
            await websocket.close(code=1000, reason="Run already completed")
            return

        # Stream new log entries from Redis pub/sub
        async for entry in log_service.subscribe(run_id):
            await websocket.send_json(
                {
                    "type": "log",
                    "run_id": entry.run_id,
                    "content": entry.content,
                    "timestamp": entry.timestamp.isoformat(),
                    "is_complete": entry.is_complete,
                }
            )

            if entry.is_complete:
                break

    except WebSocketDisconnect:
        # Client disconnected, clean up gracefully
        pass
    finally:
        # Ensure websocket is closed
        with contextlib.suppress(Exception):
            await websocket.close()


@router.get("/{run_id}/logs/stream")
async def stream_run_logs_sse(
    run_id: str,
    current_user: CurrentUserSSE,
    run_service: RunServiceDep,
    log_service: LogServiceDep,
) -> EventSourceResponse:
    """Stream run logs in real-time via Server-Sent Events.

    Connects to the Redis pub/sub channel for the specified run and streams
    log updates to the client as SSE events.

    The stream will:
    - First send any existing output from the run as a "log" event
    - Then stream new log entries as "log" events as they are published
    - Send a "complete" event when the run finishes

    Event format:
    ```
    event: log
    data: {"run_id": "run-123", "content": "Hello", "timestamp": "...", "is_complete": false}

    event: complete
    data: {"status": "succeeded"}
    ```
    """
    # Verify the run exists
    run = run_service.get_run(run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run not found: {run_id}",
        )

    async def event_generator() -> AsyncGenerator[dict[str, str], None]:
        # Send existing output first if available
        if run.output:
            timestamp = run.completed_at or run.started_at or run.created_at
            yield {
                "event": "log",
                "data": json.dumps(
                    {
                        "run_id": run_id,
                        "content": run.output,
                        "timestamp": timestamp.isoformat() if timestamp else None,
                        "is_complete": run.is_terminal(),
                    }
                ),
            }

        # If run is already terminal, send complete event and stop
        if run.is_terminal():
            yield {
                "event": "complete",
                "data": json.dumps({"status": run.status.value}),
            }
            return

        # Stream new log entries from Redis pub/sub
        async for entry in log_service.subscribe(run_id):
            yield {
                "event": "log",
                "data": json.dumps(
                    {
                        "run_id": entry.run_id,
                        "content": entry.content,
                        "timestamp": entry.timestamp.isoformat(),
                        "is_complete": entry.is_complete,
                    }
                ),
            }

            if entry.is_complete:
                # Fetch fresh run status for completion event
                final_run = run_service.get_run(run_id)
                final_status = final_run.status.value if final_run else "unknown"
                yield {
                    "event": "complete",
                    "data": json.dumps({"status": final_status}),
                }
                break

    return EventSourceResponse(event_generator())


@router.get("/{run_id}/logs/download")
async def download_run_logs(
    run_id: str,
    current_user: CurrentUser,
    run_service: RunServiceDep,
) -> PlainTextResponse:
    """Download run logs as a plain text file.

    Returns the complete output from the run as a downloadable text file.
    The filename includes the run ID for easy identification.
    """
    run = run_service.get_run(run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run not found: {run_id}",
        )

    # Get the log content, defaulting to empty string if no output
    content = run.output or ""

    return PlainTextResponse(
        content=content,
        media_type="text/plain",
        headers={
            "Content-Disposition": f'attachment; filename="run-{run_id}.log"',
        },
    )
