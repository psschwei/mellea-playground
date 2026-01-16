"""Tests for environment API routes."""

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
    import mellea_api.services.environment as env_module
    import mellea_api.services.environment_builder as builder_module
    import mellea_api.services.idle_timeout as idle_module
    import mellea_api.services.run as run_module
    import mellea_api.services.run_executor as run_executor_module
    import mellea_api.services.warmup as warmup_module
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
        env_module._environment_service = None
        builder_module._environment_builder_service = None
        idle_module._idle_timeout_service = None
        idle_module._idle_timeout_controller = None
        run_module._run_service = None
        run_executor_module._run_executor = None
        run_executor_module._run_executor_controller = None
        warmup_module._warmup_service = None
        warmup_module._warmup_controller = None

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
            env_module._environment_service = None
            builder_module._environment_builder_service = None
            idle_module._idle_timeout_service = None
            idle_module._idle_timeout_controller = None
            run_module._run_service = None
            run_executor_module._run_executor = None
            run_executor_module._run_executor_controller = None
            warmup_module._warmup_service = None
            warmup_module._warmup_controller = None


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


@pytest.fixture
def program(client: TestClient, auth_headers: dict[str, str]) -> dict:
    """Create a program for testing environments."""
    response = client.post(
        "/api/v1/assets",
        headers=auth_headers,
        json={
            "type": "program",
            "name": "Test Program",
            "entrypoint": "main.py",
            "projectRoot": "workspaces/test",
            "dependencies": {"source": "requirements"},
            "imageTag": "mellea-test:latest",
        },
    )
    assert response.status_code == 201
    return response.json()["asset"]


