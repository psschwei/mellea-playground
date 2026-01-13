"""Tests for EnvironmentBuilder service."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from mellea_api.core.config import Settings
from mellea_api.models.assets import DependencySpec, PackageRef, ProgramAsset
from mellea_api.models.common import DependencySource
from mellea_api.services.environment_builder import EnvironmentBuilderService


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
def mock_docker_client():
    """Create a mock Docker client."""
    with patch("mellea_api.services.environment_builder.docker") as mock_docker:
        client = MagicMock()
        mock_docker.from_env.return_value = client
        yield client


@pytest.fixture
def builder_service(settings: Settings, mock_docker_client: MagicMock):
    """Create an EnvironmentBuilder service with mocked Docker client."""
    service = EnvironmentBuilderService(settings=settings)
    service._docker_client = mock_docker_client
    return service


@pytest.fixture
def sample_deps():
    """Create sample dependency specification."""
    return DependencySpec(
        source=DependencySource.PYPROJECT,
        packages=[
            PackageRef(name="requests", version="2.31.0"),
            PackageRef(name="pydantic", version="2.5.0"),
        ],
        pythonVersion="3.12",
    )


@pytest.fixture
def sample_deps_with_extras():
    """Create sample dependency specification with extras."""
    return DependencySpec(
        source=DependencySource.PYPROJECT,
        packages=[
            PackageRef(name="pydantic", version="2.5.0", extras=["email"]),
        ],
        pythonVersion="3.12",
    )


@pytest.fixture
def sample_program(sample_deps: DependencySpec):
    """Create a sample program with dependencies."""
    return ProgramAsset(
        name="Test Program",
        owner="user-123",
        entrypoint="src/main.py",
        projectRoot="workspaces/test",
        dependencies=sample_deps,
    )


class TestCacheKeyComputation:
    """Tests for cache key computation."""

    def test_compute_cache_key_deterministic(
        self, builder_service: EnvironmentBuilderService, sample_deps: DependencySpec
    ):
        """Test that cache key is deterministic for same deps."""
        key1 = builder_service.compute_cache_key(sample_deps)
        key2 = builder_service.compute_cache_key(sample_deps)

        assert key1 == key2
        assert len(key1) == 64  # SHA256 hex length

    def test_compute_cache_key_different_for_different_deps(
        self, builder_service: EnvironmentBuilderService
    ):
        """Test that different deps produce different keys."""
        deps1 = DependencySpec(
            source=DependencySource.MANUAL,
            packages=[PackageRef(name="requests")],
        )
        deps2 = DependencySpec(
            source=DependencySource.MANUAL,
            packages=[PackageRef(name="httpx")],
        )

        key1 = builder_service.compute_cache_key(deps1)
        key2 = builder_service.compute_cache_key(deps2)

        assert key1 != key2

    def test_compute_cache_key_order_independent(
        self, builder_service: EnvironmentBuilderService
    ):
        """Test that package order doesn't affect cache key."""
        deps1 = DependencySpec(
            source=DependencySource.MANUAL,
            packages=[
                PackageRef(name="requests"),
                PackageRef(name="pydantic"),
            ],
        )
        deps2 = DependencySpec(
            source=DependencySource.MANUAL,
            packages=[
                PackageRef(name="pydantic"),
                PackageRef(name="requests"),
            ],
        )

        key1 = builder_service.compute_cache_key(deps1)
        key2 = builder_service.compute_cache_key(deps2)

        assert key1 == key2

    def test_compute_cache_key_case_insensitive(
        self, builder_service: EnvironmentBuilderService
    ):
        """Test that package names are normalized to lowercase."""
        deps1 = DependencySpec(
            source=DependencySource.MANUAL,
            packages=[PackageRef(name="Requests")],
        )
        deps2 = DependencySpec(
            source=DependencySource.MANUAL,
            packages=[PackageRef(name="requests")],
        )

        key1 = builder_service.compute_cache_key(deps1)
        key2 = builder_service.compute_cache_key(deps2)

        assert key1 == key2

    def test_compute_cache_key_version_matters(
        self, builder_service: EnvironmentBuilderService
    ):
        """Test that version changes affect cache key."""
        deps1 = DependencySpec(
            source=DependencySource.MANUAL,
            packages=[PackageRef(name="requests", version="2.30.0")],
        )
        deps2 = DependencySpec(
            source=DependencySource.MANUAL,
            packages=[PackageRef(name="requests", version="2.31.0")],
        )

        key1 = builder_service.compute_cache_key(deps1)
        key2 = builder_service.compute_cache_key(deps2)

        assert key1 != key2

    def test_compute_cache_key_python_version_matters(
        self, builder_service: EnvironmentBuilderService
    ):
        """Test that Python version affects cache key."""
        deps1 = DependencySpec(
            source=DependencySource.MANUAL,
            packages=[PackageRef(name="requests")],
            pythonVersion="3.11",
        )
        deps2 = DependencySpec(
            source=DependencySource.MANUAL,
            packages=[PackageRef(name="requests")],
            pythonVersion="3.12",
        )

        key1 = builder_service.compute_cache_key(deps1)
        key2 = builder_service.compute_cache_key(deps2)

        assert key1 != key2


