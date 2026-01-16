"""API route modules."""

from mellea_api.routes.archive_upload import router as archive_upload_router
from mellea_api.routes.artifacts import router as artifacts_router
from mellea_api.routes.assets import router as assets_router
from mellea_api.routes.auth import router as auth_router
from mellea_api.routes.builds import router as builds_router
from mellea_api.routes.controller import router as controller_router
from mellea_api.routes.credentials import router as credentials_router
from mellea_api.routes.environments import router as environments_router
from mellea_api.routes.github_import import router as github_import_router
from mellea_api.routes.health import router as health_router
from mellea_api.routes.runs import router as runs_router

__all__ = [
    "archive_upload_router",
    "artifacts_router",
    "assets_router",
    "auth_router",
    "builds_router",
    "controller_router",
    "credentials_router",
    "environments_router",
    "github_import_router",
    "health_router",
    "runs_router",
]
