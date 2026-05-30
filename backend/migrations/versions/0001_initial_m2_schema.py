"""Initial M2 schema: organizations, users, projects, strategies,
strategy_versions, strategy_runs, audit_timeline_events.

Revision ID: 0001
Revises:
Create Date: 2026-05-30
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # organizations
    op.create_table(
        "organizations",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_organizations"),
        sa.UniqueConstraint("slug", name="uq_organizations_slug"),
    )
    op.create_index("ix_organizations_slug", "organizations", ["slug"])

    # users
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("role", sa.String(50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("organization_id", "email", name="uq_users_org_email"),
    )
    op.create_index("ix_users_organization_id", "users", ["organization_id"])

    # projects
    op.create_table(
        "projects",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_projects"),
        sa.UniqueConstraint("organization_id", "slug", name="uq_projects_org_slug"),
    )
    op.create_index("ix_projects_organization_id", "projects", ["organization_id"])

    # strategies
    op.create_table(
        "strategies",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("asset_class", sa.String(50), nullable=False),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_strategies"),
    )
    op.create_index("ix_strategies_project_id", "strategies", ["project_id"])
    op.create_index("ix_strategies_slug", "strategies", ["slug"])

    # strategy_versions
    op.create_table(
        "strategy_versions",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("strategy_id", sa.String(36), nullable=False),
        sa.Column("version_label", sa.String(100), nullable=False),
        sa.Column("git_commit", sa.String(255), nullable=True),
        sa.Column("branch_name", sa.String(255), nullable=True),
        sa.Column("code_path", sa.String(512), nullable=True),
        sa.Column("signal_name", sa.String(255), nullable=True),
        sa.Column("signal_description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["strategy_id"], ["strategies.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_strategy_versions"),
    )
    op.create_index(
        "ix_strategy_versions_strategy_id", "strategy_versions", ["strategy_id"]
    )

    # strategy_runs
    op.create_table(
        "strategy_runs",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("strategy_id", sa.String(36), nullable=False),
        sa.Column("strategy_version_id", sa.String(36), nullable=True),
        sa.Column("run_name", sa.String(255), nullable=False),
        sa.Column("run_type", sa.String(50), nullable=False),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("params_json", sa.JSON(), nullable=True),
        sa.Column("assumptions_json", sa.JSON(), nullable=True),
        sa.Column("metrics_json", sa.JSON(), nullable=True),
        sa.Column("universe_name", sa.String(255), nullable=True),
        sa.Column("dataset_version", sa.String(255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["strategy_id"], ["strategies.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["strategy_version_id"], ["strategy_versions.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_strategy_runs"),
    )
    op.create_index(
        "ix_strategy_runs_strategy_id", "strategy_runs", ["strategy_id"]
    )
    op.create_index(
        "ix_strategy_runs_strategy_version_id",
        "strategy_runs",
        ["strategy_version_id"],
    )

    # audit_timeline_events
    op.create_table(
        "audit_timeline_events",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("project_id", sa.String(36), nullable=True),
        sa.Column("strategy_id", sa.String(36), nullable=True),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("source_type", sa.String(100), nullable=True),
        sa.Column("source_id", sa.String(255), nullable=True),
        sa.Column("severity", sa.String(50), nullable=False),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["strategy_id"], ["strategies.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_audit_timeline_events"),
    )
    op.create_index(
        "ix_audit_timeline_events_organization_id",
        "audit_timeline_events",
        ["organization_id"],
    )
    op.create_index(
        "ix_audit_timeline_events_project_id",
        "audit_timeline_events",
        ["project_id"],
    )
    op.create_index(
        "ix_audit_timeline_events_strategy_id",
        "audit_timeline_events",
        ["strategy_id"],
    )
    op.create_index(
        "ix_audit_timeline_events_event_type",
        "audit_timeline_events",
        ["event_type"],
    )
    op.create_index(
        "ix_audit_timeline_events_event_time",
        "audit_timeline_events",
        ["event_time"],
    )


def downgrade() -> None:
    op.drop_table("audit_timeline_events")
    op.drop_table("strategy_runs")
    op.drop_table("strategy_versions")
    op.drop_table("strategies")
    op.drop_table("projects")
    op.drop_table("users")
    op.drop_table("organizations")
