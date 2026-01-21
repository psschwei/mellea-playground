"""Tests for PermissionService."""

from unittest.mock import MagicMock

import pytest

from mellea_api.core.deps import require_permission
from mellea_api.models.assets import AssetMetadata, SharedAccess
from mellea_api.models.common import AccessType, Permission, SharingMode
from mellea_api.models.permission import (
    AccessControlEntry,
    PermissionCheck,
    ResourceType,
    permission_includes,
)
from mellea_api.models.user import User, UserRole, UserStatus
from mellea_api.services.permission import (
    PermissionDeniedError,
    PermissionService,
)


@pytest.fixture
def mock_settings(tmp_path):
    """Create mock settings with a temporary data directory."""
    settings = MagicMock()
    settings.data_dir = tmp_path
    (tmp_path / "metadata").mkdir(parents=True, exist_ok=True)
    return settings


@pytest.fixture
def permission_service(mock_settings):
    """Create a PermissionService with mock settings."""
    return PermissionService(settings=mock_settings)


@pytest.fixture
def admin_user():
    """Create an admin user."""
    return User(
        id="admin-user-id",
        email="admin@example.com",
        display_name="Admin User",
        role=UserRole.ADMIN,
        status=UserStatus.ACTIVE,
    )


@pytest.fixture
def developer_user():
    """Create a developer user."""
    return User(
        id="dev-user-id",
        email="dev@example.com",
        display_name="Developer User",
        role=UserRole.DEVELOPER,
        status=UserStatus.ACTIVE,
    )


@pytest.fixture
def end_user():
    """Create an end user."""
    return User(
        id="end-user-id",
        email="user@example.com",
        display_name="End User",
        role=UserRole.END_USER,
        status=UserStatus.ACTIVE,
    )


@pytest.fixture
def other_user():
    """Create another user for sharing tests."""
    return User(
        id="other-user-id",
        email="other@example.com",
        display_name="Other User",
        role=UserRole.END_USER,
        status=UserStatus.ACTIVE,
    )


@pytest.fixture
def private_asset(developer_user):
    """Create a private asset owned by developer_user."""
    return AssetMetadata(
        id="asset-123",
        name="Test Asset",
        description="A test asset",
        owner=developer_user.id,
        sharing=SharingMode.PRIVATE,
        shared_with=[],
    )


@pytest.fixture
def public_asset(developer_user):
    """Create a public asset owned by developer_user."""
    return AssetMetadata(
        id="asset-456",
        name="Public Asset",
        description="A public asset",
        owner=developer_user.id,
        sharing=SharingMode.PUBLIC,
        shared_with=[],
    )


@pytest.fixture
def shared_asset(developer_user, other_user):
    """Create an asset shared with other_user."""
    return AssetMetadata(
        id="asset-789",
        name="Shared Asset",
        description="A shared asset",
        owner=developer_user.id,
        sharing=SharingMode.SHARED,
        shared_with=[
            SharedAccess(
                type=AccessType.USER,
                id=other_user.id,
                permission=Permission.RUN,
            ),
        ],
    )


class TestPermissionIncludes:
    """Tests for permission_includes helper function."""

    def test_edit_includes_all(self):
        """Test that EDIT includes RUN and VIEW."""
        assert permission_includes(Permission.EDIT, Permission.VIEW)
        assert permission_includes(Permission.EDIT, Permission.RUN)
        assert permission_includes(Permission.EDIT, Permission.EDIT)

    def test_run_includes_view(self):
        """Test that RUN includes VIEW but not EDIT."""
        assert permission_includes(Permission.RUN, Permission.VIEW)
        assert permission_includes(Permission.RUN, Permission.RUN)
        assert not permission_includes(Permission.RUN, Permission.EDIT)

    def test_view_only_includes_view(self):
        """Test that VIEW only includes VIEW."""
        assert permission_includes(Permission.VIEW, Permission.VIEW)
        assert not permission_includes(Permission.VIEW, Permission.RUN)
        assert not permission_includes(Permission.VIEW, Permission.EDIT)


