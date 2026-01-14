"""IdleTimeoutService for detecting and cleaning up idle resources."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from mellea_api.core.config import Settings, get_settings
from mellea_api.models.common import EnvironmentStatus, RunExecutionStatus
from mellea_api.services.environment import EnvironmentService, get_environment_service
from mellea_api.services.k8s_jobs import K8sJobService, get_k8s_job_service
from mellea_api.services.run import RunService, get_run_service

if TYPE_CHECKING:
    from mellea_api.models.environment import Environment

logger = logging.getLogger(__name__)


@dataclass
class IdleResource:
    """Represents a resource identified as idle."""

    resource_type: str  # "environment", "run", "job"
    resource_id: str
    idle_since: datetime
    idle_duration_minutes: float


@dataclass
class CleanupResult:
    """Result of a cleanup operation."""

    success: bool
    resource_type: str
    resource_id: str
    action: str  # "stopped", "deleted", "cleaned"
    error: str | None = None


@dataclass
class ControllerMetrics:
    """Metrics from a controller run."""

    timestamp: datetime = field(default_factory=datetime.utcnow)
    environments_checked: int = 0
    environments_stopped: int = 0
    runs_checked: int = 0
    runs_deleted: int = 0
    jobs_checked: int = 0
    jobs_cleaned: int = 0
    errors: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0


class IdleTimeoutService:
    """Service for detecting and cleaning up idle resources.

    Identifies environments that have been idle (no runs, not actively used)
    for longer than the configured timeout and stops or deletes them to
    save resources and reduce costs.

    Example:
        ```python
        service = get_idle_timeout_service()

        # Find idle environments
        idle_envs = service.find_idle_environments()

        # Run full cleanup cycle
        metrics = await service.run_cleanup_cycle()
        print(f"Stopped {metrics.environments_stopped} idle environments")
        ```
    """

    def __init__(
        self,
        settings: Settings | None = None,
        environment_service: EnvironmentService | None = None,
        run_service: RunService | None = None,
        k8s_job_service: K8sJobService | None = None,
    ) -> None:
        """Initialize the IdleTimeoutService.

        Args:
            settings: Application settings (uses default if not provided)
            environment_service: Optional EnvironmentService instance
            run_service: Optional RunService instance
            k8s_job_service: Optional K8sJobService instance
        """
        self.settings = settings or get_settings()
        self._environment_service = environment_service
        self._run_service = run_service
        self._k8s_job_service = k8s_job_service
        self._last_run_metrics: ControllerMetrics | None = None

    @property
    def environment_service(self) -> EnvironmentService:
        """Get the environment service instance."""
        if self._environment_service is None:
            self._environment_service = get_environment_service()
        return self._environment_service

    @property
    def run_service(self) -> RunService:
        """Get the run service instance."""
        if self._run_service is None:
            self._run_service = get_run_service()
        return self._run_service

    @property
    def k8s_job_service(self) -> K8sJobService:
        """Get the K8s job service instance."""
        if self._k8s_job_service is None:
            self._k8s_job_service = get_k8s_job_service()
        return self._k8s_job_service

    def _is_environment_idle(self, env: Environment) -> tuple[bool, datetime | None]:
        """Check if an environment is idle.

        An environment is considered idle if:
        - It's in READY or RUNNING status
        - No runs have been executed recently (within timeout period)

        Args:
            env: Environment to check

        Returns:
            Tuple of (is_idle, idle_since_timestamp)
        """
        if env.status not in {EnvironmentStatus.READY, EnvironmentStatus.RUNNING}:
            return False, None

        # Get all runs for this environment
        runs = self.run_service.list_runs(environment_id=env.id)

        # Find the most recent activity timestamp
        last_activity = env.updated_at

        for run in runs:
            if run.completed_at and run.completed_at > last_activity:
                last_activity = run.completed_at
            elif run.started_at and run.started_at > last_activity:
                last_activity = run.started_at

        # Check if idle for longer than threshold
        idle_threshold = timedelta(minutes=self.settings.environment_idle_timeout_minutes)
        now = datetime.utcnow()

        if now - last_activity > idle_threshold:
            return True, last_activity

        return False, None

    def find_idle_environments(self) -> list[IdleResource]:
        """Find all environments that have been idle beyond the threshold.

        Returns:
            List of IdleResource objects for idle environments
        """
        idle_resources: list[IdleResource] = []

        # Check READY and RUNNING environments
        for status in [EnvironmentStatus.READY, EnvironmentStatus.RUNNING]:
            environments = self.environment_service.list_environments(status=status)

            for env in environments:
                is_idle, idle_since = self._is_environment_idle(env)
                if is_idle and idle_since:
                    idle_duration = (datetime.utcnow() - idle_since).total_seconds() / 60
                    idle_resources.append(
                        IdleResource(
                            resource_type="environment",
                            resource_id=env.id,
                            idle_since=idle_since,
                            idle_duration_minutes=idle_duration,
                        )
                    )

        return idle_resources

    def find_stale_runs(self) -> list[IdleResource]:
        """Find completed runs older than retention period.

        Returns:
            List of IdleResource objects for stale runs
        """
        idle_resources: list[IdleResource] = []
        retention_threshold = timedelta(days=self.settings.run_retention_days)
        now = datetime.utcnow()

        # Check completed runs (succeeded, failed, cancelled)
        for status in [
            RunExecutionStatus.SUCCEEDED,
            RunExecutionStatus.FAILED,
            RunExecutionStatus.CANCELLED,
        ]:
            runs = self.run_service.list_runs(status=status)

            for run in runs:
                completed_at = run.completed_at or run.created_at
                if now - completed_at > retention_threshold:
                    stale_duration = (now - completed_at).total_seconds() / 60
                    idle_resources.append(
                        IdleResource(
                            resource_type="run",
                            resource_id=run.id,
                            idle_since=completed_at,
                            idle_duration_minutes=stale_duration,
                        )
                    )

        return idle_resources

    def stop_idle_environment(self, env_id: str) -> CleanupResult:
        """Stop an idle environment.

        Args:
            env_id: Environment ID to stop

        Returns:
            CleanupResult indicating success or failure
        """
        try:
            env = self.environment_service.get_environment(env_id)
            if env is None:
                return CleanupResult(
                    success=False,
                    resource_type="environment",
                    resource_id=env_id,
                    action="stop",
                    error="Environment not found",
                )

            # Transition through proper state machine
            if env.status == EnvironmentStatus.RUNNING:
                self.environment_service.stop_environment(env_id)
                self.environment_service.mark_stopped(env_id)
                logger.info(f"Stopped idle environment {env_id}")
            elif env.status == EnvironmentStatus.READY:
                # READY environments can be deleted directly
                self.environment_service.delete_environment(env_id)
                logger.info(f"Deleted idle READY environment {env_id}")

            return CleanupResult(
                success=True,
                resource_type="environment",
                resource_id=env_id,
                action="stopped",
            )

        except Exception as e:
            logger.error(f"Failed to stop environment {env_id}: {e}")
            return CleanupResult(
                success=False,
                resource_type="environment",
                resource_id=env_id,
                action="stop",
                error=str(e),
            )

    def delete_stale_run(self, run_id: str) -> CleanupResult:
        """Delete a stale run record.

        Note: This only deletes the run metadata. Associated K8s jobs
        should already be cleaned up by Kubernetes TTL.

        Args:
            run_id: Run ID to delete

        Returns:
            CleanupResult indicating success or failure
        """
        try:
            run = self.run_service.get_run(run_id)
            if run is None:
                return CleanupResult(
                    success=False,
                    resource_type="run",
                    resource_id=run_id,
                    action="delete",
                    error="Run not found",
                )

            # Delete run record from store
            deleted = self.run_service.run_store.delete(run_id)
            if deleted:
                logger.info(f"Deleted stale run {run_id}")
                return CleanupResult(
                    success=True,
                    resource_type="run",
                    resource_id=run_id,
                    action="deleted",
                )
            else:
                return CleanupResult(
                    success=False,
                    resource_type="run",
                    resource_id=run_id,
                    action="delete",
                    error="Failed to delete run",
                )

        except Exception as e:
            logger.error(f"Failed to delete run {run_id}: {e}")
            return CleanupResult(
                success=False,
                resource_type="run",
                resource_id=run_id,
                action="delete",
                error=str(e),
            )

    async def run_cleanup_cycle(self) -> ControllerMetrics:
        """Run a full cleanup cycle.

        This method:
        1. Finds and stops idle environments
        2. Finds and deletes stale run records
        3. Cleans up orphaned K8s jobs

        Returns:
            ControllerMetrics with statistics about the cleanup
        """
        start_time = datetime.utcnow()
        metrics = ControllerMetrics(timestamp=start_time)

        logger.info("Starting idle timeout cleanup cycle")

        # 1. Stop idle environments
        idle_envs = self.find_idle_environments()
        metrics.environments_checked = len(
            self.environment_service.list_environments(status=EnvironmentStatus.READY)
        ) + len(
            self.environment_service.list_environments(status=EnvironmentStatus.RUNNING)
        )

        for idle_env in idle_envs:
            result = self.stop_idle_environment(idle_env.resource_id)
            if result.success:
                metrics.environments_stopped += 1
            else:
                metrics.errors.append(
                    f"Failed to stop env {idle_env.resource_id}: {result.error}"
                )

        # 2. Delete stale runs
        stale_runs = self.find_stale_runs()
        all_runs = self.run_service.list_runs()
        metrics.runs_checked = len(all_runs)

        for stale_run in stale_runs:
            result = self.delete_stale_run(stale_run.resource_id)
            if result.success:
                metrics.runs_deleted += 1
            else:
                metrics.errors.append(
                    f"Failed to delete run {stale_run.resource_id}: {result.error}"
                )

        # Calculate duration
        end_time = datetime.utcnow()
        metrics.duration_seconds = (end_time - start_time).total_seconds()

        self._last_run_metrics = metrics

        logger.info(
            f"Cleanup cycle complete: "
            f"stopped {metrics.environments_stopped} environments, "
            f"deleted {metrics.runs_deleted} runs, "
            f"duration {metrics.duration_seconds:.2f}s"
        )

        return metrics

    def get_last_metrics(self) -> ControllerMetrics | None:
        """Get metrics from the last cleanup run.

        Returns:
            Last ControllerMetrics or None if no run has occurred
        """
        return self._last_run_metrics

    def get_idle_summary(self) -> dict:
        """Get a summary of current idle resources.

        Returns:
            Dictionary with counts and details of idle resources
        """
        idle_envs = self.find_idle_environments()
        stale_runs = self.find_stale_runs()

        return {
            "idle_environments": {
                "count": len(idle_envs),
                "resources": [
                    {
                        "id": r.resource_id,
                        "idle_since": r.idle_since.isoformat(),
                        "idle_minutes": round(r.idle_duration_minutes, 1),
                    }
                    for r in idle_envs
                ],
            },
            "stale_runs": {
                "count": len(stale_runs),
                "resources": [
                    {
                        "id": r.resource_id,
                        "completed_at": r.idle_since.isoformat(),
                        "age_days": round(r.idle_duration_minutes / 1440, 1),
                    }
                    for r in stale_runs
                ],
            },
            "thresholds": {
                "environment_idle_timeout_minutes": self.settings.environment_idle_timeout_minutes,
                "run_retention_days": self.settings.run_retention_days,
            },
        }


class IdleTimeoutController:
    """Background controller that periodically runs cleanup cycles.

    This controller manages the background task that calls the IdleTimeoutService
    at regular intervals to clean up idle resources.

    Example:
        ```python
        controller = IdleTimeoutController()
        await controller.start()  # Start background cleanup
        # ... application runs ...
        await controller.stop()   # Stop on shutdown
        ```
    """

    def __init__(
        self,
        settings: Settings | None = None,
        idle_service: IdleTimeoutService | None = None,
    ) -> None:
        """Initialize the controller.

        Args:
            settings: Application settings (uses default if not provided)
            idle_service: Optional IdleTimeoutService instance
        """
        self.settings = settings or get_settings()
        self._idle_service = idle_service
        self._task: asyncio.Task | None = None
        self._running = False

    @property
    def idle_service(self) -> IdleTimeoutService:
        """Get the idle timeout service instance."""
        if self._idle_service is None:
            self._idle_service = get_idle_timeout_service()
        return self._idle_service

    @property
    def is_running(self) -> bool:
        """Check if the controller is running."""
        return self._running and self._task is not None

    async def _run_loop(self) -> None:
        """Background loop that runs cleanup cycles at configured intervals."""
        interval = self.settings.idle_controller_interval_seconds
        logger.info(
            f"Idle timeout controller started, running every {interval} seconds"
        )

        while self._running:
            try:
                await self.idle_service.run_cleanup_cycle()
            except Exception as e:
                logger.error(f"Error in idle timeout cleanup cycle: {e}")

            # Sleep for the configured interval
            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break

        logger.info("Idle timeout controller stopped")

    async def start(self) -> None:
        """Start the background cleanup controller.

        Does nothing if controller is disabled in settings or already running.
        """
        if not self.settings.idle_controller_enabled:
            logger.info("Idle timeout controller is disabled in settings")
            return

        if self._running:
            logger.warning("Idle timeout controller is already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("Idle timeout controller background task created")

    async def stop(self) -> None:
        """Stop the background cleanup controller.

        Waits for the current cleanup cycle to complete before stopping.
        """
        if not self._running:
            return

        self._running = False

        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

        logger.info("Idle timeout controller stopped")


# Global service instance
_idle_timeout_service: IdleTimeoutService | None = None
_idle_timeout_controller: IdleTimeoutController | None = None


def get_idle_timeout_service() -> IdleTimeoutService:
    """Get the global IdleTimeoutService instance."""
    global _idle_timeout_service
    if _idle_timeout_service is None:
        _idle_timeout_service = IdleTimeoutService()
    return _idle_timeout_service


def get_idle_timeout_controller() -> IdleTimeoutController:
    """Get the global IdleTimeoutController instance."""
    global _idle_timeout_controller
    if _idle_timeout_controller is None:
        _idle_timeout_controller = IdleTimeoutController()
    return _idle_timeout_controller
