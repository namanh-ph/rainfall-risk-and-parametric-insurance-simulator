"""Reusable API response shapes shared across routers"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PaginationMeta(BaseModel):
    """Pagination block returned alongside list responses"""

    model_config = ConfigDict(extra="forbid")

    limit: int = Field(..., ge=1)
    offset: int = Field(..., ge=0)
    total: int = Field(..., ge=0)
    returned: int = Field(..., ge=0)

    @model_validator(mode="after")
    def _returned_within_limit(self) -> PaginationMeta:
        if self.returned > self.limit:
            raise ValueError(
                f"returned ({self.returned}) cannot exceed limit ({self.limit})"
            )
        return self


class PaginatedResponse(BaseModel):
    """Generic paginated response wrapper. ``items`` is route-specific"""

    model_config = ConfigDict(extra="forbid")

    items: list[Any]
    pagination: PaginationMeta


class ErrorResponse(BaseModel):
    """Canonical error envelope used by HTTP error responses"""

    model_config = ConfigDict(extra="forbid")

    error: str
    detail: str | None = None


__all__ = ["ErrorResponse", "PaginatedResponse", "PaginationMeta"]
