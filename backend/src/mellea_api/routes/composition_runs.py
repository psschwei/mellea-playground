"""Composition run routes for managing composition workflow execution."""

import contextlib
import json
from collections.abc import AsyncGenerator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from mellea_api.core.deps import CurrentUser, CurrentUserSSE
from mellea_api.models.common import RunExecutionStatus
from mellea_api.models.composition_run import CompositionRun, NodeExecutionState
from mellea_api.services.composition_executor import (
    CompositionExecutor,
    CompositionNotFoundError,
    CompositionRunNotFoundError,
    CompositionValidationError,
    CredentialValidationError,
    EnvironmentNotReadyError,
    InvalidCompositionRunStateTransitionError,
    get_composition_executor,
)
from mellea_api.services.log import LogService, get_log_service

CompositionExecutorDep = Annotated[CompositionExecutor, Depends(get_composition_executor)]
LogServiceDep = Annotated[LogService, Depends(get_log_service)]

router = APIRouter(prefix="/api/v1/composition-runs", tags=["composition-runs"])


# =============================================================================
# Request/Response Models
# =============================================================================


class CreateCompositionRunRequest(BaseModel):
    """Request body for creating a new composition run."""

    composition_id: str = Field(alias="compositionId", description="ID of the composition to run")
    environment_id: str = Field(alias="environmentId", description="ID of the environment to run in")
    inputs: dict[str, Any] = Field(
        default_factory=dict,
        description="Input values for the composition",
    )
    credential_ids: list[str] = Field(
        default_factory=list,
        alias="credentialIds",
        description="List of credential IDs to inject as secrets",
    )
    validate_composition: bool = Field(
        default=True,
        alias="validate",
        description="Whether to validate the composition before execution",
    )

    class Config:
        populate_by_name = True


class CompositionRunResponse(BaseModel):
    """Response wrapper for composition run operations."""

    run: CompositionRun


class CompositionRunsListResponse(BaseModel):
    """Response for list composition runs operation."""

    runs: list[CompositionRun]
    total: int


class ValidationResultResponse(BaseModel):
    """Response for composition validation."""

    valid: bool
    errors: list[str]
    warnings: list[str]
    program_ids: list[str] = Field(alias="programIds")
    model_ids: list[str] = Field(alias="modelIds")

    class Config:
        populate_by_name = True


class GeneratedCodeResponse(BaseModel):
    """Response for code generation."""

    code: str
    execution_order: list[str] = Field(alias="executionOrder")
    warnings: list[str]

    class Config:
        populate_by_name = True


class ProgressResponse(BaseModel):
    """Response for composition run progress."""

    total: int
    pending: int
    running: int
    succeeded: int
    failed: int
    skipped: int
    current_node_id: str | None = Field(alias="currentNodeId")
    node_states: dict[str, NodeExecutionState] = Field(alias="nodeStates")

    class Config:
        populate_by_name = True


class AppendNodeLogRequest(BaseModel):
    """Request body for appending a log message to a node."""

    message: str = Field(description="Log message to append")
    timestamp: str | None = Field(default=None, description="Optional timestamp for the log entry")


# =============================================================================
# Routes
# =============================================================================


@router.post("", response_model=CompositionRunResponse, status_code=status.HTTP_201_CREATED)
async def create_composition_run(
    request: CreateCompositionRunRequest,
    current_user: CurrentUser,
    executor: CompositionExecutorDep,
) -> CompositionRunResponse:
    """Create and submit a new composition run.

    This validates the composition (unless validate=false), generates executable
    code from the graph, and submits a K8s job for execution.

    The run will be executed asynchronously. Use the GET endpoint or log
    streaming to monitor progress.

    Args:
        request: The composition run configuration

    Returns:
        The created CompositionRun with initial state

    Raises:
        404: If the composition or environment is not found
        400: If validation fails or credentials are invalid
    """
    try:
        run = executor.submit_run(
            owner_id=current_user.id,
            composition_id=request.composition_id,
            environment_id=request.environment_id,
            inputs=request.inputs,
            credential_ids=request.credential_ids,
            validate=request.validate_composition,
        )
        return CompositionRunResponse(run=run)

    except CompositionNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e

    except EnvironmentNotReadyError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e

    except CompositionValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": str(e), "errors": e.errors},
        ) from e

    except CredentialValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e


