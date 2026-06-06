"""M84 email tokens: one-time tokens for email verification + password reset.

Only token *hashes* are stored — the raw token is sent to the user once via
email and never persisted. See ``app.services.email_tokens``.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.base import GUIDString, UUIDPrimaryKeyMixin


class AuthEmailToken(UUIDPrimaryKeyMixin, Base):
    """A single-use, hashed email token for verification or password reset."""

    __tablename__ = "auth_email_tokens"

    user_id: Mapped[str] = mapped_column(
        GUIDString(),
        ForeignKey("auth_users.id"),
        nullable=False,
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True
    )
    # 'email_verification' | 'password_reset'
    token_type: Mapped[str] = mapped_column(String(32), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    def __repr__(self) -> str:
        return (
            f"<AuthEmailToken type={self.token_type!r} "
            f"used={self.used_at is not None}>"
        )
