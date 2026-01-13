"""Asset models for Programs, Models, and Compositions."""

from datetime import datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from mellea_api.models.common import (
    AccessType,
    DependencySource,
    ImageBuildStatus,
    ModelProvider,
    ModelScope,
    Permission,
    RunStatus,
    SharingMode,
)


def generate_uuid() -> str:
    """Generate a new UUID string."""
    return str(uuid4())


class SharedAccess(BaseModel):
    """Access grant for a user, group, or organization."""

    type: AccessType
    id: str
    permission: Permission


class AssetMetadata(BaseModel):
    """Universal metadata fields shared by all asset types."""

    id: str = Field(default_factory=generate_uuid)
    name: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    version: str = "1.0.0"
    owner: str = ""
    sharing: SharingMode = SharingMode.PRIVATE
    shared_with: list[SharedAccess] = Field(default_factory=list, alias="sharedWith")
    created_at: datetime = Field(default_factory=datetime.utcnow, alias="createdAt")
    updated_at: datetime = Field(default_factory=datetime.utcnow, alias="updatedAt")
    last_run_status: RunStatus | None = Field(default=None, alias="lastRunStatus")
    last_run_at: datetime | None = Field(default=None, alias="lastRunAt")

    class Config:
        populate_by_name = True


class PackageRef(BaseModel):
    """Reference to a Python package dependency."""

    name: str
    version: str | None = None
    extras: list[str] = Field(default_factory=list)


class DependencySpec(BaseModel):
    """Specification of program dependencies."""

    source: DependencySource
    packages: list[PackageRef] = Field(default_factory=list)
    python_version: str | None = Field(default=None, alias="pythonVersion")
    lockfile_hash: str | None = Field(default=None, alias="lockfileHash")

    class Config:
        populate_by_name = True


class SlotSignature(BaseModel):
    """Type signature for a @generative slot."""

    name: str
    args: list[dict[str, Any]] = Field(default_factory=list)
    returns: dict[str, Any] | None = None


class SlotMetadata(BaseModel):
    """Metadata for an exported @generative slot."""

    name: str
    qualified_name: str = Field(alias="qualifiedName")
    docstring: str | None = None
    signature: SlotSignature
    decorators: list[str] = Field(default_factory=list)
    source_file: str = Field(alias="sourceFile")
    line_number: int = Field(alias="lineNumber")

    class Config:
        populate_by_name = True


class ResourceProfile(BaseModel):
    """Resource limits for program execution."""

    cpu_limit: str = Field(default="1", alias="cpuLimit")
    memory_limit: str = Field(default="2Gi", alias="memoryLimit")
    timeout_seconds: int = Field(default=1800, alias="timeoutSeconds")
    ephemeral_storage_limit: str | None = Field(default=None, alias="ephemeralStorageLimit")

    class Config:
        populate_by_name = True


class ProgramAsset(AssetMetadata):
    """A Python program with mellea entrypoints and @generative slots."""

    type: Literal["program"] = "program"
    entrypoint: str
    project_root: str = Field(alias="projectRoot")
    dependencies: DependencySpec
    exported_slots: list[SlotMetadata] = Field(default_factory=list, alias="exportedSlots")
    requirements: list[str] = Field(default_factory=list)
    resource_profile: ResourceProfile = Field(
        default_factory=ResourceProfile, alias="resourceProfile"
    )
    image_tag: str | None = Field(default=None, alias="imageTag")
    image_build_status: ImageBuildStatus | None = Field(default=None, alias="imageBuildStatus")
    image_build_error: str | None = Field(default=None, alias="imageBuildError")

    class Config:
        populate_by_name = True


class EndpointConfig(BaseModel):
    """Custom endpoint configuration for LLM providers."""

    base_url: str = Field(alias="baseUrl")
    api_version: str | None = Field(default=None, alias="apiVersion")
    headers: dict[str, str] = Field(default_factory=dict)

    class Config:
        populate_by_name = True


class ModelParams(BaseModel):
    """Default parameters for LLM model inference."""

    temperature: float | None = None
    max_tokens: int | None = Field(default=None, alias="maxTokens")
    top_p: float | None = Field(default=None, alias="topP")
    frequency_penalty: float | None = Field(default=None, alias="frequencyPenalty")
    presence_penalty: float | None = Field(default=None, alias="presencePenalty")
    stop_sequences: list[str] = Field(default_factory=list, alias="stopSequences")

    class Config:
        populate_by_name = True


class ModelCapabilities(BaseModel):
    """Capabilities and constraints of an LLM model."""

    context_window: int = Field(alias="contextWindow")
    supports_streaming: bool = Field(default=True, alias="supportsStreaming")
    supports_tool_calling: bool = Field(default=False, alias="supportsToolCalling")
    supported_modalities: list[str] = Field(
        default_factory=lambda: ["text"], alias="supportedModalities"
    )
    languages: list[str] = Field(default_factory=list)

    class Config:
        populate_by_name = True


class AccessControl(BaseModel):
    """Role-based access control for a model."""

    end_users: bool = Field(default=True, alias="endUsers")
    developers: bool = Field(default=True)
    admins: bool = Field(default=True)

    class Config:
        populate_by_name = True


class ModelAsset(AssetMetadata):
    """An LLM backend configuration."""

    type: Literal["model"] = "model"
    provider: ModelProvider
    model_id: str = Field(alias="modelId")
    endpoint: EndpointConfig | None = None
    credentials_ref: str | None = Field(default=None, alias="credentialsRef")
    default_params: ModelParams = Field(default_factory=ModelParams, alias="defaultParams")
    capabilities: ModelCapabilities | None = None
    access_control: AccessControl = Field(default_factory=AccessControl, alias="accessControl")
    scope: ModelScope = ModelScope.ALL

    class Config:
        populate_by_name = True


class CompositionGraph(BaseModel):
    """Graph definition for a composition (nodes and edges)."""

    nodes: list[dict[str, Any]] = Field(default_factory=list)
    edges: list[dict[str, Any]] = Field(default_factory=list)


class CompositionSpec(BaseModel):
    """Specification for composition execution."""

    inputs: dict[str, Any] = Field(default_factory=dict)
    outputs: dict[str, Any] = Field(default_factory=dict)


class CompositionAsset(AssetMetadata):
    """A visual workflow linking programs and models."""

    type: Literal["composition"] = "composition"
    program_refs: list[str] = Field(default_factory=list, alias="programRefs")
    model_refs: list[str] = Field(default_factory=list, alias="modelRefs")
    graph: CompositionGraph = Field(default_factory=CompositionGraph)
    spec: CompositionSpec = Field(default_factory=CompositionSpec)

    class Config:
        populate_by_name = True
