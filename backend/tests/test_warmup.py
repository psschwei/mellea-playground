"""Tests for WarmupService and WarmupController."""

import asyncio
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from mellea_api.core.config import Settings
from mellea_api.models.build import LayerCacheEntry
from mellea_api.models.common import EnvironmentStatus
from mellea_api.services.assets import AssetService
from mellea_api.services.environment import EnvironmentService
from mellea_api.services.warmup import (
    PopularDependency,
    WarmupController,
    WarmupMetrics,
    WarmupService,
)


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
        warmup_enabled=True,
        warmup_interval_seconds=1,  # Fast interval for tests
        warmup_pool_size=3,
        warmup_max_age_minutes=30,
        warmup_popular_deps_count=5,
    )
    settings.ensure_data_dirs()
    return settings


@pytest.fixture
def env_service(settings: Settings):
    """Create an EnvironmentService with test settings."""
    return EnvironmentService(settings=settings)


@pytest.fixture
def asset_service(settings: Settings):
    """Create an AssetService with test settings."""
    return AssetService(settings=settings)


@pytest.fixture
def warmup_service(settings: Settings, env_service: EnvironmentService, asset_service: AssetService):
    """Create a WarmupService with test settings."""
    # Create a mock environment builder since we don't want to build images in tests
    mock_builder = MagicMock()
    mock_builder.cache_store.list_all.return_value = []

    return WarmupService(
        settings=settings,
        environment_service=env_service,
        environment_builder=mock_builder,
        asset_service=asset_service,
    )


class TestWarmupMetrics:
    """Tests for WarmupMetrics dataclass."""

    def test_default_metrics(self):
        """Test WarmupMetrics default values."""
        metrics = WarmupMetrics()
        assert metrics.warm_pool_size == 0
        assert metrics.environments_created == 0
        assert metrics.environments_recycled == 0
        assert metrics.layers_pre_built == 0
        assert metrics.errors == []
        assert metrics.duration_seconds == 0.0


class TestPopularDependency:
    """Tests for PopularDependency dataclass."""

    def test_create_popular_dependency(self):
        """Test creating a PopularDependency."""
        now = datetime.utcnow()
        dep = PopularDependency(
            cache_key="abc123",
            image_tag="mellea-deps:abc123",
            use_count=10,
            last_used_at=now,
        )
        assert dep.cache_key == "abc123"
        assert dep.use_count == 10


class TestWarmupServiceConfiguration:
    """Tests for WarmupService configuration."""

    def test_service_initialization(self, warmup_service: WarmupService, settings: Settings):
        """Test service initializes with correct settings."""
        assert warmup_service.settings == settings
        assert warmup_service.settings.warmup_pool_size == 3

    def test_service_lazy_initialization(self, settings: Settings):
        """Test that services are lazily initialized."""
        service = WarmupService(settings=settings)
        # Services should be None initially
        assert service._environment_service is None
        assert service._asset_service is None


class TestGetWarmEnvironments:
    """Tests for getting warm environments."""

    def test_get_warm_environments_empty(self, warmup_service: WarmupService):
        """Test getting warm environments when none exist."""
        warm = warmup_service.get_warm_environments()
        assert warm == []

    def test_get_warm_environments(
        self,
        warmup_service: WarmupService,
        env_service: EnvironmentService,
    ):
        """Test getting warm environments."""
        # Create a READY environment
        env = env_service.create_environment("prog-123", "image:tag")
        env_service.update_status(env.id, EnvironmentStatus.READY)

        warm = warmup_service.get_warm_environments()
        assert len(warm) == 1
        assert warm[0].id == env.id

    def test_non_ready_environments_not_warm(
        self,
        warmup_service: WarmupService,
        env_service: EnvironmentService,
    ):
        """Test that non-READY environments are not considered warm."""
        # Create a CREATING environment (not READY)
        env_service.create_environment("prog-123", "image:tag")

        warm = warmup_service.get_warm_environments()
        assert len(warm) == 0


