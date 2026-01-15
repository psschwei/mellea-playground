"""RunExecutor for submitting and managing program runs on Kubernetes."""

import asyncio
import contextlib
import logging
from dataclasses import dataclass, field
from datetime import datetime

from mellea_api.core.config import Settings, get_settings
from mellea_api.models.assets import ProgramAsset
from mellea_api.models.build import BuildJobStatus
from mellea_api.models.common import ImageBuildStatus, RunExecutionStatus
from mellea_api.models.k8s import JobInfo, JobStatus
from mellea_api.models.run import Run
from mellea_api.services.assets import AssetService, get_asset_service
from mellea_api.services.credentials import CredentialService, get_credential_service
from mellea_api.services.environment import EnvironmentService, get_environment_service
from mellea_api.services.k8s_jobs import K8sJobService, get_k8s_job_service
from mellea_api.services.kaniko_builder import KanikoBuildService, get_kaniko_build_service
from mellea_api.services.run import RunNotFoundError, RunService, get_run_service

logger = logging.getLogger(__name__)


class EnvironmentNotReadyError(Exception):
    """Raised when trying to run in an environment that's not ready."""

    pass


class ProgramNotFoundError(Exception):
    """Raised when the program for a run is not found."""

    pass


class CredentialValidationError(Exception):
    """Raised when credential validation fails before run submission."""

    pass


class BuildInProgressError(Exception):
    """Raised when trying to submit a run while the build is still in progress."""

    pass


