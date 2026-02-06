"""Notification Service with WebSocket push support."""

import asyncio
import logging
from datetime import datetime
from typing import Any

from fastapi import WebSocket

from mellea_api.core.config import Settings, get_settings
from mellea_api.core.store import JsonStore
from mellea_api.models.notification import (
    Notification,
    NotificationPreferences,
    NotificationPriority,
    NotificationType,
    NotificationTypePreference,
)

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket connections for real-time notifications.

    Maintains a mapping of user IDs to their active WebSocket connections,
    allowing notifications to be pushed to specific users.
    """

    def __init__(self) -> None:
        """Initialize the connection manager."""
        # Map of user_id -> list of active WebSocket connections
        self._connections: dict[str, list[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, user_id: str) -> None:
        """Register a new WebSocket connection for a user.

        Args:
            websocket: The WebSocket connection to register
            user_id: The user ID associated with this connection
        """
        await websocket.accept()
        async with self._lock:
            if user_id not in self._connections:
                self._connections[user_id] = []
            self._connections[user_id].append(websocket)
            logger.info(f"WebSocket connected for user {user_id}")

    async def disconnect(self, websocket: WebSocket, user_id: str) -> None:
        """Remove a WebSocket connection for a user.

        Args:
            websocket: The WebSocket connection to remove
            user_id: The user ID associated with this connection
        """
        async with self._lock:
            if user_id in self._connections:
                if websocket in self._connections[user_id]:
                    self._connections[user_id].remove(websocket)
                if not self._connections[user_id]:
                    del self._connections[user_id]
                logger.info(f"WebSocket disconnected for user {user_id}")

    async def send_to_user(self, user_id: str, message: dict[str, Any]) -> int:
        """Send a message to all connections for a specific user.

        Args:
            user_id: The user ID to send to
            message: The message to send (will be JSON serialized)

        Returns:
            Number of connections the message was sent to
        """
        sent_count = 0
        async with self._lock:
            connections = self._connections.get(user_id, [])
            dead_connections = []

            for websocket in connections:
                try:
                    await websocket.send_json(message)
                    sent_count += 1
                except Exception as e:
                    logger.warning(f"Failed to send to WebSocket: {e}")
                    dead_connections.append(websocket)

            # Clean up dead connections
            for dead in dead_connections:
                if dead in self._connections.get(user_id, []):
                    self._connections[user_id].remove(dead)

        return sent_count

    async def broadcast(self, message: dict[str, Any]) -> int:
        """Broadcast a message to all connected users.

        Args:
            message: The message to broadcast

        Returns:
            Number of connections the message was sent to
        """
        sent_count = 0
        async with self._lock:
            for user_id in list(self._connections.keys()):
                for websocket in self._connections.get(user_id, []):
                    try:
                        await websocket.send_json(message)
                        sent_count += 1
                    except Exception as e:
                        logger.warning(f"Failed to broadcast to WebSocket: {e}")
        return sent_count

    def get_connected_users(self) -> list[str]:
        """Get list of currently connected user IDs."""
        return list(self._connections.keys())

    def get_connection_count(self, user_id: str | None = None) -> int:
        """Get the number of active connections.

        Args:
            user_id: If provided, count only connections for this user

        Returns:
            Number of active connections
        """
        if user_id:
            return len(self._connections.get(user_id, []))
        return sum(len(conns) for conns in self._connections.values())


class NotificationService:
    """Service for managing user notifications with real-time push.

    Provides methods to create, query, and push notifications to users.
    Supports WebSocket connections for real-time delivery.

    Example:
        ```python
        service = get_notification_service()

        # Create and push a notification
        notification = await service.create_notification(
            user_id="user-123",
            type=NotificationType.RUN_COMPLETED,
            title="Run Completed",
            message="Your program run has finished successfully.",
            resource_type="run",
            resource_id="run-456",
        )

        # Get notifications for a user
        notifications, total, unread = service.get_notifications(
            user_id="user-123",
            unread_only=True,
        )
        ```
    """

    def __init__(self, settings: Settings | None = None) -> None:
        """Initialize the NotificationService.

        Args:
            settings: Application settings (uses default if not provided)
        """
        self.settings = settings or get_settings()
        self._store: JsonStore[Notification] | None = None
        self._preferences_store: JsonStore[NotificationPreferences] | None = None
        self.connection_manager = ConnectionManager()

    @property
    def store(self) -> JsonStore[Notification]:
        """Get the notification store, initializing if needed."""
        if self._store is None:
            file_path = self.settings.data_dir / "metadata" / "notifications.json"
            self._store = JsonStore[Notification](
                file_path=file_path,
                collection_key="notifications",
                model_class=Notification,
            )
        return self._store

    @property
    def preferences_store(self) -> JsonStore[NotificationPreferences]:
        """Get the preferences store, initializing if needed."""
        if self._preferences_store is None:
            file_path = self.settings.data_dir / "metadata" / "notification_preferences.json"
            self._preferences_store = JsonStore[NotificationPreferences](
                file_path=file_path,
                collection_key="preferences",
                model_class=NotificationPreferences,
            )
        return self._preferences_store

    async def create_notification(
        self,
        user_id: str,
        type: NotificationType,
        title: str,
        message: str,
        priority: NotificationPriority = NotificationPriority.NORMAL,
        resource_type: str | None = None,
        resource_id: str | None = None,
        action_url: str | None = None,
        metadata: dict[str, str] | None = None,
        push: bool = True,
    ) -> Notification:
        """Create a notification and optionally push it to connected clients.

        Args:
            user_id: User ID to send notification to
            type: Type of notification
            title: Notification title
            message: Notification body
            priority: Priority level
            resource_type: Related resource type
            resource_id: Related resource ID
            action_url: URL for action
            metadata: Additional context
            push: Whether to push via WebSocket (default True)

        Returns:
            The created notification
        """
        notification = Notification(
            user_id=user_id,
            type=type,
            title=title,
            message=message,
            priority=priority,
            resource_type=resource_type,
            resource_id=resource_id,
            action_url=action_url,
            metadata=metadata,
        )

        # Store the notification
        created = self.store.create(notification)
        logger.debug(f"Created notification {created.id} for user {user_id}: {title}")

        # Push to connected clients
        if push:
            await self.push_notification(created)

        return created

    async def push_notification(self, notification: Notification) -> int:
        """Push a notification to connected WebSocket clients.

        Args:
            notification: The notification to push

        Returns:
            Number of clients the notification was pushed to
        """
        message = {
            "type": "notification",
            "payload": notification.model_dump(mode="json", by_alias=True),
        }
        sent_count = await self.connection_manager.send_to_user(
            notification.user_id, message
        )
        if sent_count > 0:
            logger.debug(
                f"Pushed notification {notification.id} to {sent_count} connection(s)"
            )
        return sent_count

    def get_notifications(
        self,
        user_id: str,
        unread_only: bool = False,
        type: NotificationType | None = None,
        since: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Notification], int, int]:
        """Get notifications for a user with filtering.

        Args:
            user_id: User ID to get notifications for
            unread_only: Only return unread notifications
            type: Filter by notification type
            since: Only return notifications after this time
            limit: Maximum notifications to return
            offset: Number of notifications to skip

        Returns:
            Tuple of (notifications, total_count, unread_count)
        """
        # Get all notifications for the user
        all_notifications = self.store.find(lambda n: n.user_id == user_id)

        # Calculate unread count before filtering
        unread_count = sum(1 for n in all_notifications if not n.is_read)

        # Apply filters
        notifications = all_notifications

        if unread_only:
            notifications = [n for n in notifications if not n.is_read]

        if type:
            notifications = [n for n in notifications if n.type == type]

        if since:
            notifications = [n for n in notifications if n.created_at >= since]

        # Sort by created_at descending (newest first)
        notifications.sort(key=lambda n: n.created_at, reverse=True)

        # Get total before pagination
        total = len(notifications)

        # Apply pagination
        notifications = notifications[offset : offset + limit]

        return notifications, total, unread_count

    def mark_as_read(self, notification_id: str, user_id: str) -> Notification | None:
        """Mark a notification as read.

        Args:
            notification_id: ID of the notification to mark as read
            user_id: User ID (for ownership verification)

        Returns:
            The updated notification if found and owned by user, None otherwise
        """
        notification = self.store.get_by_id(notification_id)
        if notification is None or notification.user_id != user_id:
            return None

        if not notification.is_read:
            notification.is_read = True
            notification.read_at = datetime.utcnow()
            self.store.update(notification_id, notification)
            logger.debug(f"Marked notification {notification_id} as read")

        return notification

    def mark_all_as_read(self, user_id: str) -> int:
        """Mark all notifications for a user as read.

        Args:
            user_id: User ID

        Returns:
            Number of notifications marked as read
        """
        notifications = self.store.find(
            lambda n: n.user_id == user_id and not n.is_read
        )
        count = 0
        now = datetime.utcnow()

        for notification in notifications:
            notification.is_read = True
            notification.read_at = now
            self.store.update(notification.id, notification)
            count += 1

        if count > 0:
            logger.info(f"Marked {count} notifications as read for user {user_id}")

        return count

    def delete_notification(self, notification_id: str, user_id: str) -> bool:
        """Delete a notification.

        Args:
            notification_id: ID of the notification to delete
            user_id: User ID (for ownership verification)

        Returns:
            True if deleted, False if not found or not owned by user
        """
        notification = self.store.get_by_id(notification_id)
        if notification is None or notification.user_id != user_id:
            return False

        return self.store.delete(notification_id)

    def delete_old_notifications(self, user_id: str, days: int = 30) -> int:
        """Delete notifications older than a specified number of days.

        Args:
            user_id: User ID
            days: Delete notifications older than this many days

        Returns:
            Number of notifications deleted
        """
        from datetime import timedelta

        cutoff = datetime.utcnow() - timedelta(days=days)
        notifications = self.store.find(
            lambda n: n.user_id == user_id and n.created_at < cutoff
        )

        count = 0
        for notification in notifications:
            if self.store.delete(notification.id):
                count += 1

        if count > 0:
            logger.info(
                f"Deleted {count} old notifications for user {user_id} (older than {days} days)"
            )

        return count

    def get_preferences(self, user_id: str) -> NotificationPreferences:
        """Get notification preferences for a user.

        Creates default preferences if none exist.

        Args:
            user_id: User ID

        Returns:
            User's notification preferences
        """
        prefs = self.preferences_store.get_by_id(user_id)
        if prefs is None:
            # Create default preferences with all types enabled
            prefs = NotificationPreferences(user_id=user_id)
            # Initialize with default preferences for all notification types
            for ntype in NotificationType:
                prefs.type_preferences[ntype.value] = NotificationTypePreference()
            self.preferences_store.create(prefs)
            logger.debug(f"Created default preferences for user {user_id}")
        return prefs

    def update_preferences(
        self,
        user_id: str,
        global_enabled: bool | None = None,
        quiet_hours_start: str | None = None,
        quiet_hours_end: str | None = None,
        type_preferences: dict[str, NotificationTypePreference] | None = None,
    ) -> NotificationPreferences:
        """Update notification preferences for a user.

        Args:
            user_id: User ID
            global_enabled: Master switch for all notifications
            quiet_hours_start: Start of quiet hours
            quiet_hours_end: End of quiet hours
            type_preferences: Per-type settings to update (merged with existing)

        Returns:
            Updated preferences
        """
        prefs = self.get_preferences(user_id)

        if global_enabled is not None:
            prefs.global_enabled = global_enabled

        if quiet_hours_start is not None:
            prefs.quiet_hours_start = quiet_hours_start if quiet_hours_start else None

        if quiet_hours_end is not None:
            prefs.quiet_hours_end = quiet_hours_end if quiet_hours_end else None

        if type_preferences is not None:
            # Merge with existing preferences
            for ntype, pref in type_preferences.items():
                prefs.type_preferences[ntype] = pref

        self.preferences_store.update(user_id, prefs)
        logger.info(f"Updated notification preferences for user {user_id}")
        return prefs


# Global service instance
_notification_service: NotificationService | None = None


def get_notification_service() -> NotificationService:
    """Get the global NotificationService instance."""
    global _notification_service
    if _notification_service is None:
        _notification_service = NotificationService()
    return _notification_service


def reset_notification_service() -> None:
    """Reset the global NotificationService instance (for testing)."""
    global _notification_service
    _notification_service = None
