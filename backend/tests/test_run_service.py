"""Tests for RunService with state machine."""

import tempfile
from pathlib import Path

import pytest

from mellea_api.core.config import Settings
from mellea_api.models.common import RunExecutionStatus
from mellea_api.services.run import (
    InvalidRunStateTransitionError,
    RunNotFoundError,
    RunService,
)


@pytest.fixture
def temp_data_dir():
    """Create a temporary data directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def settings(temp_data_dir: Path):
    """Create test settings with temporary data directory."""
    settings = Settings(data_dir=temp_data_dir)
    settings.ensure_data_dirs()
    return settings


@pytest.fixture
def run_service(settings: Settings):
    """Create a RunService with test settings."""
    return RunService(settings=settings)


class TestStateTransitionValidation:
    """Tests for state machine transition validation."""

    def test_validate_transition_queued_to_starting(self, run_service: RunService):
        """Test QUEUED -> STARTING is valid."""
        assert run_service._validate_transition(
            RunExecutionStatus.QUEUED, RunExecutionStatus.STARTING
        )

    def test_validate_transition_queued_to_cancelled(self, run_service: RunService):
        """Test QUEUED -> CANCELLED is valid."""
        assert run_service._validate_transition(
            RunExecutionStatus.QUEUED, RunExecutionStatus.CANCELLED
        )

    def test_validate_transition_queued_to_running_invalid(self, run_service: RunService):
        """Test QUEUED -> RUNNING is invalid."""
        assert not run_service._validate_transition(
            RunExecutionStatus.QUEUED, RunExecutionStatus.RUNNING
        )

    def test_validate_transition_starting_to_running(self, run_service: RunService):
        """Test STARTING -> RUNNING is valid."""
        assert run_service._validate_transition(
            RunExecutionStatus.STARTING, RunExecutionStatus.RUNNING
        )

    def test_validate_transition_starting_to_failed(self, run_service: RunService):
        """Test STARTING -> FAILED is valid."""
        assert run_service._validate_transition(
            RunExecutionStatus.STARTING, RunExecutionStatus.FAILED
        )

    def test_validate_transition_running_to_succeeded(self, run_service: RunService):
        """Test RUNNING -> SUCCEEDED is valid."""
        assert run_service._validate_transition(
            RunExecutionStatus.RUNNING, RunExecutionStatus.SUCCEEDED
        )

    def test_validate_transition_running_to_failed(self, run_service: RunService):
        """Test RUNNING -> FAILED is valid."""
        assert run_service._validate_transition(
            RunExecutionStatus.RUNNING, RunExecutionStatus.FAILED
        )

    def test_validate_transition_running_to_cancelled(self, run_service: RunService):
        """Test RUNNING -> CANCELLED is valid."""
        assert run_service._validate_transition(
            RunExecutionStatus.RUNNING, RunExecutionStatus.CANCELLED
        )

    def test_validate_transition_same_state(self, run_service: RunService):
        """Test that same-state transitions are allowed (no-op)."""
        for status in RunExecutionStatus:
            assert run_service._validate_transition(status, status)


class TestCreateRun:
    """Tests for run creation."""

    def test_create_run_basic(self, run_service: RunService):
        """Test basic run creation."""
        run = run_service.create_run(
            environment_id="env-123",
            program_id="prog-456",
        )

        assert run.id is not None
        assert run.environment_id == "env-123"
        assert run.program_id == "prog-456"
        assert run.status == RunExecutionStatus.QUEUED
        assert run.job_name is None
        assert run.exit_code is None
        assert run.created_at is not None

    def test_create_run_unique_ids(self, run_service: RunService):
        """Test that each run gets a unique ID."""
        run1 = run_service.create_run("env-1", "prog-1")
        run2 = run_service.create_run("env-2", "prog-2")
        assert run1.id != run2.id


class TestGetRun:
    """Tests for getting runs."""

    def test_get_run_exists(self, run_service: RunService):
        """Test getting an existing run."""
        created = run_service.create_run("env-1", "prog-1")
        fetched = run_service.get_run(created.id)

        assert fetched is not None
        assert fetched.id == created.id
        assert fetched.environment_id == "env-1"

    def test_get_run_not_found(self, run_service: RunService):
        """Test getting a non-existent run."""
        result = run_service.get_run("non-existent-id")
        assert result is None


class TestListRuns:
    """Tests for listing runs."""

    def test_list_runs_empty(self, run_service: RunService):
        """Test listing when no runs exist."""
        runs = run_service.list_runs()
        assert runs == []

    def test_list_runs_all(self, run_service: RunService):
        """Test listing all runs."""
        run_service.create_run("env-1", "prog-1")
        run_service.create_run("env-2", "prog-2")
        run_service.create_run("env-3", "prog-3")

        runs = run_service.list_runs()
        assert len(runs) == 3

    def test_list_runs_filter_by_environment(self, run_service: RunService):
        """Test filtering runs by environment ID."""
        run_service.create_run("env-1", "prog-1")
        run_service.create_run("env-1", "prog-2")
        run_service.create_run("env-2", "prog-3")

        runs = run_service.list_runs(environment_id="env-1")
        assert len(runs) == 2
        assert all(r.environment_id == "env-1" for r in runs)

    def test_list_runs_filter_by_program(self, run_service: RunService):
        """Test filtering runs by program ID."""
        run_service.create_run("env-1", "prog-1")
        run_service.create_run("env-2", "prog-1")
        run_service.create_run("env-3", "prog-2")

        runs = run_service.list_runs(program_id="prog-1")
        assert len(runs) == 2
        assert all(r.program_id == "prog-1" for r in runs)

    def test_list_runs_filter_by_status(self, run_service: RunService):
        """Test filtering runs by status."""
        run1 = run_service.create_run("env-1", "prog-1")
        run_service.create_run("env-2", "prog-2")

        # Start one run
        run_service.start_run(run1.id, "job-1")

        queued_runs = run_service.list_runs(status=RunExecutionStatus.QUEUED)
        starting_runs = run_service.list_runs(status=RunExecutionStatus.STARTING)

        assert len(queued_runs) == 1
        assert len(starting_runs) == 1


class TestStartRun:
    """Tests for starting runs."""

    def test_start_run_success(self, run_service: RunService):
        """Test successful run start."""
        run = run_service.create_run("env-1", "prog-1")
        started = run_service.start_run(run.id, "mellea-run-abc12345")

        assert started.status == RunExecutionStatus.STARTING
        assert started.job_name == "mellea-run-abc12345"

    def test_start_run_not_found(self, run_service: RunService):
        """Test starting a non-existent run."""
        with pytest.raises(RunNotFoundError):
            run_service.start_run("non-existent", "job-1")

    def test_start_run_invalid_state(self, run_service: RunService):
        """Test starting a run that's already running."""
        run = run_service.create_run("env-1", "prog-1")
        run_service.start_run(run.id, "job-1")
        run_service.mark_running(run.id)

        # Try to start a running run
        with pytest.raises(InvalidRunStateTransitionError):
            run_service.start_run(run.id, "job-2")


