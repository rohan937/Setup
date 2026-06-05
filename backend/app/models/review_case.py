"""ORM models for M55 research review cases."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Text, DateTime, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import GUID as Uuid
from app.models.base import GUIDString

from app.db.base import Base
from app.models.base import UUIDPrimaryKeyMixin


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ResearchReviewCase(UUIDPrimaryKeyMixin, Base):
    """A research review case surfaced for a strategy."""

    __tablename__ = "research_review_cases"

    strategy_id: Mapped[str] = mapped_column(
        GUIDString(), ForeignKey("strategies.id"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    case_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="open")
    severity: Mapped[str] = mapped_column(String(50), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    deterministic_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    suggested_actions_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    linked_alert_ids_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    linked_regression_run_ids_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    linked_policy_evaluation_ids_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    linked_backtest_audit_ids_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    linked_run_ids_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    linked_snapshot_ids_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)

    events: Mapped[list["ResearchReviewCaseEvent"]] = relationship(
        "ResearchReviewCaseEvent",
        back_populates="case",
        cascade="all, delete-orphan",
        order_by="ResearchReviewCaseEvent.created_at",
    )

    def __repr__(self) -> str:
        return f"<ResearchReviewCase key={self.case_key!r} status={self.status!r}>"


class ResearchReviewCaseEvent(UUIDPrimaryKeyMixin, Base):
    """An event recorded on a research review case (opened, refreshed, acknowledged, resolved)."""

    __tablename__ = "research_review_case_events"

    case_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("research_review_cases.id"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)

    case: Mapped["ResearchReviewCase"] = relationship(
        "ResearchReviewCase",
        back_populates="events",
    )

    def __repr__(self) -> str:
        return f"<ResearchReviewCaseEvent type={self.event_type!r}>"
