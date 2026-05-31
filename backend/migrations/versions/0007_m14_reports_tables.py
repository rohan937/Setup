"""M14: Add reports and report_sections tables.

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-31
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "reports",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("project_id", sa.String(36), nullable=True),
        sa.Column("strategy_id", sa.String(36), nullable=True),
        sa.Column("report_type", sa.String(100), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="generated"),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_type", sa.String(100), nullable=True),
        sa.Column("source_id", sa.String(36), nullable=True),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("report_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_reports_organization_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_reports_project_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["strategy_id"],
            ["strategies.id"],
            name="fk_reports_strategy_id",
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_reports_organization_id", "reports", ["organization_id"])
    op.create_index("ix_reports_project_id", "reports", ["project_id"])
    op.create_index("ix_reports_strategy_id", "reports", ["strategy_id"])
    op.create_index("ix_reports_report_type", "reports", ["report_type"])
    op.create_index("ix_reports_source_type", "reports", ["source_type"])
    op.create_index("ix_reports_generated_at", "reports", ["generated_at"])

    op.create_table(
        "report_sections",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("report_id", sa.String(36), nullable=False),
        sa.Column("section_key", sa.String(100), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("severity", sa.String(50), nullable=True),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("evidence_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["report_id"],
            ["reports.id"],
            name="fk_report_sections_report_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_report_sections_report_id", "report_sections", ["report_id"])
    op.create_index(
        "ix_report_sections_section_key", "report_sections", ["section_key"]
    )


def downgrade() -> None:
    op.drop_index("ix_report_sections_section_key", table_name="report_sections")
    op.drop_index("ix_report_sections_report_id", table_name="report_sections")
    op.drop_table("report_sections")
    op.drop_index("ix_reports_generated_at", table_name="reports")
    op.drop_index("ix_reports_source_type", table_name="reports")
    op.drop_index("ix_reports_report_type", table_name="reports")
    op.drop_index("ix_reports_strategy_id", table_name="reports")
    op.drop_index("ix_reports_project_id", table_name="reports")
    op.drop_index("ix_reports_organization_id", table_name="reports")
    op.drop_table("reports")
