"""M84 email token service: single-use verification / password-reset tokens.

Only token *hashes* are stored. The raw token is generated here, returned to the
caller exactly once (to embed in an email link), and never persisted or logged.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.security import hash_token
from app.models.auth_email_token import AuthEmailToken
from app.models.auth_user import AuthUser


def generate_raw_token() -> str:
    """Return a fresh URL-safe random token."""
    return secrets.token_urlsafe(32)


def create_email_token(
    db: Session, user: AuthUser, token_type: str, expire_hours: int
) -> str:
    """Create a new single-use email token and return the RAW token.

    Any prior unused token of the same ``(user_id, token_type)`` is marked used
    so only one token is outstanding at a time. Only the hash is stored.
    """
    now = datetime.now(timezone.utc)
    user_id = str(user.id)

    # Invalidate any prior outstanding tokens of this type (single outstanding).
    db.query(AuthEmailToken).filter(
        AuthEmailToken.user_id == user_id,
        AuthEmailToken.token_type == token_type,
        AuthEmailToken.used_at.is_(None),
    ).update({AuthEmailToken.used_at: now}, synchronize_session=False)

    raw = generate_raw_token()
    token = AuthEmailToken(
        user_id=user_id,
        token_hash=hash_token(raw),
        token_type=token_type,
        expires_at=now + timedelta(hours=expire_hours),
        created_at=now,
    )
    db.add(token)
    db.flush()
    return raw


def consume_email_token(
    db: Session, raw_token: str, token_type: str
) -> AuthUser | None:
    """Validate and consume a raw email token.

    Returns the associated ``AuthUser`` on success (marking the token used), or
    ``None`` if the token is unknown, wrong type, already used, or expired.
    """
    now = datetime.now(timezone.utc)
    token_hash = hash_token(raw_token)

    token = (
        db.query(AuthEmailToken)
        .filter(
            AuthEmailToken.token_hash == token_hash,
            AuthEmailToken.token_type == token_type,
            AuthEmailToken.used_at.is_(None),
            AuthEmailToken.expires_at > now,
        )
        .first()
    )
    if token is None:
        return None

    token.used_at = now
    db.flush()

    user = db.query(AuthUser).filter(AuthUser.id == token.user_id).first()
    return user
