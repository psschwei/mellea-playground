"""Environment model for managing runnable container environments."""

from datetime import datetime
from uuid import uuid4

from pydantic import BaseModel, Field

from mellea_api.models.common import EnvironmentStatus


def generate_uuid() -> str:
    """Generate a new UUID string."""
    return str(uuid4())


class ResourceLimits(BaseModel):
    """Resource limits for environment containers.

    Defines CPU, memory, and timeout constraints for container execution.

    Example:
        ```python
        limits = ResourceLimits(
            cpu_cores=2.0,
            memory_mb=1024,
            timeout_seconds=600,
        )
        ```
    """

    cpu_cores: float = Field(default=1.0, alias="cpuCores")
    memory_mb: int = Field(default=512, alias="memoryMb")
    timeout_seconds: int = Field(default=300, alias="timeoutSeconds")

    class Config:
        populate_by_name = True


class Environment(BaseModel):
    """Represents a runnable environment for a program.

    An Environment tracks the lifecycle of a built container image that
    can be started, stopped, and managed. It maintains state machine
    semantics for lifecycle transitions.

    Example:
        ```python
        env = Environment(
            program_id="prog-123",
            image_tag="mellea-prog:abc123",
            status=EnvironmentStatus.READY,
        )
        ```

    Attributes:
        id: Unique identifier for the environment
        program_id: ID of the associated ProgramAsset
        image_tag: Docker image tag for this environment
        status: Current lifecycle status
        container_id: Docker container ID when running
        created_at: Timestamp when environment was created
        updated_at: Timestamp of last status update
        started_at: Timestamp when container was started
        stopped_at: Timestamp when container was stopped
        error_message: Error details if in FAILED status
        resource_limits: Resource constraints for the container
    """

    id: str = Field(default_factory=generate_uuid)
    program_id: str = Field(alias="programId")
    image_tag: str = Field(alias="imageTag")
    status: EnvironmentStatus = EnvironmentStatus.CREATING
    container_id: str | None = Field(default=None, alias="containerId")
    created_at: datetime = Field(default_factory=datetime.utcnow, alias="createdAt")
    updated_at: datetime = Field(default_factory=datetime.utcnow, alias="updatedAt")
    started_at: datetime | None = Field(default=None, alias="startedAt")
    stopped_at: datetime | None = Field(default=None, alias="stoppedAt")
    error_message: str | None = Field(default=None, alias="errorMessage")
    resource_limits: ResourceLimits | None = Field(default=None, alias="resourceLimits")

    class Config:
        populate_by_name = True
