"""M13: Add cost_sensitivity_json, fill_realism_json, fragility_summary_json
to backtest_audits.

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-31
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "backtest_audits",
        sa.Column("cost_sensitivity_json", sa.JSON(), nullable=True),
    )
    op.add_column(
        "backtest_audits",
        sa.Column("fill_realism_json", sa.JSON(), nullable=True),
    )
    op.add_column(
        "backtest_audits",
        sa.Column("fragility_summary_json", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("backtest_audits", "fragility_summary_json")
    op.drop_column("backtest_audits", "fill_realism_json")
    op.drop_column("backtest_audits", "cost_sensitivity_json")