@router.get("", response_model=CompositionRunsListResponse)
async def list_composition_runs(
    current_user: CurrentUser,
    executor: CompositionExecutorDep,
    composition_id: str | None = Query(None, alias="compositionId", description="Filter by composition ID"),
    run_status: RunExecutionStatus | None = Query(None, alias="status", description="Filter by status"),
) -> CompositionRunsListResponse:
    """List composition runs with optional filters.

    Supports filtering by:
    - compositionId: Filter by composition ID
    - status: Filter by execution status (queued, running, succeeded, failed, cancelled)

    Returns runs visible to the authenticated user.
    """
    runs = executor.list_runs(
        owner_id=current_user.id,
        composition_id=composition_id,
        status=run_status,
    )

    return CompositionRunsListResponse(runs=runs, total=len(runs))


@router.get("/{run_id}", response_model=CompositionRunResponse)
async def get_composition_run(
    run_id: str,
    current_user: CurrentUser,
    executor: CompositionExecutorDep,
) -> CompositionRunResponse:
    """Get a composition run by ID.

    Returns the run details including:
    - Current overall status
    - Per-node execution states
    - Generated code
    - Timestamps and error information
    """
    run = executor.get_run(run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Composition run not found: {run_id}",
        )

    return CompositionRunResponse(run=run)


@router.get("/{run_id}/progress", response_model=ProgressResponse)
async def get_composition_run_progress(
    run_id: str,
    current_user: CurrentUser,
    executor: CompositionExecutorDep,
) -> ProgressResponse:
    """Get execution progress for a composition run.

    Returns:
    - Counts of nodes in each state (pending, running, succeeded, failed, skipped)
    - The currently executing node ID (if any)
    - All node execution states
    """
    run = executor.get_run(run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Composition run not found: {run_id}",
        )

    progress = run.get_progress()

    return ProgressResponse(
        total=progress["total"],
        pending=progress["pending"],
        running=progress["running"],
        succeeded=progress["succeeded"],
        failed=progress["failed"],
        skipped=progress["skipped"],
        currentNodeId=run.current_node_id,
        nodeStates=run.node_states,
    )


@router.post("/{run_id}/nodes/{node_id}/logs")
async def append_node_log(
    run_id: str,
    node_id: str,
    request: AppendNodeLogRequest,
    executor: CompositionExecutorDep,
) -> dict[str, bool]:
    """Append a log message to a specific node's execution state.

    This endpoint is called by the composition runner during execution to
    emit node-level logs that can be viewed in the UI for debugging.

    Note: This endpoint does not require authentication as it's called
    from within the K8s job which doesn't have user credentials.
    The run_id serves as authorization.
    """
    try:
        # Format message with optional timestamp
        if request.timestamp:
            formatted_message = f"[{request.timestamp}] {request.message}"
        else:
            formatted_message = request.message

        executor.run_service.append_node_log(run_id, node_id, formatted_message)
        return {"success": True}

    except CompositionRunNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e


@router.post("/{run_id}/cancel", response_model=CompositionRunResponse)
async def cancel_composition_run(
    run_id: str,
    current_user: CurrentUser,
    executor: CompositionExecutorDep,
    force: bool = Query(
        default=False,
        description=(
            "If True, immediately terminates without grace period (SIGKILL). "
            "If False (default), allows graceful shutdown with SIGTERM first."
        ),
    ),
) -> CompositionRunResponse:
    """Cancel a composition run with graceful shutdown.

    By default, sends SIGTERM to allow the process to clean up gracefully,
    waiting up to 30 seconds before forcefully terminating.

    Can only cancel runs that are in QUEUED or RUNNING status.

    Args:
        force: If True, immediately terminates without grace period (SIGKILL).
               If False (default), allows graceful shutdown with SIGTERM first.
    """
    try:
        run = executor.cancel_run(run_id, force=force)
        return CompositionRunResponse(run=run)

    except CompositionRunNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e

    except InvalidCompositionRunStateTransitionError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e


