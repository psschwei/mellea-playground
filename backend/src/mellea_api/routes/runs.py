"""Run routes for managing program execution."""

import contextlib
import json
from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from mellea_api.core.deps import CurrentUser
from mellea_api.models.common import ImageBuildStatus, RunExecutionStatus
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
from mellea_api.services.run import (
    InvalidRunStateTransitionError,
    RunNotFoundError,
    RunService,
    get_run_service,
)
from mellea_api.services.run_executor import RunExecutor, get_run_executor

RunServiceDep = Annotated[RunService, Depends(get_run_service)]
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


@router.post("", response_model=RunResponse, status_code=status.HTTP_201_CREATED)
async def create_run(
    request: CreateRunRequest,
    current_user: CurrentUser,
    run_service: RunServiceDep,
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
    current_user: CurrentUser,
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
