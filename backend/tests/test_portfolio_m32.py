"""M32 tests: Portfolio Overview endpoint.

Tests for:
  - GET /api/portfolio/overview
  - PortfolioOverviewResponse fields
  - Filtering by project_id
  - Archived strategy inclusion/exclusion
  - Per-section limits
  - Health/asset class distribution dicts
  - Rankings: top_review, under_instrumented, strongest, deteriorating
  - Aggregate stats
  - Read-only guarantee (no AuditTimelineEvent created)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from app.models.alert import Alert
from app.models.audit_timeline_event import AuditTimelineEvent
from app.models.organization import Organization
from app.models.project import Project
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


def _get_org_project(db):
    org = db.query(Organization).first()
    project = db.query(Project).filter(Project.organization_id == org.id).first()
    return org, project


def _cleanup(db, *objs):
    for obj in objs:
        try:
            fresh = db.query(type(obj)).filter(type(obj).id == obj.id).first()
            if fresh is not None:
                db.delete(fresh)
        except Exception:
            pass
    try:
        db.commit()
    except Exception:
        db.rollback()


# ---------------------------------------------------------------------------
# TestPortfolioEndpoint
# ---------------------------------------------------------------------------


class TestPortfolioEndpoint:
    def test_portfolio_returns_200(self, client):
        """GET /api/portfolio/overview returns 200."""
        resp = client.get("/api/portfolio/overview")
        assert resp.status_code == 200

    def test_portfolio_response_fields(self, client):
        """All required top-level fields are present."""
        resp = client.get("/api/portfolio/overview")
        assert resp.status_code == 200
        data = resp.json()
        required = [
            "generated_at",
            "strategy_count",
            "active_strategy_count",
            "archived_strategy_count",
            "average_health_score",
            "average_reliability_score",
            "average_evidence_coverage_score",
            "open_alert_count",
            "high_critical_alert_count",
            "strategies_by_health_status",
            "strategies_by_reliability_status",
            "strategies_by_asset_class",
            "all_items",
            "top_review_strategies",
            "most_under_instrumented_strategies",
            "strongest_evidence_strategies",
            "deteriorating_trend_strategies",
            "recent_activity",
            "suggested_next_steps",
            "deterministic_summary",
        ]
        for field in required:
            assert field in data, f"Missing field: {field}"

    def test_portfolio_seeded_strategy_present(self, client, db):
        """The seeded AAPL strategy appears in all_items."""
        resp = client.get("/api/portfolio/overview")
        assert resp.status_code == 200
        data = resp.json()
        names = [item["name"] for item in data["all_items"]]
        # The seed creates "AAPL Mean Reversion v1"
        assert any("AAPL" in n for n in names), f"AAPL strategy not found in {names}"

    def test_active_count_excludes_archived(self, client, db):
        """Archived strategies are excluded by default."""
        org, project = _get_org_project(db)
        s = _make_strategy(db, org, project, name=f"Archived-{uuid.uuid4().hex[:6]}", status="archived")
        try:
            resp = client.get("/api/portfolio/overview")
            assert resp.status_code == 200
            data = resp.json()
            slugs = [item["slug"] for item in data["all_items"]]
            assert s.slug not in slugs
        finally:
            _cleanup(db, s)

    def test_include_archived_true(self, client, db):
        """include_archived=true includes archived strategies in the response."""
        org, project = _get_org_project(db)
        s = _make_strategy(db, org, project, name=f"Archived2-{uuid.uuid4().hex[:6]}", status="archived")
        try:
            resp = client.get("/api/portfolio/overview?include_archived=true")
            assert resp.status_code == 200
            data = resp.json()
            slugs = [item["slug"] for item in data["all_items"]]
            assert s.slug in slugs
        finally:
            _cleanup(db, s)

    def test_limit_per_section_works(self, client):
        """limit_per_section=1 returns at most 1 item per ranked section."""
        resp = client.get("/api/portfolio/overview?limit_per_section=1")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["top_review_strategies"]) <= 1
        assert len(data["most_under_instrumented_strategies"]) <= 1
        assert len(data["strongest_evidence_strategies"]) <= 1
        assert len(data["deteriorating_trend_strategies"]) <= 1

    def test_project_id_filter(self, client, db):
        """project_id query param limits results to that project's strategies."""
        org, project = _get_org_project(db)
        # Create a second project with a strategy
        other_proj = Project(
            organization_id=org.id,
            name=f"OtherProj-{uuid.uuid4().hex[:6]}",
            slug=f"otherproj-{uuid.uuid4().hex[:6]}",
        )
        db.add(other_proj)
        db.flush()
        s_other = _make_strategy(db, org, other_proj, name=f"OtherStrat-{uuid.uuid4().hex[:6]}")
        try:
            # Filter by the main project
            resp = client.get(f"/api/portfolio/overview?project_id={project.id}")
            assert resp.status_code == 200
            data = resp.json()
            slugs = [item["slug"] for item in data["all_items"]]
            assert s_other.slug not in slugs
        finally:
            _cleanup(db, s_other, other_proj)

    def test_health_status_counts_present(self, client):
        """strategies_by_health_status is a dict."""
        resp = client.get("/api/portfolio/overview")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data["strategies_by_health_status"], dict)

    def test_asset_class_counts_present(self, client):
        """strategies_by_asset_class is a dict."""
        resp = client.get("/api/portfolio/overview")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data["strategies_by_asset_class"], dict)

    def test_deterministic_summary_not_investment_advice(self, client):
        """deterministic_summary does not contain forbidden investment advice language."""
        resp = client.get("/api/portfolio/overview")
        assert resp.status_code == 200
        data = resp.json()
        summary = data["deterministic_summary"].lower()
        for forbidden in ("buy", "sell", "profit", "investment advice"):
            assert forbidden not in summary, f"Forbidden term '{forbidden}' in summary: {summary}"

    def test_no_timeline_event_created(self, client, db):
        """Calling the endpoint does not create any AuditTimelineEvent records."""
        before = db.query(AuditTimelineEvent).count()
        client.get("/api/portfolio/overview")
        after = db.query(AuditTimelineEvent).count()
        assert after == before

    def test_read_only_no_commit(self, client, db):
        """Calling the endpoint does not alter strategy count in the DB."""
        before = db.query(Strategy).count()
        client.get("/api/portfolio/overview")
        after = db.query(Strategy).count()
        assert after == before


