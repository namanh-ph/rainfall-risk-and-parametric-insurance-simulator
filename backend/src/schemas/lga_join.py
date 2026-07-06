"""Pydantic schemas for the asset-to-LGA spatial join"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

AssignmentMethod = Literal["covers", "intersects", "nearest_fallback", "unmatched"]


class AssetLgaAssignmentRecord(BaseModel):
    """One asset → LGA assignment, including ``unmatched`` placeholder rows"""

    model_config = ConfigDict(extra="ignore")

    asset_id: str = Field(..., min_length=1, max_length=64)
    lga_code: str | None = Field(default=None, max_length=16)
    lga_name: str | None = Field(default=None, max_length=128)
    assignment_method: AssignmentMethod
    assignment_distance_km: float | None = None
    assigned_at: datetime

    @model_validator(mode="after")
    def _validate_method_consistency(self) -> AssetLgaAssignmentRecord:
        method = self.assignment_method
        if method in ("covers", "intersects"):
            if self.assignment_distance_km != 0.0:
                raise ValueError(
                    f"{method} assignment must have assignment_distance_km == 0 "
                    f"(got {self.assignment_distance_km!r})"
                )
            if not self.lga_code:
                raise ValueError(f"{method} assignment requires lga_code")
            if not self.lga_name:
                raise ValueError(f"{method} assignment requires lga_name")
        elif method == "nearest_fallback":
            if self.assignment_distance_km is None or self.assignment_distance_km < 0:
                raise ValueError(
                    "nearest_fallback assignment requires a non-negative "
                    "assignment_distance_km"
                )
            if not self.lga_code:
                raise ValueError("nearest_fallback requires lga_code")
            if not self.lga_name:
                raise ValueError("nearest_fallback requires lga_name")
        # unmatched: lga_code/lga_name may be None, distance may be None
        return self


class AssetLgaAssignmentRunSummary(BaseModel):
    """Structured summary returned by ``run_asset_lga_assignment``"""

    model_config = ConfigDict(extra="forbid")

    assets_considered: int = Field(..., ge=0)
    lga_boundaries_available: int = Field(..., ge=0)
    assignments_generated: int = Field(..., ge=0)
    assets_updated: int = Field(..., ge=0)
    unmatched_assets: int = Field(..., ge=0)
    covers_assignments: int = Field(..., ge=0)
    intersects_assignments: int = Field(..., ge=0)
    nearest_fallback_assignments: int = Field(..., ge=0)
    allow_nearest_fallback: bool
    max_fallback_distance_km: float | None = Field(default=None, gt=0)
    replace_existing: bool


__all__ = [
    "AssetLgaAssignmentRecord",
    "AssetLgaAssignmentRunSummary",
    "AssignmentMethod",
]
