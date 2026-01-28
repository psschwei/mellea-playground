"""Share link models for resource sharing."""

from datetime import datetime
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from mellea_api.models.common import Permission
from mellea_api.models.permission import ResourceType


class ShareLink(BaseModel):
    """A shareable link for accessing a resource.

    Share links provide time-limited access to resources without
    requiring the recipient to have an account or explicit permission.

    Attributes:
        id: Unique identifier for the share link
        token: Secret token for accessing the resource (used in URLs)
        resource_id: ID of the shared resource
        resource_type: Type of the shared resource
        permission: Permission level granted by this link
        created_by: User ID of who created the link
        created_at: When the link was created
        expires_at: When the link expires (None for no expiration)
        label: Optional descriptive label for the link
        access_count: Number of times the link has been used
        last_accessed_at: Last time the link was used
        is_active: Whether the link is active (can be deactivated)
    """

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(default_factory=lambda: str(uuid4()))
    token: str = Field(default_factory=lambda: str(uuid4()))
    resource_id: str = Field(validation_alias="resourceId", serialization_alias="resourceId")
    resource_type: ResourceType = Field(
        validation_alias="resourceType", serialization_alias="resourceType"
    )
    permission: Permission = Permission.VIEW
    created_by: str = Field(validation_alias="createdBy", serialization_alias="createdBy")
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        validation_alias="createdAt",
        serialization_alias="createdAt",
    )
    expires_at: datetime | None = Field(
        default=None,
        validation_alias="expiresAt",
        serialization_alias="expiresAt",
    )
    label: str | None = None
    access_count: int = Field(
        default=0,
        validation_alias="accessCount",
        serialization_alias="accessCount",
    )
    last_accessed_at: datetime | None = Field(
        default=None,
        validation_alias="lastAccessedAt",
        serialization_alias="lastAccessedAt",
    )
    is_active: bool = Field(
        default=True,
        validation_alias="isActive",
        serialization_alias="isActive",
    )

    def is_expired(self) -> bool:
        """Check if the share link has expired."""
        if self.expires_at is None:
            return False
        return datetime.utcnow() > self.expires_at

    def is_valid(self) -> bool:
        """Check if the share link is valid (active and not expired)."""
        return self.is_active and not self.is_expired()


class CreateShareLinkRequest(BaseModel):
    """Request to create a new share link."""

    model_config = ConfigDict(populate_by_name=True)

    resource_id: str = Field(validation_alias="resourceId", serialization_alias="resourceId")
    resource_type: ResourceType = Field(
        validation_alias="resourceType", serialization_alias="resourceType"
    )
    permission: Permission = Permission.VIEW
    expires_in_hours: int | None = Field(
        default=None,
        validation_alias="expiresInHours",
        serialization_alias="expiresInHours",
        ge=1,
        le=8760,  # Max 1 year
    )
    label: str | None = None


class ShareLinkResponse(BaseModel):
    """Response containing share link details."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    token: str
    resource_id: str = Field(serialization_alias="resourceId")
    resource_type: ResourceType = Field(serialization_alias="resourceType")
    permission: Permission
    created_by: str = Field(serialization_alias="createdBy")
    created_at: datetime = Field(serialization_alias="createdAt")
    expires_at: datetime | None = Field(serialization_alias="expiresAt")
    label: str | None
    access_count: int = Field(serialization_alias="accessCount")
    last_accessed_at: datetime | None = Field(serialization_alias="lastAccessedAt")
    is_active: bool = Field(serialization_alias="isActive")
    share_url: str = Field(serialization_alias="shareUrl")

    @classmethod
    def from_share_link(cls, link: ShareLink, base_url: str = "") -> "ShareLinkResponse":
        """Create response from ShareLink model."""
        share_url = f"{base_url}/shared/{link.token}" if base_url else f"/shared/{link.token}"
        return cls(
            id=link.id,
            token=link.token,
            resource_id=link.resource_id,
            resource_type=link.resource_type,
            permission=link.permission,
            created_by=link.created_by,
            created_at=link.created_at,
            expires_at=link.expires_at,
            label=link.label,
            access_count=link.access_count,
            last_accessed_at=link.last_accessed_at,
            is_active=link.is_active,
            share_url=share_url,
        )


class ShareLinkListResponse(BaseModel):
    """Response containing a list of share links."""

    model_config = ConfigDict(populate_by_name=True)

    links: list[ShareLinkResponse]
    total: int


class ShareWithUserRequest(BaseModel):
    """Request to share a resource with a specific user."""

    model_config = ConfigDict(populate_by_name=True)

    resource_id: str = Field(validation_alias="resourceId", serialization_alias="resourceId")
    resource_type: ResourceType = Field(
        validation_alias="resourceType", serialization_alias="resourceType"
    )
    user_id: str = Field(validation_alias="userId", serialization_alias="userId")
    permission: Permission = Permission.VIEW


class SharedWithMeItem(BaseModel):
    """An item shared with the current user."""

    model_config = ConfigDict(populate_by_name=True)

    resource_id: str = Field(serialization_alias="resourceId")
    resource_type: ResourceType = Field(serialization_alias="resourceType")
    resource_name: str = Field(serialization_alias="resourceName")
    permission: Permission
    shared_by: str = Field(serialization_alias="sharedBy")
    shared_by_name: str = Field(serialization_alias="sharedByName")
    shared_at: datetime = Field(serialization_alias="sharedAt")


class SharedWithMeResponse(BaseModel):
    """Response containing resources shared with the current user."""

    model_config = ConfigDict(populate_by_name=True)

    items: list[SharedWithMeItem]
    total: int
