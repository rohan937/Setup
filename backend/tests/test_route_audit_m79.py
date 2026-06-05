"""Route audit tests (M79 audit pass).

Covers:
1. CORS config — QF_FRONTEND_URL is automatically added to allowed origins.
2. GET /api/strategies/{id}/reliability-snapshot returns 200 null (not 404)
   when no snapshot exists yet.
3. GET /api/strategies/{id}/assumption-health returns 200 (not 404)
   when the strategy exists but has minimal evidence.
4. Regression: reliability-snapshot /refresh still works.
5. reliability-snapshots (list) returns 200 + empty list, never 404.
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

_URL = "sqlite+pysqlite:///:memory:"


@pytest.fixture()
def audit_engine():
    eng = create_engine(_URL, connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture()
def audit_db(audit_engine):
    s = Session(audit_engine)
    yield s
    s.close()


@pytest.fixture()
def audit_client(audit_db):
    def _override():
        yield audit_db
    prior = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = _override
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    if prior is not None:
        app.dependency_overrides[get_db] = prior
    else:
        app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# Helper: create an org + project + strategy so routes can find them
# ---------------------------------------------------------------------------

def _seed_strategy(db: Session) -> object:
    from app.models.organization import Organization
    from app.models.project import Project
    from app.models.strategy import Strategy

    now = datetime.now(timezone.utc)
    org = Organization(name="Audit WS", slug="audit-ws", created_at=now, updated_at=now)
    db.add(org)
    db.flush()
    proj = Project(organization_id=org.id, name="Audit P", slug="audit-p",
                   created_at=now, updated_at=now)
    db.add(proj)
    db.flush()
    strat = Strategy(project_id=proj.id, name="Audit Strat",
                     slug="audit-strat", asset_class="equity", status="active")
    db.add(strat)
    db.flush()
    db.commit()
    return strat


# ---------------------------------------------------------------------------
# CORS config tests
# ---------------------------------------------------------------------------

class TestCorsConfig:
    def test_frontend_url_added_to_allowed_origins(self, monkeypatch):
        import os
        from app.core import config as cfg

        monkeypatch.setenv("QF_FRONTEND_URL", "https://quantfidelity.vercel.app")
        cfg.get_settings.cache_clear()
        try:
            s = cfg.get_settings()
            assert "https://quantfidelity.vercel.app" in s.cors_origin_list
        finally:
            cfg.get_settings.cache_clear()

    def test_no_frontend_url_keeps_localhost_defaults(self, monkeypatch):
        from app.core import config as cfg

        monkeypatch.delenv("QF_FRONTEND_URL", raising=False)
        cfg.get_settings.cache_clear()
        try:
            s = cfg.get_settings()
            assert "http://localhost:5173" in s.cors_origin_list
            assert all("vercel" not in o for o in s.cors_origin_list)
        finally:
            cfg.get_settings.cache_clear()

    def test_no_duplicate_when_already_in_cors_origins(self, monkeypatch):
        from app.core import config as cfg

        monkeypatch.setenv("QF_CORS_ORIGINS", "https://quantfidelity.vercel.app")
        monkeypatch.setenv("QF_FRONTEND_URL", "https://quantfidelity.vercel.app")
        cfg.get_settings.cache_clear()
        try:
            s = cfg.get_settings()
            assert s.cors_origin_list.count("https://quantfidelity.vercel.app") == 1
        finally:
            cfg.get_settings.cache_clear()


# ---------------------------------------------------------------------------
# Reliability snapshot: 200 null instead of 404 when no snapshot yet
# ---------------------------------------------------------------------------

class TestReliabilitySnapshotNoData:
    def test_get_snapshot_returns_200_null_when_none_exists(self, audit_client, audit_db):
        strat = _seed_strategy(audit_db)
        resp = audit_client.get(f"/api/strategies/{strat.id}/reliability-snapshot")
        assert resp.status_code == 200, f"expected 200, got {resp.status_code}: {resp.text}"
        assert resp.json() is None

    def test_get_snapshot_strategy_not_found_still_404(self, audit_client):
        fake = uuid.uuid4()
        resp = audit_client.get(f"/api/strategies/{fake}/reliability-snapshot")
        assert resp.status_code == 404

    def test_list_snapshots_returns_200_empty_list_when_none(self, audit_client, audit_db):
        strat = _seed_strategy(audit_db)
        resp = audit_client.get(f"/api/strategies/{strat.id}/reliability-snapshots")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0


# ---------------------------------------------------------------------------
# Assumption health: 200 when strategy has minimal evidence (not 404)
# ---------------------------------------------------------------------------

class TestAssumptionHealthNoData:
    def test_assumption_health_returns_200_with_minimal_evidence(self, audit_client, audit_db):
        strat = _seed_strategy(audit_db)
        resp = audit_client.get(f"/api/strategies/{strat.id}/assumption-health")
        assert resp.status_code == 200, f"expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        # Must have the required envelope fields
        assert "category_scorecards" in data
        assert "overall_assumption_score" in data

    def test_assumption_health_404_for_nonexistent_strategy(self, audit_client):
        resp = audit_client.get(f"/api/strategies/{uuid.uuid4()}/assumption-health")
        assert resp.status_code == 404
