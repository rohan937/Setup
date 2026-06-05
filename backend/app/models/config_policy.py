"""ORM models for M54 strategy config policy engine."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import GUID as Uuid

from app.db.base import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class StrategyConfigPolicy(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A named policy containing a set of rules to evaluate against config snapshots."""

    __tablename__ = "strategy_config_policies"

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

    # Relationships
    strategy: Mapped["Strategy"] = relationship(  # noqa: F821
        "Strategy",
        foreign_keys=[strategy_id],
    )
    evaluations: Mapped[list["StrategyConfigPolicyEvaluation"]] = relationship(
        "StrategyConfigPolicyEvaluation",
        back_populates="policy",
        cascade="all, delete-orphan",
        order_by="StrategyConfigPolicyEvaluation.created_at",
    )

    def __repr__(self) -> str:
        return f"<StrategyConfigPolicy name={self.name!r} active={self.is_active}>"


class StrategyConfigPolicyEvaluation(UUIDPrimaryKeyMixin, Base):
    """One evaluation run of a policy against a config snapshot."""

    __tablename__ = "strategy_config_policy_evaluations"

    strategy_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("strategies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    policy_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("strategy_config_policies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    config_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("strategy_config_snapshots.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    overall_status: Mapped[str] = mapped_column(String(50), nullable=False)
    passed_count: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
    warning_count: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
    failed_count: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
    critical_failed_count: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
    result_json: Mapped[dict | None] = mapped_column(JSON(), nullable=True)
    deterministic_summary: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
    )

    # Relationships
    policy: Mapped["StrategyConfigPolicy"] = relationship(
        "StrategyConfigPolicy",
        back_populates="evaluations",
    )
    results: Mapped[list["StrategyConfigPolicyResult"]] = relationship(
        "StrategyConfigPolicyResult",
        back_populates="evaluation",
        cascade="all, delete-orphan",
        order_by="StrategyConfigPolicyResult.created_at",
    )

    def __repr__(self) -> str:
        return f"<StrategyConfigPolicyEvaluation status={self.overall_status!r}>"


class StrategyConfigPolicyResult(Base):
    """One rule result within a policy evaluation."""

    __tablename__ = "strategy_config_policy_results"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    evaluation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("strategy_config_policy_evaluations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    rule_key: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    severity: Mapped[str] = mapped_column(String(50), nullable=False)
    is_required: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)
    observed_value: Mapped[str | None] = mapped_column(Text(), nullable=True)
    expected_value: Mapped[str | None] = mapped_column(Text(), nullable=True)
    key_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    evidence_json: Mapped[dict | None] = mapped_column(JSON(), nullable=True)
    suggested_action: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
    )

    # Relationships
    evaluation: Mapped["StrategyConfigPolicyEvaluation"] = relationship(
        "StrategyConfigPolicyEvaluation",
        back_populates="results",
    )

    def __repr__(self) -> str:
        return f"<StrategyConfigPolicyResult key={self.rule_key!r} status={self.status!r}>"
