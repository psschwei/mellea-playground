"""Tests for build API routes."""

import os
import tempfile
from collections.abc import Iterator
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from mellea_api.models.build import BuildJobStatus, BuildResult


@pytest.fixture
def client() -> Iterator[TestClient]:
    """Create a test client with fresh service state and temp directory."""
    import mellea_api.services.assets as assets_module
    import mellea_api.services.auth as auth_module
    import mellea_api.services.environment_builder as builder_module
    import mellea_api.services.kaniko_builder as kaniko_module
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
        builder_module._environment_builder_service = None
        kaniko_module._kaniko_build_service = None

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
            builder_module._environment_builder_service = None
            kaniko_module._kaniko_build_service = None


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
def sample_program_id(client: TestClient, auth_headers: dict[str, str]) -> str:
    """Create a sample program and return its ID."""
    response = client.post(
        "/api/v1/assets",
        headers=auth_headers,
        json={
            "type": "program",
            "name": "Build Test Program",
            "description": "A test program for build tests",
            "entrypoint": "main.py",
            "projectRoot": "workspaces/test",
            "dependencies": {
                "source": "manual",
                "packages": [
                    {"name": "requests", "version": "2.31.0"},
                ],
                "pythonVersion": "3.12",
            },
        },
    )
    assert response.status_code == 201
    return response.json()["asset"]["id"]


class TestBuildProgramImage:
    """Tests for POST /api/v1/builds/programs/{program_id} endpoint."""

    def test_build_program_not_found(self, client: TestClient) -> None:
        """Test building a non-existent program returns 404."""
        response = client.post("/api/v1/builds/programs/nonexistent-id")
        assert response.status_code == 404

    def test_build_program_no_source_files(
        self, client: TestClient, sample_program_id: str
    ) -> None:
        """Test building without source files returns build failure."""
        # The workspace directory exists but has no source files
        # Build will fail at some point in the pipeline
        response = client.post(f"/api/v1/builds/programs/{sample_program_id}")
        # Build returns 200 with success=False on build errors
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert data["errorMessage"] is not None

    def test_build_program_success(
        self,
        client: TestClient,
        sample_program_id: str,
    ) -> None:
        """Test successful program build with mocked Docker client."""
        from mellea_api.core.config import get_settings
        from mellea_api.services.environment_builder import get_environment_builder_service

        # Create workspace directory with source file
        settings = get_settings()
        workspace_path = settings.data_dir / "workspaces" / sample_program_id
        workspace_path.mkdir(parents=True, exist_ok=True)
        (workspace_path / "main.py").write_text("print('hello')")

        # Get the service and inject mock Docker client
        builder = get_environment_builder_service()
        mock_client = MagicMock()
        mock_client.images.build.return_value = (MagicMock(), [])
        mock_client.images.get.return_value = MagicMock(attrs={"Size": 1000000})
        builder._docker_client = mock_client

        response = client.post(f"/api/v1/builds/programs/{sample_program_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["imageTag"] is not None
        assert "mellea-prog" in data["imageTag"]

    def test_build_program_with_force_rebuild(
        self,
        client: TestClient,
        sample_program_id: str,
    ) -> None:
        """Test building with force_rebuild flag."""
        from mellea_api.core.config import get_settings
        from mellea_api.services.environment_builder import get_environment_builder_service

        # Create workspace
        settings = get_settings()
        workspace_path = settings.data_dir / "workspaces" / sample_program_id
        workspace_path.mkdir(parents=True, exist_ok=True)
        (workspace_path / "main.py").write_text("print('hello')")

        # Get the service and inject mock Docker client
        builder = get_environment_builder_service()
        mock_client = MagicMock()
        mock_client.images.build.return_value = (MagicMock(), [])
        mock_client.images.get.return_value = MagicMock(attrs={"Size": 1000000})
        builder._docker_client = mock_client

        response = client.post(
            f"/api/v1/builds/programs/{sample_program_id}",
            json={"forceRebuild": True},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        # Force rebuild should result in cache miss
        assert data["cacheHit"] is False


class TestGetBuildJobStatus:
    """Tests for GET /api/v1/builds/jobs/{job_name} endpoint."""

    def test_get_build_job_not_found(self, client: TestClient) -> None:
        """Test getting status of non-existent job returns 404."""
        with patch(
            "mellea_api.services.kaniko_builder.KanikoBuildService.get_build_status"
        ) as mock_status:
            mock_status.side_effect = RuntimeError("Build job nonexistent-job not found")

            response = client.get("/api/v1/builds/jobs/nonexistent-job")

            assert response.status_code == 404


class TestGetBuildJobLogs:
    """Tests for GET /api/v1/builds/jobs/{job_name}/logs endpoint."""

    def test_get_build_logs_not_found(self, client: TestClient) -> None:
        """Test getting logs of non-existent job returns 404."""
        with patch(
            "mellea_api.services.kaniko_builder.KanikoBuildService.get_build_logs"
        ) as mock_logs:
            mock_logs.side_effect = RuntimeError("Failed to get build logs: not found")

            response = client.get("/api/v1/builds/jobs/nonexistent-job/logs")

            assert response.status_code == 404


class TestDeleteBuildJob:
    """Tests for DELETE /api/v1/builds/jobs/{job_name} endpoint."""

    def test_delete_build_job_not_found(self, client: TestClient) -> None:
        """Test deleting non-existent job returns 404."""
        with patch(
            "mellea_api.services.kaniko_builder.KanikoBuildService.delete_build_job"
        ) as mock_delete:
            mock_delete.return_value = False

            response = client.delete("/api/v1/builds/jobs/nonexistent-job")

            assert response.status_code == 404

    def test_delete_build_job_success(self, client: TestClient) -> None:
        """Test successful job deletion."""
        with patch(
            "mellea_api.services.kaniko_builder.KanikoBuildService.delete_build_job"
        ) as mock_delete:
            mock_delete.return_value = True

            response = client.delete("/api/v1/builds/jobs/mellea-build-test1234")

            assert response.status_code == 200
            data = response.json()
            assert data["deleted"] is True


class TestCacheOperations:
    """Tests for cache-related endpoints."""

    def test_get_cache_stats_empty(self, client: TestClient) -> None:
        """Test getting cache stats when empty."""
        response = client.get("/api/v1/builds/cache")

        assert response.status_code == 200
        data = response.json()
        assert data["totalEntries"] == 0
        assert data["entries"] == []

    def test_invalidate_cache_entry_not_found(self, client: TestClient) -> None:
        """Test invalidating non-existent cache entry returns 404."""
        response = client.delete("/api/v1/builds/cache/nonexistent-key")
        assert response.status_code == 404

    def test_prune_cache(self, client: TestClient) -> None:
        """Test pruning cache entries."""
        response = client.post("/api/v1/builds/cache/prune?max_age_days=30")

        assert response.status_code == 200
        data = response.json()
        assert "pruned" in data
        assert data["max_age_days"] == 30
