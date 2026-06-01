"""Tests for M20: Strategy Comparison Dashboard.

Tests cover:
  - Service-level compare_strategies function
  - POST /api/strategies/compare endpoint
  - Evidence coverage computation
  - Reliability ranking (scored before null)
  - Gap generation
  - Deterministic language (no investment/performance words)

All tests use the shared session-scoped fixtures from conftest.py.
"""
from __future__ import annotations

import uuid

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FORBIDDEN_WORDS = [
    "better strategy",
    "more profitable",
    "should trade",
    "alpha is stronger",
    "buy signal",
    "sell signal",
    "profit from",
    "expected return",
    "future performance",
    "investment recommendation",
]


def _has_forbidden(text: str) -> list[str]:
    low = text.lower()
    return [w for w in FORBIDDEN_WORDS if w in low]


# ---------------------------------------------------------------------------
# TestStrategyComparisonService — unit tests using DB session
# ---------------------------------------------------------------------------


class TestStrategyComparisonService:
    """Unit tests for compare_strategies() service function."""

    def test_requires_at_least_two_ids(self, db):
        from app.services.strategy_comparison import compare_strategies

        strat = db.query(__import__("app.models.strategy", fromlist=["Strategy"]).Strategy).first()
        assert strat is not None
        with pytest.raises(ValueError, match="At least 2"):
            compare_strategies([strat.id], db)

    def test_rejects_more_than_eight_ids(self, db):
        from app.services.strategy_comparison import compare_strategies

        fake_ids = [uuid.uuid4() for _ in range(9)]
        with pytest.raises(ValueError, match="At most 8"):
            compare_strategies(fake_ids, db)

    def test_rejects_unknown_strategy_id(self, db):
        from app.services.strategy_comparison import compare_strategies
        from app.models.strategy import Strategy

        real_strat = db.query(Strategy).first()
        assert real_strat is not None
        fake_id = uuid.uuid4()
        with pytest.raises(ValueError, match="not found"):
            compare_strategies([real_strat.id, fake_id], db)

    def test_rejects_archived_strategy_by_default(self, db):
        """Archived strategy rejected unless include_archived=True."""
        from app.services.strategy_comparison import compare_strategies
        from app.models.strategy import Strategy
        from app.models.project import Project

        # Create a fresh archived strategy for this test
        project = db.query(Project).first()
        assert project is not None
        archived = Strategy(
            project_id=project.id,
            name="Archived Test Strategy M20",
            slug=f"archived-test-m20-{uuid.uuid4().hex[:6]}",
            asset_class="equity",
            status="archived",
        )
        db.add(archived)
        db.flush()

        active = db.query(Strategy).filter(Strategy.status == "active").first()
        assert active is not None

        with pytest.raises(ValueError, match="Archived"):
            compare_strategies([active.id, archived.id], db)

    def test_archived_allowed_with_flag(self, db):
        """include_archived=True lets archived strategies through."""
        from app.services.strategy_comparison import compare_strategies
        from app.models.strategy import Strategy
        from app.models.project import Project

        project = db.query(Project).first()
        archived = Strategy(
            project_id=project.id,
            name="Archived Allowed M20",
            slug=f"archived-allowed-m20-{uuid.uuid4().hex[:6]}",
            asset_class="equity",
            status="archived",
        )
        db.add(archived)
        db.flush()

        active = db.query(Strategy).filter(Strategy.status == "active").first()
        result = compare_strategies([active.id, archived.id], db, include_archived=True)
        assert len(result.strategies) == 2

    def test_returns_correct_count_of_strategies(self, db):
        from app.services.strategy_comparison import compare_strategies
        from app.models.strategy import Strategy

        strats = db.query(Strategy).filter(Strategy.status == "active").limit(2).all()
        if len(strats) < 2:
            pytest.skip("Need at least 2 active strategies")
        result = compare_strategies([strats[0].id, strats[1].id], db)
        assert len(result.strategies) == 2

    def test_strategy_identities_present(self, db):
        from app.services.strategy_comparison import compare_strategies
        from app.models.strategy import Strategy

        strats = db.query(Strategy).filter(Strategy.status == "active").limit(2).all()
        if len(strats) < 2:
            pytest.skip("Need at least 2 active strategies")
        result = compare_strategies([strats[0].id, strats[1].id], db)
        ids_in_result = {str(item.strategy_id) for item in result.strategies}
        assert str(strats[0].id) in ids_in_result
        assert str(strats[1].id) in ids_in_result

    def test_coverage_counts_present(self, db):
        from app.services.strategy_comparison import compare_strategies
        from app.models.strategy import Strategy

        strats = db.query(Strategy).filter(Strategy.status == "active").limit(2).all()
        if len(strats) < 2:
            pytest.skip("Need at least 2 active strategies")
        result = compare_strategies([strats[0].id, strats[1].id], db)
        for item in result.strategies:
            cov = item.coverage
            assert cov is not None
            assert cov.run_count >= 0
            assert cov.backtest_run_count >= 0
            assert cov.dataset_snapshot_linked_count >= 0
            assert cov.backtest_audit_count >= 0
            assert cov.config_snapshot_count >= 0
            assert cov.universe_snapshot_count >= 0
            assert cov.signal_snapshot_count >= 0
            assert cov.open_alert_count >= 0
            assert cov.report_count >= 0
            assert cov.timeline_event_count >= 0
            assert 0.0 <= cov.evidence_coverage_score <= 100.0

    def test_gaps_list_present(self, db):
        from app.services.strategy_comparison import compare_strategies
        from app.models.strategy import Strategy

        strats = db.query(Strategy).filter(Strategy.status == "active").limit(2).all()
        if len(strats) < 2:
            pytest.skip("Need at least 2 active strategies")
        result = compare_strategies([strats[0].id, strats[1].id], db)
        for item in result.strategies:
            assert isinstance(item.gaps, list)

    def test_reliability_ranking_present(self, db):
        from app.services.strategy_comparison import compare_strategies
        from app.models.strategy import Strategy

        strats = db.query(Strategy).filter(Strategy.status == "active").limit(2).all()
        if len(strats) < 2:
            pytest.skip("Need at least 2 active strategies")
        result = compare_strategies([strats[0].id, strats[1].id], db)
        assert len(result.ranked_by_reliability) == 2
        assert result.ranked_by_reliability[0].rank == 1
        assert result.ranked_by_reliability[1].rank == 2

    def test_evidence_coverage_ranking_present(self, db):
        from app.services.strategy_comparison import compare_strategies
        from app.models.strategy import Strategy

        strats = db.query(Strategy).filter(Strategy.status == "active").limit(2).all()
        if len(strats) < 2:
            pytest.skip("Need at least 2 active strategies")
        result = compare_strategies([strats[0].id, strats[1].id], db)
        assert len(result.ranked_by_evidence_coverage) == 2
        scores = [r.score for r in result.ranked_by_evidence_coverage]
        # Should be ordered descending (or equal)
        assert scores[0] >= scores[1]  # type: ignore[operator]

    def test_deterministic_explanation_present(self, db):
        from app.services.strategy_comparison import compare_strategies
        from app.models.strategy import Strategy

        strats = db.query(Strategy).filter(Strategy.status == "active").limit(2).all()
        if len(strats) < 2:
            pytest.skip("Need at least 2 active strategies")
        result = compare_strategies([strats[0].id, strats[1].id], db)
        assert isinstance(result.deterministic_explanation, str)
        assert len(result.deterministic_explanation) > 20

    def test_explanation_avoids_forbidden_language(self, db):
        from app.services.strategy_comparison import compare_strategies
        from app.models.strategy import Strategy

        strats = db.query(Strategy).filter(Strategy.status == "active").limit(2).all()
        if len(strats) < 2:
            pytest.skip("Need at least 2 active strategies")
        result = compare_strategies([strats[0].id, strats[1].id], db)
        found = _has_forbidden(result.deterministic_explanation)
        assert not found, f"Forbidden words found: {found}"

    def test_explanation_ends_with_evidence_disclaimer(self, db):
        from app.services.strategy_comparison import compare_strategies
        from app.models.strategy import Strategy

        strats = db.query(Strategy).filter(Strategy.status == "active").limit(2).all()
        if len(strats) < 2:
            pytest.skip("Need at least 2 active strategies")
        result = compare_strategies([strats[0].id, strats[1].id], db)
        assert "logged QuantFidelity evidence" in result.deterministic_explanation
        assert "not expected trading performance" in result.deterministic_explanation

    def test_shared_gaps_subset_of_individual_gaps(self, db):
        from app.services.strategy_comparison import compare_strategies
        from app.models.strategy import Strategy

        strats = db.query(Strategy).filter(Strategy.status == "active").limit(2).all()
        if len(strats) < 2:
            pytest.skip("Need at least 2 active strategies")
        result = compare_strategies([strats[0].id, strats[1].id], db)
        all_gaps = [set(item.gaps) for item in result.strategies]
        shared = all_gaps[0].intersection(*all_gaps[1:])
        assert set(result.shared_gaps) == shared

    def test_generated_at_is_recent(self, db):
        from app.services.strategy_comparison import compare_strategies
        from app.models.strategy import Strategy
        from datetime import datetime, timezone, timedelta

        strats = db.query(Strategy).filter(Strategy.status == "active").limit(2).all()
        if len(strats) < 2:
            pytest.skip("Need at least 2 active strategies")
        result = compare_strategies([strats[0].id, strats[1].id], db)
        now = datetime.now(timezone.utc)
        assert (now - result.generated_at).total_seconds() < 60


