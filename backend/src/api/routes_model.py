"""Model metadata and prediction HTTP endpoints (read-only)"""

from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.api.deps import (
    get_db,
    pagination_params,
    parse_as_of_date,
    validate_asset_id,
    validate_risk_band,
)
from src.schemas.api_common import PaginationMeta
from src.schemas.api_model import (
    ModelMetadataResponse,
    ModelPredictionDetailResponse,
    ModelPredictionItem,
    ModelPredictionListResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["model"])

DEFAULT_MODEL_NAME = "rainfall_risk_lgbm"
DEFAULT_MODEL_VERSION = "v1"
DEFAULT_FEATURE_VERSION = "rainfall_risk_features_v1"
ARTIFACT_ROOT = Path("../backend/artifacts/models")
LOCAL_ARTIFACT_ROOT = Path("artifacts/models")

_ALLOWED_PREDICTION_SORT_FIELDS: dict[str, str] = {
    "ml_risk_rank": "mp.ml_risk_rank",
    "ml_risk_probability": "mp.ml_risk_probability",
    "risk_score": "ars.risk_score",
    "asset_value": "a.asset_value",
    "coverage_limit": "a.coverage_limit",
}


def _default_artifact_dir(
    model_name: str, model_version: str, as_of_date: date
) -> Path:
    """Probe a few candidate locations for the artefact directory"""
    name = f"{model_name}_{model_version}_{as_of_date.isoformat()}"
    candidates = (
        LOCAL_ARTIFACT_ROOT / name,           # invoked from backend/
        ARTIFACT_ROOT / name,                  # invoked from repo root
        Path("backend/artifacts/models") / name,
    )
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return candidates[0]


