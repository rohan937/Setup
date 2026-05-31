from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.db.base import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class BacktestAudit(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Stores the result of a deterministic backtest reality check for one strategy run.

    Each run may have at most one audit record — POST replaces any existing audit.
    """

    __tablename__ = "backtest_audits"

    strategy_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("strategy_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Overall trust score: 0–100.  Starts at 100; each issue deducts a penalty.
    trust_score: Mapped[int] = mapped_column(Integer, nullable=False, default=100)

    # Category subscores (same formula, scoped to issues in that category).
    lookahead_risk_score: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    cost_realism_score: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    fill_realism_score: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    liquidity_realism_score: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    borrow_realism_score: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    data_quality_score: Mapped[int] = mapped_column(Integer, nullable=False, default=100)

    # Human-readable status derived from trust_score.
    # See BacktestStatus in constants.py.
    overall_status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="excellent"
    )

    # Hedged plain-language summary of the audit findings.
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # M13: cost sensitivity, fill realism, and fragility summary as JSON blobs.
    # Nullable — populated only when the run has sufficient input data.
    cost_sensitivity_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    fill_realism_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    fragility_summary_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Relationships
    strategy_run: Mapped["StrategyRun"] = relationship(  # noqa: F821
        "StrategyRun",
        back_populates="backtest_audits",
    )
    issues: Mapped[list["BacktestIssue"]] = relationship(  # noqa: F821
        "BacktestIssue",
        back_populates="backtest_audit",
        cascade="all, delete-orphan",
        order_by="BacktestIssue.created_at",
    )

    def __repr__(self) -> str:
        return (
            f"<BacktestAudit run={self.strategy_run_id} "
            f"trust={self.trust_score} status={self.overall_status!r}>"
        )
