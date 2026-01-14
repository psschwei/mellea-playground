"""Application configuration using Pydantic Settings."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="MELLEA_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application
    app_name: str = "Mellea Playground API"
    debug: bool = False
    environment: Literal["development", "staging", "production"] = "development"

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    # Storage
    data_dir: Path = Path("data")

    # Redis
    redis_url: str = "redis://localhost:6379"

    # OpenTelemetry
    otel_enabled: bool = True
    otel_service_name: str = "mellea-api"
    otel_exporter_endpoint: str = "http://localhost:4317"

    # Security
    secret_key: str = "dev-secret-key-change-in-production"
    access_token_expire_minutes: int = 60 * 24  # 24 hours

    # Container Registry
    registry_url: str | None = None  # e.g., "registry.example.com", "ghcr.io/user", "quay.io/org"
    registry_username: str | None = None
    registry_password: str | None = None

    # Build Backend
    build_backend: Literal["docker", "kaniko"] = "docker"
    build_namespace: str = "mellea-builds"
    kaniko_image: str = "gcr.io/kaniko-project/executor:v1.23.0"
    build_timeout_seconds: int = 1800  # 30 minutes
    build_cpu_limit: str = "2"
    build_memory_limit: str = "2Gi"

    # Idle Timeout Controller
    idle_controller_enabled: bool = True
    idle_controller_interval_seconds: int = 300  # 5 minutes between checks
    environment_idle_timeout_minutes: int = 60  # Stop environments idle for 1 hour
    run_retention_days: int = 7  # Delete completed runs after 7 days
    stale_job_timeout_minutes: int = 30  # Clean up orphaned K8s jobs

    # Environment Warmup Controller
    warmup_enabled: bool = True
    warmup_interval_seconds: int = 60  # Check warmup pool every minute
    warmup_pool_size: int = 3  # Number of warm environments to maintain
    warmup_max_age_minutes: int = 30  # Recycle warm envs older than this
    warmup_popular_deps_count: int = 5  # Pre-build top N popular dependency sets

    def ensure_data_dirs(self) -> None:
        """Create data directory structure if it doesn't exist."""
        subdirs = ["metadata", "workspaces", "artifacts", "runs"]
        for subdir in subdirs:
            (self.data_dir / subdir).mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
