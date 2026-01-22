"""CompositionRun model for tracking composition workflow execution."""

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from mellea_api.models.common import RunExecutionStatus


def generate_uuid() -> str:
    """Generate a new UUID string."""
    return str(uuid4())


class NodeExecutionStatus(str, Enum):
    """Execution status for individual nodes in a composition."""

    PENDING = "pending"  # Not yet started
    RUNNING = "running"  # Currently executing
    SUCCEEDED = "succeeded"  # Completed successfully
    FAILED = "failed"  # Completed with error
    SKIPPED = "skipped"  # Skipped (e.g., conditional branch not taken)


class NodeExecutionState(BaseModel):
    """Execution state for a single node in the composition.

    Tracks the runtime state of each node during composition execution,
    including timing, outputs, and error information.
    """

    node_id: str = Field(alias="nodeId")
    status: NodeExecutionStatus = NodeExecutionStatus.PENDING
    started_at: datetime | None = Field(default=None, alias="startedAt")
    completed_at: datetime | None = Field(default=None, alias="completedAt")
    output: Any | None = None
    error_message: str | None = Field(default=None, alias="errorMessage")
    logs: list[str] = Field(default_factory=list)

    class Config:
        populate_by_name = True

    def mark_running(self) -> None:
        """Mark this node as running."""
        self.status = NodeExecutionStatus.RUNNING
        self.started_at = datetime.utcnow()

    def mark_succeeded(self, output: Any = None) -> None:
        """Mark this node as succeeded."""
        self.status = NodeExecutionStatus.SUCCEEDED
        self.completed_at = datetime.utcnow()
        if output is not None:
            self.output = output

    def mark_failed(self, error: str) -> None:
        """Mark this node as failed."""
        self.status = NodeExecutionStatus.FAILED
        self.completed_at = datetime.utcnow()
        self.error_message = error

    def mark_skipped(self) -> None:
        """Mark this node as skipped."""
        self.status = NodeExecutionStatus.SKIPPED
        self.completed_at = datetime.utcnow()

    def append_log(self, message: str) -> None:
        """Append a log message to this node's logs."""
        self.logs.append(message)


