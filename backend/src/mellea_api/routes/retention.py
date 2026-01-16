"""Retention policy routes for managing automatic resource cleanup."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

from mellea_api.core.deps import CurrentUser
from mellea_api.models.retention_policy import (
    PolicyPreviewResult,
    ResourceType,
    RetentionCondition,
    RetentionPolicy,
)
from mellea_api.services.retention_policy import (
    RetentionPolicyService,
    get_retention_policy_service,
)

RetentionPolicyServiceDep = Annotated[
    RetentionPolicyService, Depends(get_retention_policy_service)
]

router = APIRouter(prefix="/api/v1/retention", tags=["retention"])


# -------------------------------------------------------------------------
# Request/Response Models
# -------------------------------------------------------------------------


class CreatePolicyRequest(BaseModel):
    """Request body for creating a retention policy."""

    name: str = Field(description="Human-readable name for the policy")
    description: str | None = Field(default=None, description="Optional description")
    resource_type: ResourceType = Field(
        alias="resourceType", description="Type of resource this policy applies to"
    )
    condition: RetentionCondition = Field(description="The condition type to evaluate")
    threshold: int = Field(
        description="Value for the condition (days, bytes, etc.)"
    )
    status_value: str | None = Field(
        default=None,
        alias="statusValue",
        description="Status value when condition is STATUS",
    )
    enabled: bool = Field(default=True, description="Whether the policy is active")
    priority: int = Field(
        default=0, description="Higher priority policies are evaluated first"
    )

    class Config:
        populate_by_name = True


class UpdatePolicyRequest(BaseModel):
    """Request body for updating a retention policy."""

    name: str | None = Field(default=None, description="New name")
    description: str | None = Field(default=None, description="New description")
    threshold: int | None = Field(default=None, description="New threshold value")
    status_value: str | None = Field(
        default=None, alias="statusValue", description="New status value"
    )
    enabled: bool | None = Field(default=None, description="New enabled state")
    priority: int | None = Field(default=None, description="New priority")

    class Config:
        populate_by_name = True


class PolicyResponse(BaseModel):
    """Response wrapper for policy operations."""

    policy: RetentionPolicy


class PoliciesListResponse(BaseModel):
    """Response for list policies operation."""

    policies: list[RetentionPolicy]
    total: int


class PreviewResponse(BaseModel):
    """Response for policy preview."""

    preview: PolicyPreviewResult


class CleanupResponse(BaseModel):
    """Response for cleanup operation."""

    model_config = ConfigDict(populate_by_name=True)

    policies_evaluated: int = Field(serialization_alias="policiesEvaluated")
    artifacts_deleted: int = Field(serialization_alias="artifactsDeleted")
    runs_deleted: int = Field(serialization_alias="runsDeleted")
    environments_cleaned: int = Field(serialization_alias="environmentsCleaned")
    logs_deleted: int = Field(serialization_alias="logsDeleted")
    storage_freed_bytes: int = Field(serialization_alias="storageFreedBytes")
    errors: list[str]
    duration_seconds: float = Field(serialization_alias="durationSeconds")


class MetricsResponse(BaseModel):
    """Response for metrics query."""

    model_config = ConfigDict(populate_by_name=True)

    has_metrics: bool = Field(serialization_alias="hasMetrics")
    timestamp: str | None = None
    policies_evaluated: int = Field(default=0, serialization_alias="policiesEvaluated")
    artifacts_deleted: int = Field(default=0, serialization_alias="artifactsDeleted")
    runs_deleted: int = Field(default=0, serialization_alias="runsDeleted")
    environments_cleaned: int = Field(default=0, serialization_alias="environmentsCleaned")
    logs_deleted: int = Field(default=0, serialization_alias="logsDeleted")
    storage_freed_bytes: int = Field(default=0, serialization_alias="storageFreedBytes")
    errors: list[str] = Field(default_factory=list)
    duration_seconds: float = Field(default=0.0, serialization_alias="durationSeconds")


# -------------------------------------------------------------------------
# Routes
# -------------------------------------------------------------------------


@router.post("/policies", response_model=PolicyResponse, status_code=status.HTTP_201_CREATED)
async def create_policy(
    request: CreatePolicyRequest,
    current_user: CurrentUser,
    retention_service: RetentionPolicyServiceDep,
) -> PolicyResponse:
    """Create a new retention policy.

    Creates a policy that defines rules for automatically cleaning up resources.
    Only admins can create system-wide policies (user_id=None).
    Regular users create policies that only affect their own resources.
    """
    # Regular users create user-scoped policies, admins can create system-wide
    user_id = None if current_user.role.value == "admin" else current_user.id

    policy = retention_service.create_policy(
        name=request.name,
        description=request.description,
        resource_type=request.resource_type,
        condition=request.condition,
        threshold=request.threshold,
        status_value=request.status_value,
        enabled=request.enabled,
        priority=request.priority,
        user_id=user_id,
    )

    return PolicyResponse(policy=policy)


@router.get("/policies", response_model=PoliciesListResponse)
async def list_policies(
    current_user: CurrentUser,
    retention_service: RetentionPolicyServiceDep,
    resource_type: ResourceType | None = Query(
        None, alias="resourceType", description="Filter by resource type"
    ),
    enabled_only: bool = Query(
        False, alias="enabledOnly", description="Only show enabled policies"
    ),
) -> PoliciesListResponse:
    """List retention policies.

    Returns policies visible to the authenticated user:
    - Admins see all policies
    - Regular users see their own policies plus system-wide policies
    """
    # Admins see all, users see their own + system-wide
    user_id = None if current_user.role.value == "admin" else current_user.id

    policies = retention_service.list_policies(
        resource_type=resource_type,
        enabled_only=enabled_only,
        user_id=user_id,
    )

    return PoliciesListResponse(policies=policies, total=len(policies))


@router.get("/policies/{policy_id}", response_model=PolicyResponse)
async def get_policy(
    policy_id: str,
    current_user: CurrentUser,
    retention_service: RetentionPolicyServiceDep,
) -> PolicyResponse:
    """Get a retention policy by ID.

    Returns the policy if the user has access to view it.
    """
    policy = retention_service.get_policy(policy_id)
    if policy is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Policy not found: {policy_id}",
        )

    # Check access: admins see all, users see their own + system-wide
    if (
        current_user.role.value != "admin"
        and policy.user_id is not None
        and policy.user_id != current_user.id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to view this policy",
        )

    return PolicyResponse(policy=policy)


@router.put("/policies/{policy_id}", response_model=PolicyResponse)
async def update_policy(
    policy_id: str,
    request: UpdatePolicyRequest,
    current_user: CurrentUser,
    retention_service: RetentionPolicyServiceDep,
) -> PolicyResponse:
    """Update an existing retention policy.

    Only the policy owner or an admin can update a policy.
    """
    policy = retention_service.get_policy(policy_id)
    if policy is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Policy not found: {policy_id}",
        )

    # Check ownership: admins can update all, users can only update their own
    if current_user.role.value != "admin" and policy.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to update this policy",
        )

    updated = retention_service.update_policy(
        policy_id=policy_id,
        name=request.name,
        description=request.description,
        threshold=request.threshold,
        status_value=request.status_value,
        enabled=request.enabled,
        priority=request.priority,
    )

    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Policy not found: {policy_id}",
        )

    return PolicyResponse(policy=updated)


@router.delete("/policies/{policy_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_policy(
    policy_id: str,
    current_user: CurrentUser,
    retention_service: RetentionPolicyServiceDep,
) -> None:
    """Delete a retention policy.

    Only the policy owner or an admin can delete a policy.
    """
    policy = retention_service.get_policy(policy_id)
    if policy is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Policy not found: {policy_id}",
        )

    # Check ownership: admins can delete all, users can only delete their own
    if current_user.role.value != "admin" and policy.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to delete this policy",
        )

    retention_service.delete_policy(policy_id)


@router.post("/cleanup", response_model=CleanupResponse)
async def trigger_cleanup(
    current_user: CurrentUser,
    retention_service: RetentionPolicyServiceDep,
) -> CleanupResponse:
    """Trigger a manual retention cleanup cycle.

    Only admins can trigger manual cleanup cycles. This evaluates all enabled
    policies and deletes/cleans matching resources.
    """
    if current_user.role.value != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can trigger manual cleanup cycles",
        )

    metrics = await retention_service.run_cleanup_cycle()

    return CleanupResponse(
        policies_evaluated=metrics.policies_evaluated,
        artifacts_deleted=metrics.artifacts_deleted,
        runs_deleted=metrics.runs_deleted,
        environments_cleaned=metrics.environments_cleaned,
        logs_deleted=metrics.logs_deleted,
        storage_freed_bytes=metrics.storage_freed_bytes,
        errors=metrics.errors,
        duration_seconds=metrics.duration_seconds,
    )


@router.get("/metrics", response_model=MetricsResponse)
async def get_metrics(
    current_user: CurrentUser,
    retention_service: RetentionPolicyServiceDep,
) -> MetricsResponse:
    """Get metrics from the last cleanup run.

    Returns statistics about what was cleaned up in the most recent
    retention policy evaluation cycle.
    """
    metrics = retention_service.get_last_metrics()

    if metrics is None:
        return MetricsResponse(has_metrics=False)

    return MetricsResponse(
        has_metrics=True,
        timestamp=metrics.timestamp.isoformat(),
        policies_evaluated=metrics.policies_evaluated,
        artifacts_deleted=metrics.artifacts_deleted,
        runs_deleted=metrics.runs_deleted,
        environments_cleaned=metrics.environments_cleaned,
        logs_deleted=metrics.logs_deleted,
        storage_freed_bytes=metrics.storage_freed_bytes,
        errors=metrics.errors,
        duration_seconds=metrics.duration_seconds,
    )


@router.get("/preview/{policy_id}", response_model=PreviewResponse)
async def preview_policy(
    policy_id: str,
    current_user: CurrentUser,
    retention_service: RetentionPolicyServiceDep,
) -> PreviewResponse:
    """Preview what a policy would delete.

    Returns a list of resources that match the policy criteria without
    actually deleting them. Useful for testing policies before enabling.
    """
    policy = retention_service.get_policy(policy_id)
    if policy is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Policy not found: {policy_id}",
        )

    # Check access: admins see all, users see their own + system-wide
    if (
        current_user.role.value != "admin"
        and policy.user_id is not None
        and policy.user_id != current_user.id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to preview this policy",
        )

    preview = retention_service.preview_policy(policy_id)
    if preview is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Policy not found: {policy_id}",
        )

    return PreviewResponse(preview=preview)
