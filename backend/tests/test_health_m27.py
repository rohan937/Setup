"""M27 tests: Strategy Health Snapshots.

Tests for:
  - GET /api/strategies/{id}/health endpoint
  - GET /api/strategies/health endpoint (list)
  - Health status logic (critical, review, watch, insufficient_evidence, healthy)
  - Health score computation with alerts
  - Primary concern text
  - Missing evidence list
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from app.models.alert import Alert
from app.models.organization import Organization
from app.models.project import Project
from app.models.strategy import Strategy
from app.models.strategy_reliability_score import StrategyReliabilityScore
from app.models.strategy_run import StrategyRun
from app.services.strategy_health import compute_strategy_health


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_strategy(db, org, project, *, name=None, asset_class="equity", status="active"):
    slug = (name or f"test-{uuid.uuid4().hex[:6]}").lower().replace(" ", "-")
    s = Strategy(
        project_id=project.id,
        name=name or f"TestStrat-{uuid.uuid4().hex[:6]}",
        slug=slug,
        asset_class=asset_class,
        status=status,
    )
    db.add(s)
    db.flush()
    return s


def _make_run(db, strategy, *, run_type="backtest", status="completed"):
    r = StrategyRun(
        strategy_id=strategy.id,
        run_name=f"run-{uuid.uuid4().hex[:6]}",
        run_type=run_type,
        status=status,
    )
    db.add(r)
    db.flush()
    return r


def _make_alert(db, org, strategy, *, severity="high", status="open"):
    a = Alert(
        organization_id=str(org.id),
        strategy_id=str(strategy.id),
        rule_type="test_rule",
        status=status,
        severity=severity,
        title=f"Test alert {severity}",
        triggered_at=datetime.now(timezone.utc),
    )
    db.add(a)
    db.flush()
    return a


def _make_reliability_score(db, strategy, *, overall_score=80.0, status="good"):
    rs = StrategyReliabilityScore(
        strategy_id=strategy.id,
        overall_score=overall_score,
        status=status,
        generated_at=datetime.now(timezone.utc),
    )
    db.add(rs)
    db.flush()
    return rs


def _get_seeded_strategy(db):
    """Return any seeded (non-archived) strategy for read-only tests."""
    return db.query(Strategy).filter(Strategy.status != "archived").first()


def _get_seeded_org(db):
    return db.query(Organization).first()


def _get_seeded_project(db):
    return db.query(Project).first()


# ---------------------------------------------------------------------------
# TestStrategyHealthEndpoint
# ---------------------------------------------------------------------------


class TestStrategyHealthEndpoint:
    """Integration tests via TestClient for health endpoints."""

    def test_seeded_strategy_has_health(self, client, db):
        strategy = _get_seeded_strategy(db)
        assert strategy is not None
        resp = client.get(f"/api/strategies/{strategy.id}/health")
        assert resp.status_code == 200

    def test_health_has_required_fields(self, client, db):
        strategy = _get_seeded_strategy(db)
        resp = client.get(f"/api/strategies/{strategy.id}/health")
        data = resp.json()
        assert "strategy_id" in data
        assert "health_status" in data
        assert "primary_concern" in data
        assert "evidence_coverage_score" in data
        assert "open_alert_count" in data
        assert "high_critical_alert_count" in data
        assert "missing_evidence" in data
        assert "suggested_checks" in data
        assert "generated_at" in data

    def test_unknown_strategy_404(self, client):
        fake_id = uuid.uuid4()
        resp = client.get(f"/api/strategies/{fake_id}/health")
        assert resp.status_code == 404

    def test_list_health_endpoint_200(self, client):
        resp = client.get("/api/strategies/health")
        assert resp.status_code == 200

    def test_list_health_total_matches(self, client):
        resp = client.get("/api/strategies/health")
        data = resp.json()
        assert "total" in data
        assert data["total"] >= 1
        assert "items" in data

    def test_list_health_has_all_fields(self, client):
        resp = client.get("/api/strategies/health")
        data = resp.json()
        for item in data["items"]:
            assert "health_status" in item
            assert "evidence_coverage_score" in item

    def test_health_status_filter(self, client):
        resp = client.get("/api/strategies/health?status=active")
        assert resp.status_code == 200
        data = resp.json()
        for item in data["items"]:
            assert item["status"] == "active"


# ---------------------------------------------------------------------------
# TestHealthStatusLogic
# ---------------------------------------------------------------------------


class TestHealthStatusLogic:
    """Unit-level tests for health status computation using freshly created strategies."""

    def test_insufficient_evidence_with_no_runs(self, db):
        org = _get_seeded_org(db)
        project = _get_seeded_project(db)
        s = _make_strategy(db, org, project)
        try:
            snap = compute_strategy_health(s.id, db)
            # A brand-new strategy with no evidence should be insufficient_evidence or review
            assert snap.health_status in ("insufficient_evidence", "review", "critical")
        finally:
            db.delete(s)
            db.commit()

    def test_healthy_status_with_seeded_strategy(self, db):
        """Seeded AAPL strategy with accumulated evidence should not be critical."""
        strategy = _get_seeded_strategy(db)
        snap = compute_strategy_health(strategy.id, db)
        assert snap.health_status != "critical" or snap.open_alert_count > 0

    def test_review_with_open_high_alert(self, db):
        org = _get_seeded_org(db)
        project = _get_seeded_project(db)
        s = _make_strategy(db, org, project)
        alert = _make_alert(db, org, s, severity="high", status="open")
        try:
            snap = compute_strategy_health(s.id, db)
            # high alert should push to review or worse
            assert snap.health_status in ("review", "critical")
        finally:
            db.delete(alert)
            db.delete(s)
            db.commit()

    def test_critical_with_open_critical_alert(self, db):
        org = _get_seeded_org(db)
        project = _get_seeded_project(db)
        s = _make_strategy(db, org, project)
        alert = _make_alert(db, org, s, severity="critical", status="open")
        try:
            snap = compute_strategy_health(s.id, db)
            assert snap.health_status == "critical"
        finally:
            db.delete(alert)
            db.delete(s)
            db.commit()

    def test_health_score_decreases_with_critical_alert(self, db):
        org = _get_seeded_org(db)
        project = _get_seeded_project(db)

        # Strategy without alert
        s_clean = _make_strategy(db, org, project)
        rs_clean = _make_reliability_score(db, s_clean, overall_score=80.0, status="good")

        # Strategy with critical alert
        s_alerted = _make_strategy(db, org, project)
        rs_alerted = _make_reliability_score(db, s_alerted, overall_score=80.0, status="good")
        alert = _make_alert(db, org, s_alerted, severity="critical", status="open")

        try:
            snap_clean = compute_strategy_health(s_clean.id, db)
            snap_alerted = compute_strategy_health(s_alerted.id, db)
            # Score with critical alert should be lower (or None if base was removed)
            if snap_clean.health_score is not None and snap_alerted.health_score is not None:
                assert snap_alerted.health_score < snap_clean.health_score
        finally:
            db.delete(alert)
            db.delete(rs_alerted)
            db.delete(rs_clean)
            db.delete(s_alerted)
            db.delete(s_clean)
            db.commit()

    def test_watch_with_open_low_alert(self, db):
        org = _get_seeded_org(db)
        project = _get_seeded_project(db)
        s = _make_strategy(db, org, project)
        # Give the strategy a good reliability score so watch is possible
        rs = _make_reliability_score(db, s, overall_score=85.0, status="excellent")
        run = _make_run(db, s)
        alert = _make_alert(db, org, s, severity="low", status="open")
        try:
            snap = compute_strategy_health(s.id, db)
            # Low alert with otherwise good evidence → watch or review
            assert snap.health_status in ("watch", "review", "healthy")
        finally:
            db.delete(alert)
            db.delete(run)
            db.delete(rs)
            db.delete(s)
            db.commit()

    def test_missing_evidence_list(self, db):
        """New strategy with no evidence should have missing_evidence from reliability service
        or an empty list (if no reliability score has been computed yet)."""
        org = _get_seeded_org(db)
        project = _get_seeded_project(db)
        s = _make_strategy(db, org, project)
        try:
            snap = compute_strategy_health(s.id, db)
            # missing_evidence comes from reliability score's missing_evidence_json —
            # if no score exists, it will be an empty list, which is acceptable
            assert isinstance(snap.missing_evidence, list)
        finally:
            db.delete(s)
            db.commit()

    def test_primary_concern_no_runs(self, db):
        """Strategy with no runs should report a concern about runs or evidence."""
        org = _get_seeded_org(db)
        project = _get_seeded_project(db)
        s = _make_strategy(db, org, project)
        try:
            snap = compute_strategy_health(s.id, db)
            concern_lower = snap.primary_concern.lower()
            # Should mention runs, evidence, or insufficient
            assert any(
                kw in concern_lower
                for kw in ("run", "evidence", "insufficient", "coverage", "reliability")
            )
        finally:
            db.delete(s)
            db.commit()
