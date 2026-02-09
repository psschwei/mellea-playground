"""Admin routes for user management and quota monitoring."""

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from mellea_api.core.deps import AdminUser as AdminUserDep
from mellea_api.models.user import User, UserQuotas, UserRole, UserStatus
from mellea_api.services.auth import AuthService, get_auth_service
from mellea_api.services.quota import QuotaService, get_quota_service
from mellea_api.services.run import RunService, get_run_service

AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
QuotaServiceDep = Annotated[QuotaService, Depends(get_quota_service)]
RunServiceDep = Annotated[RunService, Depends(get_run_service)]

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


# --- Response Models ---


class AdminUserStats(BaseModel):
    """User statistics for admin dashboard."""

    model_config = ConfigDict(populate_by_name=True)

    total_users: int = Field(serialization_alias="totalUsers")
    active_users: int = Field(serialization_alias="activeUsers")
    suspended_users: int = Field(serialization_alias="suspendedUsers")
    pending_users: int = Field(serialization_alias="pendingUsers")
    users_by_role: dict[str, int] = Field(serialization_alias="usersByRole")


class AdminUserUsageStats(BaseModel):
    """Usage statistics for a user."""

    model_config = ConfigDict(populate_by_name=True)

    total_runs: int = Field(default=0, serialization_alias="totalRuns")
    total_programs: int = Field(default=0, serialization_alias="totalPrograms")
    storage_used_mb: float = Field(default=0.0, serialization_alias="storageUsedMB")


class AdminUserResponse(BaseModel):
    """Extended user model for admin view."""

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    id: str
    email: EmailStr
    display_name: str = Field(serialization_alias="displayName")
    avatar_url: str | None = Field(default=None, serialization_alias="avatarUrl")
    role: UserRole
    status: UserStatus
    created_at: datetime = Field(serialization_alias="createdAt")
    last_login_at: datetime | None = Field(default=None, serialization_alias="lastLoginAt")
    quotas: UserQuotas | None = None
    usage_stats: AdminUserUsageStats | None = Field(default=None, serialization_alias="usageStats")


class AdminUserListResponse(BaseModel):
    """Paginated user list response."""

    model_config = ConfigDict(populate_by_name=True)

    users: list[AdminUserResponse]
    total: int
    page: int
    limit: int
    total_pages: int = Field(serialization_alias="totalPages")


class UpdateUserRequest(BaseModel):
    """Request to update a user."""

    model_config = ConfigDict(populate_by_name=True)

    display_name: str | None = Field(default=None, validation_alias="displayName")
    role: UserRole | None = None
    status: UserStatus | None = None
    quotas: UserQuotas | None = None


class QuotaUsageStats(BaseModel):
    """System-wide quota usage statistics."""

    model_config = ConfigDict(populate_by_name=True)

    total_users: int = Field(serialization_alias="totalUsers")
    users_at_limit: int = Field(serialization_alias="usersAtLimit")
    total_cpu_hours_used: float = Field(serialization_alias="totalCpuHoursUsed")
    total_runs_today: int = Field(serialization_alias="totalRunsToday")
    top_users_by_cpu: list[dict[str, Any]] = Field(serialization_alias="topUsersByCpu")
    top_users_by_runs: list[dict[str, Any]] = Field(serialization_alias="topUsersByRuns")


# --- Helper Functions ---


def _user_to_admin_user(
    user: User,
    run_service: RunService | None = None,
) -> AdminUserResponse:
    """Convert a User to AdminUserResponse with usage stats."""
    usage_stats = None
    if run_service:
        all_runs = run_service.list_runs(owner_id=user.id)
        usage_stats = AdminUserUsageStats(
            total_runs=len(all_runs),
            total_programs=0,  # Would need asset service to calculate
            storage_used_mb=0.0,  # Would need storage service to calculate
        )

    return AdminUserResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        avatar_url=user.avatar_url,
        role=user.role,
        status=user.status,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
        quotas=user.quotas,
        usage_stats=usage_stats,
    )


# --- User Management Endpoints ---


