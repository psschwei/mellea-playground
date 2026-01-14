"""Tests for CredentialService and encrypted file backend."""

import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from mellea_api.core.config import Settings
from mellea_api.models.common import CredentialType, ModelProvider
from mellea_api.models.credential import Credential, CredentialUpdate
from mellea_api.services.credentials import (
    CredentialNotFoundError,
    CredentialService,
    EncryptedFileBackend,
)


@pytest.fixture
def temp_data_dir():
    """Create a temporary data directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def settings(temp_data_dir: Path):
    """Create test settings with temporary data directory."""
    settings = Settings(
        data_dir=temp_data_dir,
        secret_key="test-secret-key-for-encryption-12345",
    )
    settings.ensure_data_dirs()
    return settings


@pytest.fixture
def backend(settings: Settings):
    """Create an EncryptedFileBackend with test settings."""
    return EncryptedFileBackend(settings)


@pytest.fixture
def credential_service(settings: Settings):
    """Create a CredentialService with test settings."""
    backend = EncryptedFileBackend(settings)
    return CredentialService(settings=settings, backend=backend)


class TestEncryptedFileBackend:
    """Tests for the encrypted file backend."""

    def test_create_credential(self, backend: EncryptedFileBackend):
        """Test creating a credential."""
        credential = Credential(
            name="Test API Key",
            type=CredentialType.API_KEY,
            provider=ModelProvider.OPENAI,
            ownerId="user-123",
        )
        secret_data = {"api_key": "sk-test-key-12345"}

        result = backend.create(credential, secret_data)

        assert result.id == credential.id
        assert result.name == "Test API Key"
        assert result.type == CredentialType.API_KEY

    def test_get_credential(self, backend: EncryptedFileBackend):
        """Test retrieving credential metadata."""
        credential = Credential(
            name="Test Key",
            type=CredentialType.API_KEY,
            provider=ModelProvider.ANTHROPIC,
        )
        backend.create(credential, {"api_key": "test-key"})

        result = backend.get(credential.id)

        assert result is not None
        assert result.id == credential.id
        assert result.name == "Test Key"

    def test_get_nonexistent_credential(self, backend: EncryptedFileBackend):
        """Test getting a credential that doesn't exist."""
        result = backend.get("nonexistent-id")
        assert result is None

    def test_get_secret(self, backend: EncryptedFileBackend):
        """Test retrieving decrypted secret data."""
        credential = Credential(
            name="Test Key",
            type=CredentialType.API_KEY,
        )
        secret_data = {"api_key": "sk-secret-123", "org_id": "org-456"}
        backend.create(credential, secret_data)

        result = backend.get_secret(credential.id)

        assert result is not None
        assert result["api_key"] == "sk-secret-123"
        assert result["org_id"] == "org-456"

    def test_get_secret_nonexistent(self, backend: EncryptedFileBackend):
        """Test getting secret for nonexistent credential."""
        result = backend.get_secret("nonexistent-id")
        assert result is None

    def test_list_all_credentials(self, backend: EncryptedFileBackend):
        """Test listing all credentials."""
        cred1 = Credential(name="Key 1", type=CredentialType.API_KEY)
        cred2 = Credential(name="Key 2", type=CredentialType.REGISTRY)
        backend.create(cred1, {"key": "value1"})
        backend.create(cred2, {"key": "value2"})

        result = backend.list_all()

        assert len(result) == 2

    def test_list_filter_by_type(self, backend: EncryptedFileBackend):
        """Test filtering credentials by type."""
        cred1 = Credential(name="API Key", type=CredentialType.API_KEY)
        cred2 = Credential(name="Registry", type=CredentialType.REGISTRY)
        backend.create(cred1, {"key": "value1"})
        backend.create(cred2, {"key": "value2"})

        result = backend.list_all(credential_type=CredentialType.API_KEY)

        assert len(result) == 1
        assert result[0].type == CredentialType.API_KEY

    def test_list_filter_by_owner(self, backend: EncryptedFileBackend):
        """Test filtering credentials by owner."""
        cred1 = Credential(name="Key 1", type=CredentialType.API_KEY, ownerId="user-1")
        cred2 = Credential(name="Key 2", type=CredentialType.API_KEY, ownerId="user-2")
        backend.create(cred1, {"key": "value1"})
        backend.create(cred2, {"key": "value2"})

        result = backend.list_all(owner_id="user-1")

        assert len(result) == 1
        assert result[0].owner_id == "user-1"

    def test_update_credential_metadata(self, backend: EncryptedFileBackend):
        """Test updating credential metadata."""
        credential = Credential(name="Old Name", type=CredentialType.API_KEY)
        backend.create(credential, {"key": "value"})

        updates = CredentialUpdate(name="New Name", description="Updated desc")
        result = backend.update(credential.id, updates)

        assert result is not None
        assert result.name == "New Name"
        assert result.description == "Updated desc"

    def test_update_credential_secret(self, backend: EncryptedFileBackend):
        """Test rotating credential secret."""
        credential = Credential(name="Test Key", type=CredentialType.API_KEY)
        backend.create(credential, {"api_key": "old-key"})

        updates = CredentialUpdate(secretData={"api_key": "new-key"})
        backend.update(credential.id, updates)

        # Verify new secret
        secret = backend.get_secret(credential.id)
        assert secret is not None
        assert secret["api_key"] == "new-key"

    def test_update_nonexistent_credential(self, backend: EncryptedFileBackend):
        """Test updating a credential that doesn't exist."""
        updates = CredentialUpdate(name="New Name")
        result = backend.update("nonexistent-id", updates)
        assert result is None

    def test_delete_credential(self, backend: EncryptedFileBackend):
        """Test deleting a credential."""
        credential = Credential(name="Test Key", type=CredentialType.API_KEY)
        backend.create(credential, {"key": "value"})

        result = backend.delete(credential.id)

        assert result is True
        assert backend.get(credential.id) is None
        assert backend.get_secret(credential.id) is None

    def test_delete_nonexistent_credential(self, backend: EncryptedFileBackend):
        """Test deleting a credential that doesn't exist."""
        result = backend.delete("nonexistent-id")
        assert result is False

    def test_encryption_persists_across_instances(
        self, settings: Settings, backend: EncryptedFileBackend
    ):
        """Test that encrypted data can be read by a new backend instance."""
        credential = Credential(name="Test Key", type=CredentialType.API_KEY)
        secret_data = {"api_key": "sk-secret-key"}
        backend.create(credential, secret_data)

        # Create new backend instance
        new_backend = EncryptedFileBackend(settings)

        # Should be able to read the credential
        cred = new_backend.get(credential.id)
        assert cred is not None
        assert cred.name == "Test Key"

        # Should be able to decrypt the secret
        secret = new_backend.get_secret(credential.id)
        assert secret is not None
        assert secret["api_key"] == "sk-secret-key"


