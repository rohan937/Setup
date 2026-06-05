"""API key management routes — M24 API Key Foundation.

POST   /api/api-keys              — create a new API key
GET    /api/api-keys              — list API keys
PATCH  /api/api-keys/{id}/revoke  — revoke an API key
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.constants import EventType, Severity
from app.core.rbac import require_can_manage_api_keys
from app.db.session import get_db
from app.models.api_key import ApiKey
from app.models.audit_timeline_event import AuditTimelineEvent
from app.models.organization import Organization
from app.schemas.api_keys import (
    ApiKeyCreateRequest,
    ApiKeyCreateResponse,
    ApiKeyListResponse,
    ApiKeyRead,
    ApiKeyRevokeResponse,
)
from app.services.api_keys import generate_api_key, hash_api_key

router = APIRouter(tags=["api-keys"])

settings = get_settings()


def _get_org(db: Session, organization_id: uuid.UUID | None) -> Organization:
    """Resolve the organization, defaulting to the first org in local dev."""
    if organization_id is not None:
        org = db.query(Organization).filter(Organization.id == organization_id).first()
        if org is None:
            raise HTTPException(status_code=404, detail="Organization not found")
        return org
    # Local dev fallback: use the first available organization.
    org = db.query(Organization).first()
    if org is None:
        raise HTTPException(status_code=500, detail="No organization found in database")
    return org


@router.post("/api-keys", response_model=ApiKeyCreateResponse, status_code=201)
def create_api_key(
    body: ApiKeyCreateRequest,
    db: Session = Depends(get_db),
    _member=Depends(require_can_manage_api_keys),
) -> ApiKeyCreateResponse:
    """Create a new API key.

    The ``raw_key`` in the response is the ONLY time the plaintext key is
    returned.  Store it securely — QuantFidelity will never show it again.
    """
    # If organization_id is None but project_id is provided, infer org from project.
    resolved_org_id = body.organization_id
    if resolved_org_id is None and body.project_id is not None:
        from app.models.project import Project as _Project
        _proj = db.query(_Project).filter(_Project.id == body.project_id).first()
        if _proj is None:
            raise HTTPException(status_code=404, detail="Project not found")
        resolved_org_id = _proj.organization_id

    org = _get_org(db, resolved_org_id)

    # Validate project if provided
    if body.project_id is not None:
        from app.models.project import Project
        project = db.query(Project).filter(Project.id == body.project_id).first()
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")

    raw_key, key_prefix = generate_api_key(env=settings.qf_api_key_env)
    key_hash = hash_api_key(raw_key, settings.qf_api_key_hash_secret)

    # Use org.id.hex (32-char hex, no hyphens) — not str(org.id) (36-char with
    # hyphens) — because SQLAlchemy's Uuid(as_uuid=True) stores the PK in that
    # format.  Using str() produces a hyphenated string that fails the FK
    # constraint on PostgreSQL where VARCHAR equality is exact.  Every other
    # String(36) FK reference in the codebase consistently uses .hex.
    api_key = ApiKey(
        organization_id=org.id.hex,
        project_id=body.project_id.hex if body.project_id is not None else None,
        name=body.name,
        key_prefix=key_prefix,
        key_hash=key_hash,
        scopes_json=body.scopes,
        status="active",
    )
    db.add(api_key)
    db.flush()

    event = AuditTimelineEvent(
        organization_id=org.id,
        project_id=body.project_id,
        event_type=EventType.api_key_created,
        title=f"API key created: {body.name}",
        description=(
            f"API key '{body.name}' created with prefix '{key_prefix}'. "
            f"Scopes: {', '.join(body.scopes)}."
        ),
        source_type="api_key",
        source_id=str(api_key.id),
        severity=Severity.info,
        metadata_json={
            "api_key_name": body.name,
            "key_prefix": key_prefix,
            "scopes": body.scopes,
        },
    )
    db.add(event)

    db.commit()
    db.refresh(api_key)

    return ApiKeyCreateResponse(
        api_key=ApiKeyRead.model_validate(api_key),
        raw_key=raw_key,
    )


@router.get("/api-keys", response_model=ApiKeyListResponse)
def list_api_keys(
    organization_id: str | None = None,
    project_id: str | None = None,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    _member=Depends(require_can_manage_api_keys),
) -> ApiKeyListResponse:
    """List API keys (never returns the raw key or key hash). RBAC: Owner/Admin only."""
    # Normalise the filter values to the .hex format used for storage so that
    # both the 36-char hyphenated (str(uuid)) and 32-char hex (uuid.hex) forms
    # accepted as query params produce correct results.
    def _to_hex(value: str | None) -> str | None:
        if value is None:
            return None
        try:
            return uuid.UUID(value).hex
        except (ValueError, AttributeError):
            return value  # pass through as-is and let the DB return empty

    q = db.query(ApiKey)
    if organization_id is not None:
        q = q.filter(ApiKey.organization_id == _to_hex(organization_id))
    if project_id is not None:
        q = q.filter(ApiKey.project_id == _to_hex(project_id))
    if status is not None:
        q = q.filter(ApiKey.status == status)

    total = q.count()
    items = q.order_by(ApiKey.created_at.desc()).offset(offset).limit(limit).all()

    return ApiKeyListResponse(
        items=[ApiKeyRead.model_validate(k) for k in items],
        total=total,
    )


@router.patch("/api-keys/{api_key_id}/revoke", response_model=ApiKeyRevokeResponse)
def revoke_api_key(
    api_key_id: uuid.UUID,
    db: Session = Depends(get_db),
    _member=Depends(require_can_manage_api_keys),
) -> ApiKeyRevokeResponse:
    """Revoke an API key. RBAC: Owner/Admin only. Revoked keys are rejected by the auth dependency."""
    key = db.query(ApiKey).filter(ApiKey.id == api_key_id).first()
    if key is None:
        raise HTTPException(status_code=404, detail="API key not found")

    now = datetime.now(timezone.utc)
    key.status = "revoked"
    key.revoked_at = now
    db.flush()

    event = AuditTimelineEvent(
        organization_id=uuid.UUID(key.organization_id) if isinstance(key.organization_id, str) else key.organization_id,
        project_id=uuid.UUID(key.project_id) if isinstance(key.project_id, str) else key.project_id,
        event_type=EventType.api_key_revoked,
        title=f"API key revoked: {key.name}",
        description=f"API key '{key.name}' (prefix: {key.key_prefix}) was revoked.",
        source_type="api_key",
        source_id=str(key.id),
        severity=Severity.info,
        metadata_json={
            "api_key_name": key.name,
            "key_prefix": key.key_prefix,
            "revoked_at": now.isoformat(),
        },
    )
    db.add(event)

    db.commit()
    db.refresh(key)

    return ApiKeyRevokeResponse(
        id=key.id,
        status=key.status,
        revoked_at=key.revoked_at,
    )