class TestCacheOperations:
    """Tests for layer cache operations."""

    def test_get_cached_layer_miss(self, builder_service: EnvironmentBuilderService):
        """Test cache miss returns None."""
        result = builder_service.get_cached_layer("nonexistent-key")
        assert result is None

    def test_create_and_get_cache_entry(
        self, builder_service: EnvironmentBuilderService, sample_deps: DependencySpec
    ):
        """Test creating and retrieving a cache entry."""
        cache_key = builder_service.compute_cache_key(sample_deps)
        image_tag = f"mellea-deps:{cache_key[:12]}"

        created = builder_service.create_cache_entry(
            cache_key=cache_key,
            image_tag=image_tag,
            deps=sample_deps,
        )

        assert created.cache_key == cache_key
        assert created.image_tag == image_tag
        assert created.package_count == 2

        found = builder_service.get_cached_layer(cache_key)
        assert found is not None
        assert found.cache_key == cache_key
        assert found.use_count == 2  # Incremented on lookup

    def test_invalidate_cache_entry(
        self, builder_service: EnvironmentBuilderService, sample_deps: DependencySpec
    ):
        """Test invalidating a cache entry."""
        cache_key = builder_service.compute_cache_key(sample_deps)

        builder_service.create_cache_entry(
            cache_key=cache_key,
            image_tag="test:tag",
            deps=sample_deps,
        )

        result = builder_service.invalidate_cache_entry(cache_key)
        assert result is True

        found = builder_service.get_cached_layer(cache_key)
        assert found is None

    def test_invalidate_nonexistent_cache_entry(
        self, builder_service: EnvironmentBuilderService
    ):
        """Test that invalidating nonexistent entry returns False."""
        result = builder_service.invalidate_cache_entry("nonexistent-key")
        assert result is False

    def test_list_cache_entries(
        self, builder_service: EnvironmentBuilderService, sample_deps: DependencySpec
    ):
        """Test listing all cache entries."""
        cache_key = builder_service.compute_cache_key(sample_deps)

        builder_service.create_cache_entry(
            cache_key=cache_key,
            image_tag="test:tag",
            deps=sample_deps,
        )

        entries = builder_service.list_cache_entries()
        assert len(entries) == 1
        assert entries[0].cache_key == cache_key


class TestDockerfileGeneration:
    """Tests for Dockerfile generation."""

    def test_generate_deps_dockerfile(
        self, builder_service: EnvironmentBuilderService, sample_deps: DependencySpec
    ):
        """Test dependency Dockerfile generation."""
        dockerfile, requirements = builder_service.generate_deps_dockerfile(sample_deps)

        assert "FROM python:3.12-slim" in dockerfile
        assert "pip install" in dockerfile

        assert "requests==2.31.0" in requirements
        assert "pydantic==2.5.0" in requirements

    def test_generate_deps_dockerfile_with_extras(
        self,
        builder_service: EnvironmentBuilderService,
        sample_deps_with_extras: DependencySpec,
    ):
        """Test Dockerfile with package extras."""
        _, requirements = builder_service.generate_deps_dockerfile(
            sample_deps_with_extras
        )
        assert "pydantic[email]==2.5.0" in requirements

    def test_generate_deps_dockerfile_different_python_version(
        self, builder_service: EnvironmentBuilderService
    ):
        """Test Dockerfile with different Python version."""
        deps = DependencySpec(
            source=DependencySource.MANUAL,
            packages=[PackageRef(name="requests")],
            pythonVersion="3.11",
        )

        dockerfile, _ = builder_service.generate_deps_dockerfile(deps)
        assert "FROM python:3.11-slim" in dockerfile

    def test_generate_program_dockerfile(
        self,
        builder_service: EnvironmentBuilderService,
        sample_program: ProgramAsset,
    ):
        """Test program Dockerfile generation."""
        dockerfile = builder_service.generate_program_dockerfile(
            sample_program,
            "mellea-deps:abc123",
        )

        assert "FROM mellea-deps:abc123" in dockerfile
        assert "COPY . /app/" in dockerfile
        assert sample_program.entrypoint in dockerfile


