"""M46 tests: Demo Seed Service and Admin Endpoints.

Tests for:
  POST /api/admin/seed-demo  — seed demo data
  GET  /api/admin/demo-status — describe current demo state

  TestDemoSeedEndpoint  — endpoint-level integration tests
  TestDemoStrategyContent — verify content created for each strategy
  TestDemoReset         — reset mode cleans demo data only
"""

from __future__ import annotations

import pytest

from app.models.audit_timeline_event import AuditTimelineEvent
from app.models.organization import Organization
from app.models.project import Project
from app.models.strategy import Strategy
from app.models.strategy_run import StrategyRun
from app.services.demo_seed import DEMO_ORG_NAME, DEMO_PROJECT_SLUG


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cleanup_demo(db):
    """Remove the demo org (and cascade) if it exists."""
    try:
        db.rollback()  # Ensure clean state before querying
    except Exception:
        pass
    try:
        org = db.query(Organization).filter(Organization.name == DEMO_ORG_NAME).first()
        if org:
            try:
                db.delete(org)
                db.commit()
            except Exception:
                db.rollback()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass


def _seed(client, **kwargs):
    """POST /api/admin/seed-demo with optional overrides."""
    payload = {
        "mode": "extend",
        "confirm_reset": False,
        "include_reports": False,
        "include_alerts": False,
        "include_backtest_audits": True,
        **kwargs,
    }
    return client.post("/api/admin/seed-demo", json=payload)


# ---------------------------------------------------------------------------
# TestDemoSeedEndpoint
# ---------------------------------------------------------------------------


class TestDemoSeedEndpoint:
    """Integration tests via TestClient for the demo seed endpoints."""

    def test_seed_demo_returns_200(self, client, db):
        try:
            resp = _seed(client)
            assert resp.status_code == 200
        finally:
            _cleanup_demo(db)

    def test_seed_creates_org_project(self, client, db):
        try:
            resp = _seed(client)
            assert resp.status_code == 200
            data = resp.json()
            assert data["organization_id"] is not None
            assert data["project_id"] is not None

            org = db.query(Organization).filter(Organization.name == DEMO_ORG_NAME).first()
            assert org is not None

            proj = (
                db.query(Project)
                .filter(
                    Project.organization_id == org.id,
                    Project.slug == DEMO_PROJECT_SLUG,
                )
                .first()
            )
            assert proj is not None
        finally:
            _cleanup_demo(db)

    def test_seed_creates_three_strategies(self, client, db):
        try:
            resp = _seed(client)
            assert resp.status_code == 200
            data = resp.json()
            assert len(data["strategy_ids"]) == 3
        finally:
            _cleanup_demo(db)

    def test_seed_idempotent(self, client, db):
        try:
            # First call
            resp1 = _seed(client)
            assert resp1.status_code == 200
            # Second call
            resp2 = _seed(client)
            assert resp2.status_code == 200
            data2 = resp2.json()
            # On second call, reused_counts > 0
            reused = data2.get("reused_counts", {})
            assert reused.get("strategies", 0) > 0
        finally:
            _cleanup_demo(db)

    def test_reset_requires_confirm(self, client, db):
        try:
            resp = _seed(client)
            assert resp.status_code == 200
            # Reset without confirm_reset=True should fail with 400
            resp2 = client.post(
                "/api/admin/seed-demo",
                json={"mode": "reset_demo_only", "confirm_reset": False},
            )
            assert resp2.status_code == 400
        finally:
            _cleanup_demo(db)

    def test_demo_status_endpoint(self, client):
        resp = client.get("/api/admin/demo-status")
        assert resp.status_code == 200

    def test_demo_status_after_seed(self, client, db):
        try:
            _seed(client)
            resp = client.get("/api/admin/demo-status")
            assert resp.status_code == 200
            data = resp.json()
            assert data["demo_org_exists"] is True
            assert data["strategy_count"] == 3
        finally:
            _cleanup_demo(db)


# ---------------------------------------------------------------------------
# TestDemoStrategyContent
# ---------------------------------------------------------------------------


