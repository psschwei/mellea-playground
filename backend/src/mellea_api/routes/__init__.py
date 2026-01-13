"""API route modules."""

from mellea_api.routes.assets import router as assets_router
from mellea_api.routes.auth import router as auth_router
from mellea_api.routes.health import router as health_router
from mellea_api.routes.runs import router as runs_router

__all__ = ["assets_router", "auth_router", "health_router", "runs_router"]
