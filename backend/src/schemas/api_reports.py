"""Pydantic schemas for the HTML report export endpoint."""

from __future__ import annotations

import re
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.domain.constants import DEFAULT_PAYOUT_SIMULATION_ID

DEFAULT_MODEL_NAME = "rainfall_risk_lgbm"
DEFAULT_MODEL_VERSION = "v1"
DEFAULT_FEATURE_VERSION = "rainfall_risk_features_v1"
DEFAULT_REPORT_TITLE = "Portfolio Risk Report"

# Allow letters, digits, dot, dash, underscore — no path separators, no '..'
_SAFE_FILENAME = re.compile(r"^[A-Za-z0-9._-]+\.html$")


class ReportExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    as_of_date: date = date(2025, 12, 31)
    simulation_id: str = Field(
        default=DEFAULT_PAYOUT_SIMULATION_ID, min_length=1, max_length=64
    )
    model_name: str = Field(default=DEFAULT_MODEL_NAME, min_length=1, max_length=128)
    model_version: str = Field(default=DEFAULT_MODEL_VERSION, min_length=1, max_length=64)
    feature_version: str = Field(
        default=DEFAULT_FEATURE_VERSION, min_length=1, max_length=64
    )
    report_title: str = Field(default=DEFAULT_REPORT_TITLE, min_length=1, max_length=200)
    output_filename: str | None = None
    include_methodology: bool = True
    include_top_assets: bool = True
    top_n: int = Field(default=20, ge=1, le=100)

    @field_validator("output_filename")
    @classmethod
    def _safe_filename(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            return None
        if ".." in stripped or "/" in stripped or "\\" in stripped:
            raise ValueError("output_filename must not contain path separators or '..'")
        if not _SAFE_FILENAME.match(stripped):
            raise ValueError(
                "output_filename must match [A-Za-z0-9._-]+.html (no path traversal)"
            )
        return stripped


class ReportSectionStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    section: str = Field(..., min_length=1)
    available: bool
    row_count: int = Field(..., ge=0)
    message: str | None = None


class ReportExportResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_id: str = Field(..., min_length=1)
    report_title: str = Field(..., min_length=1)
    as_of_date: date
    simulation_id: str
    model_name: str
    model_version: str
    feature_version: str
    output_path: str = Field(..., min_length=1)
    relative_output_path: str
    file_size_bytes: int = Field(..., ge=0)
    created_at: datetime
    sections: list[ReportSectionStatus] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


__all__ = [
    "DEFAULT_FEATURE_VERSION",
    "DEFAULT_MODEL_NAME",
    "DEFAULT_MODEL_VERSION",
    "DEFAULT_REPORT_TITLE",
    "ReportExportRequest",
    "ReportExportResponse",
    "ReportSectionStatus",
]
