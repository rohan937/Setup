"""ORM models for M53 strategy regression tests."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.db.base import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class StrategyRegressionTest(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A single regression test definition for a strategy."""

    __tablename__ = "strategy_regression_tests"

    strategy_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("strategies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    test_key: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    # metric_delta / metric_threshold / evidence_score_threshold /
    # freshness_status / alert_state / readiness_verdict / drift_status /
    # shadow_status / assumption_health / backtest_trust
    test_type: Mapped[str] = mapped_column(String(50), nullable=False)
    metric_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # gte / lte / eq / neq / max_drop_pct / max_increase_pct /
    # max_absolute_drop / status_not_in
    operator: Mapped[str] = mapped_column(String(50), nullable=False)
    threshold_value: Mapped[float | None] = mapped_column(Float(), nullable=True)
    threshold_json: Mapped[dict | None] = mapped_column(JSON(), nullable=True)
    severity: Mapped[str] = mapped_column(String(50), nullable=False, default="medium")
    is_required: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)

    # Relationships
    strategy: Mapped["Strategy"] = relationship(  # noqa: F821
        "Strategy",
        foreign_keys=[strategy_id],
    )

    def __repr__(self) -> str:
        return f"<StrategyRegressionTest key={self.test_key!r} type={self.test_type!r}>"


class StrategyRegressionTestRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A single execution of a strategy's regression test suite."""

    __tablename__ = "strategy_regression_test_runs"

    strategy_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("strategies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    suite_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mode: Mapped[str] = mapped_column(String(50), nullable=False)
    baseline_run_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("strategy_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    comparison_run_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("strategy_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # passed / warning / failed / insufficient_evidence
    overall_status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="insufficient_evidence"
    )
    passed_count: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
    failed_count: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
    warning_count: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
    required_failed_count: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
    result_json: Mapped[dict | None] = mapped_column(JSON(), nullable=True)
    deterministic_summary: Mapped[str | None] = mapped_column(Text(), nullable=True)

    # Relationships
    strategy: Mapped["Strategy"] = relationship(  # noqa: F821
        "Strategy",
        foreign_keys=[strategy_id],
    )
    results: Mapped[list["StrategyRegressionTestResult"]] = relationship(
        "StrategyRegressionTestResult",
        back_populates="test_run",
        cascade="all, delete-orphan",
        order_by="StrategyRegressionTestResult.created_at",
    )

    def __repr__(self) -> str:
        return (
            f"<StrategyRegressionTestRun mode={self.mode!r} "
            f"status={self.overall_status!r}>"
        )


class StrategyRegressionTestResult(Base):
    """A single test result within a regression test run."""

    __tablename__ = "strategy_regression_test_results"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    test_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("strategy_regression_test_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    regression_test_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("strategy_regression_tests.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    test_key: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    # passed / warning / failed / skipped
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    severity: Mapped[str] = mapped_column(String(50), nullable=False, default="medium")
    is_required: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)
    observed_value: Mapped[str | None] = mapped_column(String(255), nullable=True)
    expected_value: Mapped[str | None] = mapped_column(String(255), nullable=True)
    baseline_value: Mapped[str | None] = mapped_column(String(255), nullable=True)
    comparison_value: Mapped[str | None] = mapped_column(String(255), nullable=True)
    evidence_json: Mapped[dict | None] = mapped_column(JSON(), nullable=True)
    suggested_action: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    # Relationships
    test_run: Mapped["StrategyRegressionTestRun"] = relationship(
        "StrategyRegressionTestRun",
        back_populates="results",
    )

    def __repr__(self) -> str:
        return (
            f"<StrategyRegressionTestResult key={self.test_key!r} "
            f"status={self.status!r}>"
        )
