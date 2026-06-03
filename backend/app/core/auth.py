"""FastAPI authentication dependencies — M24 API Key + M68 JWT User Auth."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.models.api_key import ApiKey


async def get_optional_api_key(
    request: Request,
    db: Session = Depends(get_db),
) -> ApiKey | None:
    """Extract and validate an API key from request headers if present.

    Returns the :class:`ApiKey` ORM object if the key is valid and active,
    or ``None`` if no key was provided or the key is invalid/revoked.

    Updates ``last_used_at`` on the key when a valid key is found (flushed
    but not committed — the route is responsible for the final commit).
    """
    from app.services.api_keys import extract_api_key_from_request, hash_api_key

    raw_key = extract_api_key_from_request(request)
    if not raw_key:
        return None

    settings = get_settings()
    key_hash = hash_api_key(raw_key, settings.qf_api_key_hash_secret)

    key = db.query(ApiKey).filter(
        ApiKey.key_hash == key_hash,
        ApiKey.status == "active",
    ).first()

    if key is None:
        return None

    # Record usage — flush only, route commits later.
    key.last_used_at = datetime.now(timezone.utc)
    db.flush()

    return key


async def require_api_key_if_enabled(
    api_key: ApiKey | None = Depends(get_optional_api_key),
) -> ApiKey | None:
    """Enforce API key authentication when ``QF_REQUIRE_API_KEY_FOR_INGESTION`` is true.

    If the feature flag is enabled and no valid API key is present, raises
    HTTP 401 with an informative message.  Otherwise passes through.
    """
    from app.core.config import get_settings
    from fastapi import HTTPException

    settings = get_settings()
    if settings.qf_require_api_key_for_ingestion and api_key is None:
        raise HTTPException(
            status_code=401,
            detail=(
                "Valid API key required. "
                "Include 'Authorization: Bearer <key>' or 'X-QF-Api-Key: <key>' header."
            ),
        )
    return api_key


# ---------------------------------------------------------------------------
# M68: JWT bearer dependencies
# ---------------------------------------------------------------------------

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
):
    """Return the authenticated :class:`AuthUser` or raise HTTP 401."""
    import uuid as _uuid

    from app.core.security import decode_access_token
    from app.models.auth_user import AuthUser

    if credentials is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = decode_access_token(credentials.credentials)
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    sub = payload.get("sub")
    if sub is None:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    # AuthUser.id is Uuid(as_uuid=True) — convert string sub to uuid.UUID
    try:
        user_uuid = _uuid.UUID(sub)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=401, detail="Invalid token payload")
    user = db.query(AuthUser).filter(AuthUser.id == user_uuid).first()
    if user is None or user.status != "active":
        raise HTTPException(status_code=401, detail="User not found or disabled")
    return user


async def get_optional_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
):
    """Return the authenticated :class:`AuthUser` or ``None`` (no 401)."""
    import uuid as _uuid

    from app.core.security import decode_access_token
    from app.models.auth_user import AuthUser

    if credentials is None:
        return None
    payload = decode_access_token(credentials.credentials)
    if payload is None:
        return None
    sub = payload.get("sub")
    if sub is None:
        return None
    try:
        user_uuid = _uuid.UUID(sub)
    except (ValueError, AttributeError):
        return None
    return db.query(AuthUser).filter(AuthUser.id == user_uuid).first()
