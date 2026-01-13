"""Service layer for business logic."""

from mellea_api.services.assets import (
    AssetAlreadyExistsError,
    AssetNotFoundError,
    AssetService,
    WorkspaceError,
    get_asset_service,
)
from mellea_api.services.auth import (
    AuthenticationError,
    AuthService,
    RegistrationError,
    get_auth_service,
)
from mellea_api.services.environment_builder import (
    EnvironmentBuilderService,
    ImageBuildError,
    get_environment_builder_service,
)

__all__ = [
    # Asset service
    "AssetService",
    "get_asset_service",
    "AssetNotFoundError",
    "AssetAlreadyExistsError",
    "WorkspaceError",
    # Auth service
    "AuthService",
    "get_auth_service",
    "AuthenticationError",
    "RegistrationError",
    # Environment builder service
    "EnvironmentBuilderService",
    "get_environment_builder_service",
    "ImageBuildError",
]
