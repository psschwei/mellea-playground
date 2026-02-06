"""Audit Service for application-wide action logging."""

import logging
from datetime import datetime

from mellea_api.core.config import Settings, get_settings
from mellea_api.core.store import JsonStore
from mellea_api.models.audit import (
    AuditAction,
    AuditEvent,
    AuditResourceType,
)
from mellea_api.models.user import UserRole

logger = logging.getLogger(__name__)


class AuditService:
    """Service for managing application-wide audit trail.

    Provides methods to record and query audit events for all actions,
    enabling compliance tracking, security monitoring, and debugging.

    Example:
        ```python
        service = get_audit_service()

        # Record an asset creation event
        service.record_event(
            user_id="user-123",
            user_email="alice@example.com",
            user_role=UserRole.DEVELOPER,
            action=AuditAction.ASSET_CREATED,
            resource_type=AuditResourceType.PROGRAM,
            resource_id="prog-456",
            resource_name="My Program",
        )

        # Query audit events
        events = service.get_events(
            user_id="user-123",
            action=AuditAction.ASSET_CREATED,
            limit=50,
        )
        ```
    """

    def __init__(self, settings: Settings | None = None) -> None:
        """Initialize the AuditService.

        Args:
            settings: Application settings (uses default if not provided)
        """
        self.settings = settings or get_settings()
        self._store: JsonStore[AuditEvent] | None = None

    @property
    def store(self) -> JsonStore[AuditEvent]:
        """Get the audit store, initializing if needed."""
        if self._store is None:
            file_path = self.settings.data_dir / "metadata" / "audit_events.json"
            self._store = JsonStore[AuditEvent](
                file_path=file_path,
                collection_key="events",
                model_class=AuditEvent,
            )
        return self._store

    def record_event(
        self,
        user_id: str,
        user_email: str,
        user_role: UserRole,
        action: AuditAction,
        resource_type: AuditResourceType,
        resource_id: str,
        resource_name: str | None = None,
        details: dict[str, str] | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        success: bool = True,
        error_message: str | None = None,
    ) -> AuditEvent:
        """Record an audit event.

        Args:
            user_id: User ID who performed the action
            user_email: Email of the user
            user_role: Role of the user at time of action
            action: Type of action performed
            resource_type: Type of resource affected
            resource_id: ID of the affected resource
            resource_name: Human-readable name of the resource
            details: Additional context (e.g., {"target_user": "user-789"})
            ip_address: IP address of the actor
            user_agent: Browser/client user agent
            success: Whether the action succeeded
            error_message: Error message if action failed

        Returns:
            The created audit event
        """
        event = AuditEvent(
            user_id=user_id,
            user_email=user_email,
            user_role=user_role,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            resource_name=resource_name,
            details=details,
            ip_address=ip_address,
            user_agent=user_agent,
            success=success,
            error_message=error_message,
        )
        created = self.store.create(event)
        logger.debug(
            f"Recorded audit event: {action.value} on {resource_type.value}/{resource_id} "
            f"by {user_email}"
        )
        return created

    def get_events(
        self,
        user_id: str | None = None,
        resource_id: str | None = None,
        resource_type: AuditResourceType | None = None,
        action: AuditAction | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        success: bool | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[AuditEvent], int]:
        """Query audit events with filters.

        Args:
            user_id: Filter by acting user
            resource_id: Filter by resource ID
            resource_type: Filter by resource type
            action: Filter by action type
            since: Filter events after this time
            until: Filter events before this time
            success: Filter by success status
            limit: Maximum number of events to return
            offset: Number of events to skip (for pagination)

        Returns:
            Tuple of (list of matching audit events, total count before pagination)
        """
        # Get all events and apply filters
        events = self.store.list_all()

        if user_id:
            events = [e for e in events if e.user_id == user_id]

        if resource_id:
            events = [e for e in events if e.resource_id == resource_id]

        if resource_type:
            events = [e for e in events if e.resource_type == resource_type]

        if action:
            events = [e for e in events if e.action == action]

        if since:
            events = [e for e in events if e.timestamp >= since]

        if until:
            events = [e for e in events if e.timestamp <= until]

        if success is not None:
            events = [e for e in events if e.success == success]

        # Sort by timestamp descending (newest first)
        events.sort(key=lambda e: e.timestamp, reverse=True)

        # Get total count before pagination
        total = len(events)

        # Apply pagination
        events = events[offset : offset + limit]

        return events, total

    def get_events_by_user(
        self,
        user_id: str,
        action: AuditAction | None = None,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[AuditEvent]:
        """Get all audit events performed by a specific user.

        Args:
            user_id: User ID to get events for
            action: Filter by action type
            since: Filter events after this time
            limit: Maximum number of events to return

        Returns:
            List of matching audit events, sorted by timestamp (newest first)
        """
        events, _ = self.get_events(
            user_id=user_id,
            action=action,
            since=since,
            limit=limit,
        )
        return events

    def get_events_by_resource(
        self,
        resource_type: AuditResourceType,
        resource_id: str,
        action: AuditAction | None = None,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[AuditEvent]:
        """Get all audit events for a specific resource.

        Args:
            resource_type: Type of resource
            resource_id: Resource ID to get events for
            action: Filter by action type
            since: Filter events after this time
            limit: Maximum number of events to return

        Returns:
            List of matching audit events, sorted by timestamp (newest first)
        """
        events, _ = self.get_events(
            resource_type=resource_type,
            resource_id=resource_id,
            action=action,
            since=since,
            limit=limit,
        )
        return events

    def delete_events_for_resource(
        self,
        resource_type: AuditResourceType,
        resource_id: str,
    ) -> int:
        """Delete all audit events for a resource.

        Used when a resource is deleted to optionally clean up associated audit data.
        Note: In many compliance scenarios, you may want to retain audit data even
        after resource deletion.

        Args:
            resource_type: Type of resource
            resource_id: ID of the resource to delete events for

        Returns:
            Number of events deleted
        """
        events = self.get_events_by_resource(
            resource_type=resource_type,
            resource_id=resource_id,
            limit=10000,  # Get all events
        )
        count = 0
        for event in events:
            if self.store.delete(event.id):
                count += 1

        if count > 0:
            logger.info(
                f"Deleted {count} audit events for {resource_type.value}/{resource_id}"
            )

        return count


# Global service instance
_audit_service: AuditService | None = None


def get_audit_service() -> AuditService:
    """Get the global AuditService instance."""
    global _audit_service
    if _audit_service is None:
        _audit_service = AuditService()
    return _audit_service


def reset_audit_service() -> None:
    """Reset the global AuditService instance (for testing)."""
    global _audit_service
    _audit_service = None
