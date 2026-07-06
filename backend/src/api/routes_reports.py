"""HTML report export endpoint.

`POST /api/v1/reports/export` generates a static HTML portfolio report
from persisted analytics outputs and writes it under
`backend/artifacts/reports/`. The endpoint is intentionally mutating
**only on the filesystem** — it never invokes ingestion, station
matching, LGA assignment, rainfall feature engineering, risk scoring,
payout simulation, threshold sensitivity, ML dataset construction,
model training, or batch prediction.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.api.deps import get_db
from src.reports.export import export_portfolio_report
from src.schemas.api_reports import (
    ReportExportRequest,
    ReportExportResponse,
    ReportSectionStatus,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["reports"])


@router.post("/reports/export", response_model=ReportExportResponse)
def post_reports_export(
    body: ReportExportRequest = Body(...),
    db: Session = Depends(get_db),
) -> ReportExportResponse:
    try:
        result = export_portfolio_report(db, body)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Unexpected failure while exporting portfolio report")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected failure while exporting portfolio report",
        ) from exc

    sections = [
        ReportSectionStatus.model_validate(s) for s in result.get("sections", [])
    ]
    return ReportExportResponse(
        report_id=result["report_id"],
        report_title=result["report_title"],
        as_of_date=result["as_of_date"],
        simulation_id=result["simulation_id"],
        model_name=result["model_name"],
        model_version=result["model_version"],
        feature_version=result["feature_version"],
        output_path=result["output_path"],
        relative_output_path=result["relative_output_path"],
        file_size_bytes=result["file_size_bytes"],
        created_at=result["created_at"],
        sections=sections,
        warnings=list(result.get("warnings") or []),
    )


__all__ = ["router"]
