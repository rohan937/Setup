"""FastAPI authentication dependencies — M24 API Key Foundation."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import Depends, Request
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
