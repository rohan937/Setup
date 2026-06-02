"""M37: Add column_quality_json, row_quality_json, quality_summary_json to dataset_snapshots.

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-06-02
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "c2d3e4f5a6b7"
down_revision: str | None = "b1c2d3e4f5a6"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "dataset_snapshots",
        sa.Column("column_quality_json", sa.JSON(), nullable=True),
    )
    op.add_column(
        "dataset_snapshots",
        sa.Column("row_quality_json", sa.JSON(), nullable=True),
    )
    op.add_column(
        "dataset_snapshots",
        sa.Column("quality_summary_json", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("dataset_snapshots", "quality_summary_json")
    op.drop_column("dataset_snapshots", "row_quality_json")
    op.drop_column("dataset_snapshots", "column_quality_json")
