"""Pydantic schemas for the M94 Promotion Review Packet."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class PromotionPacketExportResponse(BaseModel):
    """Response schema for a promotion packet export (JSON or Markdown)."""

    model_config = ConfigDict(from_attributes=True)

    filename: str
    format: str
    content: str
    strategy_id: str
    target_stage: str | None
    generated_at: str
    disclaimer: str