@router.post("/{run_id}/sync", response_model=CompositionRunResponse)
async def sync_composition_run_status(
    run_id: str,
    current_user: CurrentUser,
    executor: CompositionExecutorDep,
) -> CompositionRunResponse:
    """Sync a composition run's status with its K8s job.

    Queries the K8s job and updates the run's status accordingly.
    Useful for manually refreshing status between polling intervals.
    """
    try:
        run = executor.sync_run_status(run_id)
        return CompositionRunResponse(run=run)

    except CompositionRunNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e


@router.websocket("/{run_id}/logs")
async def stream_composition_run_logs(
    websocket: WebSocket,
    run_id: str,
    executor: CompositionExecutorDep,
    log_service: LogServiceDep,
) -> None:
    """Stream composition run logs in real-time via WebSocket.

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
    run = executor.get_run(run_id)
    if run is None:
        await websocket.close(code=4004, reason=f"Composition run not found: {run_id}")
        return

    await websocket.accept()

    try:
        # Send existing output first if available
        if run.output:
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
async def stream_composition_run_logs_sse(
    run_id: str,
    current_user: CurrentUserSSE,
    executor: CompositionExecutorDep,
    log_service: LogServiceDep,
) -> EventSourceResponse:
    """Stream composition run logs in real-time via Server-Sent Events.

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
    run = executor.get_run(run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Composition run not found: {run_id}",
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
                final_run = executor.get_run(run_id)
                final_status = final_run.status.value if final_run else "unknown"
                yield {
                    "event": "complete",
                    "data": json.dumps({"status": final_status}),
                }
                break

    return EventSourceResponse(event_generator())


@router.get("/{run_id}/logs/download")
async def download_composition_run_logs(
    run_id: str,
    current_user: CurrentUser,
    executor: CompositionExecutorDep,
) -> PlainTextResponse:
    """Download composition run logs as a plain text file.

    Returns the complete output from the run as a downloadable text file.
    The filename includes the run ID for easy identification.
    """
    run = executor.get_run(run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Composition run not found: {run_id}",
        )

    # Get the log content, defaulting to empty string if no output
    content = run.output or ""

    return PlainTextResponse(
        content=content,
        media_type="text/plain",
        headers={
            "Content-Disposition": f'attachment; filename="composition-run-{run_id}.log"',
        },
    )


@router.get("/{run_id}/code")
async def get_composition_run_code(
    run_id: str,
    current_user: CurrentUser,
    executor: CompositionExecutorDep,
) -> PlainTextResponse:
    """Get the generated Python code for a composition run.

    Returns the Python code that was generated for this execution.
    Useful for debugging and understanding what the composition does.
    """
    run = executor.get_run(run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Composition run not found: {run_id}",
        )

    code = run.generated_code or "# No code generated"

    return PlainTextResponse(
        content=code,
        media_type="text/x-python",
        headers={
            "Content-Disposition": f'attachment; filename="composition-{run_id}.py"',
        },
    )


# =============================================================================
# Composition Validation and Code Generation (non-run routes)
# =============================================================================


@router.post("/validate/{composition_id}", response_model=ValidationResultResponse)
async def validate_composition(
    composition_id: str,
    current_user: CurrentUser,
    executor: CompositionExecutorDep,
) -> ValidationResultResponse:
    """Validate a composition for execution.

    Checks that:
    - All referenced programs exist
    - All referenced models exist
    - The graph has no cycles
    - Required node parameters are set

    Returns validation result with any errors and warnings.
    """
    result = executor.validate_composition(composition_id)

    return ValidationResultResponse(
        valid=result.valid,
        errors=result.errors,
        warnings=result.warnings,
        programIds=result.program_ids,
        modelIds=result.model_ids,
    )


@router.post("/generate/{composition_id}", response_model=GeneratedCodeResponse)
async def generate_composition_code(
    composition_id: str,
    current_user: CurrentUser,
    executor: CompositionExecutorDep,
) -> GeneratedCodeResponse:
    """Generate executable Python code from a composition.

    Returns the generated code without executing it. Useful for:
    - Previewing what code will be generated
    - Exporting compositions as standalone scripts
    - Debugging composition structure
    """
    try:
        generated = executor.generate_code(composition_id)
        return GeneratedCodeResponse(
            code=generated.code,
            executionOrder=generated.execution_order,
            warnings=generated.warnings,
        )

    except CompositionNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e
