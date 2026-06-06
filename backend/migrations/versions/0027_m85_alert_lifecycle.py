"""M85 alert lifecycle: alert recommended_fix/owner, rule severity/strategy scope, alert_history"""
from alembic import op
import sqlalchemy as sa

revision = '0027_m85_alert_lifecycle'
down_revision = '0026_m84_email_verification'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # alerts: remediation text + assigned owner.
    op.add_column('alerts', sa.Column('recommended_fix', sa.Text, nullable=True))
    op.add_column('alerts', sa.Column('owner_user_id', sa.String(36), nullable=True))
    op.create_index('ix_alerts_owner_user_id', 'alerts', ['owner_user_id'])

    # alert_rules: default severity + optional strategy scope.
    op.add_column('alert_rules', sa.Column('severity', sa.String(50), nullable=True))
    op.add_column('alert_rules', sa.Column('strategy_id', sa.String(36), nullable=True))
    op.create_index('ix_alert_rules_strategy_id', 'alert_rules', ['strategy_id'])

    # alert_history: immutable lifecycle audit log.
    op.create_table(
        'alert_history',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('alert_id', sa.String(36), nullable=False),
        sa.Column('actor_user_id', sa.String(36), nullable=True),
        sa.Column('action', sa.String(50), nullable=False),
        sa.Column('note', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.PrimaryKeyConstraint('id', name='pk_alert_history'),
        sa.ForeignKeyConstraint(
            ['alert_id'], ['alerts.id'],
            name='fk_alert_history_alert_id',
            ondelete='CASCADE',
        ),
    )
    op.create_index('ix_alert_history_alert_id', 'alert_history', ['alert_id'])


def downgrade() -> None:
    op.drop_index('ix_alert_history_alert_id', table_name='alert_history')
    op.drop_table('alert_history')

    op.drop_index('ix_alert_rules_strategy_id', table_name='alert_rules')
    op.drop_column('alert_rules', 'strategy_id')
    op.drop_column('alert_rules', 'severity')

    op.drop_index('ix_alerts_owner_user_id', table_name='alerts')
    op.drop_column('alerts', 'owner_user_id')
    op.drop_column('alerts', 'recommended_fix')
