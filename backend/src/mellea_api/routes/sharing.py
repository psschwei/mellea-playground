"""Sharing API routes for managing share links and user sharing."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from mellea_api.core.deps import CurrentUser, OptionalUser
from mellea_api.models.assets import CompositionAsset, ModelAsset, ProgramAsset
from mellea_api.models.common import Permission
from mellea_api.models.permission import ResourceType
from mellea_api.models.sharing import (
    CreateShareLinkRequest,
    SharedWithMeItem,
    SharedWithMeResponse,
    ShareLinkListResponse,
    ShareLinkResponse,
    ShareWithUserRequest,
)
from mellea_api.services.permission import get_permission_service
from mellea_api.services.sharing import (
    ShareLinkExpiredError,
    ShareLinkInactiveError,
    ShareLinkNotFoundError,
    SharingService,
    get_sharing_service,
)

router = APIRouter(prefix="/api/sharing", tags=["sharing"])

# Dependencies
SharingServiceDep = Annotated[SharingService, Depends(get_sharing_service)]

# Type alias for any asset type
AssetType = ProgramAsset | ModelAsset | CompositionAsset | None


def _check_resource_permission(
    user: CurrentUser,
    resource_id: str,
    resource_type: ResourceType,
    required: Permission,
) -> None:
    """Check if user has permission on a resource.

    Raises HTTPException if permission denied.
    """
    from mellea_api.services.assets import get_asset_service

    asset_service = get_asset_service()
    permission_service = get_permission_service()

    # Get the asset
    asset: AssetType = None
    if resource_type == ResourceType.PROGRAM:
        asset = asset_service.get_program(resource_id)
    elif resource_type == ResourceType.MODEL:
        asset = asset_service.get_model(resource_id)
    elif resource_type == ResourceType.COMPOSITION:
        asset = asset_service.get_composition(resource_id)

    if asset is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{resource_type.value.capitalize()} not found",
        )

    # Check permission
    meta = asset.meta if hasattr(asset, "meta") else asset
    result = permission_service.check_permission(
        user=user,
        resource_id=resource_id,
        resource_type=resource_type,
        required=required,
        asset=meta,
    )

    if not result.allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=result.reason,
        )


# =============================================================================
# Share Link Endpoints
# =============================================================================


@router.post("/links", response_model=ShareLinkResponse)
async def create_share_link(
    request: Request,
    body: CreateShareLinkRequest,
    current_user: CurrentUser,
    service: SharingServiceDep,
) -> ShareLinkResponse:
    """Create a new share link for a resource.

    Requires EDIT permission on the resource.
    """
    # Check that user can share (needs edit permission)
    _check_resource_permission(
        current_user,
        body.resource_id,
        body.resource_type,
        Permission.EDIT,
    )

    link = service.create_share_link(
        resource_id=body.resource_id,
        resource_type=body.resource_type,
        permission=body.permission,
        created_by=current_user.id,
        expires_in_hours=body.expires_in_hours,
        label=body.label,
    )

    # Build base URL from request
    base_url = str(request.base_url).rstrip("/")

    return ShareLinkResponse.from_share_link(link, base_url)


@router.get("/links", response_model=ShareLinkListResponse)
async def list_share_links(
    current_user: CurrentUser,
    service: SharingServiceDep,
    resource_id: Annotated[str | None, Query(alias="resourceId")] = None,
    resource_type: Annotated[ResourceType | None, Query(alias="resourceType")] = None,
    include_inactive: Annotated[bool, Query(alias="includeInactive")] = False,
) -> ShareLinkListResponse:
    """List share links.

    If resource_id and resource_type are provided, lists links for that resource.
    Otherwise, lists all links created by the current user.
    """
    if resource_id and resource_type:
        # Check permission to view resource links
        _check_resource_permission(
            current_user,
            resource_id,
            resource_type,
            Permission.VIEW,
        )
        links = service.list_share_links_for_resource(
            resource_id, resource_type, include_inactive
        )
    else:
        # List user's own links
        links = service.list_share_links_by_user(current_user.id, include_inactive)

    responses = [ShareLinkResponse.from_share_link(link) for link in links]

    return ShareLinkListResponse(links=responses, total=len(responses))


@router.get("/links/{link_id}", response_model=ShareLinkResponse)
async def get_share_link(
    link_id: str,
    current_user: CurrentUser,
    service: SharingServiceDep,
) -> ShareLinkResponse:
    """Get a share link by ID.

    Only the link creator or resource owner can view the link details.
    """
    link = service.get_share_link(link_id)

    if link is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Share link not found",
        )

    # Check permission - must be creator or have edit permission on resource
    if link.created_by != current_user.id:
        try:
            _check_resource_permission(
                current_user,
                link.resource_id,
                link.resource_type,
                Permission.EDIT,
            )
        except HTTPException:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the link creator or resource owner can view this link",
            ) from None

    return ShareLinkResponse.from_share_link(link)


@router.delete("/links/{link_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_share_link(
    link_id: str,
    current_user: CurrentUser,
    service: SharingServiceDep,
) -> None:
    """Delete a share link.

    Only the link creator or resource owner can delete the link.
    """
    link = service.get_share_link(link_id)

    if link is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Share link not found",
        )

    # Check permission - must be creator or have edit permission on resource
    if link.created_by != current_user.id:
        try:
            _check_resource_permission(
                current_user,
                link.resource_id,
                link.resource_type,
                Permission.EDIT,
            )
        except HTTPException:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the link creator or resource owner can delete this link",
            ) from None

    service.delete_share_link(link_id)


@router.post("/links/{link_id}/deactivate", response_model=ShareLinkResponse)
async def deactivate_share_link(
    link_id: str,
    current_user: CurrentUser,
    service: SharingServiceDep,
) -> ShareLinkResponse:
    """Deactivate a share link.

    The link will still exist but won't grant access anymore.
    Only the link creator or resource owner can deactivate the link.
    """
    link = service.get_share_link(link_id)

    if link is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Share link not found",
        )

    # Check permission - must be creator or have edit permission on resource
    if link.created_by != current_user.id:
        try:
            _check_resource_permission(
                current_user,
                link.resource_id,
                link.resource_type,
                Permission.EDIT,
            )
        except HTTPException:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the link creator or resource owner can deactivate this link",
            ) from None

    updated_link = service.deactivate_share_link(link_id)
    if updated_link is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Share link not found",
        )

    return ShareLinkResponse.from_share_link(updated_link)


@router.get("/verify/{token}")
async def verify_share_link(
    token: str,
    service: SharingServiceDep,
    current_user: OptionalUser = None,
) -> dict[str, Any]:
    """Verify a share link token and return resource info.

    This endpoint can be used by both authenticated and anonymous users
    to verify a share link and get information about the shared resource.
    """
    try:
        link = service.verify_share_link_access(token)
    except ShareLinkNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Share link not found",
        ) from None
    except ShareLinkInactiveError:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Share link has been deactivated",
        ) from None
    except ShareLinkExpiredError:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Share link has expired",
        ) from None

    # Get resource info
    from mellea_api.services.assets import get_asset_service

    asset_service = get_asset_service()

    resource_name: str | None = None
    if link.resource_type == ResourceType.PROGRAM:
        program = asset_service.get_program(link.resource_id)
        if program:
            meta = program.meta if hasattr(program, "meta") else program
            resource_name = meta.name if meta else None
    elif link.resource_type == ResourceType.MODEL:
        model = asset_service.get_model(link.resource_id)
        if model:
            meta = model.meta if hasattr(model, "meta") else model
            resource_name = meta.name if meta else None
    elif link.resource_type == ResourceType.COMPOSITION:
        composition = asset_service.get_composition(link.resource_id)
        if composition:
            meta = composition.meta if hasattr(composition, "meta") else composition
            resource_name = meta.name if meta else None

    return {
        "valid": True,
        "resourceId": link.resource_id,
        "resourceType": link.resource_type.value,
        "resourceName": resource_name,
        "permission": link.permission.value,
    }


# =============================================================================
# User Sharing Endpoints
# =============================================================================


@router.post("/users", status_code=status.HTTP_201_CREATED)
async def share_with_user(
    body: ShareWithUserRequest,
    current_user: CurrentUser,
    service: SharingServiceDep,
) -> dict[str, Any]:
    """Share a resource with a specific user.

    Requires EDIT permission on the resource.
    """
    # Check permission
    _check_resource_permission(
        current_user,
        body.resource_id,
        body.resource_type,
        Permission.EDIT,
    )

    # Verify target user exists
    from mellea_api.services.auth import get_auth_service

    auth_service = get_auth_service()
    target_user = auth_service.get_user_by_id(body.user_id)

    if target_user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Target user not found",
        )

    # Can't share with yourself
    if body.user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot share a resource with yourself",
        )

    try:
        access = service.share_with_user(
            resource_id=body.resource_id,
            resource_type=body.resource_type,
            user_id=body.user_id,
            permission=body.permission,
            shared_by=current_user.id,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e

    return {
        "success": True,
        "userId": access.id,
        "permission": access.permission.value,
    }


@router.delete(
    "/users/{resource_type}/{resource_id}/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def revoke_user_access(
    resource_type: ResourceType,
    resource_id: str,
    user_id: str,
    current_user: CurrentUser,
    service: SharingServiceDep,
) -> None:
    """Revoke a user's access to a resource.

    Requires EDIT permission on the resource.
    """
    # Check permission
    _check_resource_permission(
        current_user,
        resource_id,
        resource_type,
        Permission.EDIT,
    )

    revoked = service.revoke_user_access(
        resource_id=resource_id,
        resource_type=resource_type,
        user_id=user_id,
    )

    if not revoked:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User does not have access to this resource",
        )


@router.get("/users/{resource_type}/{resource_id}")
async def list_shared_users(
    resource_type: ResourceType,
    resource_id: str,
    current_user: CurrentUser,
    service: SharingServiceDep,
) -> dict[str, Any]:
    """List users a resource is shared with.

    Requires VIEW permission on the resource.
    """
    # Check permission
    _check_resource_permission(
        current_user,
        resource_id,
        resource_type,
        Permission.VIEW,
    )

    shared_users = service.get_shared_users(resource_id, resource_type)

    # Get user details
    from mellea_api.services.auth import get_auth_service

    auth_service = get_auth_service()

    users_with_details = []
    for access in shared_users:
        user = auth_service.get_user_by_id(access.id)
        users_with_details.append(
            {
                "userId": access.id,
                "username": user.username if user else None,
                "displayName": user.display_name if user else None,
                "permission": access.permission.value,
            }
        )

    return {
        "users": users_with_details,
        "total": len(users_with_details),
    }


# =============================================================================
# Shared With Me Endpoints
# =============================================================================


@router.get("/shared-with-me", response_model=SharedWithMeResponse)
async def get_shared_with_me(
    current_user: CurrentUser,
    service: SharingServiceDep,
) -> SharedWithMeResponse:
    """Get all resources shared with the current user."""
    items_data = service.get_resources_shared_with_user(current_user)

    items = [
        SharedWithMeItem(
            resource_id=item["resource_id"],
            resource_type=item["resource_type"],
            resource_name=item["resource_name"],
            permission=item["permission"],
            shared_by=item["shared_by"],
            shared_by_name=item["shared_by_name"],
            shared_at=item["shared_at"],
        )
        for item in items_data
    ]

    return SharedWithMeResponse(items=items, total=len(items))
