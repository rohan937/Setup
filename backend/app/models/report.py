"""Report ORM model — M14 Reliability Reports."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import GUID as Uuid

from app.db.base import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Report(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A generated reliability report aggregating evidence for a strategy, audit, or snapshot.

    Reports are generated on demand (POST) and stored for later retrieval.
    They are deterministic — no AI, no live data, no external calls.
    """

    __tablename__ = "reports"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    strategy_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("strategies.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # See constants.ReportType for valid values.
    report_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    title: Mapped[str] = mapped_column(String(255), nullable=False)

    # See constants.ReportStatus for valid values.
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="generated", index=True
    )

    # Hedged plain-language executive summary of the report findings.
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # Timestamp when this report was generated (distinct from created_at for clarity).
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, index=True
    )

    # The primary evidence source (e.g. "strategy", "backtest_audit", "dataset_snapshot").
    source_type: Mapped[str | None] = mapped_column(
        String(100), nullable=True, index=True
    )
    # UUID of the source record as a string.
    source_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    # 0–100 reliability score derived from available evidence.  Null when insufficient.
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Full structured report data as a JSON blob.
    report_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Relationships
    organization: Mapped["Organization"] = relationship(  # noqa: F821
        "Organization", back_populates="reports"
    )
    project: Mapped["Project | None"] = relationship(  # noqa: F821
        "Project", back_populates="reports"
    )
    strategy: Mapped["Strategy | None"] = relationship(  # noqa: F821
        "Strategy", back_populates="reports"
    )
    sections: Mapped[list["ReportSection"]] = relationship(
        "ReportSection",
        back_populates="report",
        cascade="all, delete-orphan",
        order_by="ReportSection.order_index",
    )

    def __repr__(self) -> str:
        return (
            f"<Report type={self.report_type!r} status={self.status!r} "
            f"score={self.score} title={self.title!r}>"
        )
