"""API key generation, hashing, and verification utilities — M24."""

from __future__ import annotations

import hashlib
import hmac
import secrets


def generate_api_key(env: str = "local") -> tuple[str, str]:
    """Generate a new API key.

    Returns a ``(raw_key, key_prefix)`` tuple.

    - ``raw_key``    = ``"qf_{env}_{64_random_hex_chars}"``   (never stored)
    - ``key_prefix`` = ``"qf_{env}_{first_8_chars_of_random}"``  (safe to display)

    Uses :func:`secrets.token_hex(32)` (32 bytes → 64 hex chars) for the
    random portion, providing 256 bits of entropy.
    """
    random_hex = secrets.token_hex(32)  # 64-char hex string
    raw_key = f"qf_{env}_{random_hex}"
    key_prefix = f"qf_{env}_{random_hex[:8]}"
    return raw_key, key_prefix


def hash_api_key(raw_key: str, secret: str = "") -> str:
    """Hash an API key for storage.

    If *secret* is non-empty, uses HMAC-SHA-256 for stronger security (the
    secret acts as a pepper so that a compromised DB alone cannot brute-force
    keys).  If *secret* is empty, falls back to plain SHA-256.

    Returns a 64-character lowercase hex digest.

    Note:
        For local MVP, plain SHA-256 (empty secret) is fine.
        In production, set ``QF_API_KEY_HASH_SECRET`` in ``.env``.
    """
    if secret:
        digest = hmac.new(
            secret.encode("utf-8"),
            raw_key.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
    else:
        digest = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    return digest


def verify_api_key(raw_key: str, stored_hash: str, secret: str = "") -> bool:
    """Verify a raw API key against a stored hash using constant-time comparison.

    Uses :func:`hmac.compare_digest` to prevent timing attacks.
    """
    candidate_hash = hash_api_key(raw_key, secret)
    return hmac.compare_digest(candidate_hash, stored_hash)


def extract_api_key_from_request(request) -> str | None:  # type: ignore[type-arg]
    """Extract a raw API key from request headers.

    Checks in order:
    1. ``Authorization: Bearer <key>``
    2. ``X-QF-Api-Key: <key>``

    Returns the raw key string, or ``None`` if no key is present.
    """
    # 1. Authorization: Bearer <key>
    auth_header: str | None = request.headers.get("Authorization")
    if auth_header and auth_header.lower().startswith("bearer "):
        token = auth_header[len("bearer "):].strip()
        if token:
            return token

    # 2. X-QF-Api-Key: <key>
    api_key_header: str | None = request.headers.get("X-QF-Api-Key")
    if api_key_header and api_key_header.strip():
        return api_key_header.strip()

    return None