@router.get("/users/stats", response_model=AdminUserStats)
async def get_user_stats(
    current_user: AdminUserDep,
    auth_service: AuthServiceDep,
) -> AdminUserStats:
    """Get user statistics for the admin dashboard."""
    all_users = auth_service.store.list_all()

    total_users = len(all_users)
    active_users = 0
    suspended_users = 0
    pending_users = 0
    users_by_role: dict[str, int] = {"admin": 0, "developer": 0, "end_user": 0}

    for user in all_users:
        if user.status == UserStatus.ACTIVE:
            active_users += 1
        elif user.status == UserStatus.SUSPENDED:
            suspended_users += 1
        elif user.status == UserStatus.PENDING:
            pending_users += 1

        role_key = user.role.value
        users_by_role[role_key] = users_by_role.get(role_key, 0) + 1

    return AdminUserStats(
        total_users=total_users,
        active_users=active_users,
        suspended_users=suspended_users,
        pending_users=pending_users,
        users_by_role=users_by_role,
    )


@router.get("/users", response_model=AdminUserListResponse)
async def list_users(
    current_user: AdminUserDep,
    auth_service: AuthServiceDep,
    run_service: RunServiceDep,
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    search: str | None = Query(None),
    role: UserRole | None = Query(None),
    status: UserStatus | None = Query(None),
    sort_by: str = Query("createdAt", alias="sortBy"),
    sort_order: str = Query("desc", alias="sortOrder"),
) -> AdminUserListResponse:
    """List all users with pagination and filtering."""
    all_users = auth_service.store.list_all()

    # Apply filters
    filtered_users = all_users
    if search:
        search_lower = search.lower()
        filtered_users = [
            u
            for u in filtered_users
            if search_lower in u.email.lower()
            or search_lower in u.display_name.lower()
        ]

    if role:
        filtered_users = [u for u in filtered_users if u.role == role]

    if status:
        filtered_users = [u for u in filtered_users if u.status == status]

    # Sort
    sort_key_map = {
        "createdAt": lambda u: u.created_at or datetime.min,
        "email": lambda u: u.email.lower(),
        "displayName": lambda u: u.display_name.lower(),
        "lastLoginAt": lambda u: u.last_login_at or datetime.min,
    }
    sort_key = sort_key_map.get(sort_by, sort_key_map["createdAt"])
    filtered_users.sort(key=sort_key, reverse=(sort_order == "desc"))

    # Paginate
    total = len(filtered_users)
    total_pages = (total + limit - 1) // limit
    start = (page - 1) * limit
    end = start + limit
    page_users = filtered_users[start:end]

    # Convert to AdminUser
    admin_users = [_user_to_admin_user(u, run_service) for u in page_users]

    return AdminUserListResponse(
        users=admin_users,
        total=total,
        page=page,
        limit=limit,
        total_pages=total_pages,
    )


@router.get("/users/{user_id}", response_model=AdminUserResponse)
async def get_user(
    user_id: str,
    current_user: AdminUserDep,
    auth_service: AuthServiceDep,
    run_service: RunServiceDep,
) -> AdminUserResponse:
    """Get a single user by ID."""
    user = auth_service.get_user_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return _user_to_admin_user(user, run_service)


@router.patch("/users/{user_id}", response_model=AdminUserResponse)
async def update_user(
    user_id: str,
    update: UpdateUserRequest,
    current_user: AdminUserDep,
    auth_service: AuthServiceDep,
    run_service: RunServiceDep,
) -> AdminUserResponse:
    """Update user details."""
    user = auth_service.get_user_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Prevent self-demotion
    if user_id == current_user.id and update.role and update.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot change your own admin role",
        )

    # Apply updates
    if update.display_name is not None:
        user.display_name = update.display_name
    if update.role is not None:
        user.role = update.role
    if update.status is not None:
        user.status = update.status
    if update.quotas is not None:
        user.quotas = update.quotas

    user.updated_at = datetime.utcnow()
    auth_service.store.update(user_id, user)

    return _user_to_admin_user(user, run_service)


@router.post("/users/{user_id}/suspend", response_model=AdminUserResponse)
async def suspend_user(
    user_id: str,
    current_user: AdminUserDep,
    auth_service: AuthServiceDep,
    run_service: RunServiceDep,
    reason: str | None = None,
) -> AdminUserResponse:
    """Suspend a user account."""
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot suspend your own account",
        )

    user = auth_service.get_user_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    user.status = UserStatus.SUSPENDED
    user.updated_at = datetime.utcnow()
    auth_service.store.update(user_id, user)

    return _user_to_admin_user(user, run_service)