class TestGetStaleWarmEnvironments:
    """Tests for identifying stale warm environments."""

    def test_get_stale_environments_empty(self, warmup_service: WarmupService):
        """Test no stale environments when pool is empty."""
        stale = warmup_service.get_stale_warm_environments()
        assert stale == []

    def test_new_environment_not_stale(
        self,
        warmup_service: WarmupService,
        env_service: EnvironmentService,
    ):
        """Test that newly created environments are not stale."""
        env = env_service.create_environment("prog-123", "image:tag")
        env_service.update_status(env.id, EnvironmentStatus.READY)

        stale = warmup_service.get_stale_warm_environments()
        assert len(stale) == 0

    def test_old_environment_is_stale(
        self,
        env_service: EnvironmentService,
        asset_service: AssetService,
        temp_data_dir: Path,
    ):
        """Test that old environments are identified as stale."""
        # Use a very short max age (0 minutes)
        short_max_age_settings = Settings(
            data_dir=temp_data_dir,
            warmup_max_age_minutes=0,  # 0 minutes = immediately stale
        )

        mock_builder = MagicMock()
        mock_builder.cache_store.list_all.return_value = []

        service = WarmupService(
            settings=short_max_age_settings,
            environment_service=env_service,
            environment_builder=mock_builder,
            asset_service=asset_service,
        )

        env = env_service.create_environment("prog-123", "image:tag")
        env_service.update_status(env.id, EnvironmentStatus.READY)

        stale = service.get_stale_warm_environments()
        assert len(stale) == 1


class TestGetPoolStatus:
    """Tests for getting pool status."""

    def test_get_pool_status_empty(self, warmup_service: WarmupService, settings: Settings):
        """Test getting pool status when empty."""
        status = warmup_service.get_pool_status()

        assert status["enabled"] is True
        assert status["target_pool_size"] == settings.warmup_pool_size
        assert status["current_pool_size"] == 0
        assert status["stale_count"] == 0
        assert "warm_environments" in status
        assert "thresholds" in status

    def test_get_pool_status_with_environments(
        self,
        warmup_service: WarmupService,
        env_service: EnvironmentService,
    ):
        """Test getting pool status with warm environments."""
        env = env_service.create_environment("prog-123", "image:tag")
        env_service.update_status(env.id, EnvironmentStatus.READY)

        status = warmup_service.get_pool_status()

        assert status["current_pool_size"] == 1
        assert len(status["warm_environments"]) == 1


class TestRecycleEnvironment:
    """Tests for recycling stale environments."""

    def test_recycle_ready_environment(
        self,
        warmup_service: WarmupService,
        env_service: EnvironmentService,
    ):
        """Test recycling a READY environment."""
        env = env_service.create_environment("prog-123", "image:tag")
        env_service.update_status(env.id, EnvironmentStatus.READY)

        result = warmup_service.recycle_stale_environment(env.id)

        assert result is True
        assert env_service.get_environment(env.id) is None

    def test_recycle_nonexistent_environment(self, warmup_service: WarmupService):
        """Test recycling a nonexistent environment."""
        result = warmup_service.recycle_stale_environment("nonexistent")
        assert result is False

    def test_recycle_non_ready_environment(
        self,
        warmup_service: WarmupService,
        env_service: EnvironmentService,
    ):
        """Test that non-READY environments are not recycled."""
        env = env_service.create_environment("prog-123", "image:tag")
        # Leave in CREATING state

        result = warmup_service.recycle_stale_environment(env.id)
        assert result is False


class TestGetPopularDependencies:
    """Tests for getting popular dependencies."""

    def test_get_popular_dependencies_empty(self, warmup_service: WarmupService):
        """Test getting popular dependencies when none exist."""
        popular = warmup_service.get_popular_dependencies()
        assert popular == []

    def test_get_popular_dependencies_sorted(
        self,
        settings: Settings,
        env_service: EnvironmentService,
        asset_service: AssetService,
    ):
        """Test that dependencies are sorted by use count."""
        mock_builder = MagicMock()

        # Create mock cache entries with different use counts
        entries = [
            LayerCacheEntry(
                cache_key="key1",
                image_tag="image:1",
                python_version="3.12",
                packages_hash="hash1",
                package_count=5,
                use_count=10,
            ),
            LayerCacheEntry(
                cache_key="key2",
                image_tag="image:2",
                python_version="3.12",
                packages_hash="hash2",
                package_count=3,
                use_count=25,  # Most popular
            ),
            LayerCacheEntry(
                cache_key="key3",
                image_tag="image:3",
                python_version="3.12",
                packages_hash="hash3",
                package_count=2,
                use_count=5,
            ),
        ]
        mock_builder.cache_store.list_all.return_value = entries

        service = WarmupService(
            settings=settings,
            environment_service=env_service,
            environment_builder=mock_builder,
            asset_service=asset_service,
        )

        popular = service.get_popular_dependencies()

        assert len(popular) == 3
        # Should be sorted by use_count descending
        assert popular[0].use_count == 25
        assert popular[1].use_count == 10
        assert popular[2].use_count == 5


