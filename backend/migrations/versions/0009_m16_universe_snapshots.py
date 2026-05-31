"""M16: Add universe_snapshots table and universe_snapshot_id FK on strategy_runs.

Revision ID: 0009
Revises: 0008
Create Date: 2026-05-31
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. Create universe_snapshots table
    # ------------------------------------------------------------------
    op.create_table(
        "universe_snapshots",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("strategy_id", sa.String(36), nullable=False),
        sa.Column("strategy_version_id", sa.String(36), nullable=True),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("source_type", sa.String(100), nullable=False, server_default="manual_json"),
        sa.Column("source_filename", sa.String(512), nullable=True),
        # Normalized (sorted, uppercased, deduped) symbol list.
        sa.Column("symbols_json", sa.JSON(), nullable=False),
        sa.Column("symbol_count", sa.Integer(), nullable=False, server_default="0"),
        # Optional metadata: universe_type, liquidity_filter, rebalance, etc.
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        # SHA-256 of (sorted symbols + optional metadata). Deterministic.
        sa.Column("universe_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["strategy_id"],
            ["strategies.id"],
            name="fk_universe_snapshots_strategy_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["strategy_version_id"],
            ["strategy_versions.id"],
            name="fk_universe_snapshots_version_id",
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_universe_snapshots_strategy_id", "universe_snapshots", ["strategy_id"])
    op.create_index("ix_universe_snapshots_version_id", "universe_snapshots", ["strategy_version_id"])
    op.create_index("ix_universe_snapshots_universe_hash", "universe_snapshots", ["universe_hash"])
    op.create_index("ix_universe_snapshots_created_at", "universe_snapshots", ["created_at"])

    # ------------------------------------------------------------------
    # 2. Add universe_snapshot_id column to strategy_runs (SET NULL on delete)
    # ------------------------------------------------------------------
    op.add_column(
        "strategy_runs",
        sa.Column("universe_snapshot_id", sa.String(36), nullable=True),
    )
    op.create_index(
        "ix_strategy_runs_universe_snapshot_id",
        "strategy_runs",
        ["universe_snapshot_id"],
    )
    # SQLite does not support adding FK constraints via ALTER TABLE;
    # the FK is enforced at the ORM level instead. For PostgreSQL this
    # would be added with op.create_foreign_key().


def downgrade() -> None:
    op.drop_index("ix_strategy_runs_universe_snapshot_id", "strategy_runs")
    op.drop_column("strategy_runs", "universe_snapshot_id")

    op.drop_index("ix_universe_snapshots_created_at", "universe_snapshots")
    op.drop_index("ix_universe_snapshots_universe_hash", "universe_snapshots")
    op.drop_index("ix_universe_snapshots_version_id", "universe_snapshots")
    op.drop_index("ix_universe_snapshots_strategy_id", "universe_snapshots")
    op.drop_table("universe_snapshots")
