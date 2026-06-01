"""M25: Add sdk_ingestion_batches table for idempotency support.

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-06-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "sdk_ingestion_batches",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=True),
        sa.Column("project_id", sa.String(36), nullable=True),
        sa.Column("strategy_id", sa.String(36), nullable=False),
        sa.Column("api_key_id", sa.String(36), nullable=True),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="received"),
        sa.Column("response_json", sa.JSON(), nullable=True),
        sa.Column("error_json", sa.JSON(), nullable=True),
        sa.Column("created_object_refs_json", sa.JSON(), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["strategy_id"],
            ["strategies.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["api_key_id"],
            ["api_keys.id"],
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint("strategy_id", "idempotency_key"),
    )
    op.create_index(
        "ix_sdk_ingestion_batches_strategy_id",
        "sdk_ingestion_batches",
        ["strategy_id"],
    )
    op.create_index(
        "ix_sdk_ingestion_batches_api_key_id",
        "sdk_ingestion_batches",
        ["api_key_id"],
    )
    op.create_index(
        "ix_sdk_ingestion_batches_idempotency_key",
        "sdk_ingestion_batches",
        ["idempotency_key"],
    )
    op.create_index(
        "ix_sdk_ingestion_batches_status",
        "sdk_ingestion_batches",
        ["status"],
    )
    op.create_index(
        "ix_sdk_ingestion_batches_received_at",
        "sdk_ingestion_batches",
        ["received_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_sdk_ingestion_batches_received_at", "sdk_ingestion_batches")
    op.drop_index("ix_sdk_ingestion_batches_status", "sdk_ingestion_batches")
    op.drop_index("ix_sdk_ingestion_batches_idempotency_key", "sdk_ingestion_batches")
    op.drop_index("ix_sdk_ingestion_batches_api_key_id", "sdk_ingestion_batches")
    op.drop_index("ix_sdk_ingestion_batches_strategy_id", "sdk_ingestion_batches")
    op.drop_table("sdk_ingestion_batches")
