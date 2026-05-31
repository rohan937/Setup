"""M15: Add strategy_config_snapshots table.

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-31
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "strategy_config_snapshots",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("strategy_id", sa.String(36), nullable=False),
        sa.Column("strategy_version_id", sa.String(36), nullable=True),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("source_type", sa.String(100), nullable=False, server_default="manual_json"),
        sa.Column("source_filename", sa.String(512), nullable=True),
        sa.Column("config_json", sa.JSON(), nullable=False),
        sa.Column("config_hash", sa.String(64), nullable=False),
        sa.Column("param_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("assumption_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["strategy_id"],
            ["strategies.id"],
            name="fk_config_snapshots_strategy_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["strategy_version_id"],
            ["strategy_versions.id"],
            name="fk_config_snapshots_version_id",
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_config_snapshots_strategy_id", "strategy_config_snapshots", ["strategy_id"])
    op.create_index("ix_config_snapshots_version_id", "strategy_config_snapshots", ["strategy_version_id"])
    op.create_index("ix_config_snapshots_config_hash", "strategy_config_snapshots", ["config_hash"])
    op.create_index("ix_config_snapshots_created_at", "strategy_config_snapshots", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_config_snapshots_created_at", "strategy_config_snapshots")
    op.drop_index("ix_config_snapshots_config_hash", "strategy_config_snapshots")
    op.drop_index("ix_config_snapshots_version_id", "strategy_config_snapshots")
    op.drop_index("ix_config_snapshots_strategy_id", "strategy_config_snapshots")
    op.drop_table("strategy_config_snapshots")
