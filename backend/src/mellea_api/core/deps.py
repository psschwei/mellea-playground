"""FastAPI dependencies for authentication and authorization."""

from collections.abc import Callable, Coroutine
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Query, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from mellea_api.core.security import decode_access_token
from mellea_api.models.assets import (
    CompositionAsset,
    ModelAsset,
    ProgramAsset,
)
from mellea_api.models.common import Permission
from mellea_api.models.permission import ResourceType
from mellea_api.models.user import User, UserRole
from mellea_api.services.auth import get_auth_service
from mellea_api.services.permission import (
    PermissionDeniedError,
    PermissionService,
    get_permission_service,
)

# HTTP Bearer token security scheme
security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
) -> User:
    """Get the current authenticated user from the JWT token.

    This is a FastAPI dependency that extracts and validates the JWT token
    from the Authorization header and returns the corresponding user.

    Args:
        credentials: HTTP Bearer credentials from the request

    Returns:
        The authenticated user

    Raises:
        HTTPException: 401 if token is missing, invalid, or user not found
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Decode the token
    payload = decode_access_token(credentials.credentials)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Get user from database
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )

    auth_service = get_auth_service()
    user = auth_service.get_user_by_id(user_id)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if user.status.value != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Account is {user.status.value}",
        )

    return user


async def get_current_user_optional(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
) -> User | None:
    """Get the current user if authenticated, None otherwise.

    Use this for endpoints that work for both authenticated and anonymous users.

    Args:
        credentials: HTTP Bearer credentials from the request

    Returns:
        The authenticated user if valid token provided, None otherwise
    """
    if credentials is None:
        return None

    payload = decode_access_token(credentials.credentials)
    if payload is None:
        return None

    user_id = payload.get("sub")
    if not user_id:
        return None

    auth_service = get_auth_service()
    user = auth_service.get_user_by_id(user_id)

    if user is None or user.status.value != "active":
        return None

    return user


def require_role(
    minimum_role: UserRole,
) -> Callable[..., Coroutine[Any, Any, User]]:
    """Create a dependency that requires a minimum role level.

    Role hierarchy: end_user < developer < admin

    Args:
        minimum_role: The minimum role required for access

    Returns:
        A FastAPI dependency function

    Example:
        @router.post("/programs")
        async def create_program(
            current_user: Annotated[User, Depends(require_role(UserRole.DEVELOPER))]
        ):
            ...
    """
    role_hierarchy = {
        UserRole.END_USER: 0,
        UserRole.DEVELOPER: 1,
        UserRole.ADMIN: 2,
    }

    async def role_checker(
        current_user: Annotated[User, Depends(get_current_user)],
    ) -> User:
        user_level = role_hierarchy.get(current_user.role, 0)
        required_level = role_hierarchy.get(minimum_role, 0)

        if user_level < required_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This action requires {minimum_role.value} role or higher",
            )

        return current_user

    return role_checker


async def get_current_user_sse(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    token: Annotated[str | None, Query()] = None,
) -> User:
    """Get the current authenticated user for SSE endpoints.

    Supports both Authorization header and query parameter token for
    EventSource compatibility (EventSource doesn't support custom headers).

    Args:
        credentials: HTTP Bearer credentials from the request
        token: Optional token from query parameter (for SSE)

    Returns:
        The authenticated user

    Raises:
        HTTPException: 401 if token is missing, invalid, or user not found
    """
    # Try header first, then query param
    raw_token = None
    if credentials is not None:
        raw_token = credentials.credentials
    elif token is not None:
        raw_token = token

    if raw_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Decode the token
    payload = decode_access_token(raw_token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Get user from database
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )

    auth_service = get_auth_service()
    user = auth_service.get_user_by_id(user_id)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if user.status.value != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Account is {user.status.value}",
        )

    return user


def require_permission(
    resource_type: ResourceType,
    required: Permission,
    resource_id_param: str = "id",
) -> Callable[..., Coroutine[Any, Any, User]]:
    """Create a dependency that requires a specific permission on a resource.

    This decorator factory creates a FastAPI dependency that checks whether
    the current user has the required permission on the specified resource.

    Args:
        resource_type: Type of resource being accessed (PROGRAM, MODEL, COMPOSITION)
        required: Permission level required (VIEW, RUN, EDIT)
        resource_id_param: Name of the path parameter containing the resource ID
            (default: "id")

    Returns:
        A FastAPI dependency function that performs the permission check

    Example:
        @router.get("/programs/{id}")
        async def get_program(
            id: str,
            current_user: Annotated[User, Depends(require_permission(
                ResourceType.PROGRAM,
                Permission.VIEW,
            ))],
        ):
            ...

        @router.put("/models/{model_id}")
        async def update_model(
            model_id: str,
            current_user: Annotated[User, Depends(require_permission(
                ResourceType.MODEL,
                Permission.EDIT,
                resource_id_param="model_id",
            ))],
        ):
            ...
    """
    from mellea_api.services.assets import get_asset_service

    async def permission_checker(
        request: Request,
        current_user: Annotated[User, Depends(get_current_user)],
    ) -> User:
        # Get resource ID from path parameters
        resource_id = request.path_params.get(resource_id_param)
        if not resource_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Missing resource ID parameter: {resource_id_param}",
            )

        # Get the asset to check permissions
        asset_service = get_asset_service()
        permission_service = get_permission_service()

        # Load asset metadata based on resource type
        asset: ProgramAsset | ModelAsset | CompositionAsset | None = None
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
        try:
            permission_service.require_permission(
                user=current_user,
                resource_id=resource_id,
                resource_type=resource_type,
                required=required,
                asset=asset.meta if hasattr(asset, "meta") else asset,
            )
        except PermissionDeniedError as e:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=str(e),
            ) from e

        return current_user

    return permission_checker


class ImpersonationInfo:
    """Information about an active impersonation session."""

    def __init__(
        self,
        impersonator_id: str,
        impersonator_email: str,
        target_user: User,
    ) -> None:
        self.impersonator_id = impersonator_id
        self.impersonator_email = impersonator_email
        self.target_user = target_user


async def get_impersonation_info(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
) -> ImpersonationInfo | None:
    """Get impersonation info if the current session is an impersonation.

    Returns:
        ImpersonationInfo if this is an impersonation session, None otherwise
    """
    if credentials is None:
        return None

    payload = decode_access_token(credentials.credentials)
    if payload is None:
        return None

    # Check if this is an impersonation token
    if not payload.get("is_impersonation"):
        return None

    # Get the target user
    user_id = payload.get("sub")
    if not user_id:
        return None

    auth_service = get_auth_service()
    target_user = auth_service.get_user_by_id(user_id)

    if target_user is None:
        return None

    return ImpersonationInfo(
        impersonator_id=payload.get("impersonator_id", ""),
        impersonator_email=payload.get("impersonator_email", ""),
        target_user=target_user,
    )


async def get_actual_admin_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
) -> User:
    """Get the actual admin user, even during impersonation.

    During impersonation, this returns the admin who is impersonating.
    Without impersonation, this returns the current user (if admin).

    Returns:
        The actual admin user

    Raises:
        HTTPException: 401 if not authenticated, 403 if not admin
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_access_token(credentials.credentials)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    auth_service = get_auth_service()

    # If impersonating, get the impersonator
    if payload.get("is_impersonation"):
        impersonator_id = payload.get("impersonator_id")
        if not impersonator_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid impersonation token",
            )
        user = auth_service.get_user_by_id(impersonator_id)
    else:
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload",
            )
        user = auth_service.get_user_by_id(user_id)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    if user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )

    return user


# Type aliases for common dependencies
CurrentUser = Annotated[User, Depends(get_current_user)]
CurrentUserSSE = Annotated[User, Depends(get_current_user_sse)]
OptionalUser = Annotated[User | None, Depends(get_current_user_optional)]
AdminUser = Annotated[User, Depends(require_role(UserRole.ADMIN))]
DeveloperUser = Annotated[User, Depends(require_role(UserRole.DEVELOPER))]
ActualAdminUser = Annotated[User, Depends(get_actual_admin_user)]
ImpersonationInfoDep = Annotated[ImpersonationInfo | None, Depends(get_impersonation_info)]

# Service dependencies
PermissionServiceDep = Annotated[PermissionService, Depends(get_permission_service)]
