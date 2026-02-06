"""Audit routes for querying application-wide audit trail (admin only)."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from mellea_api.core.deps import AdminUser
from mellea_api.models.audit import (
    AuditAction,
    AuditEventListResponse,
    AuditResourceType,
)
from mellea_api.services.audit import AuditService, get_audit_service

AuditServiceDep = Annotated[AuditService, Depends(get_audit_service)]

router = APIRouter(prefix="/api/v1/admin/audit", tags=["admin-audit"])


@router.get("", response_model=AuditEventListResponse)
async def get_audit_events(
    current_user: AdminUser,
    audit_service: AuditServiceDep,
    user_id: str | None = Query(None, alias="userId", description="Filter by acting user"),
    resource_id: str | None = Query(
        None, alias="resourceId", description="Filter by resource ID"
    ),
    resource_type: AuditResourceType | None = Query(
        None, alias="resourceType", description="Filter by resource type"
    ),
    action: AuditAction | None = Query(None, description="Filter by action type"),
    since: datetime | None = Query(
        None, alias="from", description="Filter events after this time (ISO 8601)"
    ),
    until: datetime | None = Query(
        None, alias="to", description="Filter events before this time (ISO 8601)"
    ),
    success: bool | None = Query(None, description="Filter by success status"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum events to return"),
    offset: int = Query(0, ge=0, description="Number of events to skip"),
) -> AuditEventListResponse:
    """Query audit events with filters (admin only).

    Returns a paginated list of audit events matching the specified filters.
    All parameters are optional and can be combined for more specific queries.

    Typical use cases:
    - View all actions by a specific user
    - Track changes to a specific resource
    - Monitor login attempts
    - Review admin actions
    """
    events, total = audit_service.get_events(
        user_id=user_id,
        resource_id=resource_id,
        resource_type=resource_type,
        action=action,
        since=since,
        until=until,
        success=success,
        limit=limit,
        offset=offset,
    )

    return AuditEventListResponse(
        events=events,
        total=total,
        limit=limit,
        offset=offset,
    )
