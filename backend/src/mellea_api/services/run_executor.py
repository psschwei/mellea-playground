"""RunExecutor for submitting and managing program runs on Kubernetes."""

import logging

from mellea_api.models.common import RunExecutionStatus
from mellea_api.models.k8s import JobInfo, JobStatus
from mellea_api.models.run import Run
from mellea_api.services.credentials import CredentialService, get_credential_service
from mellea_api.services.environment import EnvironmentService, get_environment_service
from mellea_api.services.k8s_jobs import K8sJobService, get_k8s_job_service
from mellea_api.services.run import RunNotFoundError, RunService, get_run_service

logger = logging.getLogger(__name__)


class EnvironmentNotReadyError(Exception):
    """Raised when trying to run in an environment that's not ready."""

    pass


class ProgramNotFoundError(Exception):
    """Raised when the program for a run is not found."""

    pass


# Mapping from K8s JobStatus to RunExecutionStatus
JOB_STATUS_TO_RUN_STATUS: dict[JobStatus, RunExecutionStatus] = {
    JobStatus.PENDING: RunExecutionStatus.STARTING,
    JobStatus.RUNNING: RunExecutionStatus.RUNNING,
    JobStatus.SUCCEEDED: RunExecutionStatus.SUCCEEDED,
    JobStatus.FAILED: RunExecutionStatus.FAILED,
}


