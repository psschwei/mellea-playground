"""Tests for EnvironmentBuilder service."""

import os
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


class TestMelleaDependencyInjection:
    """Tests for mellea dependency injection."""

    def test_ensure_mellea_dependency_adds_mellea(
        self, builder_service: EnvironmentBuilderService, sample_deps: DependencySpec
    ):
        """Test that mellea is added when not present."""
        result = builder_service.ensure_mellea_dependency(sample_deps)

        mellea_pkg = next(
            (pkg for pkg in result.packages if pkg.name == "mellea"), None
        )
        assert mellea_pkg is not None
        assert mellea_pkg.version == builder_service.MELLEA_VERSION

    def test_ensure_mellea_dependency_preserves_existing(
        self, builder_service: EnvironmentBuilderService
    ):
        """Test that existing mellea dependency is preserved."""
        deps_with_mellea = DependencySpec(
            source=DependencySource.PYPROJECT,
            packages=[
                PackageRef(name="mellea", version="0.2.0", extras=["custom"]),
                PackageRef(name="requests", version="2.31.0"),
            ],
            pythonVersion="3.12",
        )

        result = builder_service.ensure_mellea_dependency(deps_with_mellea)

        # Should not add another mellea
        mellea_pkgs = [pkg for pkg in result.packages if pkg.name.lower() == "mellea"]
        assert len(mellea_pkgs) == 1
        # Should preserve original version
        assert mellea_pkgs[0].version == "0.2.0"

    def test_ensure_mellea_dependency_adds_backend_extras(
        self, builder_service: EnvironmentBuilderService, sample_deps: DependencySpec
    ):
        """Test that backend-specific extras are added."""
        result = builder_service.ensure_mellea_dependency(sample_deps, backend="ollama")

        mellea_pkg = next(
            (pkg for pkg in result.packages if pkg.name == "mellea"), None
        )
        assert mellea_pkg is not None
        assert "ollama" in mellea_pkg.extras

    def test_ensure_mellea_dependency_handles_unknown_backend(
        self, builder_service: EnvironmentBuilderService, sample_deps: DependencySpec
    ):
        """Test that unknown backends don't cause errors."""
        result = builder_service.ensure_mellea_dependency(
            sample_deps, backend="unknown_backend"
        )

        mellea_pkg = next(
            (pkg for pkg in result.packages if pkg.name == "mellea"), None
        )
        assert mellea_pkg is not None
        # No extras for unknown backend
        assert len(mellea_pkg.extras) == 0


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

        assert "FROM kind-registry:5000/mellea-python:3.12" in dockerfile
        assert "pip install" in dockerfile

        assert "requests==2.31.0" in requirements
        assert "pydantic==2.5.0" in requirements

    def test_generate_deps_dockerfile_has_buildkit_syntax(
        self, builder_service: EnvironmentBuilderService, sample_deps: DependencySpec
    ):
        """Test that Dockerfile contains BuildKit syntax header."""
        dockerfile, _ = builder_service.generate_deps_dockerfile(sample_deps)

        # BuildKit syntax directive must be on the first line
        first_line = dockerfile.strip().split("\n")[0]
        assert first_line == "# syntax=docker/dockerfile:1"

    def test_generate_deps_dockerfile_has_pip_cache_mount(
        self, builder_service: EnvironmentBuilderService, sample_deps: DependencySpec
    ):
        """Test that Dockerfile uses BuildKit cache mount for pip."""
        dockerfile, _ = builder_service.generate_deps_dockerfile(sample_deps)

        assert "--mount=type=cache,target=/root/.cache/pip" in dockerfile
        # Should NOT use --no-cache-dir anymore
        assert "--no-cache-dir" not in dockerfile

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
        assert "FROM kind-registry:5000/mellea-python:3.11" in dockerfile

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

        # Pre-populate cache - need to include mellea since build_image injects it
        deps_with_mellea = builder_service.ensure_mellea_dependency(sample_deps)
        cache_key = builder_service.compute_cache_key(deps_with_mellea)
        deps_image_tag = f"mellea-deps:{cache_key[:12]}"

        builder_service.create_cache_entry(
            cache_key=cache_key,
            image_tag=deps_image_tag,
            deps=deps_with_mellea,
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

    def test_build_dependency_layer_enables_buildkit(
        self,
        builder_service: EnvironmentBuilderService,
        sample_program: ProgramAsset,
        mock_docker_client: MagicMock,
        temp_data_dir: Path,
    ):
        """Test that BuildKit is enabled during dependency layer build."""
        # Setup workspace
        workspace_path = temp_data_dir / "workspaces" / sample_program.id
        workspace_path.mkdir(parents=True)
        (workspace_path / "src").mkdir()
        (workspace_path / "src" / "main.py").write_text("print('hello')")

        # Track DOCKER_BUILDKIT value during build
        buildkit_values_during_build = []

        def capture_buildkit(*args, **kwargs):
            buildkit_values_during_build.append(os.environ.get("DOCKER_BUILDKIT"))
            return (MagicMock(), [])

        mock_docker_client.images.build.side_effect = capture_buildkit
        mock_docker_client.images.get.return_value = MagicMock(attrs={"Size": 1000})

        # Clear DOCKER_BUILDKIT before test
        old_buildkit = os.environ.pop("DOCKER_BUILDKIT", None)
        try:
            result = builder_service.build_image(sample_program, workspace_path)

            assert result.success
            # First build call is for deps layer - should have BUILDKIT=1
            assert len(buildkit_values_during_build) == 2
            assert buildkit_values_during_build[0] == "1"

            # Verify DOCKER_BUILDKIT is restored after build
            assert os.environ.get("DOCKER_BUILDKIT") is None
        finally:
            # Restore original value
            if old_buildkit is not None:
                os.environ["DOCKER_BUILDKIT"] = old_buildkit


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


class TestRegistryOperations:
    """Tests for container registry push/pull operations."""

    @pytest.fixture
    def settings_with_registry(self, temp_data_dir: Path):
        """Create test settings with registry configured."""
        settings = Settings(
            data_dir=temp_data_dir,
            registry_url="registry.example.com",
            registry_username="testuser",
            registry_password="testpass",
        )
        settings.ensure_data_dirs()
        return settings

    @pytest.fixture
    def builder_with_registry(
        self, settings_with_registry: Settings, mock_docker_client: MagicMock
    ):
        """Create an EnvironmentBuilder service with registry configured."""
        service = EnvironmentBuilderService(settings=settings_with_registry)
        service._docker_client = mock_docker_client
        return service

    def test_get_full_image_tag_without_registry(
        self, builder_service: EnvironmentBuilderService
    ):
        """Test get_full_image_tag returns original tag when no registry configured."""
        result = builder_service.get_full_image_tag("mellea-deps:abc123")
        assert result == "mellea-deps:abc123"

    def test_get_full_image_tag_with_registry(
        self, builder_with_registry: EnvironmentBuilderService
    ):
        """Test get_full_image_tag prefixes registry URL when configured."""
        result = builder_with_registry.get_full_image_tag("mellea-deps:abc123")
        assert result == "registry.example.com/mellea-deps:abc123"

    def test_login_to_registry_no_registry_configured(
        self, builder_service: EnvironmentBuilderService
    ):
        """Test login returns True when no registry is configured."""
        result = builder_service.login_to_registry()
        assert result is True

    def test_login_to_registry_success(
        self, builder_with_registry: EnvironmentBuilderService, mock_docker_client: MagicMock
    ):
        """Test successful registry login."""
        result = builder_with_registry.login_to_registry()

        assert result is True
        assert builder_with_registry._registry_logged_in is True
        mock_docker_client.login.assert_called_once_with(
            username="testuser",
            password="testpass",
            registry="registry.example.com",
        )

    def test_login_to_registry_already_logged_in(
        self, builder_with_registry: EnvironmentBuilderService, mock_docker_client: MagicMock
    ):
        """Test login is skipped if already logged in."""
        builder_with_registry._registry_logged_in = True

        result = builder_with_registry.login_to_registry()

        assert result is True
        mock_docker_client.login.assert_not_called()

    def test_login_to_registry_missing_credentials(self, temp_data_dir: Path):
        """Test login fails when credentials are missing."""
        settings = Settings(
            data_dir=temp_data_dir,
            registry_url="registry.example.com",
            # No username/password
        )
        settings.ensure_data_dirs()
        service = EnvironmentBuilderService(settings=settings)

        result = service.login_to_registry()

        assert result is False
        assert service._registry_logged_in is False

    def test_login_to_registry_failure(
        self, builder_with_registry: EnvironmentBuilderService, mock_docker_client: MagicMock
    ):
        """Test login handles Docker exception."""
        from docker.errors import DockerException

        mock_docker_client.login.side_effect = DockerException("Auth failed")

        result = builder_with_registry.login_to_registry()

        assert result is False
        assert builder_with_registry._registry_logged_in is False

    def test_push_image_no_registry(
        self, builder_service: EnvironmentBuilderService, mock_docker_client: MagicMock
    ):
        """Test push returns False when no registry is configured."""
        result = builder_service.push_image("mellea-deps:abc123")

        assert result is False
        mock_docker_client.images.push.assert_not_called()

    def test_push_image_success(
        self, builder_with_registry: EnvironmentBuilderService, mock_docker_client: MagicMock
    ):
        """Test successful image push."""
        mock_image = MagicMock()
        mock_docker_client.images.get.return_value = mock_image
        mock_docker_client.images.push.return_value = iter([{"status": "Pushing"}])

        result = builder_with_registry.push_image("mellea-deps:abc123")

        assert result is True
        mock_image.tag.assert_called_once_with("registry.example.com/mellea-deps:abc123")
        mock_docker_client.images.push.assert_called_once_with(
            "registry.example.com/mellea-deps:abc123", stream=True, decode=True
        )

    def test_push_image_error_in_output(
        self, builder_with_registry: EnvironmentBuilderService, mock_docker_client: MagicMock
    ):
        """Test push handles error in push output."""
        from mellea_api.services.environment_builder import RegistryPushError

        mock_image = MagicMock()
        mock_docker_client.images.get.return_value = mock_image
        mock_docker_client.images.push.return_value = iter([
            {"status": "Pushing"},
            {"error": "denied: access forbidden"},
        ])

        with pytest.raises(RegistryPushError, match="Push failed"):
            builder_with_registry.push_image("mellea-deps:abc123")

    def test_push_image_not_found_locally(
        self, builder_with_registry: EnvironmentBuilderService, mock_docker_client: MagicMock
    ):
        """Test push returns False when image not found locally."""
        from docker.errors import ImageNotFound

        mock_docker_client.images.get.side_effect = ImageNotFound("Not found")

        result = builder_with_registry.push_image("mellea-deps:abc123")

        assert result is False

    def test_pull_image_no_registry(
        self, builder_service: EnvironmentBuilderService, mock_docker_client: MagicMock
    ):
        """Test pull returns False when no registry is configured."""
        result = builder_service.pull_image("mellea-deps:abc123")

        assert result is False
        mock_docker_client.images.pull.assert_not_called()

    def test_pull_image_success(
        self, builder_with_registry: EnvironmentBuilderService, mock_docker_client: MagicMock
    ):
        """Test successful image pull."""
        mock_image = MagicMock()
        mock_docker_client.images.get.return_value = mock_image

        result = builder_with_registry.pull_image("mellea-deps:abc123")

        assert result is True
        mock_docker_client.images.pull.assert_called_once_with(
            "registry.example.com/mellea-deps:abc123"
        )
        # Should tag the pulled image with the local tag
        mock_image.tag.assert_called_once_with("mellea-deps:abc123")

    def test_pull_image_not_found_in_registry(
        self, builder_with_registry: EnvironmentBuilderService, mock_docker_client: MagicMock
    ):
        """Test pull returns False when image not in registry."""
        from docker.errors import ImageNotFound

        mock_docker_client.images.pull.side_effect = ImageNotFound("Not found")

        result = builder_with_registry.pull_image("mellea-deps:abc123")

        assert result is False

    def test_build_image_with_push(
        self,
        builder_with_registry: EnvironmentBuilderService,
        sample_program: ProgramAsset,
        mock_docker_client: MagicMock,
        temp_data_dir: Path,
    ):
        """Test build_image with push=True pushes images to registry."""
        # Setup workspace
        workspace_path = temp_data_dir / "workspaces" / sample_program.id
        workspace_path.mkdir(parents=True)
        (workspace_path / "src").mkdir()
        (workspace_path / "src" / "main.py").write_text("print('hello')")

        # Mock Docker
        mock_image = MagicMock()
        mock_docker_client.images.build.return_value = (mock_image, [])
        mock_docker_client.images.get.return_value = mock_image
        mock_docker_client.images.push.return_value = iter([{"status": "Pushing"}])

        # Build with push
        result = builder_with_registry.build_image(
            sample_program, workspace_path, push=True
        )

        assert result.success
        # Should have pushed both deps and program images
        assert mock_docker_client.images.push.call_count == 2

    def test_build_image_with_push_cache_hit_skips_deps_push(
        self,
        builder_with_registry: EnvironmentBuilderService,
        sample_program: ProgramAsset,
        sample_deps: DependencySpec,
        mock_docker_client: MagicMock,
        temp_data_dir: Path,
    ):
        """Test build with cache hit only pushes program image."""
        # Setup workspace
        workspace_path = temp_data_dir / "workspaces" / sample_program.id
        workspace_path.mkdir(parents=True)
        (workspace_path / "src").mkdir()
        (workspace_path / "src" / "main.py").write_text("print('hello')")

        # Pre-populate cache - need to include mellea since build_image injects it
        deps_with_mellea = builder_with_registry.ensure_mellea_dependency(sample_deps)
        cache_key = builder_with_registry.compute_cache_key(deps_with_mellea)
        deps_image_tag = f"mellea-deps:{cache_key[:12]}"
        builder_with_registry.create_cache_entry(
            cache_key=cache_key,
            image_tag=deps_image_tag,
            deps=deps_with_mellea,
        )

        # Mock Docker
        mock_image = MagicMock()
        mock_docker_client.images.build.return_value = (mock_image, [])
        mock_docker_client.images.get.return_value = mock_image
        mock_docker_client.images.push.return_value = iter([{"status": "Pushing"}])

        # Build with push
        result = builder_with_registry.build_image(
            sample_program, workspace_path, push=True
        )

        assert result.success
        assert result.cache_hit is True
        # Should only push program image (deps was cached, not rebuilt)
        assert mock_docker_client.images.push.call_count == 1
