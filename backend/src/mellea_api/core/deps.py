"""FastAPI dependencies for authentication and authorization."""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from mellea_api.core.security import decode_access_token
from mellea_api.models.user import User, UserRole
from mellea_api.services.auth import get_auth_service

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


def require_role(minimum_role: UserRole):
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


# Type aliases for common dependencies
CurrentUser = Annotated[User, Depends(get_current_user)]
OptionalUser = Annotated[User | None, Depends(get_current_user_optional)]
AdminUser = Annotated[User, Depends(require_role(UserRole.ADMIN))]
DeveloperUser = Annotated[User, Depends(require_role(UserRole.DEVELOPER))]
