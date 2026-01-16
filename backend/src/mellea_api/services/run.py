"""RunService for managing program execution lifecycle."""

import logging
from datetime import datetime

from mellea_api.core.config import Settings, get_settings
from mellea_api.core.store import JsonStore
from mellea_api.models.common import RunExecutionStatus
from mellea_api.models.run import VALID_RUN_TRANSITIONS, Run

logger = logging.getLogger(__name__)


class RunNotFoundError(Exception):
    """Raised when a run is not found."""

    pass


class InvalidRunStateTransitionError(Exception):
    """Raised when an invalid state transition is attempted."""

    pass


class RunNotDeletableError(Exception):
    """Raised when a run cannot be deleted due to its current state."""

    pass


class RunService:
    """Service for managing program execution lifecycle.

    Manages the lifecycle of runs from creation (queuing) through completion,
    enforcing valid state transitions and tracking execution state.

    Example:
        ```python
        service = get_run_service()

        # Create a run (queued)
        run = service.create_run(
            environment_id="env-123",
            program_id="prog-456",
        )

        # Mark as starting when K8s job is created
        run = service.start_run(run.id, job_name="mellea-run-abc12345")

        # Mark as running when pod starts
        run = service.mark_running(run.id)

        # Mark as succeeded/failed when complete
        run = service.mark_succeeded(run.id, exit_code=0)
        # or
        run = service.mark_failed(run.id, exit_code=1, error="Out of memory")
        ```
    """

    def __init__(self, settings: Settings | None = None) -> None:
        """Initialize the RunService.

        Args:
            settings: Application settings (uses default if not provided)
        """
        self.settings = settings or get_settings()
        self._run_store: JsonStore[Run] | None = None

    # -------------------------------------------------------------------------
    # Store Property (lazy initialization)
    # -------------------------------------------------------------------------

    @property
    def run_store(self) -> JsonStore[Run]:
        """Get the run store, initializing if needed."""
        if self._run_store is None:
            file_path = self.settings.data_dir / "metadata" / "runs.json"
            self._run_store = JsonStore[Run](
                file_path=file_path,
                collection_key="runs",
                model_class=Run,
            )
        return self._run_store

    # -------------------------------------------------------------------------
    # State Machine Validation
    # -------------------------------------------------------------------------

    def _validate_transition(
        self, current: RunExecutionStatus, target: RunExecutionStatus
    ) -> bool:
        """Validate if a state transition is allowed.

        Args:
            current: Current run status
            target: Target run status

        Returns:
            True if transition is valid, False otherwise
        """
        if current == target:
            return True  # No-op transitions are allowed
        allowed = VALID_RUN_TRANSITIONS.get(current, set())
        return target in allowed

    def _assert_transition(
        self, run_id: str, current: RunExecutionStatus, target: RunExecutionStatus
    ) -> None:
        """Assert that a state transition is valid, raising if not.

        Args:
            run_id: Run ID for error messages
            current: Current run status
            target: Target run status

        Raises:
            InvalidRunStateTransitionError: If transition is not valid
        """
        if not self._validate_transition(current, target):
            raise InvalidRunStateTransitionError(
                f"Invalid transition for run {run_id}: "
                f"{current.value} -> {target.value}"
            )

    # -------------------------------------------------------------------------
    # CRUD Operations
    # -------------------------------------------------------------------------

    def create_run(
        self,
        owner_id: str,
        environment_id: str,
        program_id: str,
        credential_ids: list[str] | None = None,
    ) -> Run:
        """Create a new run in QUEUED status.

        Args:
            owner_id: ID of the user creating the run
            environment_id: ID of the environment to run in
            program_id: ID of the program being executed
            credential_ids: List of credential IDs to inject as secrets

        Returns:
            The created Run in QUEUED status
        """
        run = Run(
            ownerId=owner_id,
            environmentId=environment_id,
            programId=program_id,
            status=RunExecutionStatus.QUEUED,
            credentialIds=credential_ids or [],
        )
        created = self.run_store.create(run)
        logger.info(
            f"Created run {created.id} for program {program_id} "
            f"in environment {environment_id} with {len(run.credential_ids)} credentials"
        )
        return created

    def get_run(self, run_id: str) -> Run | None:
        """Get a run by ID.

        Args:
            run_id: Run's unique identifier

        Returns:
            Run if found, None otherwise
        """
        return self.run_store.get_by_id(run_id)

    def list_runs(
        self,
        owner_id: str | None = None,
        environment_id: str | None = None,
        program_id: str | None = None,
        status: RunExecutionStatus | None = None,
    ) -> list[Run]:
        """List runs with optional filtering.

        Args:
            owner_id: Filter by owner ID
            environment_id: Filter by environment ID
            program_id: Filter by program ID
            status: Filter by status

        Returns:
            List of matching runs
        """
        runs = self.run_store.list_all()

        if owner_id:
            runs = [r for r in runs if r.owner_id == owner_id]

        if environment_id:
            runs = [r for r in runs if r.environment_id == environment_id]

        if program_id:
            runs = [r for r in runs if r.program_id == program_id]

        if status:
            runs = [r for r in runs if r.status == status]

        return runs

    def update_status(
        self,
        run_id: str,
        status: RunExecutionStatus,
        job_name: str | None = None,
        exit_code: int | None = None,
        error: str | None = None,
        output_path: str | None = None,
        output: str | None = None,
    ) -> Run:
        """Update a run's status with state machine validation.

        Args:
            run_id: Run's unique identifier
            status: New status to transition to
            job_name: K8s job name (set when transitioning to STARTING)
            exit_code: Exit code (set when transitioning to SUCCEEDED/FAILED)
            error: Error message (set when transitioning to FAILED)
            output_path: Path to output files
            output: Program stdout/stderr output

        Returns:
            Updated Run

        Raises:
            RunNotFoundError: If run doesn't exist
            InvalidRunStateTransitionError: If transition is not valid
        """
        run = self.run_store.get_by_id(run_id)
        if run is None:
            raise RunNotFoundError(f"Run not found: {run_id}")

        self._assert_transition(run_id, run.status, status)

        run.status = status

        if job_name is not None:
            run.job_name = job_name

        if exit_code is not None:
            run.exit_code = exit_code

        if error is not None:
            run.error_message = error

        if output_path is not None:
            run.output_path = output_path

        if output is not None:
            run.output = output

        # Update timestamps based on transition
        if status == RunExecutionStatus.RUNNING:
            run.started_at = datetime.utcnow()
        elif status in {
            RunExecutionStatus.SUCCEEDED,
            RunExecutionStatus.FAILED,
            RunExecutionStatus.CANCELLED,
        }:
            run.completed_at = datetime.utcnow()

        updated = self.run_store.update(run_id, run)
        if updated is None:
            raise RunNotFoundError(f"Run not found: {run_id}")

        logger.info(f"Run {run_id} transitioned to {status.value}")
        return updated

    # -------------------------------------------------------------------------
    # Lifecycle Operations
    # -------------------------------------------------------------------------

    def start_run(self, run_id: str, job_name: str) -> Run:
        """Start a run (transition QUEUED -> STARTING).

        This initiates the execution sequence by recording the K8s job name.
        The caller is responsible for actually creating the K8s job.

        Args:
            run_id: Run's unique identifier
            job_name: Name of the K8s job created for this run

        Returns:
            Updated Run in STARTING status

        Raises:
            RunNotFoundError: If run doesn't exist
            InvalidRunStateTransitionError: If not in QUEUED status
        """
        return self.update_status(
            run_id, RunExecutionStatus.STARTING, job_name=job_name
        )

    def cancel_run(self, run_id: str) -> Run:
        """Cancel a run (transition to CANCELLED).

        Can cancel from QUEUED or RUNNING status.

        Args:
            run_id: Run's unique identifier

        Returns:
            Updated Run in CANCELLED status

        Raises:
            RunNotFoundError: If run doesn't exist
            InvalidRunStateTransitionError: If not in a cancellable status
        """
        run = self.run_store.get_by_id(run_id)
        if run is None:
            raise RunNotFoundError(f"Run not found: {run_id}")

        self._assert_transition(run_id, run.status, RunExecutionStatus.CANCELLED)

        return self.update_status(run_id, RunExecutionStatus.CANCELLED)

    def mark_running(self, run_id: str, output: str | None = None) -> Run:
        """Mark a run as running.

        Convenience method for STARTING -> RUNNING transition.

        Args:
            run_id: Run's unique identifier
            output: Optional initial output from the program

        Returns:
            Updated Run in RUNNING status
        """
        return self.update_status(run_id, RunExecutionStatus.RUNNING, output=output)

    def update_output(self, run_id: str, output: str) -> Run:
        """Update a run's output without changing status.

        Args:
            run_id: Run's unique identifier
            output: Program stdout/stderr output

        Returns:
            Updated Run

        Raises:
            RunNotFoundError: If run doesn't exist
        """
        run = self.run_store.get_by_id(run_id)
        if run is None:
            raise RunNotFoundError(f"Run not found: {run_id}")

        run.output = output
        updated = self.run_store.update(run_id, run)
        if updated is None:
            raise RunNotFoundError(f"Run not found: {run_id}")

        return updated

    def mark_succeeded(
        self,
        run_id: str,
        exit_code: int = 0,
        output_path: str | None = None,
        output: str | None = None,
    ) -> Run:
        """Mark a run as succeeded.

        Convenience method for RUNNING -> SUCCEEDED transition.

        Args:
            run_id: Run's unique identifier
            exit_code: Process exit code (default 0)
            output_path: Path to output files
            output: Program stdout/stderr output

        Returns:
            Updated Run in SUCCEEDED status
        """
        return self.update_status(
            run_id,
            RunExecutionStatus.SUCCEEDED,
            exit_code=exit_code,
            output_path=output_path,
            output=output,
        )

    def mark_failed(
        self,
        run_id: str,
        exit_code: int | None = None,
        error: str | None = None,
        output_path: str | None = None,
        output: str | None = None,
    ) -> Run:
        """Mark a run as failed.

        Convenience method for transitioning to FAILED status.

        Args:
            run_id: Run's unique identifier
            exit_code: Process exit code
            error: Error message describing the failure
            output_path: Path to output files (may contain partial results)
            output: Program stdout/stderr output

        Returns:
            Updated Run in FAILED status
        """
        return self.update_status(
            run_id,
            RunExecutionStatus.FAILED,
            exit_code=exit_code,
            error=error,
            output_path=output_path,
            output=output,
        )

    # -------------------------------------------------------------------------
    # Delete Operations
    # -------------------------------------------------------------------------

    def delete_run(self, run_id: str) -> bool:
        """Delete a run by ID.

        Only runs in terminal states (SUCCEEDED, FAILED, CANCELLED) can be deleted.

        Args:
            run_id: Run's unique identifier

        Returns:
            True if deletion was successful

        Raises:
            RunNotFoundError: If run doesn't exist
            RunNotDeletableError: If run is not in a terminal state
        """
        run = self.run_store.get_by_id(run_id)
        if run is None:
            raise RunNotFoundError(f"Run not found: {run_id}")

        if not run.is_terminal():
            raise RunNotDeletableError(
                f"Cannot delete run {run_id} in status {run.status.value}. "
                "Only runs in terminal states (succeeded, failed, cancelled) can be deleted."
            )

        deleted = self.run_store.delete(run_id)
        if deleted:
            logger.info(f"Deleted run {run_id}")
        return deleted

    def delete_runs(self, run_ids: list[str]) -> dict[str, bool | str]:
        """Delete multiple runs by ID.

        Only runs in terminal states (SUCCEEDED, FAILED, CANCELLED) can be deleted.
        Continues processing even if some deletions fail.

        Args:
            run_ids: List of run IDs to delete

        Returns:
            Dictionary mapping run_id to result:
            - True: Successfully deleted
            - str: Error message if deletion failed
        """
        results: dict[str, bool | str] = {}

        for run_id in run_ids:
            try:
                self.delete_run(run_id)
                results[run_id] = True
            except RunNotFoundError:
                results[run_id] = "Run not found"
            except RunNotDeletableError as e:
                results[run_id] = str(e)

        return results


# Global service instance
_run_service: RunService | None = None


def get_run_service() -> RunService:
    """Get the global RunService instance."""
    global _run_service
    if _run_service is None:
        _run_service = RunService()
    return _run_service
