"""Tests for application-wide audit service."""

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from mellea_api.core.config import Settings
from mellea_api.models.audit import (
    AuditAction,
    AuditEvent,
    AuditResourceType,
)
from mellea_api.models.user import UserRole
from mellea_api.services.audit import AuditService


@pytest.fixture
def temp_settings():
    """Create settings with a temporary data directory."""
    with TemporaryDirectory() as temp_dir:
        settings = Settings(data_dir=Path(temp_dir))
        settings.ensure_data_dirs()
        yield settings


@pytest.fixture
def audit_service(temp_settings):
    """Create an audit service with temporary storage."""
    return AuditService(settings=temp_settings)


class TestAuditEvent:
    """Tests for AuditEvent model."""

    def test_create_event(self):
        """Test creating an audit event with required fields."""
        event = AuditEvent(
            userId="user-123",
            userEmail="test@example.com",
            userRole=UserRole.DEVELOPER,
            action=AuditAction.ASSET_CREATED,
            resourceType=AuditResourceType.PROGRAM,
            resourceId="prog-456",
        )

        assert event.user_id == "user-123"
        assert event.user_email == "test@example.com"
        assert event.user_role == UserRole.DEVELOPER
        assert event.action == AuditAction.ASSET_CREATED
        assert event.resource_type == AuditResourceType.PROGRAM
        assert event.resource_id == "prog-456"
        assert event.id is not None
        assert event.timestamp is not None
        assert event.success is True
        assert event.details is None

    def test_create_event_with_details(self):
        """Test creating an audit event with details."""
        event = AuditEvent(
            userId="user-123",
            userEmail="test@example.com",
            userRole=UserRole.DEVELOPER,
            action=AuditAction.ASSET_SHARED,
            resourceType=AuditResourceType.PROGRAM,
            resourceId="prog-456",
            details={"grantee": "user-789", "permission": "run"},
        )

        assert event.details == {"grantee": "user-789", "permission": "run"}

    def test_create_failed_event(self):
        """Test creating a failed audit event."""
        event = AuditEvent(
            userId="user-123",
            userEmail="test@example.com",
            userRole=UserRole.END_USER,
            action=AuditAction.AUTH_LOGIN_FAILED,
            resourceType=AuditResourceType.USER,
            resourceId="user-123",
            success=False,
            errorMessage="Invalid password",
        )

        assert event.success is False
        assert event.error_message == "Invalid password"