# ---------------------------------------------------------------------------
# TestStrategyComparisonScoredRanking — reliability ranking with scores
# ---------------------------------------------------------------------------


class TestStrategyComparisonScoredRanking:
    """Tests for reliability ranking with computed scores."""

    def test_scored_strategy_ranks_above_unscored(self, db, client):
        """Strategy with a reliability score should rank above one without."""
        from app.models.strategy import Strategy
        from app.models.project import Project

        project = db.query(Project).first()
        assert project is not None

        # Create two fresh strategies for this test
        s_scored = Strategy(
            project_id=project.id,
            name=f"Scored Strategy M20 {uuid.uuid4().hex[:6]}",
            slug=f"scored-m20-{uuid.uuid4().hex[:6]}",
            asset_class="equity",
            status="active",
        )
        s_unscored = Strategy(
            project_id=project.id,
            name=f"Unscored Strategy M20 {uuid.uuid4().hex[:6]}",
            slug=f"unscored-m20-{uuid.uuid4().hex[:6]}",
            asset_class="equity",
            status="active",
        )
        db.add_all([s_scored, s_unscored])
        db.flush()

        # Compute reliability score for s_scored (returns 201)
        score_resp = client.post(f"/api/strategies/{s_scored.id}/reliability-score")
        assert score_resp.status_code == 201

        # Compare via API
        resp = client.post(
            "/api/strategies/compare",
            json={"strategy_ids": [str(s_scored.id), str(s_unscored.id)]},
        )
        assert resp.status_code == 200
        data = resp.json()

        # Scored strategy should appear at rank 1
        ranking = data["ranked_by_reliability"]
        assert len(ranking) == 2
        rank1 = ranking[0]
        assert rank1["strategy_id"] == str(s_scored.id)
        rank2 = ranking[1]
        assert rank2["status"] in ("no_score", "insufficient_evidence")

    def test_null_scores_rank_last(self, db, client):
        """When a strategy has no reliability score, it ranks last."""
        from app.models.strategy import Strategy
        from app.models.project import Project

        project = db.query(Project).first()
        s1 = Strategy(
            project_id=project.id,
            name=f"RankTest1 M20 {uuid.uuid4().hex[:6]}",
            slug=f"ranktest1-m20-{uuid.uuid4().hex[:6]}",
            asset_class="equity",
            status="active",
        )
        s2 = Strategy(
            project_id=project.id,
            name=f"RankTest2 M20 {uuid.uuid4().hex[:6]}",
            slug=f"ranktest2-m20-{uuid.uuid4().hex[:6]}",
            asset_class="equity",
            status="active",
        )
        db.add_all([s1, s2])
        db.flush()

        # Only s1 gets a score
        client.post(f"/api/strategies/{s1.id}/reliability-score")

        resp = client.post(
            "/api/strategies/compare",
            json={"strategy_ids": [str(s2.id), str(s1.id)]},  # s2 first
        )
        assert resp.status_code == 200
        data = resp.json()
        ranking = data["ranked_by_reliability"]
        # s1 (scored) should be rank 1 regardless of input order
        assert ranking[0]["strategy_id"] == str(s1.id)
        assert ranking[1]["strategy_id"] == str(s2.id)


