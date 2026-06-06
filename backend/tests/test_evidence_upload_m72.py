"""M72 tests: web evidence-bundle ingestion is RBAC-gated for JWT users.

The ingest endpoint already existed (M22) and is used by the SDK/CLI via API
keys. M72 adds the M69 write-access dependency so web/JWT users must have
write-research permission. SDK/API-key callers (no JWT) resolve to a permissive
local pseudo-owner and are unaffected.

Covers:
  - owner (JWT) can ingest a bundle            -> 201
  - viewer (JWT) cannot ingest                 -> 403
  - no token (local-dev / SDK-style) can ingest -> 201 (pseudo-owner)
  - malformed bundle body                      -> 422
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.auth_user import AuthUser
from app.models.organization import Organization
from app.models.project import Project
from app.models.strategy import Strategy
from app.models.workspace_member import WorkspaceMember

_DB_URL = "sqlite+pysqlite:///:memory:"


@pytest.fixture()
def m72_engine():
    eng = create_engine(_DB_URL, connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture()
def m72_db(m72_engine):
    s = Session(m72_engine)
    yield s
    s.close()


@pytest.fixture()
def m72_strategy(m72_db):
    db = m72_db
    now = datetime.now(timezone.utc)
    org = Organization(name="Upload Org", slug="upload-org", created_at=now, updated_at=now)
    db.add(org)
    db.commit()
    db.refresh(org)
    proj = Project(organization_id=org.id, name="Upload Proj", slug="upload-proj",
                   created_at=now, updated_at=now)
    db.add(proj)
    db.commit()
    db.refresh(proj)
    strat = Strategy(project_id=proj.id, name="Upload Strat", slug="upload-strat",
                     asset_class="equity", status="active")
    db.add(strat)
    db.commit()
    db.refresh(strat)
    return strat


@pytest.fixture()
def m72_client(m72_db, m72_strategy):  # noqa: ARG001
    def _override():
        yield m72_db
    app.dependency_overrides[get_db] = _override
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.pop(get_db, None)


def _auth(tok):
    return {"Authorization": f"Bearer {tok}"}


def _make_user(client, db, role):
    email = f"{role}-{uuid.uuid4().hex[:8]}@test.com"
    r = client.post("/api/auth/register",
                    json={"email": email, "display_name": role, "password": "password123"})
    assert r.status_code == 200, r.text
    # Mark the email as verified so RBAC tests exercise role gating rather than
    # tripping the email-verification gate the ingest endpoint now enforces.
    user = db.query(AuthUser).filter(AuthUser.email == email).first()
    if user:
        user.email_verified = True
        user.email_verified_at = datetime.now(timezone.utc)
        db.commit()
    m = db.query(WorkspaceMember).filter(WorkspaceMember.email == email).first()
    if m:
        m.role = role
        db.commit()
    return r.json()["access_token"]


_BUNDLE = {
    "strategy_run": {
        "run_name": "web upload run",
        "run_type": "backtest",
        "metrics_json": {"sharpe": 1.1},
    }
}


class TestWebIngestRBAC:
    def test_owner_can_ingest(self, m72_client, m72_db, m72_strategy):
        token = _make_user(m72_client, m72_db, "owner")  # first user is owner anyway
        r = m72_client.post(f"/api/strategies/{m72_strategy.id}/evidence-bundles",
                        json=_BUNDLE, headers=_auth(token))
        assert r.status_code == 201, r.text
        assert r.json()["created_count"] >= 1

    def test_viewer_cannot_ingest(self, m72_client, m72_db, m72_strategy):
        _make_user(m72_client, m72_db, "owner")           # establish owner first
        viewer = _make_user(m72_client, m72_db, "viewer")  # second user forced to viewer
        r = m72_client.post(f"/api/strategies/{m72_strategy.id}/evidence-bundles",
                        json=_BUNDLE, headers=_auth(viewer))
        assert r.status_code == 403, r.text

    def test_no_token_still_ingests_local_dev(self, m72_client, m72_strategy):
        # SDK-style / local dev: no JWT -> permissive pseudo-owner -> allowed
        r = m72_client.post(f"/api/strategies/{m72_strategy.id}/evidence-bundles", json=_BUNDLE)
        assert r.status_code == 201, r.text

    def test_malformed_bundle_rejected(self, m72_client, m72_strategy):
        # run_type as wrong type / missing required run_name -> 422 validation
        bad = {"strategy_run": {"run_type": 12345}}
        r = m72_client.post(f"/api/strategies/{m72_strategy.id}/evidence-bundles", json=bad)
        assert r.status_code in (422, 400), r.text
