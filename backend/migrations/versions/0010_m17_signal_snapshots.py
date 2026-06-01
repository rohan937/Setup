"""M17: Add signal_snapshots table and signal_snapshot_id FK on strategy_runs.

Revision ID: 0010
Revises: 0009
Create Date: 2026-06-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. Create signal_snapshots table
    # ------------------------------------------------------------------
    op.create_table(
        "signal_snapshots",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("strategy_id", sa.String(36), nullable=False),
        sa.Column("strategy_version_id", sa.String(36), nullable=True),
        sa.Column("universe_snapshot_id", sa.String(36), nullable=True),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("signal_name", sa.String(255), nullable=True),
        sa.Column("source_type", sa.String(100), nullable=False, server_default="manual_json"),
        sa.Column("source_filename", sa.String(512), nullable=True),
        # Signal rows stored verbatim as a JSON array of objects.
        sa.Column("rows_json", sa.JSON(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("symbol_count", sa.Integer(), nullable=False, server_default="0"),
        # Sorted distinct symbol strings.
        sa.Column("symbols_json", sa.JSON(), nullable=False),
        sa.Column("min_timestamp", sa.String(100), nullable=True),
        sa.Column("max_timestamp", sa.String(100), nullable=True),
        # Signal statistics.
        sa.Column("signal_value_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("missing_signal_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("mean_value", sa.Float(), nullable=True),
        sa.Column("min_value", sa.Float(), nullable=True),
        sa.Column("max_value", sa.Float(), nullable=True),
        sa.Column("stddev_value", sa.Float(), nullable=True),
        # Deterministic SHA-256 hex of (sorted rows + optional metadata). 64 chars.
        sa.Column("signal_hash", sa.String(64), nullable=False),
        sa.Column("quality_score", sa.Integer(), nullable=False, server_default="100"),
        # Optional metadata dict; stored verbatim.
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["strategy_id"],
            ["strategies.id"],
            name="fk_signal_snapshots_strategy_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["strategy_version_id"],
            ["strategy_versions.id"],
            name="fk_signal_snapshots_version_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["universe_snapshot_id"],
            ["universe_snapshots.id"],
            name="fk_signal_snapshots_universe_snapshot_id",
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_signal_snapshots_strategy_id", "signal_snapshots", ["strategy_id"])
    op.create_index("ix_signal_snapshots_version_id", "signal_snapshots", ["strategy_version_id"])
    op.create_index("ix_signal_snapshots_universe_snapshot_id", "signal_snapshots", ["universe_snapshot_id"])
    op.create_index("ix_signal_snapshots_signal_hash", "signal_snapshots", ["signal_hash"])
    op.create_index("ix_signal_snapshots_created_at", "signal_snapshots", ["created_at"])

    # ------------------------------------------------------------------
    # 2. Add signal_snapshot_id column to strategy_runs (SET NULL on delete)
    # ------------------------------------------------------------------
    op.add_column(
        "strategy_runs",
        sa.Column("signal_snapshot_id", sa.String(36), nullable=True),
    )
    op.create_index(
        "ix_strategy_runs_signal_snapshot_id",
        "strategy_runs",
        ["signal_snapshot_id"],
    )
    # SQLite does not support adding FK constraints via ALTER TABLE;
    # the FK is enforced at the ORM level instead. For PostgreSQL this
    # would be added with op.create_foreign_key().


def downgrade() -> None:
    op.drop_index("ix_strategy_runs_signal_snapshot_id", "strategy_runs")
    op.drop_column("strategy_runs", "signal_snapshot_id")

    op.drop_index("ix_signal_snapshots_created_at", "signal_snapshots")
    op.drop_index("ix_signal_snapshots_signal_hash", "signal_snapshots")
    op.drop_index("ix_signal_snapshots_universe_snapshot_id", "signal_snapshots")
    op.drop_index("ix_signal_snapshots_version_id", "signal_snapshots")
    op.drop_index("ix_signal_snapshots_strategy_id", "signal_snapshots")
    op.drop_table("signal_snapshots")
