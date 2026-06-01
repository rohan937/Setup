"""M18: Add strategy_reliability_scores table.

Revision ID: 0011
Revises: 0010
Create Date: 2026-06-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "strategy_reliability_scores",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("strategy_id", sa.String(36), nullable=False),
        sa.Column("overall_score", sa.Float(), nullable=True),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("strategy_activity_score", sa.Float(), nullable=True),
        sa.Column("data_evidence_score", sa.Float(), nullable=True),
        sa.Column("backtest_trust_score", sa.Float(), nullable=True),
        sa.Column("config_evidence_score", sa.Float(), nullable=True),
        sa.Column("universe_evidence_score", sa.Float(), nullable=True),
        sa.Column("signal_evidence_score", sa.Float(), nullable=True),
        sa.Column("alert_penalty_score", sa.Float(), nullable=True),
        sa.Column("report_coverage_score", sa.Float(), nullable=True),
        sa.Column("evidence_counts_json", sa.JSON(), nullable=True),
        sa.Column("component_summaries_json", sa.JSON(), nullable=True),
        sa.Column("missing_evidence_json", sa.JSON(), nullable=True),
        sa.Column("suggested_checks_json", sa.JSON(), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["strategy_id"],
            ["strategies.id"],
            name="fk_strategy_reliability_scores_strategy_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_strategy_reliability_scores_strategy_id",
        "strategy_reliability_scores",
        ["strategy_id"],
    )
    op.create_index(
        "ix_strategy_reliability_scores_status",
        "strategy_reliability_scores",
        ["status"],
    )
    op.create_index(
        "ix_strategy_reliability_scores_generated_at",
        "strategy_reliability_scores",
        ["generated_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_strategy_reliability_scores_generated_at", "strategy_reliability_scores")
    op.drop_index("ix_strategy_reliability_scores_status", "strategy_reliability_scores")
    op.drop_index("ix_strategy_reliability_scores_strategy_id", "strategy_reliability_scores")
    op.drop_table("strategy_reliability_scores")
