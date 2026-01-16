"""Tests for ArtifactCollectorService with quota enforcement."""

import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from mellea_api.core.config import Settings
from mellea_api.models.artifact import ArtifactType
from mellea_api.models.user import UserQuotas
from mellea_api.services.artifact_collector import (
    ArtifactCollectorService,
    ArtifactNotFoundError,
    ArtifactTooLargeError,
    QuotaExceededError,
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
        artifact_retention_days=30,
        artifact_max_single_size_mb=10,  # 10MB for tests
    )
    settings.ensure_data_dirs()
    return settings


@pytest.fixture
def artifact_service(settings: Settings):
    """Create an ArtifactCollectorService with test settings."""
    return ArtifactCollectorService(settings=settings)


@pytest.fixture
def user_quotas():
    """Create default user quotas for tests."""
    return UserQuotas(max_storage_mb=100)  # 100MB quota


@pytest.fixture
def small_quotas():
    """Create small user quotas for testing quota enforcement."""
    return UserQuotas(max_storage_mb=1)  # 1MB quota


@pytest.fixture
def sample_file(temp_data_dir: Path):
    """Create a sample file for testing."""
    file_path = temp_data_dir / "sample.txt"
    file_path.write_text("Hello, World!" * 100)
    return file_path


@pytest.fixture
def large_file(temp_data_dir: Path):
    """Create a file larger than max single size limit."""
    file_path = temp_data_dir / "large.bin"
    # Create a 15MB file (larger than 10MB limit in test settings)
    file_path.write_bytes(b"x" * (15 * 1024 * 1024))
    return file_path


class TestCollectArtifact:
    """Tests for collecting artifacts from files."""

    def test_collect_artifact_basic(
        self,
        artifact_service: ArtifactCollectorService,
        sample_file: Path,
        user_quotas: UserQuotas,
    ):
        """Test basic artifact collection."""
        artifact = artifact_service.collect_artifact(
            run_id="run-123",
            owner_id="user-456",
            source_path=sample_file,
            name="sample.txt",
            user_quotas=user_quotas,
        )

        assert artifact.id is not None
        assert artifact.run_id == "run-123"
        assert artifact.owner_id == "user-456"
        assert artifact.name == "sample.txt"
        assert artifact.size_bytes > 0
        assert artifact.checksum is not None
        assert artifact.created_at is not None
        assert artifact.expires_at is not None

    def test_collect_artifact_with_tags(
        self,
        artifact_service: ArtifactCollectorService,
        sample_file: Path,
        user_quotas: UserQuotas,
    ):
        """Test artifact collection with tags."""
        artifact = artifact_service.collect_artifact(
            run_id="run-123",
            owner_id="user-456",
            source_path=sample_file,
            name="output.json",
            user_quotas=user_quotas,
            tags=["output", "json", "results"],
        )

        assert artifact.tags == ["output", "json", "results"]

    def test_collect_artifact_with_metadata(
        self,
        artifact_service: ArtifactCollectorService,
        sample_file: Path,
        user_quotas: UserQuotas,
    ):
        """Test artifact collection with metadata."""
        artifact = artifact_service.collect_artifact(
            run_id="run-123",
            owner_id="user-456",
            source_path=sample_file,
            name="output.json",
            user_quotas=user_quotas,
            metadata={"version": "1.0", "format": "json"},
        )

        assert artifact.metadata == {"version": "1.0", "format": "json"}

    def test_collect_artifact_custom_retention(
        self,
        artifact_service: ArtifactCollectorService,
        sample_file: Path,
        user_quotas: UserQuotas,
    ):
        """Test artifact collection with custom retention."""
        artifact = artifact_service.collect_artifact(
            run_id="run-123",
            owner_id="user-456",
            source_path=sample_file,
            name="temp.txt",
            user_quotas=user_quotas,
            retention_days=7,
        )

        # Should expire in approximately 7 days
        expected_expiry = datetime.utcnow() + timedelta(days=7)
        assert artifact.expires_at is not None
        assert abs((artifact.expires_at - expected_expiry).total_seconds()) < 60

    def test_collect_artifact_no_expiration(
        self,
        artifact_service: ArtifactCollectorService,
        sample_file: Path,
        user_quotas: UserQuotas,
    ):
        """Test artifact collection with no expiration."""
        artifact = artifact_service.collect_artifact(
            run_id="run-123",
            owner_id="user-456",
            source_path=sample_file,
            name="permanent.txt",
            user_quotas=user_quotas,
            retention_days=0,
        )

        assert artifact.expires_at is None

    def test_collect_artifact_file_not_found(
        self,
        artifact_service: ArtifactCollectorService,
        user_quotas: UserQuotas,
    ):
        """Test collecting from non-existent file."""
        with pytest.raises(FileNotFoundError):
            artifact_service.collect_artifact(
                run_id="run-123",
                owner_id="user-456",
                source_path=Path("/non/existent/file.txt"),
                name="missing.txt",
                user_quotas=user_quotas,
            )

    def test_collect_artifact_copies_file(
        self,
        artifact_service: ArtifactCollectorService,
        sample_file: Path,
        user_quotas: UserQuotas,
    ):
        """Test that artifact collection copies the file."""
        artifact = artifact_service.collect_artifact(
            run_id="run-123",
            owner_id="user-456",
            source_path=sample_file,
            name="sample.txt",
            user_quotas=user_quotas,
        )

        # Verify file exists in storage
        storage_path = artifact_service.artifacts_dir / artifact.storage_path
        assert storage_path.exists()
        assert storage_path.read_text() == sample_file.read_text()


