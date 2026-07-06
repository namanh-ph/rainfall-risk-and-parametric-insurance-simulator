# Rainfall Risk And Parametric Insurance Simulator

## Overview

This is a full-stack analytics project for simulating rainfall risk and parametric insurance payouts across a asset portfolio of Victoria, Australia. In this project, I intend to demonstrates how rainfall exposure can be converted into risk insights and insurance payout outcomes. This projects answers a question: " For a portfolio of Victorian SME or property assets, which locations are most exposed to extreme rainfall, and how much would a parametric insurance product pay out in case of extreme rainfall?"

## Features

- Victorian SME and property asset portfolio loaded from CSV
- Bureau of Meteorology rainfall stations and daily observations
- Victorian LGA boundaries from the Australian Bureau of Statistics
- Asset-to-rainfall-station matching using geospatial distance
- Asset-to-LGA assignment using PostGIS spatial joins
- Rainfall feature engineering across 1-day, 3-day, 7-day, and 30-day windows
- Rule-based rainfall risk scoring on a 0-100 scale
- Risk-band classification for portfolio segmentation
- Parametric payout simulation based on rainfall trigger thresholds
- Threshold and coverage-multiplier sensitivity analysis
- LightGBM model training for rainfall risk ranking
- MLflow experiment tracking
- FastAPI backend for asset, portfolio, simulation, model, and report endpoints
- React dashboard with map, KPIs, charts, filters, rankings, and payout views
- Static HTML portfolio report export

## Tech Stack

- Backend: Python, FastAPI, SQLAlchemy, Alembic
- Database: PostgreSQL, PostGIS
- Data and geospatial: pandas, GeoPandas, Shapely
- Machine learning: LightGBM, MLflow, scikit-learn
- Frontend: React, TypeScript, Vite, Tailwind CSS
- Visualisation: Leaflet, Recharts
- Infrastructure: Docker Compose, Makefile