class BuildFailedError(Exception):
    """Raised when trying to submit a run but the build has failed."""

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

        # Validate all credentials before starting the run
        for cred_id in run.credential_ids:
            credential = self.credential_service.get_credential(cred_id)
            if credential is None:
                raise CredentialValidationError(
                    f"Credential not found: {cred_id}"
                )
            if credential.is_expired:
                raise CredentialValidationError(
                    f"Credential has expired: {cred_id}"
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

    def cancel_run(self, run_id: str, force: bool = False) -> Run:
        """Cancel a run and its K8s job with graceful shutdown.

        By default, sends SIGTERM to allow the process to clean up gracefully,
        waiting for the termination grace period (30s) before SIGKILL.

        Args:
            run_id: ID of the run to cancel
            force: If True, immediately terminates without grace period (SIGKILL).
                   If False (default), allows graceful shutdown with SIGTERM first.

        Returns:
            Updated Run in CANCELLED status

        Raises:
            RunNotFoundError: If run doesn't exist
        """
        run = self.run_service.get_run(run_id)
        if run is None:
            raise RunNotFoundError(f"Run not found: {run_id}")

        # Cancel K8s job if it exists
        if run.job_name is not None:
            try:
                self.k8s_service.cancel_job(run.job_name, force=force)
                if force:
                    logger.info(
                        "Force cancelled K8s job %s for run %s", run.job_name, run_id
                    )
                else:
                    logger.info(
                        "Gracefully cancelled K8s job %s for run %s",
                        run.job_name,
                        run_id,
                    )
            except RuntimeError as e:
                logger.warning(
                    "Failed to cancel K8s job %s for run %s: %s",
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


@dataclass
class ExecutorMetrics:
    """Metrics from a run executor cycle."""

    timestamp: datetime = field(default_factory=datetime.utcnow)
    queued_runs_found: int = 0
    runs_submitted: int = 0
    active_runs_synced: int = 0
    errors: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0


class RunExecutorController:
    """Background controller that processes queued runs and syncs active runs.

    This controller manages the background task that:
    - Polls for QUEUED runs and submits them to Kubernetes
    - Syncs status of STARTING/RUNNING runs with their K8s jobs

    Example:
        ```python
        controller = RunExecutorController()
        await controller.start()  # Start background processing
        # ... application runs ...
        await controller.stop()   # Stop on shutdown
        ```
    """

    def __init__(
        self,
        settings: Settings | None = None,
        run_executor: "RunExecutor | None" = None,
        run_service: RunService | None = None,
        asset_service: AssetService | None = None,
        kaniko_service: KanikoBuildService | None = None,
    ) -> None:
        """Initialize the controller.

        Args:
            settings: Application settings (uses default if not provided)
            run_executor: Optional RunExecutor instance
            run_service: Optional RunService instance
            asset_service: Optional AssetService instance
            kaniko_service: Optional KanikoBuildService instance
        """
        self.settings = settings or get_settings()
        self._run_executor = run_executor
        self._run_service = run_service
        self._asset_service = asset_service
        self._kaniko_service = kaniko_service
        self._task: asyncio.Task | None = None
        self._running = False
        self._last_metrics: ExecutorMetrics | None = None

    @property
    def run_executor(self) -> "RunExecutor":
        """Get the run executor instance."""
        if self._run_executor is None:
            self._run_executor = get_run_executor()
        return self._run_executor

    @property
    def run_service(self) -> RunService:
        """Get the run service instance."""
        if self._run_service is None:
            self._run_service = get_run_service()
        return self._run_service

    @property
    def asset_service(self) -> AssetService:
        """Get the asset service instance."""
        if self._asset_service is None:
            self._asset_service = get_asset_service()
        return self._asset_service

    @property
    def kaniko_service(self) -> KanikoBuildService:
        """Get the kaniko build service instance."""
        if self._kaniko_service is None:
            self._kaniko_service = get_kaniko_build_service()
        return self._kaniko_service

    @property
    def is_running(self) -> bool:
        """Check if the controller is running."""
        return self._running and self._task is not None

    def _sync_build_status(self, program: "ProgramAsset") -> "ProgramAsset":
        """Sync a program's build status from its Kaniko job.

        Checks the Kaniko build job status and updates the program's
        image_build_status if the build has completed.

        Args:
            program: The program to sync build status for

        Returns:
            Updated program (may be same object if no changes)
        """
        job_name = f"mellea-build-{program.id[:8].lower()}"

        try:
            build = self.kaniko_service.get_build_status(job_name)

            if build.status == BuildJobStatus.SUCCEEDED:
                program.image_build_status = ImageBuildStatus.READY
                program.image_build_error = None
                self.asset_service.update_program(program.id, program)
                logger.info("Build completed for program %s", program.id)
            elif build.status == BuildJobStatus.FAILED:
                program.image_build_status = ImageBuildStatus.FAILED
                program.image_build_error = build.error_message
                self.asset_service.update_program(program.id, program)
                logger.error(
                    "Build failed for program %s: %s", program.id, build.error_message
                )
            # If still PENDING or RUNNING, leave status as BUILDING

        except RuntimeError as e:
            # Job not found - might be cleaned up or never existed
            logger.warning(
                "Could not get build status for program %s: %s", program.id, e
            )

        return program

    async def run_cycle(self) -> ExecutorMetrics:
        """Run a single processing cycle.

        This method:
        1. Finds queued runs and submits them to K8s
        2. Syncs status of active (STARTING/RUNNING) runs

        Returns:
            ExecutorMetrics with statistics about the cycle
        """
        start_time = datetime.utcnow()
        metrics = ExecutorMetrics(timestamp=start_time)

        # 1. Submit queued runs (checking build status first)
        queued_runs = self.run_service.list_runs(status=RunExecutionStatus.QUEUED)
        metrics.queued_runs_found = len(queued_runs)

        for run in queued_runs:
            try:
                # Check if the program's build is ready before submitting
                program = self.asset_service.get_program(run.program_id)
                if program is None:
                    raise ProgramNotFoundError(f"Program not found: {run.program_id}")

                if program.image_build_status == ImageBuildStatus.BUILDING:
                    # Build in progress - sync build status from Kaniko job
                    program = self._sync_build_status(program)

                    # Re-check after sync
                    if program.image_build_status == ImageBuildStatus.BUILDING:
                        # Still building - skip this run, try again next cycle
                        logger.debug(
                            "Run %s waiting for build to complete (program %s)",
                            run.id,
                            run.program_id,
                        )
                        continue

                if program.image_build_status == ImageBuildStatus.FAILED:
                    # Build failed - fail the run
                    error_msg = program.image_build_error or "Build failed"
                    logger.error(
                        "Failing run %s because build failed: %s", run.id, error_msg
                    )
                    self.run_service.mark_failed(run.id, error=f"Build failed: {error_msg}")
                    metrics.errors.append(f"Run {run.id} failed due to build failure")
                    continue

                if program.image_tag is None:
                    # No image available - this shouldn't happen but handle gracefully
                    logger.warning(
                        "Run %s has no image_tag even though build status is %s",
                        run.id,
                        program.image_build_status,
                    )
                    continue

                # Build is ready - submit the run
                self.run_executor.submit_run(run.id)
                metrics.runs_submitted += 1
                logger.info("Submitted queued run %s", run.id)
            except Exception as e:
                error_msg = f"Failed to submit run {run.id}: {e}"
                logger.error(error_msg)
                metrics.errors.append(error_msg)

        # 2. Sync active runs (STARTING and RUNNING)
        for status in [RunExecutionStatus.STARTING, RunExecutionStatus.RUNNING]:
            active_runs = self.run_service.list_runs(status=status)

            for run in active_runs:
                try:
                    self.run_executor.sync_run_status(run.id)
                    metrics.active_runs_synced += 1
                except Exception as e:
                    error_msg = f"Failed to sync run {run.id}: {e}"
                    logger.error(error_msg)
                    metrics.errors.append(error_msg)

        # Calculate duration
        end_time = datetime.utcnow()
        metrics.duration_seconds = (end_time - start_time).total_seconds()

        self._last_metrics = metrics

        if metrics.runs_submitted > 0 or metrics.errors:
            logger.info(
                "Run executor cycle: submitted %d runs, synced %d active runs, "
                "%d errors, duration %.2fs",
                metrics.runs_submitted,
                metrics.active_runs_synced,
                len(metrics.errors),
                metrics.duration_seconds,
            )

        return metrics

    async def _run_loop(self) -> None:
        """Background loop that processes runs at configured intervals."""
        interval = self.settings.run_executor_interval_seconds
        logger.info(
            "Run executor controller started, running every %d seconds", interval
        )

        while self._running:
            try:
                await self.run_cycle()
            except Exception as e:
                logger.error("Error in run executor cycle: %s", e)

            # Sleep for the configured interval
            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break

        logger.info("Run executor controller stopped")

    async def start(self) -> None:
        """Start the background run executor controller.

        Does nothing if controller is disabled in settings or already running.
        """
        if not self.settings.run_executor_enabled:
            logger.info("Run executor controller is disabled in settings")
            return

        if self._running:
            logger.warning("Run executor controller is already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("Run executor controller background task created")

    async def stop(self) -> None:
        """Stop the background run executor controller.

        Waits for the current cycle to complete before stopping.
        """
        if not self._running:
            return

        self._running = False

        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

        logger.info("Run executor controller stopped")

    def get_last_metrics(self) -> ExecutorMetrics | None:
        """Get metrics from the last cycle.

        Returns:
            Last ExecutorMetrics or None if no cycle has run
        """
        return self._last_metrics


# Global executor instance
_run_executor: RunExecutor | None = None
_run_executor_controller: RunExecutorController | None = None


def get_run_executor() -> RunExecutor:
    """Get the global RunExecutor instance."""
    global _run_executor
    if _run_executor is None:
        _run_executor = RunExecutor()
    return _run_executor


def get_run_executor_controller() -> RunExecutorController:
    """Get the global RunExecutorController instance."""
    global _run_executor_controller
    if _run_executor_controller is None:
        _run_executor_controller = RunExecutorController()
    return _run_executor_controller
