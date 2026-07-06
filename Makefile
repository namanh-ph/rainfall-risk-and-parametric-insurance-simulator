# ──────────────────────────────────────────────────────────────────────
# Simulator — developer Makefile
# Targets are documented inline; `make help` parses the `## ` annotations.
# ──────────────────────────────────────────────────────────────────────

SHELL := /bin/bash
COMPOSE ?= docker compose
BACKEND_SVC ?= backend
FRONTEND_SVC ?= frontend

.DEFAULT_GOAL := help
.PHONY: help up down logs ps build \
        backend-dev backend-shell backend-test backend-lint backend-format backend-typecheck \
        frontend-install frontend-dev frontend-shell frontend-test frontend-lint frontend-typecheck frontend-build \
        fullstack-dev fullstack-smoke \
        test lint format \
        migrate seed features score simulate train predict report \
        export-report seed-report refresh \
        clean

help: ## Show this help
	@awk 'BEGIN {FS = ":.*## "; printf "\nUsage: make <target>\n\nTargets:\n"} /^[a-zA-Z_-]+:.*## / {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# ── Compose lifecycle ────────────────────────────────────────────────
up: ## Start all services in the background (postgres, backend, frontend, mlflow)
	$(COMPOSE) up -d

down: ## Stop all services and remove containers
	$(COMPOSE) down

logs: ## Tail logs for all services
	$(COMPOSE) logs -f --tail=100

ps: ## Show service status
	$(COMPOSE) ps

build: ## Rebuild all service images
	$(COMPOSE) build

# ── Backend ──────────────────────────────────────────────────────────
backend-dev: ## Run the backend service in the foreground
	$(COMPOSE) up $(BACKEND_SVC)

backend-shell: ## Open a shell inside the backend container
	$(COMPOSE) exec $(BACKEND_SVC) /bin/bash

backend-api: ## Run the FastAPI app via uvicorn (host 0.0.0.0:8000)
	cd backend && uvicorn src.main:app --host 0.0.0.0 --port 8000

api-smoke: ## Hit the bare-path endpoints against a local server
	curl -s http://localhost:8000/health
	curl -s "http://localhost:8000/assets?limit=5"
	curl -s "http://localhost:8000/map/assets?limit=5"
	curl -s http://localhost:8000/map/lgas
	curl -s http://localhost:8000/map/stations

api-smoke-v1: ## Hit the /api/v1 endpoints
	curl -s http://localhost:8000/health
	curl -s "http://localhost:8000/api/v1/assets?limit=5"
	curl -s "http://localhost:8000/api/v1/map/assets?limit=5"
	curl -s http://localhost:8000/api/v1/portfolio/summary
	curl -s "http://localhost:8000/api/v1/portfolio/risk-ranking?limit=5"
	curl -s http://localhost:8000/api/v1/model/metadata
	curl -s "http://localhost:8000/api/v1/model/predictions?limit=5"
	curl -s -X POST http://localhost:8000/api/v1/reports/export \
	  -H "Content-Type: application/json" \
	  -d '{"as_of_date":"2025-12-31","simulation_id":"DEFAULT_2025_BASELINE","model_name":"rainfall_risk_lgbm","model_version":"v1","feature_version":"rainfall_risk_features_v1"}'

backend-test: ## Run backend pytest suite
	$(COMPOSE) exec $(BACKEND_SVC) pytest

backend-lint: ## Run ruff against backend source
	$(COMPOSE) exec $(BACKEND_SVC) ruff check .

backend-format: ## Run black + ruff --fix on backend source
	$(COMPOSE) exec $(BACKEND_SVC) bash -lc "black . && ruff check --fix ."

backend-typecheck: ## Run mypy against backend src
	$(COMPOSE) exec $(BACKEND_SVC) mypy src

# ── Frontend ─────────────────────────────────────────────────────────
frontend-install: ## Install local frontend dependencies (npm)
	cd frontend && npm install

frontend-dev: ## Run the Vite dev server locally (host 0.0.0.0:5173)
	cd frontend && npm run dev

frontend-shell: ## Open a shell inside the frontend container
	$(COMPOSE) exec $(FRONTEND_SVC) /bin/sh

frontend-test: ## Run the Vitest test suite
	cd frontend && npm test

frontend-lint: ## Run frontend ESLint
	cd frontend && npm run lint

frontend-typecheck: ## Run frontend TypeScript typecheck
	cd frontend && npm run typecheck

frontend-build: ## Build the frontend for production
	cd frontend && npm run build

# ── Full-stack convenience ───────────────────────────────────────────
fullstack-dev: ## Start the FastAPI backend locally (frontend run separately)
	$(MAKE) backend-api

fullstack-smoke: ## Hit /api/v1 smoke endpoints and build the frontend
	$(MAKE) api-smoke-v1
	cd frontend && npm run build

# ── Aggregates ───────────────────────────────────────────────────────
test: backend-test frontend-test ## Run all tests
lint: backend-lint frontend-lint ## Run all linters
format: backend-format ## Run formatters

# ── Alembic migrations ───────────────────────────────────────────────
backend-migrate: ## Run Alembic migrations against the configured database
	$(COMPOSE) exec $(BACKEND_SVC) alembic upgrade head

backend-downgrade: ## Roll back the most recent migration
	$(COMPOSE) exec $(BACKEND_SVC) alembic downgrade -1

backend-revision: ## Generate a new Alembic revision (use MSG="message" NAME="rev_name")
	$(COMPOSE) exec $(BACKEND_SVC) alembic revision --autogenerate -m "$(MSG)"

# ── Ingestion ────────────────────────────────────────────────────────
ingest-assets: ## Load the asset CSV into the assets table
	cd backend && python -m src.cli.ingest_data --assets --replace-existing

