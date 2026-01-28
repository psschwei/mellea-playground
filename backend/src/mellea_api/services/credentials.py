"""CredentialService for secure storage and management of secrets."""

from __future__ import annotations

import base64
import contextlib
import hashlib
import json
import logging
import os
import threading
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from mellea_api.core.config import Settings, get_settings
from mellea_api.models.common import CredentialType, ModelProvider
from mellea_api.models.credential import Credential, CredentialUpdate

if TYPE_CHECKING:
    from kubernetes import client as k8s_client

logger = logging.getLogger(__name__)


class CredentialNotFoundError(Exception):
    """Raised when a credential is not found."""

    pass


class CredentialValidationError(Exception):
    """Raised when credential validation fails."""

    def __init__(self, message: str, missing_keys: list[str] | None = None) -> None:
        """Initialize validation error.

        Args:
            message: Error message
            missing_keys: List of missing required keys
        """
        super().__init__(message)
        self.message = message
        self.missing_keys = missing_keys or []


# Provider-specific validation rules
# Each provider maps to: (required_keys, optional_keys)
PROVIDER_VALIDATION_RULES: dict[str, tuple[set[str], set[str]]] = {
    ModelProvider.OPENAI.value: ({"api_key"}, {"organization_id"}),
    ModelProvider.ANTHROPIC.value: ({"api_key"}, set()),
    ModelProvider.OLLAMA.value: (set(), {"api_key"}),
    ModelProvider.CUSTOM.value: (set(), set()),  # No strict validation for custom
}

# Azure has two authentication modes: API key or OAuth
AZURE_API_KEY_RULES: tuple[set[str], set[str]] = (
    {"api_key", "endpoint"},
    {"api_version"},
)
AZURE_OAUTH_RULES: tuple[set[str], set[str]] = (
    {"tenant_id", "client_id", "client_secret", "endpoint"},
    {"api_version"},
)


def validate_secret_data(
    provider: ModelProvider | str | None,
    secret_data: dict[str, str],
    credential_type: CredentialType = CredentialType.API_KEY,
) -> None:
    """Validate secret_data against provider-specific rules.

    Args:
        provider: The LLM provider (openai, anthropic, etc.)
        secret_data: The secret key-value pairs to validate
        credential_type: The type of credential

    Raises:
        CredentialValidationError: If required keys are missing or validation fails
    """
    if not secret_data:
        raise CredentialValidationError("secret_data cannot be empty")

    # Only validate API_KEY credentials with known providers
    if credential_type != CredentialType.API_KEY:
        return

    if provider is None:
        return  # No provider-specific validation

    # Normalize provider to string for lookup
    provider_str = provider.value if isinstance(provider, ModelProvider) else provider

    # Handle Azure separately due to two auth modes
    if provider_str == ModelProvider.AZURE.value:
        _validate_azure_secret_data(secret_data)
        return

    # Get validation rules for provider
    rules = PROVIDER_VALIDATION_RULES.get(provider_str)
    if rules is None:
        # Unknown provider, skip validation
        return

    required_keys, optional_keys = rules
    provided_keys = set(secret_data.keys())

    # Check for missing required keys
    missing_keys = required_keys - provided_keys
    if missing_keys:
        raise CredentialValidationError(
            f"Missing required keys for {provider_str}: {sorted(missing_keys)}",
            missing_keys=sorted(missing_keys),
        )

    # Warn about unexpected keys (but don't fail)
    allowed_keys = required_keys | optional_keys
    if allowed_keys:  # Only check if there are defined allowed keys
        unexpected_keys = provided_keys - allowed_keys
        if unexpected_keys:
            logger.warning(
                f"Unexpected keys in secret_data for {provider_str}: {unexpected_keys}"
            )