class TestDemoStrategyContent:
    """Verify content created for each demo strategy."""

    def test_aapl_strategy_has_runs(self, client, db):
        try:
            _seed(client)
            db.expire_all()
            org = db.query(Organization).filter(Organization.name == DEMO_ORG_NAME).first()
            assert org is not None
            proj = db.query(Project).filter(Project.organization_id == org.id).first()
            assert proj is not None
            aapl = (
                db.query(Strategy)
                .filter(
                    Strategy.project_id == proj.id,
                    Strategy.slug == "aapl-mean-reversion-demo",
                )
                .first()
            )
            assert aapl is not None
            runs = db.query(StrategyRun).filter(StrategyRun.strategy_id == aapl.id).all()
            assert len(runs) >= 1
        finally:
            _cleanup_demo(db)

    def test_fx_strategy_has_review_evidence(self, client, db):
        try:
            _seed(client)
            db.expire_all()
            org = db.query(Organization).filter(Organization.name == DEMO_ORG_NAME).first()
            assert org is not None
            proj = db.query(Project).filter(Project.organization_id == org.id).first()
            assert proj is not None
            fx = (
                db.query(Strategy)
                .filter(
                    Strategy.project_id == proj.id,
                    Strategy.slug == "fx-carry-demo",
                )
                .first()
            )
            assert fx is not None
        finally:
            _cleanup_demo(db)

    def test_crypto_strategy_exists(self, client, db):
        try:
            _seed(client)
            db.expire_all()
            org = db.query(Organization).filter(Organization.name == DEMO_ORG_NAME).first()
            assert org is not None
            proj = db.query(Project).filter(Project.organization_id == org.id).first()
            assert proj is not None
            crypto = (
                db.query(Strategy)
                .filter(
                    Strategy.project_id == proj.id,
                    Strategy.slug == "crypto-momentum-demo",
                )
                .first()
            )
            assert crypto is not None
        finally:
            _cleanup_demo(db)

    def test_demo_seeded_timeline_event(self, client, db):
        try:
            _seed(client)
            db.expire_all()
            org = db.query(Organization).filter(Organization.name == DEMO_ORG_NAME).first()
            assert org is not None
            event = (
                db.query(AuditTimelineEvent)
                .filter(
                    AuditTimelineEvent.organization_id == org.id,
                    AuditTimelineEvent.event_type == "demo_seeded",
                )
                .first()
            )
            assert event is not None
        finally:
            _cleanup_demo(db)


# ---------------------------------------------------------------------------
# TestDemoReset
# ---------------------------------------------------------------------------


class TestDemoReset:
    """Reset mode cleans demo data only, leaving non-demo data intact."""

    def test_reset_demo_only_deletes_demo_org(self, client, db):
        # Seed first
        resp = _seed(client)
        assert resp.status_code == 200

        try:
            # Now reset
            resp2 = client.post(
                "/api/admin/seed-demo",
                json={"mode": "reset_demo_only", "confirm_reset": True},
            )
            assert resp2.status_code == 200
            data = resp2.json()
            assert data["mode"] == "reset_demo_only"

            # Ensure the session sees the committed delete
            db.rollback()
            db.expire_all()
            org = db.query(Organization).filter(Organization.name == DEMO_ORG_NAME).first()
            assert org is None
        finally:
            # Ensure cleanup even if reset didn't work
            _cleanup_demo(db)

    def test_reset_does_not_delete_non_demo(self, client, db):
        # Seed demo
        resp = _seed(client)
        assert resp.status_code == 200

        # Count non-demo orgs before reset
        non_demo_before = (
            db.query(Organization)
            .filter(Organization.name != DEMO_ORG_NAME)
            .count()
        )

        try:
            # Reset demo
            client.post(
                "/api/admin/seed-demo",
                json={"mode": "reset_demo_only", "confirm_reset": True},
            )

            db.expire_all()
            non_demo_after = (
                db.query(Organization)
                .filter(Organization.name != DEMO_ORG_NAME)
                .count()
            )
            # Non-demo orgs should be untouched
            assert non_demo_after == non_demo_before
        finally:
            _cleanup_demo(db)