class TestCollectArtifactFromBytes:
    """Tests for collecting artifacts from bytes."""

    def test_collect_from_bytes_basic(
        self,
        artifact_service: ArtifactCollectorService,
        user_quotas: UserQuotas,
    ):
        """Test basic artifact collection from bytes."""
        content = b"Test content for artifact"

        artifact = artifact_service.collect_artifact_from_bytes(
            run_id="run-123",
            owner_id="user-456",
            content=content,
            name="output.bin",
            user_quotas=user_quotas,
        )

        assert artifact.size_bytes == len(content)
        assert artifact.checksum is not None

        # Verify stored content
        stored = artifact_service.get_artifact_content(artifact.id)
        assert stored == content

    def test_collect_from_bytes_with_type(
        self,
        artifact_service: ArtifactCollectorService,
        user_quotas: UserQuotas,
    ):
        """Test artifact collection with specific type."""
        artifact = artifact_service.collect_artifact_from_bytes(
            run_id="run-123",
            owner_id="user-456",
            content=b"log entry 1\nlog entry 2\n",
            name="execution.log",
            user_quotas=user_quotas,
            artifact_type=ArtifactType.LOG,
        )

        assert artifact.artifact_type == ArtifactType.LOG


class TestQuotaEnforcement:
    """Tests for storage quota enforcement."""

    def test_quota_exceeded_error(
        self,
        artifact_service: ArtifactCollectorService,
        small_quotas: UserQuotas,
    ):
        """Test that quota exceeded error is raised."""
        # Try to store more than 1MB
        large_content = b"x" * (2 * 1024 * 1024)  # 2MB

        with pytest.raises(QuotaExceededError) as exc_info:
            artifact_service.collect_artifact_from_bytes(
                run_id="run-123",
                owner_id="user-456",
                content=large_content,
                name="large.bin",
                user_quotas=small_quotas,
            )

        assert exc_info.value.current_usage == 0
        assert exc_info.value.quota_limit == 1024 * 1024  # 1MB
        assert exc_info.value.requested == len(large_content)

    def test_artifact_too_large_error(
        self,
        artifact_service: ArtifactCollectorService,
        large_file: Path,
        user_quotas: UserQuotas,
    ):
        """Test that artifact too large error is raised."""
        with pytest.raises(ArtifactTooLargeError) as exc_info:
            artifact_service.collect_artifact(
                run_id="run-123",
                owner_id="user-456",
                source_path=large_file,
                name="huge.bin",
                user_quotas=user_quotas,
            )

        assert exc_info.value.max_size == 10 * 1024 * 1024  # 10MB

    def test_quota_accumulation(
        self,
        artifact_service: ArtifactCollectorService,
        small_quotas: UserQuotas,
    ):
        """Test that quota tracks accumulated usage."""
        owner_id = "user-456"

        # First artifact: 500KB
        artifact_service.collect_artifact_from_bytes(
            run_id="run-1",
            owner_id=owner_id,
            content=b"x" * (500 * 1024),
            name="file1.bin",
            user_quotas=small_quotas,
        )

        # Second artifact: 400KB (total 900KB, under 1MB)
        artifact_service.collect_artifact_from_bytes(
            run_id="run-2",
            owner_id=owner_id,
            content=b"y" * (400 * 1024),
            name="file2.bin",
            user_quotas=small_quotas,
        )

        # Third artifact: 200KB (would exceed 1MB quota)
        with pytest.raises(QuotaExceededError):
            artifact_service.collect_artifact_from_bytes(
                run_id="run-3",
                owner_id=owner_id,
                content=b"z" * (200 * 1024),
                name="file3.bin",
                user_quotas=small_quotas,
            )


