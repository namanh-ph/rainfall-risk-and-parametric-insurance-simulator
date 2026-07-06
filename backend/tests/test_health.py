"""Smoke tests for the /health and /health/db routes."""

from __future__ import annotations

from fastapi.testclient import TestClient

from src.main import app

client = TestClient(app)


def test_health_returns_200_ok() -> None:
    response = client.get("/health")
    assert response.status_code == 200


def test_health_payload_status_is_ok() -> None:
    payload = client.get("/health").json()
    assert payload["status"] == "ok"


def test_health_payload_service_name() -> None:
    payload = client.get("/health").json()
    assert payload["service"] == "simulator-backend"


def test_health_payload_environment_present() -> None:
    payload = client.get("/health").json()
    assert "environment" in payload
    assert isinstance(payload["environment"], str) and payload["environment"]


def test_health_db_returns_200_with_structured_payload_even_without_postgres() -> None:
    response = client.get("/health/db")
    assert response.status_code == 200
    payload = response.json()
    assert "database" in payload
    assert "postgis" in payload
    assert payload["database"]["status"] in {"ok", "error"}
    assert payload["postgis"]["status"] in {"ok", "error"}
