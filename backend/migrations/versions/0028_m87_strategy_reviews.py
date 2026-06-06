"""M87 strategy reviews: strategies.lifecycle_stage + strategy_reviews/comments/events"""
from alembic import op
import sqlalchemy as sa

revision = '0028_m87_strategy_reviews'
down_revision = '0027_m85_alert_lifecycle'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # strategies: persisted governance-approved lifecycle stage (NULL => computed).
    op.add_column('strategies', sa.Column('lifecycle_stage', sa.String(50), nullable=True))

    # strategy_reviews: governance promotion review requests.
    op.create_table(
        'strategy_reviews',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('strategy_id', sa.String(36), nullable=False),
        sa.Column('target_stage', sa.String(50), nullable=False),
        sa.Column('current_stage_at_submission', sa.String(50), nullable=True),
        sa.Column('status', sa.String(30), nullable=False),
        sa.Column('submitted_by_user_id', sa.String(36), nullable=True),
        sa.Column('reviewer_user_id', sa.String(36), nullable=True),
        sa.Column('submitted_at', sa.DateTime, nullable=True),
        sa.Column('decided_at', sa.DateTime, nullable=True),
        sa.Column('decision', sa.String(30), nullable=True),
        sa.Column('decision_note', sa.Text, nullable=True),
        sa.Column('evidence_snapshot_json', sa.JSON, nullable=True),
        sa.Column('checklist_json', sa.JSON, nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.Column('updated_at', sa.DateTime, nullable=False),
        sa.PrimaryKeyConstraint('id', name='pk_strategy_reviews'),
        sa.ForeignKeyConstraint(
            ['strategy_id'], ['strategies.id'],
            name='fk_strategy_reviews_strategy_id',
            ondelete='CASCADE',
        ),
    )
    op.create_index('ix_strategy_reviews_strategy_id', 'strategy_reviews', ['strategy_id'])
    op.create_index('ix_strategy_reviews_status', 'strategy_reviews', ['status'])

    # strategy_review_comments: free-text comment thread.
    op.create_table(
        'strategy_review_comments',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('review_id', sa.String(36), nullable=False),
        sa.Column('author_user_id', sa.String(36), nullable=True),
        sa.Column('comment', sa.Text, nullable=False),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.PrimaryKeyConstraint('id', name='pk_strategy_review_comments'),
        sa.ForeignKeyConstraint(
            ['review_id'], ['strategy_reviews.id'],
            name='fk_strategy_review_comments_review_id',
            ondelete='CASCADE',
        ),
    )
    op.create_index(
        'ix_strategy_review_comments_review_id', 'strategy_review_comments', ['review_id']
    )

    # strategy_review_events: immutable decision/audit log.
    op.create_table(
        'strategy_review_events',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('review_id', sa.String(36), nullable=False),
        sa.Column('actor_user_id', sa.String(36), nullable=True),
        sa.Column('action', sa.String(40), nullable=False),
        sa.Column('note', sa.Text, nullable=True),
        sa.Column('metadata_json', sa.JSON, nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.PrimaryKeyConstraint('id', name='pk_strategy_review_events'),
        sa.ForeignKeyConstraint(
            ['review_id'], ['strategy_reviews.id'],
            name='fk_strategy_review_events_review_id',
            ondelete='CASCADE',
        ),
    )
    op.create_index(
        'ix_strategy_review_events_review_id', 'strategy_review_events', ['review_id']
    )


def downgrade() -> None:
    op.drop_index('ix_strategy_review_events_review_id', table_name='strategy_review_events')
    op.drop_table('strategy_review_events')

    op.drop_index('ix_strategy_review_comments_review_id', table_name='strategy_review_comments')
    op.drop_table('strategy_review_comments')

    op.drop_index('ix_strategy_reviews_status', table_name='strategy_reviews')
    op.drop_index('ix_strategy_reviews_strategy_id', table_name='strategy_reviews')
    op.drop_table('strategy_reviews')

    op.drop_column('strategies', 'lifecycle_stage')
