"""Run Audit Service for tracking run access events."""

import logging
from datetime import datetime

from mellea_api.core.config import Settings, get_settings
from mellea_api.core.store import JsonStore
from mellea_api.models.run_audit import RunAuditAction, RunAuditEvent, RunAuditSummary

logger = logging.getLogger(__name__)


class RunAuditService:
    """Service for managing run access audit trail.

    Provides methods to record and query audit events for run access,
    enabling compliance tracking and security monitoring.

    Example:
        ```python
        service = get_run_audit_service()

        # Record a view event
        service.record_event(
            run_id="run-123",
            actor_id="user-456",
            action=RunAuditAction.VIEW,
        )

        # Get audit history for a run
        events = service.get_events_for_run("run-123")

        # Get summary
        summary = service.get_audit_summary("run-123")
        ```
    """

    def __init__(self, settings: Settings | None = None) -> None:
        """Initialize the RunAuditService.

        Args:
            settings: Application settings (uses default if not provided)
        """
        self.settings = settings or get_settings()
        self._audit_store: JsonStore[RunAuditEvent] | None = None

    @property
    def audit_store(self) -> JsonStore[RunAuditEvent]:
        """Get the audit store, initializing if needed."""
        if self._audit_store is None:
            file_path = self.settings.data_dir / "metadata" / "run_audit.json"
            self._audit_store = JsonStore[RunAuditEvent](
                file_path=file_path,
                collection_key="audit_events",
                model_class=RunAuditEvent,
            )
        return self._audit_store

    def record_event(
        self,
        run_id: str,
        actor_id: str,
        action: RunAuditAction,
        details: dict[str, str] | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> RunAuditEvent:
        """Record an audit event for a run.

        Args:
            run_id: ID of the run being accessed
            actor_id: User ID who performed the action
            action: Type of action performed
            details: Additional context (e.g., {"target_user": "user-789"})
            ip_address: IP address of the actor
            user_agent: Browser/client user agent

        Returns:
            The created audit event
        """
        event = RunAuditEvent(
            run_id=run_id,
            actor_id=actor_id,
            action=action,
            details=details,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        created = self.audit_store.create(event)
        logger.debug(
            f"Recorded audit event: {action.value} on run {run_id} by {actor_id}"
        )
        return created

    def get_events_for_run(
        self,
        run_id: str,
        action: RunAuditAction | None = None,
        actor_id: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int | None = None,
    ) -> list[RunAuditEvent]:
        """Get audit events for a specific run.

        Args:
            run_id: ID of the run to get events for
            action: Filter by action type
            actor_id: Filter by actor
            since: Filter events after this time
            until: Filter events before this time
            limit: Maximum number of events to return

        Returns:
            List of matching audit events, sorted by timestamp (newest first)
        """
        events = self.audit_store.find(lambda e: e.run_id == run_id)

        if action:
            events = [e for e in events if e.action == action]

        if actor_id:
            events = [e for e in events if e.actor_id == actor_id]

        if since:
            events = [e for e in events if e.timestamp >= since]

        if until:
            events = [e for e in events if e.timestamp <= until]

        # Sort by timestamp descending (newest first)
        events.sort(key=lambda e: e.timestamp, reverse=True)

        if limit:
            events = events[:limit]

        return events

    def get_events_by_actor(
        self,
        actor_id: str,
        action: RunAuditAction | None = None,
        since: datetime | None = None,
        limit: int | None = None,
    ) -> list[RunAuditEvent]:
        """Get all audit events performed by a specific user.

        Args:
            actor_id: User ID to get events for
            action: Filter by action type
            since: Filter events after this time
            limit: Maximum number of events to return

        Returns:
            List of matching audit events, sorted by timestamp (newest first)
        """
        events = self.audit_store.find(lambda e: e.actor_id == actor_id)

        if action:
            events = [e for e in events if e.action == action]

        if since:
            events = [e for e in events if e.timestamp >= since]

        # Sort by timestamp descending
        events.sort(key=lambda e: e.timestamp, reverse=True)

        if limit:
            events = events[:limit]

        return events

    def get_audit_summary(self, run_id: str) -> RunAuditSummary:
        """Get a summary of audit events for a run.

        Args:
            run_id: ID of the run to summarize

        Returns:
            Summary statistics for the run's audit history
        """
        events = self.get_events_for_run(run_id)

        # Count events by action
        action_counts: dict[str, int] = {}
        for event in events:
            action_counts[event.action.value] = action_counts.get(event.action.value, 0) + 1

        # Get unique viewers
        unique_actors = {e.actor_id for e in events}

        # Get last accessed time
        last_accessed = events[0].timestamp if events else None

        return RunAuditSummary(
            run_id=run_id,
            total_events=len(events),
            unique_viewers=len(unique_actors),
            last_accessed=last_accessed,
            access_by_action=action_counts,
        )

    def delete_events_for_run(self, run_id: str) -> int:
        """Delete all audit events for a run.

        Used when a run is deleted to clean up associated audit data.

        Args:
            run_id: ID of the run to delete events for

        Returns:
            Number of events deleted
        """
        events = self.get_events_for_run(run_id)
        count = 0
        for event in events:
            if self.audit_store.delete(event.id):
                count += 1

        if count > 0:
            logger.info(f"Deleted {count} audit events for run {run_id}")

        return count


# Global service instance
_run_audit_service: RunAuditService | None = None


def get_run_audit_service() -> RunAuditService:
    """Get the global RunAuditService instance."""
    global _run_audit_service
    if _run_audit_service is None:
        _run_audit_service = RunAuditService()
    return _run_audit_service
