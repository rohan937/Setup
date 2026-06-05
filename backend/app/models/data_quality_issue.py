from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import GUID as Uuid

from app.db.base import Base
from app.models.base import UUIDPrimaryKeyMixin


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DataQualityIssue(UUIDPrimaryKeyMixin, Base):
    """Immutable data quality issue record attached to a snapshot.

    Append-only — no ``updated_at``.
    """

    __tablename__ = "data_quality_issues"

    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("dataset_snapshots.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # See constants.IssueType for valid values.
    issue_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    # See constants.Severity for valid values.
    severity: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    # Which field triggered the issue (optional — not all checks are field-level).
    field_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # 0-indexed row number inside the snapshot, if applicable.
    row_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Human-readable explanation of the specific finding.
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    # Relationships
    snapshot: Mapped["DatasetSnapshot"] = relationship(  # noqa: F821
        "DatasetSnapshot", back_populates="issues"
    )

    def __repr__(self) -> str:
        return (
            f"<DataQualityIssue type={self.issue_type!r} "
            f"severity={self.severity!r} row={self.row_index}>"
        )
