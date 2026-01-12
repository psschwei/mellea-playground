"""Tests for health check endpoints."""

import pytest
from fastapi.testclient import TestClient

from mellea_api.main import app


@pytest.fixture
def client() -> TestClient:
    """Create a test client."""
    return TestClient(app)


def test_health_check(client: TestClient) -> None:
    """Test the health endpoint returns healthy status."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "timestamp" in data
    assert "version" in data
    assert "environment" in data


def test_startup_check(client: TestClient) -> None:
    """Test the startup endpoint returns started status."""
    response = client.get("/startup")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "started"


def test_readiness_check(client: TestClient) -> None:
    """Test the readiness endpoint returns check results."""
    response = client.get("/ready")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "timestamp" in data
    assert "checks" in data