class TestAccessControlEntryModel:
    """Tests for AccessControlEntry model."""

    def test_creates_with_defaults(self):
        """Test ACL entry creation with defaults."""
        entry = AccessControlEntry(
            resource_id="res-123",
            resource_type=ResourceType.PROGRAM,
            principal_type=AccessType.USER,
            principal_id="user-123",
            permission=Permission.VIEW,
            granted_by="admin-123",
        )

        assert entry.resource_id == "res-123"
        assert entry.resource_type == ResourceType.PROGRAM
        assert entry.principal_type == AccessType.USER
        assert entry.principal_id == "user-123"
        assert entry.permission == Permission.VIEW
        assert entry.granted_by == "admin-123"
        assert entry.id is not None  # UUID auto-generated
        assert entry.granted_at is not None


class TestPermissionCheckModel:
    """Tests for PermissionCheck model."""

    def test_allowed_check(self):
        """Test creating an allowed permission check."""
        check = PermissionCheck(
            allowed=True,
            reason="Owner has full access",
            effective_permission=Permission.EDIT,
        )

        assert check.allowed is True
        assert check.reason == "Owner has full access"
        assert check.effective_permission == Permission.EDIT

    def test_denied_check(self):
        """Test creating a denied permission check."""
        check = PermissionCheck(
            allowed=False,
            reason="User lacks required permission",
            effective_permission=None,
        )

        assert check.allowed is False
        assert check.effective_permission is None


class TestAdminAccess:
    """Tests for admin role access."""

    def test_admin_can_view_any_asset(
        self, permission_service, admin_user, private_asset
    ):
        """Test that admins can view any asset."""
        result = permission_service.check_permission(
            user=admin_user,
            resource_id=private_asset.id,
            resource_type=ResourceType.PROGRAM,
            required=Permission.VIEW,
            asset=private_asset,
        )

        assert result.allowed is True
        assert result.reason == "Admin users have full access"
        assert result.effective_permission == Permission.EDIT

    def test_admin_can_edit_any_asset(
        self, permission_service, admin_user, private_asset
    ):
        """Test that admins can edit any asset."""
        result = permission_service.check_permission(
            user=admin_user,
            resource_id=private_asset.id,
            resource_type=ResourceType.PROGRAM,
            required=Permission.EDIT,
            asset=private_asset,
        )

        assert result.allowed is True


class TestOwnerAccess:
    """Tests for owner access."""

    def test_owner_can_view_own_asset(
        self, permission_service, developer_user, private_asset
    ):
        """Test that owners can view their own assets."""
        result = permission_service.check_permission(
            user=developer_user,
            resource_id=private_asset.id,
            resource_type=ResourceType.PROGRAM,
            required=Permission.VIEW,
            asset=private_asset,
        )

        assert result.allowed is True
        assert result.reason == "Owner has full access"

    def test_owner_can_edit_own_asset(
        self, permission_service, developer_user, private_asset
    ):
        """Test that owners can edit their own assets."""
        result = permission_service.check_permission(
            user=developer_user,
            resource_id=private_asset.id,
            resource_type=ResourceType.PROGRAM,
            required=Permission.EDIT,
            asset=private_asset,
        )

        assert result.allowed is True

    def test_owner_can_run_own_asset(
        self, permission_service, developer_user, private_asset
    ):
        """Test that owners can run their own assets."""
        result = permission_service.check_permission(
            user=developer_user,
            resource_id=private_asset.id,
            resource_type=ResourceType.PROGRAM,
            required=Permission.RUN,
            asset=private_asset,
        )

        assert result.allowed is True