class TestGetArtifact:
    """Tests for getting artifacts."""

    def test_get_artifact_exists(
        self,
        artifact_service: ArtifactCollectorService,
        user_quotas: UserQuotas,
    ):
        """Test getting an existing artifact."""
        created = artifact_service.collect_artifact_from_bytes(
            run_id="run-123",
            owner_id="user-456",
            content=b"test content",
            name="test.txt",
            user_quotas=user_quotas,
        )

        fetched = artifact_service.get_artifact(created.id)

        assert fetched is not None
        assert fetched.id == created.id
        assert fetched.name == "test.txt"

    def test_get_artifact_not_found(
        self,
        artifact_service: ArtifactCollectorService,
    ):
        """Test getting a non-existent artifact."""
        result = artifact_service.get_artifact("non-existent-id")
        assert result is None

    def test_get_artifact_content(
        self,
        artifact_service: ArtifactCollectorService,
        user_quotas: UserQuotas,
    ):
        """Test getting artifact content."""
        original_content = b"Original artifact content"
        artifact = artifact_service.collect_artifact_from_bytes(
            run_id="run-123",
            owner_id="user-456",
            content=original_content,
            name="content.bin",
            user_quotas=user_quotas,
        )

        content = artifact_service.get_artifact_content(artifact.id)
        assert content == original_content

    def test_get_artifact_content_not_found(
        self,
        artifact_service: ArtifactCollectorService,
    ):
        """Test getting content of non-existent artifact."""
        with pytest.raises(ArtifactNotFoundError):
            artifact_service.get_artifact_content("non-existent-id")


class TestListArtifacts:
    """Tests for listing artifacts."""

    def test_list_artifacts_empty(
        self,
        artifact_service: ArtifactCollectorService,
    ):
        """Test listing when no artifacts exist."""
        artifacts = artifact_service.list_artifacts()
        assert artifacts == []

    def test_list_artifacts_all(
        self,
        artifact_service: ArtifactCollectorService,
        user_quotas: UserQuotas,
    ):
        """Test listing all artifacts."""
        for i in range(3):
            artifact_service.collect_artifact_from_bytes(
                run_id=f"run-{i}",
                owner_id="user-456",
                content=f"content {i}".encode(),
                name=f"file{i}.txt",
                user_quotas=user_quotas,
            )

        artifacts = artifact_service.list_artifacts()
        assert len(artifacts) == 3

    def test_list_artifacts_filter_by_owner(
        self,
        artifact_service: ArtifactCollectorService,
        user_quotas: UserQuotas,
    ):
        """Test filtering artifacts by owner."""
        artifact_service.collect_artifact_from_bytes(
            run_id="run-1",
            owner_id="user-1",
            content=b"content",
            name="file1.txt",
            user_quotas=user_quotas,
        )
        artifact_service.collect_artifact_from_bytes(
            run_id="run-2",
            owner_id="user-2",
            content=b"content",
            name="file2.txt",
            user_quotas=user_quotas,
        )

        user1_artifacts = artifact_service.list_artifacts(owner_id="user-1")
        assert len(user1_artifacts) == 1
        assert user1_artifacts[0].owner_id == "user-1"

    def test_list_artifacts_filter_by_run(
        self,
        artifact_service: ArtifactCollectorService,
        user_quotas: UserQuotas,
    ):
        """Test filtering artifacts by run."""
        artifact_service.collect_artifact_from_bytes(
            run_id="run-1",
            owner_id="user-1",
            content=b"content",
            name="file1.txt",
            user_quotas=user_quotas,
        )
        artifact_service.collect_artifact_from_bytes(
            run_id="run-1",
            owner_id="user-1",
            content=b"content",
            name="file2.txt",
            user_quotas=user_quotas,
        )
        artifact_service.collect_artifact_from_bytes(
            run_id="run-2",
            owner_id="user-1",
            content=b"content",
            name="file3.txt",
            user_quotas=user_quotas,
        )

        run1_artifacts = artifact_service.list_artifacts(run_id="run-1")
        assert len(run1_artifacts) == 2

    def test_list_artifacts_filter_by_tags(
        self,
        artifact_service: ArtifactCollectorService,
        user_quotas: UserQuotas,
    ):
        """Test filtering artifacts by tags."""
        artifact_service.collect_artifact_from_bytes(
            run_id="run-1",
            owner_id="user-1",
            content=b"content",
            name="output.json",
            user_quotas=user_quotas,
            tags=["output", "json"],
        )
        artifact_service.collect_artifact_from_bytes(
            run_id="run-2",
            owner_id="user-1",
            content=b"content",
            name="log.txt",
            user_quotas=user_quotas,
            tags=["log"],
        )

        json_artifacts = artifact_service.list_artifacts(tags=["json"])
        assert len(json_artifacts) == 1
        assert "json" in json_artifacts[0].tags


