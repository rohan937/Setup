"""M53: Add strategy regression tests tables.

Revision ID: f5a6b7c8d9e0
Revises: e4f5a6b7c8d9
Create Date: 2026-06-02
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "f5a6b7c8d9e0"
down_revision: str | None = "e4f5a6b7c8d9"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "strategy_regression_tests",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "strategy_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("strategies.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("test_key", sa.String(100), nullable=False, index=True),
        sa.Column("test_type", sa.String(50), nullable=False),
        sa.Column("metric_key", sa.String(100), nullable=True),
        sa.Column("operator", sa.String(50), nullable=False),
        sa.Column("threshold_value", sa.Float(), nullable=True),
        sa.Column("threshold_json", sa.JSON(), nullable=True),
        sa.Column("severity", sa.String(50), nullable=False, server_default="medium"),
        sa.Column("is_required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "strategy_regression_test_runs",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "strategy_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("strategies.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("suite_label", sa.String(255), nullable=True),
        sa.Column("mode", sa.String(50), nullable=False),
        sa.Column(
            "baseline_run_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("strategy_runs.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "comparison_run_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("strategy_runs.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "overall_status",
            sa.String(50),
            nullable=False,
            server_default="insufficient_evidence",
        ),
        sa.Column("passed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("warning_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("required_failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("result_json", sa.JSON(), nullable=True),
        sa.Column("deterministic_summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "strategy_regression_test_results",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "test_run_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("strategy_regression_test_runs.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "regression_test_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("strategy_regression_tests.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column("test_key", sa.String(100), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("severity", sa.String(50), nullable=False, server_default="medium"),
        sa.Column("is_required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("observed_value", sa.String(255), nullable=True),
        sa.Column("expected_value", sa.String(255), nullable=True),
        sa.Column("baseline_value", sa.String(255), nullable=True),
        sa.Column("comparison_value", sa.String(255), nullable=True),
        sa.Column("evidence_json", sa.JSON(), nullable=True),
        sa.Column("suggested_action", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("strategy_regression_test_results")
    op.drop_table("strategy_regression_test_runs")
    op.drop_table("strategy_regression_tests")