class TestCredentialService:
    """Tests for the CredentialService."""

    def test_create_credential(self, credential_service: CredentialService):
        """Test creating a credential through the service."""
        cred = credential_service.create_credential(
            name="OpenAI Key",
            credential_type=CredentialType.API_KEY,
            secret_data={"api_key": "sk-test"},
            provider="openai",
            owner_id="user-123",
            description="Production API key",
            tags=["production", "openai"],
        )

        assert cred.name == "OpenAI Key"
        assert cred.type == CredentialType.API_KEY
        assert cred.provider == "openai"
        assert cred.owner_id == "user-123"
        assert "production" in cred.tags

    def test_get_credential(self, credential_service: CredentialService):
        """Test getting credential metadata."""
        cred = credential_service.create_credential(
            name="Test Key",
            credential_type=CredentialType.API_KEY,
            secret_data={"api_key": "test"},
        )

        result = credential_service.get_credential(cred.id)

        assert result is not None
        assert result.id == cred.id

    def test_get_secret_value_all(self, credential_service: CredentialService):
        """Test getting all secret values."""
        cred = credential_service.create_credential(
            name="Test Key",
            credential_type=CredentialType.API_KEY,
            secret_data={"api_key": "sk-123", "org_id": "org-456"},
        )

        result = credential_service.get_secret_value(cred.id)

        assert result == {"api_key": "sk-123", "org_id": "org-456"}

    def test_get_secret_value_specific_key(self, credential_service: CredentialService):
        """Test getting a specific secret value."""
        cred = credential_service.create_credential(
            name="Test Key",
            credential_type=CredentialType.API_KEY,
            secret_data={"api_key": "sk-123", "org_id": "org-456"},
        )

        result = credential_service.get_secret_value(cred.id, key="api_key")

        assert result == "sk-123"

    def test_resolve_credentials_ref(self, credential_service: CredentialService):
        """Test resolving a credentials_ref."""
        cred = credential_service.create_credential(
            name="Model Key",
            credential_type=CredentialType.API_KEY,
            secret_data={"api_key": "sk-model-key"},
        )

        result = credential_service.resolve_credentials_ref(cred.id)

        assert result is not None
        assert result["api_key"] == "sk-model-key"

    def test_list_credentials(self, credential_service: CredentialService):
        """Test listing credentials."""
        credential_service.create_credential(
            name="Key 1",
            credential_type=CredentialType.API_KEY,
            secret_data={"key": "1"},
            owner_id="user-1",
        )
        credential_service.create_credential(
            name="Key 2",
            credential_type=CredentialType.REGISTRY,
            secret_data={"key": "2"},
            owner_id="user-1",
        )

        result = credential_service.list_credentials(owner_id="user-1")

        assert len(result) == 2

    def test_update_credential(self, credential_service: CredentialService):
        """Test updating a credential."""
        cred = credential_service.create_credential(
            name="Old Name",
            credential_type=CredentialType.API_KEY,
            secret_data={"api_key": "old-key"},
        )

        updated = credential_service.update_credential(
            credential_id=cred.id,
            name="New Name",
            secret_data={"api_key": "new-key"},
        )

        assert updated.name == "New Name"

        # Verify secret was updated
        secret = credential_service.get_secret_value(cred.id)
        assert secret == {"api_key": "new-key"}

    def test_update_nonexistent_credential(self, credential_service: CredentialService):
        """Test updating a credential that doesn't exist."""
        with pytest.raises(CredentialNotFoundError):
            credential_service.update_credential(
                credential_id="nonexistent",
                name="New Name",
            )

    def test_delete_credential(self, credential_service: CredentialService):
        """Test deleting a credential."""
        cred = credential_service.create_credential(
            name="Test Key",
            credential_type=CredentialType.API_KEY,
            secret_data={"key": "value"},
        )

        result = credential_service.delete_credential(cred.id)

        assert result is True
        assert credential_service.get_credential(cred.id) is None

    def test_validate_credential_valid(self, credential_service: CredentialService):
        """Test validating a valid credential."""
        cred = credential_service.create_credential(
            name="Test Key",
            credential_type=CredentialType.API_KEY,
            secret_data={"key": "value"},
        )

        assert credential_service.validate_credential(cred.id) is True

    def test_validate_credential_expired(self, credential_service: CredentialService):
        """Test validating an expired credential."""
        cred = credential_service.create_credential(
            name="Expired Key",
            credential_type=CredentialType.API_KEY,
            secret_data={"key": "value"},
            expires_at=datetime.utcnow() - timedelta(days=1),
        )

        assert credential_service.validate_credential(cred.id) is False

    def test_validate_credential_nonexistent(
        self, credential_service: CredentialService
    ):
        """Test validating a nonexistent credential."""
        assert credential_service.validate_credential("nonexistent") is False


class TestCredentialModel:
    """Tests for the Credential model."""

    def test_is_expired_not_set(self):
        """Test is_expired when expires_at is not set."""
        cred = Credential(name="Test", type=CredentialType.API_KEY)
        assert cred.is_expired is False

    def test_is_expired_future(self):
        """Test is_expired when expires_at is in the future."""
        cred = Credential(
            name="Test",
            type=CredentialType.API_KEY,
            expiresAt=datetime.utcnow() + timedelta(days=30),
        )
        assert cred.is_expired is False

    def test_is_expired_past(self):
        """Test is_expired when expires_at is in the past."""
        cred = Credential(
            name="Test",
            type=CredentialType.API_KEY,
            expiresAt=datetime.utcnow() - timedelta(days=1),
        )
        assert cred.is_expired is True