class TestDeleteArtifact:
    """Tests for deleting artifacts."""

    def test_delete_artifact_success(
        self,
        artifact_service: ArtifactCollectorService,
        user_quotas: UserQuotas,
    ):
        """Test successful artifact deletion."""
        artifact = artifact_service.collect_artifact_from_bytes(
            run_id="run-123",
            owner_id="user-456",
            content=b"to be deleted",
            name="temp.txt",
            user_quotas=user_quotas,
        )

        # Verify file exists
        storage_path = artifact_service.artifacts_dir / artifact.storage_path
        assert storage_path.exists()

        # Delete
        result = artifact_service.delete_artifact(artifact.id)
        assert result is True

        # Verify file is gone
        assert not storage_path.exists()

        # Verify metadata is gone
        assert artifact_service.get_artifact(artifact.id) is None

    def test_delete_artifact_not_found(
        self,
        artifact_service: ArtifactCollectorService,
    ):
        """Test deleting non-existent artifact."""
        result = artifact_service.delete_artifact("non-existent-id")
        assert result is False

    def test_delete_updates_usage(
        self,
        artifact_service: ArtifactCollectorService,
        user_quotas: UserQuotas,
    ):
        """Test that deletion updates usage tracking."""
        owner_id = "user-456"
        content = b"test content" * 1000

        artifact = artifact_service.collect_artifact_from_bytes(
            run_id="run-123",
            owner_id=owner_id,
            content=content,
            name="test.txt",
            user_quotas=user_quotas,
        )

        # Check usage before deletion
        usage_before = artifact_service.get_user_usage(owner_id)
        assert usage_before.total_bytes == len(content)
        assert usage_before.artifact_count == 1

        # Delete
        artifact_service.delete_artifact(artifact.id)

        # Check usage after deletion
        usage_after = artifact_service.get_user_usage(owner_id)
        assert usage_after.total_bytes == 0
        assert usage_after.artifact_count == 0

    def test_delete_artifacts_for_run(
        self,
        artifact_service: ArtifactCollectorService,
        user_quotas: UserQuotas,
    ):
        """Test deleting all artifacts for a run."""
        run_id = "run-123"

        # Create multiple artifacts for the run
        for i in range(3):
            artifact_service.collect_artifact_from_bytes(
                run_id=run_id,
                owner_id="user-456",
                content=f"content {i}".encode(),
                name=f"file{i}.txt",
                user_quotas=user_quotas,
            )

        # Create artifact for different run
        artifact_service.collect_artifact_from_bytes(
            run_id="run-other",
            owner_id="user-456",
            content=b"other content",
            name="other.txt",
            user_quotas=user_quotas,
        )

        # Delete artifacts for the run
        deleted_count = artifact_service.delete_artifacts_for_run(run_id)
        assert deleted_count == 3

        # Verify run artifacts are gone
        remaining = artifact_service.list_artifacts(run_id=run_id)
        assert len(remaining) == 0

        # Verify other run artifact still exists
        other_remaining = artifact_service.list_artifacts(run_id="run-other")
        assert len(other_remaining) == 1


