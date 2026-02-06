"""Audit event model and schemas for action logging."""

from datetime import datetime
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from mellea_api.models.user import UserRole


class AuditAction(str, Enum):
    """Type of auditable action."""

    # Asset lifecycle
    ASSET_CREATED = "asset.created"
    ASSET_UPDATED = "asset.updated"
    ASSET_DELETED = "asset.deleted"
    ASSET_VIEWED = "asset.viewed"

    # Sharing
    ASSET_SHARED = "asset.shared"
    ASSET_UNSHARED = "asset.unshared"
    ASSET_MADE_PUBLIC = "asset.made_public"
    ASSET_MADE_PRIVATE = "asset.made_private"

    # Execution
    RUN_STARTED = "run.started"
    RUN_COMPLETED = "run.completed"
    RUN_FAILED = "run.failed"
    RUN_CANCELLED = "run.cancelled"

    # Authentication
    AUTH_LOGIN = "auth.login"
    AUTH_LOGOUT = "auth.logout"
    AUTH_LOGIN_FAILED = "auth.login_failed"

    # Admin actions
    USER_ROLE_CHANGED = "user.role_changed"
    USER_QUOTA_CHANGED = "user.quota_changed"
    USER_SUSPENDED = "user.suspended"
    USER_REACTIVATED = "user.reactivated"


class AuditResourceType(str, Enum):
    """Type of resource being audited."""

    PROGRAM = "program"
    MODEL = "model"
    COMPOSITION = "composition"
    USER = "user"
    RUN = "run"
    CREDENTIAL = "credential"


class AuditEvent(BaseModel):
    """An audit event for action tracking.

    Tracks who performed an action, what resource was affected, and when.

    Attributes:
        id: Unique identifier for this audit event
        timestamp: When the action occurred
        user_id: User ID who performed the action
        user_email: Email of the user who performed the action
        user_role: Role of the user at the time of the action
        action: Type of action performed
        resource_type: Type of resource affected
        resource_id: ID of the affected resource
        resource_name: Human-readable name of the resource (optional)
        details: Additional context about the action
        ip_address: IP address of the actor (optional)
        user_agent: Browser/client user agent (optional)
        success: Whether the action succeeded
        error_message: Error message if the action failed (optional)
    """

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    # Actor information
    user_id: str = Field(validation_alias="userId", serialization_alias="userId")
    user_email: str = Field(validation_alias="userEmail", serialization_alias="userEmail")
    user_role: UserRole = Field(validation_alias="userRole", serialization_alias="userRole")

    # Action information
    action: AuditAction
    resource_type: AuditResourceType = Field(
        validation_alias="resourceType", serialization_alias="resourceType"
    )
    resource_id: str = Field(validation_alias="resourceId", serialization_alias="resourceId")
    resource_name: str | None = Field(
        default=None, validation_alias="resourceName", serialization_alias="resourceName"
    )

    # Context
    details: dict[str, str] | None = Field(default=None)
    ip_address: str | None = Field(
        default=None, validation_alias="ipAddress", serialization_alias="ipAddress"
    )
    user_agent: str | None = Field(
        default=None, validation_alias="userAgent", serialization_alias="userAgent"
    )

    # Outcome
    success: bool = True
    error_message: str | None = Field(
        default=None, validation_alias="errorMessage", serialization_alias="errorMessage"
    )


class AuditEventListResponse(BaseModel):
    """Response for listing audit events with pagination."""

    model_config = ConfigDict(populate_by_name=True)

    events: list[AuditEvent]
    total: int
    limit: int
    offset: int
