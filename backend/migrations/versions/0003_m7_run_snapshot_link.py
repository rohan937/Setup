"""M7: add dataset_snapshot_id FK to strategy_runs.

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-31
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # Use batch mode for SQLite ALTER TABLE compatibility.
    with op.batch_alter_table("strategy_runs", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("dataset_snapshot_id", sa.String(36), nullable=True)
        )
        batch_op.create_index(
            "ix_strategy_runs_dataset_snapshot_id",
            ["dataset_snapshot_id"],
        )
        batch_op.create_foreign_key(
            "fk_strategy_runs_dataset_snapshot_id",
            "dataset_snapshots",
            ["dataset_snapshot_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("strategy_runs", schema=None) as batch_op:
        batch_op.drop_constraint(
            "fk_strategy_runs_dataset_snapshot_id", type_="foreignkey"
        )
        batch_op.drop_index("ix_strategy_runs_dataset_snapshot_id")
        batch_op.drop_column("dataset_snapshot_id")
