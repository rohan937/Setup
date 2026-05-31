from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.db.base import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class StrategyRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "strategy_runs"

    strategy_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("strategies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    strategy_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("strategy_versions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # M7: optional link to a QuantFidelity dataset snapshot.
    # dataset_version (below) remains a free-text label for unlinked runs.
    dataset_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("dataset_snapshots.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    run_name: Mapped[str] = mapped_column(String(255), nullable=False)
    # See constants.RunType for valid values.
    run_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default="backtest"
    )
    # See constants.RunStatus for valid values.
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="pending"
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # JSON fields for flexible strategy run data.
    # params_json: signal parameters, lookback, etc.
    # assumptions_json: transaction cost, fill model, borrow, etc.
    # metrics_json: sharpe, turnover, max_drawdown, etc.
    params_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    assumptions_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    metrics_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    universe_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Free-text label — kept alongside dataset_snapshot_id for unlinked runs.
    dataset_version: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    strategy: Mapped["Strategy"] = relationship(  # noqa: F821
        "Strategy", back_populates="runs"
    )
    strategy_version: Mapped["StrategyVersion | None"] = relationship(  # noqa: F821
        "StrategyVersion", back_populates="runs"
    )
    # M7: linked dataset snapshot (lazy by default; eagerly loaded in routes that need it).
    snapshot: Mapped["DatasetSnapshot | None"] = relationship(  # noqa: F821
        "DatasetSnapshot",
        back_populates="strategy_runs",
        foreign_keys="[StrategyRun.dataset_snapshot_id]",
    )
    # M8: backtest audit records for this run (at most one in practice — POST replaces).
    backtest_audits: Mapped[list["BacktestAudit"]] = relationship(  # noqa: F821
        "BacktestAudit",
        back_populates="strategy_run",
        cascade="all, delete-orphan",
        order_by="BacktestAudit.created_at",
    )

    def __repr__(self) -> str:
        return f"<StrategyRun name={self.run_name!r} type={self.run_type!r} status={self.status!r}>"
