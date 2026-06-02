"""ORM models for M59 Experiment Registry."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.db.base import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class StrategyExperiment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A named experiment grouping multiple strategy runs as variants."""

    __tablename__ = "strategy_experiments"

    strategy_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("strategies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    experiment_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    hypothesis: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="active")
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Relationships
    strategy: Mapped["Strategy"] = relationship(  # noqa: F821
        "Strategy",
        foreign_keys=[strategy_id],
    )
    experiment_runs: Mapped[list["StrategyExperimentRun"]] = relationship(
        "StrategyExperimentRun",
        back_populates="experiment",
        cascade="all, delete-orphan",
        order_by="StrategyExperimentRun.created_at",
    )
    analyses: Mapped[list["StrategyExperimentAnalysis"]] = relationship(
        "StrategyExperimentAnalysis",
        back_populates="experiment",
        cascade="all, delete-orphan",
        order_by="StrategyExperimentAnalysis.created_at",
    )

    def __repr__(self) -> str:
        return f"<StrategyExperiment name={self.name!r} status={self.status!r}>"


class StrategyExperimentRun(UUIDPrimaryKeyMixin, Base):
    """Links a strategy run to an experiment as a named variant."""

    __tablename__ = "strategy_experiment_runs"

    experiment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("strategy_experiments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    strategy_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("strategy_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    variant_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    variant_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    variant_params_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    # Relationships
    experiment: Mapped["StrategyExperiment"] = relationship(
        "StrategyExperiment",
        back_populates="experiment_runs",
    )

    def __repr__(self) -> str:
        return f"<StrategyExperimentRun variant_label={self.variant_label!r}>"


class StrategyExperimentAnalysis(UUIDPrimaryKeyMixin, Base):
    """One analysis snapshot for an experiment."""

    __tablename__ = "strategy_experiment_analyses"

    experiment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("strategy_experiments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    analysis_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    overall_status: Mapped[str] = mapped_column(String(50), nullable=False)
    variant_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    run_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    best_evidenced_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    weakest_evidence_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    result_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    deterministic_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    # Relationships
    experiment: Mapped["StrategyExperiment"] = relationship(
        "StrategyExperiment",
        back_populates="analyses",
    )

    def __repr__(self) -> str:
        return f"<StrategyExperimentAnalysis status={self.overall_status!r}>"