def _validate_azure_secret_data(secret_data: dict[str, str]) -> None:
    """Validate Azure secret_data which supports two auth modes.

    Azure supports:
    1. API Key auth: api_key + endpoint (+ optional api_version)
    2. OAuth auth: tenant_id + client_id + client_secret + endpoint (+ optional api_version)

    Args:
        secret_data: The secret key-value pairs to validate

    Raises:
        CredentialValidationError: If neither auth mode requirements are met
    """
    provided_keys = set(secret_data.keys())

    # Check API key mode
    api_key_required, api_key_optional = AZURE_API_KEY_RULES
    api_key_missing = api_key_required - provided_keys

    # Check OAuth mode
    oauth_required, oauth_optional = AZURE_OAUTH_RULES
    oauth_missing = oauth_required - provided_keys

    # If either mode is satisfied, validation passes
    if not api_key_missing:
        return
    if not oauth_missing:
        return

    # Neither mode satisfied - provide helpful error
    raise CredentialValidationError(
        "Azure credentials require either: "
        "(api_key + endpoint) for API key auth, or "
        "(tenant_id + client_id + client_secret + endpoint) for OAuth auth. "
        f"Missing for API key mode: {sorted(api_key_missing)}. "
        f"Missing for OAuth mode: {sorted(oauth_missing)}.",
        missing_keys=sorted(api_key_missing),
    )


class CredentialBackend(ABC):
    """Abstract base class for credential storage backends."""

    @abstractmethod
    def create(
        self,
        credential: Credential,
        secret_data: dict[str, str],
    ) -> Credential:
        """Create a new credential with encrypted secret data."""
        pass

    @abstractmethod
    def get(self, credential_id: str) -> Credential | None:
        """Get credential metadata by ID (no secrets)."""
        pass

    @abstractmethod
    def get_secret(self, credential_id: str) -> dict[str, str] | None:
        """Get decrypted secret data for a credential."""
        pass

    @abstractmethod
    def list_all(
        self,
        owner_id: str | None = None,
        credential_type: CredentialType | None = None,
        provider: str | None = None,
    ) -> list[Credential]:
        """List credentials with optional filtering."""
        pass

    @abstractmethod
    def update(
        self,
        credential_id: str,
        updates: CredentialUpdate,
    ) -> Credential | None:
        """Update credential metadata and/or secret data."""
        pass

    @abstractmethod
    def delete(self, credential_id: str) -> bool:
        """Delete a credential."""
        pass

    @abstractmethod
    def update_last_accessed(self, credential_id: str) -> None:
        """Update the last_accessed_at timestamp."""
        pass


