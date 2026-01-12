"""User model and related schemas."""

from datetime import datetime
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, EmailStr, Field


def generate_uuid() -> str:
    """Generate a new UUID string."""
    return str(uuid4())


class AuthProvider(str, Enum):
    """Authentication provider types."""

    LOCAL = "local"
    GOOGLE = "google"
    GITHUB = "github"
    OIDC = "oidc"


class UserRole(str, Enum):
    """User role levels with increasing privileges."""

    END_USER = "end_user"
    DEVELOPER = "developer"
    ADMIN = "admin"


class UserStatus(str, Enum):
    """User account status."""

    ACTIVE = "active"
    SUSPENDED = "suspended"
    PENDING = "pending"


class UserQuotas(BaseModel):
    """Resource quotas for a user."""

    max_concurrent_runs: int = Field(default=3, alias="maxConcurrentRuns")
    max_storage_mb: int = Field(default=5000, alias="maxStorageMB")
    max_cpu_hours_per_month: int = Field(default=100, alias="maxCpuHoursPerMonth")
    max_runs_per_day: int = Field(default=50, alias="maxRunsPerDay")

    class Config:
        populate_by_name = True


class User(BaseModel):
    """User account model."""

    # Identity
    id: str = Field(default_factory=generate_uuid)
    email: EmailStr
    username: str | None = None
    display_name: str = Field(alias="displayName")

    # Profile
    avatar_url: str | None = Field(default=None, alias="avatarUrl")
    department: str | None = None
    job_title: str | None = Field(default=None, alias="jobTitle")

    # Authentication
    auth_provider: AuthProvider = Field(default=AuthProvider.LOCAL, alias="authProvider")
    external_id: str | None = Field(default=None, alias="externalId")
    password_hash: str | None = Field(default=None, alias="passwordHash")

    # Authorization
    role: UserRole = UserRole.END_USER
    organization_id: str | None = Field(default=None, alias="organizationId")

    # State
    status: UserStatus = UserStatus.ACTIVE
    last_login_at: datetime | None = Field(default=None, alias="lastLoginAt")
    created_at: datetime = Field(default_factory=datetime.utcnow, alias="createdAt")
    updated_at: datetime = Field(default_factory=datetime.utcnow, alias="updatedAt")

    # Quotas
    quotas: UserQuotas = Field(default_factory=UserQuotas)

    class Config:
        populate_by_name = True


class UserCreate(BaseModel):
    """Schema for creating a new user."""

    email: EmailStr
    password: str = Field(min_length=8)
    display_name: str = Field(alias="displayName")
    username: str | None = None

    class Config:
        populate_by_name = True


class UserLogin(BaseModel):
    """Schema for login request."""

    email: EmailStr
    password: str


class UserPublic(BaseModel):
    """Public user information (no sensitive data)."""

    id: str
    email: EmailStr
    username: str | None = None
    display_name: str = Field(alias="displayName")
    avatar_url: str | None = Field(default=None, alias="avatarUrl")
    role: UserRole
    status: UserStatus

    class Config:
        populate_by_name = True
        from_attributes = True


class TokenResponse(BaseModel):
    """Response containing JWT token."""

    token: str
    expires_at: datetime = Field(alias="expiresAt")
    user: UserPublic

    class Config:
        populate_by_name = True


class AuthConfig(BaseModel):
    """Authentication configuration (public endpoint)."""

    mode: str
    providers: list[str]
    registration_enabled: bool = Field(alias="registrationEnabled")
    session_duration_hours: int = Field(alias="sessionDurationHours")

    class Config:
        populate_by_name = True
