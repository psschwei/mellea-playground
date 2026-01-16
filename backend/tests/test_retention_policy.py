"""Tests for RetentionPolicyService and RetentionPolicyController."""

import asyncio
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from mellea_api.core.config import Settings
from mellea_api.models.common import EnvironmentStatus, RunExecutionStatus
from mellea_api.models.retention_policy import (
    ResourceType,
    RetentionCondition,
)
from mellea_api.services.artifact_collector import ArtifactCollectorService
from mellea_api.services.environment import EnvironmentService
from mellea_api.services.retention_policy import (
    RetentionPolicyController,
    RetentionPolicyService,
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
        retention_policy_enabled=True,
        retention_policy_interval_seconds=1,  # Fast interval for tests
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
def artifact_service(settings: Settings):
    """Create an ArtifactCollectorService with test settings."""
    return ArtifactCollectorService(settings=settings)


@pytest.fixture
def retention_service(
    settings: Settings,
    artifact_service: ArtifactCollectorService,
    run_service: RunService,
    env_service: EnvironmentService,
):
    """Create a RetentionPolicyService with test settings."""
    service = RetentionPolicyService(
        settings=settings,
        artifact_service=artifact_service,
        run_service=run_service,
        environment_service=env_service,
    )
    # Clear default policies for clean tests
    for policy in service.policy_store.list_all():
        service.policy_store.delete(policy.id)
    return service


class TestPolicyCRUD:
    """Tests for retention policy CRUD operations."""

    def test_create_policy(self, retention_service: RetentionPolicyService):
        """Test creating a new retention policy."""
        policy = retention_service.create_policy(
            name="test-policy",
            description="A test policy",
            resource_type=ResourceType.ARTIFACT,
            condition=RetentionCondition.AGE_DAYS,
            threshold=30,
        )

        assert policy.id is not None
        assert policy.name == "test-policy"
        assert policy.description == "A test policy"
        assert policy.resource_type == ResourceType.ARTIFACT
        assert policy.condition == RetentionCondition.AGE_DAYS
        assert policy.threshold == 30
        assert policy.enabled is True
        assert policy.priority == 0

    def test_get_policy(self, retention_service: RetentionPolicyService):
        """Test getting a policy by ID."""
        created = retention_service.create_policy(
            name="get-test",
            resource_type=ResourceType.RUN,
            condition=RetentionCondition.AGE_DAYS,
            threshold=7,
        )

        policy = retention_service.get_policy(created.id)
        assert policy is not None
        assert policy.id == created.id
        assert policy.name == "get-test"

    def test_get_nonexistent_policy(self, retention_service: RetentionPolicyService):
        """Test getting a nonexistent policy."""
        policy = retention_service.get_policy("nonexistent")
        assert policy is None

    def test_list_policies(self, retention_service: RetentionPolicyService):
        """Test listing all policies."""
        retention_service.create_policy(
            name="policy-1",
            resource_type=ResourceType.ARTIFACT,
            condition=RetentionCondition.AGE_DAYS,
            threshold=30,
        )
        retention_service.create_policy(
            name="policy-2",
            resource_type=ResourceType.RUN,
            condition=RetentionCondition.STATUS,
            threshold=3,
            status_value="failed",
        )

        policies = retention_service.list_policies()
        assert len(policies) == 2

    def test_list_policies_by_resource_type(self, retention_service: RetentionPolicyService):
        """Test filtering policies by resource type."""
        retention_service.create_policy(
            name="artifact-policy",
            resource_type=ResourceType.ARTIFACT,
            condition=RetentionCondition.AGE_DAYS,
            threshold=30,
        )
        retention_service.create_policy(
            name="run-policy",
            resource_type=ResourceType.RUN,
            condition=RetentionCondition.AGE_DAYS,
            threshold=7,
        )

        artifact_policies = retention_service.list_policies(resource_type=ResourceType.ARTIFACT)
        assert len(artifact_policies) == 1
        assert artifact_policies[0].name == "artifact-policy"

    def test_list_enabled_policies_only(self, retention_service: RetentionPolicyService):
        """Test filtering to only enabled policies."""
        retention_service.create_policy(
            name="enabled",
            resource_type=ResourceType.ARTIFACT,
            condition=RetentionCondition.AGE_DAYS,
            threshold=30,
            enabled=True,
        )
        retention_service.create_policy(
            name="disabled",
            resource_type=ResourceType.ARTIFACT,
            condition=RetentionCondition.AGE_DAYS,
            threshold=30,
            enabled=False,
        )

        enabled = retention_service.list_policies(enabled_only=True)
        assert len(enabled) == 1
        assert enabled[0].name == "enabled"

    def test_list_policies_sorted_by_priority(self, retention_service: RetentionPolicyService):
        """Test that policies are sorted by priority (highest first)."""
        retention_service.create_policy(
            name="low-priority",
            resource_type=ResourceType.ARTIFACT,
            condition=RetentionCondition.AGE_DAYS,
            threshold=30,
            priority=0,
        )
        retention_service.create_policy(
            name="high-priority",
            resource_type=ResourceType.ARTIFACT,
            condition=RetentionCondition.AGE_DAYS,
            threshold=30,
            priority=10,
        )

        policies = retention_service.list_policies()
        assert policies[0].name == "high-priority"
        assert policies[1].name == "low-priority"

    def test_update_policy(self, retention_service: RetentionPolicyService):
        """Test updating a policy."""
        created = retention_service.create_policy(
            name="original",
            resource_type=ResourceType.ARTIFACT,
            condition=RetentionCondition.AGE_DAYS,
            threshold=30,
        )

        updated = retention_service.update_policy(
            policy_id=created.id,
            name="updated",
            threshold=60,
            enabled=False,
        )

        assert updated is not None
        assert updated.name == "updated"
        assert updated.threshold == 60
        assert updated.enabled is False

    def test_update_nonexistent_policy(self, retention_service: RetentionPolicyService):
        """Test updating a nonexistent policy."""
        updated = retention_service.update_policy(
            policy_id="nonexistent",
            name="new-name",
        )
        assert updated is None

    def test_delete_policy(self, retention_service: RetentionPolicyService):
        """Test deleting a policy."""
        created = retention_service.create_policy(
            name="to-delete",
            resource_type=ResourceType.ARTIFACT,
            condition=RetentionCondition.AGE_DAYS,
            threshold=30,
        )

        assert retention_service.delete_policy(created.id) is True
        assert retention_service.get_policy(created.id) is None

    def test_delete_nonexistent_policy(self, retention_service: RetentionPolicyService):
        """Test deleting a nonexistent policy."""
        assert retention_service.delete_policy("nonexistent") is False


class TestPolicyEvaluation:
    """Tests for policy evaluation logic."""

    def test_evaluate_run_age_policy(
        self,
        retention_service: RetentionPolicyService,
        run_service: RunService,
        settings: Settings,
    ):
        """Test evaluating age-based run policy."""
        # Create a completed run
        run = run_service.create_run(environment_id="env-123", program_id="prog-123")
        run_service.start_run(run.id, job_name="job-123")
        run_service.mark_running(run.id)
        run_service.mark_succeeded(run.id)

        # Make the run old
        run_updated = run_service.get_run(run.id)
        assert run_updated is not None
        run_updated.completed_at = datetime.utcnow() - timedelta(days=10)
        run_service.run_store.update(run.id, run_updated)

        # Create policy for 7-day old runs
        policy = retention_service.create_policy(
            name="old-runs",
            resource_type=ResourceType.RUN,
            condition=RetentionCondition.AGE_DAYS,
            threshold=7,
        )

        # Evaluate
        runs = retention_service._evaluate_run_policy(policy)
        assert len(runs) == 1
        assert runs[0].id == run.id

    def test_evaluate_run_status_policy(
        self,
        retention_service: RetentionPolicyService,
        run_service: RunService,
    ):
        """Test evaluating status-based run policy."""
        # Create a failed run
        run = run_service.create_run(environment_id="env-123", program_id="prog-123")
        run_service.start_run(run.id, job_name="job-123")
        run_service.mark_running(run.id)
        run_service.mark_failed(run.id, error="Test failure")

        # Make it old enough
        run_updated = run_service.get_run(run.id)
        assert run_updated is not None
        run_updated.completed_at = datetime.utcnow() - timedelta(days=5)
        run_service.run_store.update(run.id, run_updated)

        # Create policy for failed runs older than 3 days
        policy = retention_service.create_policy(
            name="old-failed-runs",
            resource_type=ResourceType.RUN,
            condition=RetentionCondition.STATUS,
            threshold=3,
            status_value="failed",
        )

        runs = retention_service._evaluate_run_policy(policy)
        assert len(runs) == 1
        assert runs[0].status == RunExecutionStatus.FAILED

    def test_evaluate_environment_policy(
        self,
        retention_service: RetentionPolicyService,
        env_service: EnvironmentService,
    ):
        """Test evaluating environment policy."""
        # Create a stopped environment
        env = env_service.create_environment("prog-123", "image:tag")
        env_service.update_status(env.id, EnvironmentStatus.READY)
        env_service.start_environment(env.id)
        env_service.update_status(env.id, EnvironmentStatus.RUNNING, container_id="ctr")
        env_service.stop_environment(env.id)
        env_service.mark_stopped(env.id)

        # Create policy with 0-day threshold (immediately matches)
        # Note: The store's update() method auto-updates updated_at, so we use 0-day
        # threshold to ensure matching works regardless of when the env was updated
        policy = retention_service.create_policy(
            name="old-stopped-envs",
            resource_type=ResourceType.ENVIRONMENT,
            condition=RetentionCondition.AGE_DAYS,
            threshold=0,
        )

        envs = retention_service._evaluate_environment_policy(policy)
        assert len(envs) == 1
        assert envs[0].id == env.id

    def test_running_runs_not_matched(
        self,
        retention_service: RetentionPolicyService,
        run_service: RunService,
    ):
        """Test that running runs are not matched by policies."""
        run = run_service.create_run(environment_id="env-123", program_id="prog-123")
        run_service.start_run(run.id, job_name="job-123")
        run_service.mark_running(run.id)
        # Don't complete it

        policy = retention_service.create_policy(
            name="old-runs",
            resource_type=ResourceType.RUN,
            condition=RetentionCondition.AGE_DAYS,
            threshold=0,  # Even with 0-day threshold
        )

        runs = retention_service._evaluate_run_policy(policy)
        assert len(runs) == 0  # Running runs should not be matched


class TestPolicyPreview:
    """Tests for policy preview functionality."""

    def test_preview_policy(
        self,
        retention_service: RetentionPolicyService,
        run_service: RunService,
    ):
        """Test previewing what a policy would delete."""
        # Create old completed runs
        for i in range(3):
            run = run_service.create_run(environment_id=f"env-{i}", program_id="prog-123")
            run_service.start_run(run.id, job_name=f"job-{i}")
            run_service.mark_running(run.id)
            run_service.mark_succeeded(run.id)
            # Make it old
            run_updated = run_service.get_run(run.id)
            assert run_updated is not None
            run_updated.completed_at = datetime.utcnow() - timedelta(days=10)
            run_service.run_store.update(run.id, run_updated)

        policy = retention_service.create_policy(
            name="preview-test",
            resource_type=ResourceType.RUN,
            condition=RetentionCondition.AGE_DAYS,
            threshold=7,
        )

        preview = retention_service.preview_policy(policy.id)
        assert preview is not None
        assert preview.matching_count == 3
        assert len(preview.resource_ids) == 3

    def test_preview_nonexistent_policy(self, retention_service: RetentionPolicyService):
        """Test previewing a nonexistent policy."""
        preview = retention_service.preview_policy("nonexistent")
        assert preview is None


class TestCleanupCycle:
    """Tests for full cleanup cycles."""

    @pytest.mark.asyncio
    async def test_run_cleanup_cycle_empty(self, retention_service: RetentionPolicyService):
        """Test running cleanup cycle with no matching resources."""
        metrics = await retention_service.run_cleanup_cycle()

        assert metrics.policies_evaluated == 0  # No policies created
        assert metrics.artifacts_deleted == 0
        assert metrics.runs_deleted == 0
        assert metrics.environments_cleaned == 0
        assert metrics.duration_seconds >= 0

    @pytest.mark.asyncio
    async def test_run_cleanup_cycle_deletes_old_runs(
        self,
        retention_service: RetentionPolicyService,
        run_service: RunService,
    ):
        """Test cleanup cycle that deletes old runs."""
        # Create old completed runs
        run_ids = []
        for i in range(2):
            run = run_service.create_run(environment_id=f"env-{i}", program_id="prog-123")
            run_service.start_run(run.id, job_name=f"job-{i}")
            run_service.mark_running(run.id)
            run_service.mark_succeeded(run.id)
            run_updated = run_service.get_run(run.id)
            assert run_updated is not None
            run_updated.completed_at = datetime.utcnow() - timedelta(days=10)
            run_service.run_store.update(run.id, run_updated)
            run_ids.append(run.id)

        # Create policy
        retention_service.create_policy(
            name="cleanup-old-runs",
            resource_type=ResourceType.RUN,
            condition=RetentionCondition.AGE_DAYS,
            threshold=7,
        )

        metrics = await retention_service.run_cleanup_cycle()

        assert metrics.policies_evaluated == 1
        assert metrics.runs_deleted == 2

        # Verify runs are deleted
        for run_id in run_ids:
            assert run_service.get_run(run_id) is None

    @pytest.mark.asyncio
    async def test_cleanup_cycle_respects_disabled_policies(
        self,
        retention_service: RetentionPolicyService,
        run_service: RunService,
    ):
        """Test that disabled policies are not evaluated."""
        # Create old run
        run = run_service.create_run(environment_id="env-123", program_id="prog-123")
        run_service.start_run(run.id, job_name="job-123")
        run_service.mark_running(run.id)
        run_service.mark_succeeded(run.id)
        run_updated = run_service.get_run(run.id)
        assert run_updated is not None
        run_updated.completed_at = datetime.utcnow() - timedelta(days=10)
        run_service.run_store.update(run.id, run_updated)

        # Create disabled policy
        retention_service.create_policy(
            name="disabled-policy",
            resource_type=ResourceType.RUN,
            condition=RetentionCondition.AGE_DAYS,
            threshold=7,
            enabled=False,
        )

        metrics = await retention_service.run_cleanup_cycle()

        assert metrics.policies_evaluated == 0  # Disabled policy not evaluated
        assert metrics.runs_deleted == 0
        # Run should still exist
        assert run_service.get_run(run.id) is not None

    def test_get_last_metrics(self, retention_service: RetentionPolicyService):
        """Test getting last cleanup metrics."""
        # No metrics initially
        assert retention_service.get_last_metrics() is None


class TestRetentionPolicyController:
    """Tests for the RetentionPolicyController."""

    @pytest.fixture
    def controller(self, settings: Settings, retention_service: RetentionPolicyService):
        """Create a RetentionPolicyController with test settings."""
        return RetentionPolicyController(settings=settings, retention_service=retention_service)

    def test_controller_not_running_initially(self, controller: RetentionPolicyController):
        """Test that controller is not running initially."""
        assert controller.is_running is False

    @pytest.mark.asyncio
    async def test_controller_start_and_stop(self, controller: RetentionPolicyController):
        """Test starting and stopping the controller."""
        await controller.start()
        assert controller.is_running is True

        await controller.stop()
        assert controller.is_running is False

    @pytest.mark.asyncio
    async def test_controller_disabled_in_settings(
        self,
        retention_service: RetentionPolicyService,
        temp_data_dir: Path,
    ):
        """Test that controller doesn't start when disabled in settings."""
        disabled_settings = Settings(
            data_dir=temp_data_dir,
            retention_policy_enabled=False,
        )
        controller = RetentionPolicyController(
            settings=disabled_settings,
            retention_service=retention_service,
        )

        await controller.start()
        assert controller.is_running is False

    @pytest.mark.asyncio
    async def test_controller_runs_cleanup_cycles(
        self,
        controller: RetentionPolicyController,
        retention_service: RetentionPolicyService,
    ):
        """Test that controller runs cleanup cycles periodically."""
        await controller.start()

        # Wait for at least one cycle to run
        await asyncio.sleep(1.5)

        # Check that at least one cycle ran
        metrics = retention_service.get_last_metrics()
        assert metrics is not None

        await controller.stop()

    @pytest.mark.asyncio
    async def test_controller_double_start(self, controller: RetentionPolicyController):
        """Test that starting twice doesn't create duplicate tasks."""
        await controller.start()
        task1 = controller._task

        await controller.start()  # Should be a no-op
        task2 = controller._task

        assert task1 is task2

        await controller.stop()

    @pytest.mark.asyncio
    async def test_controller_stop_without_start(self, controller: RetentionPolicyController):
        """Test that stopping without starting is safe."""
        await controller.stop()  # Should not raise
        assert controller.is_running is False


class TestDefaultPolicies:
    """Tests for default policy seeding."""

    def test_default_policies_seeded(self, settings: Settings, temp_data_dir: Path):
        """Test that default policies are seeded on first run."""
        # Create a fresh service that will seed defaults
        service = RetentionPolicyService(settings=settings)

        policies = service.list_policies()

        # Check that default policies exist
        policy_names = {p.name for p in policies}
        assert "artifact-30-day" in policy_names
        assert "run-7-day" in policy_names
        assert "failed-run-3-day" in policy_names
        assert "large-artifact-7-day" in policy_names

    def test_default_policies_not_reseeded(self, settings: Settings):
        """Test that default policies are not re-seeded if policies exist."""
        # Create service (will seed defaults)
        service = RetentionPolicyService(settings=settings)
        initial_count = len(service.list_policies())

        # Delete one policy
        policies = service.list_policies()
        if policies:
            service.delete_policy(policies[0].id)

        # Create new service instance
        service2 = RetentionPolicyService(settings=settings)

        # Should not reseed since policies exist
        final_count = len(service2.list_policies())
        assert final_count == initial_count - 1
