"""M8: add backtest_audits and backtest_issues tables.

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-31
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "backtest_audits",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("strategy_run_id", sa.String(36), nullable=False),
        sa.Column("trust_score", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("lookahead_risk_score", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("cost_realism_score", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("fill_realism_score", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("liquidity_realism_score", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("borrow_realism_score", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("data_quality_score", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("overall_status", sa.String(50), nullable=False, server_default="excellent"),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["strategy_run_id"],
            ["strategy_runs.id"],
            name="fk_backtest_audits_strategy_run_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_backtest_audits_strategy_run_id",
        "backtest_audits",
        ["strategy_run_id"],
    )
    op.create_index(
        "ix_backtest_audits_created_at",
        "backtest_audits",
        ["created_at"],
    )

    op.create_table(
        "backtest_issues",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("backtest_audit_id", sa.String(36), nullable=False),
        sa.Column("issue_type", sa.String(100), nullable=False),
        sa.Column("severity", sa.String(50), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("evidence_json", sa.JSON(), nullable=True),
        sa.Column("suggested_check", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["backtest_audit_id"],
            ["backtest_audits.id"],
            name="fk_backtest_issues_backtest_audit_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_backtest_issues_backtest_audit_id",
        "backtest_issues",
        ["backtest_audit_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_backtest_issues_backtest_audit_id", table_name="backtest_issues")
    op.drop_table("backtest_issues")
    op.drop_index("ix_backtest_audits_created_at", table_name="backtest_audits")
    op.drop_index("ix_backtest_audits_strategy_run_id", table_name="backtest_audits")
    op.drop_table("backtest_audits")
