"""Tests for notification service with WebSocket push support."""

from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from mellea_api.core.config import Settings
from mellea_api.models.notification import (
    Notification,
    NotificationPriority,
    NotificationType,
)
from mellea_api.services.notification import ConnectionManager, NotificationService


@pytest.fixture
def temp_settings():
    """Create settings with a temporary data directory."""
    with TemporaryDirectory() as temp_dir:
        settings = Settings(data_dir=Path(temp_dir))
        settings.ensure_data_dirs()
        yield settings


@pytest.fixture
def notification_service(temp_settings):
    """Create a notification service with temporary storage."""
    return NotificationService(settings=temp_settings)


class TestNotification:
    """Tests for Notification model."""

    def test_create_notification(self):
        """Test creating a notification with required fields."""
        notification = Notification(
            userId="user-123",
            type=NotificationType.RUN_COMPLETED,
            title="Run Completed",
            message="Your program finished successfully.",
        )

        assert notification.user_id == "user-123"
        assert notification.type == NotificationType.RUN_COMPLETED
        assert notification.title == "Run Completed"
        assert notification.message == "Your program finished successfully."
        assert notification.id is not None
        assert notification.created_at is not None
        assert notification.is_read is False
        assert notification.priority == NotificationPriority.NORMAL

    def test_create_notification_with_resource(self):
        """Test creating a notification with resource context."""
        notification = Notification(
            userId="user-123",
            type=NotificationType.RUN_FAILED,
            title="Run Failed",
            message="Your program encountered an error.",
            resourceType="run",
            resourceId="run-456",
            actionUrl="/runs/run-456",
            priority=NotificationPriority.HIGH,
        )

        assert notification.resource_type == "run"
        assert notification.resource_id == "run-456"
        assert notification.action_url == "/runs/run-456"
        assert notification.priority == NotificationPriority.HIGH


