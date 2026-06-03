"""M68 auth user accounts: auth_users table + workspace_members.user_id"""
from alembic import op
import sqlalchemy as sa

revision = '0025_m68_users'
down_revision = '0024_m67_workspace_members'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create auth_users table (standalone auth, not org-scoped)
    op.create_table(
        'auth_users',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('display_name', sa.String(255), nullable=False),
        sa.Column('hashed_password', sa.String(255), nullable=False),
        sa.Column('status', sa.String(50), nullable=False, server_default='active'),
        sa.Column('is_superuser', sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column('last_login_at', sa.DateTime, nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.Column('updated_at', sa.DateTime, nullable=False),
        sa.PrimaryKeyConstraint('id', name='pk_auth_users'),
        sa.UniqueConstraint('email', name='uq_auth_users_email'),
    )
    op.create_index('ix_auth_users_email', 'auth_users', ['email'])

    # Add user_id to workspace_members (nullable FK to auth_users)
    op.add_column(
        'workspace_members',
        sa.Column('user_id', sa.String(36), nullable=True)
    )
    op.create_index('ix_workspace_members_user_id', 'workspace_members', ['user_id'])


def downgrade() -> None:
    op.drop_index('ix_workspace_members_user_id', table_name='workspace_members')
    op.drop_column('workspace_members', 'user_id')

    op.drop_index('ix_auth_users_email', table_name='auth_users')
    op.drop_table('auth_users')