class RunExecutor:
    """Executor for submitting and managing program runs on Kubernetes.

    This service orchestrates program execution by:
    - Submitting runs as Kubernetes Jobs
    - Tracking job status and updating run state
    - Handling job completion/failure

    Example:
        ```python
        executor = get_run_executor()

        # Submit a queued run
        run = run_service.create_run(environment_id="env-123", program_id="prog-456")
        run = executor.submit_run(run.id)

        # Check status periodically
        run = executor.sync_run_status(run.id)

        # Run will be in SUCCEEDED/FAILED when complete
        ```
    """

    def __init__(
        self,
        run_service: RunService | None = None,
        k8s_service: K8sJobService | None = None,
        environment_service: EnvironmentService | None = None,
        credential_service: CredentialService | None = None,
    ) -> None:
        """Initialize the RunExecutor.

        Args:
            run_service: RunService instance (uses global if not provided)
            k8s_service: K8sJobService instance (uses global if not provided)
            environment_service: EnvironmentService instance (uses global if not provided)
            credential_service: CredentialService instance (uses global if not provided)
        """
        self._run_service = run_service
        self._k8s_service = k8s_service
        self._environment_service = environment_service
        self._credential_service = credential_service

    @property
    def run_service(self) -> RunService:
        """Get the RunService, using global instance if not set."""
        if self._run_service is None:
            self._run_service = get_run_service()
        return self._run_service

    @property
    def k8s_service(self) -> K8sJobService:
        """Get the K8sJobService, using global instance if not set."""
        if self._k8s_service is None:
            self._k8s_service = get_k8s_job_service()
        return self._k8s_service

    @property
    def environment_service(self) -> EnvironmentService:
        """Get the EnvironmentService, using global instance if not set."""
        if self._environment_service is None:
            self._environment_service = get_environment_service()
        return self._environment_service

    @property
    def credential_service(self) -> CredentialService:
        """Get the CredentialService, using global instance if not set."""
        if self._credential_service is None:
            self._credential_service = get_credential_service()
        return self._credential_service

    def submit_run(
        self,
        run_id: str,
        entrypoint: str = "main.py",
    ) -> Run:
        """Submit a queued run to Kubernetes.

        This creates a K8s Job for the run and transitions it from QUEUED
        to STARTING.

        Args:
            run_id: ID of the run to submit
            entrypoint: Python file to execute (default: main.py)

        Returns:
            Updated Run in STARTING status

        Raises:
            RunNotFoundError: If run doesn't exist
            EnvironmentNotReadyError: If environment is not ready
            RuntimeError: If K8s job creation fails
        """
        # Get the run
        run = self.run_service.get_run(run_id)
        if run is None:
            raise RunNotFoundError(f"Run not found: {run_id}")

        # Get the environment for image and resource limits
        env = self.environment_service.get_environment(run.environment_id)
        if env is None:
            raise EnvironmentNotReadyError(
                f"Environment not found: {run.environment_id}"
            )

        if not env.image_tag:
            raise EnvironmentNotReadyError(
                f"Environment {run.environment_id} has no image tag"
            )

        # Generate job name and transition to STARTING first
        # This allows proper state transition to FAILED if job creation fails
        job_name = f"mellea-run-{run.environment_id[:8].lower()}"
        run = self.run_service.start_run(run_id, job_name)

        # Resolve credential IDs to K8s secret names
        secret_names: list[str] = []
        for cred_id in run.credential_ids:
            secret_name = self.credential_service.get_k8s_secret_name(cred_id)
            if secret_name:
                secret_names.append(secret_name)
                logger.debug("Resolved credential %s to secret %s", cred_id, secret_name)

        # Create the K8s job
        try:
            self.k8s_service.create_run_job(
                environment_id=run.environment_id,
                image_tag=env.image_tag,
                resource_limits=env.resource_limits,
                entrypoint=entrypoint,
                secret_names=secret_names,
            )
        except RuntimeError as e:
            # Mark run as failed if job creation fails (STARTING -> FAILED is valid)
            logger.error("Failed to create K8s job for run %s: %s", run_id, e)
            return self.run_service.mark_failed(
                run_id, error=f"Failed to create K8s job: {e}"
            )

        logger.info("Submitted run %s as K8s job %s", run_id, job_name)
        return run

    def sync_run_status(self, run_id: str) -> Run:
        """Sync a run's status with its K8s job status.

        This queries the K8s job and updates the run's status accordingly.
        Should be called periodically for active runs.

        Args:
            run_id: ID of the run to sync

        Returns:
            Updated Run with current status

        Raises:
            RunNotFoundError: If run doesn't exist
        """
        run = self.run_service.get_run(run_id)
        if run is None:
            raise RunNotFoundError(f"Run not found: {run_id}")

        # Only sync runs that have been submitted to K8s
        if run.job_name is None:
            logger.debug("Run %s has no job name, skipping sync", run_id)
            return run

        # Skip terminal runs
        if run.is_terminal():
            logger.debug("Run %s is terminal, skipping sync", run_id)
            return run

        # Get job status from K8s
        try:
            job_info = self.k8s_service.get_job_status(run.job_name)
        except RuntimeError as e:
            logger.error("Failed to get job status for run %s: %s", run_id, e)
            return self.run_service.mark_failed(
                run_id, error=f"Failed to get job status: {e}"
            )

        # Update run based on job status
        return self._update_run_from_job(run, job_info)

    def _update_run_from_job(self, run: Run, job_info: JobInfo) -> Run:
        """Update a run's status based on K8s job info.

        Args:
            run: The run to update
            job_info: Job info from K8s

        Returns:
            Updated Run
        """
        current_status = run.status
        target_status = JOB_STATUS_TO_RUN_STATUS.get(job_info.status)

        if target_status is None:
            logger.warning(
                "Unknown job status %s for run %s", job_info.status, run.id
            )
            return run

        # No change needed
        if current_status == target_status:
            return run

        # Update based on target status
        if target_status == RunExecutionStatus.RUNNING:
            return self.run_service.mark_running(run.id)
        elif target_status == RunExecutionStatus.SUCCEEDED:
            return self.run_service.mark_succeeded(
                run.id,
                exit_code=job_info.exit_code or 0,
            )
        elif target_status == RunExecutionStatus.FAILED:
            return self.run_service.mark_failed(
                run.id,
                exit_code=job_info.exit_code,
                error=job_info.error_message,
            )

        # For STARTING status (from PENDING job), no update needed
        # as the run is already in STARTING
        return run

    def cancel_run(self, run_id: str) -> Run:
        """Cancel a run and its K8s job.

        Args:
            run_id: ID of the run to cancel

        Returns:
            Updated Run in CANCELLED status

        Raises:
            RunNotFoundError: If run doesn't exist
        """
        run = self.run_service.get_run(run_id)
        if run is None:
            raise RunNotFoundError(f"Run not found: {run_id}")

        # Delete K8s job if it exists
        if run.job_name is not None:
            try:
                self.k8s_service.delete_job(run.job_name)
                logger.info("Deleted K8s job %s for run %s", run.job_name, run_id)
            except RuntimeError as e:
                logger.warning(
                    "Failed to delete K8s job %s for run %s: %s",
                    run.job_name,
                    run_id,
                    e,
                )

        # Cancel the run
        return self.run_service.cancel_run(run_id)

    def cleanup_completed_job(self, run_id: str) -> bool:
        """Clean up the K8s job for a completed run.

        Jobs are automatically cleaned up by TTL, but this can be called
        to clean up immediately.

        Args:
            run_id: ID of the completed run

        Returns:
            True if job was deleted, False if not applicable

        Raises:
            RunNotFoundError: If run doesn't exist
        """
        run = self.run_service.get_run(run_id)
        if run is None:
            raise RunNotFoundError(f"Run not found: {run_id}")

        if run.job_name is None:
            return False

        if not run.is_terminal():
            logger.warning("Run %s is not terminal, not cleaning up job", run_id)
            return False

        try:
            self.k8s_service.delete_job(run.job_name)
            logger.info("Cleaned up K8s job %s for run %s", run.job_name, run_id)
            return True
        except RuntimeError as e:
            logger.warning("Failed to clean up job %s: %s", run.job_name, e)
            return False


# Global executor instance
_run_executor: RunExecutor | None = None


def get_run_executor() -> RunExecutor:
    """Get the global RunExecutor instance."""
    global _run_executor
    if _run_executor is None:
        _run_executor = RunExecutor()
    return _run_executor
