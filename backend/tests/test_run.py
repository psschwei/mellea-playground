"""Tests for Run model and state machine."""


from mellea_api.models.common import RunExecutionStatus
from mellea_api.models.run import (
    VALID_RUN_TRANSITIONS,
    Run,
    can_transition,
    is_terminal_status,
)


class TestRunModel:
    """Tests for the Run model."""

    def test_create_run_default_status(self):
        """Test that new runs start in QUEUED status."""
        run = Run(
            environment_id="env-123",
            program_id="prog-456",
        )
        assert run.status == RunExecutionStatus.QUEUED
        assert run.environment_id == "env-123"
        assert run.program_id == "prog-456"
        assert run.job_name is None
        assert run.exit_code is None
        assert run.error_message is None
        assert run.started_at is None
        assert run.completed_at is None

    def test_create_run_generates_uuid(self):
        """Test that run IDs are auto-generated."""
        run1 = Run(environment_id="env-1", program_id="prog-1")
        run2 = Run(environment_id="env-2", program_id="prog-2")
        assert run1.id != run2.id
        assert len(run1.id) == 36  # UUID format

    def test_create_run_with_all_fields(self):
        """Test creating a run with all fields specified."""
        run = Run(
            environment_id="env-123",
            program_id="prog-456",
            status=RunExecutionStatus.RUNNING,
            job_name="mellea-run-abc12345",
            exit_code=0,
            error_message=None,
            output_path="/output/run-123",
        )
        assert run.status == RunExecutionStatus.RUNNING
        assert run.job_name == "mellea-run-abc12345"
        assert run.exit_code == 0
        assert run.output_path == "/output/run-123"

    def test_run_created_at_auto_set(self):
        """Test that created_at is automatically set."""
        run = Run(environment_id="env-1", program_id="prog-1")
        assert run.created_at is not None


class TestRunExecutionStatus:
    """Tests for RunExecutionStatus enum."""

    def test_all_status_values(self):
        """Test all status enum values exist."""
        assert RunExecutionStatus.QUEUED.value == "queued"
        assert RunExecutionStatus.STARTING.value == "starting"
        assert RunExecutionStatus.RUNNING.value == "running"
        assert RunExecutionStatus.SUCCEEDED.value == "succeeded"
        assert RunExecutionStatus.FAILED.value == "failed"
        assert RunExecutionStatus.CANCELLED.value == "cancelled"


class TestStateTransitions:
    """Tests for state machine transition validation."""

    def test_valid_transitions_defined_for_all_states(self):
        """Test that all states have defined transitions."""
        for status in RunExecutionStatus:
            assert status in VALID_RUN_TRANSITIONS

    def test_terminal_states_have_no_transitions(self):
        """Test that terminal states have no outgoing transitions."""
        terminal_states = [
            RunExecutionStatus.SUCCEEDED,
            RunExecutionStatus.FAILED,
            RunExecutionStatus.CANCELLED,
        ]
        for state in terminal_states:
            assert VALID_RUN_TRANSITIONS[state] == set()

    def test_queued_can_transition_to_starting(self):
        """Test QUEUED -> STARTING is valid."""
        assert can_transition(RunExecutionStatus.QUEUED, RunExecutionStatus.STARTING)

    def test_queued_can_transition_to_cancelled(self):
        """Test QUEUED -> CANCELLED is valid."""
        assert can_transition(RunExecutionStatus.QUEUED, RunExecutionStatus.CANCELLED)

    def test_queued_cannot_transition_to_running(self):
        """Test QUEUED -> RUNNING is invalid (must go through STARTING)."""
        assert not can_transition(RunExecutionStatus.QUEUED, RunExecutionStatus.RUNNING)

    def test_starting_can_transition_to_running(self):
        """Test STARTING -> RUNNING is valid."""
        assert can_transition(RunExecutionStatus.STARTING, RunExecutionStatus.RUNNING)

    def test_starting_can_transition_to_failed(self):
        """Test STARTING -> FAILED is valid."""
        assert can_transition(RunExecutionStatus.STARTING, RunExecutionStatus.FAILED)

    def test_starting_cannot_transition_to_succeeded(self):
        """Test STARTING -> SUCCEEDED is invalid (must go through RUNNING)."""
        assert not can_transition(RunExecutionStatus.STARTING, RunExecutionStatus.SUCCEEDED)

    def test_running_can_transition_to_succeeded(self):
        """Test RUNNING -> SUCCEEDED is valid."""
        assert can_transition(RunExecutionStatus.RUNNING, RunExecutionStatus.SUCCEEDED)

    def test_running_can_transition_to_failed(self):
        """Test RUNNING -> FAILED is valid."""
        assert can_transition(RunExecutionStatus.RUNNING, RunExecutionStatus.FAILED)

    def test_running_can_transition_to_cancelled(self):
        """Test RUNNING -> CANCELLED is valid."""
        assert can_transition(RunExecutionStatus.RUNNING, RunExecutionStatus.CANCELLED)

    def test_succeeded_cannot_transition(self):
        """Test SUCCEEDED is terminal."""
        for status in RunExecutionStatus:
            assert not can_transition(RunExecutionStatus.SUCCEEDED, status)

    def test_failed_cannot_transition(self):
        """Test FAILED is terminal."""
        for status in RunExecutionStatus:
            assert not can_transition(RunExecutionStatus.FAILED, status)

    def test_cancelled_cannot_transition(self):
        """Test CANCELLED is terminal."""
        for status in RunExecutionStatus:
            assert not can_transition(RunExecutionStatus.CANCELLED, status)


