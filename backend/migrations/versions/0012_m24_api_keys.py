"""M24: Add api_keys table for API Key Foundation + SDK Auth.

Revision ID: a1b2c3d4e5f6
Revises: 0011
Create Date: 2026-06-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "0011"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "api_keys",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("project_id", sa.String(36), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("key_prefix", sa.String(50), nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=False),
        sa.Column("scopes_json", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="active"),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_api_keys_organization_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_api_keys_project_id",
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_api_keys_key_hash", "api_keys", ["key_hash"])
    op.create_index("ix_api_keys_organization_id", "api_keys", ["organization_id"])
    op.create_index("ix_api_keys_project_id", "api_keys", ["project_id"])
    op.create_index("ix_api_keys_status", "api_keys", ["status"])
    op.create_index("ix_api_keys_key_prefix", "api_keys", ["key_prefix"])


def downgrade() -> None:
    op.drop_index("ix_api_keys_key_prefix", "api_keys")
    op.drop_index("ix_api_keys_status", "api_keys")
    op.drop_index("ix_api_keys_project_id", "api_keys")
    op.drop_index("ix_api_keys_organization_id", "api_keys")
    op.drop_index("ix_api_keys_key_hash", "api_keys")
    op.drop_table("api_keys")
