"""Tests for asset API routes."""

import os
import tempfile
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client() -> Iterator[TestClient]:
    """Create a test client with fresh service state and temp directory."""
    import mellea_api.services.assets as assets_module
    import mellea_api.services.auth as auth_module
    from mellea_api.core.config import get_settings

    # Use a temporary directory for data
    with tempfile.TemporaryDirectory() as tmpdir:
        # Set environment variable before clearing cache
        old_data_dir = os.environ.get("MELLEA_DATA_DIR")
        os.environ["MELLEA_DATA_DIR"] = tmpdir

        # Clear cached settings and services to pick up new env var
        get_settings.cache_clear()
        auth_module._auth_service = None
        assets_module._asset_service = None

        # Get fresh settings and ensure directories exist
        settings = get_settings()
        settings.ensure_data_dirs()

        # Import app after settings are configured
        from mellea_api.main import create_app

        app = create_app()

        try:
            with TestClient(app) as test_client:
                yield test_client
        finally:
            # Restore environment
            if old_data_dir is not None:
                os.environ["MELLEA_DATA_DIR"] = old_data_dir
            elif "MELLEA_DATA_DIR" in os.environ:
                del os.environ["MELLEA_DATA_DIR"]

            # Clear caches again
            get_settings.cache_clear()
            auth_module._auth_service = None
            assets_module._asset_service = None


@pytest.fixture
def auth_headers(client: TestClient) -> dict[str, str]:
    """Get authorization headers for a developer user."""
    login_response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "developer@example.com",
            "password": "dev123",
        },
    )
    assert login_response.status_code == 200
    token = login_response.json()["token"]
    return {"Authorization": f"Bearer {token}"}