class CompositionRun(BaseModel):
    """Represents a single execution of a composition workflow.

    Extends the concept of a Run to track multi-node workflow execution,
    with per-node state tracking, generated code reference, and execution
    order.

    Example:
        ```python
        comp_run = CompositionRun(
            ownerId="user-789",
            environmentId="env-123",
            compositionId="comp-456",
            executionOrder=["node-1", "node-2", "node-3"],
        )
        # comp_run.status defaults to QUEUED
        ```

    Attributes:
        id: Unique identifier for this composition run
        owner_id: ID of the User who created this run
        environment_id: ID of the Environment used for this run
        composition_id: ID of the CompositionAsset being executed
        status: Current overall execution status
        job_name: Kubernetes Job name (set when job is created)
        exit_code: Process exit code (set on completion)
        error_message: Error details if failed
        created_at: When the run was queued
        started_at: When execution actually began
        completed_at: When execution finished
        execution_order: List of node IDs in execution order
        node_states: Per-node execution state tracking
        generated_code: The Python code generated for this execution
        inputs: Input values provided for the composition
        outputs: Final output values from the composition
        current_node_id: ID of the currently executing node (if any)
        credential_ids: List of credential IDs to inject as secrets
    """

    id: str = Field(default_factory=generate_uuid)
    owner_id: str = Field(alias="ownerId", description="User ID who created this run")
    environment_id: str = Field(alias="environmentId")
    composition_id: str = Field(alias="compositionId")
    status: RunExecutionStatus = RunExecutionStatus.QUEUED
    job_name: str | None = Field(default=None, alias="jobName")
    exit_code: int | None = Field(default=None, alias="exitCode")
    error_message: str | None = Field(default=None, alias="errorMessage")
    created_at: datetime = Field(default_factory=datetime.utcnow, alias="createdAt")
    started_at: datetime | None = Field(default=None, alias="startedAt")
    completed_at: datetime | None = Field(default=None, alias="completedAt")
    output: str | None = Field(default=None, description="Overall stdout/stderr output")

    # Composition-specific fields
    execution_order: list[str] = Field(default_factory=list, alias="executionOrder")
    node_states: dict[str, NodeExecutionState] = Field(
        default_factory=dict, alias="nodeStates"
    )
    generated_code: str | None = Field(default=None, alias="generatedCode")
    inputs: dict[str, Any] = Field(default_factory=dict)
    outputs: dict[str, Any] = Field(default_factory=dict)
    current_node_id: str | None = Field(default=None, alias="currentNodeId")
    credential_ids: list[str] = Field(default_factory=list, alias="credentialIds")

    class Config:
        populate_by_name = True

    def is_terminal(self) -> bool:
        """Check if this run is in a terminal state."""
        return self.status in {
            RunExecutionStatus.SUCCEEDED,
            RunExecutionStatus.FAILED,
            RunExecutionStatus.CANCELLED,
        }

    def initialize_node_states(self, node_ids: list[str]) -> None:
        """Initialize execution states for all nodes.

        Args:
            node_ids: List of node IDs to track
        """
        self.execution_order = node_ids
        self.node_states = {
            node_id: NodeExecutionState(nodeId=node_id) for node_id in node_ids
        }

    def get_node_state(self, node_id: str) -> NodeExecutionState | None:
        """Get the execution state for a specific node.

        Args:
            node_id: The node ID to get state for

        Returns:
            NodeExecutionState if found, None otherwise
        """
        return self.node_states.get(node_id)

    def update_node_state(
        self,
        node_id: str,
        status: NodeExecutionStatus,
        output: Any = None,
        error: str | None = None,
    ) -> None:
        """Update the execution state for a specific node.

        Args:
            node_id: The node ID to update
            status: New status for the node
            output: Optional output from the node
            error: Optional error message if failed
        """
        if node_id not in self.node_states:
            self.node_states[node_id] = NodeExecutionState(nodeId=node_id)

        state = self.node_states[node_id]

        if status == NodeExecutionStatus.RUNNING:
            state.mark_running()
            self.current_node_id = node_id
        elif status == NodeExecutionStatus.SUCCEEDED:
            state.mark_succeeded(output)
            self.current_node_id = None
        elif status == NodeExecutionStatus.FAILED:
            state.mark_failed(error or "Unknown error")
            self.current_node_id = None
        elif status == NodeExecutionStatus.SKIPPED:
            state.mark_skipped()

    def get_next_pending_node(self) -> str | None:
        """Get the next node that needs to be executed.

        Returns:
            The next pending node ID in execution order, or None if all done
        """
        for node_id in self.execution_order:
            state = self.node_states.get(node_id)
            if state and state.status == NodeExecutionStatus.PENDING:
                return node_id
        return None

    def get_progress(self) -> dict[str, int]:
        """Get execution progress statistics.

        Returns:
            Dictionary with counts for each status
        """
        counts = {
            "total": len(self.execution_order),
            "pending": 0,
            "running": 0,
            "succeeded": 0,
            "failed": 0,
            "skipped": 0,
        }

        for state in self.node_states.values():
            counts[state.status.value] += 1

        return counts

    def all_nodes_complete(self) -> bool:
        """Check if all nodes have completed (succeeded, failed, or skipped).

        Returns:
            True if all nodes are in a terminal state
        """
        if not self.node_states:
            return False

        terminal_statuses = {
            NodeExecutionStatus.SUCCEEDED,
            NodeExecutionStatus.FAILED,
            NodeExecutionStatus.SKIPPED,
        }

        return all(
            state.status in terminal_statuses for state in self.node_states.values()
        )

    def has_failed_nodes(self) -> bool:
        """Check if any nodes have failed.

        Returns:
            True if at least one node has failed
        """
        return any(
            state.status == NodeExecutionStatus.FAILED
            for state in self.node_states.values()
        )


# Valid state transitions for composition run execution (same as Run)
VALID_COMPOSITION_RUN_TRANSITIONS: dict[RunExecutionStatus, set[RunExecutionStatus]] = {
    RunExecutionStatus.QUEUED: {RunExecutionStatus.STARTING, RunExecutionStatus.CANCELLED},
    RunExecutionStatus.STARTING: {
        RunExecutionStatus.RUNNING,
        RunExecutionStatus.SUCCEEDED,
        RunExecutionStatus.FAILED,
        RunExecutionStatus.CANCELLED,
    },
    RunExecutionStatus.RUNNING: {
        RunExecutionStatus.SUCCEEDED,
        RunExecutionStatus.FAILED,
        RunExecutionStatus.CANCELLED,
    },
    RunExecutionStatus.SUCCEEDED: set(),
    RunExecutionStatus.FAILED: set(),
    RunExecutionStatus.CANCELLED: set(),
}


def can_transition_composition_run(
    from_status: RunExecutionStatus, to_status: RunExecutionStatus
) -> bool:
    """Check if a transition from one status to another is valid."""
    return to_status in VALID_COMPOSITION_RUN_TRANSITIONS.get(from_status, set())
