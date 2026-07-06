"""HTTP layer (FastAPI routers, request/response schemas).

Domain routers (assets, portfolio, map, simulate, model, reports) are
wired.
"""

from src.api.routes_health import router as health_router

__all__ = ["health_router"]
