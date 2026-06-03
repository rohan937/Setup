"""ORM model for M65A strategy reliability snapshot cache."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.base import UUIDPrimaryKeyMixin


class StrategyReliabilitySnapshot(UUIDPrimaryKeyMixin, Base):
    """Cached snapshot of the reliability command center for a strategy.

    Snapshots are append-only — never updated after creation.
    No TimestampMixin: has created_at but no updated_at.
    """

    __tablename__ = "strategy_reliability_snapshots"

    strategy_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("strategies.id"), nullable=False, index=True
    )
    snapshot_status: Mapped[str] = mapped_column(String(50), nullable=False, default="fresh")
    command_status: Mapped[str | None] = mapped_column(String(100), nullable=True)
    command_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    readiness_verdict: Mapped[str | None] = mapped_column(String(100), nullable=True)
    readiness_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    robustness_verdict: Mapped[str | None] = mapped_column(String(100), nullable=True)
    robustness_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    freeze_recommendation: Mapped[str | None] = mapped_column(String(100), nullable=True)
    freeze_risk_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    freshness_status: Mapped[str | None] = mapped_column(String(100), nullable=True)
    freshness_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    drift_status: Mapped[str | None] = mapped_column(String(100), nullable=True)
    drift_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    shadow_status: Mapped[str | None] = mapped_column(String(100), nullable=True)
    shadow_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    open_review_case_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    high_critical_alert_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latest_regression_status: Mapped[str | None] = mapped_column(String(100), nullable=True)
    latest_config_policy_status: Mapped[str | None] = mapped_column(String(100), nullable=True)
    latest_sla_status: Mapped[str | None] = mapped_column(String(100), nullable=True)
    top_blockers_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    action_queue_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    subsystem_statuses_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    summary_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    deterministic_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    stale_after: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    def __repr__(self) -> str:
        return (
            f"<StrategyReliabilitySnapshot strategy_id={self.strategy_id!r} "
            f"status={self.snapshot_status!r} command_status={self.command_status!r}>"
        )