class TestBuildImage:
    """Tests for full image build workflow."""

    def test_build_image_cache_miss(
        self,
        builder_service: EnvironmentBuilderService,
        sample_program: ProgramAsset,
        mock_docker_client: MagicMock,
        temp_data_dir: Path,
    ):
        """Test building an image with cache miss."""
        # Setup workspace
        workspace_path = temp_data_dir / "workspaces" / sample_program.id
        workspace_path.mkdir(parents=True)
        (workspace_path / "src").mkdir()
        (workspace_path / "src" / "main.py").write_text("print('hello')")

        # Mock Docker build
        mock_image = MagicMock()
        mock_docker_client.images.build.return_value = (mock_image, [])
        mock_docker_client.images.get.return_value = MagicMock(
            attrs={"Size": 1000000}
        )

        # Build
        result = builder_service.build_image(sample_program, workspace_path)

        assert result.success
        assert result.cache_hit is False
        assert result.image_tag is not None
        assert "mellea-prog" in result.image_tag

        # Verify Docker was called twice (deps + program)
        assert mock_docker_client.images.build.call_count == 2

    def test_build_image_cache_hit(
        self,
        builder_service: EnvironmentBuilderService,
        sample_program: ProgramAsset,
        sample_deps: DependencySpec,
        mock_docker_client: MagicMock,
        temp_data_dir: Path,
    ):
        """Test building an image with cache hit."""
        # Setup workspace
        workspace_path = temp_data_dir / "workspaces" / sample_program.id
        workspace_path.mkdir(parents=True)
        (workspace_path / "src").mkdir()
        (workspace_path / "src" / "main.py").write_text("print('hello')")

        # Pre-populate cache
        cache_key = builder_service.compute_cache_key(sample_deps)
        deps_image_tag = f"mellea-deps:{cache_key[:12]}"

        builder_service.create_cache_entry(
            cache_key=cache_key,
            image_tag=deps_image_tag,
            deps=sample_deps,
        )

        # Mock Docker - image exists
        mock_docker_client.images.get.return_value = MagicMock()
        mock_docker_client.images.build.return_value = (MagicMock(), [])

        # Build
        result = builder_service.build_image(sample_program, workspace_path)

        assert result.success
        assert result.cache_hit is True

        # Should only call build once (for program layer, not deps)
        assert mock_docker_client.images.build.call_count == 1

    def test_build_image_workspace_not_found(
        self,
        builder_service: EnvironmentBuilderService,
        sample_program: ProgramAsset,
        mock_docker_client: MagicMock,
        temp_data_dir: Path,
    ):
        """Test building fails for nonexistent workspace."""
        workspace_path = temp_data_dir / "nonexistent"

        # Mock Docker - dep build succeeds
        mock_docker_client.images.build.return_value = (MagicMock(), [])
        mock_docker_client.images.get.return_value = MagicMock(attrs={"Size": 1000})

        result = builder_service.build_image(sample_program, workspace_path)

        assert result.success is False
        assert result.error_message is not None
        assert "not found" in result.error_message.lower()

    def test_build_image_force_rebuild_skips_cache(
        self,
        builder_service: EnvironmentBuilderService,
        sample_program: ProgramAsset,
        sample_deps: DependencySpec,
        mock_docker_client: MagicMock,
        temp_data_dir: Path,
    ):
        """Test that force_rebuild skips cache lookup."""
        # Setup workspace
        workspace_path = temp_data_dir / "workspaces" / sample_program.id
        workspace_path.mkdir(parents=True)
        (workspace_path / "src").mkdir()
        (workspace_path / "src" / "main.py").write_text("print('hello')")

        # Pre-populate cache
        cache_key = builder_service.compute_cache_key(sample_deps)
        builder_service.create_cache_entry(
            cache_key=cache_key,
            image_tag="mellea-deps:cached",
            deps=sample_deps,
        )

        # Mock Docker
        mock_docker_client.images.get.return_value = MagicMock(attrs={"Size": 1000})
        mock_docker_client.images.build.return_value = (MagicMock(), [])

        # Build with force
        result = builder_service.build_image(
            sample_program, workspace_path, force_rebuild=True
        )

        assert result.success
        assert result.cache_hit is False

        # Should call build twice (deps + program) because we forced rebuild
        assert mock_docker_client.images.build.call_count == 2


class TestVerifyCachedImage:
    """Tests for image verification."""

    def test_verify_cached_image_exists_true(
        self,
        builder_service: EnvironmentBuilderService,
        mock_docker_client: MagicMock,
    ):
        """Test verifying an existing image."""
        mock_docker_client.images.get.return_value = MagicMock()

        result = builder_service.verify_cached_image_exists("test:tag")
        assert result is True

    def test_verify_cached_image_exists_false(
        self,
        builder_service: EnvironmentBuilderService,
        mock_docker_client: MagicMock,
    ):
        """Test verifying a nonexistent image."""
        from docker.errors import ImageNotFound

        mock_docker_client.images.get.side_effect = ImageNotFound("Not found")

        result = builder_service.verify_cached_image_exists("test:tag")
        assert result is False


class TestPackagesHash:
    """Tests for packages hash computation."""

    def test_compute_packages_hash(
        self, builder_service: EnvironmentBuilderService, sample_deps: DependencySpec
    ):
        """Test computing packages hash."""
        hash1 = builder_service.compute_packages_hash(sample_deps)

        assert len(hash1) == 16  # MD5 truncated
        assert hash1.isalnum()

    def test_compute_packages_hash_deterministic(
        self, builder_service: EnvironmentBuilderService, sample_deps: DependencySpec
    ):
        """Test that packages hash is deterministic."""
        hash1 = builder_service.compute_packages_hash(sample_deps)
        hash2 = builder_service.compute_packages_hash(sample_deps)

        assert hash1 == hash2
