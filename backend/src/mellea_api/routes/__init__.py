"""API route modules."""

from mellea_api.routes.archive_upload import router as archive_upload_router
from mellea_api.routes.artifacts import router as artifacts_router
from mellea_api.routes.assets import router as assets_router
from mellea_api.routes.audit import router as audit_router
from mellea_api.routes.auth import router as auth_router
from mellea_api.routes.builds import router as builds_router
from mellea_api.routes.composition_runs import router as composition_runs_router
from mellea_api.routes.controller import router as controller_router
from mellea_api.routes.credentials import router as credentials_router
from mellea_api.routes.environments import router as environments_router
from mellea_api.routes.github_import import router as github_import_router
from mellea_api.routes.health import router as health_router
from mellea_api.routes.llm_metrics import router as llm_metrics_router
from mellea_api.routes.notifications import admin_router as notifications_admin_router
from mellea_api.routes.notifications import router as notifications_router
from mellea_api.routes.notifications import ws_router as notifications_ws_router
from mellea_api.routes.retention import router as retention_router
from mellea_api.routes.run_audit import router as run_audit_router
from mellea_api.routes.runs import router as runs_router
from mellea_api.routes.sharing import router as sharing_router

__all__ = [
    "archive_upload_router",
    "artifacts_router",
    "assets_router",
    "audit_router",
    "auth_router",
    "builds_router",
    "composition_runs_router",
    "controller_router",
    "credentials_router",
    "environments_router",
    "github_import_router",
    "health_router",
    "llm_metrics_router",
    "notifications_admin_router",
    "notifications_router",
    "notifications_ws_router",
    "retention_router",
    "run_audit_router",
    "runs_router",
    "sharing_router",
]
