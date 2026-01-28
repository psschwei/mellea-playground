"""Tests for CredentialService and encrypted file backend."""

import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from mellea_api.core.config import Settings
from mellea_api.models.common import CredentialType, ModelProvider
from mellea_api.models.credential import Credential, CredentialUpdate
from mellea_api.services.credentials import (
    ConnectionTestResult,
    CredentialNotFoundError,
    CredentialService,
    CredentialValidationError,
    EncryptedFileBackend,
    register_format_validator,
    validate_api_key_format,
    validate_secret_data,
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

    # Valid-format test keys for use in tests
    VALID_OPENAI_KEY = "sk-proj-abcdefghijklmnopqrstuvwxyz"
    VALID_ANTHROPIC_KEY = "sk-ant-api03-abcdefghijklmnopqrstuvwxyz"

    def test_create_credential(self, credential_service: CredentialService):
        """Test creating a credential through the service."""
        cred = credential_service.create_credential(
            name="OpenAI Key",
            credential_type=CredentialType.API_KEY,
            secret_data={"api_key": self.VALID_OPENAI_KEY},
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


class TestProviderValidation:
    """Tests for provider-specific secret_data validation."""

    # Valid-format test keys
    VALID_OPENAI_KEY = "sk-proj-abcdefghijklmnopqrstuvwxyz"
    VALID_ANTHROPIC_KEY = "sk-ant-api03-abcdefghijklmnopqrstuvwxyz"

    def test_openai_valid(self):
        """Test valid OpenAI credentials."""
        validate_secret_data(
            ModelProvider.OPENAI,
            {"api_key": self.VALID_OPENAI_KEY},
        )
        # Should not raise

    def test_openai_with_org_id(self):
        """Test OpenAI credentials with optional organization_id."""
        validate_secret_data(
            ModelProvider.OPENAI,
            {"api_key": self.VALID_OPENAI_KEY, "organization_id": "org-123"},
        )
        # Should not raise

    def test_openai_missing_api_key(self):
        """Test OpenAI credentials missing required api_key."""
        with pytest.raises(CredentialValidationError) as exc_info:
            validate_secret_data(
                ModelProvider.OPENAI,
                {"organization_id": "org-123"},
            )
        assert "api_key" in exc_info.value.missing_keys

    def test_anthropic_valid(self):
        """Test valid Anthropic credentials."""
        validate_secret_data(
            ModelProvider.ANTHROPIC,
            {"api_key": self.VALID_ANTHROPIC_KEY},
        )
        # Should not raise

    def test_anthropic_missing_api_key(self):
        """Test Anthropic credentials missing required api_key."""
        with pytest.raises(CredentialValidationError) as exc_info:
            validate_secret_data(
                ModelProvider.ANTHROPIC,
                {"other_key": "value"},
            )
        assert "api_key" in exc_info.value.missing_keys

    def test_azure_api_key_mode(self):
        """Test Azure credentials with API key mode."""
        validate_secret_data(
            ModelProvider.AZURE,
            {"api_key": "test-key", "endpoint": "https://test.openai.azure.com"},
        )
        # Should not raise

    def test_azure_api_key_mode_with_version(self):
        """Test Azure credentials with API key mode and optional api_version."""
        validate_secret_data(
            ModelProvider.AZURE,
            {
                "api_key": "test-key",
                "endpoint": "https://test.openai.azure.com",
                "api_version": "2024-02-01",
            },
        )
        # Should not raise

    def test_azure_oauth_mode(self):
        """Test Azure credentials with OAuth mode."""
        validate_secret_data(
            ModelProvider.AZURE,
            {
                "tenant_id": "tenant-123",
                "client_id": "client-456",
                "client_secret": "secret-789",
                "endpoint": "https://test.openai.azure.com",
            },
        )
        # Should not raise

    def test_azure_missing_both_modes(self):
        """Test Azure credentials missing requirements for both modes."""
        with pytest.raises(CredentialValidationError) as exc_info:
            validate_secret_data(
                ModelProvider.AZURE,
                {"endpoint": "https://test.openai.azure.com"},
            )
        assert "api_key" in exc_info.value.message
        assert "tenant_id" in exc_info.value.message

    def test_ollama_no_auth(self):
        """Test Ollama credentials with no authentication (typical)."""
        validate_secret_data(
            ModelProvider.OLLAMA,
            {"some_config": "value"},
        )
        # Should not raise - Ollama has no required keys

    def test_ollama_with_api_key(self):
        """Test Ollama credentials with optional api_key."""
        validate_secret_data(
            ModelProvider.OLLAMA,
            {"api_key": "optional-key"},
        )
        # Should not raise

    def test_custom_provider_no_validation(self):
        """Test custom provider has no strict validation."""
        validate_secret_data(
            ModelProvider.CUSTOM,
            {"anything": "goes", "custom_field": "value"},
        )
        # Should not raise

    def test_none_provider_no_validation(self):
        """Test None provider skips validation."""
        validate_secret_data(
            None,
            {"any": "data"},
        )
        # Should not raise

    def test_string_provider(self):
        """Test validation works with string provider value."""
        validate_secret_data(
            "openai",
            {"api_key": self.VALID_OPENAI_KEY},
        )
        # Should not raise

    def test_empty_secret_data(self):
        """Test empty secret_data raises error."""
        with pytest.raises(CredentialValidationError) as exc_info:
            validate_secret_data(
                ModelProvider.OPENAI,
                {},
            )
        assert "cannot be empty" in exc_info.value.message

    def test_non_api_key_type_skips_validation(self):
        """Test non-API_KEY credential types skip provider validation."""
        # This would fail for OpenAI if validated, but REGISTRY type skips it
        validate_secret_data(
            ModelProvider.OPENAI,
            {"username": "user", "password": "pass"},
            credential_type=CredentialType.REGISTRY,
        )
        # Should not raise


class TestServiceValidation:
    """Tests for validation integration in CredentialService."""

    # Valid-format test keys
    VALID_OPENAI_KEY = "sk-proj-abcdefghijklmnopqrstuvwxyz"

    def test_create_credential_validates(self, credential_service: CredentialService):
        """Test that create_credential validates secret_data."""
        with pytest.raises(CredentialValidationError):
            credential_service.create_credential(
                name="Invalid OpenAI",
                credential_type=CredentialType.API_KEY,
                secret_data={"wrong_key": "value"},
                provider=ModelProvider.OPENAI,
            )

    def test_create_credential_valid(self, credential_service: CredentialService):
        """Test creating credential with valid secret_data."""
        cred = credential_service.create_credential(
            name="Valid OpenAI",
            credential_type=CredentialType.API_KEY,
            secret_data={"api_key": self.VALID_OPENAI_KEY},
            provider=ModelProvider.OPENAI,
        )
        assert cred.name == "Valid OpenAI"

    def test_update_credential_validates(self, credential_service: CredentialService):
        """Test that update_credential validates new secret_data."""
        # Create valid credential first
        cred = credential_service.create_credential(
            name="Test",
            credential_type=CredentialType.API_KEY,
            secret_data={"api_key": self.VALID_OPENAI_KEY},
            provider=ModelProvider.OPENAI,
        )

        # Try to update with invalid secret_data
        with pytest.raises(CredentialValidationError):
            credential_service.update_credential(
                credential_id=cred.id,
                secret_data={"wrong_key": "value"},
            )

    def test_update_credential_metadata_no_validation(
        self, credential_service: CredentialService
    ):
        """Test updating only metadata doesn't trigger validation."""
        cred = credential_service.create_credential(
            name="Test",
            credential_type=CredentialType.API_KEY,
            secret_data={"api_key": self.VALID_OPENAI_KEY},
            provider=ModelProvider.OPENAI,
        )

        # Update only name - should not validate secret_data
        updated = credential_service.update_credential(
            credential_id=cred.id,
            name="New Name",
        )
        assert updated.name == "New Name"


class TestApiKeyFormatValidation:
    """Tests for API key format validation."""

    def test_openai_valid_format(self):
        """Test valid OpenAI API key format."""
        is_valid, error = validate_api_key_format(
            "openai", "api_key", "sk-proj-abcdefghijklmnopqrstuvwxyz"
        )
        assert is_valid is True
        assert error is None

    def test_openai_valid_format_no_proj(self):
        """Test valid OpenAI API key format without proj prefix."""
        is_valid, error = validate_api_key_format(
            "openai", "api_key", "sk-abcdefghijklmnopqrstuvwxyz123456"
        )
        assert is_valid is True
        assert error is None

    def test_openai_invalid_format_wrong_prefix(self):
        """Test OpenAI API key with wrong prefix."""
        is_valid, error = validate_api_key_format(
            "openai", "api_key", "invalid-key-format"
        )
        assert is_valid is False
        assert error is not None
        assert "sk-" in error

    def test_openai_invalid_format_too_short(self):
        """Test OpenAI API key that's too short."""
        is_valid, error = validate_api_key_format(
            "openai", "api_key", "sk-short"
        )
        assert is_valid is False
        assert error is not None

    def test_anthropic_valid_format(self):
        """Test valid Anthropic API key format."""
        is_valid, error = validate_api_key_format(
            "anthropic", "api_key", "sk-ant-api03-abcdefghijklmnopqrstuvwxyz"
        )
        assert is_valid is True
        assert error is None

    def test_anthropic_valid_admin_format(self):
        """Test valid Anthropic admin API key format."""
        is_valid, error = validate_api_key_format(
            "anthropic", "api_key", "sk-ant-admin01-abcdefghijklmnopqrstuvwxyz"
        )
        assert is_valid is True
        assert error is None

    def test_anthropic_invalid_format(self):
        """Test Anthropic API key with wrong format."""
        is_valid, error = validate_api_key_format(
            "anthropic", "api_key", "sk-wrong-format"
        )
        assert is_valid is False
        assert error is not None
        assert "sk-ant" in error

    def test_unknown_provider_passes(self):
        """Test unknown provider passes validation."""
        is_valid, error = validate_api_key_format(
            "unknown-provider", "api_key", "any-format"
        )
        assert is_valid is True
        assert error is None

    def test_unknown_key_passes(self):
        """Test unknown key name passes validation."""
        is_valid, error = validate_api_key_format(
            "openai", "organization_id", "org-123"
        )
        assert is_valid is True
        assert error is None

    def test_register_custom_validator(self):
        """Test registering a custom format validator."""
        register_format_validator(
            provider="my-provider",
            key_name="api_key",
            pattern=r"^mp-[a-z0-9]{16}$",
            description="MyProvider key must start with 'mp-' followed by 16 alphanumeric chars",
            example="mp-abc123def456xyz0",
        )

        # Valid key
        is_valid, error = validate_api_key_format(
            "my-provider", "api_key", "mp-abcdefgh12345678"
        )
        assert is_valid is True

        # Invalid key
        is_valid, error = validate_api_key_format(
            "my-provider", "api_key", "wrong-format"
        )
        assert is_valid is False
        assert "mp-" in error


class TestFormatValidationIntegration:
    """Tests for format validation integrated with validate_secret_data."""

    def test_validate_secret_data_with_format(self):
        """Test validate_secret_data includes format validation."""
        # Valid format passes
        validate_secret_data(
            ModelProvider.OPENAI,
            {"api_key": "sk-proj-abcdefghijklmnopqrstuvwxyz"},
        )
        # Should not raise

    def test_validate_secret_data_invalid_format_raises(self):
        """Test validate_secret_data raises on invalid format."""
        with pytest.raises(CredentialValidationError) as exc_info:
            validate_secret_data(
                ModelProvider.OPENAI,
                {"api_key": "invalid-format-key"},
            )
        assert "Invalid format" in exc_info.value.message
        assert exc_info.value.invalid_format.get("api_key") is not None

    def test_validate_secret_data_format_disabled(self):
        """Test format validation can be disabled."""
        # This would fail format validation but passes with it disabled
        validate_secret_data(
            ModelProvider.OPENAI,
            {"api_key": "sk-short"},  # Too short but passes required key check
            validate_format=False,
        )
        # Should not raise

    def test_anthropic_format_validation(self):
        """Test Anthropic format validation in validate_secret_data."""
        with pytest.raises(CredentialValidationError) as exc_info:
            validate_secret_data(
                ModelProvider.ANTHROPIC,
                {"api_key": "sk-wrong-format"},
            )
        assert "Invalid format" in exc_info.value.message

    def test_custom_provider_skips_format(self):
        """Test custom provider skips format validation."""
        validate_secret_data(
            ModelProvider.CUSTOM,
            {"api_key": "any-format-allowed"},
        )
        # Should not raise

    def test_ollama_skips_format(self):
        """Test Ollama skips format validation (no format rules)."""
        validate_secret_data(
            ModelProvider.OLLAMA,
            {"api_key": "any-optional-key"},
        )
        # Should not raise


class TestConnectionTestResult:
    """Tests for ConnectionTestResult dataclass."""

    def test_success_result(self):
        """Test creating a success result."""
        result = ConnectionTestResult(
            success=True,
            message="Connected successfully",
            provider="openai",
            response_time_ms=123.45,
        )
        assert result.success is True
        assert result.provider == "openai"
        assert result.response_time_ms == 123.45

    def test_failure_result(self):
        """Test creating a failure result."""
        result = ConnectionTestResult(
            success=False,
            message="Invalid API key",
            provider="anthropic",
        )
        assert result.success is False
        assert result.response_time_ms is None
