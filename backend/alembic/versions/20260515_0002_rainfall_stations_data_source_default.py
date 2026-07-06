"""rename rainfall_stations.data_source default

Revision ID: 20260515_0002
Revises: 20260506_0001
Create Date: 2026-05-15
"""

from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260515_0002"
down_revision: str | None = "20260506_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "rainfall_stations",
        "data_source",
        existing_type=sa.String(length=64),
        existing_nullable=False,
        server_default=sa.text("'bom'"),
    )


def downgrade() -> None:
    op.alter_column(
        "rainfall_stations",
        "data_source",
        existing_type=sa.String(length=64),
        existing_nullable=False,
        server_default=sa.text("'synthetic'"),
    )
