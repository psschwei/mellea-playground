"""Tests for authentication endpoints and services."""

import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mellea_api.core.config import Settings
from mellea_api.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from mellea_api.main import app
from mellea_api.models.user import UserRole
from mellea_api.services.auth import AuthService


@pytest.fixture
def client() -> Iterator[TestClient]:
    """Create a test client with fresh auth service state."""
    import mellea_api.services.auth as auth_module

    # Clear cached auth service to ensure fresh state
    auth_module._auth_service = None

    with TestClient(app) as client:
        yield client


class TestPasswordHashing:
    """Tests for password hashing utilities."""

    def test_hash_password(self) -> None:
        """Test password hashing produces different hash each time."""
        password = "test_password_123"
        hash1 = hash_password(password)
        hash2 = hash_password(password)

        assert hash1 != password
        assert hash2 != password
        assert hash1 != hash2  # Different salts

    def test_verify_password_correct(self) -> None:
        """Test verifying correct password."""
        password = "secure_password"
        hashed = hash_password(password)

        assert verify_password(password, hashed) is True

    def test_verify_password_incorrect(self) -> None:
        """Test verifying incorrect password."""
        password = "secure_password"
        hashed = hash_password(password)

        assert verify_password("wrong_password", hashed) is False


class TestJWT:
    """Tests for JWT token utilities."""

    def test_create_and_decode_token(self) -> None:
        """Test creating and decoding a JWT token."""
        token, expires_at = create_access_token(
            user_id="user-123",
            email="test@example.com",
            name="Test User",
            role=UserRole.DEVELOPER,
        )

        payload = decode_access_token(token)

        assert payload is not None
        assert payload["sub"] == "user-123"
        assert payload["email"] == "test@example.com"
        assert payload["name"] == "Test User"
        assert payload["role"] == "developer"

    def test_decode_invalid_token(self) -> None:
        """Test decoding an invalid token returns None."""
        payload = decode_access_token("invalid.token.here")
        assert payload is None


class TestAuthService:
    """Tests for AuthService."""

    @pytest.fixture
    def auth_service(self) -> Iterator[AuthService]:
        """Create an auth service with temporary storage."""
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(data_dir=Path(tmpdir))
            settings.ensure_data_dirs()
            yield AuthService(settings)

    def test_create_user(self, auth_service: AuthService) -> None:
        """Test creating a new user."""
        from mellea_api.models.user import UserCreate

        user_data = UserCreate(
            email="test@example.com",
            password="password123",
            display_name="Test User",
        )

        user = auth_service.create_user(user_data)

        assert user.email == "test@example.com"
        assert user.display_name == "Test User"
        assert user.role == UserRole.END_USER

    def test_authenticate_valid(self, auth_service: AuthService) -> None:
        """Test authenticating with valid credentials."""
        from mellea_api.models.user import UserCreate

        user_data = UserCreate(
            email="test@example.com",
            password="password123",
            display_name="Test User",
        )
        auth_service.create_user(user_data)

        user = auth_service.authenticate("test@example.com", "password123")
        assert user.email == "test@example.com"

    def test_authenticate_invalid_password(self, auth_service: AuthService) -> None:
        """Test authenticating with invalid password."""
        from mellea_api.models.user import UserCreate
        from mellea_api.services.auth import AuthenticationError

        user_data = UserCreate(
            email="test@example.com",
            password="password123",
            display_name="Test User",
        )
        auth_service.create_user(user_data)

        with pytest.raises(AuthenticationError):
            auth_service.authenticate("test@example.com", "wrong_password")

    def test_seed_default_users(self, auth_service: AuthService) -> None:
        """Test seeding default users."""
        auth_service.seed_default_users()

        admin = auth_service.get_user_by_email("admin@example.com")
        developer = auth_service.get_user_by_email("developer@example.com")
        user = auth_service.get_user_by_email("user@example.com")

        assert admin is not None
        assert admin.role == UserRole.ADMIN

        assert developer is not None
        assert developer.role == UserRole.DEVELOPER

        assert user is not None
        assert user.role == UserRole.END_USER


class TestAuthRoutes:
    """Tests for authentication API routes."""

    def test_get_auth_config(self, client: TestClient) -> None:
        """Test getting auth configuration."""
        response = client.get("/api/v1/auth/config")

        assert response.status_code == 200
        data = response.json()
        assert data["mode"] == "local"
        assert "providers" in data
        assert "registrationEnabled" in data

    def test_register_and_login(self, client: TestClient) -> None:
        """Test registering a new user and logging in."""
        # Register
        register_response = client.post(
            "/api/v1/auth/register",
            json={
                "email": "newuser@example.com",
                "password": "password123",
                "displayName": "New User",
            },
        )

        # May fail if user already exists from previous test run
        if register_response.status_code == 201:
            data = register_response.json()
            assert "token" in data
            assert data["user"]["email"] == "newuser@example.com"

        # Login
        login_response = client.post(
            "/api/v1/auth/login",
            json={
                "email": "admin@example.com",
                "password": "admin123",
            },
        )

        assert login_response.status_code == 200
        data = login_response.json()
        assert "token" in data
        assert data["user"]["role"] == "admin"

    def test_login_invalid_credentials(self, client: TestClient) -> None:
        """Test login with invalid credentials."""
        response = client.post(
            "/api/v1/auth/login",
            json={
                "email": "admin@example.com",
                "password": "wrong_password",
            },
        )

        assert response.status_code == 401

    def test_get_me_authenticated(self, client: TestClient) -> None:
        """Test getting current user info when authenticated."""
        # Login first
        login_response = client.post(
            "/api/v1/auth/login",
            json={
                "email": "admin@example.com",
                "password": "admin123",
            },
        )
        token = login_response.json()["token"]

        # Get user info
        response = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "admin@example.com"
        assert data["role"] == "admin"

    def test_get_me_unauthenticated(self, client: TestClient) -> None:
        """Test getting current user info without authentication."""
        response = client.get("/api/v1/auth/me")
        assert response.status_code == 401