class TestUsageTracking:
    """Tests for usage tracking."""

    def test_get_user_usage_empty(
        self,
        artifact_service: ArtifactCollectorService,
    ):
        """Test getting usage for user with no artifacts."""
        usage = artifact_service.get_user_usage("new-user")

        assert usage.user_id == "new-user"
        assert usage.total_bytes == 0
        assert usage.artifact_count == 0

    def test_get_user_usage_with_artifacts(
        self,
        artifact_service: ArtifactCollectorService,
        user_quotas: UserQuotas,
    ):
        """Test getting usage for user with artifacts."""
        owner_id = "user-456"
        content1 = b"content one"
        content2 = b"content two"

        artifact_service.collect_artifact_from_bytes(
            run_id="run-1",
            owner_id=owner_id,
            content=content1,
            name="file1.txt",
            user_quotas=user_quotas,
        )
        artifact_service.collect_artifact_from_bytes(
            run_id="run-2",
            owner_id=owner_id,
            content=content2,
            name="file2.txt",
            user_quotas=user_quotas,
        )

        usage = artifact_service.get_user_usage(owner_id)

        assert usage.total_bytes == len(content1) + len(content2)
        assert usage.artifact_count == 2

    def test_recalculate_user_usage(
        self,
        artifact_service: ArtifactCollectorService,
        user_quotas: UserQuotas,
    ):
        """Test recalculating user usage from actual artifacts."""
        owner_id = "user-456"

        artifact_service.collect_artifact_from_bytes(
            run_id="run-1",
            owner_id=owner_id,
            content=b"test content",
            name="file.txt",
            user_quotas=user_quotas,
        )

        # Recalculate
        usage = artifact_service.recalculate_user_usage(owner_id)

        assert usage.artifact_count == 1
        assert usage.total_bytes == len(b"test content")


class TestCleanupExpiredArtifacts:
    """Tests for expired artifact cleanup."""

    def test_cleanup_removes_expired(
        self,
        artifact_service: ArtifactCollectorService,
        user_quotas: UserQuotas,
    ):
        """Test that cleanup removes expired artifacts."""
        # Create artifact with very short retention
        artifact = artifact_service.collect_artifact_from_bytes(
            run_id="run-123",
            owner_id="user-456",
            content=b"expiring content",
            name="temp.txt",
            user_quotas=user_quotas,
            retention_days=0,  # Never expires
        )

        # Manually set expires_at to the past
        artifact.expires_at = datetime.utcnow() - timedelta(days=1)
        artifact_service.artifact_store.update(artifact.id, artifact)

        # Run cleanup
        deleted = artifact_service.cleanup_expired_artifacts()

        assert deleted == 1
        assert artifact_service.get_artifact(artifact.id) is None

    def test_cleanup_keeps_non_expired(
        self,
        artifact_service: ArtifactCollectorService,
        user_quotas: UserQuotas,
    ):
        """Test that cleanup keeps non-expired artifacts."""
        artifact = artifact_service.collect_artifact_from_bytes(
            run_id="run-123",
            owner_id="user-456",
            content=b"valid content",
            name="valid.txt",
            user_quotas=user_quotas,
            retention_days=30,
        )

        # Run cleanup
        deleted = artifact_service.cleanup_expired_artifacts()

        assert deleted == 0
        assert artifact_service.get_artifact(artifact.id) is not None

    def test_cleanup_keeps_permanent(
        self,
        artifact_service: ArtifactCollectorService,
        user_quotas: UserQuotas,
    ):
        """Test that cleanup keeps artifacts with no expiration."""
        artifact = artifact_service.collect_artifact_from_bytes(
            run_id="run-123",
            owner_id="user-456",
            content=b"permanent content",
            name="permanent.txt",
            user_quotas=user_quotas,
            retention_days=0,  # Never expires
        )

        # Run cleanup
        deleted = artifact_service.cleanup_expired_artifacts()

        assert deleted == 0
        assert artifact_service.get_artifact(artifact.id) is not None
