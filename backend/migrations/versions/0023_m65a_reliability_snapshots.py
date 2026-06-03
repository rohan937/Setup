"""M65A strategy reliability snapshot cache"""
from alembic import op
import sqlalchemy as sa

revision = '0023_m65a_reliability_snapshots'
down_revision = '0022_m59_experiment_registry'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'strategy_reliability_snapshots',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('strategy_id', sa.String(36), sa.ForeignKey('strategies.id'), nullable=False, index=True),
        sa.Column('snapshot_status', sa.String(50), nullable=False, server_default='fresh'),
        sa.Column('command_status', sa.String(100), nullable=True),
        sa.Column('command_score', sa.Float, nullable=True),
        sa.Column('readiness_verdict', sa.String(100), nullable=True),
        sa.Column('readiness_score', sa.Float, nullable=True),
        sa.Column('robustness_verdict', sa.String(100), nullable=True),
        sa.Column('robustness_score', sa.Float, nullable=True),
        sa.Column('freeze_recommendation', sa.String(100), nullable=True),
        sa.Column('freeze_risk_score', sa.Float, nullable=True),
        sa.Column('freshness_status', sa.String(100), nullable=True),
        sa.Column('freshness_score', sa.Float, nullable=True),
        sa.Column('drift_status', sa.String(100), nullable=True),
        sa.Column('drift_score', sa.Float, nullable=True),
        sa.Column('shadow_status', sa.String(100), nullable=True),
        sa.Column('shadow_score', sa.Float, nullable=True),
        sa.Column('open_review_case_count', sa.Integer, nullable=False, server_default='0'),
        sa.Column('high_critical_alert_count', sa.Integer, nullable=False, server_default='0'),
        sa.Column('latest_regression_status', sa.String(100), nullable=True),
        sa.Column('latest_config_policy_status', sa.String(100), nullable=True),
        sa.Column('latest_sla_status', sa.String(100), nullable=True),
        sa.Column('top_blockers_json', sa.JSON, nullable=True),
        sa.Column('action_queue_json', sa.JSON, nullable=True),
        sa.Column('subsystem_statuses_json', sa.JSON, nullable=True),
        sa.Column('summary_json', sa.JSON, nullable=True),
        sa.Column('deterministic_summary', sa.Text, nullable=True),
        sa.Column('source_hash', sa.String(64), nullable=True, index=True),
        sa.Column('generated_at', sa.DateTime, nullable=False),
        sa.Column('stale_after', sa.DateTime, nullable=False),
        sa.Column('created_at', sa.DateTime, nullable=False),
    )


def downgrade() -> None:
    op.drop_table('strategy_reliability_snapshots')
