"""Run audit routes for querying access audit trail."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from mellea_api.core.deps import CurrentUser
from mellea_api.models.run_audit import RunAuditAction, RunAuditEvent, RunAuditSummary
from mellea_api.services.run import RunService, get_run_service
from mellea_api.services.run_audit import RunAuditService, get_run_audit_service

RunServiceDep = Annotated[RunService, Depends(get_run_service)]
RunAuditServiceDep = Annotated[RunAuditService, Depends(get_run_audit_service)]

router = APIRouter(prefix="/api/v1/runs", tags=["run-audit"])


class AuditEventsResponse(BaseModel):
    """Response containing list of audit events."""

    events: list[RunAuditEvent]
    total: int

    class Config:
        populate_by_name = True


class AuditSummaryResponse(BaseModel):
    """Response containing audit summary."""

    summary: RunAuditSummary

    class Config:
        populate_by_name = True


@router.get("/{run_id}/audit", response_model=AuditEventsResponse)
async def get_run_audit_events(
    run_id: str,
    current_user: CurrentUser,
    run_service: RunServiceDep,
    audit_service: RunAuditServiceDep,
    action: RunAuditAction | None = Query(None, description="Filter by action type"),
    actor_id: str | None = Query(None, alias="actorId", description="Filter by actor"),
    since: datetime | None = Query(None, description="Filter events after this time"),
    until: datetime | None = Query(None, description="Filter events before this time"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum events to return"),
) -> AuditEventsResponse:
    """Get audit events for a specific run.

    Returns the access audit trail for a run, showing who accessed it
    and what actions they performed.

    Only the run owner can view the audit trail.
    """
    # Verify run exists
    run = run_service.get_run(run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run not found: {run_id}",
        )

    # Only owner can view audit trail
    if run.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the run owner can view the audit trail",
        )

    events = audit_service.get_events_for_run(
        run_id=run_id,
        action=action,
        actor_id=actor_id,
        since=since,
        until=until,
        limit=limit,
    )

    return AuditEventsResponse(events=events, total=len(events))


@router.get("/{run_id}/audit/summary", response_model=AuditSummaryResponse)
async def get_run_audit_summary(
    run_id: str,
    current_user: CurrentUser,
    run_service: RunServiceDep,
    audit_service: RunAuditServiceDep,
) -> AuditSummaryResponse:
    """Get audit summary for a specific run.

    Returns aggregated statistics about run access, including
    total events, unique viewers, and counts by action type.

    Only the run owner can view the audit summary.
    """
    # Verify run exists
    run = run_service.get_run(run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run not found: {run_id}",
        )

    # Only owner can view audit summary
    if run.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the run owner can view the audit summary",
        )

    summary = audit_service.get_audit_summary(run_id)
    return AuditSummaryResponse(summary=summary)
