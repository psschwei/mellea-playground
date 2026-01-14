"""Credential model for secure storage of secrets."""

from datetime import datetime
from uuid import uuid4

from pydantic import BaseModel, Field

from mellea_api.models.common import CredentialType, ModelProvider


def generate_uuid() -> str:
    """Generate a new UUID string."""
    return str(uuid4())


class Credential(BaseModel):
    """Represents a securely stored credential.

    Credentials store sensitive information like API keys, passwords,
    and tokens. The actual secret data is encrypted at rest and never
    exposed in API responses or logs.

    Example:
        ```python
        cred = Credential(
            name="OpenAI API Key",
            type=CredentialType.API_KEY,
            provider=ModelProvider.OPENAI,
        )
        ```

    Attributes:
        id: Unique identifier for the credential
        name: Human-readable name for the credential
        description: Optional description
        type: Type of credential (api_key, registry, etc.)
        provider: Associated provider (openai, anthropic, etc.)
        owner_id: ID of the owning user
        tags: Optional tags for organization
        created_at: When the credential was created
        updated_at: When the credential was last modified
        last_accessed_at: When the credential was last used
        expires_at: Optional expiration timestamp
        is_expired: Whether the credential has expired
    """

    id: str = Field(default_factory=generate_uuid)
    name: str
    description: str = ""
    type: CredentialType
    provider: ModelProvider | str | None = None
    owner_id: str | None = Field(default=None, alias="ownerId")
    tags: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow, alias="createdAt")
    updated_at: datetime = Field(default_factory=datetime.utcnow, alias="updatedAt")
    last_accessed_at: datetime | None = Field(default=None, alias="lastAccessedAt")
    expires_at: datetime | None = Field(default=None, alias="expiresAt")

    class Config:
        populate_by_name = True

    @property
    def is_expired(self) -> bool:
        """Check if the credential has expired."""
        if self.expires_at is None:
            return False
        return datetime.utcnow() > self.expires_at


class CredentialCreate(BaseModel):
    """Request model for creating a credential."""

    name: str
    description: str = ""
    type: CredentialType
    provider: ModelProvider | str | None = None
    secret_data: dict[str, str] = Field(alias="secretData")
    tags: list[str] = Field(default_factory=list)
    expires_at: datetime | None = Field(default=None, alias="expiresAt")

    class Config:
        populate_by_name = True


class CredentialUpdate(BaseModel):
    """Request model for updating a credential."""

    name: str | None = None
    description: str | None = None
    secret_data: dict[str, str] | None = Field(default=None, alias="secretData")
    tags: list[str] | None = None
    expires_at: datetime | None = Field(default=None, alias="expiresAt")

    class Config:
        populate_by_name = True


class CredentialResponse(BaseModel):
    """Response model for credential (excludes secrets)."""

    id: str
    name: str
    description: str
    type: CredentialType
    provider: ModelProvider | str | None = None
    owner_id: str | None = Field(alias="ownerId")
    tags: list[str]
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
    last_accessed_at: datetime | None = Field(alias="lastAccessedAt")
    expires_at: datetime | None = Field(alias="expiresAt")
    is_expired: bool = Field(alias="isExpired")

    class Config:
        populate_by_name = True

    @classmethod
    def from_credential(cls, cred: Credential) -> "CredentialResponse":
        """Create a response from a Credential, excluding secrets."""
        return cls(
            id=cred.id,
            name=cred.name,
            description=cred.description,
            type=cred.type,
            provider=cred.provider,
            ownerId=cred.owner_id,
            tags=cred.tags,
            createdAt=cred.created_at,
            updatedAt=cred.updated_at,
            lastAccessedAt=cred.last_accessed_at,
            expiresAt=cred.expires_at,
            isExpired=cred.is_expired,
        )
