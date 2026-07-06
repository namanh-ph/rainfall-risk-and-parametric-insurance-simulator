"""Tests for src.core.config."""

from __future__ import annotations

from src.core.config import Settings, get_settings


def test_settings_load_with_defaults() -> None:
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.PROJECT_NAME == "Simulator"
    assert settings.ENVIRONMENT == "local"
    assert settings.BACKEND_HOST == "0.0.0.0"
    assert settings.BACKEND_PORT == 8000
    assert settings.MLFLOW_TRACKING_URI == "http://localhost:5000"
    assert settings.DATABASE_URL.startswith("postgresql+psycopg://")


def test_cors_origins_parses_comma_separated_string() -> None:
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None,
        BACKEND_CORS_ORIGINS="http://localhost:5173, http://localhost:3000",
    )
    assert settings.BACKEND_CORS_ORIGINS == [
        "http://localhost:5173",
        "http://localhost:3000",
    ]


def test_cors_origins_accepts_explicit_list() -> None:
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None,
        BACKEND_CORS_ORIGINS=["http://localhost:5173"],
    )
    assert settings.BACKEND_CORS_ORIGINS == ["http://localhost:5173"]


def test_cors_origins_empty_string_yields_empty_list() -> None:
    settings = Settings(_env_file=None, BACKEND_CORS_ORIGINS="")  # type: ignore[call-arg]
    assert settings.BACKEND_CORS_ORIGINS == []


def test_get_settings_returns_settings_object_and_is_cached() -> None:
    get_settings.cache_clear()
    first = get_settings()
    second = get_settings()
    assert isinstance(first, Settings)
    assert first is second


def test_database_url_can_be_overridden() -> None:
    settings = Settings(_env_file=None, DATABASE_URL="sqlite+pysqlite:///:memory:")  # type: ignore[call-arg]
    assert settings.DATABASE_URL == "sqlite+pysqlite:///:memory:"
