"""Notification models and schemas for real-time push notifications."""

from datetime import datetime
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class NotificationType(str, Enum):
    """Type of notification."""

    # Run lifecycle
    RUN_STARTED = "run.started"
    RUN_COMPLETED = "run.completed"
    RUN_FAILED = "run.failed"

    # Sharing
    ASSET_SHARED = "asset.shared"
    ASSET_ACCESS_REVOKED = "asset.access_revoked"

    # System
    SYSTEM_ANNOUNCEMENT = "system.announcement"
    SYSTEM_MAINTENANCE = "system.maintenance"

    # Collaboration
    COMMENT_ADDED = "comment.added"
    MENTION = "mention"


class NotificationPriority(str, Enum):
    """Priority level for notifications."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class Notification(BaseModel):
    """A notification for a user.

    Attributes:
        id: Unique identifier for this notification
        user_id: User ID who should receive this notification
        type: Type of notification
        title: Short notification title
        message: Notification body text
        priority: Notification priority level
        resource_type: Type of resource this notification relates to (optional)
        resource_id: ID of related resource (optional)
        action_url: URL for the user to take action (optional)
        is_read: Whether the user has read this notification
        created_at: When the notification was created
        read_at: When the notification was read (optional)
        metadata: Additional context about the notification
    """

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(default_factory=lambda: str(uuid4()))
    user_id: str = Field(validation_alias="userId", serialization_alias="userId")
    type: NotificationType
    title: str
    message: str
    priority: NotificationPriority = NotificationPriority.NORMAL

    # Resource context
    resource_type: str | None = Field(
        default=None, validation_alias="resourceType", serialization_alias="resourceType"
    )
    resource_id: str | None = Field(
        default=None, validation_alias="resourceId", serialization_alias="resourceId"
    )
    action_url: str | None = Field(
        default=None, validation_alias="actionUrl", serialization_alias="actionUrl"
    )

    # State
    is_read: bool = Field(default=False, validation_alias="isRead", serialization_alias="isRead")
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        validation_alias="createdAt",
        serialization_alias="createdAt",
    )
    read_at: datetime | None = Field(
        default=None, validation_alias="readAt", serialization_alias="readAt"
    )

    # Additional context
    metadata: dict[str, str] | None = None


class NotificationListResponse(BaseModel):
    """Response for listing notifications with pagination."""

    model_config = ConfigDict(populate_by_name=True)

    notifications: list[Notification]
    total: int
    unread_count: int = Field(
        validation_alias="unreadCount", serialization_alias="unreadCount"
    )
    limit: int
    offset: int


class NotificationCreateRequest(BaseModel):
    """Request to create a notification."""

    model_config = ConfigDict(populate_by_name=True)

    user_id: str = Field(validation_alias="userId", serialization_alias="userId")
    type: NotificationType
    title: str
    message: str
    priority: NotificationPriority = NotificationPriority.NORMAL
    resource_type: str | None = Field(
        default=None, validation_alias="resourceType", serialization_alias="resourceType"
    )
    resource_id: str | None = Field(
        default=None, validation_alias="resourceId", serialization_alias="resourceId"
    )
    action_url: str | None = Field(
        default=None, validation_alias="actionUrl", serialization_alias="actionUrl"
    )
    metadata: dict[str, str] | None = None


class NotificationUpdateRequest(BaseModel):
    """Request to update a notification's read status."""

    model_config = ConfigDict(populate_by_name=True)

    is_read: bool = Field(validation_alias="isRead", serialization_alias="isRead")


class WebSocketMessage(BaseModel):
    """Message format for WebSocket communication."""

    model_config = ConfigDict(populate_by_name=True)

    type: str  # "notification", "ping", "pong", "subscribe", "unsubscribe"
    payload: dict[str, str] | None = None
