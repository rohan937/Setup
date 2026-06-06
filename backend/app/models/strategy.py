from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import GUID as Uuid

from app.db.base import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class Strategy(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "strategies"

    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # See constants.AssetClass for valid values.
    asset_class: Mapped[str] = mapped_column(
        String(50), nullable=False, default="equity"
    )
    # See constants.StrategyStatus for valid values.
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="active"
    )
    # M87: governance-approved/promoted lifecycle stage. NULL => use the
    # computed lifecycle (app.services.strategy_lifecycle). See
    # constants.LIFECYCLE_STAGES for valid values.
    lifecycle_stage: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Relationships
    project: Mapped["Project"] = relationship(  # noqa: F821
        "Project", back_populates="strategies"
    )
    versions: Mapped[list["StrategyVersion"]] = relationship(  # noqa: F821
        "StrategyVersion",
        back_populates="strategy",
        cascade="all, delete-orphan",
        order_by="StrategyVersion.created_at",
    )
    runs: Mapped[list["StrategyRun"]] = relationship(  # noqa: F821
        "StrategyRun",
        back_populates="strategy",
        cascade="all, delete-orphan",
        order_by="StrategyRun.created_at",
    )
    audit_timeline_events: Mapped[list["AuditTimelineEvent"]] = relationship(  # noqa: F821
        "AuditTimelineEvent", back_populates="strategy"
    )
    alerts: Mapped[list["Alert"]] = relationship(  # noqa: F821
        "Alert", back_populates="strategy"
    )
    reports: Mapped[list["Report"]] = relationship(  # noqa: F821
        "Report", back_populates="strategy"
    )
    config_snapshots: Mapped[list["StrategyConfigSnapshot"]] = relationship(  # noqa: F821
        "StrategyConfigSnapshot",
        back_populates="strategy",
        cascade="all, delete-orphan",
        order_by="StrategyConfigSnapshot.created_at.desc()",
    )
    universe_snapshots: Mapped[list["UniverseSnapshot"]] = relationship(  # noqa: F821
        "UniverseSnapshot",
        back_populates="strategy",
        cascade="all, delete-orphan",
        order_by="UniverseSnapshot.created_at.desc()",
    )
    # M17: signal snapshots for this strategy.
    signal_snapshots: Mapped[list["SignalSnapshot"]] = relationship(  # noqa: F821
        "SignalSnapshot",
        back_populates="strategy",
        cascade="all, delete-orphan",
        order_by="SignalSnapshot.created_at.desc()",
    )
    # M18: reliability scores for this strategy.
    reliability_scores: Mapped[list["StrategyReliabilityScore"]] = relationship(  # noqa: F821
        "StrategyReliabilityScore",
        back_populates="strategy",
        cascade="all, delete-orphan",
        order_by="StrategyReliabilityScore.generated_at.desc()",
    )
    # M25: SDK ingestion batches for idempotency tracking.
    sdk_ingestion_batches: Mapped[list["SdkIngestionBatch"]] = relationship(  # noqa: F821
        "SdkIngestionBatch",
        back_populates="strategy",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Strategy slug={self.slug!r} status={self.status!r}>"