class EncryptedFileBackend(CredentialBackend):
    """File-based credential storage with encryption.

    Stores credentials in encrypted JSON files. Uses Fernet symmetric
    encryption with a key derived from a master secret.

    This backend is suitable for development and single-node deployments.
    For production Kubernetes deployments, use K8sSecretsBackend.
    """

    def __init__(self, settings: Settings) -> None:
        """Initialize the encrypted file backend.

        Args:
            settings: Application settings
        """
        self.settings = settings
        self._credentials_dir = settings.data_dir / "credentials"
        self._metadata_file = self._credentials_dir / "metadata.json"
        self._secrets_dir = self._credentials_dir / "secrets"
        self._lock = threading.RLock()
        self._fernet: Fernet | None = None

        # Ensure directories exist
        self._credentials_dir.mkdir(parents=True, exist_ok=True)
        self._secrets_dir.mkdir(parents=True, exist_ok=True)

        # Initialize metadata file
        if not self._metadata_file.exists():
            self._write_metadata({"credentials": []})

    def _get_encryption_key(self) -> bytes:
        """Derive encryption key from master secret.

        Uses PBKDF2 with the application secret key to derive
        a Fernet-compatible encryption key.
        """
        key_file = self._credentials_dir / ".key"

        if key_file.exists():
            # Load existing salt
            salt = key_file.read_bytes()
        else:
            # Generate new salt
            salt = os.urandom(16)
            key_file.write_bytes(salt)
            # Secure the key file
            key_file.chmod(0o600)

        # Derive key from secret_key and salt
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=480000,
        )
        key = base64.urlsafe_b64encode(
            kdf.derive(self.settings.secret_key.encode())
        )
        return key

    @property
    def fernet(self) -> Fernet:
        """Get the Fernet encryption instance."""
        if self._fernet is None:
            self._fernet = Fernet(self._get_encryption_key())
        return self._fernet

    def _read_metadata(self) -> dict:
        """Read credential metadata from file."""
        with open(self._metadata_file, encoding="utf-8") as f:
            return json.load(f)

    def _write_metadata(self, data: dict) -> None:
        """Write credential metadata to file atomically."""
        temp_path = self._metadata_file.with_suffix(".tmp")
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
        temp_path.replace(self._metadata_file)

    def _get_secret_path(self, credential_id: str) -> Path:
        """Get the path to a credential's encrypted secret file."""
        # Use hash of ID for filename to avoid path traversal
        safe_name = hashlib.sha256(credential_id.encode()).hexdigest()[:16]
        return self._secrets_dir / f"{safe_name}.enc"

    def _encrypt_secret(self, secret_data: dict[str, str]) -> bytes:
        """Encrypt secret data."""
        plaintext = json.dumps(secret_data).encode()
        return self.fernet.encrypt(plaintext)

    def _decrypt_secret(self, encrypted: bytes) -> dict[str, str]:
        """Decrypt secret data."""
        plaintext = self.fernet.decrypt(encrypted)
        return json.loads(plaintext.decode())

    def create(
        self,
        credential: Credential,
        secret_data: dict[str, str],
    ) -> Credential:
        """Create a new credential with encrypted secret data."""
        with self._lock:
            # Store encrypted secret
            secret_path = self._get_secret_path(credential.id)
            encrypted = self._encrypt_secret(secret_data)
            secret_path.write_bytes(encrypted)
            secret_path.chmod(0o600)

            # Store metadata
            data = self._read_metadata()
            data["credentials"].append(
                credential.model_dump(mode="json", by_alias=True)
            )
            self._write_metadata(data)

            logger.info(f"Created credential {credential.id}: {credential.name}")
            return credential

    def get(self, credential_id: str) -> Credential | None:
        """Get credential metadata by ID."""
        with self._lock:
            data = self._read_metadata()
            for cred_data in data["credentials"]:
                if cred_data.get("id") == credential_id:
                    return Credential.model_validate(cred_data)
            return None

    def get_secret(self, credential_id: str) -> dict[str, str] | None:
        """Get decrypted secret data for a credential."""
        with self._lock:
            secret_path = self._get_secret_path(credential_id)
            if not secret_path.exists():
                return None

            try:
                encrypted = secret_path.read_bytes()
                return self._decrypt_secret(encrypted)
            except Exception as e:
                logger.error(f"Failed to decrypt credential {credential_id}: {e}")
                return None

    def list_all(
        self,
        owner_id: str | None = None,
        credential_type: CredentialType | None = None,
        provider: str | None = None,
    ) -> list[Credential]:
        """List credentials with optional filtering."""
        with self._lock:
            data = self._read_metadata()
            credentials = [
                Credential.model_validate(c) for c in data["credentials"]
            ]

            if owner_id is not None:
                credentials = [c for c in credentials if c.owner_id == owner_id]

            if credential_type is not None:
                credentials = [c for c in credentials if c.type == credential_type]

            if provider is not None:
                credentials = [c for c in credentials if c.provider == provider]

            return credentials

    def update(
        self,
        credential_id: str,
        updates: CredentialUpdate,
    ) -> Credential | None:
        """Update credential metadata and/or secret data."""
        with self._lock:
            data = self._read_metadata()

            for i, cred_data in enumerate(data["credentials"]):
                if cred_data.get("id") == credential_id:
                    # Update metadata fields
                    if updates.name is not None:
                        cred_data["name"] = updates.name
                    if updates.description is not None:
                        cred_data["description"] = updates.description
                    if updates.tags is not None:
                        cred_data["tags"] = updates.tags
                    if updates.expires_at is not None:
                        cred_data["expiresAt"] = updates.expires_at.isoformat()

                    cred_data["updatedAt"] = datetime.utcnow().isoformat()

                    # Update secret if provided
                    if updates.secret_data is not None:
                        secret_path = self._get_secret_path(credential_id)
                        encrypted = self._encrypt_secret(updates.secret_data)
                        secret_path.write_bytes(encrypted)

                    data["credentials"][i] = cred_data
                    self._write_metadata(data)

                    logger.info(f"Updated credential {credential_id}")
                    return Credential.model_validate(cred_data)

            return None

    def delete(self, credential_id: str) -> bool:
        """Delete a credential and its secret."""
        with self._lock:
            data = self._read_metadata()
            original_len = len(data["credentials"])

            data["credentials"] = [
                c for c in data["credentials"] if c.get("id") != credential_id
            ]

            if len(data["credentials"]) < original_len:
                self._write_metadata(data)

                # Delete secret file
                secret_path = self._get_secret_path(credential_id)
                if secret_path.exists():
                    secret_path.unlink()

                logger.info(f"Deleted credential {credential_id}")
                return True

            return False

    def update_last_accessed(self, credential_id: str) -> None:
        """Update the last_accessed_at timestamp."""
        with self._lock:
            data = self._read_metadata()

            for cred_data in data["credentials"]:
                if cred_data.get("id") == credential_id:
                    cred_data["lastAccessedAt"] = datetime.utcnow().isoformat()
                    self._write_metadata(data)
                    return


