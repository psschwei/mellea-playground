"""Tests for EnvironmentService with state machine."""

import tempfile
from pathlib import Path

import pytest

from mellea_api.core.config import Settings
from mellea_api.models.common import EnvironmentStatus
from mellea_api.models.environment import Environment, ResourceLimits
from mellea_api.services.environment import (
    VALID_TRANSITIONS,
    EnvironmentNotFoundError,
    EnvironmentService,
    InvalidStateTransitionError,
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
def env_service(settings: Settings):
    """Create an EnvironmentService with test settings."""
    return EnvironmentService(settings=settings)


class TestEnvironmentModel:
    """Tests for the Environment model."""

    def test_create_environment_default_status(self):
        """Test that new environments start in CREATING status."""
        env = Environment(
            programId="prog-123",
            imageTag="mellea-prog:abc123",
        )
        assert env.status == EnvironmentStatus.CREATING
        assert env.program_id == "prog-123"
        assert env.image_tag == "mellea-prog:abc123"
        assert env.container_id is None
        assert env.error_message is None

    def test_create_environment_with_resource_limits(self):
        """Test creating environment with resource limits."""
        limits = ResourceLimits(cpuCores=2.0, memoryMb=1024, timeoutSeconds=600)
        env = Environment(
            programId="prog-123",
            imageTag="mellea-prog:abc123",
            resourceLimits=limits,
        )
        assert env.resource_limits is not None
        assert env.resource_limits.cpu_cores == 2.0
        assert env.resource_limits.memory_mb == 1024
        assert env.resource_limits.timeout_seconds == 600

    def test_resource_limits_defaults(self):
        """Test ResourceLimits default values."""
        limits = ResourceLimits()
        assert limits.cpu_cores == 1.0
        assert limits.memory_mb == 512
        assert limits.timeout_seconds == 300


class TestStateTransitionValidation:
    """Tests for state machine transition validation."""

    def test_valid_transitions_defined_for_all_states(self):
        """Test that all states have defined transitions."""
        for status in EnvironmentStatus:
            assert status in VALID_TRANSITIONS

    def test_validate_transition_creating_to_ready(self, env_service: EnvironmentService):
        """Test CREATING -> READY is valid."""
        assert env_service._validate_transition(
            EnvironmentStatus.CREATING, EnvironmentStatus.READY
        )

    def test_validate_transition_creating_to_failed(self, env_service: EnvironmentService):
        """Test CREATING -> FAILED is valid."""
        assert env_service._validate_transition(
            EnvironmentStatus.CREATING, EnvironmentStatus.FAILED
        )

    def test_validate_transition_ready_to_starting(self, env_service: EnvironmentService):
        """Test READY -> STARTING is valid."""
        assert env_service._validate_transition(
            EnvironmentStatus.READY, EnvironmentStatus.STARTING
        )

    def test_validate_transition_ready_to_deleting(self, env_service: EnvironmentService):
        """Test READY -> DELETING is valid."""
        assert env_service._validate_transition(
            EnvironmentStatus.READY, EnvironmentStatus.DELETING
        )

    def test_validate_transition_starting_to_running(self, env_service: EnvironmentService):
        """Test STARTING -> RUNNING is valid."""
        assert env_service._validate_transition(
            EnvironmentStatus.STARTING, EnvironmentStatus.RUNNING
        )

    def test_validate_transition_starting_to_failed(self, env_service: EnvironmentService):
        """Test STARTING -> FAILED is valid."""
        assert env_service._validate_transition(
            EnvironmentStatus.STARTING, EnvironmentStatus.FAILED
        )

    def test_validate_transition_running_to_stopping(self, env_service: EnvironmentService):
        """Test RUNNING -> STOPPING is valid."""
        assert env_service._validate_transition(
            EnvironmentStatus.RUNNING, EnvironmentStatus.STOPPING
        )

    def test_validate_transition_running_to_failed(self, env_service: EnvironmentService):
        """Test RUNNING -> FAILED is valid."""
        assert env_service._validate_transition(
            EnvironmentStatus.RUNNING, EnvironmentStatus.FAILED
        )

    def test_validate_transition_stopping_to_stopped(self, env_service: EnvironmentService):
        """Test STOPPING -> STOPPED is valid."""
        assert env_service._validate_transition(
            EnvironmentStatus.STOPPING, EnvironmentStatus.STOPPED
        )

    def test_validate_transition_stopped_to_deleting(self, env_service: EnvironmentService):
        """Test STOPPED -> DELETING is valid."""
        assert env_service._validate_transition(
            EnvironmentStatus.STOPPED, EnvironmentStatus.DELETING
        )

    def test_validate_transition_failed_to_deleting(self, env_service: EnvironmentService):
        """Test FAILED -> DELETING is valid."""
        assert env_service._validate_transition(
            EnvironmentStatus.FAILED, EnvironmentStatus.DELETING
        )

    def test_validate_transition_same_state(self, env_service: EnvironmentService):
        """Test that same-state transitions are allowed (no-op)."""
        for status in EnvironmentStatus:
            assert env_service._validate_transition(status, status)

    def test_validate_transition_invalid_ready_to_stopped(
        self, env_service: EnvironmentService
    ):
        """Test READY -> STOPPED is invalid."""
        assert not env_service._validate_transition(
            EnvironmentStatus.READY, EnvironmentStatus.STOPPED
        )

    def test_validate_transition_invalid_creating_to_running(
        self, env_service: EnvironmentService
    ):
        """Test CREATING -> RUNNING is invalid (must go through READY first)."""
        assert not env_service._validate_transition(
            EnvironmentStatus.CREATING, EnvironmentStatus.RUNNING
        )

    def test_validate_transition_invalid_stopped_to_running(
        self, env_service: EnvironmentService
    ):
        """Test STOPPED -> RUNNING is invalid (must delete and recreate)."""
        assert not env_service._validate_transition(
            EnvironmentStatus.STOPPED, EnvironmentStatus.RUNNING
        )

    def test_validate_transition_invalid_deleting_to_any(
        self, env_service: EnvironmentService
    ):
        """Test DELETING is terminal (no outbound transitions)."""
        for target in EnvironmentStatus:
            if target != EnvironmentStatus.DELETING:
                assert not env_service._validate_transition(
                    EnvironmentStatus.DELETING, target
                )


class TestCRUDOperations:
    """Tests for CRUD operations."""

    def test_create_environment(self, env_service: EnvironmentService):
        """Test creating an environment."""
        env = env_service.create_environment(
            program_id="prog-123",
            image_tag="mellea-prog:abc123",
        )

        assert env.id is not None
        assert env.program_id == "prog-123"
        assert env.image_tag == "mellea-prog:abc123"
        assert env.status == EnvironmentStatus.CREATING

    def test_create_environment_with_resource_limits(self, env_service: EnvironmentService):
        """Test creating an environment with resource limits."""
        limits = ResourceLimits(cpuCores=4.0, memoryMb=2048)

        env = env_service.create_environment(
            program_id="prog-123",
            image_tag="mellea-prog:abc123",
            resource_limits=limits,
        )

        assert env.resource_limits is not None
        assert env.resource_limits.cpu_cores == 4.0
        assert env.resource_limits.memory_mb == 2048

    def test_get_environment(self, env_service: EnvironmentService):
        """Test retrieving an environment by ID."""
        created = env_service.create_environment(
            program_id="prog-123",
            image_tag="mellea-prog:abc123",
        )

        found = env_service.get_environment(created.id)

        assert found is not None
        assert found.id == created.id
        assert found.program_id == created.program_id

    def test_get_environment_not_found(self, env_service: EnvironmentService):
        """Test that getting nonexistent environment returns None."""
        found = env_service.get_environment("nonexistent-id")
        assert found is None

    def test_list_environments_empty(self, env_service: EnvironmentService):
        """Test listing environments when none exist."""
        envs = env_service.list_environments()
        assert envs == []

    def test_list_environments(self, env_service: EnvironmentService):
        """Test listing all environments."""
        env_service.create_environment("prog-1", "image:1")
        env_service.create_environment("prog-2", "image:2")
        env_service.create_environment("prog-3", "image:3")

        envs = env_service.list_environments()
        assert len(envs) == 3

    def test_list_environments_filter_by_program(self, env_service: EnvironmentService):
        """Test filtering environments by program ID."""
        env_service.create_environment("prog-1", "image:1")
        env_service.create_environment("prog-1", "image:2")
        env_service.create_environment("prog-2", "image:3")

        envs = env_service.list_environments(program_id="prog-1")
        assert len(envs) == 2
        assert all(e.program_id == "prog-1" for e in envs)

    def test_list_environments_filter_by_status(self, env_service: EnvironmentService):
        """Test filtering environments by status."""
        env1 = env_service.create_environment("prog-1", "image:1")
        env_service.create_environment("prog-2", "image:2")

        # Move env1 to READY
        env_service.update_status(env1.id, EnvironmentStatus.READY)

        envs = env_service.list_environments(status=EnvironmentStatus.READY)
        assert len(envs) == 1
        assert envs[0].id == env1.id


class TestStatusUpdates:
    """Tests for status update operations."""

    def test_update_status_valid_transition(self, env_service: EnvironmentService):
        """Test valid status transition."""
        env = env_service.create_environment("prog-123", "image:tag")
        updated = env_service.update_status(env.id, EnvironmentStatus.READY)

        assert updated.status == EnvironmentStatus.READY
        assert updated.updated_at > env.created_at

    def test_update_status_with_error(self, env_service: EnvironmentService):
        """Test status update with error message."""
        env = env_service.create_environment("prog-123", "image:tag")
        updated = env_service.update_status(
            env.id, EnvironmentStatus.FAILED, error="Build failed: timeout"
        )

        assert updated.status == EnvironmentStatus.FAILED
        assert updated.error_message == "Build failed: timeout"

    def test_update_status_with_container_id(self, env_service: EnvironmentService):
        """Test status update with container ID."""
        env = env_service.create_environment("prog-123", "image:tag")
        env_service.update_status(env.id, EnvironmentStatus.READY)
        env_service.start_environment(env.id)

        updated = env_service.update_status(
            env.id, EnvironmentStatus.RUNNING, container_id="container-abc123"
        )

        assert updated.status == EnvironmentStatus.RUNNING
        assert updated.container_id == "container-abc123"
        assert updated.started_at is not None

    def test_update_status_sets_stopped_at(self, env_service: EnvironmentService):
        """Test that stopping sets stopped_at timestamp."""
        env = env_service.create_environment("prog-123", "image:tag")
        env_service.update_status(env.id, EnvironmentStatus.READY)
        env_service.start_environment(env.id)
        env_service.update_status(env.id, EnvironmentStatus.RUNNING, container_id="ctr")
        env_service.stop_environment(env.id)

        updated = env_service.update_status(env.id, EnvironmentStatus.STOPPED)

        assert updated.status == EnvironmentStatus.STOPPED
        assert updated.stopped_at is not None

    def test_update_status_invalid_transition(self, env_service: EnvironmentService):
        """Test that invalid transition raises error."""
        env = env_service.create_environment("prog-123", "image:tag")

        with pytest.raises(InvalidStateTransitionError) as exc_info:
            env_service.update_status(env.id, EnvironmentStatus.RUNNING)

        assert "creating" in str(exc_info.value).lower()
        assert "running" in str(exc_info.value).lower()

    def test_update_status_not_found(self, env_service: EnvironmentService):
        """Test that updating nonexistent environment raises error."""
        with pytest.raises(EnvironmentNotFoundError):
            env_service.update_status("nonexistent", EnvironmentStatus.READY)


class TestLifecycleOperations:
    """Tests for lifecycle operations (start, stop, delete)."""

    def test_start_environment(self, env_service: EnvironmentService):
        """Test starting an environment."""
        env = env_service.create_environment("prog-123", "image:tag")
        env_service.update_status(env.id, EnvironmentStatus.READY)

        started = env_service.start_environment(env.id)

        assert started.status == EnvironmentStatus.STARTING

    def test_start_environment_invalid_state(self, env_service: EnvironmentService):
        """Test that starting from wrong state raises error."""
        env = env_service.create_environment("prog-123", "image:tag")

        with pytest.raises(InvalidStateTransitionError):
            env_service.start_environment(env.id)

    def test_start_environment_not_found(self, env_service: EnvironmentService):
        """Test that starting nonexistent environment raises error."""
        with pytest.raises(EnvironmentNotFoundError):
            env_service.start_environment("nonexistent")

    def test_stop_environment(self, env_service: EnvironmentService):
        """Test stopping an environment."""
        env = env_service.create_environment("prog-123", "image:tag")
        env_service.update_status(env.id, EnvironmentStatus.READY)
        env_service.start_environment(env.id)
        env_service.update_status(env.id, EnvironmentStatus.RUNNING, container_id="ctr")

        stopped = env_service.stop_environment(env.id)

        assert stopped.status == EnvironmentStatus.STOPPING

    def test_stop_environment_invalid_state(self, env_service: EnvironmentService):
        """Test that stopping from wrong state raises error."""
        env = env_service.create_environment("prog-123", "image:tag")
        env_service.update_status(env.id, EnvironmentStatus.READY)

        with pytest.raises(InvalidStateTransitionError):
            env_service.stop_environment(env.id)

    def test_stop_environment_not_found(self, env_service: EnvironmentService):
        """Test that stopping nonexistent environment raises error."""
        with pytest.raises(EnvironmentNotFoundError):
            env_service.stop_environment("nonexistent")

    def test_delete_environment_from_ready(self, env_service: EnvironmentService):
        """Test deleting an environment from READY state."""
        env = env_service.create_environment("prog-123", "image:tag")
        env_service.update_status(env.id, EnvironmentStatus.READY)

        result = env_service.delete_environment(env.id)

        assert result is True
        assert env_service.get_environment(env.id) is None

    def test_delete_environment_from_stopped(self, env_service: EnvironmentService):
        """Test deleting an environment from STOPPED state."""
        env = env_service.create_environment("prog-123", "image:tag")
        env_service.update_status(env.id, EnvironmentStatus.READY)
        env_service.start_environment(env.id)
        env_service.update_status(env.id, EnvironmentStatus.RUNNING, container_id="ctr")
        env_service.stop_environment(env.id)
        env_service.update_status(env.id, EnvironmentStatus.STOPPED)

        result = env_service.delete_environment(env.id)

        assert result is True
        assert env_service.get_environment(env.id) is None

    def test_delete_environment_from_failed(self, env_service: EnvironmentService):
        """Test deleting an environment from FAILED state."""
        env = env_service.create_environment("prog-123", "image:tag")
        env_service.update_status(env.id, EnvironmentStatus.FAILED, error="Build error")

        result = env_service.delete_environment(env.id)

        assert result is True
        assert env_service.get_environment(env.id) is None

    def test_delete_environment_invalid_state(self, env_service: EnvironmentService):
        """Test that deleting from invalid state raises error."""
        env = env_service.create_environment("prog-123", "image:tag")

        with pytest.raises(InvalidStateTransitionError):
            env_service.delete_environment(env.id)

    def test_delete_environment_not_found(self, env_service: EnvironmentService):
        """Test that deleting nonexistent environment raises error."""
        with pytest.raises(EnvironmentNotFoundError):
            env_service.delete_environment("nonexistent")


class TestConvenienceMethods:
    """Tests for convenience methods."""

    def test_mark_ready(self, env_service: EnvironmentService):
        """Test mark_ready convenience method."""
        env = env_service.create_environment("prog-123", "image:tag")

        updated = env_service.mark_ready(env.id)

        assert updated.status == EnvironmentStatus.READY

    def test_mark_failed(self, env_service: EnvironmentService):
        """Test mark_failed convenience method."""
        env = env_service.create_environment("prog-123", "image:tag")

        updated = env_service.mark_failed(env.id, "Connection timeout")

        assert updated.status == EnvironmentStatus.FAILED
        assert updated.error_message == "Connection timeout"

    def test_mark_running(self, env_service: EnvironmentService):
        """Test mark_running convenience method."""
        env = env_service.create_environment("prog-123", "image:tag")
        env_service.mark_ready(env.id)
        env_service.start_environment(env.id)

        updated = env_service.mark_running(env.id, "container-xyz")

        assert updated.status == EnvironmentStatus.RUNNING
        assert updated.container_id == "container-xyz"
        assert updated.started_at is not None

    def test_mark_stopped(self, env_service: EnvironmentService):
        """Test mark_stopped convenience method."""
        env = env_service.create_environment("prog-123", "image:tag")
        env_service.mark_ready(env.id)
        env_service.start_environment(env.id)
        env_service.mark_running(env.id, "container-xyz")
        env_service.stop_environment(env.id)

        updated = env_service.mark_stopped(env.id)

        assert updated.status == EnvironmentStatus.STOPPED
        assert updated.stopped_at is not None


class TestFullLifecycle:
    """Integration tests for full environment lifecycle."""

    def test_full_lifecycle_success(self, env_service: EnvironmentService):
        """Test complete lifecycle: create -> build -> start -> stop -> delete."""
        # Create
        env = env_service.create_environment("prog-123", "mellea-prog:abc")
        assert env.status == EnvironmentStatus.CREATING

        # Build succeeds
        env = env_service.mark_ready(env.id)
        assert env.status == EnvironmentStatus.READY

        # Start
        env = env_service.start_environment(env.id)
        assert env.status == EnvironmentStatus.STARTING

        # Container running
        env = env_service.mark_running(env.id, "docker-ctr-123")
        assert env.status == EnvironmentStatus.RUNNING
        assert env.container_id == "docker-ctr-123"
        assert env.started_at is not None

        # Stop
        env = env_service.stop_environment(env.id)
        assert env.status == EnvironmentStatus.STOPPING

        # Container stopped
        env = env_service.mark_stopped(env.id)
        assert env.status == EnvironmentStatus.STOPPED
        assert env.stopped_at is not None

        # Delete
        result = env_service.delete_environment(env.id)
        assert result is True
        assert env_service.get_environment(env.id) is None

    def test_lifecycle_build_failure(self, env_service: EnvironmentService):
        """Test lifecycle with build failure."""
        # Create
        env = env_service.create_environment("prog-123", "mellea-prog:abc")
        assert env.status == EnvironmentStatus.CREATING

        # Build fails
        env = env_service.mark_failed(env.id, "Dockerfile syntax error")
        assert env.status == EnvironmentStatus.FAILED
        assert env.error_message is not None
        assert "Dockerfile" in env.error_message

        # Can delete failed environment
        result = env_service.delete_environment(env.id)
        assert result is True

    def test_lifecycle_runtime_failure(self, env_service: EnvironmentService):
        """Test lifecycle with runtime failure."""
        # Create and build
        env = env_service.create_environment("prog-123", "mellea-prog:abc")
        env_service.mark_ready(env.id)
        env_service.start_environment(env.id)
        env_service.mark_running(env.id, "container-123")

        # Runtime failure
        env = env_service.mark_failed(env.id, "Out of memory")
        assert env.status == EnvironmentStatus.FAILED
        assert env.error_message == "Out of memory"

        # Can delete failed environment
        result = env_service.delete_environment(env.id)
        assert result is True

    def test_multiple_environments_for_same_program(
        self, env_service: EnvironmentService
    ):
        """Test managing multiple environments for the same program."""
        # Create two environments for the same program
        env1 = env_service.create_environment("prog-123", "mellea-prog:v1")
        env2 = env_service.create_environment("prog-123", "mellea-prog:v2")

        # Both should be independent
        assert env1.id != env2.id
        assert env1.program_id == env2.program_id

        # Advance env1 to running
        env_service.mark_ready(env1.id)
        env_service.start_environment(env1.id)
        env_service.mark_running(env1.id, "ctr-1")

        # env2 should still be in creating
        env2_check = env_service.get_environment(env2.id)
        assert env2_check is not None
        assert env2_check.status == EnvironmentStatus.CREATING

        # List should show both
        envs = env_service.list_environments(program_id="prog-123")
        assert len(envs) == 2
