"""ORM model for strategy reliability scores (M18)."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON
from app.models.base import GUID as Uuid

from app.db.base import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class StrategyReliabilityScore(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A single reliability score snapshot for a strategy (M18).

    Generated on demand by POST /api/strategies/{id}/reliability-score.
    All computation is deterministic — no AI, no live market data.
    """

    __tablename__ = "strategy_reliability_scores"

    strategy_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("strategies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Overall composite score (0–100) and status label.
    overall_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    # See constants.ReliabilityScoreStatus for valid values.
    status: Mapped[str] = mapped_column(String(50), nullable=False)

    # Per-component scores (all 0–100 or None when evidence is missing).
    strategy_activity_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    data_evidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    backtest_trust_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    config_evidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    universe_evidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    signal_evidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    alert_penalty_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    report_coverage_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Structured detail blobs.
    evidence_counts_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    component_summaries_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    missing_evidence_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    suggested_checks_json: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # When this score was computed (separate from created_at for clarity).
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )

    # Relationships
    strategy: Mapped["Strategy"] = relationship(  # noqa: F821
        "Strategy", back_populates="reliability_scores"
    )

    def __repr__(self) -> str:
        return (
            f"<StrategyReliabilityScore strategy_id={self.strategy_id} "
            f"overall={self.overall_score} status={self.status!r}>"
        )
