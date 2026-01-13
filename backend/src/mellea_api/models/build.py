"""Build-related models for the EnvironmentBuilder service."""

from datetime import datetime
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field


def generate_uuid() -> str:
    """Generate a new UUID string."""
    return str(uuid4())


class BuildStage(str, Enum):
    """Stages of the image build process."""

    PREPARING = "preparing"
    CACHE_LOOKUP = "cache_lookup"
    BUILDING_DEPS = "building_deps"
    BUILDING_PROGRAM = "building_program"
    COMPLETE = "complete"
    FAILED = "failed"


class LayerCacheEntry(BaseModel):
    """A cached dependency layer image.

    Represents a reusable Docker image containing installed Python dependencies.
    Multiple ProgramAssets with identical dependencies can share this layer.
    """

    id: str = Field(default_factory=generate_uuid)
    cache_key: str
    image_tag: str
    python_version: str
    packages_hash: str
    package_count: int
    size_bytes: int | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow, alias="createdAt")
    last_used_at: datetime = Field(default_factory=datetime.utcnow, alias="lastUsedAt")
    use_count: int = 1

    class Config:
        populate_by_name = True


class BuildContext(BaseModel):
    """Context and state for a single image build operation.

    Tracks the progress of building a Docker image for a ProgramAsset,
    including cache hits/misses and timing information.
    """

    program_id: str
    cache_key: str | None = None
    cache_hit: bool = False
    dependency_image_tag: str | None = None
    final_image_tag: str | None = None
    stage: BuildStage = BuildStage.PREPARING
    stage_started_at: datetime = Field(default_factory=datetime.utcnow)
    error_message: str | None = None
    build_logs: list[str] = Field(default_factory=list)
    total_duration_seconds: float | None = None
    deps_build_duration_seconds: float | None = None
    program_build_duration_seconds: float | None = None


class BuildResult(BaseModel):
    """Result of a completed image build."""

    program_id: str
    success: bool
    image_tag: str | None = None
    cache_hit: bool = False
    error_message: str | None = None
    total_duration_seconds: float
    deps_build_duration_seconds: float | None = None
    program_build_duration_seconds: float | None = None