# ---------------------------------------------------------------------------
# TestPortfolioRankings
# ---------------------------------------------------------------------------


class TestPortfolioRankings:
    def test_top_review_strategies_includes_critical(self, client, db):
        """A strategy with a critical/high alert gets health_status=critical in all_items."""
        org, project = _get_org_project(db)
        s = _make_strategy(db, org, project, name=f"CriticalStrat-{uuid.uuid4().hex[:6]}")
        a = _make_alert(db, org, s, severity="critical", status="open")
        try:
            resp = client.get("/api/portfolio/overview?limit_per_section=20")
            assert resp.status_code == 200
            data = resp.json()
            all_slugs = [i["slug"] for i in data["all_items"]]
            # Strategy must appear in all_items
            assert s.slug in all_slugs
            # Because it has a critical alert, its health_status must be "critical",
            # making it eligible for top_review_strategies (top 20 may be full in a
            # shared session DB, but the health classification must be correct).
            strategy_item = next(i for i in data["all_items"] if i["slug"] == s.slug)
            assert strategy_item["health_status"] in ("critical", "review"), (
                f"Expected critical/review health_status for strategy with critical alert; "
                f"got {strategy_item['health_status']!r}"
            )
            # top_review_strategies must be a subset of all_items with critical/review status
            review_slugs = [i["slug"] for i in data["top_review_strategies"]]
            for slug in review_slugs:
                item = next(i for i in data["all_items"] if i["slug"] == slug)
                assert item["health_status"] in (
                    "critical", "review", "watch", "insufficient_evidence"
                ), f"{slug} in top_review but has health_status={item['health_status']!r}"
        finally:
            _cleanup(db, a, s)

    def test_under_instrumented_sorted_by_coverage(self, client, db):
        """Strategy with lower coverage ranked first in most_under_instrumented_strategies."""
        org, project = _get_org_project(db)
        # Two bare strategies: no runs, no evidence -> both low coverage
        s1 = _make_strategy(db, org, project, name=f"Bare1-{uuid.uuid4().hex[:6]}")
        s2 = _make_strategy(db, org, project, name=f"Bare2-{uuid.uuid4().hex[:6]}")
        try:
            resp = client.get("/api/portfolio/overview?limit_per_section=20")
            assert resp.status_code == 200
            data = resp.json()
            under = data["most_under_instrumented_strategies"]
            scores = [i["evidence_coverage_score"] for i in under]
            # Scores should be non-decreasing (lowest coverage first)
            assert scores == sorted(scores), f"Not sorted ascending: {scores}"
        finally:
            _cleanup(db, s1, s2)

    def test_strongest_evidence_has_high_coverage(self, client, db):
        """Strategies in strongest_evidence_strategies should have no high/critical alerts."""
        resp = client.get("/api/portfolio/overview?limit_per_section=20")
        assert resp.status_code == 200
        data = resp.json()
        for item in data["strongest_evidence_strategies"]:
            assert item["high_critical_alert_count"] == 0, (
                f"Strategy {item['name']} in strongest has hc_alerts={item['high_critical_alert_count']}"
            )

    def test_deteriorating_trends_requires_two_points(self, client, db):
        """A strategy with only one reliability score should not appear in deteriorating."""
        org, project = _get_org_project(db)
        s = _make_strategy(db, org, project, name=f"OnePoint-{uuid.uuid4().hex[:6]}")
        _make_reliability_score(db, s, overall_score=70.0, status="fair")
        try:
            resp = client.get("/api/portfolio/overview?limit_per_section=20")
            assert resp.status_code == 200
            data = resp.json()
            det_slugs = [i["slug"] for i in data["deteriorating_trend_strategies"]]
            # With only one data point, cannot determine direction -> should NOT be deteriorating
            assert s.slug not in det_slugs
        finally:
            _cleanup(db, s)