class TestAuditService:
    """Tests for AuditService."""

    def test_record_event(self, audit_service):
        """Test recording an audit event."""
        event = audit_service.record_event(
            user_id="user-123",
            user_email="test@example.com",
            user_role=UserRole.DEVELOPER,
            action=AuditAction.ASSET_CREATED,
            resource_type=AuditResourceType.PROGRAM,
            resource_id="prog-456",
            resource_name="My Program",
        )

        assert event.user_id == "user-123"
        assert event.action == AuditAction.ASSET_CREATED
        assert event.resource_name == "My Program"

    def test_record_event_with_context(self, audit_service):
        """Test recording an event with IP and user agent."""
        event = audit_service.record_event(
            user_id="user-123",
            user_email="test@example.com",
            user_role=UserRole.DEVELOPER,
            action=AuditAction.AUTH_LOGIN,
            resource_type=AuditResourceType.USER,
            resource_id="user-123",
            ip_address="192.168.1.1",
            user_agent="Mozilla/5.0",
        )

        assert event.ip_address == "192.168.1.1"
        assert event.user_agent == "Mozilla/5.0"

    def test_get_events_all(self, audit_service):
        """Test retrieving all events."""
        audit_service.record_event(
            "user-1", "user1@test.com", UserRole.DEVELOPER,
            AuditAction.ASSET_CREATED, AuditResourceType.PROGRAM, "prog-1"
        )
        audit_service.record_event(
            "user-2", "user2@test.com", UserRole.ADMIN,
            AuditAction.USER_ROLE_CHANGED, AuditResourceType.USER, "user-3"
        )

        events, total = audit_service.get_events()

        assert len(events) == 2
        assert total == 2

    def test_get_events_filter_by_user(self, audit_service):
        """Test filtering events by user."""
        audit_service.record_event(
            "user-1", "user1@test.com", UserRole.DEVELOPER,
            AuditAction.ASSET_CREATED, AuditResourceType.PROGRAM, "prog-1"
        )
        audit_service.record_event(
            "user-2", "user2@test.com", UserRole.DEVELOPER,
            AuditAction.ASSET_CREATED, AuditResourceType.PROGRAM, "prog-2"
        )
        audit_service.record_event(
            "user-1", "user1@test.com", UserRole.DEVELOPER,
            AuditAction.ASSET_UPDATED, AuditResourceType.PROGRAM, "prog-1"
        )

        events, total = audit_service.get_events(user_id="user-1")

        assert len(events) == 2
        assert total == 2
        assert all(e.user_id == "user-1" for e in events)

    def test_get_events_filter_by_resource(self, audit_service):
        """Test filtering events by resource."""
        audit_service.record_event(
            "user-1", "user1@test.com", UserRole.DEVELOPER,
            AuditAction.ASSET_CREATED, AuditResourceType.PROGRAM, "prog-1"
        )
        audit_service.record_event(
            "user-1", "user1@test.com", UserRole.DEVELOPER,
            AuditAction.ASSET_VIEWED, AuditResourceType.PROGRAM, "prog-1"
        )
        audit_service.record_event(
            "user-1", "user1@test.com", UserRole.DEVELOPER,
            AuditAction.ASSET_CREATED, AuditResourceType.MODEL, "model-1"
        )

        events, total = audit_service.get_events(
            resource_type=AuditResourceType.PROGRAM,
            resource_id="prog-1"
        )

        assert len(events) == 2
        assert total == 2
        assert all(e.resource_id == "prog-1" for e in events)

    def test_get_events_filter_by_action(self, audit_service):
        """Test filtering events by action type."""
        audit_service.record_event(
            "user-1", "user1@test.com", UserRole.DEVELOPER,
            AuditAction.ASSET_CREATED, AuditResourceType.PROGRAM, "prog-1"
        )
        audit_service.record_event(
            "user-1", "user1@test.com", UserRole.DEVELOPER,
            AuditAction.ASSET_UPDATED, AuditResourceType.PROGRAM, "prog-1"
        )
        audit_service.record_event(
            "user-1", "user1@test.com", UserRole.DEVELOPER,
            AuditAction.ASSET_CREATED, AuditResourceType.PROGRAM, "prog-2"
        )

        events, total = audit_service.get_events(action=AuditAction.ASSET_CREATED)

        assert len(events) == 2
        assert total == 2
        assert all(e.action == AuditAction.ASSET_CREATED for e in events)

    def test_get_events_filter_by_success(self, audit_service):
        """Test filtering events by success status."""
        audit_service.record_event(
            "user-1", "user1@test.com", UserRole.END_USER,
            AuditAction.AUTH_LOGIN, AuditResourceType.USER, "user-1",
            success=True
        )
        audit_service.record_event(
            "user-1", "user1@test.com", UserRole.END_USER,
            AuditAction.AUTH_LOGIN_FAILED, AuditResourceType.USER, "user-1",
            success=False, error_message="Invalid password"
        )

        failed_events, total = audit_service.get_events(success=False)

        assert len(failed_events) == 1
        assert total == 1
        assert failed_events[0].success is False

    def test_get_events_pagination(self, audit_service):
        """Test pagination of events."""
        for i in range(15):
            audit_service.record_event(
                f"user-{i}", f"user{i}@test.com", UserRole.DEVELOPER,
                AuditAction.ASSET_CREATED, AuditResourceType.PROGRAM, f"prog-{i}"
            )

        # First page
        events_page1, total = audit_service.get_events(limit=5, offset=0)
        assert len(events_page1) == 5
        assert total == 15

        # Second page
        events_page2, total = audit_service.get_events(limit=5, offset=5)
        assert len(events_page2) == 5
        assert total == 15

        # Ensure no overlap
        page1_ids = {e.id for e in events_page1}
        page2_ids = {e.id for e in events_page2}
        assert len(page1_ids & page2_ids) == 0

    def test_get_events_sorted_by_timestamp(self, audit_service):
        """Test events are sorted by timestamp (newest first)."""
        audit_service.record_event(
            "user-1", "user1@test.com", UserRole.DEVELOPER,
            AuditAction.ASSET_CREATED, AuditResourceType.PROGRAM, "prog-1"
        )
        audit_service.record_event(
            "user-1", "user1@test.com", UserRole.DEVELOPER,
            AuditAction.ASSET_UPDATED, AuditResourceType.PROGRAM, "prog-1"
        )
        audit_service.record_event(
            "user-1", "user1@test.com", UserRole.DEVELOPER,
            AuditAction.ASSET_DELETED, AuditResourceType.PROGRAM, "prog-1"
        )

        events, _ = audit_service.get_events()

        # Events should be newest first
        for i in range(len(events) - 1):
            assert events[i].timestamp >= events[i + 1].timestamp

    def test_get_events_by_user(self, audit_service):
        """Test retrieving events by user."""
        audit_service.record_event(
            "user-1", "user1@test.com", UserRole.DEVELOPER,
            AuditAction.ASSET_CREATED, AuditResourceType.PROGRAM, "prog-1"
        )
        audit_service.record_event(
            "user-1", "user1@test.com", UserRole.DEVELOPER,
            AuditAction.ASSET_CREATED, AuditResourceType.MODEL, "model-1"
        )
        audit_service.record_event(
            "user-2", "user2@test.com", UserRole.DEVELOPER,
            AuditAction.ASSET_CREATED, AuditResourceType.PROGRAM, "prog-2"
        )

        events = audit_service.get_events_by_user("user-1")

        assert len(events) == 2
        assert all(e.user_id == "user-1" for e in events)

    def test_get_events_by_resource(self, audit_service):
        """Test retrieving events by resource."""
        audit_service.record_event(
            "user-1", "user1@test.com", UserRole.DEVELOPER,
            AuditAction.ASSET_CREATED, AuditResourceType.PROGRAM, "prog-1"
        )
        audit_service.record_event(
            "user-2", "user2@test.com", UserRole.DEVELOPER,
            AuditAction.ASSET_VIEWED, AuditResourceType.PROGRAM, "prog-1"
        )
        audit_service.record_event(
            "user-1", "user1@test.com", UserRole.DEVELOPER,
            AuditAction.ASSET_CREATED, AuditResourceType.MODEL, "model-1"
        )

        events = audit_service.get_events_by_resource(
            AuditResourceType.PROGRAM, "prog-1"
        )

        assert len(events) == 2
        assert all(e.resource_id == "prog-1" for e in events)

    def test_delete_events_for_resource(self, audit_service):
        """Test deleting all events for a resource."""
        audit_service.record_event(
            "user-1", "user1@test.com", UserRole.DEVELOPER,
            AuditAction.ASSET_CREATED, AuditResourceType.PROGRAM, "prog-1"
        )
        audit_service.record_event(
            "user-1", "user1@test.com", UserRole.DEVELOPER,
            AuditAction.ASSET_UPDATED, AuditResourceType.PROGRAM, "prog-1"
        )
        audit_service.record_event(
            "user-1", "user1@test.com", UserRole.DEVELOPER,
            AuditAction.ASSET_CREATED, AuditResourceType.PROGRAM, "prog-2"
        )

        deleted_count = audit_service.delete_events_for_resource(
            AuditResourceType.PROGRAM, "prog-1"
        )

        assert deleted_count == 2
        assert len(audit_service.get_events_by_resource(
            AuditResourceType.PROGRAM, "prog-1"
        )) == 0
        assert len(audit_service.get_events_by_resource(
            AuditResourceType.PROGRAM, "prog-2"
        )) == 1