ingest-rainfall: ## Load rainfall stations and daily observations
	cd backend && python -m src.cli.ingest_data --rainfall --replace-existing

ingest-boundaries: ## Load Victorian LGA boundaries
	cd backend && python -m src.cli.ingest_data --boundaries --replace-existing

ingest-data: ## Load assets + rainfall + LGA boundaries (in order)
	cd backend && python -m src.cli.ingest_data --assets --rainfall --boundaries --replace-existing

# ── Geospatial matching ──────────────────────────────────────────────
match-stations: ## Match every asset to its nearest rainfall station (PostGIS)
	cd backend && python -m src.cli.match_stations --replace-existing

assign-lgas: ## Assign every asset to a Victorian LGA via PostGIS spatial join
	cd backend && python -m src.cli.assign_lgas --replace-existing --allow-nearest-fallback --max-fallback-distance-km 25

seed-matching: ingest-data match-stations ## Ingest + nearest-station match
seed-geospatial: ingest-data match-stations assign-lgas ## Ingest + station match + LGA assignment

# ── Feature engineering ──────────────────────────────────────────────
generate-rainfall-features: ## Engineer rainfall features (1d/3d/7d/30d, p95/p99, extreme flag)
	cd backend && python -m src.cli.generate_features --rainfall --as-of-date 2025-12-31 --replace-existing

seed-features: seed-geospatial generate-rainfall-features ## Full geospatial pipeline + rainfall features

# ── Risk scoring ─────────────────────────────────────────────────────
score-risk: ## Compute rule-based rainfall risk scores into asset_risk_scores
	cd backend && python -m src.cli.score_risk --as-of-date 2025-12-31 --replace-existing

seed-risk: seed-features score-risk ## Full pipeline + risk scoring

# ── Parametric payout simulation ─────────────────────────────────────
simulate-payouts: ## Simulate parametric rainfall payouts → payout_results
	cd backend && python -m src.cli.simulate_payouts --as-of-date 2025-12-31 --replace-existing

seed-payouts: seed-risk simulate-payouts ## Full pipeline + payout simulation

# ── Threshold + coverage-multiplier sensitivity ──────────────────────
run-threshold-sensitivity: ## Run threshold-sensitivity suite (baseline + 3 sweeps)
	cd backend && python -m src.cli.run_sensitivity --thresholds --as-of-date 2025-12-31 --replace-existing

run-coverage-sensitivity: ## Run coverage-multiplier sensitivity suite (0.75, 1.00, 1.25, 1.50)
	cd backend && python -m src.cli.run_sensitivity --coverage-multipliers --as-of-date 2025-12-31 --replace-existing

run-combined-sensitivity: ## Run both sensitivity suites
	cd backend && python -m src.cli.run_sensitivity --combined --as-of-date 2025-12-31 --replace-existing

seed-sensitivity: seed-payouts run-combined-sensitivity ## Full pipeline + payouts + combined sensitivity

# ── ML training-data construction ────────────────────────────────────
build-training-data: ## Build model_training_data rows for as_of_date 2025-12-31
	cd backend && python -m src.cli.build_training_data --as-of-date 2025-12-31 --feature-version rainfall_risk_features_v1 --replace-existing

seed-training-data: seed-sensitivity build-training-data ## Full pipeline + sensitivity + ML training-data

# ── LightGBM training ────────────────────────────────────────────────
train-model: ## Train LightGBM risk-ranking model from model_training_data
	cd backend && python -m src.cli.train_model --as-of-date 2025-12-31 --feature-version rainfall_risk_features_v1 --model-name rainfall_risk_lgbm --model-version v1

seed-model: seed-training-data train-model ## Full pipeline + ML training-data + LightGBM model

# ── Batch prediction ─────────────────────────────────────────────────
predict-model: ## Load the trained LightGBM artefact and persist model_predictions
	cd backend && python -m src.cli.predict_model --as-of-date 2025-12-31 --feature-version rainfall_risk_features_v1 --model-name rainfall_risk_lgbm --model-version v1 --replace-existing

seed-predictions: seed-model predict-model ## Full pipeline + model training + batch predictions

# ── HTML report export ───────────────────────────────────────────────
export-report: ## Export the HTML portfolio risk report from persisted analytics outputs
	cd backend && python -m src.cli.export_report --as-of-date 2025-12-31 --simulation-id DEFAULT_2025_BASELINE --model-name rainfall_risk_lgbm --model-version v1 --feature-version rainfall_risk_features_v1

seed-report: seed-predictions export-report ## Full seed pipeline + HTML report export

refresh: seed-report ## Edit CSVs then run this: full re-ingest + every derived table rebuilt

# ── Domain pipeline aliases ──────────────────────────────────────────
migrate: backend-migrate ## Alias for backend-migrate

seed: ingest-data ## Alias for ingest-data — populates assets and rainfall tables

features: generate-rainfall-features ## Alias for generate-rainfall-features

score: score-risk ## Alias for score-risk

simulate: simulate-payouts ## Alias for simulate-payouts

train: train-model ## Alias for train-model

predict: predict-model ## Alias for predict-model

report: export-report ## Alias for export-report (HTML portfolio report export)

# ── Housekeeping ─────────────────────────────────────────────────────
clean: ## Remove caches and build artefacts
	@find . -type d -name "__pycache__" -prune -exec rm -rf {} +
	@find . -type d -name ".pytest_cache" -prune -exec rm -rf {} +
	@find . -type d -name ".mypy_cache" -prune -exec rm -rf {} +
	@find . -type d -name ".ruff_cache" -prune -exec rm -rf {} +
	@rm -rf backend/dist frontend/dist frontend/.vite
