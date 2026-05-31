"""ReportSection ORM model — M14 Reliability Reports."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.db.base import Base
from app.models.base import UUIDPrimaryKeyMixin


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ReportSection(UUIDPrimaryKeyMixin, Base):
    """One section of a reliability report.

    Sections are ordered by order_index and carry structured evidence as JSON.
    They are immutable after creation — regenerating the parent report creates
    new sections (cascade delete removes old ones).
    """

    __tablename__ = "report_sections"

    report_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("reports.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Stable machine key for this section (e.g. "overview", "backtest_trust").
    section_key: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    # Human-readable section title.
    title: Mapped[str] = mapped_column(String(255), nullable=False)

    # Hedged plain-language summary for this section only.
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # Optional section-level severity (null = informational).
    # See constants.Severity for valid values.
    severity: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Display order (0-indexed, ascending).
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Structured evidence for this section.
    evidence_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    # Relationships
    report: Mapped["Report"] = relationship(  # noqa: F821
        "Report", back_populates="sections"
    )

    def __repr__(self) -> str:
        return (
            f"<ReportSection key={self.section_key!r} order={self.order_index} "
            f"severity={self.severity!r}>"
        )
