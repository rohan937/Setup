"""M39: Add universe coverage analysis JSON columns to universe_snapshots.

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
Create Date: 2026-06-02
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "e4f5a6b7c8d9"
down_revision: str | None = "d3e4f5a6b7c8"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "universe_snapshots",
        sa.Column("coverage_analysis_json", sa.JSON(), nullable=True),
    )
    op.add_column(
        "universe_snapshots",
        sa.Column("symbol_quality_json", sa.JSON(), nullable=True),
    )
    op.add_column(
        "universe_snapshots",
        sa.Column("universe_delta_json", sa.JSON(), nullable=True),
    )
    op.add_column(
        "universe_snapshots",
        sa.Column("universe_quality_summary_json", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("universe_snapshots", "universe_quality_summary_json")
    op.drop_column("universe_snapshots", "universe_delta_json")
    op.drop_column("universe_snapshots", "symbol_quality_json")
    op.drop_column("universe_snapshots", "coverage_analysis_json")