@router.post("/users/{user_id}/activate", response_model=AdminUserResponse)
async def activate_user(
    user_id: str,
    current_user: AdminUserDep,
    auth_service: AuthServiceDep,
    run_service: RunServiceDep,
) -> AdminUserResponse:
    """Activate a suspended or pending user account."""
    user = auth_service.get_user_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    user.status = UserStatus.ACTIVE
    user.updated_at = datetime.utcnow()
    auth_service.store.update(user_id, user)

    return _user_to_admin_user(user, run_service)


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: str,
    current_user: AdminUserDep,
    auth_service: AuthServiceDep,
) -> None:
    """Delete a user (soft delete by setting status to suspended)."""
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own account",
        )

    user = auth_service.get_user_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Soft delete - just mark as suspended
    user.status = UserStatus.SUSPENDED
    user.updated_at = datetime.utcnow()
    auth_service.store.update(user_id, user)


# --- Quota Monitoring Endpoints ---


@router.get("/quotas/usage", response_model=QuotaUsageStats)
async def get_quota_usage_stats(
    current_user: AdminUserDep,
    auth_service: AuthServiceDep,
    quota_service: QuotaServiceDep,
    run_service: RunServiceDep,
) -> QuotaUsageStats:
    """Get system-wide quota usage statistics."""
    all_users = auth_service.store.list_all()
    active_users = [u for u in all_users if u.status == UserStatus.ACTIVE]

    users_at_limit = 0
    total_cpu_hours = 0.0
    total_runs_today = 0
    user_cpu_usage: list[dict[str, Any]] = []
    user_runs_usage: list[dict[str, Any]] = []

    for user in active_users:
        usage = quota_service.get_user_usage(user.id)

        # Track CPU hours
        total_cpu_hours += usage.cpu_hours_month
        user_cpu_usage.append({
            "userId": user.id,
            "displayName": user.display_name,
            "email": user.email,
            "cpuHoursUsed": round(usage.cpu_hours_month, 2),
            "cpuHoursLimit": user.quotas.max_cpu_hours_per_month,
            "percentUsed": round(
                (usage.cpu_hours_month / user.quotas.max_cpu_hours_per_month) * 100
                if user.quotas.max_cpu_hours_per_month > 0
                else 0,
                1,
            ),
        })

        # Track daily runs
        total_runs_today += usage.runs_today
        user_runs_usage.append({
            "userId": user.id,
            "displayName": user.display_name,
            "email": user.email,
            "runsToday": usage.runs_today,
            "runsLimit": user.quotas.max_runs_per_day,
            "percentUsed": round(
                (usage.runs_today / user.quotas.max_runs_per_day) * 100
                if user.quotas.max_runs_per_day > 0
                else 0,
                1,
            ),
        })

        # Check if user is at any limit
        if (
            usage.runs_today >= user.quotas.max_runs_per_day
            or usage.cpu_hours_month >= user.quotas.max_cpu_hours_per_month
        ):
            users_at_limit += 1

    # Sort and get top users
    user_cpu_usage.sort(key=lambda x: x["cpuHoursUsed"], reverse=True)
    user_runs_usage.sort(key=lambda x: x["runsToday"], reverse=True)

    return QuotaUsageStats(
        total_users=len(active_users),
        users_at_limit=users_at_limit,
        total_cpu_hours_used=round(total_cpu_hours, 2),
        total_runs_today=total_runs_today,
        top_users_by_cpu=user_cpu_usage[:10],
        top_users_by_runs=user_runs_usage[:10],
    )


@router.get("/quotas/user/{user_id}")
async def get_user_quota_details(
    user_id: str,
    current_user: AdminUserDep,
    auth_service: AuthServiceDep,
    quota_service: QuotaServiceDep,
    run_service: RunServiceDep,
) -> dict[str, Any]:
    """Get detailed quota information for a specific user."""
    user = auth_service.get_user_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    quota_status = quota_service.get_quota_status(
        user_id=user.id,
        user_quotas=user.quotas,
        run_service=run_service,
    )

    return {
        "user": {
            "id": user.id,
            "displayName": user.display_name,
            "email": user.email,
            "role": user.role.value,
        },
        "quotas": quota_status,
    }
