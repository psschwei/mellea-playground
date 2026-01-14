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
from mellea_api.services.environment import (
    EnvironmentNotFoundError,
    EnvironmentService,
    InvalidStateTransitionError,
    get_environment_service,
)
from mellea_api.services.environment_builder import (
    EnvironmentBuilderService,
    ImageBuildError,
    get_environment_builder_service,
)
from mellea_api.services.credentials import (
    CredentialNotFoundError,
    CredentialService,
    get_credential_service,
)
from mellea_api.services.idle_timeout import (
    IdleTimeoutController,
    IdleTimeoutService,
    get_idle_timeout_controller,
    get_idle_timeout_service,
)
from mellea_api.services.warmup import (
    WarmupController,
    WarmupService,
    get_warmup_controller,
    get_warmup_service,
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
    # Environment service
    "EnvironmentService",
    "get_environment_service",
    "EnvironmentNotFoundError",
    "InvalidStateTransitionError",
    # Environment builder service
    "EnvironmentBuilderService",
    "get_environment_builder_service",
    "ImageBuildError",
    # Idle timeout service
    "IdleTimeoutService",
    "get_idle_timeout_service",
    "IdleTimeoutController",
    "get_idle_timeout_controller",
    # Warmup service
    "WarmupService",
    "get_warmup_service",
    "WarmupController",
    "get_warmup_controller",
]
