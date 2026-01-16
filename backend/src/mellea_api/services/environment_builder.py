"""EnvironmentBuilder service for building Docker images with layer caching."""

import contextlib
import hashlib
import json
import logging
import os
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import docker
from docker.errors import BuildError as DockerBuildError
from docker.errors import DockerException, ImageNotFound

from mellea_api.core.config import Settings, get_settings
from mellea_api.core.store import JsonStore
from mellea_api.models.assets import DependencySpec, ProgramAsset
from mellea_api.models.build import (
    BuildContext,
    BuildResult,
    BuildStage,
    LayerCacheEntry,
)

logger = logging.getLogger(__name__)


class ImageBuildError(Exception):
    """Raised when image build fails."""

    pass


class RegistryPushError(Exception):
    """Raised when pushing an image to the registry fails."""

    pass


class RegistryPullError(Exception):
    """Raised when pulling an image from the registry fails."""

    pass


class EnvironmentBuilderService:
    """Service for building Docker images for ProgramAssets with layer caching.

    Implements a two-layer image strategy:
    1. Dependency layer: Contains installed Python packages (cached by hash)
    2. Program layer: Contains program source code (built on top of cached deps)

    Example:
        ```python
        builder = get_environment_builder_service()

        # Build image for a program
        result = builder.build_image(program_id="prog-123")

        if result.success:
            print(f"Image built: {result.image_tag}")
            print(f"Cache hit: {result.cache_hit}")
        ```
    """

    BASE_IMAGES = {
        "3.11": "mellea-python:3.11",
        "3.12": "mellea-python:3.12",
    }
    DEFAULT_PYTHON_VERSION = "3.12"

    DEPS_IMAGE_PREFIX = "mellea-deps"
    PROGRAM_IMAGE_PREFIX = "mellea-prog"

    def __init__(
        self,
        settings: Settings | None = None,
    ) -> None:
        """Initialize the EnvironmentBuilder service.

        Args:
            settings: Application settings (uses default if not provided)
        """
        self.settings = settings or get_settings()
        self._cache_store: JsonStore[LayerCacheEntry] | None = None
        self._docker_client: docker.DockerClient | None = None
        self._registry_logged_in: bool = False

    # -------------------------------------------------------------------------
    # Lazy Initialization Properties
    # -------------------------------------------------------------------------

    @property
    def cache_store(self) -> JsonStore[LayerCacheEntry]:
        """Get the layer cache store, initializing if needed."""
        if self._cache_store is None:
            file_path = self.settings.data_dir / "metadata" / "layer_cache.json"
            self._cache_store = JsonStore[LayerCacheEntry](
                file_path=file_path,
                collection_key="layer_cache",
                model_class=LayerCacheEntry,
            )
        return self._cache_store

    @property
    def docker_client(self) -> docker.DockerClient:
        """Get the Docker client, initializing if needed."""
        if self._docker_client is None:
            self._docker_client = docker.from_env()
        return self._docker_client

    # -------------------------------------------------------------------------
    # Cache Key Computation
    # -------------------------------------------------------------------------

    def compute_cache_key(self, deps: DependencySpec) -> str:
        """Compute a deterministic cache key for a DependencySpec.

        The cache key is a SHA256 hash of a normalized representation of
        the dependencies, ensuring that semantically identical dependency
        specs produce the same key.

        Args:
            deps: The dependency specification to hash

        Returns:
            Hex-encoded SHA256 hash string
        """
        normalized = self._normalize_dependency_spec(deps)
        json_str = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(json_str.encode()).hexdigest()

    def _normalize_dependency_spec(self, deps: DependencySpec) -> dict[str, Any]:
        """Normalize a DependencySpec for consistent hashing.

        Sorts packages alphabetically and normalizes version specifications.
        """
        python_version = deps.python_version or self.DEFAULT_PYTHON_VERSION

        sorted_packages = sorted(
            [self._normalize_package(pkg) for pkg in deps.packages],
            key=lambda p: p["name"].lower(),
        )

        return {
            "python_version": python_version,
            "packages": sorted_packages,
        }

    def _normalize_package(self, pkg: Any) -> dict[str, Any]:
        """Normalize a package reference for hashing."""
        return {
            "name": pkg.name.lower(),
            "version": pkg.version or "",
            "extras": sorted(pkg.extras) if pkg.extras else [],
        }

    def compute_packages_hash(self, deps: DependencySpec) -> str:
        """Compute a quick hash of just the package names for comparison."""
        names = sorted(pkg.name.lower() for pkg in deps.packages)
        return hashlib.md5(",".join(names).encode()).hexdigest()[:16]

    # -------------------------------------------------------------------------
    # Cache Operations
    # -------------------------------------------------------------------------

    def get_cached_layer(self, cache_key: str) -> LayerCacheEntry | None:
        """Look up a cached dependency layer by cache key.

        Args:
            cache_key: The SHA256 hash of the normalized dependency spec

        Returns:
            LayerCacheEntry if found, None otherwise
        """
        entries = self.cache_store.find(lambda e: e.cache_key == cache_key)
        if entries:
            entry = entries[0]
            entry.last_used_at = datetime.utcnow()
            entry.use_count += 1
            self.cache_store.update(entry.id, entry)
            return entry
        return None

    def verify_cached_image_exists(self, image_tag: str) -> bool:
        """Verify that a cached image actually exists in Docker.

        Args:
            image_tag: The Docker image tag to verify

        Returns:
            True if image exists, False otherwise
        """
        try:
            self.docker_client.images.get(image_tag)
            return True
        except ImageNotFound:
            return False
        except DockerException as e:
            logger.warning(f"Error checking image {image_tag}: {e}")
            return False

    def create_cache_entry(
        self,
        cache_key: str,
        image_tag: str,
        deps: DependencySpec,
        size_bytes: int | None = None,
    ) -> LayerCacheEntry:
        """Create a new layer cache entry.

        Args:
            cache_key: The computed cache key
            image_tag: The Docker image tag for this layer
            deps: The dependency specification
            size_bytes: Optional image size

        Returns:
            The created LayerCacheEntry
        """
        entry = LayerCacheEntry(
            id=str(uuid4()),
            cache_key=cache_key,
            image_tag=image_tag,
            python_version=deps.python_version or self.DEFAULT_PYTHON_VERSION,
            packages_hash=self.compute_packages_hash(deps),
            package_count=len(deps.packages),
            size_bytes=size_bytes,
        )
        return self.cache_store.create(entry)

    def invalidate_cache_entry(self, cache_key: str) -> bool:
        """Remove a cache entry (e.g., if image was deleted).

        Args:
            cache_key: The cache key to invalidate

        Returns:
            True if entry was removed, False if not found
        """
        entries = self.cache_store.find(lambda e: e.cache_key == cache_key)
        if entries:
            return self.cache_store.delete(entries[0].id)
        return False

    def list_cache_entries(self) -> list[LayerCacheEntry]:
        """List all layer cache entries."""
        return self.cache_store.list_all()

    def prune_stale_cache_entries(self, max_age_days: int = 30) -> int:
        """Remove cache entries older than max_age_days.

        Args:
            max_age_days: Maximum age in days before pruning

        Returns:
            Number of entries pruned
        """
        cutoff = datetime.utcnow().timestamp() - (max_age_days * 86400)
        stale = self.cache_store.find(lambda e: e.last_used_at.timestamp() < cutoff)

        pruned = 0
        for entry in stale:
            with contextlib.suppress(ImageNotFound, DockerException):
                self.docker_client.images.remove(entry.image_tag)

            if self.cache_store.delete(entry.id):
                pruned += 1
                logger.info(f"Pruned stale cache entry: {entry.cache_key[:12]}...")

        return pruned

    # -------------------------------------------------------------------------
    # Registry Operations
    # -------------------------------------------------------------------------

    def get_full_image_tag(self, image_tag: str) -> str:
        """Prefix image tag with registry URL if configured.

        Args:
            image_tag: Local image tag (e.g., "mellea-deps:abc123")

        Returns:
            Full image tag with registry prefix if configured,
            otherwise returns the original tag.

        Example:
            - Without registry: "mellea-deps:abc123" -> "mellea-deps:abc123"
            - With registry: "mellea-deps:abc123" -> "registry.example.com/mellea-deps:abc123"
        """
        if self.settings.registry_url:
            return f"{self.settings.registry_url}/{image_tag}"
        return image_tag

    def login_to_registry(self) -> bool:
        """Authenticate with the container registry.

        Uses credentials from settings. Called lazily before push/pull
        operations when registry is configured.

        Returns:
            True if login succeeded or no registry configured,
            False if login failed.
        """
        if not self.settings.registry_url:
            return True

        if self._registry_logged_in:
            return True

        if not self.settings.registry_username or not self.settings.registry_password:
            logger.warning(
                f"Registry URL configured ({self.settings.registry_url}) "
                "but no credentials provided"
            )
            return False

        try:
            self.docker_client.login(
                username=self.settings.registry_username,
                password=self.settings.registry_password,
                registry=self.settings.registry_url,
            )
            self._registry_logged_in = True
            logger.info(f"Logged in to registry: {self.settings.registry_url}")
            return True
        except DockerException as e:
            logger.warning(f"Failed to login to registry {self.settings.registry_url}: {e}")
            return False

    def push_image(self, image_tag: str) -> bool:
        """Push an image to the container registry.

        Args:
            image_tag: The local image tag to push.

        Returns:
            True if push succeeded, False otherwise.

        Raises:
            RegistryPushError: If registry is configured but push fails.
        """
        if not self.settings.registry_url:
            logger.debug("No registry configured, skipping push")
            return False

        if not self.login_to_registry():
            logger.warning("Cannot push: registry login failed")
            return False

        full_tag = self.get_full_image_tag(image_tag)

        try:
            # Tag the image with the full registry path
            local_image = self.docker_client.images.get(image_tag)
            local_image.tag(full_tag)

            # Push the image
            logger.info(f"Pushing image: {full_tag}")
            push_output = self.docker_client.images.push(full_tag, stream=True, decode=True)

            for line in push_output:
                if "error" in line:
                    raise RegistryPushError(f"Push failed: {line['error']}")
                if "status" in line:
                    logger.debug(f"Push: {line.get('status', '')} {line.get('progress', '')}")

            logger.info(f"Successfully pushed: {full_tag}")
            return True

        except ImageNotFound:
            logger.warning(f"Cannot push: image not found locally: {image_tag}")
            return False
        except DockerException as e:
            logger.warning(f"Failed to push image {full_tag}: {e}")
            return False

    def pull_image(self, image_tag: str) -> bool:
        """Pull an image from the container registry.

        Args:
            image_tag: The image tag to pull (without registry prefix).

        Returns:
            True if pull succeeded, False otherwise.

        Raises:
            RegistryPullError: If registry is configured but pull fails.
        """
        if not self.settings.registry_url:
            logger.debug("No registry configured, skipping pull")
            return False

        if not self.login_to_registry():
            logger.warning("Cannot pull: registry login failed")
            return False

        full_tag = self.get_full_image_tag(image_tag)

        try:
            logger.info(f"Pulling image: {full_tag}")
            self.docker_client.images.pull(full_tag)

            # Tag the pulled image with the local tag for easier reference
            pulled_image = self.docker_client.images.get(full_tag)
            pulled_image.tag(image_tag)

            logger.info(f"Successfully pulled and tagged: {image_tag}")
            return True

        except ImageNotFound:
            logger.debug(f"Image not found in registry: {full_tag}")
            return False
        except DockerException as e:
            logger.warning(f"Failed to pull image {full_tag}: {e}")
            return False

    # -------------------------------------------------------------------------
    # Dockerfile Generation
    # -------------------------------------------------------------------------

    def generate_deps_dockerfile(
        self,
        deps: DependencySpec,
        python_version: str | None = None,
    ) -> tuple[str, str]:
        """Generate a Dockerfile for the dependency layer.

        Args:
            deps: The dependency specification
            python_version: Python version override

        Returns:
            Tuple of (Dockerfile content, requirements.txt content)
        """
        py_version = python_version or deps.python_version or self.DEFAULT_PYTHON_VERSION
        base_image = self.BASE_IMAGES.get(py_version, self.BASE_IMAGES[self.DEFAULT_PYTHON_VERSION])

        requirements_lines = []
        for pkg in deps.packages:
            line = pkg.name
            if pkg.extras:
                line += f"[{','.join(pkg.extras)}]"
            if pkg.version:
                line += f"=={pkg.version}"
            requirements_lines.append(line)

        requirements_content = "\n".join(requirements_lines)

        dockerfile = f"""# syntax=docker/dockerfile:1
# Mellea Dependency Layer
# Auto-generated - do not edit manually

FROM {base_image}

# Install dependencies
WORKDIR /app

COPY requirements.txt /tmp/requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \\
    pip install -r /tmp/requirements.txt && \\
    rm /tmp/requirements.txt
"""
        return dockerfile, requirements_content

    def generate_program_dockerfile(
        self,
        program: ProgramAsset,
        deps_image_tag: str,
    ) -> str:
        """Generate a Dockerfile for the program layer.

        Args:
            program: The program asset
            deps_image_tag: Tag of the dependency layer image

        Returns:
            Dockerfile content as string
        """
        dockerfile = f"""# Mellea Program Image
# Program: {program.name} ({program.id})
# Auto-generated - do not edit manually

FROM {deps_image_tag}

# Copy program source code
COPY . /app/

# Set working directory
WORKDIR /app

# Set entrypoint
ENV MELLEA_ENTRYPOINT="{program.entrypoint}"

# Default command runs the entrypoint
CMD ["python", "{program.entrypoint}"]
"""
        return dockerfile

    # -------------------------------------------------------------------------
    # Build Operations
    # -------------------------------------------------------------------------

    def _build_with_kaniko(
        self,
        program: ProgramAsset,
        workspace_path: Path,
    ) -> BuildResult:
        """Build a Docker image using Kaniko in Kubernetes.

        This creates a Kubernetes Job that runs Kaniko to build the image
        in-cluster without requiring a Docker daemon.

        Args:
            program: The program to build an image for
            workspace_path: Path to the program's workspace directory

        Returns:
            BuildResult with job info (build runs asynchronously)
        """
        from mellea_api.services.kaniko_builder import get_kaniko_build_service

        kaniko_service = get_kaniko_build_service()

        # Generate the combined Dockerfile (deps + program in one)
        dockerfile_content = self._generate_kaniko_dockerfile(program)

        # Read workspace files for build context
        context_files: dict[str, str] = {}
        if workspace_path.exists():
            for file_path in workspace_path.rglob("*"):
                if file_path.is_file():
                    relative_path = file_path.relative_to(workspace_path)
                    # Skip hidden files and __pycache__
                    if not any(part.startswith(".") or part == "__pycache__"
                               for part in relative_path.parts):
                        try:
                            context_files[str(relative_path)] = file_path.read_text()
                        except UnicodeDecodeError:
                            # Skip binary files
                            logger.debug(f"Skipping binary file: {relative_path}")

        # Generate full image tag with registry
        if self.settings.registry_url:
            image_tag = f"{self.settings.registry_url}/{self.PROGRAM_IMAGE_PREFIX}:{program.id[:12]}"
        else:
            # For local Kind cluster, use localhost:5001
            image_tag = f"localhost:5001/{self.PROGRAM_IMAGE_PREFIX}:{program.id[:12]}"

        logger.info(f"Starting Kaniko build for {program.id} -> {image_tag}")

        return kaniko_service.create_build_job(
            program=program,
            dockerfile_content=dockerfile_content,
            context_files=context_files,
            image_tag=image_tag,
        )

    def _generate_kaniko_dockerfile(self, program: ProgramAsset) -> str:
        """Generate a single-stage Dockerfile for Kaniko builds.

        Unlike the two-layer Docker approach, Kaniko builds use a single
        Dockerfile that installs dependencies and copies source code.

        Args:
            program: The program to build

        Returns:
            Dockerfile content as string
        """
        py_version = program.dependencies.python_version or self.DEFAULT_PYTHON_VERSION
        base_image = self.BASE_IMAGES.get(py_version, self.BASE_IMAGES[self.DEFAULT_PYTHON_VERSION])

        # Generate requirements list
        requirements_lines = []
        for pkg in program.dependencies.packages:
            line = pkg.name
            if pkg.extras:
                line += f"[{','.join(pkg.extras)}]"
            if pkg.version:
                line += f"=={pkg.version}"
            requirements_lines.append(line)

        requirements_content = "\\n".join(requirements_lines)

        dockerfile = f"""# Mellea Program Image (Kaniko Build)
# Program: {program.name} ({program.id})
# Auto-generated - do not edit manually

FROM {base_image}

WORKDIR /app

# Install dependencies
RUN printf '%b' "{requirements_content}" > /tmp/requirements.txt && \\
    pip install --no-cache-dir -r /tmp/requirements.txt && \\
    rm /tmp/requirements.txt

# Copy program source code
COPY . /app/

# Set entrypoint
ENV MELLEA_ENTRYPOINT="{program.entrypoint}"

# Default command runs the entrypoint
CMD ["python", "{program.entrypoint}"]
"""
        return dockerfile

    def build_image(
        self,
        program: ProgramAsset,
        workspace_path: Path,
        force_rebuild: bool = False,
        push: bool = False,
    ) -> BuildResult:
        """Build a Docker image for a program with layer caching.

        This is the main entry point for building program images.
        Routes to either Docker or Kaniko backend based on settings.

        Args:
            program: The program to build an image for
            workspace_path: Path to the program's workspace directory
            force_rebuild: If True, skip cache lookup
            push: If True, push the built images to the registry after build

        Returns:
            BuildResult with success status and details
        """
        # Route to Kaniko backend if configured
        if self.settings.build_backend == "kaniko":
            return self._build_with_kaniko(program, workspace_path)

        # Use Docker backend (default)
        start_time = time.time()
        context = BuildContext(program_id=program.id)

        try:
            # STAGE: Preparing
            context.stage = BuildStage.PREPARING
            cache_key = self.compute_cache_key(program.dependencies)
            context.cache_key = cache_key
            logger.info(f"Build started for {program.id}, cache_key={cache_key[:12]}...")

            # STAGE: Cache lookup
            context.stage = BuildStage.CACHE_LOOKUP
            deps_image_tag: str | None = None

            if not force_rebuild:
                cached = self.get_cached_layer(cache_key)
                if cached and self.verify_cached_image_exists(cached.image_tag):
                    context.cache_hit = True
                    deps_image_tag = cached.image_tag
                    logger.info(f"Cache HIT: Using {deps_image_tag}")

            # STAGE: Build dependency layer (if cache miss)
            deps_build_start = time.time()
            if deps_image_tag is None:
                context.stage = BuildStage.BUILDING_DEPS
                deps_image_tag = self._build_dependency_layer(
                    program.dependencies, cache_key, context
                )
                # Push dependency layer to registry if requested
                if push:
                    self.push_image(deps_image_tag)
            context.deps_build_duration_seconds = time.time() - deps_build_start
            context.dependency_image_tag = deps_image_tag

            # STAGE: Build program layer
            context.stage = BuildStage.BUILDING_PROGRAM
            program_build_start = time.time()
            final_image_tag = self._build_program_layer(
                program, deps_image_tag, workspace_path, context
            )
            context.program_build_duration_seconds = time.time() - program_build_start
            context.final_image_tag = final_image_tag

            # Push program image to registry if requested
            if push:
                self.push_image(final_image_tag)

            # STAGE: Complete
            context.stage = BuildStage.COMPLETE
            total_duration = time.time() - start_time
            context.total_duration_seconds = total_duration

            logger.info(
                f"Build complete for {program.id}: {final_image_tag} "
                f"(cache_hit={context.cache_hit}, duration={total_duration:.2f}s)"
            )

            return BuildResult(
                program_id=program.id,
                success=True,
                image_tag=final_image_tag,
                cache_hit=context.cache_hit,
                total_duration_seconds=total_duration,
                deps_build_duration_seconds=context.deps_build_duration_seconds,
                program_build_duration_seconds=context.program_build_duration_seconds,
            )

        except Exception as e:
            context.stage = BuildStage.FAILED
            context.error_message = str(e)
            total_duration = time.time() - start_time

            logger.error(f"Build failed for {program.id}: {e}")

            return BuildResult(
                program_id=program.id,
                success=False,
                error_message=str(e),
                cache_hit=context.cache_hit,
                total_duration_seconds=total_duration,
            )

    def _build_dependency_layer(
        self,
        deps: DependencySpec,
        cache_key: str,
        context: BuildContext,
    ) -> str:
        """Build the dependency layer image.

        Uses BuildKit for pip cache mounts to speed up subsequent builds.

        Args:
            deps: Dependency specification
            cache_key: Cache key for this dependency set
            context: Build context for logging

        Returns:
            Image tag of the built dependency layer
        """
        image_tag = f"{self.DEPS_IMAGE_PREFIX}:{cache_key[:12]}"

        dockerfile_content, requirements_content = self.generate_deps_dockerfile(deps)

        with tempfile.TemporaryDirectory() as build_dir:
            build_path = Path(build_dir)

            (build_path / "Dockerfile").write_text(dockerfile_content)
            (build_path / "requirements.txt").write_text(requirements_content)

            logger.info(f"Building dependency layer: {image_tag}")
            try:
                # Enable BuildKit for cache mount support
                old_buildkit = os.environ.get("DOCKER_BUILDKIT")
                os.environ["DOCKER_BUILDKIT"] = "1"
                try:
                    image, build_logs = self.docker_client.images.build(
                        path=str(build_path),
                        tag=image_tag,
                        rm=True,
                        pull=False,
                    )
                finally:
                    # Restore previous DOCKER_BUILDKIT value
                    if old_buildkit is None:
                        os.environ.pop("DOCKER_BUILDKIT", None)
                    else:
                        os.environ["DOCKER_BUILDKIT"] = old_buildkit

                for log in build_logs:
                    if "stream" in log:
                        context.build_logs.append(log["stream"].strip())

            except DockerBuildError as e:
                raise ImageBuildError(f"Dependency layer build failed: {e}") from e

        try:
            image_info = self.docker_client.images.get(image_tag)
            size_bytes = image_info.attrs.get("Size")
        except DockerException:
            size_bytes = None

        self.create_cache_entry(cache_key, image_tag, deps, size_bytes)
        logger.info(f"Dependency layer cached: {image_tag}")

        return image_tag

    def _build_program_layer(
        self,
        program: ProgramAsset,
        deps_image_tag: str,
        workspace_path: Path,
        context: BuildContext,
    ) -> str:
        """Build the program layer image.

        Args:
            program: The program asset
            deps_image_tag: Tag of the dependency layer to use as base
            workspace_path: Path to the program's workspace
            context: Build context for logging

        Returns:
            Image tag of the built program image
        """
        image_tag = f"{self.PROGRAM_IMAGE_PREFIX}:{program.id[:12]}"

        dockerfile_content = self.generate_program_dockerfile(program, deps_image_tag)

        if not workspace_path.exists():
            raise ImageBuildError(f"Workspace not found: {workspace_path}")

        dockerfile_path = workspace_path / "Dockerfile"
        try:
            dockerfile_path.write_text(dockerfile_content)

            logger.info(f"Building program layer: {image_tag}")
            image, build_logs = self.docker_client.images.build(
                path=str(workspace_path),
                tag=image_tag,
                rm=True,
            )

            for log in build_logs:
                if "stream" in log:
                    context.build_logs.append(log["stream"].strip())

        except DockerBuildError as e:
            raise ImageBuildError(f"Program layer build failed: {e}") from e
        finally:
            if dockerfile_path.exists():
                dockerfile_path.unlink()

        return image_tag


# Global service instance
_environment_builder_service: EnvironmentBuilderService | None = None


def get_environment_builder_service() -> EnvironmentBuilderService:
    """Get the global EnvironmentBuilder service instance."""
    global _environment_builder_service
    if _environment_builder_service is None:
        _environment_builder_service = EnvironmentBuilderService()
    return _environment_builder_service