class TestCreateAsset:
    """Tests for POST /api/v1/assets endpoint."""

    def test_create_program_asset(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """Test creating a program asset."""
        response = client.post(
            "/api/v1/assets",
            headers=auth_headers,
            json={
                "type": "program",
                "name": "Test Program",
                "description": "A test program",
                "entrypoint": "src/main.py",
                "projectRoot": "workspaces/test",
                "dependencies": {
                    "source": "requirements",
                    "packages": [],
                },
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["asset"]["type"] == "program"
        assert data["asset"]["name"] == "Test Program"
        assert data["asset"]["entrypoint"] == "src/main.py"
        assert "id" in data["asset"]

    def test_create_model_asset(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """Test creating a model asset."""
        response = client.post(
            "/api/v1/assets",
            headers=auth_headers,
            json={
                "type": "model",
                "name": "GPT-4o",
                "description": "OpenAI GPT-4o model",
                "provider": "openai",
                "modelId": "gpt-4o",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["asset"]["type"] == "model"
        assert data["asset"]["name"] == "GPT-4o"
        assert data["asset"]["provider"] == "openai"
        assert data["asset"]["modelId"] == "gpt-4o"

    def test_create_composition_asset(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """Test creating a composition asset."""
        response = client.post(
            "/api/v1/assets",
            headers=auth_headers,
            json={
                "type": "composition",
                "name": "Test Workflow",
                "description": "A test composition workflow",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["asset"]["type"] == "composition"
        assert data["asset"]["name"] == "Test Workflow"

    def test_create_asset_sets_owner(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """Test that creating an asset sets the owner to the current user."""
        response = client.post(
            "/api/v1/assets",
            headers=auth_headers,
            json={
                "type": "composition",
                "name": "Owned Workflow",
                "owner": "should-be-overwritten",
            },
        )

        assert response.status_code == 201
        data = response.json()
        # Owner should be set to the authenticated user, not the provided value
        assert data["asset"]["owner"] != "should-be-overwritten"

    def test_create_asset_requires_auth(self, client: TestClient) -> None:
        """Test that creating an asset requires authentication."""
        response = client.post(
            "/api/v1/assets",
            json={
                "type": "composition",
                "name": "Unauthorized",
            },
        )

        assert response.status_code == 401


class TestGetAsset:
    """Tests for GET /api/v1/assets/{id} endpoint."""

    def test_get_program_asset(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """Test retrieving a program asset by ID."""
        # Create first
        create_response = client.post(
            "/api/v1/assets",
            headers=auth_headers,
            json={
                "type": "program",
                "name": "Retrievable Program",
                "entrypoint": "main.py",
                "projectRoot": "workspaces/retrieve",
                "dependencies": {
                    "source": "requirements",
                },
            },
        )
        assert create_response.status_code == 201
        asset_id = create_response.json()["asset"]["id"]

        # Retrieve
        get_response = client.get(
            f"/api/v1/assets/{asset_id}",
            headers=auth_headers,
        )

        assert get_response.status_code == 200
        data = get_response.json()
        assert data["asset"]["id"] == asset_id
        assert data["asset"]["name"] == "Retrievable Program"
        assert data["asset"]["type"] == "program"

    def test_get_model_asset(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """Test retrieving a model asset by ID."""
        # Create first
        create_response = client.post(
            "/api/v1/assets",
            headers=auth_headers,
            json={
                "type": "model",
                "name": "Retrievable Model",
                "provider": "anthropic",
                "modelId": "claude-3-opus",
            },
        )
        assert create_response.status_code == 201
        asset_id = create_response.json()["asset"]["id"]

        # Retrieve
        get_response = client.get(
            f"/api/v1/assets/{asset_id}",
            headers=auth_headers,
        )

        assert get_response.status_code == 200
        data = get_response.json()
        assert data["asset"]["id"] == asset_id
        assert data["asset"]["type"] == "model"

    def test_get_nonexistent_asset(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """Test retrieving a non-existent asset returns 404."""
        response = client.get(
            "/api/v1/assets/nonexistent-id",
            headers=auth_headers,
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_get_asset_requires_auth(self, client: TestClient) -> None:
        """Test that retrieving an asset requires authentication."""
        response = client.get("/api/v1/assets/some-id")

        assert response.status_code == 401


class TestListAssets:
    """Tests for GET /api/v1/assets endpoint."""

    def test_list_assets_requires_auth(self, client: TestClient) -> None:
        """Test that listing assets requires authentication."""
        response = client.get("/api/v1/assets")
        assert response.status_code == 401

    def test_list_assets_empty(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """Test listing assets when none exist."""
        response = client.get("/api/v1/assets", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["assets"] == []
        assert data["total"] == 0

    def test_list_assets_returns_all_types(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """Test that listing returns all asset types."""
        # Create one of each type
        client.post(
            "/api/v1/assets",
            headers=auth_headers,
            json={
                "type": "program",
                "name": "Test Program",
                "entrypoint": "main.py",
                "projectRoot": "workspaces/test",
                "dependencies": {"source": "requirements"},
            },
        )
        client.post(
            "/api/v1/assets",
            headers=auth_headers,
            json={
                "type": "model",
                "name": "Test Model",
                "provider": "openai",
                "modelId": "gpt-4",
            },
        )
        client.post(
            "/api/v1/assets",
            headers=auth_headers,
            json={
                "type": "composition",
                "name": "Test Composition",
            },
        )

        # List all
        response = client.get("/api/v1/assets", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3
        types = {a["type"] for a in data["assets"]}
        assert types == {"program", "model", "composition"}

    def test_list_assets_filter_by_type(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """Test filtering assets by type."""
        # Create assets of different types
        client.post(
            "/api/v1/assets",
            headers=auth_headers,
            json={
                "type": "program",
                "name": "Program 1",
                "entrypoint": "main.py",
                "projectRoot": "workspaces/p1",
                "dependencies": {"source": "requirements"},
            },
        )
        client.post(
            "/api/v1/assets",
            headers=auth_headers,
            json={
                "type": "model",
                "name": "Model 1",
                "provider": "anthropic",
                "modelId": "claude-3",
            },
        )

        # Filter by program
        response = client.get("/api/v1/assets?type=program", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["assets"][0]["type"] == "program"

        # Filter by model
        response = client.get("/api/v1/assets?type=model", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["assets"][0]["type"] == "model"

    def test_list_assets_filter_by_tags(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """Test filtering assets by tags."""
        # Create assets with different tags
        client.post(
            "/api/v1/assets",
            headers=auth_headers,
            json={
                "type": "composition",
                "name": "Tagged 1",
                "tags": ["ai", "testing"],
            },
        )
        client.post(
            "/api/v1/assets",
            headers=auth_headers,
            json={
                "type": "composition",
                "name": "Tagged 2",
                "tags": ["production"],
            },
        )

        # Filter by tag
        response = client.get("/api/v1/assets?tags=ai", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["assets"][0]["name"] == "Tagged 1"

    def test_list_assets_search_by_name(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """Test searching assets by name."""
        # Create assets with distinct names
        client.post(
            "/api/v1/assets",
            headers=auth_headers,
            json={
                "type": "composition",
                "name": "My Special Workflow",
            },
        )
        client.post(
            "/api/v1/assets",
            headers=auth_headers,
            json={
                "type": "composition",
                "name": "Other Thing",
            },
        )

        # Search
        response = client.get("/api/v1/assets?q=special", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert "Special" in data["assets"][0]["name"]
