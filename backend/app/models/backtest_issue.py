from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import GUID as Uuid

from app.db.base import Base
from app.models.base import UUIDPrimaryKeyMixin


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class BacktestIssue(UUIDPrimaryKeyMixin, Base):
    """One detected realism concern within a BacktestAudit.

    Issues are immutable once created.  They are cascade-deleted when the
    parent BacktestAudit is deleted (deduplication on re-audit).
    """

    __tablename__ = "backtest_issues"

    backtest_audit_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("backtest_audits.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # See BacktestIssueType in constants.py.
    issue_type: Mapped[str] = mapped_column(String(100), nullable=False)
    # See Severity in constants.py.
    severity: Mapped[str] = mapped_column(String(50), nullable=False)

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    # Optional structured evidence (what value was found, thresholds crossed, etc.)
    evidence_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Optional actionable guidance — a specific thing the user can verify.
    suggested_check: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        nullable=False,
    )

    # Relationships
    backtest_audit: Mapped["BacktestAudit"] = relationship(  # noqa: F821
        "BacktestAudit",
        back_populates="issues",
    )

    def __repr__(self) -> str:
        return (
            f"<BacktestIssue type={self.issue_type!r} severity={self.severity!r} "
            f"title={self.title!r}>"
        )
