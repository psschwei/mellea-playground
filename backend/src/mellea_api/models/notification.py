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


class NotificationTypePreference(BaseModel):
    """Preference settings for a specific notification type."""

    model_config = ConfigDict(populate_by_name=True)

    enabled: bool = True
    push_enabled: bool = Field(
        default=True, validation_alias="pushEnabled", serialization_alias="pushEnabled"
    )
    email_enabled: bool = Field(
        default=False, validation_alias="emailEnabled", serialization_alias="emailEnabled"
    )


class NotificationPreferences(BaseModel):
    """User notification preferences.

    Attributes:
        id: Alias for user_id (used as the store identifier)
        user_id: User ID these preferences belong to
        global_enabled: Master switch for all notifications
        quiet_hours_start: Start of quiet hours (HH:MM format, optional)
        quiet_hours_end: End of quiet hours (HH:MM format, optional)
        type_preferences: Per-type notification settings
    """

    model_config = ConfigDict(populate_by_name=True)

    # Use user_id as both the primary key and the id field for the store
    user_id: str = Field(validation_alias="userId", serialization_alias="userId")

    @property
    def id(self) -> str:
        """Return user_id as the id for store compatibility."""
        return self.user_id
    global_enabled: bool = Field(
        default=True, validation_alias="globalEnabled", serialization_alias="globalEnabled"
    )
    quiet_hours_start: str | None = Field(
        default=None,
        validation_alias="quietHoursStart",
        serialization_alias="quietHoursStart",
    )
    quiet_hours_end: str | None = Field(
        default=None,
        validation_alias="quietHoursEnd",
        serialization_alias="quietHoursEnd",
    )
    type_preferences: dict[str, NotificationTypePreference] = Field(
        default_factory=dict,
        validation_alias="typePreferences",
        serialization_alias="typePreferences",
    )

    def get_type_preference(self, notification_type: NotificationType) -> NotificationTypePreference:
        """Get preference for a notification type, returning defaults if not set."""
        return self.type_preferences.get(
            notification_type.value, NotificationTypePreference()
        )

    def should_send(self, notification_type: NotificationType) -> bool:
        """Check if a notification of this type should be sent."""
        if not self.global_enabled:
            return False
        pref = self.get_type_preference(notification_type)
        return pref.enabled

    def should_push(self, notification_type: NotificationType) -> bool:
        """Check if a push notification should be sent."""
        if not self.should_send(notification_type):
            return False
        pref = self.get_type_preference(notification_type)
        return pref.push_enabled

    def should_email(self, notification_type: NotificationType) -> bool:
        """Check if an email notification should be sent."""
        if not self.should_send(notification_type):
            return False
        pref = self.get_type_preference(notification_type)
        return pref.email_enabled


class NotificationPreferencesUpdateRequest(BaseModel):
    """Request to update notification preferences."""

    model_config = ConfigDict(populate_by_name=True)

    global_enabled: bool | None = Field(
        default=None, validation_alias="globalEnabled", serialization_alias="globalEnabled"
    )
    quiet_hours_start: str | None = Field(
        default=None,
        validation_alias="quietHoursStart",
        serialization_alias="quietHoursStart",
    )
    quiet_hours_end: str | None = Field(
        default=None,
        validation_alias="quietHoursEnd",
        serialization_alias="quietHoursEnd",
    )
    type_preferences: dict[str, NotificationTypePreference] | None = Field(
        default=None,
        validation_alias="typePreferences",
        serialization_alias="typePreferences",
    )
