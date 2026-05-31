"""M11: add alert_rules and alerts tables.

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-31
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "alert_rules",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("rule_type", sa.String(100), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("threshold", sa.Integer(), nullable=True),
        sa.Column("config_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_alert_rules_organization_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_alert_rules_organization_id",
        "alert_rules",
        ["organization_id"],
    )
    op.create_index(
        "ix_alert_rules_rule_type",
        "alert_rules",
        ["rule_type"],
    )

    op.create_table(
        "alerts",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("rule_type", sa.String(100), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="open"),
        sa.Column("severity", sa.String(50), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("source_type", sa.String(100), nullable=True),
        sa.Column("source_id", sa.String(36), nullable=True),
        sa.Column("strategy_id", sa.String(36), nullable=True),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("snoozed_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_alerts_organization_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["strategy_id"],
            ["strategies.id"],
            name="fk_alerts_strategy_id",
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_alerts_organization_id", "alerts", ["organization_id"])
    op.create_index("ix_alerts_status", "alerts", ["status"])
    op.create_index("ix_alerts_severity", "alerts", ["severity"])
    op.create_index("ix_alerts_source_type", "alerts", ["source_type"])
    op.create_index("ix_alerts_strategy_id", "alerts", ["strategy_id"])
    op.create_index("ix_alerts_triggered_at", "alerts", ["triggered_at"])


def downgrade() -> None:
    op.drop_index("ix_alerts_triggered_at", table_name="alerts")
    op.drop_index("ix_alerts_strategy_id", table_name="alerts")
    op.drop_index("ix_alerts_source_type", table_name="alerts")
    op.drop_index("ix_alerts_severity", table_name="alerts")
    op.drop_index("ix_alerts_status", table_name="alerts")
    op.drop_index("ix_alerts_organization_id", table_name="alerts")
    op.drop_table("alerts")
    op.drop_index("ix_alert_rules_rule_type", table_name="alert_rules")
    op.drop_index("ix_alert_rules_organization_id", table_name="alert_rules")
    op.drop_table("alert_rules")
