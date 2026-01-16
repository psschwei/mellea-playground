"""Authentication routes for login, registration, and user info."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from mellea_api.core.config import Settings, get_settings
from mellea_api.core.deps import CurrentUser
from mellea_api.models.user import (
    AuthConfig,
    TokenResponse,
    UserCreate,
    UserLogin,
    UserPublic,
)
from mellea_api.services.auth import (
    AuthenticationError,
    AuthService,
    RegistrationError,
    get_auth_service,
)
from mellea_api.services.quota import QuotaService, get_quota_service
from mellea_api.services.run import RunService, get_run_service

SettingsDep = Annotated[Settings, Depends(get_settings)]
AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
QuotaServiceDep = Annotated[QuotaService, Depends(get_quota_service)]
RunServiceDep = Annotated[RunService, Depends(get_run_service)]

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.get("/config", response_model=AuthConfig)
async def get_auth_config(
    settings: SettingsDep,
) -> AuthConfig:
    """Get authentication configuration.

    This is a public endpoint that returns the available authentication methods.
    """
    return AuthConfig(
        mode="local",  # Will be "oidc" in production
        providers=["local"],  # Will include "google", "github" when configured
        registration_enabled=True,
        session_duration_hours=settings.access_token_expire_minutes // 60,
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    credentials: UserLogin,
    auth_service: AuthServiceDep,
) -> TokenResponse:
    """Login with email and password.

    Returns a JWT token for subsequent authenticated requests.
    """
    try:
        return auth_service.login(credentials.email, credentials.password)
    except AuthenticationError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        ) from e


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    user_data: UserCreate,
    auth_service: AuthServiceDep,
) -> TokenResponse:
    """Register a new user account.

    Creates a new user with the end_user role and returns a JWT token.
    """
    try:
        return auth_service.register(user_data)
    except RegistrationError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        ) from e


@router.get("/me", response_model=UserPublic)
async def get_current_user_info(
    current_user: CurrentUser,
) -> UserPublic:
    """Get the current authenticated user's information."""
    return UserPublic.model_validate(current_user)


@router.get("/me/quotas")
async def get_quota_status(
    current_user: CurrentUser,
    quota_service: QuotaServiceDep,
    run_service: RunServiceDep,
) -> dict:
    """Get the current user's quota status and usage.

    Returns current usage and limits for:
    - concurrent_runs: Number of active runs (queued, starting, running)
    - daily_runs: Number of runs created today
    - cpu_hours_month: CPU hours used this month
    - storage_mb: Storage quota limit
    """
    return quota_service.get_quota_status(
        user_id=current_user.id,
        user_quotas=current_user.quotas,
        run_service=run_service,
    )


@router.post("/logout")
async def logout(
    current_user: CurrentUser,
) -> dict[str, str]:
    """Logout the current user.

    Note: Since we use stateless JWTs, this endpoint is primarily for
    client-side token clearing. In a production system, you might want
    to implement token blacklisting for immediate invalidation.
    """
    return {"message": "Successfully logged out"}


# OAuth stub routes for future implementation
@router.get("/oauth/{provider}")
async def oauth_redirect(provider: str) -> dict[str, str]:
    """Initiate OAuth flow with the specified provider.

    Currently a stub - will redirect to provider's consent screen when implemented.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=f"OAuth provider '{provider}' not yet configured",
    )


@router.get("/oauth/callback")
async def oauth_callback(code: str, state: str) -> dict[str, str]:
    """Handle OAuth callback from provider.

    Currently a stub - will exchange code for tokens when implemented.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="OAuth callback not yet implemented",
    )
