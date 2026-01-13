"""EnvironmentService for managing environment lifecycle with state machine."""

import logging
from datetime import datetime

from mellea_api.core.config import Settings, get_settings
from mellea_api.core.store import JsonStore
from mellea_api.models.common import EnvironmentStatus
from mellea_api.models.environment import Environment, ResourceLimits

logger = logging.getLogger(__name__)


class EnvironmentNotFoundError(Exception):
    """Raised when an environment is not found."""

    pass


class InvalidStateTransitionError(Exception):
    """Raised when an invalid state transition is attempted."""

    pass


# Valid state transitions as a mapping from current state to allowed target states
VALID_TRANSITIONS: dict[EnvironmentStatus, set[EnvironmentStatus]] = {
    EnvironmentStatus.CREATING: {EnvironmentStatus.READY, EnvironmentStatus.FAILED},
    EnvironmentStatus.READY: {EnvironmentStatus.STARTING, EnvironmentStatus.DELETING},
    EnvironmentStatus.STARTING: {EnvironmentStatus.RUNNING, EnvironmentStatus.FAILED},
    EnvironmentStatus.RUNNING: {EnvironmentStatus.STOPPING, EnvironmentStatus.FAILED},
    EnvironmentStatus.STOPPING: {EnvironmentStatus.STOPPED},
    EnvironmentStatus.STOPPED: {EnvironmentStatus.DELETING},
    EnvironmentStatus.FAILED: {EnvironmentStatus.DELETING},
    EnvironmentStatus.DELETING: set(),  # Terminal state, no transitions allowed
}


