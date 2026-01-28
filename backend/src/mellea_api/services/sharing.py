"""SharingService for managing share links and user sharing."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, cast

from mellea_api.core.config import Settings, get_settings
from mellea_api.core.store import JsonStore
from mellea_api.models.assets import CompositionAsset, ModelAsset, ProgramAsset, SharedAccess
from mellea_api.models.common import AccessType, Permission, SharingMode
from mellea_api.models.permission import ResourceType
from mellea_api.models.sharing import ShareLink
from mellea_api.models.user import User

# Type alias for any asset type
AssetType = ProgramAsset | ModelAsset | CompositionAsset | None

logger = logging.getLogger(__name__)


class ShareLinkNotFoundError(Exception):
    """Raised when a share link is not found."""

    pass


class ShareLinkExpiredError(Exception):
    """Raised when a share link has expired."""

    pass


class ShareLinkInactiveError(Exception):
    """Raised when a share link is inactive."""

    pass


class SharingService:
    """Service for managing resource sharing.

    Provides functionality for:
    - Creating and managing share links for anonymous access
    - Sharing resources with specific users
    - Tracking share link usage
    - Validating share link access

    Example:
        ```python
        service = get_sharing_service()

        # Create a share link
        link = service.create_share_link(
            resource_id="prog-123",
            resource_type=ResourceType.PROGRAM,
            permission=Permission.VIEW,
            created_by="user-456",
            expires_in_hours=24,
        )

        # Verify access via share link
        link = service.verify_share_link_access(token=link.token)

        # Share with a specific user
        service.share_with_user(
            resource_id="prog-123",
            resource_type=ResourceType.PROGRAM,
            user_id="user-789",
            permission=Permission.RUN,
            shared_by="user-456",
        )
        ```
    """

    def __init__(self, settings: Settings | None = None) -> None:
        """Initialize the SharingService.

        Args:
            settings: Application settings (uses default if not provided)
        """
        self.settings = settings or get_settings()
        self._share_link_store: JsonStore[ShareLink] | None = None

    @property
    def share_link_store(self) -> JsonStore[ShareLink]:
        """Get the share link store, initializing if needed."""
        if self._share_link_store is None:
            file_path = self.settings.data_dir / "metadata" / "share_links.json"
            self._share_link_store = JsonStore[ShareLink](
                file_path=file_path,
                collection_key="links",
                model_class=ShareLink,
            )
        return self._share_link_store

    # =========================================================================
    # Share Link Management
    # =========================================================================

    def create_share_link(
        self,
        resource_id: str,
        resource_type: ResourceType,
        permission: Permission,
        created_by: str,
        expires_in_hours: int | None = None,
        label: str | None = None,
    ) -> ShareLink:
        """Create a new share link for a resource.

        Args:
            resource_id: ID of the resource to share
            resource_type: Type of the resource
            permission: Permission level for the link
            created_by: User ID creating the link
            expires_in_hours: Optional expiration time in hours
            label: Optional descriptive label

        Returns:
            The created ShareLink
        """
        expires_at = None
        if expires_in_hours is not None:
            expires_at = datetime.utcnow() + timedelta(hours=expires_in_hours)

        link = ShareLink(
            resource_id=resource_id,
            resource_type=resource_type,
            permission=permission,
            created_by=created_by,
            expires_at=expires_at,
            label=label,
        )

        self.share_link_store.create(link)
        logger.info(
            f"Created share link {link.id} for {resource_type.value}:{resource_id} "
            f"with {permission.value} permission"
        )

        return link

    def get_share_link(self, link_id: str) -> ShareLink | None:
        """Get a share link by ID.

        Args:
            link_id: The share link ID

        Returns:
            The ShareLink if found, None otherwise
        """
        return self.share_link_store.get_by_id(link_id)

    def get_share_link_by_token(self, token: str) -> ShareLink | None:
        """Get a share link by its token.

        Args:
            token: The share link token

        Returns:
            The ShareLink if found, None otherwise
        """
        links = self.share_link_store.find(lambda link: link.token == token)
        return links[0] if links else None

    def verify_share_link_access(self, token: str) -> ShareLink:
        """Verify that a share link token grants access.

        This checks that the link exists, is active, and not expired.
        Also tracks access for analytics.

        Args:
            token: The share link token

        Returns:
            The valid ShareLink

        Raises:
            ShareLinkNotFoundError: If link doesn't exist
            ShareLinkInactiveError: If link is deactivated
            ShareLinkExpiredError: If link has expired
        """
        link = self.get_share_link_by_token(token)

        if link is None:
            raise ShareLinkNotFoundError(f"Share link not found: {token}")

        if not link.is_active:
            raise ShareLinkInactiveError(f"Share link is inactive: {link.id}")

        if link.is_expired():
            raise ShareLinkExpiredError(f"Share link has expired: {link.id}")

        # Track access
        self._track_link_access(link)

        return link

    def _track_link_access(self, link: ShareLink) -> None:
        """Track that a share link was accessed.

        Args:
            link: The ShareLink that was accessed
        """
        link.access_count += 1
        link.last_accessed_at = datetime.utcnow()
        self.share_link_store.update(link.id, link)

    def deactivate_share_link(self, link_id: str) -> ShareLink | None:
        """Deactivate a share link.

        Args:
            link_id: The share link ID

        Returns:
            The updated ShareLink if found, None otherwise
        """
        link = self.get_share_link(link_id)
        if link is None:
            return None

        link.is_active = False
        self.share_link_store.update(link.id, link)
        logger.info(f"Deactivated share link {link_id}")

        return link

    def delete_share_link(self, link_id: str) -> bool:
        """Delete a share link.

        Args:
            link_id: The share link ID

        Returns:
            True if deleted, False if not found
        """
        result = self.share_link_store.delete(link_id)
        if result:
            logger.info(f"Deleted share link {link_id}")
        return result

    def list_share_links_for_resource(
        self,
        resource_id: str,
        resource_type: ResourceType,
        include_inactive: bool = False,
    ) -> list[ShareLink]:
        """List all share links for a resource.

        Args:
            resource_id: ID of the resource
            resource_type: Type of the resource
            include_inactive: Whether to include inactive links

        Returns:
            List of ShareLinks for the resource
        """

        def predicate(link: ShareLink) -> bool:
            matches = link.resource_id == resource_id and link.resource_type == resource_type
            if not include_inactive:
                matches = matches and link.is_active
            return matches

        return self.share_link_store.find(predicate)

    def list_share_links_by_user(
        self,
        user_id: str,
        include_inactive: bool = False,
    ) -> list[ShareLink]:
        """List all share links created by a user.

        Args:
            user_id: ID of the user
            include_inactive: Whether to include inactive links

        Returns:
            List of ShareLinks created by the user
        """

        def predicate(link: ShareLink) -> bool:
            matches = link.created_by == user_id
            if not include_inactive:
                matches = matches and link.is_active
            return matches

        return self.share_link_store.find(predicate)

    def delete_share_links_for_resource(
        self,
        resource_id: str,
        resource_type: ResourceType,
    ) -> int:
        """Delete all share links for a resource.

        Used when a resource is deleted.

        Args:
            resource_id: ID of the resource
            resource_type: Type of the resource

        Returns:
            Number of links deleted
        """
        links = self.list_share_links_for_resource(
            resource_id, resource_type, include_inactive=True
        )

        for link in links:
            self.share_link_store.delete(link.id)

        if links:
            logger.info(
                f"Deleted {len(links)} share links for {resource_type.value}:{resource_id}"
            )

        return len(links)

    # =========================================================================
    # User Sharing
    # =========================================================================

    def share_with_user(
        self,
        resource_id: str,
        resource_type: ResourceType,
        user_id: str,
        permission: Permission,
        shared_by: str,
    ) -> SharedAccess:
        """Share a resource with a specific user.

        This updates the asset's shared_with list to include the user.

        Args:
            resource_id: ID of the resource to share
            resource_type: Type of the resource
            user_id: ID of the user to share with
            permission: Permission level to grant
            shared_by: User ID doing the sharing

        Returns:
            The SharedAccess entry
        """
        from mellea_api.services.assets import get_asset_service

        asset_service = get_asset_service()

        # Get the asset
        asset: AssetType = None
        if resource_type == ResourceType.PROGRAM:
            asset = asset_service.get_program(resource_id)
        elif resource_type == ResourceType.MODEL:
            asset = asset_service.get_model(resource_id)
        elif resource_type == ResourceType.COMPOSITION:
            asset = asset_service.get_composition(resource_id)

        if asset is None:
            raise ValueError(f"Resource not found: {resource_type.value}:{resource_id}")

        # Get the metadata (asset might be the metadata itself or have a .meta attribute)
        meta = asset.meta if hasattr(asset, "meta") else asset

        # Check if user already has access
        existing_access = None
        for access in meta.shared_with:
            if access.type == AccessType.USER and access.id == user_id:
                existing_access = access
                break

        if existing_access:
            # Update existing permission
            existing_access.permission = permission
        else:
            # Add new access
            new_access = SharedAccess(
                type=AccessType.USER,
                id=user_id,
                permission=permission,
            )
            meta.shared_with.append(new_access)
            existing_access = new_access

        # Update sharing mode if needed
        if meta.sharing == SharingMode.PRIVATE:
            meta.sharing = SharingMode.SHARED

        # Save the asset
        if resource_type == ResourceType.PROGRAM:
            asset_service.update_program(resource_id, cast(ProgramAsset, asset))
        elif resource_type == ResourceType.MODEL:
            asset_service.update_model(resource_id, cast(ModelAsset, asset))
        elif resource_type == ResourceType.COMPOSITION:
            asset_service.update_composition(resource_id, cast(CompositionAsset, asset))

        logger.info(
            f"Shared {resource_type.value}:{resource_id} with user {user_id} "
            f"({permission.value}) by {shared_by}"
        )

        return existing_access

    def revoke_user_access(
        self,
        resource_id: str,
        resource_type: ResourceType,
        user_id: str,
    ) -> bool:
        """Revoke a user's access to a resource.

        Args:
            resource_id: ID of the resource
            resource_type: Type of the resource
            user_id: ID of the user to revoke

        Returns:
            True if access was revoked, False if user didn't have access
        """
        from mellea_api.services.assets import get_asset_service

        asset_service = get_asset_service()

        # Get the asset
        asset: AssetType = None
        if resource_type == ResourceType.PROGRAM:
            asset = asset_service.get_program(resource_id)
        elif resource_type == ResourceType.MODEL:
            asset = asset_service.get_model(resource_id)
        elif resource_type == ResourceType.COMPOSITION:
            asset = asset_service.get_composition(resource_id)

        if asset is None:
            return False

        # Get the metadata
        meta = asset.meta if hasattr(asset, "meta") else asset

        # Find and remove the user's access
        original_len = len(meta.shared_with)
        meta.shared_with = [
            access
            for access in meta.shared_with
            if not (access.type == AccessType.USER and access.id == user_id)
        ]

        if len(meta.shared_with) == original_len:
            return False

        # Update sharing mode if no more shared users
        if not meta.shared_with and meta.sharing == SharingMode.SHARED:
            meta.sharing = SharingMode.PRIVATE

        # Save the asset
        if resource_type == ResourceType.PROGRAM:
            asset_service.update_program(resource_id, cast(ProgramAsset, asset))
        elif resource_type == ResourceType.MODEL:
            asset_service.update_model(resource_id, cast(ModelAsset, asset))
        elif resource_type == ResourceType.COMPOSITION:
            asset_service.update_composition(resource_id, cast(CompositionAsset, asset))

        logger.info(f"Revoked user {user_id} access from {resource_type.value}:{resource_id}")

        return True

    def get_shared_users(
        self,
        resource_id: str,
        resource_type: ResourceType,
    ) -> list[SharedAccess]:
        """Get list of users a resource is shared with.

        Args:
            resource_id: ID of the resource
            resource_type: Type of the resource

        Returns:
            List of SharedAccess entries for users
        """
        from mellea_api.services.assets import get_asset_service

        asset_service = get_asset_service()

        # Get the asset
        asset: AssetType = None
        if resource_type == ResourceType.PROGRAM:
            asset = asset_service.get_program(resource_id)
        elif resource_type == ResourceType.MODEL:
            asset = asset_service.get_model(resource_id)
        elif resource_type == ResourceType.COMPOSITION:
            asset = asset_service.get_composition(resource_id)

        if asset is None:
            return []

        # Get the metadata
        meta = asset.meta if hasattr(asset, "meta") else asset

        # Return only USER type access entries
        return [access for access in meta.shared_with if access.type == AccessType.USER]

    def get_resources_shared_with_user(
        self,
        user: User,
    ) -> list[dict[str, Any]]:
        """Get all resources shared with a user.

        Args:
            user: The user to check

        Returns:
            List of resource info dicts with resource_id, resource_type, and permission
        """
        from mellea_api.services.assets import get_asset_service
        from mellea_api.services.auth import get_auth_service

        asset_service = get_asset_service()
        auth_service = get_auth_service()
        shared_items = []

        # Check programs
        for program in asset_service.list_programs():
            meta = program.meta if hasattr(program, "meta") else program
            for access in meta.shared_with:
                if access.type == AccessType.USER and access.id == user.id:
                    owner = auth_service.get_user_by_id(meta.owner)
                    shared_items.append(
                        {
                            "resource_id": meta.id,
                            "resource_type": ResourceType.PROGRAM,
                            "resource_name": meta.name,
                            "permission": access.permission,
                            "shared_by": meta.owner,
                            "shared_by_name": owner.display_name if owner else "Unknown",
                            "shared_at": meta.updated_at,
                        }
                    )
                    break

        # Check models
        for model in asset_service.list_models():
            meta = model.meta if hasattr(model, "meta") else model
            for access in meta.shared_with:
                if access.type == AccessType.USER and access.id == user.id:
                    owner = auth_service.get_user_by_id(meta.owner)
                    shared_items.append(
                        {
                            "resource_id": meta.id,
                            "resource_type": ResourceType.MODEL,
                            "resource_name": meta.name,
                            "permission": access.permission,
                            "shared_by": meta.owner,
                            "shared_by_name": owner.display_name if owner else "Unknown",
                            "shared_at": meta.updated_at,
                        }
                    )
                    break

        # Check compositions
        for comp in asset_service.list_compositions():
            meta = comp.meta if hasattr(comp, "meta") else comp
            for access in meta.shared_with:
                if access.type == AccessType.USER and access.id == user.id:
                    owner = auth_service.get_user_by_id(meta.owner)
                    shared_items.append(
                        {
                            "resource_id": meta.id,
                            "resource_type": ResourceType.COMPOSITION,
                            "resource_name": meta.name,
                            "permission": access.permission,
                            "shared_by": meta.owner,
                            "shared_by_name": owner.display_name if owner else "Unknown",
                            "shared_at": meta.updated_at,
                        }
                    )
                    break

        return shared_items


# Global service instance
_sharing_service: SharingService | None = None


def get_sharing_service() -> SharingService:
    """Get the global SharingService instance."""
    global _sharing_service
    if _sharing_service is None:
        _sharing_service = SharingService()
    return _sharing_service