# ---------------------------------------------------------------------------
# TestStrategyComparisonEndpoint — HTTP-level tests
# ---------------------------------------------------------------------------


class TestStrategyComparisonEndpoint:
    """HTTP endpoint tests for POST /api/strategies/compare."""

    def test_compare_two_strategies_success(self, client, db):
        from app.models.strategy import Strategy

        strats = db.query(Strategy).filter(Strategy.status == "active").limit(2).all()
        if len(strats) < 2:
            pytest.skip("Need at least 2 active strategies")
        resp = client.post(
            "/api/strategies/compare",
            json={"strategy_ids": [str(strats[0].id), str(strats[1].id)]},
        )
        assert resp.status_code == 200

    def test_compare_response_has_required_fields(self, client, db):
        from app.models.strategy import Strategy

        strats = db.query(Strategy).filter(Strategy.status == "active").limit(2).all()
        if len(strats) < 2:
            pytest.skip("Need at least 2 active strategies")
        resp = client.post(
            "/api/strategies/compare",
            json={"strategy_ids": [str(strats[0].id), str(strats[1].id)]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "strategies" in data
        assert "ranked_by_reliability" in data
        assert "ranked_by_evidence_coverage" in data
        assert "shared_gaps" in data
        assert "differentiators" in data
        assert "deterministic_explanation" in data
        assert "generated_at" in data

    def test_compare_strategy_items_have_coverage(self, client, db):
        from app.models.strategy import Strategy

        strats = db.query(Strategy).filter(Strategy.status == "active").limit(2).all()
        if len(strats) < 2:
            pytest.skip("Need at least 2 active strategies")
        resp = client.post(
            "/api/strategies/compare",
            json={"strategy_ids": [str(strats[0].id), str(strats[1].id)]},
        )
        data = resp.json()
        for item in data["strategies"]:
            cov = item["coverage"]
            assert "run_count" in cov
            assert "backtest_run_count" in cov
            assert "dataset_snapshot_linked_count" in cov
            assert "backtest_audit_count" in cov
            assert "evidence_coverage_score" in cov

    def test_compare_rejects_fewer_than_two_ids(self, client):
        resp = client.post(
            "/api/strategies/compare",
            json={"strategy_ids": [str(uuid.uuid4())]},
        )
        assert resp.status_code == 422

    def test_compare_rejects_more_than_eight_ids(self, client):
        ids = [str(uuid.uuid4()) for _ in range(9)]
        resp = client.post("/api/strategies/compare", json={"strategy_ids": ids})
        assert resp.status_code == 422

    def test_compare_rejects_missing_strategy(self, client, db):
        from app.models.strategy import Strategy

        real = db.query(Strategy).filter(Strategy.status == "active").first()
        assert real is not None
        fake = str(uuid.uuid4())
        resp = client.post(
            "/api/strategies/compare",
            json={"strategy_ids": [str(real.id), fake]},
        )
        assert resp.status_code == 404

    def test_compare_rejects_archived_without_flag(self, client, db):
        from app.models.strategy import Strategy
        from app.models.project import Project

        project = db.query(Project).first()
        archived = Strategy(
            project_id=project.id,
            name=f"Archived Endpoint Test M20 {uuid.uuid4().hex[:6]}",
            slug=f"archived-ep-m20-{uuid.uuid4().hex[:6]}",
            asset_class="equity",
            status="archived",
        )
        db.add(archived)
        db.flush()

        active = db.query(Strategy).filter(Strategy.status == "active").first()
        resp = client.post(
            "/api/strategies/compare",
            json={
                "strategy_ids": [str(active.id), str(archived.id)],
                "include_archived": False,
            },
        )
        assert resp.status_code == 400

    def test_compare_allows_archived_with_flag(self, client, db):
        from app.models.strategy import Strategy
        from app.models.project import Project

        project = db.query(Project).first()
        archived = Strategy(
            project_id=project.id,
            name=f"Archived Flag Test M20 {uuid.uuid4().hex[:6]}",
            slug=f"archived-flag-m20-{uuid.uuid4().hex[:6]}",
            asset_class="equity",
            status="archived",
        )
        db.add(archived)
        db.flush()

        active = db.query(Strategy).filter(Strategy.status == "active").first()
        resp = client.post(
            "/api/strategies/compare",
            json={
                "strategy_ids": [str(active.id), str(archived.id)],
                "include_archived": True,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["strategies"]) == 2

    def test_compare_ranking_counts_match_strategy_count(self, client, db):
        from app.models.strategy import Strategy

        strats = db.query(Strategy).filter(Strategy.status == "active").limit(3).all()
        if len(strats) < 2:
            pytest.skip("Need at least 2 active strategies")
        ids = [str(s.id) for s in strats]
        resp = client.post("/api/strategies/compare", json={"strategy_ids": ids})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["ranked_by_reliability"]) == len(strats)
        assert len(data["ranked_by_evidence_coverage"]) == len(strats)

    def test_compare_explanation_not_investment_advice(self, client, db):
        from app.models.strategy import Strategy

        strats = db.query(Strategy).filter(Strategy.status == "active").limit(2).all()
        if len(strats) < 2:
            pytest.skip("Need at least 2 active strategies")
        resp = client.post(
            "/api/strategies/compare",
            json={"strategy_ids": [str(strats[0].id), str(strats[1].id)]},
        )
        assert resp.status_code == 200
        data = resp.json()
        found = _has_forbidden(data["deterministic_explanation"])
        assert not found, f"Forbidden words in explanation: {found}"

    def test_compare_strongest_weakest_null_when_no_scores(self, client, db):
        """When no strategies have reliability scores, strongest/weakest are null."""
        from app.models.strategy import Strategy
        from app.models.project import Project

        project = db.query(Project).first()
        s1 = Strategy(
            project_id=project.id,
            name=f"NoScore1 M20 {uuid.uuid4().hex[:6]}",
            slug=f"noscore1-m20-{uuid.uuid4().hex[:6]}",
            asset_class="equity",
            status="active",
        )
        s2 = Strategy(
            project_id=project.id,
            name=f"NoScore2 M20 {uuid.uuid4().hex[:6]}",
            slug=f"noscore2-m20-{uuid.uuid4().hex[:6]}",
            asset_class="equity",
            status="active",
        )
        db.add_all([s1, s2])
        db.flush()

        resp = client.post(
            "/api/strategies/compare",
            json={"strategy_ids": [str(s1.id), str(s2.id)]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["strongest_strategy_id"] is None
        assert data["weakest_strategy_id"] is None

    def test_compare_open_alert_count_included(self, client, db):
        """open_alert_count is populated in coverage (may be 0)."""
        from app.models.strategy import Strategy

        strats = db.query(Strategy).filter(Strategy.status == "active").limit(2).all()
        if len(strats) < 2:
            pytest.skip("Need at least 2 active strategies")
        resp = client.post(
            "/api/strategies/compare",
            json={"strategy_ids": [str(strats[0].id), str(strats[1].id)]},
        )
        assert resp.status_code == 200
        data = resp.json()
        for item in data["strategies"]:
            assert "open_alert_count" in item["coverage"]

    def test_compare_gaps_include_expected_keys(self, client, db):
        """Gaps for a brand-new strategy should include known gap types."""
        from app.models.strategy import Strategy
        from app.models.project import Project

        project = db.query(Project).first()
        fresh = Strategy(
            project_id=project.id,
            name=f"GapTest M20 {uuid.uuid4().hex[:6]}",
            slug=f"gap-test-m20-{uuid.uuid4().hex[:6]}",
            asset_class="equity",
            status="active",
        )
        db.add(fresh)
        db.flush()

        existing = db.query(Strategy).filter(
            Strategy.status == "active", Strategy.id != fresh.id
        ).first()
        assert existing is not None

        resp = client.post(
            "/api/strategies/compare",
            json={"strategy_ids": [str(fresh.id), str(existing.id)]},
        )
        assert resp.status_code == 200
        data = resp.json()
        fresh_item = next(
            i for i in data["strategies"] if i["strategy_id"] == str(fresh.id)
        )
        # Fresh strategy has no runs or evidence — should have gap flags
        valid_gap_keys = {
            "no_runs",
            "no_dataset_evidence",
            "no_backtest_audit",
            "no_signal_evidence",
            "no_universe_evidence",
            "no_config_snapshot",
            "open_high_alerts",
            "insufficient_reliability_score",
            "stale_reliability_score",
        }
        for gap in fresh_item["gaps"]:
            assert gap in valid_gap_keys, f"Unknown gap key: {gap}"
        # Fresh strategy must have at least these gaps
        assert "no_runs" in fresh_item["gaps"]
        assert "insufficient_reliability_score" in fresh_item["gaps"]

    def test_compare_high_alert_gap_triggered(self, client, db):
        """open_high_alerts gap is set when strategy has a high/critical open alert."""
        from app.models.strategy import Strategy
        from app.models.project import Project
        from app.models.organization import Organization
        from app.models.alert import Alert
        from datetime import datetime, timezone

        project = db.query(Project).first()
        org = db.query(Organization).first()

        alert_strat = Strategy(
            project_id=project.id,
            name=f"AlertGap M20 {uuid.uuid4().hex[:6]}",
            slug=f"alertgap-m20-{uuid.uuid4().hex[:6]}",
            asset_class="equity",
            status="active",
        )
        db.add(alert_strat)
        db.flush()

        # Create a high open alert for this strategy
        # Note: Alert.organization_id is String(36), so must pass str
        alert = Alert(
            organization_id=str(org.id),
            rule_type="data_health_below_threshold",
            status="open",
            severity="high",
            title="Test high alert for comparison M20",
            strategy_id=str(alert_strat.id),
            triggered_at=datetime.now(timezone.utc),
        )
        db.add(alert)
        db.flush()

        other = db.query(Strategy).filter(
            Strategy.status == "active", Strategy.id != alert_strat.id
        ).first()
        assert other is not None

        resp = client.post(
            "/api/strategies/compare",
            json={"strategy_ids": [str(alert_strat.id), str(other.id)]},
        )
        assert resp.status_code == 200
        data = resp.json()
        alert_item = next(
            i for i in data["strategies"]
            if i["strategy_id"] == str(alert_strat.id)
        )
        assert "open_high_alerts" in alert_item["gaps"]
        assert alert_item["highest_severity_open_alert"] == "high"

    def test_no_timeline_event_created(self, client, db):
        """POST /compare must not create any audit timeline events."""
        from app.models.strategy import Strategy
        from app.models.audit_timeline_event import AuditTimelineEvent

        strats = db.query(Strategy).filter(Strategy.status == "active").limit(2).all()
        if len(strats) < 2:
            pytest.skip("Need at least 2 active strategies")

        count_before = (
            db.query(AuditTimelineEvent)
            .count()
        )
        client.post(
            "/api/strategies/compare",
            json={"strategy_ids": [str(strats[0].id), str(strats[1].id)]},
        )
        count_after = db.query(AuditTimelineEvent).count()
        assert count_after == count_before

    def test_compare_invalid_uuid_returns_422(self, client):
        resp = client.post(
            "/api/strategies/compare",
            json={"strategy_ids": ["not-a-uuid", str(uuid.uuid4())]},
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# TestEvidenceCoverageScore
# ---------------------------------------------------------------------------


class TestEvidenceCoverageScore:
    """Unit tests for coverage score computation."""

    def test_empty_strategy_has_zero_coverage(self):
        from app.services.strategy_comparison import (
            StrategyEvidenceCoverageData,
            _compute_coverage_score,
        )

        cov = StrategyEvidenceCoverageData(
            run_count=0,
            backtest_run_count=0,
            research_run_count=0,
            paper_run_count=0,
            live_run_count=0,
            dataset_snapshot_linked_count=0,
            backtest_audit_count=0,
            config_snapshot_count=0,
            universe_snapshot_count=0,
            signal_snapshot_count=0,
            open_alert_count=0,
            report_count=0,
            timeline_event_count=0,
            evidence_coverage_score=0.0,
        )
        assert _compute_coverage_score(cov) == 0.0

    def test_full_evidence_gives_max_score(self):
        from app.services.strategy_comparison import (
            StrategyEvidenceCoverageData,
            _compute_coverage_score,
        )

        cov = StrategyEvidenceCoverageData(
            run_count=3,
            backtest_run_count=2,
            research_run_count=1,
            paper_run_count=0,
            live_run_count=0,
            dataset_snapshot_linked_count=2,
            backtest_audit_count=1,
            config_snapshot_count=1,
            universe_snapshot_count=1,
            signal_snapshot_count=1,
            open_alert_count=0,
            report_count=1,
            timeline_event_count=5,
            evidence_coverage_score=0.0,
        )
        score = _compute_coverage_score(cov)
        assert score == 100.0

    def test_partial_evidence_score(self):
        from app.services.strategy_comparison import (
            StrategyEvidenceCoverageData,
            _compute_coverage_score,
        )

        cov = StrategyEvidenceCoverageData(
            run_count=1,         # +10
            backtest_run_count=1,  # +10
            research_run_count=0,
            paper_run_count=0,
            live_run_count=0,
            dataset_snapshot_linked_count=0,  # no +20
            backtest_audit_count=0,           # no +20
            config_snapshot_count=0,
            universe_snapshot_count=0,
            signal_snapshot_count=0,
            open_alert_count=0,
            report_count=0,
            timeline_event_count=0,
            evidence_coverage_score=0.0,
        )
        assert _compute_coverage_score(cov) == 20.0


# ---------------------------------------------------------------------------
# TestGapGeneration
# ---------------------------------------------------------------------------


class TestGapGeneration:
    """Unit tests for deterministic gap label generation."""

    def _make_item(self, **kwargs):
        """Build a minimal StrategyComparisonItemData for gap testing."""
        from app.services.strategy_comparison import (
            StrategyComparisonItemData,
            StrategyEvidenceCoverageData,
        )
        from datetime import datetime, timezone

        defaults = dict(
            strategy_id=uuid.uuid4(),
            name="Test",
            slug="test",
            asset_class="equity",
            status="active",
            overall_reliability_score=None,
            reliability_status=None,
            reliability_generated_at=None,
            strategy_activity_score=None,
            data_evidence_score=None,
            backtest_trust_score=None,
            config_evidence_score=None,
            universe_evidence_score=None,
            signal_evidence_score=None,
            alert_penalty_score=None,
            report_coverage_score=None,
            missing_evidence=[],
            suggested_checks=[],
            coverage=StrategyEvidenceCoverageData(
                run_count=0,
                backtest_run_count=0,
                research_run_count=0,
                paper_run_count=0,
                live_run_count=0,
                dataset_snapshot_linked_count=0,
                backtest_audit_count=0,
                config_snapshot_count=0,
                universe_snapshot_count=0,
                signal_snapshot_count=0,
                open_alert_count=0,
                report_count=0,
                timeline_event_count=0,
                evidence_coverage_score=0.0,
            ),
            latest_run_at=None,
            latest_backtest_trust_score=None,
            latest_data_health_score=None,
            latest_signal_quality_score=None,
            latest_report_score=None,
            highest_severity_open_alert=None,
        )
        defaults.update(kwargs)
        return StrategyComparisonItemData(**defaults)

    def test_no_runs_gap(self):
        from app.services.strategy_comparison import _compute_gaps
        from datetime import datetime, timezone

        item = self._make_item()
        gaps = _compute_gaps(item, item.coverage, datetime.now(timezone.utc))
        assert "no_runs" in gaps

    def test_no_dataset_evidence_gap(self):
        from app.services.strategy_comparison import _compute_gaps
        from datetime import datetime, timezone

        item = self._make_item()
        gaps = _compute_gaps(item, item.coverage, datetime.now(timezone.utc))
        assert "no_dataset_evidence" in gaps

    def test_open_high_alerts_gap(self):
        from app.services.strategy_comparison import _compute_gaps
        from datetime import datetime, timezone

        item = self._make_item(highest_severity_open_alert="high")
        gaps = _compute_gaps(item, item.coverage, datetime.now(timezone.utc))
        assert "open_high_alerts" in gaps

    def test_open_critical_alerts_gap(self):
        from app.services.strategy_comparison import _compute_gaps
        from datetime import datetime, timezone

        item = self._make_item(highest_severity_open_alert="critical")
        gaps = _compute_gaps(item, item.coverage, datetime.now(timezone.utc))
        assert "open_high_alerts" in gaps

    def test_medium_alert_does_not_trigger_gap(self):
        from app.services.strategy_comparison import _compute_gaps
        from datetime import datetime, timezone

        item = self._make_item(highest_severity_open_alert="medium")
        gaps = _compute_gaps(item, item.coverage, datetime.now(timezone.utc))
        assert "open_high_alerts" not in gaps

    def test_insufficient_reliability_gap(self):
        from app.services.strategy_comparison import _compute_gaps
        from datetime import datetime, timezone

        item = self._make_item(reliability_status="insufficient_evidence")
        gaps = _compute_gaps(item, item.coverage, datetime.now(timezone.utc))
        assert "insufficient_reliability_score" in gaps

    def test_stale_reliability_gap(self):
        from app.services.strategy_comparison import _compute_gaps
        from datetime import datetime, timezone, timedelta

        old = datetime.now(timezone.utc) - timedelta(days=45)
        item = self._make_item(
            overall_reliability_score=70.0,
            reliability_status="good",
            reliability_generated_at=old,
        )
        gaps = _compute_gaps(item, item.coverage, datetime.now(timezone.utc))
        assert "stale_reliability_score" in gaps

    def test_fresh_score_no_stale_gap(self):
        from app.services.strategy_comparison import _compute_gaps
        from datetime import datetime, timezone, timedelta

        recent = datetime.now(timezone.utc) - timedelta(days=5)
        item = self._make_item(
            overall_reliability_score=70.0,
            reliability_status="good",
            reliability_generated_at=recent,
        )
        gaps = _compute_gaps(item, item.coverage, datetime.now(timezone.utc))
        assert "stale_reliability_score" not in gaps
