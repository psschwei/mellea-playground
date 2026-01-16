"""ArtifactCollectorService for managing run artifacts with quota enforcement."""

import hashlib
import logging
import mimetypes
import shutil
from datetime import datetime, timedelta
from pathlib import Path

from mellea_api.core.config import Settings, get_settings
from mellea_api.core.store import JsonStore
from mellea_api.models.artifact import Artifact, ArtifactType, ArtifactUsage
from mellea_api.models.user import UserQuotas

logger = logging.getLogger(__name__)


class ArtifactNotFoundError(Exception):
    """Raised when an artifact is not found."""

    pass


class QuotaExceededError(Exception):
    """Raised when a user's storage quota would be exceeded."""

    def __init__(self, message: str, current_usage: int, quota_limit: int, requested: int):
        super().__init__(message)
        self.current_usage = current_usage
        self.quota_limit = quota_limit
        self.requested = requested


class ArtifactTooLargeError(Exception):
    """Raised when an artifact exceeds the maximum allowed size."""

    def __init__(self, message: str, size: int, max_size: int):
        super().__init__(message)
        self.size = size
        self.max_size = max_size


class ArtifactCollectorService:
    """Service for collecting and managing run artifacts with quota enforcement.

    Handles storage of artifacts generated during program execution, enforcing
    user storage quotas and automatic cleanup of expired artifacts.

    Example:
        ```python
        service = get_artifact_collector_service()

        # Collect an artifact from a run
        artifact = service.collect_artifact(
            run_id="run-123",
            owner_id="user-456",
            source_path=Path("/tmp/output.json"),
            name="results.json",
            user_quotas=user.quotas,
        )

        # Get user's storage usage
        usage = service.get_user_usage("user-456")
        print(f"Using {usage.total_bytes} of {user.quotas.max_storage_mb * 1024 * 1024}")

        # Clean up expired artifacts
        deleted = service.cleanup_expired_artifacts()
        ```
    """

    def __init__(self, settings: Settings | None = None) -> None:
        """Initialize the ArtifactCollectorService.

        Args:
            settings: Application settings (uses default if not provided)
        """
        self.settings = settings or get_settings()
        self._artifact_store: JsonStore[Artifact] | None = None
        self._usage_store: JsonStore[ArtifactUsage] | None = None

    # -------------------------------------------------------------------------
    # Store Properties (lazy initialization)
    # -------------------------------------------------------------------------

    @property
    def artifact_store(self) -> JsonStore[Artifact]:
        """Get the artifact metadata store, initializing if needed."""
        if self._artifact_store is None:
            file_path = self.settings.data_dir / "metadata" / "artifacts.json"
            self._artifact_store = JsonStore[Artifact](
                file_path=file_path,
                collection_key="artifacts",
                model_class=Artifact,
            )
        return self._artifact_store

    @property
    def usage_store(self) -> JsonStore[ArtifactUsage]:
        """Get the usage tracking store, initializing if needed."""
        if self._usage_store is None:
            file_path = self.settings.data_dir / "metadata" / "artifact_usage.json"
            self._usage_store = JsonStore[ArtifactUsage](
                file_path=file_path,
                collection_key="usage",
                model_class=ArtifactUsage,
            )
        return self._usage_store

    @property
    def artifacts_dir(self) -> Path:
        """Get the artifacts storage directory."""
        return self.settings.data_dir / "artifacts"

    # -------------------------------------------------------------------------
    # Quota Validation
    # -------------------------------------------------------------------------

    def _check_quota(
        self, owner_id: str, size_bytes: int, user_quotas: UserQuotas
    ) -> None:
        """Check if storing an artifact would exceed the user's quota.

        Args:
            owner_id: ID of the artifact owner
            size_bytes: Size of the artifact to store
            user_quotas: User's quota limits

        Raises:
            QuotaExceededError: If storing the artifact would exceed quota
            ArtifactTooLargeError: If artifact exceeds single-file size limit
        """
        # Check single-file size limit
        max_single_size = self.settings.artifact_max_single_size_mb * 1024 * 1024
        if size_bytes > max_single_size:
            raise ArtifactTooLargeError(
                f"Artifact size ({size_bytes} bytes) exceeds maximum allowed size "
                f"({max_single_size} bytes)",
                size=size_bytes,
                max_size=max_single_size,
            )

        # Check user quota
        usage = self.get_user_usage(owner_id)
        quota_bytes = user_quotas.max_storage_mb * 1024 * 1024

        if usage.total_bytes + size_bytes > quota_bytes:
            raise QuotaExceededError(
                f"Storing this artifact ({size_bytes} bytes) would exceed your "
                f"storage quota. Current usage: {usage.total_bytes} bytes, "
                f"Quota: {quota_bytes} bytes",
                current_usage=usage.total_bytes,
                quota_limit=quota_bytes,
                requested=size_bytes,
            )

    def _update_usage(self, owner_id: str, delta_bytes: int, delta_count: int) -> None:
        """Update a user's storage usage.

        Args:
            owner_id: ID of the user
            delta_bytes: Change in bytes (positive for add, negative for remove)
            delta_count: Change in artifact count
        """
        existing = self.usage_store.get_by_id(owner_id)

        if existing:
            existing.total_bytes = max(0, existing.total_bytes + delta_bytes)
            existing.artifact_count = max(0, existing.artifact_count + delta_count)
            existing.last_updated = datetime.utcnow()
            self.usage_store.update(owner_id, existing)
        else:
            # Create new usage record - id is set automatically from user_id
            new_usage = ArtifactUsage(
                userId=owner_id,
                total_bytes=max(0, delta_bytes),
                artifact_count=max(0, delta_count),
            )
            self.usage_store.create(new_usage)

    # -------------------------------------------------------------------------
    # File Operations
    # -------------------------------------------------------------------------

    def _compute_checksum(self, file_path: Path) -> str:
        """Compute SHA-256 checksum of a file.

        Args:
            file_path: Path to the file

        Returns:
            Hex-encoded SHA-256 checksum
        """
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()

    def _get_storage_path(self, run_id: str, artifact_id: str, name: str) -> str:
        """Generate a storage path for an artifact.

        Args:
            run_id: ID of the run
            artifact_id: ID of the artifact
            name: Original filename

        Returns:
            Relative storage path within artifacts directory
        """
        # Organize by run_id for easy cleanup when runs are deleted
        return f"{run_id}/{artifact_id}/{name}"

    # -------------------------------------------------------------------------
    # CRUD Operations
    # -------------------------------------------------------------------------

    def collect_artifact(
        self,
        run_id: str,
        owner_id: str,
        source_path: Path,
        name: str,
        user_quotas: UserQuotas,
        artifact_type: ArtifactType = ArtifactType.FILE,
        tags: list[str] | None = None,
        metadata: dict[str, str] | None = None,
        retention_days: int | None = None,
    ) -> Artifact:
        """Collect an artifact from a source file and store it.

        Args:
            run_id: ID of the run that produced this artifact
            owner_id: ID of the user who owns this artifact
            source_path: Path to the source file to collect
            name: Name for the artifact
            user_quotas: User's quota limits for validation
            artifact_type: Type of artifact
            tags: Optional tags for categorization
            metadata: Optional additional metadata
            retention_days: Days to retain (None uses default, 0 = never expire)

        Returns:
            The created Artifact

        Raises:
            FileNotFoundError: If source file doesn't exist
            QuotaExceededError: If storing would exceed user's quota
            ArtifactTooLargeError: If artifact exceeds size limit
        """
        if not source_path.exists():
            raise FileNotFoundError(f"Source file not found: {source_path}")

        # Get file size and validate quotas
        size_bytes = source_path.stat().st_size
        self._check_quota(owner_id, size_bytes, user_quotas)

        # Create artifact record
        artifact = Artifact(
            runId=run_id,
            ownerId=owner_id,
            name=name,
            artifact_type=artifact_type,
            size_bytes=size_bytes,
            storagePath="",  # Will be set after we have the ID
            mime_type=mimetypes.guess_type(name)[0],
            tags=tags or [],
            metadata=metadata or {},
        )

        # Set storage path now that we have the ID
        storage_path = self._get_storage_path(run_id, artifact.id, name)
        artifact.storage_path = storage_path

        # Compute checksum
        artifact.checksum = self._compute_checksum(source_path)

        # Set expiration
        if retention_days is None:
            retention_days = self.settings.artifact_retention_days
        if retention_days > 0:
            artifact.expires_at = datetime.utcnow() + timedelta(days=retention_days)

        # Copy file to storage
        dest_path = self.artifacts_dir / storage_path
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, dest_path)

        # Save metadata and update usage
        created = self.artifact_store.create(artifact)
        self._update_usage(owner_id, size_bytes, 1)

        logger.info(
            f"Collected artifact {created.id} ({name}, {size_bytes} bytes) "
            f"for run {run_id}, owner {owner_id}"
        )

        return created

    def collect_artifact_from_bytes(
        self,
        run_id: str,
        owner_id: str,
        content: bytes,
        name: str,
        user_quotas: UserQuotas,
        artifact_type: ArtifactType = ArtifactType.FILE,
        tags: list[str] | None = None,
        metadata: dict[str, str] | None = None,
        retention_days: int | None = None,
    ) -> Artifact:
        """Collect an artifact from bytes content.

        Args:
            run_id: ID of the run that produced this artifact
            owner_id: ID of the user who owns this artifact
            content: Raw bytes content to store
            name: Name for the artifact
            user_quotas: User's quota limits for validation
            artifact_type: Type of artifact
            tags: Optional tags for categorization
            metadata: Optional additional metadata
            retention_days: Days to retain (None uses default, 0 = never expire)

        Returns:
            The created Artifact

        Raises:
            QuotaExceededError: If storing would exceed user's quota
            ArtifactTooLargeError: If artifact exceeds size limit
        """
        size_bytes = len(content)
        self._check_quota(owner_id, size_bytes, user_quotas)

        # Create artifact record
        artifact = Artifact(
            runId=run_id,
            ownerId=owner_id,
            name=name,
            artifact_type=artifact_type,
            size_bytes=size_bytes,
            storagePath="",
            mime_type=mimetypes.guess_type(name)[0],
            tags=tags or [],
            metadata=metadata or {},
        )

        # Set storage path
        storage_path = self._get_storage_path(run_id, artifact.id, name)
        artifact.storage_path = storage_path

        # Compute checksum
        artifact.checksum = hashlib.sha256(content).hexdigest()

        # Set expiration
        if retention_days is None:
            retention_days = self.settings.artifact_retention_days
        if retention_days > 0:
            artifact.expires_at = datetime.utcnow() + timedelta(days=retention_days)

        # Write content to storage
        dest_path = self.artifacts_dir / storage_path
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        dest_path.write_bytes(content)

        # Save metadata and update usage
        created = self.artifact_store.create(artifact)
        self._update_usage(owner_id, size_bytes, 1)

        logger.info(
            f"Collected artifact {created.id} ({name}, {size_bytes} bytes) "
            f"from bytes for run {run_id}, owner {owner_id}"
        )

        return created

    def get_artifact(self, artifact_id: str) -> Artifact | None:
        """Get an artifact by ID.

        Args:
            artifact_id: Artifact's unique identifier

        Returns:
            Artifact if found, None otherwise
        """
        return self.artifact_store.get_by_id(artifact_id)

    def get_artifact_content(self, artifact_id: str) -> bytes:
        """Get the content of an artifact.

        Args:
            artifact_id: Artifact's unique identifier

        Returns:
            Raw bytes content of the artifact

        Raises:
            ArtifactNotFoundError: If artifact doesn't exist
            FileNotFoundError: If artifact file is missing
        """
        artifact = self.artifact_store.get_by_id(artifact_id)
        if artifact is None:
            raise ArtifactNotFoundError(f"Artifact not found: {artifact_id}")

        file_path = self.artifacts_dir / artifact.storage_path
        if not file_path.exists():
            raise FileNotFoundError(f"Artifact file missing: {file_path}")

        return file_path.read_bytes()

    def get_artifact_path(self, artifact_id: str) -> Path:
        """Get the filesystem path to an artifact.

        Args:
            artifact_id: Artifact's unique identifier

        Returns:
            Path to the artifact file

        Raises:
            ArtifactNotFoundError: If artifact doesn't exist
        """
        artifact = self.artifact_store.get_by_id(artifact_id)
        if artifact is None:
            raise ArtifactNotFoundError(f"Artifact not found: {artifact_id}")

        return self.artifacts_dir / artifact.storage_path

    def list_artifacts(
        self,
        owner_id: str | None = None,
        run_id: str | None = None,
        artifact_type: ArtifactType | None = None,
        tags: list[str] | None = None,
    ) -> list[Artifact]:
        """List artifacts with optional filtering.

        Args:
            owner_id: Filter by owner ID
            run_id: Filter by run ID
            artifact_type: Filter by artifact type
            tags: Filter by tags (artifact must have all specified tags)

        Returns:
            List of matching artifacts
        """
        artifacts = self.artifact_store.list_all()

        if owner_id:
            artifacts = [a for a in artifacts if a.owner_id == owner_id]

        if run_id:
            artifacts = [a for a in artifacts if a.run_id == run_id]

        if artifact_type:
            artifacts = [a for a in artifacts if a.artifact_type == artifact_type]

        if tags:
            artifacts = [a for a in artifacts if all(t in a.tags for t in tags)]

        return artifacts

    def delete_artifact(self, artifact_id: str) -> bool:
        """Delete an artifact and its stored file.

        Args:
            artifact_id: Artifact's unique identifier

        Returns:
            True if deleted, False if not found
        """
        artifact = self.artifact_store.get_by_id(artifact_id)
        if artifact is None:
            return False

        # Delete the file
        file_path = self.artifacts_dir / artifact.storage_path
        if file_path.exists():
            file_path.unlink()
            # Clean up empty parent directories
            try:
                file_path.parent.rmdir()
                file_path.parent.parent.rmdir()
            except OSError:
                pass  # Directory not empty, that's fine

        # Update usage
        self._update_usage(artifact.owner_id, -artifact.size_bytes, -1)

        # Delete metadata
        deleted = self.artifact_store.delete(artifact_id)
        if deleted:
            logger.info(f"Deleted artifact {artifact_id}")

        return deleted

    def delete_artifacts_for_run(self, run_id: str) -> int:
        """Delete all artifacts associated with a run.

        Args:
            run_id: Run's unique identifier

        Returns:
            Number of artifacts deleted
        """
        artifacts = self.list_artifacts(run_id=run_id)
        deleted_count = 0

        for artifact in artifacts:
            if self.delete_artifact(artifact.id):
                deleted_count += 1

        # Also clean up the run directory
        run_dir = self.artifacts_dir / run_id
        if run_dir.exists():
            shutil.rmtree(run_dir, ignore_errors=True)

        logger.info(f"Deleted {deleted_count} artifacts for run {run_id}")
        return deleted_count

    # -------------------------------------------------------------------------
    # Usage Operations
    # -------------------------------------------------------------------------

    def get_user_usage(self, user_id: str) -> ArtifactUsage:
        """Get storage usage for a user.

        Args:
            user_id: User's unique identifier

        Returns:
            ArtifactUsage record (created with zeros if not found)
        """
        usage = self.usage_store.get_by_id(user_id)
        if usage is None:
            return ArtifactUsage(userId=user_id)
        return usage

    def recalculate_user_usage(self, user_id: str) -> ArtifactUsage:
        """Recalculate storage usage for a user from actual artifacts.

        Useful for fixing discrepancies in usage tracking.

        Args:
            user_id: User's unique identifier

        Returns:
            Updated ArtifactUsage record
        """
        artifacts = self.list_artifacts(owner_id=user_id)
        total_bytes = sum(a.size_bytes for a in artifacts)
        artifact_count = len(artifacts)

        existing = self.usage_store.get_by_id(user_id)
        if existing:
            existing.total_bytes = total_bytes
            existing.artifact_count = artifact_count
            existing.last_updated = datetime.utcnow()
            self.usage_store.update(user_id, existing)
            usage = existing
        else:
            usage = ArtifactUsage(
                userId=user_id,
                total_bytes=total_bytes,
                artifact_count=artifact_count,
            )
            self.usage_store.create(usage)

        logger.info(
            f"Recalculated usage for user {user_id}: "
            f"{total_bytes} bytes, {artifact_count} artifacts"
        )

        return usage

    # -------------------------------------------------------------------------
    # Cleanup Operations
    # -------------------------------------------------------------------------

    def cleanup_expired_artifacts(self) -> int:
        """Delete all artifacts that have passed their expiration date.

        Returns:
            Number of artifacts deleted
        """
        now = datetime.utcnow()
        artifacts = self.artifact_store.list_all()
        deleted_count = 0

        for artifact in artifacts:
            if artifact.expires_at and artifact.expires_at < now:
                if self.delete_artifact(artifact.id):
                    deleted_count += 1

        if deleted_count > 0:
            logger.info(f"Cleaned up {deleted_count} expired artifacts")

        return deleted_count


# Global service instance
_artifact_collector_service: ArtifactCollectorService | None = None


def get_artifact_collector_service() -> ArtifactCollectorService:
    """Get the global ArtifactCollectorService instance."""
    global _artifact_collector_service
    if _artifact_collector_service is None:
        _artifact_collector_service = ArtifactCollectorService()
    return _artifact_collector_service