class TestWarmupCycle:
    """Tests for warmup cycles."""

    @pytest.mark.asyncio
    async def test_warmup_cycle_empty(self, warmup_service: WarmupService):
        """Test warmup cycle with no programs."""
        metrics = await warmup_service.run_warmup_cycle()

        assert metrics.warm_pool_size == 0
        assert metrics.environments_created == 0
        assert metrics.environments_recycled == 0
        assert metrics.duration_seconds >= 0

    @pytest.mark.asyncio
    async def test_warmup_cycle_recycles_stale(
        self,
        env_service: EnvironmentService,
        asset_service: AssetService,
        temp_data_dir: Path,
    ):
        """Test that warmup cycle recycles stale environments."""
        # Use very short max age
        short_max_age_settings = Settings(
            data_dir=temp_data_dir,
            warmup_max_age_minutes=0,  # Immediately stale
            warmup_pool_size=0,  # Don't try to create new ones
        )

        mock_builder = MagicMock()
        mock_builder.cache_store.list_all.return_value = []

        service = WarmupService(
            settings=short_max_age_settings,
            environment_service=env_service,
            environment_builder=mock_builder,
            asset_service=asset_service,
        )

        # Create a warm environment
        env = env_service.create_environment("prog-123", "image:tag")
        env_service.update_status(env.id, EnvironmentStatus.READY)

        metrics = await service.run_warmup_cycle()

        assert metrics.environments_recycled == 1

    @pytest.mark.asyncio
    async def test_warmup_cycle_stores_metrics(self, warmup_service: WarmupService):
        """Test that warmup cycle stores metrics."""
        assert warmup_service.get_last_metrics() is None

        await warmup_service.run_warmup_cycle()

        metrics = warmup_service.get_last_metrics()
        assert metrics is not None


class TestWarmupController:
    """Tests for WarmupController."""

    @pytest.fixture
    def controller(self, settings: Settings, warmup_service: WarmupService):
        """Create a WarmupController with test settings."""
        return WarmupController(settings=settings, warmup_service=warmup_service)

    def test_controller_not_running_initially(self, controller: WarmupController):
        """Test that controller is not running initially."""
        assert controller.is_running is False

    @pytest.mark.asyncio
    async def test_controller_start_and_stop(self, controller: WarmupController):
        """Test starting and stopping the controller."""
        await controller.start()
        assert controller.is_running is True

        await controller.stop()
        assert controller.is_running is False

    @pytest.mark.asyncio
    async def test_controller_disabled_in_settings(
        self,
        warmup_service: WarmupService,
        temp_data_dir: Path,
    ):
        """Test that controller doesn't start when disabled in settings."""
        disabled_settings = Settings(
            data_dir=temp_data_dir,
            warmup_enabled=False,
        )
        controller = WarmupController(
            settings=disabled_settings,
            warmup_service=warmup_service,
        )

        await controller.start()
        assert controller.is_running is False

    @pytest.mark.asyncio
    async def test_controller_double_start(self, controller: WarmupController):
        """Test that double start doesn't create duplicate tasks."""
        await controller.start()
        task1 = controller._task

        await controller.start()  # Should be a no-op
        task2 = controller._task

        assert task1 is task2

        await controller.stop()

    @pytest.mark.asyncio
    async def test_controller_stop_without_start(self, controller: WarmupController):
        """Test that stopping without starting is safe."""
        await controller.stop()  # Should not raise
        assert controller.is_running is False

    @pytest.mark.asyncio
    async def test_controller_runs_warmup_cycles(
        self,
        controller: WarmupController,
        warmup_service: WarmupService,
    ):
        """Test that controller runs warmup cycles periodically."""
        await controller.start()

        # Wait for at least one cycle to run
        await asyncio.sleep(1.5)

        # Check that at least one cycle ran
        metrics = warmup_service.get_last_metrics()
        assert metrics is not None

        await controller.stop()
