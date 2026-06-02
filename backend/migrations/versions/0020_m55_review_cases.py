"""M55 research review cases"""
from alembic import op
import sqlalchemy as sa

revision = '0020_m55_review_cases'
down_revision = '0019_m54_config_policies'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'research_review_cases',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('strategy_id', sa.String(36), sa.ForeignKey('strategies.id'), nullable=False, index=True),
        sa.Column('title', sa.String(500), nullable=False),
        sa.Column('case_key', sa.String(255), nullable=False, index=True),
        sa.Column('status', sa.String(50), nullable=False, default='open'),
        sa.Column('severity', sa.String(50), nullable=False),
        sa.Column('category', sa.String(100), nullable=False),
        sa.Column('summary', sa.Text, nullable=True),
        sa.Column('deterministic_summary', sa.Text, nullable=True),
        sa.Column('evidence_json', sa.JSON, nullable=True),
        sa.Column('suggested_actions_json', sa.JSON, nullable=True),
        sa.Column('linked_alert_ids_json', sa.JSON, nullable=True),
        sa.Column('linked_regression_run_ids_json', sa.JSON, nullable=True),
        sa.Column('linked_policy_evaluation_ids_json', sa.JSON, nullable=True),
        sa.Column('linked_backtest_audit_ids_json', sa.JSON, nullable=True),
        sa.Column('linked_run_ids_json', sa.JSON, nullable=True),
        sa.Column('linked_snapshot_ids_json', sa.JSON, nullable=True),
        sa.Column('opened_at', sa.DateTime, nullable=False),
        sa.Column('acknowledged_at', sa.DateTime, nullable=True),
        sa.Column('resolved_at', sa.DateTime, nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.Column('updated_at', sa.DateTime, nullable=False),
    )

    op.create_table(
        'research_review_case_events',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('case_id', sa.String(36), sa.ForeignKey('research_review_cases.id'), nullable=False, index=True),
        sa.Column('event_type', sa.String(100), nullable=False),
        sa.Column('title', sa.String(500), nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('metadata_json', sa.JSON, nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False),
    )


def downgrade() -> None:
    op.drop_table('research_review_case_events')
    op.drop_table('research_review_cases')
