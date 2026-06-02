"""M54 config policies"""
from alembic import op
import sqlalchemy as sa

revision = '0019_m54_config_policies'
down_revision = 'f5a6b7c8d9e0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'strategy_config_policies',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('strategy_id', sa.String(36), sa.ForeignKey('strategies.id'), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('is_active', sa.Boolean, nullable=False, default=True),
        sa.Column('policy_json', sa.JSON, nullable=False),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.Column('updated_at', sa.DateTime, nullable=False),
    )
    op.create_index('ix_strategy_config_policies_strategy_id', 'strategy_config_policies', ['strategy_id'])

    op.create_table(
        'strategy_config_policy_evaluations',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('strategy_id', sa.String(36), sa.ForeignKey('strategies.id'), nullable=False),
        sa.Column('policy_id', sa.String(36), sa.ForeignKey('strategy_config_policies.id'), nullable=False),
        sa.Column('config_snapshot_id', sa.String(36), sa.ForeignKey('strategy_config_snapshots.id'), nullable=True),
        sa.Column('overall_status', sa.String(50), nullable=False),
        sa.Column('passed_count', sa.Integer, nullable=False, default=0),
        sa.Column('warning_count', sa.Integer, nullable=False, default=0),
        sa.Column('failed_count', sa.Integer, nullable=False, default=0),
        sa.Column('skipped_count', sa.Integer, nullable=False, default=0),
        sa.Column('critical_failed_count', sa.Integer, nullable=False, default=0),
        sa.Column('result_json', sa.JSON, nullable=True),
        sa.Column('deterministic_summary', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False),
    )
    op.create_index('ix_strategy_config_policy_evaluations_strategy_id', 'strategy_config_policy_evaluations', ['strategy_id'])
    op.create_index('ix_strategy_config_policy_evaluations_policy_id', 'strategy_config_policy_evaluations', ['policy_id'])
    op.create_index('ix_strategy_config_policy_evaluations_config_snapshot_id', 'strategy_config_policy_evaluations', ['config_snapshot_id'])

    op.create_table(
        'strategy_config_policy_results',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('evaluation_id', sa.String(36), sa.ForeignKey('strategy_config_policy_evaluations.id'), nullable=False),
        sa.Column('rule_key', sa.String(255), nullable=False),
        sa.Column('title', sa.String(500), nullable=False),
        sa.Column('status', sa.String(50), nullable=False),
        sa.Column('severity', sa.String(50), nullable=False),
        sa.Column('is_required', sa.Boolean, nullable=False, default=True),
        sa.Column('observed_value', sa.Text, nullable=True),
        sa.Column('expected_value', sa.Text, nullable=True),
        sa.Column('key_path', sa.String(500), nullable=True),
        sa.Column('evidence_json', sa.JSON, nullable=True),
        sa.Column('suggested_action', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False),
    )
    op.create_index('ix_strategy_config_policy_results_evaluation_id', 'strategy_config_policy_results', ['evaluation_id'])


def downgrade() -> None:
    op.drop_table('strategy_config_policy_results')
    op.drop_table('strategy_config_policy_evaluations')
    op.drop_table('strategy_config_policies')
