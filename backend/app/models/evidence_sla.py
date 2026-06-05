"""ORM models for M56 Evidence SLA Monitor."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import GUID as Uuid

from app.db.base import Base
from app.models.base import UUIDPrimaryKeyMixin


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class EvidenceSLAPolicy(UUIDPrimaryKeyMixin, Base):
    """A named SLA policy containing a set of rules to evaluate evidence freshness and quality."""

    __tablename__ = "evidence_sla_policies"

    strategy_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("strategies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)
    policy_json: Mapped[dict] = mapped_column(JSON(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )

    # Relationships
    strategy: Mapped["Strategy"] = relationship(  # noqa: F821
        "Strategy",
        foreign_keys=[strategy_id],
    )
    evaluations: Mapped[list["EvidenceSLAEvaluation"]] = relationship(
        "EvidenceSLAEvaluation",
        back_populates="policy",
        cascade="all, delete-orphan",
        order_by="EvidenceSLAEvaluation.created_at",
    )

    def __repr__(self) -> str:
        return f"<EvidenceSLAPolicy name={self.name!r} active={self.is_active}>"


class EvidenceSLAEvaluation(UUIDPrimaryKeyMixin, Base):
    """One evaluation run of an SLA policy for a strategy."""

    __tablename__ = "evidence_sla_evaluations"

    strategy_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("strategies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    policy_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("evidence_sla_policies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    overall_status: Mapped[str] = mapped_column(String(50), nullable=False)
    passed_count: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
    warning_count: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
    violated_count: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
    critical_violation_count: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
    result_json: Mapped[dict | None] = mapped_column(JSON(), nullable=True)
    deterministic_summary: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
    )

    # Relationships
    policy: Mapped["EvidenceSLAPolicy"] = relationship(
        "EvidenceSLAPolicy",
        back_populates="evaluations",
    )
    results: Mapped[list["EvidenceSLAResult"]] = relationship(
        "EvidenceSLAResult",
        back_populates="evaluation",
        cascade="all, delete-orphan",
        order_by="EvidenceSLAResult.created_at",
    )

    def __repr__(self) -> str:
        return f"<EvidenceSLAEvaluation status={self.overall_status!r}>"


class EvidenceSLAResult(UUIDPrimaryKeyMixin, Base):
    """One rule result within an SLA evaluation."""

    __tablename__ = "evidence_sla_results"

    evaluation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("evidence_sla_evaluations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    rule_key: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    evidence_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    severity: Mapped[str] = mapped_column(String(50), nullable=False)
    is_required: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)
    observed_value: Mapped[str | None] = mapped_column(Text(), nullable=True)
    expected_value: Mapped[str | None] = mapped_column(Text(), nullable=True)
    days_since_latest: Mapped[float | None] = mapped_column(Float(), nullable=True)
    latest_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    evidence_json: Mapped[dict | None] = mapped_column(JSON(), nullable=True)
    suggested_action: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
    )

    # Relationships
    evaluation: Mapped["EvidenceSLAEvaluation"] = relationship(
        "EvidenceSLAEvaluation",
        back_populates="results",
    )

    def __repr__(self) -> str:
        return f"<EvidenceSLAResult key={self.rule_key!r} status={self.status!r}>"
