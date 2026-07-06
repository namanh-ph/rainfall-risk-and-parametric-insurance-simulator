"""OpenAPI schema coverage tests for the API surface."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.main import app

client = TestClient(app)


@pytest.fixture(scope="module")
def openapi_schema() -> dict:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    return response.json()


def test_openapi_endpoint_is_available(openapi_schema: dict) -> None:
    assert openapi_schema["openapi"].startswith("3.")
    assert "paths" in openapi_schema


@pytest.mark.parametrize(
    "path",
    [
        "/assets",
        "/assets/{asset_id}",
        "/assets/{asset_id}/risk",
        "/assets/{asset_id}/rainfall",
        "/assets/{asset_id}/station",
        "/map/assets",
        "/map/lgas",
        "/map/stations",
    ],
)
def test_openapi_contains_asset_map_bare_path(
    openapi_schema: dict, path: str
) -> None:
    assert path in openapi_schema["paths"], f"OpenAPI missing {path}"


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/assets",
        "/api/v1/assets/{asset_id}",
        "/api/v1/assets/{asset_id}/risk",
        "/api/v1/assets/{asset_id}/rainfall",
        "/api/v1/assets/{asset_id}/station",
        "/api/v1/map/assets",
        "/api/v1/map/lgas",
        "/api/v1/map/stations",
    ],
)
def test_openapi_contains_asset_map_v1_path(
    openapi_schema: dict, path: str
) -> None:
    assert path in openapi_schema["paths"], f"OpenAPI missing {path}"


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/portfolio/summary",
        "/api/v1/portfolio/risk-ranking",
        "/api/v1/simulate/payout",
        "/api/v1/simulate/threshold-sensitivity",
        "/api/v1/model/metadata",
        "/api/v1/model/predictions",
        "/api/v1/model/predictions/{asset_id}",
    ],
)
def test_openapi_contains_business_v1_path(
    openapi_schema: dict, path: str
) -> None:
    assert path in openapi_schema["paths"], f"OpenAPI missing {path}"


def test_openapi_includes_health_routes(openapi_schema: dict) -> None:
    paths = openapi_schema["paths"]
    assert "/health" in paths
    assert "/health/db" in paths
    # versioned aliases
    assert "/api/v1/health" in paths
    assert "/api/v1/health/db" in paths


def test_openapi_includes_report_export(openapi_schema: dict) -> None:
    """Report export must be discoverable via OpenAPI."""
    paths = openapi_schema["paths"]
    assert "/api/v1/reports/export" in paths
    # The bare alias is intentionally NOT mounted to keep the mutating
    # report endpoint scoped to /api/v1 only
    assert "/reports/export" not in paths


def test_openapi_report_export_uses_post(openapi_schema: dict) -> None:
    paths = openapi_schema["paths"]
    operations = paths.get("/api/v1/reports/export", {})
    assert "post" in operations
    # Sanity-check the response schema is wired through
    responses = operations["post"].get("responses", {})
    assert "200" in responses or "201" in responses
