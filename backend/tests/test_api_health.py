"""Smoke tests for the health endpoints, run via FastAPI TestClient."""

from __future__ import annotations

from fastapi.testclient import TestClient

from src.main import app

client = TestClient(app)


def test_health_returns_200() -> None:
    response = client.get("/health")
    assert response.status_code == 200


def test_health_payload_shape() -> None:
    payload = client.get("/health").json()
    assert payload["status"] == "ok"
    assert payload["service"] == "simulator-backend"
    assert "environment" in payload and isinstance(payload["environment"], str)


def test_health_db_returns_200_with_structured_payload() -> None:
    response = client.get("/health/db")
    assert response.status_code == 200
    payload = response.json()
    assert "database" in payload
    assert "postgis" in payload
    assert payload["database"]["status"] in {"ok", "error"}
    assert payload["postgis"]["status"] in {"ok", "error"}
