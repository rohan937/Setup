from __future__ import annotations

from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class Organization(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "organizations"
    __table_args__ = (UniqueConstraint("slug", name="uq_organizations_slug"),)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    # Relationships
    users: Mapped[list["User"]] = relationship(  # noqa: F821
        "User", back_populates="organization", cascade="all, delete-orphan"
    )
    projects: Mapped[list["Project"]] = relationship(  # noqa: F821
        "Project", back_populates="organization", cascade="all, delete-orphan"
    )
    audit_timeline_events: Mapped[list["AuditTimelineEvent"]] = relationship(  # noqa: F821
        "AuditTimelineEvent", back_populates="organization"
    )
    alert_rules: Mapped[list["AlertRule"]] = relationship(  # noqa: F821
        "AlertRule", back_populates="organization", cascade="all, delete-orphan"
    )
    alerts: Mapped[list["Alert"]] = relationship(  # noqa: F821
        "Alert", back_populates="organization", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Organization slug={self.slug!r}>"
