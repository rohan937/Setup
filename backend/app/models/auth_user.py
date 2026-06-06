from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.base import UUIDPrimaryKeyMixin


class AuthUser(UUIDPrimaryKeyMixin, Base):
    """Standalone authentication user, not org-scoped.

    Replaces the legacy org-scoped User model for auth purposes (M68).
    """

    __tablename__ = "auth_users"

    email: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, index=True
    )
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="active")
    is_superuser: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    email_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    email_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    def __repr__(self) -> str:
        return f"<AuthUser email={self.email!r} status={self.status!r}>"
