"""WarmupService for pre-building and maintaining warm environment pools."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from mellea_api.core.config import Settings, get_settings
from mellea_api.core.store import JsonStore
from mellea_api.models.build import LayerCacheEntry
from mellea_api.models.common import EnvironmentStatus
from mellea_api.services.assets import AssetService, get_asset_service
from mellea_api.services.environment import EnvironmentService, get_environment_service
from mellea_api.services.environment_builder import (
    EnvironmentBuilderService,
    get_environment_builder_service,
)

if TYPE_CHECKING:
    from mellea_api.models.environment import Environment

logger = logging.getLogger(__name__)


@dataclass
class WarmEnvironment:
    """A pre-warmed environment ready for fast allocation."""

    environment_id: str
    program_id: str
    image_tag: str
    cache_key: str
    created_at: datetime
    status: str


@dataclass
class WarmupMetrics:
    """Metrics from a warmup cycle."""

    timestamp: datetime = field(default_factory=datetime.utcnow)
    warm_pool_size: int = 0
    environments_created: int = 0
    environments_recycled: int = 0
    layers_pre_built: int = 0
    errors: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0


@dataclass
class PopularDependency:
    """A popular dependency set that should be pre-built."""

    cache_key: str
    image_tag: str
    use_count: int
    last_used_at: datetime


class WarmupService:
    """Service for maintaining warm environment pools for faster starts.

    Pre-builds popular dependency layers and maintains a pool of ready
    environments that can be quickly assigned to run requests.

    Example:
        ```python
        service = get_warmup_service()

        # Get the current warm pool status
        status = service.get_pool_status()
        print(f"Warm environments: {status['warm_count']}")

        # Run a warmup cycle
        metrics = await service.run_warmup_cycle()
        print(f"Created {metrics.environments_created} new warm envs")
        ```
    """

    def __init__(
        self,
        settings: Settings | None = None,
        environment_service: EnvironmentService | None = None,
        environment_builder: EnvironmentBuilderService | None = None,
        asset_service: AssetService | None = None,
    ) -> None:
        """Initialize the WarmupService.

        Args:
            settings: Application settings (uses default if not provided)
            environment_service: Optional EnvironmentService instance
            environment_builder: Optional EnvironmentBuilderService instance
            asset_service: Optional AssetService instance
        """
        self.settings = settings or get_settings()
        self._environment_service = environment_service
        self._environment_builder = environment_builder
        self._asset_service = asset_service
        self._last_metrics: WarmupMetrics | None = None

    @property
    def environment_service(self) -> EnvironmentService:
        """Get the environment service instance."""
        if self._environment_service is None:
            self._environment_service = get_environment_service()
        return self._environment_service

    @property
    def environment_builder(self) -> EnvironmentBuilderService:
        """Get the environment builder service instance."""
        if self._environment_builder is None:
            self._environment_builder = get_environment_builder_service()
        return self._environment_builder

    @property
    def asset_service(self) -> AssetService:
        """Get the asset service instance."""
        if self._asset_service is None:
            self._asset_service = get_asset_service()
        return self._asset_service

    def get_popular_dependencies(self, limit: int | None = None) -> list[PopularDependency]:
        """Get the most popular dependency sets based on usage.

        Args:
            limit: Maximum number of results (uses config default if None)

        Returns:
            List of PopularDependency sorted by use_count descending
        """
        if limit is None:
            limit = self.settings.warmup_popular_deps_count

        cache_entries = self.environment_builder.cache_store.list_all()

        # Sort by use_count descending
        sorted_entries = sorted(cache_entries, key=lambda e: e.use_count, reverse=True)

        return [
            PopularDependency(
                cache_key=entry.cache_key,
                image_tag=entry.image_tag,
                use_count=entry.use_count,
                last_used_at=entry.last_used_at,
            )
            for entry in sorted_entries[:limit]
        ]

    def get_warm_environments(self) -> list[Environment]:
        """Get all currently warm (READY) environments.

        Returns:
            List of environments in READY status
        """
        return self.environment_service.list_environments(status=EnvironmentStatus.READY)

    def get_stale_warm_environments(self) -> list[Environment]:
        """Find warm environments that are too old and should be recycled.

        Returns:
            List of READY environments older than warmup_max_age_minutes
        """
        warm_envs = self.get_warm_environments()
        max_age = timedelta(minutes=self.settings.warmup_max_age_minutes)
        now = datetime.utcnow()

        return [env for env in warm_envs if now - env.created_at > max_age]

    def get_pool_status(self) -> dict:
        """Get current status of the warm pool.

        Returns:
            Dictionary with pool statistics
        """
        warm_envs = self.get_warm_environments()
        stale_envs = self.get_stale_warm_environments()
        popular_deps = self.get_popular_dependencies()

        return {
            "enabled": self.settings.warmup_enabled,
            "target_pool_size": self.settings.warmup_pool_size,
            "current_pool_size": len(warm_envs),
            "stale_count": len(stale_envs),
            "popular_dependencies_count": len(popular_deps),
            "warm_environments": [
                {
                    "id": env.id,
                    "program_id": env.program_id,
                    "image_tag": env.image_tag,
                    "created_at": env.created_at.isoformat(),
                    "age_minutes": (datetime.utcnow() - env.created_at).total_seconds() / 60,
                }
                for env in warm_envs
            ],
            "thresholds": {
                "max_age_minutes": self.settings.warmup_max_age_minutes,
                "check_interval_seconds": self.settings.warmup_interval_seconds,
            },
        }

    def recycle_stale_environment(self, env_id: str) -> bool:
        """Delete a stale warm environment.

        Args:
            env_id: Environment ID to recycle

        Returns:
            True if successfully deleted, False otherwise
        """
        try:
            env = self.environment_service.get_environment(env_id)
            if env is None:
                return False

            if env.status == EnvironmentStatus.READY:
                self.environment_service.delete_environment(env_id)
                logger.info(f"Recycled stale warm environment {env_id}")
                return True

            return False
        except Exception as e:
            logger.error(f"Failed to recycle environment {env_id}: {e}")
            return False

    def create_warm_environment(self, program_id: str) -> Environment | None:
        """Create a new warm environment for a program.

        Builds the image and creates an environment in READY state.

        Args:
            program_id: Program ID to create environment for

        Returns:
            Created Environment or None if failed
        """
        try:
            # Get the program
            program = self.asset_service.get_program(program_id)
            if program is None:
                logger.warning(f"Program {program_id} not found for warmup")
                return None

            # Build the image
            result = self.environment_builder.build_image(program_id)
            if not result.success or not result.image_tag:
                logger.error(f"Failed to build image for warmup: {result.error_message}")
                return None

            # Create the environment
            env = self.environment_service.create_environment(
                program_id=program_id,
                image_tag=result.image_tag,
            )

            # Mark as ready
            env = self.environment_service.mark_ready(env.id)
            logger.info(f"Created warm environment {env.id} for program {program_id}")

            return env

        except Exception as e:
            logger.error(f"Failed to create warm environment for {program_id}: {e}")
            return None

    def get_warm_environment_for_program(self, program_id: str) -> Environment | None:
        """Get an available warm environment for a specific program.

        Args:
            program_id: Program ID to find warm environment for

        Returns:
            Available warm Environment or None if none available
        """
        warm_envs = self.get_warm_environments()

        for env in warm_envs:
            if env.program_id == program_id:
                return env

        return None

    async def run_warmup_cycle(self) -> WarmupMetrics:
        """Run a full warmup cycle.

        This method:
        1. Recycles stale warm environments
        2. Creates new warm environments to maintain pool size
        3. Pre-builds popular dependency layers

        Returns:
            WarmupMetrics with statistics about the cycle
        """
        start_time = datetime.utcnow()
        metrics = WarmupMetrics(timestamp=start_time)

        logger.info("Starting warmup cycle")

        # 1. Recycle stale environments
        stale_envs = self.get_stale_warm_environments()
        for env in stale_envs:
            if self.recycle_stale_environment(env.id):
                metrics.environments_recycled += 1
            else:
                metrics.errors.append(f"Failed to recycle env {env.id}")

        # 2. Check pool size and create new warm environments if needed
        current_warm = self.get_warm_environments()
        metrics.warm_pool_size = len(current_warm)

        needed = self.settings.warmup_pool_size - len(current_warm)

        if needed > 0:
            # Get programs to warm up (prioritize recently used)
            programs = self.asset_service.list_programs()

            # Sort by last_run_at if available
            programs_sorted = sorted(
                programs,
                key=lambda p: p.last_run_at or datetime.min,
                reverse=True,
            )

            # Filter out programs that already have warm environments
            warm_program_ids = {env.program_id for env in current_warm}
            programs_to_warm = [
                p for p in programs_sorted if p.id not in warm_program_ids
            ][:needed]

            for program in programs_to_warm:
                env = self.create_warm_environment(program.id)
                if env:
                    metrics.environments_created += 1
                else:
                    metrics.errors.append(f"Failed to warm program {program.id}")

        # Update final pool size
        metrics.warm_pool_size = len(self.get_warm_environments())

        # Calculate duration
        end_time = datetime.utcnow()
        metrics.duration_seconds = (end_time - start_time).total_seconds()

        self._last_metrics = metrics

        logger.info(
            f"Warmup cycle complete: "
            f"pool_size={metrics.warm_pool_size}, "
            f"created={metrics.environments_created}, "
            f"recycled={metrics.environments_recycled}, "
            f"duration={metrics.duration_seconds:.2f}s"
        )

        return metrics

    def get_last_metrics(self) -> WarmupMetrics | None:
        """Get metrics from the last warmup cycle.

        Returns:
            Last WarmupMetrics or None if no cycle has run
        """
        return self._last_metrics


class WarmupController:
    """Background controller that maintains the warm pool.

    Runs warmup cycles at regular intervals to ensure environments
    are pre-built and ready for fast allocation.

    Example:
        ```python
        controller = get_warmup_controller()
        await controller.start()  # Start background warmup
        # ... application runs ...
        await controller.stop()   # Stop on shutdown
        ```
    """

    def __init__(
        self,
        settings: Settings | None = None,
        warmup_service: WarmupService | None = None,
    ) -> None:
        """Initialize the controller.

        Args:
            settings: Application settings (uses default if not provided)
            warmup_service: Optional WarmupService instance
        """
        self.settings = settings or get_settings()
        self._warmup_service = warmup_service
        self._task: asyncio.Task | None = None
        self._running = False

    @property
    def warmup_service(self) -> WarmupService:
        """Get the warmup service instance."""
        if self._warmup_service is None:
            self._warmup_service = get_warmup_service()
        return self._warmup_service

    @property
    def is_running(self) -> bool:
        """Check if the controller is running."""
        return self._running and self._task is not None

    async def _run_loop(self) -> None:
        """Background loop that runs warmup cycles at configured intervals."""
        interval = self.settings.warmup_interval_seconds
        logger.info(f"Warmup controller started, running every {interval} seconds")

        while self._running:
            try:
                await self.warmup_service.run_warmup_cycle()
            except Exception as e:
                logger.error(f"Error in warmup cycle: {e}")

            # Sleep for the configured interval
            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break

        logger.info("Warmup controller stopped")

    async def start(self) -> None:
        """Start the background warmup controller.

        Does nothing if controller is disabled in settings or already running.
        """
        if not self.settings.warmup_enabled:
            logger.info("Warmup controller is disabled in settings")
            return

        if self._running:
            logger.warning("Warmup controller is already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("Warmup controller background task created")

    async def stop(self) -> None:
        """Stop the background warmup controller.

        Waits for the current warmup cycle to complete before stopping.
        """
        if not self._running:
            return

        self._running = False

        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

        logger.info("Warmup controller stopped")


# Global service instances
_warmup_service: WarmupService | None = None
_warmup_controller: WarmupController | None = None


def get_warmup_service() -> WarmupService:
    """Get the global WarmupService instance."""
    global _warmup_service
    if _warmup_service is None:
        _warmup_service = WarmupService()
    return _warmup_service


def get_warmup_controller() -> WarmupController:
    """Get the global WarmupController instance."""
    global _warmup_controller
    if _warmup_controller is None:
        _warmup_controller = WarmupController()
    return _warmup_controller