class TestPublicAccess:
    """Tests for public asset access."""

    def test_anyone_can_view_public_asset(
        self, permission_service, other_user, public_asset
    ):
        """Test that any user can view a public asset."""
        result = permission_service.check_permission(
            user=other_user,
            resource_id=public_asset.id,
            resource_type=ResourceType.PROGRAM,
            required=Permission.VIEW,
            asset=public_asset,
        )

        assert result.allowed is True
        assert "public" in result.reason.lower()

    def test_anonymous_can_view_public_asset(
        self, permission_service, public_asset
    ):
        """Test that anonymous users can view public assets."""
        result = permission_service.check_permission(
            user=None,
            resource_id=public_asset.id,
            resource_type=ResourceType.PROGRAM,
            required=Permission.VIEW,
            asset=public_asset,
        )

        assert result.allowed is True

    def test_public_does_not_grant_run(
        self, permission_service, other_user, public_asset
    ):
        """Test that public sharing only grants VIEW, not RUN."""
        result = permission_service.check_permission(
            user=other_user,
            resource_id=public_asset.id,
            resource_type=ResourceType.PROGRAM,
            required=Permission.RUN,
            asset=public_asset,
        )

        assert result.allowed is False

    def test_public_does_not_grant_edit(
        self, permission_service, other_user, public_asset
    ):
        """Test that public sharing does not grant EDIT."""
        result = permission_service.check_permission(
            user=other_user,
            resource_id=public_asset.id,
            resource_type=ResourceType.PROGRAM,
            required=Permission.EDIT,
            asset=public_asset,
        )

        assert result.allowed is False


class TestSharedAccess:
    """Tests for explicitly shared access."""

    def test_shared_user_can_run(
        self, permission_service, other_user, shared_asset
    ):
        """Test that a user with RUN permission can run."""
        result = permission_service.check_permission(
            user=other_user,
            resource_id=shared_asset.id,
            resource_type=ResourceType.PROGRAM,
            required=Permission.RUN,
            asset=shared_asset,
        )

        assert result.allowed is True
        assert "sharing" in result.reason.lower()

    def test_shared_user_can_view(
        self, permission_service, other_user, shared_asset
    ):
        """Test that a user with RUN permission can also view (included)."""
        result = permission_service.check_permission(
            user=other_user,
            resource_id=shared_asset.id,
            resource_type=ResourceType.PROGRAM,
            required=Permission.VIEW,
            asset=shared_asset,
        )

        assert result.allowed is True

    def test_shared_user_cannot_edit(
        self, permission_service, other_user, shared_asset
    ):
        """Test that a user with RUN permission cannot edit."""
        result = permission_service.check_permission(
            user=other_user,
            resource_id=shared_asset.id,
            resource_type=ResourceType.PROGRAM,
            required=Permission.EDIT,
            asset=shared_asset,
        )

        assert result.allowed is False


class TestPrivateAccess:
    """Tests for private asset access."""

    def test_non_owner_cannot_view_private(
        self, permission_service, other_user, private_asset
    ):
        """Test that non-owners cannot view private assets."""
        result = permission_service.check_permission(
            user=other_user,
            resource_id=private_asset.id,
            resource_type=ResourceType.PROGRAM,
            required=Permission.VIEW,
            asset=private_asset,
        )

        assert result.allowed is False

    def test_anonymous_cannot_view_private(
        self, permission_service, private_asset
    ):
        """Test that anonymous users cannot view private assets."""
        result = permission_service.check_permission(
            user=None,
            resource_id=private_asset.id,
            resource_type=ResourceType.PROGRAM,
            required=Permission.VIEW,
            asset=private_asset,
        )

        assert result.allowed is False
        assert "authentication required" in result.reason.lower()


class TestRequirePermission:
    """Tests for require_permission method."""

    def test_require_permission_passes(
        self, permission_service, developer_user, private_asset
    ):
        """Test that require_permission passes when allowed."""
        # Should not raise
        permission_service.require_permission(
            user=developer_user,
            resource_id=private_asset.id,
            resource_type=ResourceType.PROGRAM,
            required=Permission.VIEW,
            asset=private_asset,
        )

    def test_require_permission_raises(
        self, permission_service, other_user, private_asset
    ):
        """Test that require_permission raises when denied."""
        with pytest.raises(PermissionDeniedError) as exc_info:
            permission_service.require_permission(
                user=other_user,
                resource_id=private_asset.id,
                resource_type=ResourceType.PROGRAM,
                required=Permission.VIEW,
                asset=private_asset,
            )

        assert exc_info.value.user_id == other_user.id
        assert exc_info.value.resource_id == private_asset.id
        assert exc_info.value.required_permission == Permission.VIEW


