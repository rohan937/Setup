"""API root / metadata endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.config import Settings, get_settings
from app.schemas.common import ApiInfoResponse

router = APIRouter(tags=["meta"])


@router.get("", response_model=ApiInfoResponse)
def api_root(settings: Settings = Depends(get_settings)) -> ApiInfoResponse:
    """API root. Returns service metadata for clients and the SDK."""
    return ApiInfoResponse(
        name=settings.app_name,
        version=settings.version,
        environment=settings.environment,
        api_version=settings.api_v1_prefix,
        docs_url="/docs",
    )
