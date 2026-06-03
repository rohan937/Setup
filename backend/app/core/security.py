"""Password hashing and JWT utilities for M68 auth."""

from __future__ import annotations

import binascii
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

from app.core.config import get_settings


# ---------------------------------------------------------------------------
# Password hashing (stdlib pbkdf2 — no passlib required)
# ---------------------------------------------------------------------------

def hash_password(password: str) -> str:
    """Hash *password* using PBKDF2-HMAC-SHA256 with a random salt.

    Returns a string in the format ``<hex_salt>:<hex_dk>``.
    """
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 260_000)
    return salt + ":" + binascii.hexlify(dk).decode()


def verify_password(plain: str, hashed: str) -> bool:
    """Return ``True`` if *plain* matches the stored *hashed* value."""
    try:
        salt, stored = hashed.split(":", 1)
    except ValueError:
        return False
    dk = hashlib.pbkdf2_hmac("sha256", plain.encode(), salt.encode(), 260_000)
    return secrets.compare_digest(binascii.hexlify(dk).decode(), stored)


# ---------------------------------------------------------------------------
# JWT utilities
# ---------------------------------------------------------------------------

def create_access_token(
    user_id: str,
    email: str,
    expires_minutes: int = 1440,
) -> str:
    """Create a signed JWT access token.

    Payload keys: ``sub`` (user_id), ``email``, ``exp``, ``type``.
    """
    settings = get_settings()
    exp = datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)
    payload: dict[str, Any] = {
        "sub": user_id,
        "email": email,
        "exp": exp,
        "type": "access",
    }
    return jwt.encode(
        payload,
        settings.QF_JWT_SECRET_KEY,
        algorithm=settings.QF_JWT_ALGORITHM,
    )


def decode_access_token(token: str) -> dict | None:
    """Verify and decode a JWT access token.

    Returns the decoded payload dict, or ``None`` if the token is invalid or
    expired.
    """
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.QF_JWT_SECRET_KEY,
            algorithms=[settings.QF_JWT_ALGORITHM],
        )
        if payload.get("type") != "access":
            return None
        return payload
    except jwt.PyJWTError:
        return None
