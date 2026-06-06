"""StrategyReview ORM models — M87 Strategy Review.

A *strategy review* is a governance promotion request: a submitter asks for a
strategy to be advanced to a ``target_stage``, a reviewer approves / rejects /
requests changes, and every decision is captured immutably.

Distinct from ``ResearchReviewCase`` (issue groupings) — see ``review_case.py``.

``submitted_by_user_id`` / ``reviewer_user_id`` / ``author_user_id`` /
``actor_user_id`` are ``str(auth_user.id)`` of the acting user, or ``None`` for
system / pseudo actions.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.base import GUIDString, UUIDPrimaryKeyMixin, _utcnow


class StrategyReview(UUIDPrimaryKeyMixin, Base):
    """A governance promotion review for a strategy targeting a lifecycle stage."""

    __tablename__ = "strategy_reviews"

    strategy_id: Mapped[str] = mapped_column(
        GUIDString(),
        ForeignKey("strategies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # See constants.LIFECYCLE_STAGES for valid values.
    target_stage: Mapped[str] = mapped_column(String(50), nullable=False)
    current_stage_at_submission: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )
    # See constants.ReviewStatus for valid values.
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="submitted"
    )
    submitted_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    reviewer_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # See constants.ReviewDecision for valid values.
    decision: Mapped[str | None] = mapped_column(String(30), nullable=True)
    decision_note: Mapped[str | None] = mapped_column(Text(), nullable=True)
    evidence_snapshot_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    checklist_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class StrategyReviewComment(UUIDPrimaryKeyMixin, Base):
    """A free-text comment on a strategy review thread."""

    __tablename__ = "strategy_review_comments"

    review_id: Mapped[str] = mapped_column(
        GUIDString(),
        ForeignKey("strategy_reviews.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    author_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    comment: Mapped[str] = mapped_column(Text(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class StrategyReviewEvent(UUIDPrimaryKeyMixin, Base):
    """An immutable decision / audit-log entry for a strategy review.

    ``action`` is one of the values in ``constants.ReviewAction``.
    """

    __tablename__ = "strategy_review_events"

    review_id: Mapped[str] = mapped_column(
        GUIDString(),
        ForeignKey("strategy_reviews.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    actor_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    note: Mapped[str | None] = mapped_column(Text(), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