class K8sSecretsBackend(CredentialBackend):
    """Kubernetes Secrets backend for production deployments.

    Stores credentials as Kubernetes Secrets in a configurable namespace.
    Provides native K8s integration with RBAC and audit logging.

    The namespace can be configured via MELLEA_CREDENTIALS_NAMESPACE
    environment variable (defaults to "mellea-credentials").
    """

    LABEL_SELECTOR = "app.kubernetes.io/managed-by=mellea-credentials"

    def __init__(self, settings: Settings | None = None) -> None:
        """Initialize the K8s Secrets backend.

        Args:
            settings: Application settings (optional, uses global if not provided)
        """
        from kubernetes import client, config

        self._settings = settings or get_settings()
        self._namespace = self._settings.credentials_namespace

        try:
            config.load_incluster_config()
            logger.info("Loaded in-cluster K8s config for credentials")
        except config.ConfigException:
            try:
                config.load_kube_config()
                logger.info("Loaded kubeconfig for credentials")
            except config.ConfigException as e:
                raise RuntimeError("No K8s config available") from e

        self._core_api = client.CoreV1Api()
        self._lock = threading.RLock()
        logger.info(f"K8s credentials backend using namespace: {self._namespace}")

    def _secret_name(self, credential_id: str) -> str:
        """Generate K8s Secret name from credential ID."""
        # Use hash prefix for valid K8s name
        safe_id = hashlib.sha256(credential_id.encode()).hexdigest()[:8]
        return f"mellea-cred-{safe_id}"

    def _credential_to_secret(
        self,
        credential: Credential,
        secret_data: dict[str, str],
    ) -> k8s_client.V1Secret:
        """Convert credential to K8s Secret."""
        from kubernetes import client

        # Encode secret data as base64
        encoded_data = {
            k: base64.b64encode(v.encode()).decode()
            for k, v in secret_data.items()
        }

        # Store metadata as annotation
        metadata_json = credential.model_dump_json(by_alias=True)

        return client.V1Secret(
            api_version="v1",
            kind="Secret",
            metadata=client.V1ObjectMeta(
                name=self._secret_name(credential.id),
                namespace=self._namespace,
                labels={
                    "app.kubernetes.io/managed-by": "mellea-credentials",
                    "mellea.io/credential-id": credential.id,
                    "mellea.io/credential-type": credential.type.value,
                },
                annotations={
                    "mellea.io/metadata": metadata_json,
                },
            ),
            type="Opaque",
            data=encoded_data,
        )

    def _secret_to_credential(self, secret: k8s_client.V1Secret) -> Credential:
        """Convert K8s Secret to Credential."""
        metadata_json = secret.metadata.annotations.get("mellea.io/metadata", "{}")
        return Credential.model_validate_json(metadata_json)

    def create(
        self,
        credential: Credential,
        secret_data: dict[str, str],
    ) -> Credential:
        """Create a new credential as K8s Secret."""
        from kubernetes.client.exceptions import ApiException

        with self._lock:
            secret = self._credential_to_secret(credential, secret_data)

            try:
                self._core_api.create_namespaced_secret(
                    namespace=self._namespace,
                    body=secret,
                )
                logger.info(f"Created K8s Secret for credential {credential.id}")
                return credential
            except ApiException as e:
                logger.error(f"Failed to create K8s Secret: {e}")
                raise RuntimeError(f"Failed to create credential: {e.reason}") from e

    def get(self, credential_id: str) -> Credential | None:
        """Get credential metadata from K8s Secret."""
        from kubernetes.client.exceptions import ApiException

        with self._lock:
            try:
                secret = self._core_api.read_namespaced_secret(
                    name=self._secret_name(credential_id),
                    namespace=self._namespace,
                )
                return self._secret_to_credential(secret)
            except ApiException as e:
                if e.status == 404:
                    return None
                raise

    def get_secret(self, credential_id: str) -> dict[str, str] | None:
        """Get decrypted secret data from K8s Secret."""
        from kubernetes.client.exceptions import ApiException

        with self._lock:
            try:
                secret = self._core_api.read_namespaced_secret(
                    name=self._secret_name(credential_id),
                    namespace=self._namespace,
                )
                if secret.data is None:
                    return {}
                return {
                    k: base64.b64decode(v).decode()
                    for k, v in secret.data.items()
                }
            except ApiException as e:
                if e.status == 404:
                    return None
                raise

    def list_all(
        self,
        owner_id: str | None = None,
        credential_type: CredentialType | None = None,
        provider: str | None = None,
    ) -> list[Credential]:
        """List credentials from K8s Secrets."""
        with self._lock:
            label_selector = self.LABEL_SELECTOR

            if credential_type is not None:
                label_selector += f",mellea.io/credential-type={credential_type.value}"

            secrets = self._core_api.list_namespaced_secret(
                namespace=self._namespace,
                label_selector=label_selector,
            )

            credentials = [
                self._secret_to_credential(s) for s in secrets.items
            ]

            if owner_id is not None:
                credentials = [c for c in credentials if c.owner_id == owner_id]

            if provider is not None:
                credentials = [c for c in credentials if c.provider == provider]

            return credentials

    def update(
        self,
        credential_id: str,
        updates: CredentialUpdate,
    ) -> Credential | None:
        """Update K8s Secret with new credential data."""
        from kubernetes.client.exceptions import ApiException

        with self._lock:
            try:
                # Get existing secret
                secret = self._core_api.read_namespaced_secret(
                    name=self._secret_name(credential_id),
                    namespace=self._namespace,
                )
                credential = self._secret_to_credential(secret)

                # Apply updates to credential
                if updates.name is not None:
                    credential.name = updates.name
                if updates.description is not None:
                    credential.description = updates.description
                if updates.tags is not None:
                    credential.tags = updates.tags
                if updates.expires_at is not None:
                    credential.expires_at = updates.expires_at
                credential.updated_at = datetime.utcnow()

                # Update secret data if provided
                if updates.secret_data is not None:
                    secret.data = {
                        k: base64.b64encode(v.encode()).decode()
                        for k, v in updates.secret_data.items()
                    }

                # Update metadata annotation
                secret.metadata.annotations["mellea.io/metadata"] = (
                    credential.model_dump_json(by_alias=True)
                )

                self._core_api.replace_namespaced_secret(
                    name=self._secret_name(credential_id),
                    namespace=self._namespace,
                    body=secret,
                )

                logger.info(f"Updated K8s Secret for credential {credential_id}")
                return credential

            except ApiException as e:
                if e.status == 404:
                    return None
                raise

    def delete(self, credential_id: str) -> bool:
        """Delete K8s Secret."""
        from kubernetes.client.exceptions import ApiException

        with self._lock:
            try:
                self._core_api.delete_namespaced_secret(
                    name=self._secret_name(credential_id),
                    namespace=self._namespace,
                )
                logger.info(f"Deleted K8s Secret for credential {credential_id}")
                return True
            except ApiException as e:
                if e.status == 404:
                    return False
                raise

    def update_last_accessed(self, credential_id: str) -> None:
        """Update last_accessed_at in K8s Secret annotation."""
        from kubernetes.client.exceptions import ApiException

        with self._lock:
            try:
                secret = self._core_api.read_namespaced_secret(
                    name=self._secret_name(credential_id),
                    namespace=self._namespace,
                )
                credential = self._secret_to_credential(secret)
                credential.last_accessed_at = datetime.utcnow()

                secret.metadata.annotations["mellea.io/metadata"] = (
                    credential.model_dump_json(by_alias=True)
                )

                self._core_api.replace_namespaced_secret(
                    name=self._secret_name(credential_id),
                    namespace=self._namespace,
                    body=secret,
                )
            except ApiException:
                pass  # Non-critical update