class EnvironmentService:
    """Service for managing environment lifecycle with state machine semantics.

    Manages the lifecycle of environments from creation through deletion,
    enforcing valid state transitions and tracking container state.

    Example:
        ```python
        service = get_environment_service()

        # Create an environment
        env = service.create_environment(
            program_id="prog-123",
            image_tag="mellea-prog:abc123",
        )

        # Mark as ready after build completes
        env = service.update_status(env.id, EnvironmentStatus.READY)

        # Start the environment
        env = service.start_environment(env.id)

        # Stop when done
        env = service.stop_environment(env.id)

        # Delete to clean up
        service.delete_environment(env.id)
        ```
    """

    def __init__(self, settings: Settings | None = None) -> None:
        """Initialize the EnvironmentService.

        Args:
            settings: Application settings (uses default if not provided)
        """
        self.settings = settings or get_settings()
        self._environment_store: JsonStore[Environment] | None = None

    # -------------------------------------------------------------------------
    # Store Property (lazy initialization)
    # -------------------------------------------------------------------------

    @property
    def environment_store(self) -> JsonStore[Environment]:
        """Get the environment store, initializing if needed."""
        if self._environment_store is None:
            file_path = self.settings.data_dir / "metadata" / "environments.json"
            self._environment_store = JsonStore[Environment](
                file_path=file_path,
                collection_key="environments",
                model_class=Environment,
            )
        return self._environment_store

    # -------------------------------------------------------------------------
    # State Machine Validation
    # -------------------------------------------------------------------------

    def _validate_transition(
        self, current: EnvironmentStatus, target: EnvironmentStatus
    ) -> bool:
        """Validate if a state transition is allowed.

        Args:
            current: Current environment status
            target: Target environment status

        Returns:
            True if transition is valid, False otherwise
        """
        if current == target:
            return True  # No-op transitions are allowed
        allowed = VALID_TRANSITIONS.get(current, set())
        return target in allowed

    def _assert_transition(
        self, env_id: str, current: EnvironmentStatus, target: EnvironmentStatus
    ) -> None:
        """Assert that a state transition is valid, raising if not.

        Args:
            env_id: Environment ID for error messages
            current: Current environment status
            target: Target environment status

        Raises:
            InvalidStateTransitionError: If transition is not valid
        """
        if not self._validate_transition(current, target):
            raise InvalidStateTransitionError(
                f"Invalid transition for environment {env_id}: "
                f"{current.value} -> {target.value}"
            )

    # -------------------------------------------------------------------------
    # CRUD Operations
    # -------------------------------------------------------------------------

    def create_environment(
        self,
        program_id: str,
        image_tag: str,
        resource_limits: ResourceLimits | None = None,
    ) -> Environment:
        """Create a new environment in CREATING status.

        Args:
            program_id: ID of the associated program
            image_tag: Docker image tag for the environment
            resource_limits: Optional resource constraints

        Returns:
            The created Environment
        """
        env = Environment(
            programId=program_id,
            imageTag=image_tag,
            status=EnvironmentStatus.CREATING,
            resourceLimits=resource_limits,
        )
        created = self.environment_store.create(env)
        logger.info(
            f"Created environment {created.id} for program {program_id} "
            f"with image {image_tag}"
        )
        return created

    def get_environment(self, env_id: str) -> Environment | None:
        """Get an environment by ID.

        Args:
            env_id: Environment's unique identifier

        Returns:
            Environment if found, None otherwise
        """
        return self.environment_store.get_by_id(env_id)

    def list_environments(
        self,
        program_id: str | None = None,
        status: EnvironmentStatus | None = None,
    ) -> list[Environment]:
        """List environments with optional filtering.

        Args:
            program_id: Filter by program ID
            status: Filter by status

        Returns:
            List of matching environments
        """
        environments = self.environment_store.list_all()

        if program_id:
            environments = [e for e in environments if e.program_id == program_id]

        if status:
            environments = [e for e in environments if e.status == status]

        return environments

    def update_status(
        self,
        env_id: str,
        status: EnvironmentStatus,
        error: str | None = None,
        container_id: str | None = None,
    ) -> Environment:
        """Update an environment's status with state machine validation.

        Args:
            env_id: Environment's unique identifier
            status: New status to transition to
            error: Error message (used when transitioning to FAILED)
            container_id: Container ID (used when transitioning to RUNNING)

        Returns:
            Updated Environment

        Raises:
            EnvironmentNotFoundError: If environment doesn't exist
            InvalidStateTransitionError: If transition is not valid
        """
        env = self.environment_store.get_by_id(env_id)
        if env is None:
            raise EnvironmentNotFoundError(f"Environment not found: {env_id}")

        self._assert_transition(env_id, env.status, status)

        env.status = status
        env.updated_at = datetime.utcnow()

        if error:
            env.error_message = error

        if container_id:
            env.container_id = container_id

        # Update timestamps based on transition
        if status == EnvironmentStatus.RUNNING:
            env.started_at = datetime.utcnow()
        elif status == EnvironmentStatus.STOPPED:
            env.stopped_at = datetime.utcnow()

        updated = self.environment_store.update(env_id, env)
        if updated is None:
            raise EnvironmentNotFoundError(f"Environment not found: {env_id}")

        logger.info(f"Environment {env_id} transitioned to {status.value}")
        return updated

    # -------------------------------------------------------------------------
    # Lifecycle Operations
    # -------------------------------------------------------------------------

    def start_environment(self, env_id: str) -> Environment:
        """Start an environment (transition READY -> STARTING).

        This initiates the start sequence. The caller is responsible for
        actually starting the container and then calling update_status
        to transition to RUNNING or FAILED.

        Args:
            env_id: Environment's unique identifier

        Returns:
            Updated Environment in STARTING status

        Raises:
            EnvironmentNotFoundError: If environment doesn't exist
            InvalidStateTransitionError: If not in READY status
        """
        env = self.environment_store.get_by_id(env_id)
        if env is None:
            raise EnvironmentNotFoundError(f"Environment not found: {env_id}")

        self._assert_transition(env_id, env.status, EnvironmentStatus.STARTING)

        env.status = EnvironmentStatus.STARTING
        env.updated_at = datetime.utcnow()

        updated = self.environment_store.update(env_id, env)
        if updated is None:
            raise EnvironmentNotFoundError(f"Environment not found: {env_id}")

        logger.info(f"Environment {env_id} starting")
        return updated

    def stop_environment(self, env_id: str) -> Environment:
        """Stop an environment (transition RUNNING -> STOPPING).

        This initiates the stop sequence. The caller is responsible for
        actually stopping the container and then calling update_status
        to transition to STOPPED.

        Args:
            env_id: Environment's unique identifier

        Returns:
            Updated Environment in STOPPING status

        Raises:
            EnvironmentNotFoundError: If environment doesn't exist
            InvalidStateTransitionError: If not in RUNNING status
        """
        env = self.environment_store.get_by_id(env_id)
        if env is None:
            raise EnvironmentNotFoundError(f"Environment not found: {env_id}")

        self._assert_transition(env_id, env.status, EnvironmentStatus.STOPPING)

        env.status = EnvironmentStatus.STOPPING
        env.updated_at = datetime.utcnow()

        updated = self.environment_store.update(env_id, env)
        if updated is None:
            raise EnvironmentNotFoundError(f"Environment not found: {env_id}")

        logger.info(f"Environment {env_id} stopping")
        return updated

    def delete_environment(self, env_id: str) -> bool:
        """Delete an environment.

        Can only delete environments in READY, STOPPED, or FAILED status.
        Transitions to DELETING before removal.

        Args:
            env_id: Environment's unique identifier

        Returns:
            True if deleted successfully

        Raises:
            EnvironmentNotFoundError: If environment doesn't exist
            InvalidStateTransitionError: If not in a deletable status
        """
        env = self.environment_store.get_by_id(env_id)
        if env is None:
            raise EnvironmentNotFoundError(f"Environment not found: {env_id}")

        self._assert_transition(env_id, env.status, EnvironmentStatus.DELETING)

        # Transition to DELETING first
        env.status = EnvironmentStatus.DELETING
        env.updated_at = datetime.utcnow()
        self.environment_store.update(env_id, env)

        # Then delete
        deleted = self.environment_store.delete(env_id)
        if deleted:
            logger.info(f"Deleted environment {env_id}")
        return deleted

    def mark_ready(self, env_id: str) -> Environment:
        """Mark an environment as ready after successful build.

        Convenience method for CREATING -> READY transition.

        Args:
            env_id: Environment's unique identifier

        Returns:
            Updated Environment in READY status
        """
        return self.update_status(env_id, EnvironmentStatus.READY)

    def mark_failed(self, env_id: str, error: str) -> Environment:
        """Mark an environment as failed.

        Convenience method for transitioning to FAILED status.

        Args:
            env_id: Environment's unique identifier
            error: Error message describing the failure

        Returns:
            Updated Environment in FAILED status
        """
        return self.update_status(env_id, EnvironmentStatus.FAILED, error=error)

    def mark_running(self, env_id: str, container_id: str) -> Environment:
        """Mark an environment as running with container ID.

        Convenience method for STARTING -> RUNNING transition.

        Args:
            env_id: Environment's unique identifier
            container_id: Docker container ID

        Returns:
            Updated Environment in RUNNING status
        """
        return self.update_status(
            env_id, EnvironmentStatus.RUNNING, container_id=container_id
        )

    def mark_stopped(self, env_id: str) -> Environment:
        """Mark an environment as stopped.

        Convenience method for STOPPING -> STOPPED transition.

        Args:
            env_id: Environment's unique identifier

        Returns:
            Updated Environment in STOPPED status
        """
        return self.update_status(env_id, EnvironmentStatus.STOPPED)


# Global service instance
_environment_service: EnvironmentService | None = None


def get_environment_service() -> EnvironmentService:
    """Get the global EnvironmentService instance."""
    global _environment_service
    if _environment_service is None:
        _environment_service = EnvironmentService()
    return _environment_service
