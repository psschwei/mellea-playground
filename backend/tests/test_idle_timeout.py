"""Tests for IdleTimeoutService and IdleTimeoutController."""

import asyncio
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from mellea_api.core.config import Settings
from mellea_api.models.common import EnvironmentStatus
from mellea_api.services.environment import EnvironmentService
from mellea_api.services.idle_timeout import (
    IdleTimeoutController,
    IdleTimeoutService,
)
from mellea_api.services.run import RunService


@pytest.fixture
def temp_data_dir():
    """Create a temporary data directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def settings(temp_data_dir: Path):
    """Create test settings with temporary data directory."""
    settings = Settings(
        data_dir=temp_data_dir,
        environment_idle_timeout_minutes=60,
        run_retention_days=7,
        idle_controller_enabled=True,
        idle_controller_interval_seconds=1,  # Fast interval for tests
    )
    settings.ensure_data_dirs()
    return settings


@pytest.fixture
def env_service(settings: Settings):
    """Create an EnvironmentService with test settings."""
    return EnvironmentService(settings=settings)


@pytest.fixture
def run_service(settings: Settings):
    """Create a RunService with test settings."""
    return RunService(settings=settings)


@pytest.fixture
def idle_service(settings: Settings, env_service: EnvironmentService, run_service: RunService):
    """Create an IdleTimeoutService with test settings."""
    return IdleTimeoutService(
        settings=settings,
        environment_service=env_service,
        run_service=run_service,
    )


class TestIdleEnvironmentDetection:
    """Tests for detecting idle environments."""

    def test_find_idle_environments_empty(self, idle_service: IdleTimeoutService):
        """Test finding idle environments when none exist."""
        idle = idle_service.find_idle_environments()
        assert idle == []

    def test_environment_not_idle_if_recently_updated(
        self,
        idle_service: IdleTimeoutService,
        env_service: EnvironmentService,
    ):
        """Test that recently updated environments are not considered idle."""
        # Create a READY environment
        env = env_service.create_environment("prog-123", "image:tag")
        env_service.update_status(env.id, EnvironmentStatus.READY)

        idle = idle_service.find_idle_environments()
        assert len(idle) == 0  # Just created, not idle yet

    def test_environment_idle_after_timeout(
        self,
        env_service: EnvironmentService,
        run_service: RunService,
        temp_data_dir: Path,
    ):
        """Test that environments are detected as idle after timeout."""
        # Use a very short timeout (0 minutes) so environment is immediately idle
        short_timeout_settings = Settings(
            data_dir=temp_data_dir,
            environment_idle_timeout_minutes=0,  # 0 minute timeout = always idle
            run_retention_days=7,
        )
        idle_service = IdleTimeoutService(
            settings=short_timeout_settings,
            environment_service=env_service,
            run_service=run_service,
        )

        # Create a READY environment
        env = env_service.create_environment("prog-123", "image:tag")
        env_service.update_status(env.id, EnvironmentStatus.READY)

        idle = idle_service.find_idle_environments()
        assert len(idle) == 1
        assert idle[0].resource_id == env.id
        assert idle[0].resource_type == "environment"

    def test_running_environment_not_idle_with_recent_run(
        self,
        idle_service: IdleTimeoutService,
        env_service: EnvironmentService,
        run_service: RunService,
        settings: Settings,
    ):
        """Test that environments with recent runs are not considered idle."""
        # Create and start an environment
        env = env_service.create_environment("prog-123", "image:tag")
        env_service.update_status(env.id, EnvironmentStatus.READY)
        env_service.start_environment(env.id)
        env_service.update_status(env.id, EnvironmentStatus.RUNNING, container_id="ctr")

        # Set environment updated_at to past threshold
        env_updated = env_service.get_environment(env.id)
        assert env_updated is not None
        env_updated.updated_at = datetime.utcnow() - timedelta(
            minutes=settings.environment_idle_timeout_minutes + 10
        )
        env_service.environment_store.update(env.id, env_updated)

        # Create a recent run that completed
        run = run_service.create_run(environment_id=env.id, program_id="prog-123")
        run_service.start_run(run.id, job_name="job-123")
        run_service.mark_running(run.id)
        run_service.mark_succeeded(run.id)

        idle = idle_service.find_idle_environments()
        # Should not be idle because run completed recently
        assert len(idle) == 0


class TestStaleRunDetection:
    """Tests for detecting stale runs."""

    def test_find_stale_runs_empty(self, idle_service: IdleTimeoutService):
        """Test finding stale runs when none exist."""
        stale = idle_service.find_stale_runs()
        assert stale == []

    def test_completed_run_not_stale_if_recent(
        self,
        idle_service: IdleTimeoutService,
        run_service: RunService,
    ):
        """Test that recently completed runs are not considered stale."""
        run = run_service.create_run(environment_id="env-123", program_id="prog-123")
        run_service.start_run(run.id, job_name="job-123")
        run_service.mark_running(run.id)
        run_service.mark_succeeded(run.id)

        stale = idle_service.find_stale_runs()
        assert len(stale) == 0

    def test_run_stale_after_retention(
        self,
        idle_service: IdleTimeoutService,
        run_service: RunService,
        settings: Settings,
    ):
        """Test that runs are detected as stale after retention period."""
        run = run_service.create_run(environment_id="env-123", program_id="prog-123")
        run_service.start_run(run.id, job_name="job-123")
        run_service.mark_running(run.id)
        run_service.mark_succeeded(run.id)

        # Manually set completed_at to past retention
        run_updated = run_service.get_run(run.id)
        assert run_updated is not None
        run_updated.completed_at = datetime.utcnow() - timedelta(
            days=settings.run_retention_days + 1
        )
        run_service.run_store.update(run.id, run_updated)

        stale = idle_service.find_stale_runs()
        assert len(stale) == 1
        assert stale[0].resource_id == run.id
        assert stale[0].resource_type == "run"

    def test_failed_run_detected_as_stale(
        self,
        idle_service: IdleTimeoutService,
        run_service: RunService,
        settings: Settings,
    ):
        """Test that failed runs are also detected as stale."""
        run = run_service.create_run(environment_id="env-123", program_id="prog-123")
        run_service.start_run(run.id, job_name="job-123")
        run_service.mark_running(run.id)
        run_service.mark_failed(run.id, error="Test failure")

        # Set completed_at to past retention
        run_updated = run_service.get_run(run.id)
        assert run_updated is not None
        run_updated.completed_at = datetime.utcnow() - timedelta(
            days=settings.run_retention_days + 1
        )
        run_service.run_store.update(run.id, run_updated)

        stale = idle_service.find_stale_runs()
        assert len(stale) == 1


class TestCleanupOperations:
    """Tests for cleanup operations."""

    def test_stop_idle_environment(
        self,
        idle_service: IdleTimeoutService,
        env_service: EnvironmentService,
    ):
        """Test stopping an idle RUNNING environment."""
        env = env_service.create_environment("prog-123", "image:tag")
        env_service.update_status(env.id, EnvironmentStatus.READY)
        env_service.start_environment(env.id)
        env_service.update_status(env.id, EnvironmentStatus.RUNNING, container_id="ctr")

        result = idle_service.stop_idle_environment(env.id)

        assert result.success is True
        assert result.resource_id == env.id
        assert result.action == "stopped"

        # Verify environment is stopped
        env_stopped = env_service.get_environment(env.id)
        assert env_stopped is not None
        assert env_stopped.status == EnvironmentStatus.STOPPED

    def test_stop_idle_environment_ready_state(
        self,
        idle_service: IdleTimeoutService,
        env_service: EnvironmentService,
    ):
        """Test that READY environments are deleted instead of stopped."""
        env = env_service.create_environment("prog-123", "image:tag")
        env_service.update_status(env.id, EnvironmentStatus.READY)

        result = idle_service.stop_idle_environment(env.id)

        assert result.success is True
        # READY environments are deleted
        assert env_service.get_environment(env.id) is None

    def test_stop_nonexistent_environment(self, idle_service: IdleTimeoutService):
        """Test stopping a nonexistent environment."""
        result = idle_service.stop_idle_environment("nonexistent")

        assert result.success is False
        assert result.error == "Environment not found"

    def test_delete_stale_run(
        self,
        idle_service: IdleTimeoutService,
        run_service: RunService,
    ):
        """Test deleting a stale run."""
        run = run_service.create_run(environment_id="env-123", program_id="prog-123")
        run_service.start_run(run.id, job_name="job-123")
        run_service.mark_running(run.id)
        run_service.mark_succeeded(run.id)

        result = idle_service.delete_stale_run(run.id)

        assert result.success is True
        assert result.resource_id == run.id
        assert result.action == "deleted"

        # Verify run is deleted
        assert run_service.get_run(run.id) is None

    def test_delete_nonexistent_run(self, idle_service: IdleTimeoutService):
        """Test deleting a nonexistent run."""
        result = idle_service.delete_stale_run("nonexistent")

        assert result.success is False
        assert result.error == "Run not found"


class TestCleanupCycle:
    """Tests for full cleanup cycles."""

    @pytest.mark.asyncio
    async def test_run_cleanup_cycle_empty(self, idle_service: IdleTimeoutService):
        """Test running cleanup cycle with no resources."""
        metrics = await idle_service.run_cleanup_cycle()

        assert metrics.environments_stopped == 0
        assert metrics.runs_deleted == 0
        assert metrics.duration_seconds >= 0

    @pytest.mark.asyncio
    async def test_run_cleanup_cycle_with_idle_resources(
        self,
        env_service: EnvironmentService,
        run_service: RunService,
        temp_data_dir: Path,
    ):
        """Test cleanup cycle that stops idle environments and deletes stale runs."""
        # Use short timeouts so resources are immediately considered idle/stale
        short_timeout_settings = Settings(
            data_dir=temp_data_dir,
            environment_idle_timeout_minutes=0,  # Immediately idle
            run_retention_days=0,  # Immediately stale
        )
        idle_service = IdleTimeoutService(
            settings=short_timeout_settings,
            environment_service=env_service,
            run_service=run_service,
        )

        # Create an environment that will be idle
        env = env_service.create_environment("prog-123", "image:tag")
        env_service.update_status(env.id, EnvironmentStatus.READY)

        # Create a run that will be stale
        run = run_service.create_run(environment_id="env-123", program_id="prog-123")
        run_service.start_run(run.id, job_name="job-123")
        run_service.mark_running(run.id)
        run_service.mark_succeeded(run.id)

        metrics = await idle_service.run_cleanup_cycle()

        # READY environments are deleted
        assert metrics.environments_stopped >= 1
        assert metrics.runs_deleted == 1

    def test_get_idle_summary(
        self,
        env_service: EnvironmentService,
        run_service: RunService,
        temp_data_dir: Path,
    ):
        """Test getting idle resource summary."""
        # Use short timeout so environment is immediately idle
        short_timeout_settings = Settings(
            data_dir=temp_data_dir,
            environment_idle_timeout_minutes=0,  # Immediately idle
            run_retention_days=7,
        )
        idle_service = IdleTimeoutService(
            settings=short_timeout_settings,
            environment_service=env_service,
            run_service=run_service,
        )

        # Create an environment that will be idle
        env = env_service.create_environment("prog-123", "image:tag")
        env_service.update_status(env.id, EnvironmentStatus.READY)

        summary = idle_service.get_idle_summary()

        assert "idle_environments" in summary
        assert "stale_runs" in summary
        assert "thresholds" in summary
        assert summary["idle_environments"]["count"] == 1


class TestIdleTimeoutController:
    """Tests for the IdleTimeoutController."""

    @pytest.fixture
    def controller(self, settings: Settings, idle_service: IdleTimeoutService):
        """Create an IdleTimeoutController with test settings."""
        return IdleTimeoutController(settings=settings, idle_service=idle_service)

    def test_controller_not_running_initially(self, controller: IdleTimeoutController):
        """Test that controller is not running initially."""
        assert controller.is_running is False

    @pytest.mark.asyncio
    async def test_controller_start_and_stop(self, controller: IdleTimeoutController):
        """Test starting and stopping the controller."""
        await controller.start()
        assert controller.is_running is True

        await controller.stop()
        assert controller.is_running is False

    @pytest.mark.asyncio
    async def test_controller_disabled_in_settings(
        self,
        idle_service: IdleTimeoutService,
        temp_data_dir: Path,
    ):
        """Test that controller doesn't start when disabled in settings."""
        disabled_settings = Settings(
            data_dir=temp_data_dir,
            idle_controller_enabled=False,
        )
        controller = IdleTimeoutController(
            settings=disabled_settings,
            idle_service=idle_service,
        )

        await controller.start()
        assert controller.is_running is False

    @pytest.mark.asyncio
    async def test_controller_runs_cleanup_cycles(
        self,
        controller: IdleTimeoutController,
        idle_service: IdleTimeoutService,
    ):
        """Test that controller runs cleanup cycles periodically."""
        await controller.start()

        # Wait for at least one cycle to run
        await asyncio.sleep(1.5)

        # Check that at least one cycle ran
        metrics = idle_service.get_last_metrics()
        assert metrics is not None

        await controller.stop()

    @pytest.mark.asyncio
    async def test_controller_double_start(self, controller: IdleTimeoutController):
        """Test that starting twice doesn't create duplicate tasks."""
        await controller.start()
        task1 = controller._task

        await controller.start()  # Should be a no-op
        task2 = controller._task

        assert task1 is task2

        await controller.stop()

    @pytest.mark.asyncio
    async def test_controller_stop_without_start(self, controller: IdleTimeoutController):
        """Test that stopping without starting is safe."""
        await controller.stop()  # Should not raise
        assert controller.is_running is False
