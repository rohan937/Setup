"""M59 experiment registry"""
from alembic import op
import sqlalchemy as sa

revision = '0022_m59_experiment_registry'
down_revision = '0021_m56_evidence_sla'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'strategy_experiments',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('strategy_id', sa.String(36), sa.ForeignKey('strategies.id'), nullable=False, index=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('slug', sa.String(255), nullable=False, index=True),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('experiment_type', sa.String(100), nullable=True),
        sa.Column('hypothesis', sa.Text, nullable=True),
        sa.Column('status', sa.String(50), nullable=False, server_default='active'),
        sa.Column('metadata_json', sa.JSON, nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.Column('updated_at', sa.DateTime, nullable=False),
    )

    op.create_table(
        'strategy_experiment_runs',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('experiment_id', sa.String(36), sa.ForeignKey('strategy_experiments.id'), nullable=False, index=True),
        sa.Column('strategy_run_id', sa.String(36), sa.ForeignKey('strategy_runs.id'), nullable=False, index=True),
        sa.Column('variant_label', sa.String(255), nullable=True),
        sa.Column('variant_key', sa.String(255), nullable=True),
        sa.Column('variant_params_json', sa.JSON, nullable=True),
        sa.Column('notes', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False),
    )

    op.create_table(
        'strategy_experiment_analyses',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('experiment_id', sa.String(36), sa.ForeignKey('strategy_experiments.id'), nullable=False, index=True),
        sa.Column('analysis_label', sa.String(255), nullable=True),
        sa.Column('overall_status', sa.String(50), nullable=False),
        sa.Column('variant_count', sa.Integer, nullable=False, server_default='0'),
        sa.Column('run_count', sa.Integer, nullable=False, server_default='0'),
        sa.Column('best_evidenced_run_id', sa.String(36), nullable=True),
        sa.Column('weakest_evidence_run_id', sa.String(36), nullable=True),
        sa.Column('result_json', sa.JSON, nullable=True),
        sa.Column('deterministic_summary', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False),
    )


def downgrade() -> None:
    op.drop_table('strategy_experiment_analyses')
    op.drop_table('strategy_experiment_runs')
    op.drop_table('strategy_experiments')