class TestNotificationService:
    """Tests for NotificationService."""

    @pytest.mark.asyncio
    async def test_create_notification(self, notification_service):
        """Test creating a notification."""
        notification = await notification_service.create_notification(
            user_id="user-123",
            type=NotificationType.RUN_COMPLETED,
            title="Run Completed",
            message="Your program finished successfully.",
            push=False,  # Don't try to push (no WebSocket)
        )

        assert notification.user_id == "user-123"
        assert notification.type == NotificationType.RUN_COMPLETED
        assert notification.title == "Run Completed"
        assert notification.is_read is False

    @pytest.mark.asyncio
    async def test_create_notification_with_metadata(self, notification_service):
        """Test creating a notification with metadata."""
        notification = await notification_service.create_notification(
            user_id="user-123",
            type=NotificationType.ASSET_SHARED,
            title="Asset Shared",
            message="Someone shared an asset with you.",
            resource_type="program",
            resource_id="prog-456",
            metadata={"sharer": "alice@example.com"},
            push=False,
        )

        assert notification.metadata == {"sharer": "alice@example.com"}
        assert notification.resource_type == "program"
        assert notification.resource_id == "prog-456"

    @pytest.mark.asyncio
    async def test_get_notifications(self, notification_service):
        """Test retrieving notifications for a user."""
        # Create notifications for two users
        await notification_service.create_notification(
            "user-1", NotificationType.RUN_COMPLETED,
            "Run 1 Complete", "Message 1", push=False
        )
        await notification_service.create_notification(
            "user-1", NotificationType.RUN_FAILED,
            "Run 2 Failed", "Message 2", push=False
        )
        await notification_service.create_notification(
            "user-2", NotificationType.RUN_COMPLETED,
            "Run 3 Complete", "Message 3", push=False
        )

        notifications, total, unread = notification_service.get_notifications("user-1")

        assert len(notifications) == 2
        assert total == 2
        assert unread == 2
        assert all(n.user_id == "user-1" for n in notifications)

    @pytest.mark.asyncio
    async def test_get_notifications_unread_only(self, notification_service):
        """Test filtering for unread notifications."""
        n1 = await notification_service.create_notification(
            "user-1", NotificationType.RUN_COMPLETED,
            "Run 1", "Message 1", push=False
        )
        await notification_service.create_notification(
            "user-1", NotificationType.RUN_COMPLETED,
            "Run 2", "Message 2", push=False
        )

        # Mark one as read
        notification_service.mark_as_read(n1.id, "user-1")

        notifications, total, unread = notification_service.get_notifications(
            "user-1", unread_only=True
        )

        assert len(notifications) == 1
        assert unread == 1

    @pytest.mark.asyncio
    async def test_get_notifications_filter_by_type(self, notification_service):
        """Test filtering notifications by type."""
        await notification_service.create_notification(
            "user-1", NotificationType.RUN_COMPLETED,
            "Run Complete", "Message", push=False
        )
        await notification_service.create_notification(
            "user-1", NotificationType.RUN_FAILED,
            "Run Failed", "Message", push=False
        )
        await notification_service.create_notification(
            "user-1", NotificationType.ASSET_SHARED,
            "Asset Shared", "Message", push=False
        )

        notifications, total, _ = notification_service.get_notifications(
            "user-1", type=NotificationType.RUN_FAILED
        )

        assert len(notifications) == 1
        assert notifications[0].type == NotificationType.RUN_FAILED

    @pytest.mark.asyncio
    async def test_get_notifications_sorted_by_date(self, notification_service):
        """Test notifications are sorted newest first."""
        await notification_service.create_notification(
            "user-1", NotificationType.RUN_COMPLETED,
            "First", "Message 1", push=False
        )
        await notification_service.create_notification(
            "user-1", NotificationType.RUN_COMPLETED,
            "Second", "Message 2", push=False
        )
        await notification_service.create_notification(
            "user-1", NotificationType.RUN_COMPLETED,
            "Third", "Message 3", push=False
        )

        notifications, _, _ = notification_service.get_notifications("user-1")

        # Newest first
        for i in range(len(notifications) - 1):
            assert notifications[i].created_at >= notifications[i + 1].created_at

    @pytest.mark.asyncio
    async def test_mark_as_read(self, notification_service):
        """Test marking a notification as read."""
        notification = await notification_service.create_notification(
            "user-1", NotificationType.RUN_COMPLETED,
            "Run Complete", "Message", push=False
        )

        assert notification.is_read is False
        assert notification.read_at is None

        updated = notification_service.mark_as_read(notification.id, "user-1")

        assert updated is not None
        assert updated.is_read is True
        assert updated.read_at is not None

    @pytest.mark.asyncio
    async def test_mark_as_read_wrong_user(self, notification_service):
        """Test marking another user's notification as read fails."""
        notification = await notification_service.create_notification(
            "user-1", NotificationType.RUN_COMPLETED,
            "Run Complete", "Message", push=False
        )

        result = notification_service.mark_as_read(notification.id, "user-2")

        assert result is None

    @pytest.mark.asyncio
    async def test_mark_all_as_read(self, notification_service):
        """Test marking all notifications as read."""
        await notification_service.create_notification(
            "user-1", NotificationType.RUN_COMPLETED,
            "Run 1", "Message", push=False
        )
        await notification_service.create_notification(
            "user-1", NotificationType.RUN_COMPLETED,
            "Run 2", "Message", push=False
        )
        await notification_service.create_notification(
            "user-2", NotificationType.RUN_COMPLETED,
            "Run 3", "Message", push=False
        )

        count = notification_service.mark_all_as_read("user-1")

        assert count == 2

        # Verify user-1's notifications are read
        notifications, _, unread = notification_service.get_notifications("user-1")
        assert unread == 0
        assert all(n.is_read for n in notifications)

        # Verify user-2's notification is still unread
        notifications, _, unread = notification_service.get_notifications("user-2")
        assert unread == 1

    @pytest.mark.asyncio
    async def test_delete_notification(self, notification_service):
        """Test deleting a notification."""
        notification = await notification_service.create_notification(
            "user-1", NotificationType.RUN_COMPLETED,
            "Run Complete", "Message", push=False
        )

        result = notification_service.delete_notification(notification.id, "user-1")

        assert result is True
        assert notification_service.store.get_by_id(notification.id) is None

    @pytest.mark.asyncio
    async def test_delete_notification_wrong_user(self, notification_service):
        """Test deleting another user's notification fails."""
        notification = await notification_service.create_notification(
            "user-1", NotificationType.RUN_COMPLETED,
            "Run Complete", "Message", push=False
        )

        result = notification_service.delete_notification(notification.id, "user-2")

        assert result is False
        assert notification_service.store.get_by_id(notification.id) is not None

    @pytest.mark.asyncio
    async def test_pagination(self, notification_service):
        """Test pagination of notifications."""
        for i in range(15):
            await notification_service.create_notification(
                "user-1", NotificationType.RUN_COMPLETED,
                f"Run {i}", f"Message {i}", push=False
            )

        # First page
        page1, total, _ = notification_service.get_notifications(
            "user-1", limit=5, offset=0
        )
        assert len(page1) == 5
        assert total == 15

        # Second page
        page2, total, _ = notification_service.get_notifications(
            "user-1", limit=5, offset=5
        )
        assert len(page2) == 5
        assert total == 15

        # No overlap
        page1_ids = {n.id for n in page1}
        page2_ids = {n.id for n in page2}
        assert len(page1_ids & page2_ids) == 0