class TestAclStore:
    """Tests for ACL storage operations."""

    def test_grant_permission_creates_entry(
        self, permission_service, developer_user, other_user, private_asset
    ):
        """Test that granting permission creates an ACL entry."""
        entry = permission_service.grant_permission(
            resource_id=private_asset.id,
            resource_type=ResourceType.PROGRAM,
            principal_id=other_user.id,
            principal_type=AccessType.USER,
            permission=Permission.VIEW,
            granted_by=developer_user.id,
        )

        assert entry.resource_id == private_asset.id
        assert entry.principal_id == other_user.id
        assert entry.permission == Permission.VIEW

    def test_grant_permission_updates_existing(
        self, permission_service, developer_user, other_user, private_asset
    ):
        """Test that granting permission again updates the entry."""
        # Grant VIEW first
        permission_service.grant_permission(
            resource_id=private_asset.id,
            resource_type=ResourceType.PROGRAM,
            principal_id=other_user.id,
            principal_type=AccessType.USER,
            permission=Permission.VIEW,
            granted_by=developer_user.id,
        )

        # Grant EDIT (should update, not create new)
        entry = permission_service.grant_permission(
            resource_id=private_asset.id,
            resource_type=ResourceType.PROGRAM,
            principal_id=other_user.id,
            principal_type=AccessType.USER,
            permission=Permission.EDIT,
            granted_by=developer_user.id,
        )

        assert entry.permission == Permission.EDIT

        # Only one entry should exist
        entries = permission_service.list_resource_permissions(
            private_asset.id, ResourceType.PROGRAM
        )
        assert len(entries) == 1

    def test_acl_permission_allows_access(
        self, permission_service, developer_user, other_user, private_asset
    ):
        """Test that ACL entries grant access."""
        # Grant permission via ACL
        permission_service.grant_permission(
            resource_id=private_asset.id,
            resource_type=ResourceType.PROGRAM,
            principal_id=other_user.id,
            principal_type=AccessType.USER,
            permission=Permission.RUN,
            granted_by=developer_user.id,
        )

        # Check access
        result = permission_service.check_permission(
            user=other_user,
            resource_id=private_asset.id,
            resource_type=ResourceType.PROGRAM,
            required=Permission.VIEW,
            asset=private_asset,
        )

        assert result.allowed is True
        assert "acl" in result.reason.lower()

    def test_revoke_permission(
        self, permission_service, developer_user, other_user, private_asset
    ):
        """Test that revoking permission removes access."""
        # Grant permission
        permission_service.grant_permission(
            resource_id=private_asset.id,
            resource_type=ResourceType.PROGRAM,
            principal_id=other_user.id,
            principal_type=AccessType.USER,
            permission=Permission.VIEW,
            granted_by=developer_user.id,
        )

        # Revoke permission
        revoked = permission_service.revoke_permission(
            resource_id=private_asset.id,
            resource_type=ResourceType.PROGRAM,
            principal_id=other_user.id,
            principal_type=AccessType.USER,
        )

        assert revoked is True

        # Check access is denied
        result = permission_service.check_permission(
            user=other_user,
            resource_id=private_asset.id,
            resource_type=ResourceType.PROGRAM,
            required=Permission.VIEW,
            asset=private_asset,
        )

        assert result.allowed is False

    def test_revoke_nonexistent_returns_false(
        self, permission_service, private_asset
    ):
        """Test that revoking non-existent permission returns False."""
        revoked = permission_service.revoke_permission(
            resource_id=private_asset.id,
            resource_type=ResourceType.PROGRAM,
            principal_id="nonexistent-user",
            principal_type=AccessType.USER,
        )

        assert revoked is False

    def test_list_resource_permissions(
        self, permission_service, developer_user, private_asset
    ):
        """Test listing permissions for a resource."""
        # Grant multiple permissions
        for i in range(3):
            permission_service.grant_permission(
                resource_id=private_asset.id,
                resource_type=ResourceType.PROGRAM,
                principal_id=f"user-{i}",
                principal_type=AccessType.USER,
                permission=Permission.VIEW,
                granted_by=developer_user.id,
            )

        entries = permission_service.list_resource_permissions(
            private_asset.id, ResourceType.PROGRAM
        )

        assert len(entries) == 3

    def test_list_user_permissions(
        self, permission_service, developer_user, other_user
    ):
        """Test listing permissions for a user."""
        # Grant permissions on multiple resources
        for i in range(3):
            permission_service.grant_permission(
                resource_id=f"resource-{i}",
                resource_type=ResourceType.PROGRAM,
                principal_id=other_user.id,
                principal_type=AccessType.USER,
                permission=Permission.VIEW,
                granted_by=developer_user.id,
            )

        entries = permission_service.list_user_permissions(other_user.id)

        assert len(entries) == 3

    def test_delete_resource_permissions(
        self, permission_service, developer_user, private_asset
    ):
        """Test deleting all permissions for a resource."""
        # Grant multiple permissions
        for i in range(3):
            permission_service.grant_permission(
                resource_id=private_asset.id,
                resource_type=ResourceType.PROGRAM,
                principal_id=f"user-{i}",
                principal_type=AccessType.USER,
                permission=Permission.VIEW,
                granted_by=developer_user.id,
            )

        # Delete all
        deleted = permission_service.delete_resource_permissions(
            private_asset.id, ResourceType.PROGRAM
        )

        assert deleted == 3

        # Verify empty
        entries = permission_service.list_resource_permissions(
            private_asset.id, ResourceType.PROGRAM
        )
        assert len(entries) == 0