class TestAuditActions:
    """Tests for different audit action types."""

    def test_asset_lifecycle_actions(self, audit_service):
        """Test asset lifecycle action types."""
        actions = [
            AuditAction.ASSET_CREATED,
            AuditAction.ASSET_UPDATED,
            AuditAction.ASSET_DELETED,
            AuditAction.ASSET_VIEWED,
        ]

        for action in actions:
            event = audit_service.record_event(
                "user-1", "user@test.com", UserRole.DEVELOPER,
                action, AuditResourceType.PROGRAM, "prog-1"
            )
            assert event.action == action

    def test_sharing_actions(self, audit_service):
        """Test sharing action types."""
        actions = [
            AuditAction.ASSET_SHARED,
            AuditAction.ASSET_UNSHARED,
            AuditAction.ASSET_MADE_PUBLIC,
            AuditAction.ASSET_MADE_PRIVATE,
        ]

        for action in actions:
            event = audit_service.record_event(
                "user-1", "user@test.com", UserRole.DEVELOPER,
                action, AuditResourceType.PROGRAM, "prog-1"
            )
            assert event.action == action

    def test_run_actions(self, audit_service):
        """Test run action types."""
        actions = [
            AuditAction.RUN_STARTED,
            AuditAction.RUN_COMPLETED,
            AuditAction.RUN_FAILED,
            AuditAction.RUN_CANCELLED,
        ]

        for action in actions:
            event = audit_service.record_event(
                "user-1", "user@test.com", UserRole.DEVELOPER,
                action, AuditResourceType.RUN, "run-1"
            )
            assert event.action == action

    def test_auth_actions(self, audit_service):
        """Test auth action types."""
        actions = [
            AuditAction.AUTH_LOGIN,
            AuditAction.AUTH_LOGOUT,
            AuditAction.AUTH_LOGIN_FAILED,
        ]

        for action in actions:
            event = audit_service.record_event(
                "user-1", "user@test.com", UserRole.END_USER,
                action, AuditResourceType.USER, "user-1"
            )
            assert event.action == action

    def test_admin_actions(self, audit_service):
        """Test admin action types."""
        actions = [
            AuditAction.USER_ROLE_CHANGED,
            AuditAction.USER_QUOTA_CHANGED,
            AuditAction.USER_SUSPENDED,
            AuditAction.USER_REACTIVATED,
        ]

        for action in actions:
            event = audit_service.record_event(
                "admin-1", "admin@test.com", UserRole.ADMIN,
                action, AuditResourceType.USER, "user-1"
            )
            assert event.action == action

    def test_share_with_details(self, audit_service):
        """Test share action with grantee details."""
        event = audit_service.record_event(
            user_id="user-1",
            user_email="user@test.com",
            user_role=UserRole.DEVELOPER,
            action=AuditAction.ASSET_SHARED,
            resource_type=AuditResourceType.PROGRAM,
            resource_id="prog-1",
            resource_name="My Program",
            details={
                "grantee": "user-2",
                "grantee_email": "user2@test.com",
                "permission": "run"
            },
        )

        assert event.action == AuditAction.ASSET_SHARED
        assert event.details["grantee"] == "user-2"
        assert event.details["permission"] == "run"

    def test_role_change_with_details(self, audit_service):
        """Test role change action with from/to details."""
        event = audit_service.record_event(
            user_id="admin-1",
            user_email="admin@test.com",
            user_role=UserRole.ADMIN,
            action=AuditAction.USER_ROLE_CHANGED,
            resource_type=AuditResourceType.USER,
            resource_id="user-1",
            details={"from_role": "end_user", "to_role": "developer"},
        )

        assert event.action == AuditAction.USER_ROLE_CHANGED
        assert event.details["from_role"] == "end_user"
        assert event.details["to_role"] == "developer"