class TestListEnvironments:
    """Tests for GET /api/v1/environments endpoint."""

    def test_list_environments_requires_auth(self, client: TestClient) -> None:
        """Test that listing environments requires authentication."""
        response = client.get("/api/v1/environments")
        assert response.status_code == 401

    def test_list_environments_empty(self, client: TestClient, auth_headers: dict[str, str]) -> None:
        """Test listing environments when none exist."""
        response = client.get("/api/v1/environments", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["environments"] == []
        assert data["total"] == 0

    def test_list_environments_returns_created(
        self, client: TestClient, auth_headers: dict[str, str], program: dict
    ) -> None:
        """Test that created environments appear in the list."""
        # Create an environment
        create_response = client.post(
            "/api/v1/environments",
            headers=auth_headers,
            json={
                "programId": program["id"],
                "imageTag": "mellea-test:v1",
            },
        )
        assert create_response.status_code == 201
        env_id = create_response.json()["environment"]["id"]

        # List environments
        response = client.get("/api/v1/environments", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["environments"]) == 1
        assert data["environments"][0]["id"] == env_id

    def test_list_environments_filter_by_program(
        self, client: TestClient, auth_headers: dict[str, str], program: dict
    ) -> None:
        """Test filtering environments by program ID."""
        # Create an environment
        client.post(
            "/api/v1/environments",
            headers=auth_headers,
            json={
                "programId": program["id"],
                "imageTag": "mellea-test:v1",
            },
        )

        # Filter by correct program
        response = client.get(
            f"/api/v1/environments?programId={program['id']}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["total"] == 1

        # Filter by non-existent program
        response = client.get(
            "/api/v1/environments?programId=nonexistent",
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["total"] == 0

    def test_list_environments_filter_by_status(
        self, client: TestClient, auth_headers: dict[str, str], program: dict
    ) -> None:
        """Test filtering environments by status."""
        # Create an environment (starts in CREATING status)
        client.post(
            "/api/v1/environments",
            headers=auth_headers,
            json={
                "programId": program["id"],
                "imageTag": "mellea-test:v1",
            },
        )

        # Filter by creating status
        response = client.get("/api/v1/environments?status=creating", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["total"] == 1

        # Filter by ready status (should be empty)
        response = client.get("/api/v1/environments?status=ready", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["total"] == 0


class TestCreateEnvironment:
    """Tests for POST /api/v1/environments endpoint."""

    def test_create_environment_requires_auth(self, client: TestClient) -> None:
        """Test that creating an environment requires authentication."""
        response = client.post(
            "/api/v1/environments",
            json={"programId": "some-id", "imageTag": "test:v1"},
        )
        assert response.status_code == 401

    def test_create_environment_success(
        self, client: TestClient, auth_headers: dict[str, str], program: dict
    ) -> None:
        """Test successfully creating an environment."""
        response = client.post(
            "/api/v1/environments",
            headers=auth_headers,
            json={
                "programId": program["id"],
                "imageTag": "mellea-test:v1",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert "environment" in data
        assert data["environment"]["programId"] == program["id"]
        assert data["environment"]["imageTag"] == "mellea-test:v1"
        assert data["environment"]["status"] == "creating"
        assert "id" in data["environment"]

    def test_create_environment_with_resource_limits(
        self, client: TestClient, auth_headers: dict[str, str], program: dict
    ) -> None:
        """Test creating an environment with resource limits."""
        response = client.post(
            "/api/v1/environments",
            headers=auth_headers,
            json={
                "programId": program["id"],
                "imageTag": "mellea-test:v1",
                "resourceLimits": {
                    "cpuCores": 2.0,
                    "memoryMb": 1024,
                    "timeoutSeconds": 600,
                },
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["environment"]["resourceLimits"]["cpuCores"] == 2.0
        assert data["environment"]["resourceLimits"]["memoryMb"] == 1024
        assert data["environment"]["resourceLimits"]["timeoutSeconds"] == 600


class TestGetEnvironment:
    """Tests for GET /api/v1/environments/{id} endpoint."""

    def test_get_environment_requires_auth(self, client: TestClient) -> None:
        """Test that getting an environment requires authentication."""
        response = client.get("/api/v1/environments/some-id")
        assert response.status_code == 401

    def test_get_environment_nonexistent(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """Test getting a non-existent environment returns 404."""
        response = client.get("/api/v1/environments/nonexistent", headers=auth_headers)
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_get_environment_success(
        self, client: TestClient, auth_headers: dict[str, str], program: dict
    ) -> None:
        """Test successfully getting an environment by ID."""
        # Create an environment
        create_response = client.post(
            "/api/v1/environments",
            headers=auth_headers,
            json={
                "programId": program["id"],
                "imageTag": "mellea-test:v1",
            },
        )
        assert create_response.status_code == 201
        env_id = create_response.json()["environment"]["id"]

        # Get the environment
        response = client.get(f"/api/v1/environments/{env_id}", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["environment"]["id"] == env_id
        assert data["environment"]["programId"] == program["id"]


class TestDeleteEnvironment:
    """Tests for DELETE /api/v1/environments/{id} endpoint."""

    def test_delete_environment_requires_auth(self, client: TestClient) -> None:
        """Test that deleting an environment requires authentication."""
        response = client.delete("/api/v1/environments/some-id")
        assert response.status_code == 401

    def test_delete_environment_nonexistent(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """Test deleting a non-existent environment returns 404."""
        response = client.delete("/api/v1/environments/nonexistent", headers=auth_headers)
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_delete_environment_creating_state_fails(
        self, client: TestClient, auth_headers: dict[str, str], program: dict
    ) -> None:
        """Test that environments in CREATING state cannot be deleted."""
        # Create an environment (starts in CREATING)
        create_response = client.post(
            "/api/v1/environments",
            headers=auth_headers,
            json={
                "programId": program["id"],
                "imageTag": "mellea-test:v1",
            },
        )
        assert create_response.status_code == 201
        env_id = create_response.json()["environment"]["id"]

        # Try to delete
        response = client.delete(f"/api/v1/environments/{env_id}", headers=auth_headers)
        assert response.status_code == 400
        assert "invalid transition" in response.json()["detail"].lower()

    def test_delete_environment_ready_state_success(
        self, client: TestClient, auth_headers: dict[str, str], program: dict
    ) -> None:
        """Test that environments in READY state can be deleted."""
        # Create an environment
        create_response = client.post(
            "/api/v1/environments",
            headers=auth_headers,
            json={
                "programId": program["id"],
                "imageTag": "mellea-test:v1",
            },
        )
        assert create_response.status_code == 201
        env_id = create_response.json()["environment"]["id"]

        # Mark as ready
        mark_response = client.post(
            f"/api/v1/environments/{env_id}/mark-ready",
            headers=auth_headers,
        )
        assert mark_response.status_code == 200

        # Delete
        response = client.delete(f"/api/v1/environments/{env_id}", headers=auth_headers)
        assert response.status_code == 204

        # Verify deleted
        get_response = client.get(f"/api/v1/environments/{env_id}", headers=auth_headers)
        assert get_response.status_code == 404


class TestEnvironmentLifecycle:
    """Tests for environment lifecycle endpoints."""

    def test_mark_ready_requires_auth(self, client: TestClient) -> None:
        """Test that marking ready requires authentication."""
        response = client.post("/api/v1/environments/some-id/mark-ready")
        assert response.status_code == 401

    def test_mark_ready_nonexistent(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """Test marking a non-existent environment as ready returns 404."""
        response = client.post(
            "/api/v1/environments/nonexistent/mark-ready",
            headers=auth_headers,
        )
        assert response.status_code == 404

    def test_mark_ready_success(
        self, client: TestClient, auth_headers: dict[str, str], program: dict
    ) -> None:
        """Test successfully marking an environment as ready."""
        # Create an environment
        create_response = client.post(
            "/api/v1/environments",
            headers=auth_headers,
            json={
                "programId": program["id"],
                "imageTag": "mellea-test:v1",
            },
        )
        assert create_response.status_code == 201
        env_id = create_response.json()["environment"]["id"]
        assert create_response.json()["environment"]["status"] == "creating"

        # Mark as ready
        response = client.post(
            f"/api/v1/environments/{env_id}/mark-ready",
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["environment"]["status"] == "ready"

    def test_start_environment_requires_ready_state(
        self, client: TestClient, auth_headers: dict[str, str], program: dict
    ) -> None:
        """Test that starting requires environment to be in READY state."""
        # Create an environment (starts in CREATING)
        create_response = client.post(
            "/api/v1/environments",
            headers=auth_headers,
            json={
                "programId": program["id"],
                "imageTag": "mellea-test:v1",
            },
        )
        assert create_response.status_code == 201
        env_id = create_response.json()["environment"]["id"]

        # Try to start from CREATING (invalid)
        response = client.post(
            f"/api/v1/environments/{env_id}/start",
            headers=auth_headers,
        )
        assert response.status_code == 400
        assert "invalid transition" in response.json()["detail"].lower()

    def test_start_environment_success(
        self, client: TestClient, auth_headers: dict[str, str], program: dict
    ) -> None:
        """Test successfully starting an environment."""
        # Create an environment
        create_response = client.post(
            "/api/v1/environments",
            headers=auth_headers,
            json={
                "programId": program["id"],
                "imageTag": "mellea-test:v1",
            },
        )
        assert create_response.status_code == 201
        env_id = create_response.json()["environment"]["id"]

        # Mark as ready first
        client.post(f"/api/v1/environments/{env_id}/mark-ready", headers=auth_headers)

        # Start
        response = client.post(
            f"/api/v1/environments/{env_id}/start",
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["environment"]["status"] == "starting"

    def test_mark_failed_success(
        self, client: TestClient, auth_headers: dict[str, str], program: dict
    ) -> None:
        """Test successfully marking an environment as failed."""
        # Create an environment
        create_response = client.post(
            "/api/v1/environments",
            headers=auth_headers,
            json={
                "programId": program["id"],
                "imageTag": "mellea-test:v1",
            },
        )
        assert create_response.status_code == 201
        env_id = create_response.json()["environment"]["id"]

        # Mark as failed
        response = client.post(
            f"/api/v1/environments/{env_id}/mark-failed",
            headers=auth_headers,
            json={"error": "Build failed: dependency not found"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["environment"]["status"] == "failed"
        assert data["environment"]["errorMessage"] == "Build failed: dependency not found"


class TestBulkDeleteEnvironments:
    """Tests for POST /api/v1/environments/bulk-delete endpoint."""

    def test_bulk_delete_requires_auth(self, client: TestClient) -> None:
        """Test that bulk delete requires authentication."""
        response = client.post(
            "/api/v1/environments/bulk-delete",
            json={"environmentIds": []},
        )
        assert response.status_code == 401

    def test_bulk_delete_empty_list(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """Test bulk delete with empty list."""
        response = client.post(
            "/api/v1/environments/bulk-delete",
            headers=auth_headers,
            json={"environmentIds": []},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["deletedCount"] == 0
        assert data["failedCount"] == 0

    def test_bulk_delete_mixed_results(
        self, client: TestClient, auth_headers: dict[str, str], program: dict
    ) -> None:
        """Test bulk delete with mixed success and failure."""
        # Create two environments
        env1_response = client.post(
            "/api/v1/environments",
            headers=auth_headers,
            json={"programId": program["id"], "imageTag": "test:v1"},
        )
        env1_id = env1_response.json()["environment"]["id"]

        env2_response = client.post(
            "/api/v1/environments",
            headers=auth_headers,
            json={"programId": program["id"], "imageTag": "test:v2"},
        )
        env2_id = env2_response.json()["environment"]["id"]

        # Mark env1 as ready (deletable)
        client.post(f"/api/v1/environments/{env1_id}/mark-ready", headers=auth_headers)

        # env2 stays in CREATING (not deletable)

        # Bulk delete both
        response = client.post(
            "/api/v1/environments/bulk-delete",
            headers=auth_headers,
            json={"environmentIds": [env1_id, env2_id, "nonexistent"]},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["deletedCount"] == 1
        assert data["failedCount"] == 2
        assert data["results"][env1_id] is True
        assert "invalid transition" in data["results"][env2_id].lower()
        assert "not found" in data["results"]["nonexistent"].lower()


class TestEnvironmentStats:
    """Tests for GET /api/v1/environments/stats endpoint."""

    def test_stats_requires_auth(self, client: TestClient) -> None:
        """Test that stats requires authentication."""
        response = client.get("/api/v1/environments/stats")
        assert response.status_code == 401

    def test_stats_empty(self, client: TestClient, auth_headers: dict[str, str]) -> None:
        """Test stats when no environments exist."""
        response = client.get("/api/v1/environments/stats", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["byStatus"] == {}

    def test_stats_with_environments(
        self, client: TestClient, auth_headers: dict[str, str], program: dict
    ) -> None:
        """Test stats with some environments."""
        # Create environments
        env1_response = client.post(
            "/api/v1/environments",
            headers=auth_headers,
            json={"programId": program["id"], "imageTag": "test:v1"},
        )
        env1_id = env1_response.json()["environment"]["id"]

        client.post(
            "/api/v1/environments",
            headers=auth_headers,
            json={"programId": program["id"], "imageTag": "test:v2"},
        )

        # Mark env1 as ready
        client.post(f"/api/v1/environments/{env1_id}/mark-ready", headers=auth_headers)

        # Get stats
        response = client.get("/api/v1/environments/stats", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert data["byStatus"]["creating"] == 1
        assert data["byStatus"]["ready"] == 1


class TestWarmPoolStatus:
    """Tests for GET /api/v1/environments/warm-pool endpoint."""

    def test_warm_pool_requires_auth(self, client: TestClient) -> None:
        """Test that warm pool status requires authentication."""
        response = client.get("/api/v1/environments/warm-pool")
        assert response.status_code == 401

    def test_warm_pool_status(self, client: TestClient, auth_headers: dict[str, str]) -> None:
        """Test getting warm pool status."""
        response = client.get("/api/v1/environments/warm-pool", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "enabled" in data
        assert "targetPoolSize" in data
        assert "currentPoolSize" in data
        assert "warmEnvironments" in data
        assert "thresholds" in data
