"""Static-file checks for the Alembic configuration"""

from __future__ import annotations

from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"
ALEMBIC_DIR = BACKEND_ROOT / "alembic"
ALEMBIC_ENV = ALEMBIC_DIR / "env.py"
VERSIONS_DIR = ALEMBIC_DIR / "versions"

CANONICAL_TABLES = (
    "assets",
    "rainfall_stations",
    "rainfall_observations",
    "asset_station_mapping",
    "lga_boundaries",
    "rainfall_features",
    "asset_risk_scores",
    "simulation_runs",
    "payout_results",
    "model_training_data",
    "model_predictions",
)


def _load_migration_text() -> str:
    files = [
        path
        for path in VERSIONS_DIR.glob("*.py")
        if path.name not in {"__init__.py"} and not path.name.startswith(".")
    ]
    assert files, "expected at least one migration in alembic/versions"
    # Return the concatenated text so tests are agnostic to revision split
    return "\n".join(path.read_text(encoding="utf-8") for path in files)


def test_alembic_ini_exists() -> None:
    assert ALEMBIC_INI.is_file()


def test_alembic_env_exists() -> None:
    assert ALEMBIC_ENV.is_file()


def test_versions_directory_has_migration() -> None:
    files = [path for path in VERSIONS_DIR.glob("*.py") if path.name != "__init__.py"]
    assert files, "no Alembic migration files found"


def test_migration_creates_postgis_extension() -> None:
    text = _load_migration_text()
    assert "CREATE EXTENSION IF NOT EXISTS postgis" in text


def test_migration_references_all_canonical_tables() -> None:
    text = _load_migration_text()
    missing = [name for name in CANONICAL_TABLES if name not in text]
    assert not missing, f"Migration is missing references to: {missing}"
