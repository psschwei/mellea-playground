"""PermissionService for access control and ACL checks."""

from __future__ import annotations

import logging
from datetime import datetime
from uuid import uuid4

from mellea_api.core.config import Settings, get_settings
from mellea_api.core.store import JsonStore
from mellea_api.models.assets import AssetMetadata
from mellea_api.models.common import AccessType, Permission, SharingMode
from mellea_api.models.permission import (
    AccessControlEntry,
    PermissionCheck,
    ResourceType,
    permission_includes,
)
from mellea_api.models.user import User, UserRole

logger = logging.getLogger(__name__)


class PermissionDeniedError(Exception):
    """Raised when a user lacks required permission.

    Attributes:
        message: Human-readable error message
        user_id: ID of the user who was denied
        resource_id: ID of the resource being accessed
        required_permission: Permission that was required
    """

    def __init__(
        self,
        message: str,
        user_id: str,
        resource_id: str,
        required_permission: Permission,
    ):
        super().__init__(message)
        self.user_id = user_id
        self.resource_id = resource_id
        self.required_permission = required_permission


class ResourceNotFoundError(Exception):
    """Raised when a resource cannot be found for permission check."""

    pass


class PermissionService:
    """Service for access control and permission checking.

    Provides methods to check and manage permissions for assets (programs,
    models, compositions). Supports:
    - Ownership-based access (owners have full control)
    - Role-based access (admins have full access to everything)
    - Sharing mode (public assets can be viewed by anyone)
    - Explicit ACL entries (shared_with grants on assets)
    - Stored ACL entries (for additional granular control)

    Example:
        ```python
        service = get_permission_service()

        # Check if user can view an asset
        result = service.check_permission(
            user=current_user,
            resource_id=program_id,
            resource_type=ResourceType.PROGRAM,
            required=Permission.VIEW,
            asset=program,
        )

        if not result.allowed:
            raise HTTPException(status_code=403, detail=result.reason)

        # Grant permission to another user
        service.grant_permission(
            resource_id=program_id,
            resource_type=ResourceType.PROGRAM,
            principal_id=other_user_id,
            principal_type=AccessType.USER,
            permission=Permission.EDIT,
            granted_by=current_user.id,
        )
        ```
    """

    def __init__(self, settings: Settings | None = None) -> None:
        """Initialize the PermissionService.

        Args:
            settings: Application settings (uses default if not provided)
        """
        self.settings = settings or get_settings()
        self._acl_store: JsonStore[AccessControlEntry] | None = None

    @property
    def acl_store(self) -> JsonStore[AccessControlEntry]:
        """Get the ACL store, initializing if needed."""
        if self._acl_store is None:
            file_path = self.settings.data_dir / "metadata" / "acl.json"
            self._acl_store = JsonStore[AccessControlEntry](
                file_path=file_path,
                collection_key="entries",
                model_class=AccessControlEntry,
            )
        return self._acl_store

    def _is_admin(self, user: User) -> bool:
        """Check if user has admin role."""
        return user.role == UserRole.ADMIN

    def _is_owner(self, user: User, asset: AssetMetadata) -> bool:
        """Check if user is the owner of the asset."""
        return asset.owner == user.id

    def _get_shared_access_permission(
        self,
        user: User,
        asset: AssetMetadata,
    ) -> Permission | None:
        """Get the permission level from asset's shared_with list.

        Checks if user has been explicitly granted access via the
        asset's shared_with list.

        Args:
            user: User to check
            asset: Asset with shared_with grants

        Returns:
            Permission level if found, None otherwise
        """
        for access in asset.shared_with:
            # Check direct user grant
            if access.type == AccessType.USER and access.id == user.id:
                return access.permission

            # Future: could check GROUP and ORG memberships here
            # if access.type == AccessType.GROUP:
            #     if user_in_group(user.id, access.id):
            #         return access.permission

        return None

    def _get_acl_permission(
        self,
        user: User,
        resource_id: str,
        resource_type: ResourceType,
    ) -> Permission | None:
        """Get the permission level from stored ACL entries.

        Args:
            user: User to check
            resource_id: ID of the resource
            resource_type: Type of resource

        Returns:
            Highest permission level found, None if no entries
        """
        # Find all ACL entries for this resource and user
        entries = self.acl_store.find(
            lambda e: (
                e.resource_id == resource_id
                and e.resource_type == resource_type
                and e.principal_type == AccessType.USER
                and e.principal_id == user.id
            )
        )

        if not entries:
            return None

        # Return the highest permission level found
        from mellea_api.models.permission import PERMISSION_HIERARCHY

        highest_perm = None
        highest_level = 0

        for entry in entries:
            level = PERMISSION_HIERARCHY.get(entry.permission, 0)
            if level > highest_level:
                highest_level = level
                highest_perm = entry.permission

        return highest_perm

    def check_permission(
        self,
        user: User | None,
        resource_id: str,
        resource_type: ResourceType,
        required: Permission,
        asset: AssetMetadata | None = None,
    ) -> PermissionCheck:
        """Check if a user has permission to access a resource.

        Permission is granted based on (in order of precedence):
        1. Admin role - admins have full access to everything
        2. Ownership - owners have full control over their assets
        3. Public sharing - public assets can be viewed by anyone
        4. Explicit ACL - shared_with grants on the asset
        5. Stored ACL - additional ACL entries in storage

        Args:
            user: User requesting access (None for anonymous)
            resource_id: ID of the resource being accessed
            resource_type: Type of resource (program, model, composition)
            required: Permission level required
            asset: Asset metadata (if already loaded, for efficiency)

        Returns:
            PermissionCheck with allowed status and reason
        """
        # Anonymous users can only view public assets
        if user is None:
            if (
                asset
                and asset.sharing == SharingMode.PUBLIC
                and required == Permission.VIEW
            ):
                return PermissionCheck(
                    allowed=True,
                    reason="Public asset is viewable by anyone",
                    effective_permission=Permission.VIEW,
                )
            return PermissionCheck(
                allowed=False,
                reason="Authentication required",
                effective_permission=None,
            )

        # Admins have full access
        if self._is_admin(user):
            return PermissionCheck(
                allowed=True,
                reason="Admin users have full access",
                effective_permission=Permission.EDIT,
            )

        # Need asset metadata for further checks
        if asset is None:
            return PermissionCheck(
                allowed=False,
                reason="Resource not found",
                effective_permission=None,
            )

        # Owners have full access
        if self._is_owner(user, asset):
            return PermissionCheck(
                allowed=True,
                reason="Owner has full access",
                effective_permission=Permission.EDIT,
            )

        # Check public access (view only)
        if (
            asset.sharing == SharingMode.PUBLIC
            and permission_includes(Permission.VIEW, required)
        ):
            return PermissionCheck(
                allowed=True,
                reason="Public asset is viewable by anyone",
                effective_permission=Permission.VIEW,
            )

        # Check shared access on asset
        shared_perm = self._get_shared_access_permission(user, asset)
        if shared_perm and permission_includes(shared_perm, required):
            return PermissionCheck(
                allowed=True,
                reason=f"Granted {shared_perm.value} permission via sharing",
                effective_permission=shared_perm,
            )

        # Check stored ACL entries
        acl_perm = self._get_acl_permission(user, resource_id, resource_type)
        if acl_perm and permission_includes(acl_perm, required):
            return PermissionCheck(
                allowed=True,
                reason=f"Granted {acl_perm.value} permission via ACL",
                effective_permission=acl_perm,
            )

        # No permission found
        return PermissionCheck(
            allowed=False,
            reason=f"User lacks required {required.value} permission",
            effective_permission=shared_perm or acl_perm,
        )

    def require_permission(
        self,
        user: User | None,
        resource_id: str,
        resource_type: ResourceType,
        required: Permission,
        asset: AssetMetadata | None = None,
    ) -> None:
        """Require a permission, raising an exception if not granted.

        This is a convenience method that calls check_permission and
        raises PermissionDeniedError if access is not allowed.

        Args:
            user: User requesting access
            resource_id: ID of the resource being accessed
            resource_type: Type of resource
            required: Permission level required
            asset: Asset metadata (if already loaded)

        Raises:
            PermissionDeniedError: If permission is not granted
        """
        result = self.check_permission(
            user=user,
            resource_id=resource_id,
            resource_type=resource_type,
            required=required,
            asset=asset,
        )

        if not result.allowed:
            user_id = user.id if user else "anonymous"
            raise PermissionDeniedError(
                message=result.reason,
                user_id=user_id,
                resource_id=resource_id,
                required_permission=required,
            )

    def grant_permission(
        self,
        resource_id: str,
        resource_type: ResourceType,
        principal_id: str,
        principal_type: AccessType,
        permission: Permission,
        granted_by: str,
    ) -> AccessControlEntry:
        """Grant a permission to a principal.

        Creates an ACL entry granting access. If the principal already
        has an entry for this resource, updates the permission level.

        Args:
            resource_id: ID of the resource
            resource_type: Type of resource
            principal_id: ID of the user/group/org receiving permission
            principal_type: Type of principal
            permission: Permission level to grant
            granted_by: User ID of who is granting permission

        Returns:
            The created or updated ACL entry
        """
        # Check for existing entry
        existing = self.acl_store.find(
            lambda e: (
                e.resource_id == resource_id
                and e.resource_type == resource_type
                and e.principal_id == principal_id
                and e.principal_type == principal_type
            )
        )

        if existing:
            # Update existing entry
            entry = existing[0]
            entry.permission = permission
            entry.granted_by = granted_by
            entry.granted_at = datetime.utcnow()
            self.acl_store.update(entry.id, entry)
            logger.info(
                f"Updated permission: {principal_type.value}:{principal_id} "
                f"-> {permission.value} on {resource_type.value}:{resource_id}"
            )
            return entry

        # Create new entry
        entry = AccessControlEntry(
            id=str(uuid4()),
            resource_id=resource_id,
            resource_type=resource_type,
            principal_type=principal_type,
            principal_id=principal_id,
            permission=permission,
            granted_by=granted_by,
        )
        self.acl_store.create(entry)
        logger.info(
            f"Granted permission: {principal_type.value}:{principal_id} "
            f"-> {permission.value} on {resource_type.value}:{resource_id}"
        )
        return entry

    def revoke_permission(
        self,
        resource_id: str,
        resource_type: ResourceType,
        principal_id: str,
        principal_type: AccessType,
    ) -> bool:
        """Revoke a permission from a principal.

        Removes the ACL entry for the given principal and resource.

        Args:
            resource_id: ID of the resource
            resource_type: Type of resource
            principal_id: ID of the user/group/org losing permission
            principal_type: Type of principal

        Returns:
            True if an entry was removed, False if not found
        """
        entries = self.acl_store.find(
            lambda e: (
                e.resource_id == resource_id
                and e.resource_type == resource_type
                and e.principal_id == principal_id
                and e.principal_type == principal_type
            )
        )

        if not entries:
            return False

        for entry in entries:
            self.acl_store.delete(entry.id)

        logger.info(
            f"Revoked permission: {principal_type.value}:{principal_id} "
            f"from {resource_type.value}:{resource_id}"
        )
        return True

    def list_resource_permissions(
        self,
        resource_id: str,
        resource_type: ResourceType,
    ) -> list[AccessControlEntry]:
        """List all ACL entries for a resource.

        Args:
            resource_id: ID of the resource
            resource_type: Type of resource

        Returns:
            List of ACL entries
        """
        return self.acl_store.find(
            lambda e: e.resource_id == resource_id and e.resource_type == resource_type
        )

    def list_user_permissions(
        self,
        user_id: str,
    ) -> list[AccessControlEntry]:
        """List all ACL entries for a user.

        Args:
            user_id: User ID

        Returns:
            List of ACL entries where user is the principal
        """
        return self.acl_store.find(
            lambda e: e.principal_type == AccessType.USER and e.principal_id == user_id
        )

    def delete_resource_permissions(
        self,
        resource_id: str,
        resource_type: ResourceType,
    ) -> int:
        """Delete all ACL entries for a resource.

        Used when a resource is deleted.

        Args:
            resource_id: ID of the resource
            resource_type: Type of resource

        Returns:
            Number of entries deleted
        """
        entries = self.list_resource_permissions(resource_id, resource_type)
        for entry in entries:
            self.acl_store.delete(entry.id)

        if entries:
            logger.info(
                f"Deleted {len(entries)} ACL entries for "
                f"{resource_type.value}:{resource_id}"
            )

        return len(entries)

    def can_view(
        self,
        user: User | None,
        asset: AssetMetadata,
        resource_type: ResourceType,
    ) -> bool:
        """Check if user can view an asset.

        Convenience method for common VIEW permission check.

        Args:
            user: User to check
            asset: Asset to check access for
            resource_type: Type of asset

        Returns:
            True if user can view
        """
        result = self.check_permission(
            user=user,
            resource_id=asset.id,
            resource_type=resource_type,
            required=Permission.VIEW,
            asset=asset,
        )
        return result.allowed

    def can_run(
        self,
        user: User | None,
        asset: AssetMetadata,
        resource_type: ResourceType,
    ) -> bool:
        """Check if user can run/execute an asset.

        Convenience method for common RUN permission check.

        Args:
            user: User to check
            asset: Asset to check access for
            resource_type: Type of asset

        Returns:
            True if user can run
        """
        result = self.check_permission(
            user=user,
            resource_id=asset.id,
            resource_type=resource_type,
            required=Permission.RUN,
            asset=asset,
        )
        return result.allowed

    def can_edit(
        self,
        user: User | None,
        asset: AssetMetadata,
        resource_type: ResourceType,
    ) -> bool:
        """Check if user can edit an asset.

        Convenience method for common EDIT permission check.

        Args:
            user: User to check
            asset: Asset to check access for
            resource_type: Type of asset

        Returns:
            True if user can edit
        """
        result = self.check_permission(
            user=user,
            resource_id=asset.id,
            resource_type=resource_type,
            required=Permission.EDIT,
            asset=asset,
        )
        return result.allowed

    def get_effective_permission(
        self,
        user: User | None,
        asset: AssetMetadata,
        resource_type: ResourceType,
    ) -> Permission | None:
        """Get the highest permission level a user has on an asset.

        Args:
            user: User to check
            asset: Asset to check
            resource_type: Type of asset

        Returns:
            Highest permission level, or None if no access
        """
        # Try each permission level from highest to lowest
        for perm in [Permission.EDIT, Permission.RUN, Permission.VIEW]:
            result = self.check_permission(
                user=user,
                resource_id=asset.id,
                resource_type=resource_type,
                required=perm,
                asset=asset,
            )
            if result.allowed:
                return perm

        return None


# Global service instance
_permission_service: PermissionService | None = None


def get_permission_service() -> PermissionService:
    """Get the global PermissionService instance."""
    global _permission_service
    if _permission_service is None:
        _permission_service = PermissionService()
    return _permission_service