class TestConvenienceMethods:
    """Tests for convenience methods (can_view, can_run, can_edit)."""

    def test_can_view(self, permission_service, developer_user, private_asset):
        """Test can_view convenience method."""
        assert permission_service.can_view(
            developer_user, private_asset, ResourceType.PROGRAM
        )

    def test_can_run(self, permission_service, developer_user, private_asset):
        """Test can_run convenience method."""
        assert permission_service.can_run(
            developer_user, private_asset, ResourceType.PROGRAM
        )

    def test_can_edit(self, permission_service, developer_user, private_asset):
        """Test can_edit convenience method."""
        assert permission_service.can_edit(
            developer_user, private_asset, ResourceType.PROGRAM
        )

    def test_get_effective_permission_owner(
        self, permission_service, developer_user, private_asset
    ):
        """Test getting effective permission for owner."""
        perm = permission_service.get_effective_permission(
            developer_user, private_asset, ResourceType.PROGRAM
        )
        assert perm == Permission.EDIT

    def test_get_effective_permission_public(
        self, permission_service, other_user, public_asset
    ):
        """Test getting effective permission for public asset."""
        perm = permission_service.get_effective_permission(
            other_user, public_asset, ResourceType.PROGRAM
        )
        assert perm == Permission.VIEW

    def test_get_effective_permission_none(
        self, permission_service, other_user, private_asset
    ):
        """Test getting effective permission when no access."""
        perm = permission_service.get_effective_permission(
            other_user, private_asset, ResourceType.PROGRAM
        )
        assert perm is None


class TestRequirePermissionDecorator:
    """Tests for the require_permission FastAPI dependency decorator."""

    @pytest.fixture
    def mock_asset_service(self, private_asset):
        """Create a mock AssetService."""
        mock = MagicMock()
        mock.get_program.return_value = MagicMock(meta=private_asset)
        mock.get_model.return_value = None
        mock.get_composition.return_value = None
        return mock

    @pytest.fixture
    def mock_permission_service_allow(self):
        """Create a mock PermissionService that allows access."""
        mock = MagicMock()
        mock.require_permission.return_value = None
        return mock

    @pytest.fixture
    def mock_permission_service_deny(self):
        """Create a mock PermissionService that denies access."""
        mock = MagicMock()
        mock.require_permission.side_effect = PermissionDeniedError(
            message="Access denied",
            user_id="test-user",
            resource_id="test-resource",
            required_permission=Permission.VIEW,
        )
        return mock

    def test_require_permission_decorator_exists(self):
        """Test that the decorator factory exists and is callable."""
        checker = require_permission(
            resource_type=ResourceType.PROGRAM,
            required=Permission.VIEW,
        )
        assert callable(checker)

    def test_require_permission_with_custom_param(self):
        """Test that the decorator accepts custom resource_id_param."""
        checker = require_permission(
            resource_type=ResourceType.MODEL,
            required=Permission.EDIT,
            resource_id_param="model_id",
        )
        assert callable(checker)