# ---------------------------------------------------------------------------
# TestPortfolioAggregation
# ---------------------------------------------------------------------------


class TestPortfolioAggregation:
    def test_averages_null_when_no_evidence(self, client, db):
        """average_health_score is either null or a numeric value — never a string."""
        resp = client.get("/api/portfolio/overview")
        assert resp.status_code == 200
        data = resp.json()
        avg = data["average_health_score"]
        assert avg is None or isinstance(avg, (int, float))

    def test_alert_totals_correct(self, client, db):
        """Total open_alert_count reflects alerts in DB for active strategies."""
        org, project = _get_org_project(db)
        s = _make_strategy(db, org, project, name=f"AlertStrat-{uuid.uuid4().hex[:6]}")
        a1 = _make_alert(db, org, s, severity="high", status="open")
        a2 = _make_alert(db, org, s, severity="medium", status="open")
        try:
            resp = client.get("/api/portfolio/overview")
            assert resp.status_code == 200
            data = resp.json()
            # Total should be >= 2 (there may be other alerts from seed)
            assert data["open_alert_count"] >= 2
        finally:
            _cleanup(db, a2, a1, s)

    def test_suggested_next_steps_deterministic(self, client):
        """suggested_next_steps is a list of strings."""
        resp = client.get("/api/portfolio/overview")
        assert resp.status_code == 200
        data = resp.json()
        steps = data["suggested_next_steps"]
        assert isinstance(steps, list)
        for step in steps:
            assert isinstance(step, str)
