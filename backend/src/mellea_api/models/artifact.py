"""Artifact model for storing run outputs and files."""

from datetime import datetime
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


def generate_uuid() -> str:
    """Generate a new UUID string."""
    return str(uuid4())


class ArtifactType(str, Enum):
    """Type of artifact."""

    FILE = "file"
    DIRECTORY = "directory"
    LOG = "log"
    OUTPUT = "output"


class Artifact(BaseModel):
    """Represents a stored artifact from a run.

    Artifacts are files or data generated during program execution that
    are persisted for later retrieval. They can include logs, output files,
    generated data, etc.

    Attributes:
        id: Unique identifier for this artifact
        run_id: ID of the run that produced this artifact
        owner_id: ID of the user who owns this artifact
        name: Human-readable name for the artifact
        artifact_type: Type of artifact (file, directory, log, output)
        size_bytes: Size of the artifact in bytes
        storage_path: Relative path within the artifacts directory
        mime_type: MIME type of the artifact content
        checksum: SHA-256 checksum of the artifact
        created_at: When the artifact was created
        expires_at: When the artifact will be automatically deleted (None = never)
        tags: Optional tags for categorization
        metadata: Optional additional metadata
    """

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(default_factory=generate_uuid)
    run_id: str = Field(validation_alias="runId", serialization_alias="runId")
    owner_id: str = Field(validation_alias="ownerId", serialization_alias="ownerId")
    name: str
    artifact_type: ArtifactType = Field(
        default=ArtifactType.FILE,
        validation_alias="artifactType",
        serialization_alias="artifactType",
    )
    size_bytes: int = Field(
        default=0, validation_alias="sizeBytes", serialization_alias="sizeBytes"
    )
    storage_path: str = Field(
        validation_alias="storagePath", serialization_alias="storagePath"
    )
    mime_type: str | None = Field(
        default=None, validation_alias="mimeType", serialization_alias="mimeType"
    )
    checksum: str | None = None
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        validation_alias="createdAt",
        serialization_alias="createdAt",
    )
    expires_at: datetime | None = Field(
        default=None, validation_alias="expiresAt", serialization_alias="expiresAt"
    )
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, str] = Field(default_factory=dict)


class ArtifactUsage(BaseModel):
    """Tracks storage usage for a user.

    Attributes:
        id: Same as user_id, used for JsonStore lookup
        user_id: ID of the user
        total_bytes: Total bytes used by artifacts
        artifact_count: Number of artifacts stored
        last_updated: When this usage record was last updated
    """

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(default="")  # Set to user_id for JsonStore compatibility
    user_id: str = Field(validation_alias="userId", serialization_alias="userId")
    total_bytes: int = Field(
        default=0, validation_alias="totalBytes", serialization_alias="totalBytes"
    )
    artifact_count: int = Field(
        default=0, validation_alias="artifactCount", serialization_alias="artifactCount"
    )
    last_updated: datetime = Field(
        default_factory=datetime.utcnow,
        validation_alias="lastUpdated",
        serialization_alias="lastUpdated",
    )

    def __init__(self, **data):
        super().__init__(**data)
        # Ensure id matches user_id for JsonStore compatibility
        if not self.id and self.user_id:
            object.__setattr__(self, "id", self.user_id)
