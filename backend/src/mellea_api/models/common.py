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
