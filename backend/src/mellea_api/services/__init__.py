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
from mellea_api.services.code_generator import (
    CodeGenerator,
    CodeGeneratorOptions,
    GeneratedCode,
    get_code_generator,
)
from mellea_api.services.composition_executor import (
    CompositionExecutor,
    CompositionNotFoundError,
    CompositionRunNotFoundError,
    CompositionRunService,
    CompositionValidationError,
    CredentialValidationError,
    EnvironmentNotReadyError,
    InvalidCompositionRunStateTransitionError,
    ValidationResult,
    get_composition_executor,
    get_composition_run_service,
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
from mellea_api.services.idle_timeout import (
    IdleTimeoutController,
    IdleTimeoutService,
    get_idle_timeout_controller,
    get_idle_timeout_service,
)
from mellea_api.services.kaniko_builder import (
    KanikoBuildService,
    get_kaniko_build_service,
    reset_kaniko_build_service,
)
from mellea_api.services.log import (
    LogEntry,
    LogService,
    get_log_service,
    reset_log_service,
)
from mellea_api.services.model_pricing import (
    ModelPrice,
    ModelPricing,
    get_model_pricing,
)
from mellea_api.services.permission import (
    PermissionDeniedError,
    PermissionService,
    ResourceNotFoundError,
    get_permission_service,
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
    # Code generator service
    "CodeGenerator",
    "CodeGeneratorOptions",
    "GeneratedCode",
    "get_code_generator",
    # Composition executor service
    "CompositionExecutor",
    "CompositionRunService",
    "get_composition_executor",
    "get_composition_run_service",
    "CompositionNotFoundError",
    "CompositionRunNotFoundError",
    "CompositionValidationError",
    "CredentialValidationError",
    "EnvironmentNotReadyError",
    "InvalidCompositionRunStateTransitionError",
    "ValidationResult",
    # Environment service
    "EnvironmentService",
    "get_environment_service",
    "EnvironmentNotFoundError",
    "InvalidStateTransitionError",
    # Environment builder service
    "EnvironmentBuilderService",
    "get_environment_builder_service",
    "ImageBuildError",
    # Kaniko build service
    "KanikoBuildService",
    "get_kaniko_build_service",
    "reset_kaniko_build_service",
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
    # Log service
    "LogService",
    "get_log_service",
    "LogEntry",
    "reset_log_service",
    # Model pricing service
    "ModelPricing",
    "ModelPrice",
    "get_model_pricing",
    # Permission service
    "PermissionService",
    "get_permission_service",
    "PermissionDeniedError",
    "ResourceNotFoundError",
]
