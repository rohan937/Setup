"""M67 workspace settings + members foundation"""
from alembic import op
import sqlalchemy as sa

revision = '0024_m67_workspace_members'
down_revision = '0023_m65a_reliability_snapshots'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add display_name, description, website to organizations (they don't exist yet)
    op.add_column('organizations', sa.Column('display_name', sa.String(255), nullable=True))
    op.add_column('organizations', sa.Column('description', sa.Text, nullable=True))
    op.add_column('organizations', sa.Column('website', sa.String(500), nullable=True))

    # Create workspace_members table
    op.create_table(
        'workspace_members',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('organization_id', sa.String(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('display_name', sa.String(255), nullable=False),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('role', sa.String(50), nullable=False, server_default='member'),
        sa.Column('status', sa.String(50), nullable=False, server_default='active'),
        sa.Column('title', sa.Text, nullable=True),
        sa.Column('notes', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.Column('updated_at', sa.DateTime, nullable=False),
    )
    op.create_index('ix_workspace_members_organization_id', 'workspace_members', ['organization_id'])
    op.create_index('ix_workspace_members_email', 'workspace_members', ['email'])


def downgrade() -> None:
    op.drop_index('ix_workspace_members_email', table_name='workspace_members')
    op.drop_index('ix_workspace_members_organization_id', table_name='workspace_members')
    op.drop_table('workspace_members')

    op.drop_column('organizations', 'website')
    op.drop_column('organizations', 'description')
    op.drop_column('organizations', 'display_name')
