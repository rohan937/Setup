"""M6 dataset tables: datasets, dataset_snapshots, data_quality_issues.

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-31
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # datasets
    op.create_table(
        "datasets",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("dataset_type", sa.String(50), nullable=False),
        sa.Column("source_type", sa.String(50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_datasets"),
    )
    op.create_index("ix_datasets_project_id", "datasets", ["project_id"])

    # dataset_snapshots
    op.create_table(
        "dataset_snapshots",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("dataset_id", sa.String(36), nullable=False),
        sa.Column("version_label", sa.String(100), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("health_score", sa.Integer(), nullable=False),
        sa.Column("rows_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["dataset_id"], ["datasets.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_dataset_snapshots"),
    )
    op.create_index(
        "ix_dataset_snapshots_dataset_id", "dataset_snapshots", ["dataset_id"]
    )

    # data_quality_issues
    op.create_table(
        "data_quality_issues",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("snapshot_id", sa.String(36), nullable=False),
        sa.Column("issue_type", sa.String(100), nullable=False),
        sa.Column("severity", sa.String(50), nullable=False),
        sa.Column("field_name", sa.String(255), nullable=True),
        sa.Column("row_index", sa.Integer(), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["snapshot_id"], ["dataset_snapshots.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_data_quality_issues"),
    )
    op.create_index(
        "ix_data_quality_issues_snapshot_id",
        "data_quality_issues",
        ["snapshot_id"],
    )
    op.create_index(
        "ix_data_quality_issues_issue_type",
        "data_quality_issues",
        ["issue_type"],
    )
    op.create_index(
        "ix_data_quality_issues_severity",
        "data_quality_issues",
        ["severity"],
    )


def downgrade() -> None:
    op.drop_table("data_quality_issues")
    op.drop_table("dataset_snapshots")
    op.drop_table("datasets")
