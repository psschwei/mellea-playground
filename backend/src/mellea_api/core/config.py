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

    def ensure_data_dirs(self) -> None:
        """Create data directory structure if it doesn't exist."""
        subdirs = ["metadata", "workspaces", "artifacts", "runs"]
        for subdir in subdirs:
            (self.data_dir / subdir).mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
