"""M36: Add v3 analysis columns to backtest_audits table.

Revision ID: b1c2d3e4f5a6
Revises: b2c3d4e5f6a7
Create Date: 2026-06-02
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "b1c2d3e4f5a6"
down_revision: str | None = "b2c3d4e5f6a7"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "backtest_audits",
        sa.Column("cost_sensitivity_sweep_json", sa.JSON(), nullable=True),
    )
    op.add_column(
        "backtest_audits",
        sa.Column("fill_sensitivity_json", sa.JSON(), nullable=True),
    )
    op.add_column(
        "backtest_audits",
        sa.Column("penalty_attribution_json", sa.JSON(), nullable=True),
    )
    op.add_column(
        "backtest_audits",
        sa.Column("improvement_checks_json", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("backtest_audits", "improvement_checks_json")
    op.drop_column("backtest_audits", "penalty_attribution_json")
    op.drop_column("backtest_audits", "fill_sensitivity_json")
    op.drop_column("backtest_audits", "cost_sensitivity_sweep_json")
