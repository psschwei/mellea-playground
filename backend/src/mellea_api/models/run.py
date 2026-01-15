"""Run model for tracking program execution instances."""

from datetime import datetime
from uuid import uuid4

from pydantic import BaseModel, Field

from mellea_api.models.common import RunExecutionStatus


def generate_uuid() -> str:
    """Generate a new UUID string."""
    return str(uuid4())


# Valid state transitions for run execution
VALID_RUN_TRANSITIONS: dict[RunExecutionStatus, set[RunExecutionStatus]] = {
    RunExecutionStatus.QUEUED: {RunExecutionStatus.STARTING, RunExecutionStatus.CANCELLED},
    RunExecutionStatus.STARTING: {
        RunExecutionStatus.RUNNING,
        RunExecutionStatus.SUCCEEDED,  # Jobs can complete before being observed as RUNNING
        RunExecutionStatus.FAILED,
        RunExecutionStatus.CANCELLED,
    },
    RunExecutionStatus.RUNNING: {
        RunExecutionStatus.SUCCEEDED,
        RunExecutionStatus.FAILED,
        RunExecutionStatus.CANCELLED,
    },
    RunExecutionStatus.SUCCEEDED: set(),  # Terminal state
    RunExecutionStatus.FAILED: set(),  # Terminal state
    RunExecutionStatus.CANCELLED: set(),  # Terminal state
}


def is_terminal_status(status: RunExecutionStatus) -> bool:
    """Check if a status is terminal (no further transitions allowed)."""
    return status in {
        RunExecutionStatus.SUCCEEDED,
        RunExecutionStatus.FAILED,
        RunExecutionStatus.CANCELLED,
    }


def can_transition(from_status: RunExecutionStatus, to_status: RunExecutionStatus) -> bool:
    """Check if a transition from one status to another is valid."""
    return to_status in VALID_RUN_TRANSITIONS.get(from_status, set())


class Run(BaseModel):
    """Represents a single execution of a program.

    A Run tracks the lifecycle of executing a program in a container,
    from queuing through completion or failure.

    Example:
        ```python
        run = Run(
            environmentId="env-123",
            programId="prog-456",
        )
        # run.status defaults to QUEUED
        ```

    Attributes:
        id: Unique identifier for this run
        environment_id: ID of the Environment used for this run
        program_id: ID of the ProgramAsset being run
        status: Current execution status
        job_name: Kubernetes Job name (set when job is created)
        exit_code: Process exit code (set on completion)
        error_message: Error details if failed
        created_at: When the run was queued
        started_at: When execution actually began
        completed_at: When execution finished (success, failure, or cancellation)
        output_path: Path to output files/logs
        credential_ids: List of credential IDs to inject as secrets
    """

    id: str = Field(default_factory=generate_uuid)
    environment_id: str = Field(alias="environmentId")
    program_id: str = Field(alias="programId")
    status: RunExecutionStatus = RunExecutionStatus.QUEUED
    job_name: str | None = Field(default=None, alias="jobName")
    exit_code: int | None = Field(default=None, alias="exitCode")
    error_message: str | None = Field(default=None, alias="errorMessage")
    created_at: datetime = Field(default_factory=datetime.utcnow, alias="createdAt")
    started_at: datetime | None = Field(default=None, alias="startedAt")
    completed_at: datetime | None = Field(default=None, alias="completedAt")
    output_path: str | None = Field(default=None, alias="outputPath")
    output: str | None = Field(default=None, description="Program stdout/stderr output")
    credential_ids: list[str] = Field(default_factory=list, alias="credentialIds")

    class Config:
        populate_by_name = True

    def is_terminal(self) -> bool:
        """Check if this run is in a terminal state."""
        return is_terminal_status(self.status)

    def can_transition_to(self, new_status: RunExecutionStatus) -> bool:
        """Check if transitioning to the given status is valid."""
        return can_transition(self.status, new_status)
