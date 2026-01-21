"""Permission and Access Control models."""

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from mellea_api.models.common import AccessType, Permission


class ResourceType(str, Enum):
    """Type of resource for permission checks."""

    PROGRAM = "program"
    MODEL = "model"
    COMPOSITION = "composition"


class AccessControlEntry(BaseModel):
    """An entry in an access control list.

    Represents a permission grant from a resource owner to a principal
    (user, group, or organization).

    Attributes:
        id: Unique identifier for this ACL entry
        resource_id: ID of the resource being protected
        resource_type: Type of the resource (program, model, composition)
        principal_type: Type of principal (user, group, org)
        principal_id: ID of the principal being granted access
        permission: Permission level granted
        granted_by: User ID of who granted this permission
        granted_at: When the permission was granted
    """

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(default_factory=lambda: str(uuid4()))
    resource_id: str = Field(validation_alias="resourceId", serialization_alias="resourceId")
    resource_type: ResourceType = Field(
        validation_alias="resourceType", serialization_alias="resourceType"
    )
    principal_type: AccessType = Field(
        validation_alias="principalType", serialization_alias="principalType"
    )
    principal_id: str = Field(validation_alias="principalId", serialization_alias="principalId")
    permission: Permission
    granted_by: str = Field(validation_alias="grantedBy", serialization_alias="grantedBy")
    granted_at: datetime = Field(
        default_factory=datetime.utcnow,
        validation_alias="grantedAt",
        serialization_alias="grantedAt",
    )

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)


class PermissionCheck(BaseModel):
    """Result of a permission check.

    Attributes:
        allowed: Whether access is allowed
        reason: Explanation of why access was allowed or denied
        effective_permission: The permission level that applies (if allowed)
    """

    allowed: bool
    reason: str
    effective_permission: Permission | None = Field(
        default=None, validation_alias="effectivePermission", serialization_alias="effectivePermission"
    )

    model_config = ConfigDict(populate_by_name=True)


# Permission hierarchy: higher permissions include lower ones
PERMISSION_HIERARCHY: dict[Permission, int] = {
    Permission.VIEW: 1,
    Permission.RUN: 2,
    Permission.EDIT: 3,
}


def permission_includes(granted: Permission, required: Permission) -> bool:
    """Check if a granted permission includes the required permission.

    Higher permissions include lower ones:
    - EDIT includes RUN and VIEW
    - RUN includes VIEW
    - VIEW is the lowest level

    Args:
        granted: The permission that was granted
        required: The permission being checked

    Returns:
        True if the granted permission is sufficient
    """
    return PERMISSION_HIERARCHY.get(granted, 0) >= PERMISSION_HIERARCHY.get(required, 0)
