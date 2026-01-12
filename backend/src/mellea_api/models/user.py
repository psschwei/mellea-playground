"""User model and related schemas."""

from datetime import datetime
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, EmailStr, Field


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

    model_config = ConfigDict(populate_by_name=True)

    max_concurrent_runs: int = Field(default=3, serialization_alias="maxConcurrentRuns")
    max_storage_mb: int = Field(default=5000, serialization_alias="maxStorageMB")
    max_cpu_hours_per_month: int = Field(default=100, serialization_alias="maxCpuHoursPerMonth")
    max_runs_per_day: int = Field(default=50, serialization_alias="maxRunsPerDay")


class User(BaseModel):
    """User account model."""

    model_config = ConfigDict(populate_by_name=True)

    # Identity
    id: str = Field(default_factory=generate_uuid)
    email: EmailStr
    username: str | None = None
    display_name: str = Field(serialization_alias="displayName")

    # Profile
    avatar_url: str | None = Field(default=None, serialization_alias="avatarUrl")
    department: str | None = None
    job_title: str | None = Field(default=None, serialization_alias="jobTitle")

    # Authentication
    auth_provider: AuthProvider = Field(default=AuthProvider.LOCAL, serialization_alias="authProvider")
    external_id: str | None = Field(default=None, serialization_alias="externalId")
    password_hash: str | None = Field(default=None, serialization_alias="passwordHash")

    # Authorization
    role: UserRole = UserRole.END_USER
    organization_id: str | None = Field(default=None, serialization_alias="organizationId")

    # State
    status: UserStatus = UserStatus.ACTIVE
    last_login_at: datetime | None = Field(default=None, serialization_alias="lastLoginAt")
    created_at: datetime = Field(default_factory=datetime.utcnow, serialization_alias="createdAt")
    updated_at: datetime = Field(default_factory=datetime.utcnow, serialization_alias="updatedAt")

    # Quotas
    quotas: UserQuotas = Field(default_factory=UserQuotas)


class UserCreate(BaseModel):
    """Schema for creating a new user."""

    model_config = ConfigDict(populate_by_name=True)

    email: EmailStr
    password: str = Field(min_length=8)
    display_name: str = Field(validation_alias="displayName")
    username: str | None = None


class UserLogin(BaseModel):
    """Schema for login request."""

    email: EmailStr
    password: str


class UserPublic(BaseModel):
    """Public user information (no sensitive data)."""

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    id: str
    email: EmailStr
    username: str | None = None
    display_name: str = Field(serialization_alias="displayName")
    avatar_url: str | None = Field(default=None, serialization_alias="avatarUrl")
    role: UserRole
    status: UserStatus


class TokenResponse(BaseModel):
    """Response containing JWT token."""

    model_config = ConfigDict(populate_by_name=True)

    token: str
    expires_at: datetime = Field(serialization_alias="expiresAt")
    user: UserPublic


class AuthConfig(BaseModel):
    """Authentication configuration (public endpoint)."""

    model_config = ConfigDict(populate_by_name=True)

    mode: str
    providers: list[str]
    registration_enabled: bool = Field(serialization_alias="registrationEnabled")
    session_duration_hours: int = Field(serialization_alias="sessionDurationHours")
