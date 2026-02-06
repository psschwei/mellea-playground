"""Tests for run access audit trail."""

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from mellea_api.core.config import Settings
from mellea_api.models.run_audit import RunAuditAction, RunAuditEvent
from mellea_api.services.run_audit import RunAuditService


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
    return RunAuditService(settings=temp_settings)


class TestRunAuditEvent:
    """Tests for RunAuditEvent model."""

    def test_create_event(self):
        """Test creating an audit event with required fields."""
        event = RunAuditEvent(
            runId="run-123",
            actorId="user-456",
            action=RunAuditAction.VIEW,
        )

        assert event.run_id == "run-123"
        assert event.actor_id == "user-456"
        assert event.action == RunAuditAction.VIEW
        assert event.id is not None
        assert event.timestamp is not None
        assert event.details is None

    def test_create_event_with_details(self):
        """Test creating an audit event with details."""
        event = RunAuditEvent(
            runId="run-123",
            actorId="user-456",
            action=RunAuditAction.SHARE,
            details={"target_user": "user-789", "permission": "view"},
        )

        assert event.details == {"target_user": "user-789", "permission": "view"}

    def test_create_event_with_metadata(self):
        """Test creating an audit event with IP and user agent."""
        event = RunAuditEvent(
            runId="run-123",
            actorId="user-456",
            action=RunAuditAction.VIEW,
            ipAddress="192.168.1.1",
            userAgent="Mozilla/5.0",
        )

        assert event.ip_address == "192.168.1.1"
        assert event.user_agent == "Mozilla/5.0"


