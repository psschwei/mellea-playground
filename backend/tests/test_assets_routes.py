"""Tests for asset API routes."""

import os
import tempfile
from collections.abc import Iterator
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from mellea_api.models.build import BuildResult


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


class TestBuildAssetImage:
    """Tests for POST /api/v1/assets/{id}/build endpoint."""

    def test_build_asset_image_success(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """Test successfully building a program image."""
        # Create a program first
        create_response = client.post(
            "/api/v1/assets",
            headers=auth_headers,
            json={
                "type": "program",
                "name": "Build Test Program",
                "entrypoint": "main.py",
                "projectRoot": "workspaces/build-test",
                "dependencies": {"source": "requirements"},
            },
        )
        assert create_response.status_code == 201
        asset_id = create_response.json()["asset"]["id"]

        # Mock the environment builder service
        mock_result = BuildResult(
            program_id=asset_id,
            success=True,
            image_tag=f"mellea-program-{asset_id}:latest",
            cache_hit=False,
            total_duration_seconds=5.5,
        )

        with patch(
            "mellea_api.routes.assets.get_environment_builder_service"
        ) as mock_get_builder:
            mock_builder = MagicMock()
            mock_builder.build_image.return_value = mock_result
            mock_get_builder.return_value = mock_builder

            # Build the image
            build_response = client.post(
                f"/api/v1/assets/{asset_id}/build",
                headers=auth_headers,
            )

        assert build_response.status_code == 200
        data = build_response.json()
        assert data["result"]["success"] is True
        assert data["result"]["imageTag"] == f"mellea-program-{asset_id}:latest"
        assert data["result"]["programId"] == asset_id

        # Verify the program was updated with the image tag
        get_response = client.get(f"/api/v1/assets/{asset_id}", headers=auth_headers)
        assert get_response.status_code == 200
        program_data = get_response.json()["asset"]
        assert program_data["imageTag"] == f"mellea-program-{asset_id}:latest"
        assert program_data["imageBuildStatus"] == "ready"

    def test_build_asset_image_with_options(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """Test building with forceRebuild and push options."""
        # Create a program
        create_response = client.post(
            "/api/v1/assets",
            headers=auth_headers,
            json={
                "type": "program",
                "name": "Build Options Test",
                "entrypoint": "main.py",
                "projectRoot": "workspaces/options-test",
                "dependencies": {"source": "requirements"},
            },
        )
        assert create_response.status_code == 201
        asset_id = create_response.json()["asset"]["id"]

        mock_result = BuildResult(
            program_id=asset_id,
            success=True,
            image_tag=f"mellea-program-{asset_id}:latest",
            cache_hit=False,
            total_duration_seconds=10.0,
        )

        with patch(
            "mellea_api.routes.assets.get_environment_builder_service"
        ) as mock_get_builder:
            mock_builder = MagicMock()
            mock_builder.build_image.return_value = mock_result
            mock_get_builder.return_value = mock_builder

            # Build with options
            build_response = client.post(
                f"/api/v1/assets/{asset_id}/build",
                headers=auth_headers,
                json={"forceRebuild": True, "push": True},
            )

            # Verify the options were passed to build_image
            mock_builder.build_image.assert_called_once()
            call_kwargs = mock_builder.build_image.call_args.kwargs
            assert call_kwargs["force_rebuild"] is True
            assert call_kwargs["push"] is True

        assert build_response.status_code == 200

    def test_build_asset_image_failure(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """Test handling of build failure."""
        # Create a program
        create_response = client.post(
            "/api/v1/assets",
            headers=auth_headers,
            json={
                "type": "program",
                "name": "Build Fail Test",
                "entrypoint": "main.py",
                "projectRoot": "workspaces/fail-test",
                "dependencies": {"source": "requirements"},
            },
        )
        assert create_response.status_code == 201
        asset_id = create_response.json()["asset"]["id"]

        # Mock a failed build
        mock_result = BuildResult(
            program_id=asset_id,
            success=False,
            error_message="Docker daemon not available",
            total_duration_seconds=0.5,
        )

        with patch(
            "mellea_api.routes.assets.get_environment_builder_service"
        ) as mock_get_builder:
            mock_builder = MagicMock()
            mock_builder.build_image.return_value = mock_result
            mock_get_builder.return_value = mock_builder

            build_response = client.post(
                f"/api/v1/assets/{asset_id}/build",
                headers=auth_headers,
            )

        assert build_response.status_code == 200
        data = build_response.json()
        assert data["result"]["success"] is False
        assert data["result"]["errorMessage"] == "Docker daemon not available"

        # Verify the program status was updated to failed
        get_response = client.get(f"/api/v1/assets/{asset_id}", headers=auth_headers)
        program_data = get_response.json()["asset"]
        assert program_data["imageBuildStatus"] == "failed"
        assert program_data["imageBuildError"] == "Docker daemon not available"

    def test_build_nonexistent_asset(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """Test building a non-existent asset returns 404."""
        response = client.post(
            "/api/v1/assets/nonexistent-id/build",
            headers=auth_headers,
        )
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_build_asset_requires_auth(self, client: TestClient) -> None:
        """Test that building an asset requires authentication."""
        response = client.post("/api/v1/assets/some-id/build")
        assert response.status_code == 401


class TestUpdateAsset:
    """Tests for PUT /api/v1/assets/{id} endpoint."""

    def test_update_program_asset(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """Test updating a program asset's metadata."""
        # Create first
        create_response = client.post(
            "/api/v1/assets",
            headers=auth_headers,
            json={
                "type": "program",
                "name": "Original Name",
                "description": "Original description",
                "entrypoint": "main.py",
                "projectRoot": "workspaces/update-test",
                "dependencies": {"source": "requirements"},
                "tags": ["original"],
            },
        )
        assert create_response.status_code == 201
        asset_id = create_response.json()["asset"]["id"]

        # Update
        update_response = client.put(
            f"/api/v1/assets/{asset_id}",
            headers=auth_headers,
            json={
                "name": "Updated Name",
                "description": "Updated description",
                "tags": ["updated", "new-tag"],
            },
        )

        assert update_response.status_code == 200
        data = update_response.json()
        assert data["asset"]["name"] == "Updated Name"
        assert data["asset"]["description"] == "Updated description"
        assert data["asset"]["tags"] == ["updated", "new-tag"]
        # Verify unchanged fields remain
        assert data["asset"]["entrypoint"] == "main.py"

    def test_update_model_asset(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """Test updating a model asset's metadata."""
        # Create first
        create_response = client.post(
            "/api/v1/assets",
            headers=auth_headers,
            json={
                "type": "model",
                "name": "Original Model",
                "provider": "openai",
                "modelId": "gpt-4",
            },
        )
        assert create_response.status_code == 201
        asset_id = create_response.json()["asset"]["id"]

        # Update
        update_response = client.put(
            f"/api/v1/assets/{asset_id}",
            headers=auth_headers,
            json={"name": "Updated Model", "version": "2.0.0"},
        )

        assert update_response.status_code == 200
        data = update_response.json()
        assert data["asset"]["name"] == "Updated Model"
        assert data["asset"]["version"] == "2.0.0"
        # Verify unchanged fields
        assert data["asset"]["provider"] == "openai"
        assert data["asset"]["modelId"] == "gpt-4"

    def test_update_composition_asset(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """Test updating a composition asset's metadata."""
        # Create first
        create_response = client.post(
            "/api/v1/assets",
            headers=auth_headers,
            json={
                "type": "composition",
                "name": "Original Workflow",
            },
        )
        assert create_response.status_code == 201
        asset_id = create_response.json()["asset"]["id"]

        # Update
        update_response = client.put(
            f"/api/v1/assets/{asset_id}",
            headers=auth_headers,
            json={"name": "Updated Workflow", "description": "New description"},
        )

        assert update_response.status_code == 200
        data = update_response.json()
        assert data["asset"]["name"] == "Updated Workflow"
        assert data["asset"]["description"] == "New description"

    def test_update_nonexistent_asset(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """Test updating a non-existent asset returns 404."""
        response = client.put(
            "/api/v1/assets/nonexistent-id",
            headers=auth_headers,
            json={"name": "Should Fail"},
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_update_asset_requires_auth(self, client: TestClient) -> None:
        """Test that updating an asset requires authentication."""
        response = client.put(
            "/api/v1/assets/some-id",
            json={"name": "Unauthorized"},
        )
        assert response.status_code == 401

    def test_update_asset_partial_update(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """Test that partial updates only modify specified fields."""
        # Create
        create_response = client.post(
            "/api/v1/assets",
            headers=auth_headers,
            json={
                "type": "composition",
                "name": "Partial Test",
                "description": "Original description",
                "tags": ["tag1", "tag2"],
            },
        )
        assert create_response.status_code == 201
        asset_id = create_response.json()["asset"]["id"]

        # Update only name
        update_response = client.put(
            f"/api/v1/assets/{asset_id}",
            headers=auth_headers,
            json={"name": "New Name Only"},
        )

        assert update_response.status_code == 200
        data = update_response.json()
        assert data["asset"]["name"] == "New Name Only"
        # Other fields unchanged
        assert data["asset"]["description"] == "Original description"
        assert data["asset"]["tags"] == ["tag1", "tag2"]


class TestDeleteAsset:
    """Tests for DELETE /api/v1/assets/{id} endpoint."""

    def test_delete_program_asset(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """Test deleting a program asset."""
        # Create first
        create_response = client.post(
            "/api/v1/assets",
            headers=auth_headers,
            json={
                "type": "program",
                "name": "Delete Test Program",
                "entrypoint": "main.py",
                "projectRoot": "workspaces/delete-test",
                "dependencies": {"source": "requirements"},
            },
        )
        assert create_response.status_code == 201
        asset_id = create_response.json()["asset"]["id"]

        # Delete
        delete_response = client.delete(
            f"/api/v1/assets/{asset_id}",
            headers=auth_headers,
        )

        assert delete_response.status_code == 200
        data = delete_response.json()
        assert data["deleted"] is True
        assert "deleted successfully" in data["message"]

        # Verify it's gone
        get_response = client.get(
            f"/api/v1/assets/{asset_id}",
            headers=auth_headers,
        )
        assert get_response.status_code == 404

    def test_delete_model_asset(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """Test deleting a model asset."""
        # Create first
        create_response = client.post(
            "/api/v1/assets",
            headers=auth_headers,
            json={
                "type": "model",
                "name": "Delete Test Model",
                "provider": "anthropic",
                "modelId": "claude-3",
            },
        )
        assert create_response.status_code == 201
        asset_id = create_response.json()["asset"]["id"]

        # Delete
        delete_response = client.delete(
            f"/api/v1/assets/{asset_id}",
            headers=auth_headers,
        )

        assert delete_response.status_code == 200
        data = delete_response.json()
        assert data["deleted"] is True

        # Verify it's gone
        get_response = client.get(
            f"/api/v1/assets/{asset_id}",
            headers=auth_headers,
        )
        assert get_response.status_code == 404

    def test_delete_composition_asset(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """Test deleting a composition asset."""
        # Create first
        create_response = client.post(
            "/api/v1/assets",
            headers=auth_headers,
            json={
                "type": "composition",
                "name": "Delete Test Composition",
            },
        )
        assert create_response.status_code == 201
        asset_id = create_response.json()["asset"]["id"]

        # Delete
        delete_response = client.delete(
            f"/api/v1/assets/{asset_id}",
            headers=auth_headers,
        )

        assert delete_response.status_code == 200
        data = delete_response.json()
        assert data["deleted"] is True

        # Verify it's gone
        get_response = client.get(
            f"/api/v1/assets/{asset_id}",
            headers=auth_headers,
        )
        assert get_response.status_code == 404

    def test_delete_nonexistent_asset(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """Test deleting a non-existent asset returns 404."""
        response = client.delete(
            "/api/v1/assets/nonexistent-id",
            headers=auth_headers,
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_delete_asset_requires_auth(self, client: TestClient) -> None:
        """Test that deleting an asset requires authentication."""
        response = client.delete("/api/v1/assets/some-id")
        assert response.status_code == 401