class TestConnectionManager:
    """Tests for WebSocket ConnectionManager."""

    @pytest.mark.asyncio
    async def test_get_connected_users_empty(self):
        """Test getting connected users when none are connected."""
        manager = ConnectionManager()
        assert manager.get_connected_users() == []

    @pytest.mark.asyncio
    async def test_get_connection_count_empty(self):
        """Test connection count when empty."""
        manager = ConnectionManager()
        assert manager.get_connection_count() == 0
        assert manager.get_connection_count("user-1") == 0


class TestNotificationTypes:
    """Tests for different notification types."""

    @pytest.mark.asyncio
    async def test_run_notifications(self, notification_service):
        """Test run lifecycle notification types."""
        types = [
            NotificationType.RUN_STARTED,
            NotificationType.RUN_COMPLETED,
            NotificationType.RUN_FAILED,
        ]

        for type in types:
            notification = await notification_service.create_notification(
                "user-1", type, "Title", "Message", push=False
            )
            assert notification.type == type

    @pytest.mark.asyncio
    async def test_sharing_notifications(self, notification_service):
        """Test sharing notification types."""
        types = [
            NotificationType.ASSET_SHARED,
            NotificationType.ASSET_ACCESS_REVOKED,
        ]

        for type in types:
            notification = await notification_service.create_notification(
                "user-1", type, "Title", "Message", push=False
            )
            assert notification.type == type

    @pytest.mark.asyncio
    async def test_system_notifications(self, notification_service):
        """Test system notification types."""
        types = [
            NotificationType.SYSTEM_ANNOUNCEMENT,
            NotificationType.SYSTEM_MAINTENANCE,
        ]

        for type in types:
            notification = await notification_service.create_notification(
                "user-1", type, "Title", "Message",
                priority=NotificationPriority.HIGH,
                push=False
            )
            assert notification.type == type
            assert notification.priority == NotificationPriority.HIGH

    @pytest.mark.asyncio
    async def test_collaboration_notifications(self, notification_service):
        """Test collaboration notification types."""
        notification = await notification_service.create_notification(
            "user-1", NotificationType.MENTION,
            "You were mentioned", "Alice mentioned you in a comment",
            resource_type="comment",
            resource_id="comment-123",
            push=False
        )

        assert notification.type == NotificationType.MENTION
        assert notification.resource_type == "comment"


class TestNotificationPriority:
    """Tests for notification priority levels."""

    @pytest.mark.asyncio
    async def test_default_priority(self, notification_service):
        """Test default priority is NORMAL."""
        notification = await notification_service.create_notification(
            "user-1", NotificationType.RUN_COMPLETED,
            "Title", "Message", push=False
        )

        assert notification.priority == NotificationPriority.NORMAL

    @pytest.mark.asyncio
    async def test_urgent_priority(self, notification_service):
        """Test urgent priority notification."""
        notification = await notification_service.create_notification(
            "user-1", NotificationType.RUN_FAILED,
            "Critical Error", "Your run failed due to a critical error",
            priority=NotificationPriority.URGENT,
            push=False
        )

        assert notification.priority == NotificationPriority.URGENT

    @pytest.mark.asyncio
    async def test_low_priority(self, notification_service):
        """Test low priority notification."""
        notification = await notification_service.create_notification(
            "user-1", NotificationType.SYSTEM_ANNOUNCEMENT,
            "Minor Update", "A minor update was applied",
            priority=NotificationPriority.LOW,
            push=False
        )

        assert notification.priority == NotificationPriority.LOW
