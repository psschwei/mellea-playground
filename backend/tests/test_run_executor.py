"""Tests for RunExecutor."""

import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from mellea_api.core.config import Settings
from mellea_api.models.common import CredentialType, RunExecutionStatus
from mellea_api.models.environment import Environment, ResourceLimits
from mellea_api.models.k8s import JobInfo, JobStatus
from mellea_api.services.credentials import CredentialService
from mellea_api.services.environment import EnvironmentService
from mellea_api.services.k8s_jobs import K8sJobService
from mellea_api.services.run import RunNotFoundError, RunService
from mellea_api.services.run_executor import (
    CredentialValidationError,
    EnvironmentNotReadyError,
    RunExecutor,
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


@pytest.fixture
def environment_service(settings: Settings):
    """Create an EnvironmentService with test settings."""
    return EnvironmentService(settings=settings)


@pytest.fixture
def mock_k8s_service():
    """Create a mock K8sJobService."""
    mock = MagicMock(spec=K8sJobService)
    return mock


@pytest.fixture
def credential_service(settings: Settings):
    """Create a CredentialService with test settings."""
    return CredentialService(settings=settings)


@pytest.fixture
def run_executor(
    run_service: RunService,
    environment_service: EnvironmentService,
    credential_service: CredentialService,
    mock_k8s_service,
):
    """Create a RunExecutor with real run/env/cred services and mocked K8s."""
    return RunExecutor(
        run_service=run_service,
        k8s_service=mock_k8s_service,
        environment_service=environment_service,
        credential_service=credential_service,
    )


@pytest.fixture
def sample_environment(environment_service: EnvironmentService):
    """Create a sample environment for testing."""
    env = environment_service.create_environment(
        program_id="prog-123",
        image_tag="mellea-prog:test123",
        resource_limits=ResourceLimits(cpuCores=2.0, memoryMb=1024),
    )
    # Mark as ready
    return environment_service.mark_ready(env.id)


class TestSubmitRun:
    """Tests for submitting runs to K8s."""

    def test_submit_run_success(
        self,
        run_executor: RunExecutor,
        run_service: RunService,
        sample_environment: Environment,
        mock_k8s_service,
    ):
        """Test successful run submission."""
        # Create a run
        run = run_service.create_run(
            environment_id=sample_environment.id,
            program_id="prog-123",
        )
        assert run.status == RunExecutionStatus.QUEUED

        # Submit the run
        submitted = run_executor.submit_run(run.id)

        # Verify status and job name (job name is generated from environment ID)
        assert submitted.status == RunExecutionStatus.STARTING
        assert submitted.job_name is not None
        assert submitted.job_name.startswith("mellea-run-")
        assert sample_environment.id[:8].lower() in submitted.job_name

        # Verify K8s service was called correctly
        mock_k8s_service.create_run_job.assert_called_once_with(
            environment_id=sample_environment.id,
            image_tag="mellea-prog:test123",
            resource_limits=sample_environment.resource_limits,
            entrypoint="main.py",
            secret_names=[],
        )

    def test_submit_run_custom_entrypoint(
        self,
        run_executor: RunExecutor,
        run_service: RunService,
        sample_environment: Environment,
        mock_k8s_service,
    ):
        """Test submitting a run with custom entrypoint."""
        run = run_service.create_run(
            environment_id=sample_environment.id,
            program_id="prog-123",
        )
        mock_k8s_service.create_run_job.return_value = "test-job"

        run_executor.submit_run(run.id, entrypoint="scripts/analyze.py")

        # Verify custom entrypoint was passed
        call_args = mock_k8s_service.create_run_job.call_args
        assert call_args.kwargs["entrypoint"] == "scripts/analyze.py"

    def test_submit_run_not_found(self, run_executor: RunExecutor):
        """Test submitting a non-existent run."""
        with pytest.raises(RunNotFoundError):
            run_executor.submit_run("non-existent-run")

    def test_submit_run_environment_not_found(
        self,
        run_executor: RunExecutor,
        run_service: RunService,
    ):
        """Test submitting a run with non-existent environment."""
        run = run_service.create_run(
            environment_id="non-existent-env",
            program_id="prog-123",
        )

        with pytest.raises(EnvironmentNotReadyError):
            run_executor.submit_run(run.id)

    def test_submit_run_environment_no_image(
        self,
        run_executor: RunExecutor,
        run_service: RunService,
        environment_service: EnvironmentService,
    ):
        """Test submitting a run when environment has no image tag."""
        # Create environment with empty image tag
        env = environment_service.create_environment(
            program_id="prog-123",
            image_tag="",  # Empty image tag
        )

        run = run_service.create_run(
            environment_id=env.id,
            program_id="prog-123",
        )

        with pytest.raises(EnvironmentNotReadyError):
            run_executor.submit_run(run.id)

    def test_submit_run_k8s_failure(
        self,
        run_executor: RunExecutor,
        run_service: RunService,
        sample_environment: Environment,
        mock_k8s_service,
    ):
        """Test handling K8s job creation failure."""
        run = run_service.create_run(
            environment_id=sample_environment.id,
            program_id="prog-123",
        )

        # Configure mock to raise error
        mock_k8s_service.create_run_job.side_effect = RuntimeError("K8s API error")

        # Submit should mark run as failed
        result = run_executor.submit_run(run.id)

        assert result.status == RunExecutionStatus.FAILED
        assert result.error_message is not None
        assert "K8s API error" in result.error_message


class TestSubmitRunCredentialValidation:
    """Tests for credential validation during run submission."""

    def test_submit_run_with_nonexistent_credential(
        self,
        run_executor: RunExecutor,
        run_service: RunService,
        sample_environment: Environment,
    ):
        """Test submitting a run with a non-existent credential raises error."""
        run = run_service.create_run(
            environment_id=sample_environment.id,
            program_id="prog-123",
            credential_ids=["nonexistent-cred"],
        )

        with pytest.raises(CredentialValidationError) as exc_info:
            run_executor.submit_run(run.id)
        assert "not found" in str(exc_info.value).lower()

    def test_submit_run_with_expired_credential(
        self,
        run_executor: RunExecutor,
        run_service: RunService,
        credential_service: CredentialService,
        sample_environment: Environment,
    ):
        """Test submitting a run with an expired credential raises error."""
        # Create an expired credential
        expired_time = datetime.utcnow() - timedelta(days=1)
        credential = credential_service.create_credential(
            name="Expired API Key",
            credential_type=CredentialType.API_KEY,
            secret_data={"api_key": "test-key"},
            expires_at=expired_time,
        )

        run = run_service.create_run(
            environment_id=sample_environment.id,
            program_id="prog-123",
            credential_ids=[credential.id],
        )

        with pytest.raises(CredentialValidationError) as exc_info:
            run_executor.submit_run(run.id)
        assert "expired" in str(exc_info.value).lower()

    def test_submit_run_with_valid_credential(
        self,
        run_executor: RunExecutor,
        run_service: RunService,
        credential_service: CredentialService,
        sample_environment: Environment,
        mock_k8s_service,
    ):
        """Test submitting a run with a valid credential succeeds."""
        # Create a valid credential
        credential = credential_service.create_credential(
            name="Valid API Key",
            credential_type=CredentialType.API_KEY,
            secret_data={"api_key": "test-key"},
        )

        run = run_service.create_run(
            environment_id=sample_environment.id,
            program_id="prog-123",
            credential_ids=[credential.id],
        )

        # Submit should succeed
        submitted = run_executor.submit_run(run.id)
        assert submitted.status == RunExecutionStatus.STARTING

    def test_submit_run_with_future_expiring_credential(
        self,
        run_executor: RunExecutor,
        run_service: RunService,
        credential_service: CredentialService,
        sample_environment: Environment,
        mock_k8s_service,
    ):
        """Test submitting a run with a future-expiring credential succeeds."""
        # Create a credential that expires tomorrow
        future_time = datetime.utcnow() + timedelta(days=1)
        credential = credential_service.create_credential(
            name="Future Expiring Key",
            credential_type=CredentialType.API_KEY,
            secret_data={"api_key": "test-key"},
            expires_at=future_time,
        )

        run = run_service.create_run(
            environment_id=sample_environment.id,
            program_id="prog-123",
            credential_ids=[credential.id],
        )

        # Submit should succeed
        submitted = run_executor.submit_run(run.id)
        assert submitted.status == RunExecutionStatus.STARTING

    def test_submit_run_validates_all_credentials(
        self,
        run_executor: RunExecutor,
        run_service: RunService,
        credential_service: CredentialService,
        sample_environment: Environment,
    ):
        """Test that all credentials are validated, not just the first."""
        # Create one valid and one expired credential
        valid_cred = credential_service.create_credential(
            name="Valid Key",
            credential_type=CredentialType.API_KEY,
            secret_data={"api_key": "valid"},
        )
        expired_cred = credential_service.create_credential(
            name="Expired Key",
            credential_type=CredentialType.API_KEY,
            secret_data={"api_key": "expired"},
            expires_at=datetime.utcnow() - timedelta(days=1),
        )

        run = run_service.create_run(
            environment_id=sample_environment.id,
            program_id="prog-123",
            credential_ids=[valid_cred.id, expired_cred.id],
        )

        with pytest.raises(CredentialValidationError) as exc_info:
            run_executor.submit_run(run.id)
        assert "expired" in str(exc_info.value).lower()


class TestSyncRunStatus:
    """Tests for syncing run status from K8s."""

    def test_sync_status_running(
        self,
        run_executor: RunExecutor,
        run_service: RunService,
        sample_environment: Environment,
        mock_k8s_service,
    ):
        """Test syncing status when job is running."""
        # Create and start a run
        run = run_service.create_run(
            environment_id=sample_environment.id,
            program_id="prog-123",
        )
        run = run_service.start_run(run.id, "test-job")

        # Configure K8s to return RUNNING status
        mock_k8s_service.get_job_status.return_value = JobInfo(
            name="test-job",
            namespace="mellea-runs",
            status=JobStatus.RUNNING,
        )

        # Sync status
        synced = run_executor.sync_run_status(run.id)

        assert synced.status == RunExecutionStatus.RUNNING
        assert synced.started_at is not None

    def test_sync_status_succeeded(
        self,
        run_executor: RunExecutor,
        run_service: RunService,
        sample_environment: Environment,
        mock_k8s_service,
    ):
        """Test syncing status when job succeeded."""
        # Create, start, and mark running
        run = run_service.create_run(
            environment_id=sample_environment.id,
            program_id="prog-123",
        )
        run = run_service.start_run(run.id, "test-job")
        run = run_service.mark_running(run.id)

        # Configure K8s to return SUCCEEDED status
        mock_k8s_service.get_job_status.return_value = JobInfo(
            name="test-job",
            namespace="mellea-runs",
            status=JobStatus.SUCCEEDED,
            exitCode=0,
        )

        # Sync status
        synced = run_executor.sync_run_status(run.id)

        assert synced.status == RunExecutionStatus.SUCCEEDED
        assert synced.exit_code == 0
        assert synced.completed_at is not None

    def test_sync_status_failed(
        self,
        run_executor: RunExecutor,
        run_service: RunService,
        sample_environment: Environment,
        mock_k8s_service,
    ):
        """Test syncing status when job failed."""
        # Create, start, and mark running
        run = run_service.create_run(
            environment_id=sample_environment.id,
            program_id="prog-123",
        )
        run = run_service.start_run(run.id, "test-job")
        run = run_service.mark_running(run.id)

        # Configure K8s to return FAILED status
        mock_k8s_service.get_job_status.return_value = JobInfo(
            name="test-job",
            namespace="mellea-runs",
            status=JobStatus.FAILED,
            exitCode=1,
            errorMessage="OOMKilled",
        )

        # Sync status
        synced = run_executor.sync_run_status(run.id)

        assert synced.status == RunExecutionStatus.FAILED
        assert synced.exit_code == 1
        assert synced.error_message == "OOMKilled"

    def test_sync_status_no_job_name(
        self,
        run_executor: RunExecutor,
        run_service: RunService,
        sample_environment: Environment,
    ):
        """Test syncing status when run has no job name (not submitted)."""
        run = run_service.create_run(
            environment_id=sample_environment.id,
            program_id="prog-123",
        )

        # Should return unchanged
        synced = run_executor.sync_run_status(run.id)
        assert synced.status == RunExecutionStatus.QUEUED
        assert synced.job_name is None

    def test_sync_status_terminal_run(
        self,
        run_executor: RunExecutor,
        run_service: RunService,
        sample_environment: Environment,
        mock_k8s_service,
    ):
        """Test syncing status for a terminal run (should be skipped)."""
        # Create and complete a run
        run = run_service.create_run(
            environment_id=sample_environment.id,
            program_id="prog-123",
        )
        run = run_service.start_run(run.id, "test-job")
        run = run_service.mark_running(run.id)
        run = run_service.mark_succeeded(run.id)

        # Sync should not call K8s
        synced = run_executor.sync_run_status(run.id)

        mock_k8s_service.get_job_status.assert_not_called()
        assert synced.status == RunExecutionStatus.SUCCEEDED

    def test_sync_status_not_found(self, run_executor: RunExecutor):
        """Test syncing status for non-existent run."""
        with pytest.raises(RunNotFoundError):
            run_executor.sync_run_status("non-existent")

    def test_sync_status_k8s_error(
        self,
        run_executor: RunExecutor,
        run_service: RunService,
        sample_environment: Environment,
        mock_k8s_service,
    ):
        """Test handling K8s error during sync."""
        run = run_service.create_run(
            environment_id=sample_environment.id,
            program_id="prog-123",
        )
        run = run_service.start_run(run.id, "test-job")

        # Configure K8s to raise error
        mock_k8s_service.get_job_status.side_effect = RuntimeError("K8s error")

        # Should mark run as failed
        synced = run_executor.sync_run_status(run.id)
        assert synced.status == RunExecutionStatus.FAILED


class TestCancelRun:
    """Tests for cancelling runs with graceful shutdown."""

    def test_cancel_run_graceful_default(
        self,
        run_executor: RunExecutor,
        run_service: RunService,
        sample_environment: Environment,
        mock_k8s_service,
    ):
        """Test graceful cancellation (default) sends SIGTERM with grace period."""
        # Create and start a run
        run = run_service.create_run(
            environment_id=sample_environment.id,
            program_id="prog-123",
        )
        run = run_service.start_run(run.id, "test-job")
        run = run_service.mark_running(run.id)

        # Cancel with default (graceful)
        cancelled = run_executor.cancel_run(run.id)

        assert cancelled.status == RunExecutionStatus.CANCELLED
        # Should call cancel_job with force=False for graceful shutdown
        mock_k8s_service.cancel_job.assert_called_once_with("test-job", force=False)

    def test_cancel_run_force(
        self,
        run_executor: RunExecutor,
        run_service: RunService,
        sample_environment: Environment,
        mock_k8s_service,
    ):
        """Test force cancellation immediately terminates without grace period."""
        # Create and start a run
        run = run_service.create_run(
            environment_id=sample_environment.id,
            program_id="prog-123",
        )
        run = run_service.start_run(run.id, "test-job")
        run = run_service.mark_running(run.id)

        # Force cancel
        cancelled = run_executor.cancel_run(run.id, force=True)

        assert cancelled.status == RunExecutionStatus.CANCELLED
        # Should call cancel_job with force=True for immediate termination
        mock_k8s_service.cancel_job.assert_called_once_with("test-job", force=True)

    def test_cancel_run_no_job(
        self,
        run_executor: RunExecutor,
        run_service: RunService,
        sample_environment: Environment,
        mock_k8s_service,
    ):
        """Test cancelling a queued run without a K8s job."""
        run = run_service.create_run(
            environment_id=sample_environment.id,
            program_id="prog-123",
        )

        cancelled = run_executor.cancel_run(run.id)

        assert cancelled.status == RunExecutionStatus.CANCELLED
        mock_k8s_service.cancel_job.assert_not_called()

    def test_cancel_run_k8s_failure(
        self,
        run_executor: RunExecutor,
        run_service: RunService,
        sample_environment: Environment,
        mock_k8s_service,
    ):
        """Test cancelling when K8s job cancellation fails (should still cancel run)."""
        run = run_service.create_run(
            environment_id=sample_environment.id,
            program_id="prog-123",
        )
        run = run_service.start_run(run.id, "test-job")

        # Configure K8s to fail
        mock_k8s_service.cancel_job.side_effect = RuntimeError("Cancel failed")

        # Should still cancel the run
        cancelled = run_executor.cancel_run(run.id)
        assert cancelled.status == RunExecutionStatus.CANCELLED

    def test_cancel_run_not_found(self, run_executor: RunExecutor):
        """Test cancelling a non-existent run."""
        with pytest.raises(RunNotFoundError):
            run_executor.cancel_run("non-existent")


class TestCleanupCompletedJob:
    """Tests for cleaning up completed jobs."""

    def test_cleanup_completed_job_success(
        self,
        run_executor: RunExecutor,
        run_service: RunService,
        sample_environment: Environment,
        mock_k8s_service,
    ):
        """Test cleaning up a completed job."""
        # Create and complete a run
        run = run_service.create_run(
            environment_id=sample_environment.id,
            program_id="prog-123",
        )
        run = run_service.start_run(run.id, "test-job")
        run = run_service.mark_running(run.id)
        run = run_service.mark_succeeded(run.id)

        result = run_executor.cleanup_completed_job(run.id)

        assert result is True
        mock_k8s_service.delete_job.assert_called_once_with("test-job")

    def test_cleanup_job_no_job_name(
        self,
        run_executor: RunExecutor,
        run_service: RunService,
        sample_environment: Environment,
        mock_k8s_service,
    ):
        """Test cleanup when run has no job name."""
        run = run_service.create_run(
            environment_id=sample_environment.id,
            program_id="prog-123",
        )
        run = run_service.cancel_run(run.id)  # Cancelled before submission

        result = run_executor.cleanup_completed_job(run.id)

        assert result is False
        mock_k8s_service.delete_job.assert_not_called()

    def test_cleanup_job_not_terminal(
        self,
        run_executor: RunExecutor,
        run_service: RunService,
        sample_environment: Environment,
        mock_k8s_service,
    ):
        """Test cleanup when run is not terminal."""
        run = run_service.create_run(
            environment_id=sample_environment.id,
            program_id="prog-123",
        )
        run = run_service.start_run(run.id, "test-job")
        run = run_service.mark_running(run.id)

        result = run_executor.cleanup_completed_job(run.id)

        assert result is False
        mock_k8s_service.delete_job.assert_not_called()

    def test_cleanup_job_not_found(self, run_executor: RunExecutor):
        """Test cleanup for non-existent run."""
        with pytest.raises(RunNotFoundError):
            run_executor.cleanup_completed_job("non-existent")


class TestFullLifecycle:
    """Tests for complete run lifecycle scenarios."""

    def test_successful_run_lifecycle(
        self,
        run_executor: RunExecutor,
        run_service: RunService,
        sample_environment: Environment,
        mock_k8s_service,
    ):
        """Test a complete successful run lifecycle."""
        # 1. Create run
        run = run_service.create_run(
            environment_id=sample_environment.id,
            program_id="prog-123",
        )
        assert run.status == RunExecutionStatus.QUEUED

        # 2. Submit to K8s
        run = run_executor.submit_run(run.id)
        assert run.status == RunExecutionStatus.STARTING
        assert run.job_name is not None
        assert run.job_name.startswith("mellea-run-")

        # 3. K8s reports RUNNING
        mock_k8s_service.get_job_status.return_value = JobInfo(
            name="mellea-run-abc",
            namespace="mellea-runs",
            status=JobStatus.RUNNING,
        )
        run = run_executor.sync_run_status(run.id)
        assert run.status == RunExecutionStatus.RUNNING

        # 4. K8s reports SUCCEEDED
        mock_k8s_service.get_job_status.return_value = JobInfo(
            name="mellea-run-abc",
            namespace="mellea-runs",
            status=JobStatus.SUCCEEDED,
            exitCode=0,
        )
        run = run_executor.sync_run_status(run.id)
        assert run.status == RunExecutionStatus.SUCCEEDED
        assert run.exit_code == 0

        # 5. Cleanup
        result = run_executor.cleanup_completed_job(run.id)
        assert result is True

    def test_failed_run_lifecycle(
        self,
        run_executor: RunExecutor,
        run_service: RunService,
        sample_environment: Environment,
        mock_k8s_service,
    ):
        """Test a run that fails during execution."""
        # Create and submit
        run = run_service.create_run(
            environment_id=sample_environment.id,
            program_id="prog-123",
        )
        mock_k8s_service.create_run_job.return_value = "mellea-run-abc"
        run = run_executor.submit_run(run.id)

        # K8s reports RUNNING
        mock_k8s_service.get_job_status.return_value = JobInfo(
            name="mellea-run-abc",
            namespace="mellea-runs",
            status=JobStatus.RUNNING,
        )
        run = run_executor.sync_run_status(run.id)

        # K8s reports FAILED
        mock_k8s_service.get_job_status.return_value = JobInfo(
            name="mellea-run-abc",
            namespace="mellea-runs",
            status=JobStatus.FAILED,
            exitCode=137,
            errorMessage="OOMKilled",
        )
        run = run_executor.sync_run_status(run.id)

        assert run.status == RunExecutionStatus.FAILED
        assert run.exit_code == 137
        assert run.error_message == "OOMKilled"

    def test_run_with_credentials_lifecycle(
        self,
        run_executor: RunExecutor,
        run_service: RunService,
        credential_service: CredentialService,
        sample_environment: Environment,
        mock_k8s_service,
    ):
        """Test a run with valid credentials succeeds."""
        # Create a valid credential
        credential = credential_service.create_credential(
            name="Test API Key",
            credential_type=CredentialType.API_KEY,
            secret_data={"api_key": "test-key"},
        )

        # Create run with credential
        run = run_service.create_run(
            environment_id=sample_environment.id,
            program_id="prog-123",
            credential_ids=[credential.id],
        )

        # Submit should succeed
        run = run_executor.submit_run(run.id)
        assert run.status == RunExecutionStatus.STARTING

        # Verify K8s was called with secret names
        call_args = mock_k8s_service.create_run_job.call_args
        assert len(call_args.kwargs["secret_names"]) == 1

    def test_cancelled_run_lifecycle(
        self,
        run_executor: RunExecutor,
        run_service: RunService,
        sample_environment: Environment,
        mock_k8s_service,
    ):
        """Test a run that is cancelled during execution."""
        # Create and submit
        run = run_service.create_run(
            environment_id=sample_environment.id,
            program_id="prog-123",
        )
        mock_k8s_service.create_run_job.return_value = "mellea-run-abc"
        run = run_executor.submit_run(run.id)

        # K8s reports RUNNING
        mock_k8s_service.get_job_status.return_value = JobInfo(
            name="mellea-run-abc",
            namespace="mellea-runs",
            status=JobStatus.RUNNING,
        )
        run = run_executor.sync_run_status(run.id)
        assert run.status == RunExecutionStatus.RUNNING

        # User cancels (graceful by default)
        run = run_executor.cancel_run(run.id)

        assert run.status == RunExecutionStatus.CANCELLED
        mock_k8s_service.cancel_job.assert_called_once()

    def test_startup_failure_lifecycle(
        self,
        run_executor: RunExecutor,
        run_service: RunService,
        sample_environment: Environment,
        mock_k8s_service,
    ):
        """Test a run that fails during K8s job creation."""
        run = run_service.create_run(
            environment_id=sample_environment.id,
            program_id="prog-123",
        )

        # K8s job creation fails
        mock_k8s_service.create_run_job.side_effect = RuntimeError("ImagePullBackOff")

        run = run_executor.submit_run(run.id)

        assert run.status == RunExecutionStatus.FAILED
        assert run.error_message is not None
        assert "ImagePullBackOff" in run.error_message
        # Job name is set because we transition to STARTING before creating the K8s job
        assert run.job_name is not None
