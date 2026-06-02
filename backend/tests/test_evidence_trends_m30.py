"""M30 tests: Evidence Trends endpoint.

Tests for:
  - GET /api/strategies/{id}/evidence-trends endpoint
  - Trend direction computation (improving, deteriorating, flat, insufficient_history)
  - Trend summary messages
  - Suggested checks when no evidence
  - No AuditTimelineEvent side effects
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from app.models.audit_timeline_event import AuditTimelineEvent
from app.models.backtest_audit import BacktestAudit
from app.models.dataset import Dataset
from app.models.dataset_snapshot import DatasetSnapshot
from app.models.organization import Organization
from app.models.project import Project
from app.models.signal_snapshot import SignalSnapshot
from app.models.strategy import Strategy
from app.models.strategy_reliability_score import StrategyReliabilityScore
from app.models.strategy_run import StrategyRun


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


def _make_reliability_score(db, strategy, overall_score, *, status="good"):
    s = StrategyReliabilityScore(
        strategy_id=strategy.id,
        overall_score=overall_score,
        status=status,
        generated_at=datetime.now(timezone.utc),
    )
    db.add(s)
    db.flush()
    return s


def _make_backtest_audit(db, run, *, trust_score=80):
    a = BacktestAudit(
        strategy_run_id=run.id,
        trust_score=trust_score,
        overall_status="good",
        summary="Test audit",
    )
    db.add(a)
    db.flush()
    return a


def _make_signal_snapshot(db, strategy, *, quality_score=80, label=None):
    snap = SignalSnapshot(
        strategy_id=strategy.id,
        label=label or f"sig-{uuid.uuid4().hex[:6]}",
        signal_name="test_signal",
        rows_json=[],
        row_count=0,
        symbol_count=0,
        symbols_json=[],
        missing_signal_count=0,
        signal_value_count=0,
        signal_hash=uuid.uuid4().hex,
        quality_score=quality_score,
    )
    db.add(snap)
    db.flush()
    return snap


def _get_seeded_org(db):
    return db.query(Organization).first()


def _get_seeded_project(db):
    return db.query(Project).first()


# ---------------------------------------------------------------------------
# TestEvidenceTrendsEndpoint
# ---------------------------------------------------------------------------


class TestEvidenceTrendsEndpoint:
    """Integration tests via TestClient for evidence-trends endpoint."""

    def test_endpoint_returns_200(self, client, db):
        org = _get_seeded_org(db)
        project = _get_seeded_project(db)
        strategy = _make_strategy(db, org, project)
        db.commit()

        try:
            resp = client.get(f"/api/strategies/{strategy.id}/evidence-trends")
            assert resp.status_code == 200
        finally:
            db.delete(strategy)
            db.commit()

    def test_response_has_required_fields(self, client, db):
        org = _get_seeded_org(db)
        project = _get_seeded_project(db)
        strategy = _make_strategy(db, org, project)
        db.commit()

        try:
            resp = client.get(f"/api/strategies/{strategy.id}/evidence-trends")
            assert resp.status_code == 200
            data = resp.json()
            assert "reliability_trend" in data
            assert "data_health_trend" in data
            assert "backtest_trust_trend" in data
            assert "signal_quality_trend" in data
            assert "strategy_id" in data
            assert "strategy_name" in data
            assert "overall_summary" in data
            assert "suggested_checks" in data
        finally:
            db.delete(strategy)
            db.commit()

    def test_endpoint_returns_404_for_unknown(self, client):
        fake_id = uuid.uuid4()
        resp = client.get(f"/api/strategies/{fake_id}/evidence-trends")
        assert resp.status_code == 404

    def test_trend_fields_present(self, client, db):
        org = _get_seeded_org(db)
        project = _get_seeded_project(db)
        strategy = _make_strategy(db, org, project)
        db.commit()

        try:
            resp = client.get(f"/api/strategies/{strategy.id}/evidence-trends")
            assert resp.status_code == 200
            data = resp.json()
            for key in ["reliability_trend", "data_health_trend", "backtest_trust_trend", "signal_quality_trend"]:
                trend = data[key]
                assert "direction" in trend
                assert "point_count" in trend
                assert "deterministic_summary" in trend
        finally:
            db.delete(strategy)
            db.commit()


# ---------------------------------------------------------------------------
# TestTrendDirection
# ---------------------------------------------------------------------------


class TestTrendDirection:
    """Unit-level tests for trend direction computation via the endpoint."""

    def test_reliability_insufficient_no_scores(self, client, db):
        org = _get_seeded_org(db)
        project = _get_seeded_project(db)
        strategy = _make_strategy(db, org, project)
        db.commit()

        try:
            resp = client.get(f"/api/strategies/{strategy.id}/evidence-trends")
            assert resp.status_code == 200
            trend = resp.json()["reliability_trend"]
            assert trend["direction"] == "insufficient_history"
            assert trend["point_count"] == 0
        finally:
            db.delete(strategy)
            db.commit()

    def test_reliability_insufficient_one_score(self, client, db):
        org = _get_seeded_org(db)
        project = _get_seeded_project(db)
        strategy = _make_strategy(db, org, project)
        score = _make_reliability_score(db, strategy, 75)
        db.commit()

        try:
            resp = client.get(f"/api/strategies/{strategy.id}/evidence-trends")
            assert resp.status_code == 200
            trend = resp.json()["reliability_trend"]
            assert trend["direction"] == "insufficient_history"
            assert trend["point_count"] == 1
        finally:
            db.delete(score)
            db.flush()
            db.delete(strategy)
            db.commit()

    def test_reliability_improving(self, client, db):
        org = _get_seeded_org(db)
        project = _get_seeded_project(db)
        strategy = _make_strategy(db, org, project)
        s1 = _make_reliability_score(db, strategy, 60)
        s2 = _make_reliability_score(db, strategy, 80)  # delta = +20 > 2
        db.commit()

        try:
            resp = client.get(f"/api/strategies/{strategy.id}/evidence-trends")
            assert resp.status_code == 200
            trend = resp.json()["reliability_trend"]
            assert trend["direction"] == "improving"
        finally:
            for obj in [s2, s1]:
                db.delete(obj)
            db.flush()
            db.delete(strategy)
            db.commit()

    def test_reliability_deteriorating(self, client, db):
        org = _get_seeded_org(db)
        project = _get_seeded_project(db)
        strategy = _make_strategy(db, org, project)
        s1 = _make_reliability_score(db, strategy, 80)
        s2 = _make_reliability_score(db, strategy, 55)  # delta = -25 < -2
        db.commit()

        try:
            resp = client.get(f"/api/strategies/{strategy.id}/evidence-trends")
            assert resp.status_code == 200
            trend = resp.json()["reliability_trend"]
            assert trend["direction"] == "deteriorating"
        finally:
            for obj in [s2, s1]:
                db.delete(obj)
            db.flush()
            db.delete(strategy)
            db.commit()

    def test_reliability_flat(self, client, db):
        org = _get_seeded_org(db)
        project = _get_seeded_project(db)
        strategy = _make_strategy(db, org, project)
        s1 = _make_reliability_score(db, strategy, 75)
        s2 = _make_reliability_score(db, strategy, 76)  # delta = +1, within ±2
        db.commit()

        try:
            resp = client.get(f"/api/strategies/{strategy.id}/evidence-trends")
            assert resp.status_code == 200
            trend = resp.json()["reliability_trend"]
            assert trend["direction"] == "flat"
        finally:
            for obj in [s2, s1]:
                db.delete(obj)
            db.flush()
            db.delete(strategy)
            db.commit()

    def test_backtest_trust_trend_from_audits(self, client, db):
        org = _get_seeded_org(db)
        project = _get_seeded_project(db)
        strategy = _make_strategy(db, org, project)
        run1 = _make_run(db, strategy)
        run2 = _make_run(db, strategy)
        a1 = _make_backtest_audit(db, run1, trust_score=50)
        a2 = _make_backtest_audit(db, run2, trust_score=90)  # improving
        db.commit()

        try:
            resp = client.get(f"/api/strategies/{strategy.id}/evidence-trends")
            assert resp.status_code == 200
            trend = resp.json()["backtest_trust_trend"]
            assert trend["direction"] == "improving"
            assert trend["point_count"] == 2
        finally:
            for obj in [a2, a1, run2, run1]:
                db.delete(obj)
            db.flush()
            db.delete(strategy)
            db.commit()

    def test_signal_quality_trend_from_snapshots(self, client, db):
        org = _get_seeded_org(db)
        project = _get_seeded_project(db)
        strategy = _make_strategy(db, org, project)
        snap1 = _make_signal_snapshot(db, strategy, quality_score=40)
        snap2 = _make_signal_snapshot(db, strategy, quality_score=90)  # improving
        db.commit()

        try:
            resp = client.get(f"/api/strategies/{strategy.id}/evidence-trends")
            assert resp.status_code == 200
            trend = resp.json()["signal_quality_trend"]
            assert trend["direction"] == "improving"
            assert trend["point_count"] == 2
        finally:
            for obj in [snap2, snap1]:
                db.delete(obj)
            db.flush()
            db.delete(strategy)
            db.commit()

    def test_limit_per_series(self, client, db):
        org = _get_seeded_org(db)
        project = _get_seeded_project(db)
        strategy = _make_strategy(db, org, project)
        scores = [_make_reliability_score(db, strategy, 70 + i) for i in range(5)]
        db.commit()

        try:
            resp = client.get(
                f"/api/strategies/{strategy.id}/evidence-trends?limit_per_series=1"
            )
            assert resp.status_code == 200
            trend = resp.json()["reliability_trend"]
            assert trend["point_count"] <= 1
            assert len(trend["points"]) <= 1
        finally:
            for obj in reversed(scores):
                db.delete(obj)
            db.flush()
            db.delete(strategy)
            db.commit()


# ---------------------------------------------------------------------------
# TestTrendSummary
# ---------------------------------------------------------------------------


class TestTrendSummary:
    """Tests for deterministic_summary messages and suggested_checks."""

    def test_summary_mentions_improving(self, client, db):
        org = _get_seeded_org(db)
        project = _get_seeded_project(db)
        strategy = _make_strategy(db, org, project)
        s1 = _make_reliability_score(db, strategy, 50)
        s2 = _make_reliability_score(db, strategy, 85)
        db.commit()

        try:
            resp = client.get(f"/api/strategies/{strategy.id}/evidence-trends")
            assert resp.status_code == 200
            summary = resp.json()["reliability_trend"]["deterministic_summary"]
            assert "improved" in summary.lower()
        finally:
            for obj in [s2, s1]:
                db.delete(obj)
            db.flush()
            db.delete(strategy)
            db.commit()

    def test_summary_mentions_deteriorating(self, client, db):
        org = _get_seeded_org(db)
        project = _get_seeded_project(db)
        strategy = _make_strategy(db, org, project)
        s1 = _make_reliability_score(db, strategy, 85)
        s2 = _make_reliability_score(db, strategy, 50)
        db.commit()

        try:
            resp = client.get(f"/api/strategies/{strategy.id}/evidence-trends")
            assert resp.status_code == 200
            summary = resp.json()["reliability_trend"]["deterministic_summary"]
            assert "deteriorated" in summary.lower()
        finally:
            for obj in [s2, s1]:
                db.delete(obj)
            db.flush()
            db.delete(strategy)
            db.commit()

    def test_summary_for_insufficient(self, client, db):
        org = _get_seeded_org(db)
        project = _get_seeded_project(db)
        strategy = _make_strategy(db, org, project)
        db.commit()

        try:
            resp = client.get(f"/api/strategies/{strategy.id}/evidence-trends")
            assert resp.status_code == 200
            summary = resp.json()["reliability_trend"]["deterministic_summary"]
            # Should mention needing more data
            lower = summary.lower()
            assert "no" in lower or "only" in lower or "insufficient" in lower
        finally:
            db.delete(strategy)
            db.commit()

    def test_suggested_checks_when_no_evidence(self, client, db):
        org = _get_seeded_org(db)
        project = _get_seeded_project(db)
        strategy = _make_strategy(db, org, project)
        db.commit()

        try:
            resp = client.get(f"/api/strategies/{strategy.id}/evidence-trends")
            assert resp.status_code == 200
            data = resp.json()
            # With no evidence at all, all four series are insufficient_history
            assert len(data["suggested_checks"]) > 0
        finally:
            db.delete(strategy)
            db.commit()

    def test_no_timeline_event_created(self, client, db):
        org = _get_seeded_org(db)
        project = _get_seeded_project(db)
        strategy = _make_strategy(db, org, project)
        db.commit()

        before_count = (
            db.query(AuditTimelineEvent)
            .filter(AuditTimelineEvent.strategy_id == strategy.id)
            .count()
        )

        try:
            resp = client.get(f"/api/strategies/{strategy.id}/evidence-trends")
            assert resp.status_code == 200

            after_count = (
                db.query(AuditTimelineEvent)
                .filter(AuditTimelineEvent.strategy_id == strategy.id)
                .count()
            )
            assert after_count == before_count
        finally:
            db.delete(strategy)
            db.commit()
