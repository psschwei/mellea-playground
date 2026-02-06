"""Run access audit trail model."""

from datetime import datetime
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class RunAuditAction(str, Enum):
    """Type of auditable run access action."""

    VIEW = "view"  # Run was viewed
    CREATE = "create"  # Run was created
    DELETE = "delete"  # Run was deleted
    CANCEL = "cancel"  # Run was cancelled
    SHARE = "share"  # Run was shared with a user
    REVOKE = "revoke"  # User access was revoked
    VISIBILITY_CHANGE = "visibility_change"  # Visibility mode changed
    LOGS_VIEW = "logs_view"  # Logs were viewed/downloaded
    LOGS_STREAM = "logs_stream"  # Logs were streamed


class RunAuditEvent(BaseModel):
    """An audit event for run access tracking.

    Tracks who accessed a run, what action they performed, and when.

    Attributes:
        id: Unique identifier for this audit event
        run_id: ID of the run being accessed
        actor_id: User ID who performed the action
        action: Type of action performed
        timestamp: When the action occurred
        details: Additional context about the action (e.g., target user for share)
        ip_address: IP address of the actor (optional)
        user_agent: Browser/client user agent (optional)
    """

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(default_factory=lambda: str(uuid4()))
    run_id: str = Field(validation_alias="runId", serialization_alias="runId")
    actor_id: str = Field(validation_alias="actorId", serialization_alias="actorId")
    action: RunAuditAction
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    details: dict[str, str] | None = Field(default=None)
    ip_address: str | None = Field(
        default=None, validation_alias="ipAddress", serialization_alias="ipAddress"
    )
    user_agent: str | None = Field(
        default=None, validation_alias="userAgent", serialization_alias="userAgent"
    )


class RunAuditSummary(BaseModel):
    """Summary of audit events for a run.

    Attributes:
        run_id: ID of the run
        total_events: Total number of audit events
        unique_viewers: Number of unique users who viewed the run
        last_accessed: When the run was last accessed
        access_by_action: Count of events grouped by action type
    """

    model_config = ConfigDict(populate_by_name=True)

    run_id: str = Field(validation_alias="runId", serialization_alias="runId")
    total_events: int = Field(
        validation_alias="totalEvents", serialization_alias="totalEvents"
    )
    unique_viewers: int = Field(
        validation_alias="uniqueViewers", serialization_alias="uniqueViewers"
    )
    last_accessed: datetime | None = Field(
        default=None, validation_alias="lastAccessed", serialization_alias="lastAccessed"
    )
    access_by_action: dict[str, int] = Field(
        default_factory=dict,
        validation_alias="accessByAction",
        serialization_alias="accessByAction",
    )
