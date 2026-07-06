"""FastAPI application factory."""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes_assets import router as assets_router
from src.api.routes_health import router as health_router
from src.api.routes_map import router as map_router
from src.api.routes_model import router as model_router
from src.api.routes_portfolio import router as portfolio_router
from src.api.routes_reports import router as reports_router
from src.api.routes_simulation import router as simulation_router
from src.core.config import get_settings
from src.core.logging import configure_logging

SERVICE_VERSION = "0.1.0"
API_V1_PREFIX = "/api/v1"


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.LOG_LEVEL)
    logger = logging.getLogger(__name__)

    app = FastAPI(
        title=settings.PROJECT_NAME,
        version=SERVICE_VERSION,
        description=(
            "Rainfall-risk and parametric-insurance simulator for Victorian "
            "SME and property assets."
        ),
    )

    if settings.BACKEND_CORS_ORIGINS:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.BACKEND_CORS_ORIGINS,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # Canonical /api/v1 mount — every router lives here
    app.include_router(health_router, prefix=API_V1_PREFIX)
    app.include_router(assets_router, prefix=API_V1_PREFIX)
    app.include_router(map_router, prefix=API_V1_PREFIX)
    app.include_router(portfolio_router, prefix=API_V1_PREFIX)
    app.include_router(simulation_router, prefix=API_V1_PREFIX)
    app.include_router(model_router, prefix=API_V1_PREFIX)
    app.include_router(reports_router, prefix=API_V1_PREFIX)

    # Backwards-compatible bare aliases for health and selected routers
    app.include_router(health_router)
    app.include_router(assets_router)
    app.include_router(map_router)

    logger.info(
        "app=%s version=%s environment=%s",
        settings.PROJECT_NAME,
        SERVICE_VERSION,
        settings.ENVIRONMENT,
    )
    return app


app = create_app()
