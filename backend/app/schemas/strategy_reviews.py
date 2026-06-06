"""Pydantic schemas for the Strategy Review endpoints (M87).

The service returns ORM objects + plain dicts; routes build these models via
``model_validate`` (ORM) or ``Model(**dict)`` (checklist/packet).
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator


# ---------------------------------------------------------------------------
# Read models
# ---------------------------------------------------------------------------

class StrategyReviewRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    strategy_id: str
    target_stage: str
    current_stage_at_submission: str | None = None
    status: str
    submitted_by_user_id: str | None = None
    reviewer_user_id: str | None = None
    submitted_at: datetime | None = None
    decided_at: datetime | None = None
    decision: str | None = None
    decision_note: str | None = None
    evidence_snapshot_json: dict | None = None
    checklist_json: dict | None = None
    created_at: datetime
    updated_at: datetime

    @field_validator("id", "strategy_id", mode="before")
    @classmethod
    def _stringify(cls, v):
        return str(v) if isinstance(v, uuid.UUID) else v


class StrategyReviewCommentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    review_id: str
    author_user_id: str | None = None
    comment: str
    created_at: datetime

    @field_validator("id", "review_id", mode="before")
    @classmethod
    def _stringify(cls, v):
        return str(v) if isinstance(v, uuid.UUID) else v


class StrategyReviewEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    review_id: str
    actor_user_id: str | None = None
    action: str
    note: str | None = None
    metadata_json: dict | None = None
    created_at: datetime

    @field_validator("id", "review_id", mode="before")
    @classmethod
    def _stringify(cls, v):
        return str(v) if isinstance(v, uuid.UUID) else v


# ---------------------------------------------------------------------------
# Checklist
# ---------------------------------------------------------------------------

class ReviewChecklistItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    title: str
    category: str
    status: str  # pass | warn | fail | missing
    required: bool
    detail: str | None = None
    observed_value: str | None = None
    suggested_action: str | None = None


class ReviewChecklistBlocker(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    title: str
    reason: str | None = None
    suggested_action: str | None = None


class ReviewChecklist(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    target_stage: str
    current_stage: str | None = None
    items: list[ReviewChecklistItem]
    can_approve: bool
    blockers: list[ReviewChecklistBlocker]
    generated_at: datetime
    disclaimer: str


# ---------------------------------------------------------------------------
# Composite responses
# ---------------------------------------------------------------------------

class StrategyReviewDetailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    review: StrategyReviewRead
    checklist: ReviewChecklist
    comments: list[StrategyReviewCommentRead] = []
    events: list[StrategyReviewEventRead] = []


class StrategyReviewListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[StrategyReviewRead]


class ReviewPacketResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    filename: str
    format: str
    content: str | None = None


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------

class CreateReviewRequest(BaseModel):
    target_stage: str
    as_draft: bool = False


class ReviewDecisionRequest(BaseModel):
    note: str | None = None


class ReviewCommentRequest(BaseModel):
    comment: str
