"""Retention policy model for automatic resource cleanup."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


def generate_uuid() -> str:
    """Generate a new UUID string."""
    return str(uuid4())


class ResourceType(str, Enum):
    """Type of resource that a retention policy can target."""

    ARTIFACT = "artifact"
    RUN = "run"
    ENVIRONMENT = "environment"
    LOG = "log"


class RetentionCondition(str, Enum):
    """Condition type for retention policy evaluation."""

    AGE_DAYS = "age_days"  # Resource older than N days
    STATUS = "status"  # Resource in specific status
    SIZE_BYTES = "size_bytes"  # Resource larger than N bytes
    UNUSED_DAYS = "unused_days"  # Not accessed in N days


class RetentionPolicy(BaseModel):
    """Represents a configurable retention policy for automatic resource cleanup.

    Retention policies define rules for automatically cleaning up resources based on
    various conditions like age, status, size, or access patterns.

    Attributes:
        id: Unique identifier for this policy
        name: Human-readable name for the policy
        description: Optional description of what the policy does
        resource_type: Type of resource this policy applies to
        condition: The condition type to evaluate
        threshold: Value for the condition (e.g., days for age_days, bytes for size_bytes)
        status_value: Status value when condition is STATUS (e.g., "failed", "succeeded")
        enabled: Whether the policy is active
        priority: Higher priority policies are evaluated first (default 0)
        user_id: Owner of the policy (None = system-wide policy)
        created_at: When the policy was created
        updated_at: When the policy was last updated
    """

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(default_factory=generate_uuid)
    name: str
    description: str | None = None
    resource_type: ResourceType = Field(
        validation_alias="resourceType", serialization_alias="resourceType"
    )
    condition: RetentionCondition
    threshold: int  # Value for condition (days, bytes, etc.)
    status_value: str | None = Field(
        default=None,
        validation_alias="statusValue",
        serialization_alias="statusValue",
        description="Status value when condition is STATUS",
    )
    enabled: bool = True
    priority: int = 0  # Higher = evaluated first
    user_id: str | None = Field(
        default=None,
        validation_alias="userId",
        serialization_alias="userId",
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        validation_alias="createdAt",
        serialization_alias="createdAt",
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        validation_alias="updatedAt",
        serialization_alias="updatedAt",
    )


@dataclass
class RetentionMetrics:
    """Metrics from a retention policy cleanup run.

    Tracks statistics about what resources were evaluated and cleaned up
    during a retention policy execution cycle.

    Attributes:
        timestamp: When the cleanup cycle ran
        policies_evaluated: Number of policies that were evaluated
        artifacts_deleted: Number of artifacts deleted
        runs_deleted: Number of runs deleted
        environments_cleaned: Number of environments cleaned up
        logs_deleted: Number of logs deleted
        storage_freed_bytes: Total bytes of storage freed
        errors: List of error messages from failed operations
        duration_seconds: How long the cleanup cycle took
    """

    timestamp: datetime = field(default_factory=datetime.utcnow)
    policies_evaluated: int = 0
    artifacts_deleted: int = 0
    runs_deleted: int = 0
    environments_cleaned: int = 0
    logs_deleted: int = 0
    storage_freed_bytes: int = 0
    errors: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0


class PolicyPreviewResult(BaseModel):
    """Result of previewing what a policy would delete.

    Attributes:
        policy_id: ID of the policy being previewed
        resource_type: Type of resources that would be affected
        matching_count: Number of resources that match the policy
        total_size_bytes: Total size in bytes of matching resources
        resource_ids: List of resource IDs that would be deleted
    """

    model_config = ConfigDict(populate_by_name=True)

    policy_id: str = Field(validation_alias="policyId", serialization_alias="policyId")
    resource_type: ResourceType = Field(
        validation_alias="resourceType", serialization_alias="resourceType"
    )
    matching_count: int = Field(
        validation_alias="matchingCount", serialization_alias="matchingCount"
    )
    total_size_bytes: int = Field(
        default=0,
        validation_alias="totalSizeBytes",
        serialization_alias="totalSizeBytes",
    )
    resource_ids: list[str] = Field(
        default_factory=list,
        validation_alias="resourceIds",
        serialization_alias="resourceIds",
    )
