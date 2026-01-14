"""Tests for run API routes."""

import os
import tempfile
from collections.abc import Iterator
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client() -> Iterator[TestClient]:
    """Create a test client with fresh service state and temp directory."""
    import mellea_api.services.assets as assets_module
    import mellea_api.services.auth as auth_module
    import mellea_api.services.credentials as cred_module
    import mellea_api.services.environment as env_module
    import mellea_api.services.run as run_module
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
        cred_module._credential_service = None
        env_module._environment_service = None
        run_module._run_service = None

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
            cred_module._credential_service = None
            env_module._environment_service = None
            run_module._run_service = None


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
def program_with_image(client: TestClient, auth_headers: dict[str, str]) -> dict:
    """Create a program with a built image for testing runs."""
    # Create a program
    response = client.post(
        "/api/v1/assets",
        headers=auth_headers,
        json={
            "type": "program",
            "name": "Test Program",
            "entrypoint": "main.py",
            "projectRoot": "workspaces/test",
            "dependencies": {"source": "requirements"},
            "imageTag": "mellea-test:latest",  # Simulate built image
        },
    )
    assert response.status_code == 201
    return response.json()["asset"]


class TestCreateRun:
    """Tests for POST /api/v1/runs endpoint."""

    def test_create_run_requires_auth(self, client: TestClient) -> None:
        """Test that creating a run requires authentication."""
        response = client.post(
            "/api/v1/runs",
            json={"programId": "some-id"},
        )
        assert response.status_code == 401

    def test_create_run_nonexistent_program(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """Test creating a run for a non-existent program returns 404."""
        response = client.post(
            "/api/v1/runs",
            headers=auth_headers,
            json={"programId": "nonexistent"},
        )
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_create_run_program_without_image(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """Test creating a run for a program without built image returns 400."""
        # Create a program without imageTag
        create_response = client.post(
            "/api/v1/assets",
            headers=auth_headers,
            json={
                "type": "program",
                "name": "No Image Program",
                "entrypoint": "main.py",
                "projectRoot": "workspaces/noimage",
                "dependencies": {"source": "requirements"},
            },
        )
        assert create_response.status_code == 201
        program_id = create_response.json()["asset"]["id"]

        # Try to create run
        response = client.post(
            "/api/v1/runs",
            headers=auth_headers,
            json={"programId": program_id},
        )
        assert response.status_code == 400
        assert "image" in response.json()["detail"].lower()

    def test_create_run_success(
        self, client: TestClient, auth_headers: dict[str, str], program_with_image: dict
    ) -> None:
        """Test successfully creating a run."""
        response = client.post(
            "/api/v1/runs",
            headers=auth_headers,
            json={"programId": program_with_image["id"]},
        )
        assert response.status_code == 201
        data = response.json()
        assert "run" in data
        assert data["run"]["programId"] == program_with_image["id"]
        assert data["run"]["status"] == "queued"
        assert "id" in data["run"]
        assert "environmentId" in data["run"]


class TestListRuns:
    """Tests for GET /api/v1/runs endpoint."""

    def test_list_runs_requires_auth(self, client: TestClient) -> None:
        """Test that listing runs requires authentication."""
        response = client.get("/api/v1/runs")
        assert response.status_code == 401

    def test_list_runs_empty(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """Test listing runs when none exist."""
        response = client.get("/api/v1/runs", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["runs"] == []
        assert data["total"] == 0

    def test_list_runs_returns_created_runs(
        self, client: TestClient, auth_headers: dict[str, str], program_with_image: dict
    ) -> None:
        """Test that created runs appear in the list."""
        # Create a run
        create_response = client.post(
            "/api/v1/runs",
            headers=auth_headers,
            json={"programId": program_with_image["id"]},
        )
        assert create_response.status_code == 201
        run_id = create_response.json()["run"]["id"]

        # List runs
        response = client.get("/api/v1/runs", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["runs"]) == 1
        assert data["runs"][0]["id"] == run_id

    def test_list_runs_filter_by_program(
        self, client: TestClient, auth_headers: dict[str, str], program_with_image: dict
    ) -> None:
        """Test filtering runs by program ID."""
        # Create a run
        client.post(
            "/api/v1/runs",
            headers=auth_headers,
            json={"programId": program_with_image["id"]},
        )

        # List with correct filter
        response = client.get(
            f"/api/v1/runs?programId={program_with_image['id']}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["total"] == 1

        # List with incorrect filter
        response = client.get(
            "/api/v1/runs?programId=nonexistent",
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["total"] == 0

    def test_list_runs_filter_by_status(
        self, client: TestClient, auth_headers: dict[str, str], program_with_image: dict
    ) -> None:
        """Test filtering runs by status."""
        # Create a run (will be in queued status)
        client.post(
            "/api/v1/runs",
            headers=auth_headers,
            json={"programId": program_with_image["id"]},
        )

        # Filter by queued
        response = client.get("/api/v1/runs?status=queued", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["total"] == 1

        # Filter by running (should be empty)
        response = client.get("/api/v1/runs?status=running", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["total"] == 0


class TestGetRun:
    """Tests for GET /api/v1/runs/{id} endpoint."""

    def test_get_run_requires_auth(self, client: TestClient) -> None:
        """Test that getting a run requires authentication."""
        response = client.get("/api/v1/runs/some-id")
        assert response.status_code == 401

    def test_get_run_nonexistent(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """Test getting a non-existent run returns 404."""
        response = client.get("/api/v1/runs/nonexistent", headers=auth_headers)
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_get_run_success(
        self, client: TestClient, auth_headers: dict[str, str], program_with_image: dict
    ) -> None:
        """Test successfully getting a run by ID."""
        # Create a run
        create_response = client.post(
            "/api/v1/runs",
            headers=auth_headers,
            json={"programId": program_with_image["id"]},
        )
        assert create_response.status_code == 201
        run_id = create_response.json()["run"]["id"]

        # Get the run
        response = client.get(f"/api/v1/runs/{run_id}", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["run"]["id"] == run_id
        assert data["run"]["programId"] == program_with_image["id"]
        assert data["run"]["status"] == "queued"


class TestCancelRun:
    """Tests for POST /api/v1/runs/{id}/cancel endpoint."""

    def test_cancel_run_requires_auth(self, client: TestClient) -> None:
        """Test that cancelling a run requires authentication."""
        response = client.post("/api/v1/runs/some-id/cancel")
        assert response.status_code == 401

    def test_cancel_run_nonexistent(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """Test cancelling a non-existent run returns 404."""
        response = client.post("/api/v1/runs/nonexistent/cancel", headers=auth_headers)
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_cancel_run_success(
        self, client: TestClient, auth_headers: dict[str, str], program_with_image: dict
    ) -> None:
        """Test successfully cancelling a queued run."""
        # Create a run
        create_response = client.post(
            "/api/v1/runs",
            headers=auth_headers,
            json={"programId": program_with_image["id"]},
        )
        assert create_response.status_code == 201
        run_id = create_response.json()["run"]["id"]

        # Cancel the run
        response = client.post(f"/api/v1/runs/{run_id}/cancel", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["run"]["id"] == run_id
        assert data["run"]["status"] == "cancelled"


class TestCreateRunWithCredentials:
    """Tests for credential validation when creating runs."""

    def test_create_run_with_nonexistent_credential(
        self, client: TestClient, auth_headers: dict[str, str], program_with_image: dict
    ) -> None:
        """Test creating a run with a non-existent credential returns 404."""
        response = client.post(
            "/api/v1/runs",
            headers=auth_headers,
            json={
                "programId": program_with_image["id"],
                "credentialIds": ["nonexistent-cred-id"],
            },
        )
        assert response.status_code == 404
        assert "credential" in response.json()["detail"].lower()

    def test_create_run_with_expired_credential(
        self, client: TestClient, auth_headers: dict[str, str], program_with_image: dict
    ) -> None:
        """Test creating a run with an expired credential returns 400."""
        # Create an expired credential
        expired_time = (datetime.utcnow() - timedelta(days=1)).isoformat()
        cred_response = client.post(
            "/api/v1/credentials",
            headers=auth_headers,
            json={
                "name": "Expired API Key",
                "type": "api_key",
                "secretData": {"api_key": "test-key"},
                "expiresAt": expired_time,
            },
        )
        assert cred_response.status_code == 201
        cred_id = cred_response.json()["id"]

        # Try to create run with expired credential
        response = client.post(
            "/api/v1/runs",
            headers=auth_headers,
            json={
                "programId": program_with_image["id"],
                "credentialIds": [cred_id],
            },
        )
        assert response.status_code == 400
        assert "expired" in response.json()["detail"].lower()

    def test_create_run_with_valid_credential(
        self, client: TestClient, auth_headers: dict[str, str], program_with_image: dict
    ) -> None:
        """Test creating a run with a valid credential succeeds."""
        # Create a valid credential (no expiration)
        cred_response = client.post(
            "/api/v1/credentials",
            headers=auth_headers,
            json={
                "name": "Valid API Key",
                "type": "api_key",
                "secretData": {"api_key": "test-key"},
            },
        )
        assert cred_response.status_code == 201
        cred_id = cred_response.json()["id"]

        # Create run with valid credential
        response = client.post(
            "/api/v1/runs",
            headers=auth_headers,
            json={
                "programId": program_with_image["id"],
                "credentialIds": [cred_id],
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["run"]["credentialIds"] == [cred_id]

    def test_create_run_with_future_expiring_credential(
        self, client: TestClient, auth_headers: dict[str, str], program_with_image: dict
    ) -> None:
        """Test creating a run with a credential that expires in the future succeeds."""
        # Create a credential that expires tomorrow
        future_time = (datetime.utcnow() + timedelta(days=1)).isoformat()
        cred_response = client.post(
            "/api/v1/credentials",
            headers=auth_headers,
            json={
                "name": "Future Expiring Key",
                "type": "api_key",
                "secretData": {"api_key": "test-key"},
                "expiresAt": future_time,
            },
        )
        assert cred_response.status_code == 201
        cred_id = cred_response.json()["id"]

        # Create run with future-expiring credential
        response = client.post(
            "/api/v1/runs",
            headers=auth_headers,
            json={
                "programId": program_with_image["id"],
                "credentialIds": [cred_id],
            },
        )
        assert response.status_code == 201
