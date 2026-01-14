"""Common enums and types used across models."""

from enum import Enum


class SharingMode(str, Enum):
    """Asset sharing visibility mode."""

    PRIVATE = "private"
    SHARED = "shared"
    PUBLIC = "public"


class RunStatus(str, Enum):
    """Status of the last run for an asset."""

    NEVER_RUN = "never_run"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ModelProvider(str, Enum):
    """Supported LLM providers."""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    OLLAMA = "ollama"
    AZURE = "azure"
    CUSTOM = "custom"


class ModelScope(str, Enum):
    """Where a model can be used."""

    CHAT = "chat"
    AGENT = "agent"
    COMPOSITION = "composition"
    ALL = "all"


class ImageBuildStatus(str, Enum):
    """Status of container image build."""

    PENDING = "pending"
    BUILDING = "building"
    READY = "ready"
    FAILED = "failed"


class DependencySource(str, Enum):
    """Source of dependency specification."""

    PYPROJECT = "pyproject"
    REQUIREMENTS = "requirements"
    MANUAL = "manual"


class AccessType(str, Enum):
    """Type of shared access entity."""

    USER = "user"
    GROUP = "group"
    ORG = "org"


class Permission(str, Enum):
    """Permission level for shared access."""

    VIEW = "view"
    RUN = "run"
    EDIT = "edit"


class EnvironmentStatus(str, Enum):
    """Status of an environment in its lifecycle.

    State machine transitions:
        CREATING -> READY (build succeeded)
        CREATING -> FAILED (build failed)
        READY -> STARTING (start requested)
        STARTING -> RUNNING (container started)
        STARTING -> FAILED (start failed)
        RUNNING -> STOPPING (stop requested)
        STOPPING -> STOPPED (container stopped)
        RUNNING -> FAILED (runtime error)
        READY -> DELETING (delete requested)
        STOPPED -> DELETING (delete requested)
        FAILED -> DELETING (delete requested)
    """

    CREATING = "creating"  # Initial state, being built
    READY = "ready"  # Built and available
    STARTING = "starting"  # Container starting
    RUNNING = "running"  # Container running
    STOPPING = "stopping"  # Container stopping
    STOPPED = "stopped"  # Container stopped
    FAILED = "failed"  # Build or runtime failure
    DELETING = "deleting"  # Being cleaned up


class CredentialType(str, Enum):
    """Type of stored credential."""

    API_KEY = "api_key"  # LLM provider API keys
    REGISTRY = "registry"  # Container registry credentials
    DATABASE = "database"  # Database connection credentials
    OAUTH_TOKEN = "oauth_token"  # OAuth tokens
    SSH_KEY = "ssh_key"  # SSH keys for deployments
    CUSTOM = "custom"  # User-defined credential type


class RunExecutionStatus(str, Enum):
    """Status of a program run execution.

    State machine transitions:
        QUEUED -> STARTING (job creation started)
        QUEUED -> CANCELLED (user cancelled before start)
        STARTING -> RUNNING (K8s job started)
        STARTING -> FAILED (job creation failed)
        RUNNING -> SUCCEEDED (exit code 0)
        RUNNING -> FAILED (exit code != 0 or timeout)
        RUNNING -> CANCELLED (user cancelled during execution)
    """

    QUEUED = "queued"  # Initial state, waiting to start
    STARTING = "starting"  # K8s Job being created
    RUNNING = "running"  # Job is executing
    SUCCEEDED = "succeeded"  # Completed successfully (exit code 0)
    FAILED = "failed"  # Completed with error
    CANCELLED = "cancelled"  # User cancelled
