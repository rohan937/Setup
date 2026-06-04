"""M78 tests: Advanced demo strategy seed.

Covers:
  - service creates the strategy with a full evidence trail
  - idempotency: a second run does not duplicate the strategy
  - created strategy has multiple runs + reports + audits + alerts
  - endpoint POST /api/admin/demo/advanced-strategy requires can_seed_demo
  - endpoint response contains strategy_id + counts

Uses an isolated in-memory DB so the shared session DB is untouched.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 — register ORM metadata
from app.db.base import Base
from app.db.session import get_db
from app.main import app

_DB_URL = "sqlite+pysqlite:///:memory:"


@pytest.fixture()
def iso_engine():
    engine = create_engine(
        _DB_URL, connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture()
def iso_db(iso_engine):
    session = Session(iso_engine)
    yield session
    session.close()


# ---------------------------------------------------------------------------
# Service-level tests
# ---------------------------------------------------------------------------

class TestSeedService:
    def test_creates_strategy(self, iso_db):
        from app.services.advanced_demo_seed import seed_advanced_demo_strategy, STRATEGY_SLUG
        from app.models.strategy import Strategy

        res = seed_advanced_demo_strategy(iso_db)
        assert res["status"] == "created"
        assert res["strategy_id"]
        s = iso_db.query(Strategy).filter(Strategy.slug == STRATEGY_SLUG).first()
        assert s is not None
        assert s.name == "US Equity Quality-Momentum Rotation"
        assert s.asset_class == "equity"

    def test_has_multiple_runs_and_versions(self, iso_db):
        from app.services.advanced_demo_seed import seed_advanced_demo_strategy
        from app.models.strategy import Strategy
        from app.models.strategy_run import StrategyRun
        from app.models.strategy_version import StrategyVersion

        seed_advanced_demo_strategy(iso_db)
        s = iso_db.query(Strategy).first()
        assert iso_db.query(StrategyVersion).filter_by(strategy_id=s.id).count() == 4
        assert iso_db.query(StrategyRun).filter_by(strategy_id=s.id).count() >= 4

    def test_has_reports_audits_alerts(self, iso_db):
        from app.services.advanced_demo_seed import seed_advanced_demo_strategy
        from app.models.strategy import Strategy
        from app.models.report import Report
        from app.models.alert import Alert
        from app.models.backtest_audit import BacktestAudit
        from app.models.strategy_run import StrategyRun

        seed_advanced_demo_strategy(iso_db)
        s = iso_db.query(Strategy).first()
        assert iso_db.query(Report).filter_by(strategy_id=s.id).count() >= 1
        assert iso_db.query(Alert).filter(Alert.strategy_id == s.id.hex).count() >= 5
        audit_count = (
            iso_db.query(BacktestAudit)
            .join(StrategyRun, BacktestAudit.strategy_run_id == StrategyRun.id)
            .filter(StrategyRun.strategy_id == s.id)
            .count()
        )
        assert audit_count >= 1

    def test_has_review_cases_with_mixed_status(self, iso_db):
        from app.services.advanced_demo_seed import seed_advanced_demo_strategy
        from app.models.strategy import Strategy
        from app.models.review_case import ResearchReviewCase

        seed_advanced_demo_strategy(iso_db)
        s = iso_db.query(Strategy).first()
        cases = iso_db.query(ResearchReviewCase).filter_by(strategy_id=s.id.hex).all()
        assert len(cases) == 3
        statuses = {c.status for c in cases}
        # At least one resolved and one still open.
        assert "resolved" in statuses
        assert "open" in statuses

    def test_idempotent_no_duplicate_strategy(self, iso_db):
        from app.services.advanced_demo_seed import seed_advanced_demo_strategy, STRATEGY_SLUG
        from app.models.strategy import Strategy
        from app.models.strategy_run import StrategyRun

        r1 = seed_advanced_demo_strategy(iso_db)
        r2 = seed_advanced_demo_strategy(iso_db)
        assert r1["status"] == "created"
        assert r2["status"] == "refreshed"
        # Exactly one strategy, run count unchanged.
        assert iso_db.query(Strategy).filter(Strategy.slug == STRATEGY_SLUG).count() == 1
        s = iso_db.query(Strategy).first()
        runs_after = iso_db.query(StrategyRun).filter_by(strategy_id=s.id).count()
        r3 = seed_advanced_demo_strategy(iso_db)
        assert iso_db.query(StrategyRun).filter_by(strategy_id=s.id).count() == runs_after
        assert r3["total_artifacts"] == r2["total_artifacts"]

    def test_counts_present(self, iso_db):
        from app.services.advanced_demo_seed import seed_advanced_demo_strategy

        res = seed_advanced_demo_strategy(iso_db)
        for key in ("versions", "runs", "audits", "reports", "alerts", "review_cases"):
            assert key in res["counts"]
        assert res["total_artifacts"] > 0
        assert "not real trading" in res["disclaimer"].lower()


# ---------------------------------------------------------------------------
# Endpoint RBAC tests (isolated client)
# ---------------------------------------------------------------------------

@pytest.fixture()
def iso_setup(iso_db):
    from app.models.organization import Organization
    from app.models.project import Project
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    org = Organization(name="M78 WS", slug="m78-ws", created_at=now, updated_at=now)
    iso_db.add(org)
    iso_db.commit()
    proj = Project(organization_id=org.id, name="M78 P", slug="m78-p",
                   created_at=now, updated_at=now)
    iso_db.add(proj)
    iso_db.commit()
    return org, proj


@pytest.fixture()
def iso_client(iso_db, iso_setup):  # noqa: ARG001
    def _override():
        yield iso_db
    prior = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = _override
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    if prior is not None:
        app.dependency_overrides[get_db] = prior
    else:
        app.dependency_overrides.pop(get_db, None)


def _viewer_token(client, db) -> str:
    from app.models.workspace_member import WorkspaceMember
    client.post("/api/auth/register", json={
        "email": f"owner-{uuid.uuid4().hex[:6]}@test.com",
        "display_name": "Owner", "password": "password123",
    })
    email = f"viewer-{uuid.uuid4().hex[:8]}@test.com"
    resp = client.post("/api/auth/register", json={
        "email": email, "display_name": "Viewer", "password": "password123",
    })
    assert resp.status_code == 200, resp.text
    member = db.query(WorkspaceMember).filter(WorkspaceMember.email == email).first()
    member.role = "viewer"
    db.commit()
    return resp.json()["access_token"]


class TestEndpoint:
    def test_endpoint_seeds_and_returns_counts(self, iso_client):
        # No token → permissive pseudo-owner in local dev.
        resp = iso_client.post("/api/admin/demo/advanced-strategy")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["strategy_id"]
        assert body["strategy_name"] == "US Equity Quality-Momentum Rotation"
        assert body["counts"]["runs"] >= 4
        assert body["status"] in ("created", "refreshed")

    def test_viewer_cannot_seed(self, iso_client, iso_db):
        token = _viewer_token(iso_client, iso_db)
        resp = iso_client.post(
            "/api/admin/demo/advanced-strategy",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403, resp.text
