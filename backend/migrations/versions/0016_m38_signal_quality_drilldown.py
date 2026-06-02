"""M38: Add signal quality drilldown JSON columns to signal_snapshots.

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-06-02
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "d3e4f5a6b7c8"
down_revision: str | None = "c2d3e4f5a6b7"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "signal_snapshots",
        sa.Column("signal_distribution_json", sa.JSON(), nullable=True),
    )
    op.add_column(
        "signal_snapshots",
        sa.Column("symbol_quality_json", sa.JSON(), nullable=True),
    )
    op.add_column(
        "signal_snapshots",
        sa.Column("signal_row_quality_json", sa.JSON(), nullable=True),
    )
    op.add_column(
        "signal_snapshots",
        sa.Column("signal_quality_summary_json", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("signal_snapshots", "signal_quality_summary_json")
    op.drop_column("signal_snapshots", "signal_row_quality_json")
    op.drop_column("signal_snapshots", "symbol_quality_json")
    op.drop_column("signal_snapshots", "signal_distribution_json")
