"""M84 email verification + password reset: email_verified columns + auth_email_tokens"""
from alembic import op
import sqlalchemy as sa

revision = '0026_m84_email_verification'
down_revision = '0025_m68_users'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add email verification columns to auth_users.
    op.add_column(
        'auth_users',
        sa.Column('email_verified', sa.Boolean, nullable=False, server_default=sa.false()),
    )
    op.add_column(
        'auth_users',
        sa.Column('email_verified_at', sa.DateTime, nullable=True),
    )

    # Single-use, hashed email tokens (verification + password reset).
    op.create_table(
        'auth_email_tokens',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('user_id', sa.String(36), nullable=False),
        sa.Column('token_hash', sa.String(64), nullable=False),
        sa.Column('token_type', sa.String(32), nullable=False),
        sa.Column('expires_at', sa.DateTime, nullable=False),
        sa.Column('used_at', sa.DateTime, nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.PrimaryKeyConstraint('id', name='pk_auth_email_tokens'),
        sa.ForeignKeyConstraint(
            ['user_id'], ['auth_users.id'], name='fk_auth_email_tokens_user_id'
        ),
    )
    op.create_index('ix_auth_email_tokens_token_hash', 'auth_email_tokens', ['token_hash'])
    op.create_index('ix_auth_email_tokens_user_id', 'auth_email_tokens', ['user_id'])

    # GRANDFATHER existing users as verified.
    # This prevents existing production users from being locked out of sensitive
    # actions (which will require a verified email) after this migration ships.
    # Only NEW registrations created after this point start unverified.
    op.execute(
        "UPDATE auth_users SET email_verified = true, "
        "email_verified_at = CURRENT_TIMESTAMP WHERE email_verified = false"
    )


def downgrade() -> None:
    op.drop_index('ix_auth_email_tokens_user_id', table_name='auth_email_tokens')
    op.drop_index('ix_auth_email_tokens_token_hash', table_name='auth_email_tokens')
    op.drop_table('auth_email_tokens')
    op.drop_column('auth_users', 'email_verified_at')
    op.drop_column('auth_users', 'email_verified')