def _load_artifact_metadata(artifact_dir: Path) -> dict[str, Any]:
    """Read metadata.json + metrics.json if present; tolerate missing files"""
    metadata: dict[str, Any] = {}
    metadata_file = artifact_dir / "metadata.json"
    metrics_file = artifact_dir / "metrics.json"
    if metadata_file.is_file():
        try:
            metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            logger.warning("Failed to parse metadata.json at %s: %s", metadata_file, exc)
            metadata = {}
    if metrics_file.is_file():
        try:
            metadata["metrics"] = json.loads(metrics_file.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            logger.warning("Failed to parse metrics.json at %s: %s", metrics_file, exc)
    return metadata


def _fetch_prediction_count(
    db: Session,
    *,
    as_of_date: date,
    model_name: str,
    model_version: str,
) -> int:
    sql = text(
        """
        SELECT COUNT(*)
        FROM model_predictions
        WHERE as_of_date = :as_of_date
          AND model_name = :model_name
          AND model_version = :model_version
        """
    )
    value = db.execute(
        sql,
        {
            "as_of_date": as_of_date,
            "model_name": model_name,
            "model_version": model_version,
        },
    ).scalar()
    return int(value or 0)


@router.get("/model/metadata", response_model=ModelMetadataResponse)
def get_model_metadata(
    as_of_date: date = Depends(parse_as_of_date),
    feature_version: str = Query(DEFAULT_FEATURE_VERSION),
    model_name: str = Query(DEFAULT_MODEL_NAME),
    model_version: str = Query(DEFAULT_MODEL_VERSION),
    artifact_dir: str | None = Query(None),
    db: Session = Depends(get_db),
) -> ModelMetadataResponse:
    artifact_path = Path(artifact_dir) if artifact_dir else _default_artifact_dir(
        model_name, model_version, as_of_date
    )
    artefact_metadata = _load_artifact_metadata(artifact_path)
    prediction_count = _fetch_prediction_count(
        db,
        as_of_date=as_of_date,
        model_name=model_name,
        model_version=model_version,
    )

    payload: dict[str, Any] = {
        "model_name": artefact_metadata.get("model_name") or model_name,
        "model_version": artefact_metadata.get("model_version") or model_version,
        "as_of_date": as_of_date,
        "feature_version": artefact_metadata.get("feature_version") or feature_version,
        "target_name": artefact_metadata.get("target_name"),
        "artifact_path": (
            artefact_metadata.get("artifact_path") or str(artifact_path)
        ),
        "metrics": artefact_metadata.get("metrics"),
        "feature_count": artefact_metadata.get("feature_count"),
        "train_row_count": artefact_metadata.get("train_row_count"),
        "test_row_count": artefact_metadata.get("test_row_count"),
        "positive_count": artefact_metadata.get("positive_count"),
        "negative_count": artefact_metadata.get("negative_count"),
        "positive_rate": artefact_metadata.get("positive_rate"),
        "mlflow_logged": artefact_metadata.get("mlflow_logged"),
        "mlflow_run_id": artefact_metadata.get("mlflow_run_id"),
        "prediction_count": prediction_count,
        "created_at": artefact_metadata.get("created_at"),
    }
    return ModelMetadataResponse.model_validate(payload)


_PRED_BASE_FROM = """
FROM model_predictions mp
JOIN assets a ON a.asset_id = mp.asset_id
LEFT JOIN lga_boundaries l ON l.lga_code = a.lga_code
LEFT JOIN asset_risk_scores ars
    ON ars.asset_id = mp.asset_id AND ars.as_of_date = mp.as_of_date
WHERE mp.as_of_date = :as_of_date
  AND mp.model_name = :model_name
  AND mp.model_version = :model_version
"""


def _fetch_prediction_list(
    db: Session,
    *,
    limit: int,
    offset: int,
    as_of_date: date,
    model_name: str,
    model_version: str,
    risk_band: str | None,
    industry: str | None,
    lga_code: str | None,
    sort_column: str,
    sort_order: str,
) -> tuple[list[dict[str, Any]], int]:
    params: dict[str, Any] = {
        "as_of_date": as_of_date,
        "model_name": model_name,
        "model_version": model_version,
        "limit": limit,
        "offset": offset,
    }
    extra_where: list[str] = []
    if risk_band is not None:
        extra_where.append("ars.risk_band = :risk_band")
        params["risk_band"] = risk_band
    if industry is not None:
        extra_where.append("a.industry = :industry")
        params["industry"] = industry
    if lga_code is not None:
        extra_where.append("a.lga_code = :lga_code")
        params["lga_code"] = lga_code
    extra_where_sql = (" AND " + " AND ".join(extra_where)) if extra_where else ""

    count_sql = text(f"SELECT COUNT(*) {_PRED_BASE_FROM} {extra_where_sql}")
    total = db.execute(count_sql, params).scalar() or 0

    list_sql = text(
        f"""
SELECT
    mp.asset_id, a.business_type, a.industry, a.postcode,
    a.lga_code, l.lga_name,
    ars.risk_score, ars.risk_band,
    mp.ml_risk_probability, mp.ml_risk_rank, mp.top_risk_driver,
    mp.as_of_date, mp.model_name, mp.model_version
{_PRED_BASE_FROM}
{extra_where_sql}
ORDER BY {sort_column} {sort_order} NULLS LAST, mp.asset_id ASC
LIMIT :limit OFFSET :offset
"""
    )
    rows = db.execute(list_sql, params).all()
    return [dict(row._mapping) for row in rows], int(total)


def _asset_exists(db: Session, asset_id: str) -> bool:
    result = db.execute(
        text("SELECT 1 FROM assets WHERE asset_id = :asset_id LIMIT 1"),
        {"asset_id": asset_id},
    ).first()
    return result is not None


def _fetch_prediction_detail(
    db: Session,
    *,
    asset_id: str,
    as_of_date: date,
    model_name: str,
    model_version: str,
) -> dict[str, Any] | None:
    sql = text(
        """
SELECT
    mp.asset_id, a.business_type, a.industry, a.postcode,
    a.lga_code, l.lga_name,
    ars.risk_score, ars.risk_band,
    rf.rainfall_3d_mm, rf.rainfall_percentile, rf.extreme_rainfall_flag,
    mp.ml_risk_probability, mp.ml_risk_rank, mp.top_risk_driver,
    mp.as_of_date, mp.model_name, mp.model_version
FROM model_predictions mp
JOIN assets a ON a.asset_id = mp.asset_id
LEFT JOIN lga_boundaries l ON l.lga_code = a.lga_code
LEFT JOIN asset_risk_scores ars
    ON ars.asset_id = mp.asset_id AND ars.as_of_date = mp.as_of_date
LEFT JOIN rainfall_features rf
    ON rf.asset_id = mp.asset_id AND rf.as_of_date = mp.as_of_date
WHERE mp.asset_id = :asset_id
  AND mp.as_of_date = :as_of_date
  AND mp.model_name = :model_name
  AND mp.model_version = :model_version
"""
    )
    row = db.execute(
        sql,
        {
            "asset_id": asset_id,
            "as_of_date": as_of_date,
            "model_name": model_name,
            "model_version": model_version,
        },
    ).first()
    return dict(row._mapping) if row else None


_VALID_SORT_COLUMNS = {
    "ml_risk_rank": "mp.ml_risk_rank",
    "ml_risk_probability": "mp.ml_risk_probability",
    "asset_id": "mp.asset_id",
    "risk_score": "ars.risk_score",
    "asset_value": "a.asset_value",
    "coverage_limit": "a.coverage_limit",
}


@router.get(
    "/model/predictions",
    response_model=ModelPredictionListResponse,
)
def get_model_predictions(
    as_of_date: date = Depends(parse_as_of_date),
    model_name: str = Query(DEFAULT_MODEL_NAME),
    model_version: str = Query(DEFAULT_MODEL_VERSION),
    risk_band: str | None = Query(None),
    industry: str | None = Query(None),
    lga_code: str | None = Query(None),
    sort_by: str = Query("ml_risk_rank"),
    sort_order: str = Query("asc"),
    pagination: dict[str, int] = Depends(pagination_params),
    db: Session = Depends(get_db),
) -> ModelPredictionListResponse:
    if risk_band is not None:
        risk_band = validate_risk_band(risk_band)
    if sort_by not in _VALID_SORT_COLUMNS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"sort_by must be one of {sorted(_VALID_SORT_COLUMNS)}",
        )
    if sort_order.lower() not in {"asc", "desc"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="sort_order must be 'asc' or 'desc'",
        )

    rows, total = _fetch_prediction_list(
        db,
        limit=pagination["limit"],
        offset=pagination["offset"],
        as_of_date=as_of_date,
        model_name=model_name,
        model_version=model_version,
        risk_band=risk_band,
        industry=industry,
        lga_code=lga_code,
        sort_column=_VALID_SORT_COLUMNS[sort_by],
        sort_order=sort_order.upper(),
    )

    return ModelPredictionListResponse(
        items=[ModelPredictionItem.model_validate(row) for row in rows],
        pagination=PaginationMeta(
            limit=pagination["limit"],
            offset=pagination["offset"],
            total=int(total),
            returned=len(rows),
        ),
        model_name=model_name,
        model_version=model_version,
        as_of_date=as_of_date,
        sort_by=sort_by,
        sort_order=sort_order.lower(),
    )


@router.get(
    "/model/predictions/{asset_id}",
    response_model=ModelPredictionDetailResponse,
)
def get_model_prediction(
    asset_id: str,
    as_of_date: date = Depends(parse_as_of_date),
    model_name: str = Query(DEFAULT_MODEL_NAME),
    model_version: str = Query(DEFAULT_MODEL_VERSION),
    db: Session = Depends(get_db),
) -> ModelPredictionDetailResponse:
    asset_id = validate_asset_id(asset_id)
    if not _asset_exists(db, asset_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"asset_id {asset_id!r} not found",
        )
    row = _fetch_prediction_detail(
        db,
        asset_id=asset_id,
        as_of_date=as_of_date,
        model_name=model_name,
        model_version=model_version,
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"No model_predictions row for asset_id={asset_id!r}, "
                f"as_of_date={as_of_date.isoformat()}, "
                f"model={model_name!r}, version={model_version!r}"
            ),
        )
    return ModelPredictionDetailResponse.model_validate(row)


__all__ = ["router"]
