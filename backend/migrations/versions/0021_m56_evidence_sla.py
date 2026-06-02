"""M56 evidence SLA monitor"""
from alembic import op
import sqlalchemy as sa

revision = '0021_m56_evidence_sla'
down_revision = '0020_m55_review_cases'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'evidence_sla_policies',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('strategy_id', sa.String(36), sa.ForeignKey('strategies.id'), nullable=False, index=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('is_active', sa.Boolean, nullable=False, server_default='1'),
        sa.Column('policy_json', sa.JSON, nullable=False),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.Column('updated_at', sa.DateTime, nullable=False),
    )

    op.create_table(
        'evidence_sla_evaluations',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('strategy_id', sa.String(36), sa.ForeignKey('strategies.id'), nullable=False, index=True),
        sa.Column('policy_id', sa.String(36), sa.ForeignKey('evidence_sla_policies.id'), nullable=False, index=True),
        sa.Column('overall_status', sa.String(50), nullable=False),
        sa.Column('passed_count', sa.Integer, nullable=False, server_default='0'),
        sa.Column('warning_count', sa.Integer, nullable=False, server_default='0'),
        sa.Column('violated_count', sa.Integer, nullable=False, server_default='0'),
        sa.Column('skipped_count', sa.Integer, nullable=False, server_default='0'),
        sa.Column('critical_violation_count', sa.Integer, nullable=False, server_default='0'),
        sa.Column('result_json', sa.JSON, nullable=True),
        sa.Column('deterministic_summary', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False),
    )

    op.create_table(
        'evidence_sla_results',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('evaluation_id', sa.String(36), sa.ForeignKey('evidence_sla_evaluations.id'), nullable=False, index=True),
        sa.Column('rule_key', sa.String(255), nullable=False),
        sa.Column('title', sa.String(500), nullable=False),
        sa.Column('evidence_type', sa.String(100), nullable=True),
        sa.Column('status', sa.String(50), nullable=False),
        sa.Column('severity', sa.String(50), nullable=False),
        sa.Column('is_required', sa.Boolean, nullable=False, server_default='1'),
        sa.Column('observed_value', sa.Text, nullable=True),
        sa.Column('expected_value', sa.Text, nullable=True),
        sa.Column('days_since_latest', sa.Float, nullable=True),
        sa.Column('latest_at', sa.DateTime, nullable=True),
        sa.Column('evidence_json', sa.JSON, nullable=True),
        sa.Column('suggested_action', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False),
    )


def downgrade() -> None:
    op.drop_table('evidence_sla_results')
    op.drop_table('evidence_sla_evaluations')
    op.drop_table('evidence_sla_policies')
