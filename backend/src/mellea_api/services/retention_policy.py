"""RetentionPolicyService for managing and executing retention policies."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import datetime
from typing import TYPE_CHECKING

from mellea_api.core.config import Settings, get_settings
from mellea_api.core.store import JsonStore
from mellea_api.models.common import EnvironmentStatus, RunExecutionStatus
from mellea_api.models.retention_policy import (
    PolicyPreviewResult,
    ResourceType,
    RetentionCondition,
    RetentionMetrics,
    RetentionPolicy,
)
from mellea_api.services.artifact_collector import (
    ArtifactCollectorService,
    get_artifact_collector_service,
)
from mellea_api.services.environment import EnvironmentService, get_environment_service
from mellea_api.services.run import RunService, get_run_service

if TYPE_CHECKING:
    from mellea_api.models.artifact import Artifact
    from mellea_api.models.environment import Environment
    from mellea_api.models.run import Run

logger = logging.getLogger(__name__)


# Default policies to seed on first run
DEFAULT_POLICIES: list[dict[str, str | int | bool | ResourceType | RetentionCondition | None]] = [
    {
        "name": "artifact-30-day",
        "description": "Delete artifacts older than 30 days",
        "resource_type": ResourceType.ARTIFACT,
        "condition": RetentionCondition.AGE_DAYS,
        "threshold": 30,
        "enabled": True,
        "priority": 0,
    },
    {
        "name": "run-7-day",
        "description": "Delete completed runs older than 7 days",
        "resource_type": ResourceType.RUN,
        "condition": RetentionCondition.AGE_DAYS,
        "threshold": 7,
        "enabled": True,
        "priority": 0,
    },
    {
        "name": "failed-run-3-day",
        "description": "Delete failed runs older than 3 days",
        "resource_type": ResourceType.RUN,
        "condition": RetentionCondition.STATUS,
        "threshold": 3,  # days old
        "status_value": "failed",
        "enabled": True,
        "priority": 1,  # Higher priority, evaluated first
    },
    {
        "name": "large-artifact-7-day",
        "description": "Delete artifacts larger than 500MB after 7 days",
        "resource_type": ResourceType.ARTIFACT,
        "condition": RetentionCondition.SIZE_BYTES,
        "threshold": 500 * 1024 * 1024,  # 500MB in bytes
        "enabled": True,
        "priority": 1,
    },
]


class RetentionPolicyService:
    """Service for managing and executing retention policies.

    Provides CRUD operations for retention policies and methods to evaluate
    and apply policies for automatic resource cleanup.

    Example:
        ```python
        service = get_retention_policy_service()

        # Create a custom policy
        policy = service.create_policy(
            name="old-logs",
            description="Delete logs older than 14 days",
            resource_type=ResourceType.LOG,
            condition=RetentionCondition.AGE_DAYS,
            threshold=14,
        )

        # Preview what would be deleted
        preview = service.preview_policy(policy.id)
        print(f"Would delete {preview.matching_count} resources")

        # Run cleanup cycle
        metrics = await service.run_cleanup_cycle()
        print(f"Deleted {metrics.artifacts_deleted} artifacts")
        ```
    """

    def __init__(
        self,
        settings: Settings | None = None,
        artifact_service: ArtifactCollectorService | None = None,
        run_service: RunService | None = None,
        environment_service: EnvironmentService | None = None,
    ) -> None:
        """Initialize the RetentionPolicyService.

        Args:
            settings: Application settings (uses default if not provided)
            artifact_service: Optional ArtifactCollectorService instance
            run_service: Optional RunService instance
            environment_service: Optional EnvironmentService instance
        """
        self.settings = settings or get_settings()
        self._policy_store: JsonStore[RetentionPolicy] | None = None
        self._artifact_service = artifact_service
        self._run_service = run_service
        self._environment_service = environment_service
        self._last_run_metrics: RetentionMetrics | None = None
        self._seeded = False

    # -------------------------------------------------------------------------
    # Store and Service Properties (lazy initialization)
    # -------------------------------------------------------------------------

    @property
    def policy_store(self) -> JsonStore[RetentionPolicy]:
        """Get the policy store, initializing if needed."""
        if self._policy_store is None:
            file_path = self.settings.data_dir / "metadata" / "retention_policies.json"
            self._policy_store = JsonStore[RetentionPolicy](
                file_path=file_path,
                collection_key="policies",
                model_class=RetentionPolicy,
            )
            # Seed default policies if this is the first time
            if not self._seeded:
                self._seed_default_policies()
                self._seeded = True
        return self._policy_store

    @property
    def artifact_service(self) -> ArtifactCollectorService:
        """Get the artifact service instance."""
        if self._artifact_service is None:
            self._artifact_service = get_artifact_collector_service()
        return self._artifact_service

    @property
    def run_service(self) -> RunService:
        """Get the run service instance."""
        if self._run_service is None:
            self._run_service = get_run_service()
        return self._run_service

    @property
    def environment_service(self) -> EnvironmentService:
        """Get the environment service instance."""
        if self._environment_service is None:
            self._environment_service = get_environment_service()
        return self._environment_service

    # -------------------------------------------------------------------------
    # Default Policy Seeding
    # -------------------------------------------------------------------------

    def _seed_default_policies(self) -> None:
        """Seed default retention policies if none exist."""
        existing = self._policy_store.list_all() if self._policy_store else []
        if existing:
            return  # Don't seed if policies already exist

        logger.info("Seeding default retention policies")
        for policy_data in DEFAULT_POLICIES:
            name = str(policy_data["name"])
            description = policy_data.get("description")
            resource_type = policy_data["resource_type"]
            condition = policy_data["condition"]
            threshold = policy_data["threshold"]
            status_value = policy_data.get("status_value")
            enabled = policy_data.get("enabled", True)
            priority = policy_data.get("priority", 0)

            # Type assertions for mypy
            assert isinstance(resource_type, ResourceType)
            assert isinstance(condition, RetentionCondition)
            assert isinstance(threshold, int)
            assert isinstance(enabled, bool)
            assert isinstance(priority, int)

            policy = RetentionPolicy(
                name=name,
                description=str(description) if description else None,
                resource_type=resource_type,
                condition=condition,
                threshold=threshold,
                status_value=str(status_value) if status_value else None,
                enabled=enabled,
                priority=priority,
            )
            if self._policy_store:
                self._policy_store.create(policy)
                logger.info(f"Created default policy: {policy.name}")

    # -------------------------------------------------------------------------
    # CRUD Operations
    # -------------------------------------------------------------------------

    def create_policy(
        self,
        name: str,
        resource_type: ResourceType,
        condition: RetentionCondition,
        threshold: int,
        description: str | None = None,
        status_value: str | None = None,
        enabled: bool = True,
        priority: int = 0,
        user_id: str | None = None,
    ) -> RetentionPolicy:
        """Create a new retention policy.

        Args:
            name: Human-readable name for the policy
            resource_type: Type of resource this policy applies to
            condition: The condition type to evaluate
            threshold: Value for the condition
            description: Optional description
            status_value: Status value when condition is STATUS
            enabled: Whether the policy is active
            priority: Higher priority policies are evaluated first
            user_id: Owner of the policy (None = system-wide)

        Returns:
            The created RetentionPolicy
        """
        policy = RetentionPolicy(
            name=name,
            description=description,
            resource_type=resource_type,
            condition=condition,
            threshold=threshold,
            status_value=status_value,
            enabled=enabled,
            priority=priority,
            user_id=user_id,
        )
        created = self.policy_store.create(policy)
        logger.info(f"Created retention policy: {created.id} ({created.name})")
        return created

    def get_policy(self, policy_id: str) -> RetentionPolicy | None:
        """Get a policy by ID.

        Args:
            policy_id: Policy's unique identifier

        Returns:
            RetentionPolicy if found, None otherwise
        """
        return self.policy_store.get_by_id(policy_id)

    def list_policies(
        self,
        resource_type: ResourceType | None = None,
        enabled_only: bool = False,
        user_id: str | None = None,
    ) -> list[RetentionPolicy]:
        """List policies with optional filtering.

        Args:
            resource_type: Filter by resource type
            enabled_only: Only return enabled policies
            user_id: Filter by user ID (None = all policies)

        Returns:
            List of matching policies sorted by priority (highest first)
        """
        policies = self.policy_store.list_all()

        if resource_type:
            policies = [p for p in policies if p.resource_type == resource_type]

        if enabled_only:
            policies = [p for p in policies if p.enabled]

        if user_id is not None:
            # Include user's policies and system-wide policies
            policies = [p for p in policies if p.user_id == user_id or p.user_id is None]

        # Sort by priority (highest first)
        policies.sort(key=lambda p: p.priority, reverse=True)

        return policies

    def update_policy(
        self,
        policy_id: str,
        name: str | None = None,
        description: str | None = None,
        threshold: int | None = None,
        status_value: str | None = None,
        enabled: bool | None = None,
        priority: int | None = None,
    ) -> RetentionPolicy | None:
        """Update an existing policy.

        Args:
            policy_id: Policy's unique identifier
            name: New name (optional)
            description: New description (optional)
            threshold: New threshold value (optional)
            status_value: New status value (optional)
            enabled: New enabled state (optional)
            priority: New priority (optional)

        Returns:
            Updated RetentionPolicy if found, None otherwise
        """
        policy = self.policy_store.get_by_id(policy_id)
        if policy is None:
            return None

        if name is not None:
            policy.name = name
        if description is not None:
            policy.description = description
        if threshold is not None:
            policy.threshold = threshold
        if status_value is not None:
            policy.status_value = status_value
        if enabled is not None:
            policy.enabled = enabled
        if priority is not None:
            policy.priority = priority

        policy.updated_at = datetime.utcnow()

        updated = self.policy_store.update(policy_id, policy)
        if updated:
            logger.info(f"Updated retention policy: {policy_id}")
        return updated

    def delete_policy(self, policy_id: str) -> bool:
        """Delete a policy by ID.

        Args:
            policy_id: Policy's unique identifier

        Returns:
            True if deleted, False if not found
        """
        deleted = self.policy_store.delete(policy_id)
        if deleted:
            logger.info(f"Deleted retention policy: {policy_id}")
        return deleted

    # -------------------------------------------------------------------------
    # Policy Evaluation
    # -------------------------------------------------------------------------

    def _evaluate_artifact_policy(self, policy: RetentionPolicy) -> list[Artifact]:
        """Evaluate a policy against artifacts.

        Args:
            policy: The retention policy to evaluate

        Returns:
            List of artifacts that match the policy
        """
        artifacts = self.artifact_service.artifact_store.list_all()
        now = datetime.utcnow()
        matching: list[Artifact] = []

        for artifact in artifacts:
            if policy.condition == RetentionCondition.AGE_DAYS:
                age_days = (now - artifact.created_at).days
                if age_days >= policy.threshold:
                    matching.append(artifact)

            elif policy.condition == RetentionCondition.SIZE_BYTES:
                # For size-based policies, also check age (threshold is size, use 7 days as default age)
                age_days = (now - artifact.created_at).days
                if artifact.size_bytes >= policy.threshold and age_days >= 7:
                    matching.append(artifact)

            elif policy.condition == RetentionCondition.UNUSED_DAYS:
                # For now, use created_at as proxy for last access
                # In a real implementation, we'd track last_accessed_at
                unused_days = (now - artifact.created_at).days
                if unused_days >= policy.threshold:
                    matching.append(artifact)

        return matching

    def _evaluate_run_policy(self, policy: RetentionPolicy) -> list[Run]:
        """Evaluate a policy against runs.

        Args:
            policy: The retention policy to evaluate

        Returns:
            List of runs that match the policy
        """
        runs = self.run_service.run_store.list_all()
        now = datetime.utcnow()
        matching: list[Run] = []

        # Only consider completed runs
        terminal_statuses = {
            RunExecutionStatus.SUCCEEDED,
            RunExecutionStatus.FAILED,
            RunExecutionStatus.CANCELLED,
        }

        for run in runs:
            if run.status not in terminal_statuses:
                continue

            completed_at = run.completed_at or run.created_at

            if policy.condition == RetentionCondition.AGE_DAYS:
                age_days = (now - completed_at).days
                if age_days >= policy.threshold:
                    matching.append(run)

            elif policy.condition == RetentionCondition.STATUS:
                # Status-based policy: match status AND age threshold
                if policy.status_value and run.status.value == policy.status_value:
                    age_days = (now - completed_at).days
                    if age_days >= policy.threshold:
                        matching.append(run)

        return matching

    def _evaluate_environment_policy(self, policy: RetentionPolicy) -> list[Environment]:
        """Evaluate a policy against environments.

        Args:
            policy: The retention policy to evaluate

        Returns:
            List of environments that match the policy
        """
        environments = self.environment_service.environment_store.list_all()
        now = datetime.utcnow()
        matching: list[Environment] = []

        # Only consider stopped or failed environments
        cleanable_statuses = {
            EnvironmentStatus.STOPPED,
            EnvironmentStatus.FAILED,
        }

        for env in environments:
            if env.status not in cleanable_statuses:
                continue

            if policy.condition == RetentionCondition.AGE_DAYS:
                age_days = (now - env.updated_at).days
                if age_days >= policy.threshold:
                    matching.append(env)

            elif policy.condition == RetentionCondition.STATUS:
                if policy.status_value and env.status.value == policy.status_value:
                    age_days = (now - env.updated_at).days
                    if age_days >= policy.threshold:
                        matching.append(env)

            elif policy.condition == RetentionCondition.UNUSED_DAYS:
                unused_days = (now - env.updated_at).days
                if unused_days >= policy.threshold:
                    matching.append(env)

        return matching

    def preview_policy(self, policy_id: str) -> PolicyPreviewResult | None:
        """Preview what resources a policy would delete.

        Args:
            policy_id: Policy's unique identifier

        Returns:
            PolicyPreviewResult with matching resources, or None if policy not found
        """
        policy = self.policy_store.get_by_id(policy_id)
        if policy is None:
            return None

        resource_ids: list[str] = []
        total_size = 0

        if policy.resource_type == ResourceType.ARTIFACT:
            artifacts = self._evaluate_artifact_policy(policy)
            resource_ids = [a.id for a in artifacts]
            total_size = sum(a.size_bytes for a in artifacts)

        elif policy.resource_type == ResourceType.RUN:
            runs = self._evaluate_run_policy(policy)
            resource_ids = [r.id for r in runs]

        elif policy.resource_type == ResourceType.ENVIRONMENT:
            environments = self._evaluate_environment_policy(policy)
            resource_ids = [e.id for e in environments]

        return PolicyPreviewResult(
            policy_id=policy_id,
            resource_type=policy.resource_type,
            matching_count=len(resource_ids),
            total_size_bytes=total_size,
            resource_ids=resource_ids,
        )

    # -------------------------------------------------------------------------
    # Policy Application
    # -------------------------------------------------------------------------

    def _apply_artifact_policy(self, policy: RetentionPolicy) -> tuple[int, int, list[str]]:
        """Apply a policy to delete matching artifacts.

        Args:
            policy: The retention policy to apply

        Returns:
            Tuple of (deleted_count, bytes_freed, errors)
        """
        artifacts = self._evaluate_artifact_policy(policy)
        deleted = 0
        bytes_freed = 0
        errors: list[str] = []

        for artifact in artifacts:
            try:
                size = artifact.size_bytes
                if self.artifact_service.delete_artifact(artifact.id):
                    deleted += 1
                    bytes_freed += size
                    logger.debug(f"Policy {policy.name}: deleted artifact {artifact.id}")
            except Exception as e:
                errors.append(f"Failed to delete artifact {artifact.id}: {e}")
                logger.error(f"Policy {policy.name}: failed to delete artifact {artifact.id}: {e}")

        return deleted, bytes_freed, errors

    def _apply_run_policy(self, policy: RetentionPolicy) -> tuple[int, list[str]]:
        """Apply a policy to delete matching runs.

        Args:
            policy: The retention policy to apply

        Returns:
            Tuple of (deleted_count, errors)
        """
        runs = self._evaluate_run_policy(policy)
        deleted = 0
        errors: list[str] = []

        for run in runs:
            try:
                if self.run_service.run_store.delete(run.id):
                    deleted += 1
                    logger.debug(f"Policy {policy.name}: deleted run {run.id}")
            except Exception as e:
                errors.append(f"Failed to delete run {run.id}: {e}")
                logger.error(f"Policy {policy.name}: failed to delete run {run.id}: {e}")

        return deleted, errors

    def _apply_environment_policy(self, policy: RetentionPolicy) -> tuple[int, list[str]]:
        """Apply a policy to clean up matching environments.

        Args:
            policy: The retention policy to apply

        Returns:
            Tuple of (cleaned_count, errors)
        """
        environments = self._evaluate_environment_policy(policy)
        cleaned = 0
        errors: list[str] = []

        for env in environments:
            try:
                if self.environment_service.delete_environment(env.id):
                    cleaned += 1
                    logger.debug(f"Policy {policy.name}: cleaned environment {env.id}")
            except Exception as e:
                errors.append(f"Failed to clean environment {env.id}: {e}")
                logger.error(f"Policy {policy.name}: failed to clean environment {env.id}: {e}")

        return cleaned, errors

    # -------------------------------------------------------------------------
    # Cleanup Cycle
    # -------------------------------------------------------------------------

    async def run_cleanup_cycle(self) -> RetentionMetrics:
        """Run a full cleanup cycle evaluating all enabled policies.

        This method:
        1. Gets all enabled policies sorted by priority
        2. Evaluates each policy against its target resource type
        3. Deletes/cleans matching resources
        4. Records metrics about the cleanup

        Returns:
            RetentionMetrics with statistics about the cleanup
        """
        start_time = datetime.utcnow()
        metrics = RetentionMetrics(timestamp=start_time)

        logger.info("Starting retention policy cleanup cycle")

        # Get all enabled policies sorted by priority
        policies = self.list_policies(enabled_only=True)
        metrics.policies_evaluated = len(policies)

        for policy in policies:
            try:
                if policy.resource_type == ResourceType.ARTIFACT:
                    deleted, bytes_freed, errors = self._apply_artifact_policy(policy)
                    metrics.artifacts_deleted += deleted
                    metrics.storage_freed_bytes += bytes_freed
                    metrics.errors.extend(errors)

                elif policy.resource_type == ResourceType.RUN:
                    deleted, errors = self._apply_run_policy(policy)
                    metrics.runs_deleted += deleted
                    metrics.errors.extend(errors)

                elif policy.resource_type == ResourceType.ENVIRONMENT:
                    cleaned, errors = self._apply_environment_policy(policy)
                    metrics.environments_cleaned += cleaned
                    metrics.errors.extend(errors)

                elif policy.resource_type == ResourceType.LOG:
                    # Log cleanup not implemented yet
                    pass

            except Exception as e:
                error_msg = f"Error evaluating policy {policy.id} ({policy.name}): {e}"
                metrics.errors.append(error_msg)
                logger.error(error_msg)

        # Calculate duration
        end_time = datetime.utcnow()
        metrics.duration_seconds = (end_time - start_time).total_seconds()

        self._last_run_metrics = metrics

        logger.info(
            f"Retention cleanup cycle complete: "
            f"evaluated {metrics.policies_evaluated} policies, "
            f"deleted {metrics.artifacts_deleted} artifacts, "
            f"deleted {metrics.runs_deleted} runs, "
            f"cleaned {metrics.environments_cleaned} environments, "
            f"freed {metrics.storage_freed_bytes} bytes, "
            f"duration {metrics.duration_seconds:.2f}s"
        )

        return metrics

    def get_last_metrics(self) -> RetentionMetrics | None:
        """Get metrics from the last cleanup run.

        Returns:
            Last RetentionMetrics or None if no run has occurred
        """
        return self._last_run_metrics


class RetentionPolicyController:
    """Background controller that periodically runs retention policy cleanup cycles.

    This controller manages the background task that calls the RetentionPolicyService
    at regular intervals to clean up resources based on configured policies.

    Example:
        ```python
        controller = RetentionPolicyController()
        await controller.start()  # Start background cleanup
        # ... application runs ...
        await controller.stop()   # Stop on shutdown
        ```
    """

    def __init__(
        self,
        settings: Settings | None = None,
        retention_service: RetentionPolicyService | None = None,
    ) -> None:
        """Initialize the controller.

        Args:
            settings: Application settings (uses default if not provided)
            retention_service: Optional RetentionPolicyService instance
        """
        self.settings = settings or get_settings()
        self._retention_service = retention_service
        self._task: asyncio.Task[None] | None = None
        self._running = False

    @property
    def retention_service(self) -> RetentionPolicyService:
        """Get the retention policy service instance."""
        if self._retention_service is None:
            self._retention_service = get_retention_policy_service()
        return self._retention_service

    @property
    def is_running(self) -> bool:
        """Check if the controller is running."""
        return self._running and self._task is not None

    async def _run_loop(self) -> None:
        """Background loop that runs cleanup cycles at configured intervals."""
        interval = self.settings.retention_policy_interval_seconds
        logger.info(
            f"Retention policy controller started, running every {interval} seconds"
        )

        while self._running:
            try:
                await self.retention_service.run_cleanup_cycle()
            except Exception as e:
                logger.error(f"Error in retention policy cleanup cycle: {e}")

            # Sleep for the configured interval
            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break

        logger.info("Retention policy controller stopped")

    async def start(self) -> None:
        """Start the background cleanup controller.

        Does nothing if controller is disabled in settings or already running.
        """
        if not self.settings.retention_policy_enabled:
            logger.info("Retention policy controller is disabled in settings")
            return

        if self._running:
            logger.warning("Retention policy controller is already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("Retention policy controller background task created")

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

        logger.info("Retention policy controller stopped")


# Global service instances
_retention_policy_service: RetentionPolicyService | None = None
_retention_policy_controller: RetentionPolicyController | None = None


def get_retention_policy_service() -> RetentionPolicyService:
    """Get the global RetentionPolicyService instance."""
    global _retention_policy_service
    if _retention_policy_service is None:
        _retention_policy_service = RetentionPolicyService()
    return _retention_policy_service


def get_retention_policy_controller() -> RetentionPolicyController:
    """Get the global RetentionPolicyController instance."""
    global _retention_policy_controller
    if _retention_policy_controller is None:
        _retention_policy_controller = RetentionPolicyController()
    return _retention_policy_controller