class TestRunAuditService:
    """Tests for RunAuditService."""

    def test_record_event(self, audit_service):
        """Test recording an audit event."""
        event = audit_service.record_event(
            run_id="run-123",
            actor_id="user-456",
            action=RunAuditAction.VIEW,
        )

        assert event.run_id == "run-123"
        assert event.actor_id == "user-456"
        assert event.action == RunAuditAction.VIEW

    def test_record_event_with_details(self, audit_service):
        """Test recording an event with details."""
        event = audit_service.record_event(
            run_id="run-123",
            actor_id="user-456",
            action=RunAuditAction.SHARE,
            details={"target_user": "user-789"},
        )

        assert event.details == {"target_user": "user-789"}

    def test_get_events_for_run(self, audit_service):
        """Test retrieving events for a specific run."""
        # Record multiple events for different runs
        audit_service.record_event("run-123", "user-1", RunAuditAction.VIEW)
        audit_service.record_event("run-123", "user-2", RunAuditAction.VIEW)
        audit_service.record_event("run-456", "user-1", RunAuditAction.VIEW)
        audit_service.record_event("run-123", "user-1", RunAuditAction.SHARE)

        events = audit_service.get_events_for_run("run-123")

        assert len(events) == 3
        assert all(e.run_id == "run-123" for e in events)

    def test_get_events_for_run_filter_by_action(self, audit_service):
        """Test filtering events by action type."""
        audit_service.record_event("run-123", "user-1", RunAuditAction.VIEW)
        audit_service.record_event("run-123", "user-1", RunAuditAction.SHARE)
        audit_service.record_event("run-123", "user-1", RunAuditAction.VIEW)

        events = audit_service.get_events_for_run("run-123", action=RunAuditAction.VIEW)

        assert len(events) == 2
        assert all(e.action == RunAuditAction.VIEW for e in events)

    def test_get_events_for_run_filter_by_actor(self, audit_service):
        """Test filtering events by actor."""
        audit_service.record_event("run-123", "user-1", RunAuditAction.VIEW)
        audit_service.record_event("run-123", "user-2", RunAuditAction.VIEW)
        audit_service.record_event("run-123", "user-1", RunAuditAction.VIEW)

        events = audit_service.get_events_for_run("run-123", actor_id="user-1")

        assert len(events) == 2
        assert all(e.actor_id == "user-1" for e in events)

    def test_get_events_for_run_limit(self, audit_service):
        """Test limiting number of events returned."""
        for i in range(10):
            audit_service.record_event("run-123", f"user-{i}", RunAuditAction.VIEW)

        events = audit_service.get_events_for_run("run-123", limit=5)

        assert len(events) == 5

    def test_get_events_for_run_sorted_by_timestamp(self, audit_service):
        """Test events are sorted by timestamp (newest first)."""
        audit_service.record_event("run-123", "user-1", RunAuditAction.VIEW)
        audit_service.record_event("run-123", "user-2", RunAuditAction.SHARE)
        audit_service.record_event("run-123", "user-3", RunAuditAction.DELETE)

        events = audit_service.get_events_for_run("run-123")

        # Events should be newest first
        for i in range(len(events) - 1):
            assert events[i].timestamp >= events[i + 1].timestamp

    def test_get_events_by_actor(self, audit_service):
        """Test retrieving events by actor."""
        audit_service.record_event("run-123", "user-1", RunAuditAction.VIEW)
        audit_service.record_event("run-456", "user-1", RunAuditAction.VIEW)
        audit_service.record_event("run-789", "user-2", RunAuditAction.VIEW)

        events = audit_service.get_events_by_actor("user-1")

        assert len(events) == 2
        assert all(e.actor_id == "user-1" for e in events)

    def test_get_audit_summary(self, audit_service):
        """Test getting audit summary for a run."""
        audit_service.record_event("run-123", "user-1", RunAuditAction.VIEW)
        audit_service.record_event("run-123", "user-2", RunAuditAction.VIEW)
        audit_service.record_event("run-123", "user-1", RunAuditAction.SHARE)

        summary = audit_service.get_audit_summary("run-123")

        assert summary.run_id == "run-123"
        assert summary.total_events == 3
        assert summary.unique_viewers == 2
        assert summary.access_by_action["view"] == 2
        assert summary.access_by_action["share"] == 1
        assert summary.last_accessed is not None

    def test_get_audit_summary_empty(self, audit_service):
        """Test getting summary for run with no events."""
        summary = audit_service.get_audit_summary("run-nonexistent")

        assert summary.run_id == "run-nonexistent"
        assert summary.total_events == 0
        assert summary.unique_viewers == 0
        assert summary.last_accessed is None
        assert summary.access_by_action == {}

    def test_delete_events_for_run(self, audit_service):
        """Test deleting all events for a run."""
        audit_service.record_event("run-123", "user-1", RunAuditAction.VIEW)
        audit_service.record_event("run-123", "user-2", RunAuditAction.VIEW)
        audit_service.record_event("run-456", "user-1", RunAuditAction.VIEW)

        deleted_count = audit_service.delete_events_for_run("run-123")

        assert deleted_count == 2
        assert len(audit_service.get_events_for_run("run-123")) == 0
        assert len(audit_service.get_events_for_run("run-456")) == 1


class TestRunAuditActions:
    """Tests for different audit action types."""

    def test_all_action_types(self, audit_service):
        """Test recording all action types."""
        actions = [
            RunAuditAction.VIEW,
            RunAuditAction.CREATE,
            RunAuditAction.DELETE,
            RunAuditAction.CANCEL,
            RunAuditAction.SHARE,
            RunAuditAction.REVOKE,
            RunAuditAction.VISIBILITY_CHANGE,
            RunAuditAction.LOGS_VIEW,
            RunAuditAction.LOGS_STREAM,
        ]

        for action in actions:
            event = audit_service.record_event("run-123", "user-1", action)
            assert event.action == action

    def test_visibility_change_details(self, audit_service):
        """Test visibility change with from/to details."""
        event = audit_service.record_event(
            run_id="run-123",
            actor_id="user-1",
            action=RunAuditAction.VISIBILITY_CHANGE,
            details={"from": "private", "to": "public"},
        )

        assert event.action == RunAuditAction.VISIBILITY_CHANGE
        assert event.details["from"] == "private"
        assert event.details["to"] == "public"

    def test_share_with_permission_details(self, audit_service):
        """Test share action with target user and permission."""
        event = audit_service.record_event(
            run_id="run-123",
            actor_id="user-1",
            action=RunAuditAction.SHARE,
            details={"target_user": "user-789", "permission": "edit"},
        )

        assert event.action == RunAuditAction.SHARE
        assert event.details["target_user"] == "user-789"
        assert event.details["permission"] == "edit"