class TestCancelRun:
    """Tests for cancelling runs."""

    def test_cancel_queued_run(self, run_service: RunService):
        """Test cancelling a queued run."""
        run = run_service.create_run("env-1", "prog-1")
        cancelled = run_service.cancel_run(run.id)

        assert cancelled.status == RunExecutionStatus.CANCELLED
        assert cancelled.completed_at is not None

    def test_cancel_running_run(self, run_service: RunService):
        """Test cancelling a running run."""
        run = run_service.create_run("env-1", "prog-1")
        run_service.start_run(run.id, "job-1")
        run_service.mark_running(run.id)

        cancelled = run_service.cancel_run(run.id)
        assert cancelled.status == RunExecutionStatus.CANCELLED

    def test_cancel_not_found(self, run_service: RunService):
        """Test cancelling a non-existent run."""
        with pytest.raises(RunNotFoundError):
            run_service.cancel_run("non-existent")

    def test_cancel_invalid_state(self, run_service: RunService):
        """Test cancelling a run in terminal state."""
        run = run_service.create_run("env-1", "prog-1")
        run_service.start_run(run.id, "job-1")
        run_service.mark_running(run.id)
        run_service.mark_succeeded(run.id)

        with pytest.raises(InvalidRunStateTransitionError):
            run_service.cancel_run(run.id)


class TestMarkRunning:
    """Tests for marking runs as running."""

    def test_mark_running_success(self, run_service: RunService):
        """Test marking a starting run as running."""
        run = run_service.create_run("env-1", "prog-1")
        run_service.start_run(run.id, "job-1")

        running = run_service.mark_running(run.id)

        assert running.status == RunExecutionStatus.RUNNING
        assert running.started_at is not None

    def test_mark_running_invalid_state(self, run_service: RunService):
        """Test marking a queued run as running (should fail)."""
        run = run_service.create_run("env-1", "prog-1")

        with pytest.raises(InvalidRunStateTransitionError):
            run_service.mark_running(run.id)


class TestMarkSucceeded:
    """Tests for marking runs as succeeded."""

    def test_mark_succeeded_basic(self, run_service: RunService):
        """Test marking a running run as succeeded."""
        run = run_service.create_run("env-1", "prog-1")
        run_service.start_run(run.id, "job-1")
        run_service.mark_running(run.id)

        succeeded = run_service.mark_succeeded(run.id)

        assert succeeded.status == RunExecutionStatus.SUCCEEDED
        assert succeeded.exit_code == 0
        assert succeeded.completed_at is not None

    def test_mark_succeeded_with_exit_code(self, run_service: RunService):
        """Test marking succeeded with custom exit code."""
        run = run_service.create_run("env-1", "prog-1")
        run_service.start_run(run.id, "job-1")
        run_service.mark_running(run.id)

        succeeded = run_service.mark_succeeded(run.id, exit_code=0)
        assert succeeded.exit_code == 0

    def test_mark_succeeded_with_output_path(self, run_service: RunService):
        """Test marking succeeded with output path."""
        run = run_service.create_run("env-1", "prog-1")
        run_service.start_run(run.id, "job-1")
        run_service.mark_running(run.id)

        succeeded = run_service.mark_succeeded(
            run.id, output_path="/output/run-123"
        )
        assert succeeded.output_path == "/output/run-123"