def _is_k8s_environment() -> bool:
    """Check if running in a Kubernetes environment."""
    return os.path.exists("/var/run/secrets/kubernetes.io/serviceaccount")


class CredentialService:
    """Service for secure credential management.

    Provides a unified interface for storing and retrieving credentials,
    abstracting the underlying storage backend (encrypted files or K8s Secrets).

    Example:
        ```python
        service = get_credential_service()

        # Create a credential
        cred = service.create_credential(
            name="OpenAI API Key",
            credential_type=CredentialType.API_KEY,
            secret_data={"api_key": "sk-..."},
            provider="openai",
        )

        # Get secret value
        secret = service.get_secret_value(cred.id)
        api_key = secret["api_key"]

        # Delete when done
        service.delete_credential(cred.id)
        ```
    """

    def __init__(
        self,
        settings: Settings | None = None,
        backend: CredentialBackend | None = None,
    ) -> None:
        """Initialize the CredentialService.

        Args:
            settings: Application settings
            backend: Optional backend override (for testing)
        """
        self.settings = settings or get_settings()
        self._backend = backend

    @property
    def backend(self) -> CredentialBackend:
        """Get the credential storage backend."""
        if self._backend is None:
            if _is_k8s_environment():
                try:
                    self._backend = K8sSecretsBackend(self.settings)
                    logger.info("Using K8s Secrets backend for credentials")
                except RuntimeError:
                    logger.warning(
                        "K8s environment detected but secrets unavailable, "
                        "falling back to encrypted file backend"
                    )
                    self._backend = EncryptedFileBackend(self.settings)
            else:
                self._backend = EncryptedFileBackend(self.settings)
                logger.info("Using encrypted file backend for credentials")
        return self._backend

    def create_credential(
        self,
        name: str,
        credential_type: CredentialType,
        secret_data: dict[str, str],
        provider: str | None = None,
        owner_id: str | None = None,
        description: str = "",
        tags: list[str] | None = None,
        expires_at: datetime | None = None,
    ) -> Credential:
        """Create a new credential.

        Args:
            name: Human-readable name
            credential_type: Type of credential
            secret_data: Secret key-value pairs to store
            provider: Associated provider (openai, anthropic, etc.)
            owner_id: ID of owning user
            description: Optional description
            tags: Optional tags
            expires_at: Optional expiration time

        Returns:
            The created Credential

        Raises:
            CredentialValidationError: If secret_data fails provider validation
        """
        # Validate secret_data against provider requirements
        validate_secret_data(provider, secret_data, credential_type)

        credential = Credential(
            name=name,
            type=credential_type,
            provider=provider,
            ownerId=owner_id,
            description=description,
            tags=tags or [],
            expiresAt=expires_at,
        )

        return self.backend.create(credential, secret_data)

    def get_credential(self, credential_id: str) -> Credential | None:
        """Get credential metadata by ID.

        Note: This does NOT return the secret data. Use get_secret_value()
        to retrieve the actual secrets.

        Args:
            credential_id: Credential's unique identifier

        Returns:
            Credential if found, None otherwise
        """
        return self.backend.get(credential_id)

    def get_secret_value(
        self,
        credential_id: str,
        key: str | None = None,
    ) -> dict[str, str] | str | None:
        """Get decrypted secret value(s) for a credential.

        Args:
            credential_id: Credential's unique identifier
            key: Optional specific key to retrieve

        Returns:
            If key is None: dict of all secret data
            If key is provided: the specific value or None
            None if credential not found
        """
        secret_data = self.backend.get_secret(credential_id)

        if secret_data is None:
            return None

        # Update last accessed time (non-blocking)
        with contextlib.suppress(Exception):
            self.backend.update_last_accessed(credential_id)

        if key is not None:
            return secret_data.get(key)

        return secret_data

    def resolve_credentials_ref(
        self,
        credentials_ref: str,
    ) -> dict[str, str] | None:
        """Resolve a credentials_ref to actual secret data.

        This is used by ModelAsset and other components that store
        credential references.

        Args:
            credentials_ref: The credential ID reference

        Returns:
            Decrypted secret data or None if not found
        """
        # Call with key=None to get full dict
        result = self.get_secret_value(credentials_ref, key=None)
        if result is None or isinstance(result, dict):
            return result
        return None  # Defensive fallback

    def list_credentials(
        self,
        owner_id: str | None = None,
        credential_type: CredentialType | None = None,
        provider: str | None = None,
    ) -> list[Credential]:
        """List credentials with optional filtering.

        Args:
            owner_id: Filter by owner
            credential_type: Filter by type
            provider: Filter by provider

        Returns:
            List of matching credentials (without secrets)
        """
        return self.backend.list_all(owner_id, credential_type, provider)

    def update_credential(
        self,
        credential_id: str,
        name: str | None = None,
        description: str | None = None,
        secret_data: dict[str, str] | None = None,
        tags: list[str] | None = None,
        expires_at: datetime | None = None,
    ) -> Credential:
        """Update a credential.

        Args:
            credential_id: Credential to update
            name: New name (optional)
            description: New description (optional)
            secret_data: New secret data (optional)
            tags: New tags (optional)
            expires_at: New expiration (optional)

        Returns:
            Updated Credential

        Raises:
            CredentialNotFoundError: If credential doesn't exist
            CredentialValidationError: If secret_data fails provider validation
        """
        # If updating secret_data, validate against existing credential's provider
        if secret_data is not None:
            existing = self.backend.get(credential_id)
            if existing is None:
                raise CredentialNotFoundError(f"Credential not found: {credential_id}")
            validate_secret_data(existing.provider, secret_data, existing.type)

        updates = CredentialUpdate(
            name=name,
            description=description,
            secretData=secret_data,
            tags=tags,
            expiresAt=expires_at,
        )

        result = self.backend.update(credential_id, updates)

        if result is None:
            raise CredentialNotFoundError(f"Credential not found: {credential_id}")

        return result

    def delete_credential(self, credential_id: str) -> bool:
        """Delete a credential.

        Args:
            credential_id: Credential to delete

        Returns:
            True if deleted, False if not found
        """
        return self.backend.delete(credential_id)

    def validate_credential(self, credential_id: str) -> bool:
        """Check if a credential exists and is not expired.

        Args:
            credential_id: Credential to validate

        Returns:
            True if valid, False otherwise
        """
        credential = self.backend.get(credential_id)

        if credential is None:
            return False

        return not credential.is_expired

    def get_k8s_secret_name(self, credential_id: str) -> str | None:
        """Get the Kubernetes Secret name for a credential.

        This returns the K8s Secret name that corresponds to the credential,
        following the same naming convention used by K8sSecretsBackend.

        Args:
            credential_id: Credential's unique identifier

        Returns:
            K8s Secret name (e.g., 'mellea-cred-abc12345') or None if not found
        """
        # Verify credential exists
        credential = self.backend.get(credential_id)
        if credential is None:
            return None

        # Generate K8s secret name using same logic as K8sSecretsBackend
        safe_id = hashlib.sha256(credential_id.encode()).hexdigest()[:8]
        return f"mellea-cred-{safe_id}"


# Global service instance
_credential_service: CredentialService | None = None


def get_credential_service() -> CredentialService:
    """Get the global CredentialService instance."""
    global _credential_service
    if _credential_service is None:
        _credential_service = CredentialService()
    return _credential_service