class TestIsTerminalStatus:
    """Tests for is_terminal_status function."""

    def test_succeeded_is_terminal(self):
        """Test SUCCEEDED is terminal."""
        assert is_terminal_status(RunExecutionStatus.SUCCEEDED)

    def test_failed_is_terminal(self):
        """Test FAILED is terminal."""
        assert is_terminal_status(RunExecutionStatus.FAILED)

    def test_cancelled_is_terminal(self):
        """Test CANCELLED is terminal."""
        assert is_terminal_status(RunExecutionStatus.CANCELLED)

    def test_queued_is_not_terminal(self):
        """Test QUEUED is not terminal."""
        assert not is_terminal_status(RunExecutionStatus.QUEUED)

    def test_starting_is_not_terminal(self):
        """Test STARTING is not terminal."""
        assert not is_terminal_status(RunExecutionStatus.STARTING)

    def test_running_is_not_terminal(self):
        """Test RUNNING is not terminal."""
        assert not is_terminal_status(RunExecutionStatus.RUNNING)


class TestRunMethods:
    """Tests for Run model methods."""

    def test_is_terminal_on_queued_run(self):
        """Test is_terminal() returns False for QUEUED run."""
        run = Run(environment_id="env-1", program_id="prog-1")
        assert not run.is_terminal()

    def test_is_terminal_on_succeeded_run(self):
        """Test is_terminal() returns True for SUCCEEDED run."""
        run = Run(
            environment_id="env-1",
            program_id="prog-1",
            status=RunExecutionStatus.SUCCEEDED,
        )
        assert run.is_terminal()

    def test_is_terminal_on_failed_run(self):
        """Test is_terminal() returns True for FAILED run."""
        run = Run(
            environment_id="env-1",
            program_id="prog-1",
            status=RunExecutionStatus.FAILED,
        )
        assert run.is_terminal()

    def test_can_transition_to_from_queued(self):
        """Test can_transition_to() on QUEUED run."""
        run = Run(environment_id="env-1", program_id="prog-1")
        assert run.can_transition_to(RunExecutionStatus.STARTING)
        assert run.can_transition_to(RunExecutionStatus.CANCELLED)
        assert not run.can_transition_to(RunExecutionStatus.RUNNING)

    def test_can_transition_to_from_running(self):
        """Test can_transition_to() on RUNNING run."""
        run = Run(
            environment_id="env-1",
            program_id="prog-1",
            status=RunExecutionStatus.RUNNING,
        )
        assert run.can_transition_to(RunExecutionStatus.SUCCEEDED)
        assert run.can_transition_to(RunExecutionStatus.FAILED)
        assert run.can_transition_to(RunExecutionStatus.CANCELLED)
        assert not run.can_transition_to(RunExecutionStatus.QUEUED)

    def test_can_transition_to_from_terminal(self):
        """Test can_transition_to() returns False for all statuses on terminal run."""
        run = Run(
            environment_id="env-1",
            program_id="prog-1",
            status=RunExecutionStatus.SUCCEEDED,
        )
        for status in RunExecutionStatus:
            assert not run.can_transition_to(status)


class TestRunLifecycleScenarios:
    """Tests for common run lifecycle scenarios."""

    def test_successful_run_lifecycle(self):
        """Test a successful run through all states."""
        # Create run (QUEUED)
        run = Run(environment_id="env-1", program_id="prog-1")
        assert run.status == RunExecutionStatus.QUEUED

        # Valid transition: QUEUED -> STARTING
        assert run.can_transition_to(RunExecutionStatus.STARTING)

        # Valid transition: STARTING -> RUNNING
        run.status = RunExecutionStatus.STARTING
        assert run.can_transition_to(RunExecutionStatus.RUNNING)

        # Valid transition: RUNNING -> SUCCEEDED
        run.status = RunExecutionStatus.RUNNING
        assert run.can_transition_to(RunExecutionStatus.SUCCEEDED)

        # Terminal state
        run.status = RunExecutionStatus.SUCCEEDED
        assert run.is_terminal()

    def test_failed_run_lifecycle(self):
        """Test a run that fails during execution."""
        run = Run(environment_id="env-1", program_id="prog-1")

        # Progress to RUNNING
        run.status = RunExecutionStatus.STARTING
        run.status = RunExecutionStatus.RUNNING

        # Fail
        assert run.can_transition_to(RunExecutionStatus.FAILED)
        run.status = RunExecutionStatus.FAILED
        assert run.is_terminal()

    def test_cancelled_before_start(self):
        """Test a run cancelled before it starts."""
        run = Run(environment_id="env-1", program_id="prog-1")

        # Cancel from QUEUED
        assert run.can_transition_to(RunExecutionStatus.CANCELLED)
        run.status = RunExecutionStatus.CANCELLED
        assert run.is_terminal()

    def test_cancelled_during_execution(self):
        """Test a run cancelled while running."""
        run = Run(environment_id="env-1", program_id="prog-1")

        # Progress to RUNNING
        run.status = RunExecutionStatus.STARTING
        run.status = RunExecutionStatus.RUNNING

        # Cancel
        assert run.can_transition_to(RunExecutionStatus.CANCELLED)
        run.status = RunExecutionStatus.CANCELLED
        assert run.is_terminal()

    def test_startup_failure(self):
        """Test a run that fails during startup."""
        run = Run(environment_id="env-1", program_id="prog-1")

        # Attempt to start
        run.status = RunExecutionStatus.STARTING

        # Fail during startup (e.g., K8s job creation failed)
        assert run.can_transition_to(RunExecutionStatus.FAILED)
        run.status = RunExecutionStatus.FAILED
        assert run.is_terminal()