class TestMarkFailed:
    """Tests for marking runs as failed."""

    def test_mark_failed_from_running(self, run_service: RunService):
        """Test marking a running run as failed."""
        run = run_service.create_run("env-1", "prog-1")
        run_service.start_run(run.id, "job-1")
        run_service.mark_running(run.id)

        failed = run_service.mark_failed(run.id, exit_code=1, error="Out of memory")

        assert failed.status == RunExecutionStatus.FAILED
        assert failed.exit_code == 1
        assert failed.error_message == "Out of memory"
        assert failed.completed_at is not None

    def test_mark_failed_from_starting(self, run_service: RunService):
        """Test marking a starting run as failed (job creation failure)."""
        run = run_service.create_run("env-1", "prog-1")
        run_service.start_run(run.id, "job-1")

        failed = run_service.mark_failed(run.id, error="Failed to create K8s job")

        assert failed.status == RunExecutionStatus.FAILED
        assert failed.error_message == "Failed to create K8s job"


class TestFullLifecycle:
    """Tests for complete run lifecycle scenarios."""

    def test_successful_run_lifecycle(self, run_service: RunService):
        """Test a complete successful run lifecycle."""
        # Create
        run = run_service.create_run("env-1", "prog-1")
        assert run.status == RunExecutionStatus.QUEUED

        # Start
        run = run_service.start_run(run.id, "mellea-run-abc")
        assert run.status == RunExecutionStatus.STARTING
        assert run.job_name == "mellea-run-abc"

        # Running
        run = run_service.mark_running(run.id)
        assert run.status == RunExecutionStatus.RUNNING
        assert run.started_at is not None

        # Succeeded
        run = run_service.mark_succeeded(run.id, exit_code=0, output_path="/out")
        assert run.status == RunExecutionStatus.SUCCEEDED
        assert run.exit_code == 0
        assert run.output_path == "/out"
        assert run.completed_at is not None

    def test_failed_run_lifecycle(self, run_service: RunService):
        """Test a run that fails during execution."""
        run = run_service.create_run("env-1", "prog-1")
        run_service.start_run(run.id, "job-1")
        run_service.mark_running(run.id)

        run = run_service.mark_failed(run.id, exit_code=137, error="OOMKilled")

        assert run.status == RunExecutionStatus.FAILED
        assert run.exit_code == 137
        assert run.error_message == "OOMKilled"

    def test_cancelled_before_start(self, run_service: RunService):
        """Test cancelling a run before it starts."""
        run = run_service.create_run("env-1", "prog-1")
        run = run_service.cancel_run(run.id)

        assert run.status == RunExecutionStatus.CANCELLED
        assert run.job_name is None  # Never started

    def test_cancelled_during_execution(self, run_service: RunService):
        """Test cancelling a run during execution."""
        run = run_service.create_run("env-1", "prog-1")
        run_service.start_run(run.id, "job-1")
        run_service.mark_running(run.id)

        run = run_service.cancel_run(run.id)
        assert run.status == RunExecutionStatus.CANCELLED

    def test_startup_failure(self, run_service: RunService):
        """Test a run that fails during K8s job creation."""
        run = run_service.create_run("env-1", "prog-1")
        run_service.start_run(run.id, "job-1")

        run = run_service.mark_failed(run.id, error="ImagePullBackOff")

        assert run.status == RunExecutionStatus.FAILED
        assert run.started_at is None  # Never actually ran

    def test_multiple_runs_same_program(self, run_service: RunService):
        """Test multiple runs of the same program."""
        run1 = run_service.create_run("env-1", "prog-1")
        run2 = run_service.create_run("env-1", "prog-1")
        run3 = run_service.create_run("env-1", "prog-1")

        # Complete run1
        run_service.start_run(run1.id, "job-1")
        run_service.mark_running(run1.id)
        run_service.mark_succeeded(run1.id)

        # Fail run2
        run_service.start_run(run2.id, "job-2")
        run_service.mark_running(run2.id)
        run_service.mark_failed(run2.id, error="timeout")

        # Cancel run3
        run_service.cancel_run(run3.id)

        # Verify all runs exist with different statuses
        runs = run_service.list_runs(program_id="prog-1")
        assert len(runs) == 3

        statuses = {r.status for r in runs}
        assert RunExecutionStatus.SUCCEEDED in statuses
        assert RunExecutionStatus.FAILED in statuses
        assert RunExecutionStatus.CANCELLED in statuses
