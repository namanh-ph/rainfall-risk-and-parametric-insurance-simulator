FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

# System deps for GeoPandas/Shapely/psycopg, plus build essentials for LightGBM wheels
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        libgeos-dev \
        libproj-dev \
        libgdal-dev \
        gdal-bin \
        libpq-dev \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml /app/pyproject.toml

RUN pip install --upgrade pip && pip install -e ".[dev]"

COPY . /app

EXPOSE 8000

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
