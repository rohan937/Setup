"""Tests for M34: Multi-Run Cross-Strategy Comparison.

Coverage:
  - Service-level compare_multi_strategy_runs validation
  - POST /api/strategies/runs/compare-multi endpoint
  - Metric/evidence matrix construction
  - Rankings (nulls last)
  - Gap identification
  - Deterministic language (no investment/performance words)
  - No AuditTimelineEvent side-effects

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


def _make_strategy(db, project_id, *, suffix: str = "", asset_class: str = "equity") -> object:
    from app.models.strategy import Strategy

    slug = f"m34-test-{suffix}-{uuid.uuid4().hex[:8]}"
    strat = Strategy(
        project_id=project_id,
        name=f"M34 Test Strategy {suffix}",
        slug=slug,
        asset_class=asset_class,
        status="active",
    )
    db.add(strat)
    db.flush()
    return strat


def _make_run(db, strategy_id, *, run_name: str = "Test Run", metrics: dict | None = None) -> object:
    from datetime import datetime, timezone

    from app.models.strategy_run import StrategyRun

    run = StrategyRun(
        strategy_id=strategy_id,
        run_name=run_name,
        run_type="backtest",
        status="completed",
        completed_at=datetime.now(timezone.utc),
        metrics_json=metrics or {},
        assumptions_json={},
    )
    db.add(run)
    db.flush()
    return run


# ---------------------------------------------------------------------------
# TestMultiRunComparisonService — unit tests via service layer
# ---------------------------------------------------------------------------


class TestMultiRunComparisonService:
    def test_requires_at_least_two_ids(self, db):
        from app.services.multi_run_comparison import compare_multi_strategy_runs
        from app.models.strategy import Strategy

        strat = db.query(Strategy).first()
        assert strat is not None
        with pytest.raises(ValueError, match="At least 2"):
            compare_multi_strategy_runs([strat.id], db)

    def test_rejects_more_than_four_ids(self, db):
        from app.services.multi_run_comparison import compare_multi_strategy_runs

        fake_ids = [uuid.uuid4() for _ in range(5)]
        with pytest.raises(ValueError, match="At most 4"):
            compare_multi_strategy_runs(fake_ids, db)

    def test_rejects_unknown_strategy_id(self, db):
        from app.services.multi_run_comparison import compare_multi_strategy_runs
        from app.models.strategy import Strategy

        real = db.query(Strategy).first()
        assert real is not None
        fake = uuid.uuid4()
        with pytest.raises(ValueError, match="not found"):
            compare_multi_strategy_runs([real.id, fake], db)

    def test_rejects_invalid_mode(self, db):
        from app.services.multi_run_comparison import compare_multi_strategy_runs
        from app.models.project import Project

        project = db.query(Project).first()
        assert project is not None
        s1 = _make_strategy(db, project.id, suffix="mode1")
        s2 = _make_strategy(db, project.id, suffix="mode2")
        _make_run(db, s1.id, run_name="Mode Run 1")
        _make_run(db, s2.id, run_name="Mode Run 2")
        try:
            with pytest.raises(ValueError, match="Invalid mode"):
                compare_multi_strategy_runs([s1.id, s2.id], db, mode="bogus")
        finally:
            db.delete(s1)
            db.delete(s2)
            db.flush()

    def test_selected_mode_requires_run_ids(self, db):
        from app.services.multi_run_comparison import compare_multi_strategy_runs
        from app.models.project import Project

        project = db.query(Project).first()
        s1 = _make_strategy(db, project.id, suffix="sel1a")
        s2 = _make_strategy(db, project.id, suffix="sel1b")
        try:
            with pytest.raises(ValueError, match="run_ids required"):
                compare_multi_strategy_runs([s1.id, s2.id], db, mode="selected")
        finally:
            db.delete(s1)
            db.delete(s2)
            db.flush()

    def test_latest_mode_fails_for_strategy_with_no_runs(self, db):
        from app.services.multi_run_comparison import compare_multi_strategy_runs
        from app.models.strategy import Strategy
        from app.models.project import Project

        project = db.query(Project).first()
        # Strategy with no runs
        no_run_strat = _make_strategy(db, project.id, suffix="norun")
        existing = db.query(Strategy).filter(Strategy.status == "active").first()
        assert existing is not None
        try:
            with pytest.raises(ValueError, match="no runs"):
                compare_multi_strategy_runs([existing.id, no_run_strat.id], db)
        finally:
            db.delete(no_run_strat)
            db.flush()


# ---------------------------------------------------------------------------
# TestMultiRunComparisonEndpoint — HTTP endpoint tests
# ---------------------------------------------------------------------------


class TestMultiRunComparisonEndpoint:
    def test_compare_two_strategies_latest(self, client, db):
        from app.models.project import Project

        project = db.query(Project).first()
        assert project is not None
        s1 = _make_strategy(db, project.id, suffix="ep1a")
        s2 = _make_strategy(db, project.id, suffix="ep1b")
        _make_run(db, s1.id, run_name="EP Run A", metrics={"sharpe": 1.2})
        _make_run(db, s2.id, run_name="EP Run B", metrics={"sharpe": 0.8})
        try:
            resp = client.post(
                "/api/strategies/runs/compare-multi",
                json={"strategy_ids": [str(s1.id), str(s2.id)]},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert "items" in data
            assert len(data["items"]) == 2
        finally:
            db.delete(s1)
            db.delete(s2)
            db.flush()

    def test_response_fields_present(self, client, db):
        from app.models.project import Project

        project = db.query(Project).first()
        s1 = _make_strategy(db, project.id, suffix="rf1")
        s2 = _make_strategy(db, project.id, suffix="rf2")
        _make_run(db, s1.id, run_name="RF Run 1")
        _make_run(db, s2.id, run_name="RF Run 2")
        try:
            resp = client.post(
                "/api/strategies/runs/compare-multi",
                json={"strategy_ids": [str(s1.id), str(s2.id)]},
            )
            assert resp.status_code == 200
            data = resp.json()
            for key in (
                "items",
                "metric_matrix",
                "evidence_matrix",
                "assumption_matrix",
                "rankings",
                "gaps",
                "shared_gaps",
                "highlighted_differences",
                "deterministic_explanation",
                "compared_at",
                "mode",
            ):
                assert key in data, f"missing key: {key}"
        finally:
            db.delete(s1)
            db.delete(s2)
            db.flush()

    def test_rejects_fewer_than_two(self, client, db):
        from app.models.project import Project

        project = db.query(Project).first()
        s1 = _make_strategy(db, project.id, suffix="lt2")
        _make_run(db, s1.id, run_name="LT2 Run")
        try:
            resp = client.post(
                "/api/strategies/runs/compare-multi",
                json={"strategy_ids": [str(s1.id)]},
            )
            assert resp.status_code == 422
        finally:
            db.delete(s1)
            db.flush()

    def test_rejects_more_than_four(self, client, db):
        resp = client.post(
            "/api/strategies/runs/compare-multi",
            json={"strategy_ids": [str(uuid.uuid4()) for _ in range(5)]},
        )
        assert resp.status_code == 422

    def test_rejects_missing_strategy(self, client, db):
        from app.models.strategy import Strategy

        real = db.query(Strategy).first()
        assert real is not None
        resp = client.post(
            "/api/strategies/runs/compare-multi",
            json={"strategy_ids": [str(real.id), str(uuid.uuid4())]},
        )
        assert resp.status_code == 400

    def test_rejects_no_runs_in_latest_mode(self, client, db):
        from app.models.strategy import Strategy
        from app.models.project import Project

        project = db.query(Project).first()
        no_run_strat = _make_strategy(db, project.id, suffix="norun-ep")
        existing = db.query(Strategy).filter(Strategy.status == "active").first()
        assert existing is not None
        try:
            resp = client.post(
                "/api/strategies/runs/compare-multi",
                json={"strategy_ids": [str(existing.id), str(no_run_strat.id)]},
            )
            assert resp.status_code == 400
        finally:
            db.delete(no_run_strat)
            db.flush()

    def test_selected_mode_uses_provided_runs(self, client, db):
        from app.models.project import Project

        project = db.query(Project).first()
        s1 = _make_strategy(db, project.id, suffix="sel1")
        s2 = _make_strategy(db, project.id, suffix="sel2")
        r1 = _make_run(db, s1.id, run_name="Selected Run A", metrics={"sharpe": 1.5})
        r2 = _make_run(db, s2.id, run_name="Selected Run B", metrics={"sharpe": 0.9})
        try:
            resp = client.post(
                "/api/strategies/runs/compare-multi",
                json={
                    "strategy_ids": [str(s1.id), str(s2.id)],
                    "mode": "selected",
                    "run_ids": [str(r1.id), str(r2.id)],
                },
            )
            assert resp.status_code == 200
            data = resp.json()
            run_names = [item["run_name"] for item in data["items"]]
            assert "Selected Run A" in run_names
            assert "Selected Run B" in run_names
        finally:
            db.delete(s1)
            db.delete(s2)
            db.flush()

    def test_selected_mode_rejects_wrong_strategy(self, client, db):
        from app.models.project import Project

        project = db.query(Project).first()
        s1 = _make_strategy(db, project.id, suffix="wrng1")
        s2 = _make_strategy(db, project.id, suffix="wrng2")
        s_other = _make_strategy(db, project.id, suffix="wrng3")
        r1 = _make_run(db, s1.id, run_name="Wrong Run 1")
        r_other = _make_run(db, s_other.id, run_name="Wrong Run Other")
        try:
            resp = client.post(
                "/api/strategies/runs/compare-multi",
                json={
                    "strategy_ids": [str(s1.id), str(s2.id)],
                    "mode": "selected",
                    "run_ids": [str(r1.id), str(r_other.id)],
                },
            )
            # Should fail because r_other belongs to s_other which is not in the list
            # (and no run provided for s2)
            assert resp.status_code == 400
        finally:
            db.delete(s1)
            db.delete(s2)
            db.delete(s_other)
            db.flush()

    def test_no_timeline_event_created(self, client, db):
        from app.models.audit_timeline_event import AuditTimelineEvent
        from app.models.project import Project

        project = db.query(Project).first()
        s1 = _make_strategy(db, project.id, suffix="tl1")
        s2 = _make_strategy(db, project.id, suffix="tl2")
        _make_run(db, s1.id, run_name="TL Run 1")
        _make_run(db, s2.id, run_name="TL Run 2")
        try:
            count_before = db.query(AuditTimelineEvent).count()
            resp = client.post(
                "/api/strategies/runs/compare-multi",
                json={"strategy_ids": [str(s1.id), str(s2.id)]},
            )
            assert resp.status_code == 200
            count_after = db.query(AuditTimelineEvent).count()
            assert count_after == count_before, "comparison must not create timeline events"
        finally:
            db.delete(s1)
            db.delete(s2)
            db.flush()

    def test_explanation_no_investment_language(self, client, db):
        from app.models.project import Project

        project = db.query(Project).first()
        s1 = _make_strategy(db, project.id, suffix="lang1")
        s2 = _make_strategy(db, project.id, suffix="lang2")
        _make_run(db, s1.id, run_name="Lang Run 1")
        _make_run(db, s2.id, run_name="Lang Run 2")
        try:
            resp = client.post(
                "/api/strategies/runs/compare-multi",
                json={"strategy_ids": [str(s1.id), str(s2.id)]},
            )
            assert resp.status_code == 200
            explanation = resp.json()["deterministic_explanation"]
            forbidden = _has_forbidden(explanation)
            assert not forbidden, f"Forbidden words in explanation: {forbidden}"
        finally:
            db.delete(s1)
            db.delete(s2)
            db.flush()


# ---------------------------------------------------------------------------
# TestMultiRunMatrices
# ---------------------------------------------------------------------------


class TestMultiRunMatrices:
    def test_metric_matrix_has_shared_metrics(self, client, db):
        from app.models.project import Project

        project = db.query(Project).first()
        s1 = _make_strategy(db, project.id, suffix="mm1")
        s2 = _make_strategy(db, project.id, suffix="mm2")
        _make_run(db, s1.id, run_name="MM Run 1", metrics={"sharpe": 1.4, "volatility": 0.12})
        _make_run(db, s2.id, run_name="MM Run 2", metrics={"sharpe": 0.9, "volatility": 0.18})
        try:
            resp = client.post(
                "/api/strategies/runs/compare-multi",
                json={"strategy_ids": [str(s1.id), str(s2.id)]},
            )
            assert resp.status_code == 200
            matrix = resp.json()["metric_matrix"]
            assert "sharpe" in matrix
            assert "volatility" in matrix
        finally:
            db.delete(s1)
            db.delete(s2)
            db.flush()

    def test_evidence_matrix_has_evidence_keys(self, client, db):
        from app.models.project import Project

        project = db.query(Project).first()
        s1 = _make_strategy(db, project.id, suffix="ev1")
        s2 = _make_strategy(db, project.id, suffix="ev2")
        _make_run(db, s1.id, run_name="Ev Run 1")
        _make_run(db, s2.id, run_name="Ev Run 2")
        try:
            resp = client.post(
                "/api/strategies/runs/compare-multi",
                json={"strategy_ids": [str(s1.id), str(s2.id)]},
            )
            assert resp.status_code == 200
            em = resp.json()["evidence_matrix"]
            for key in ("evidence_coverage_score", "open_alert_count"):
                assert key in em, f"missing evidence matrix key: {key}"
        finally:
            db.delete(s1)
            db.delete(s2)
            db.flush()

    def test_rankings_null_last(self, client, db):
        """Strategy with null backtest trust score ranks after one with numeric score."""
        from app.models.project import Project

        project = db.query(Project).first()
        # s1 has no evidence (null trust score), s2 also has no evidence
        # We need to verify null values are ranked last.
        # Use the seed strategy which may have evidence, and a bare strategy with no evidence.
        s_bare = _make_strategy(db, project.id, suffix="rank_bare")
        from app.models.strategy import Strategy

        # Pick an existing strategy that has runs (from seed)
        existing = db.query(Strategy).filter(Strategy.status == "active").first()
        assert existing is not None
        _make_run(db, s_bare.id, run_name="Rank Bare Run")
        try:
            resp = client.post(
                "/api/strategies/runs/compare-multi",
                json={"strategy_ids": [str(existing.id), str(s_bare.id)]},
            )
            assert resp.status_code == 200
            rankings = resp.json()["rankings"]
            assert "by_backtest_trust" in rankings
            trust_ranking = rankings["by_backtest_trust"]
            assert len(trust_ranking) == 2
            # Items with value None should come last
            vals = [r["value"] for r in trust_ranking]
            none_indices = [i for i, v in enumerate(vals) if v is None]
            numeric_indices = [i for i, v in enumerate(vals) if v is not None]
            if none_indices and numeric_indices:
                assert min(none_indices) > max(numeric_indices), (
                    "null values should rank after numeric values"
                )
        finally:
            db.delete(s_bare)
            db.flush()

    def test_gaps_identified_for_missing_evidence(self, client, db):
        """Strategy without signal evidence should appear in gaps."""
        from app.models.project import Project

        project = db.query(Project).first()
        s_no_sig = _make_strategy(db, project.id, suffix="gap1")
        s_no_sig2 = _make_strategy(db, project.id, suffix="gap2")
        _make_run(db, s_no_sig.id, run_name="Gap Run 1")
        _make_run(db, s_no_sig2.id, run_name="Gap Run 2")
        try:
            resp = client.post(
                "/api/strategies/runs/compare-multi",
                json={"strategy_ids": [str(s_no_sig.id), str(s_no_sig2.id)]},
            )
            assert resp.status_code == 200
            gaps = resp.json()["gaps"]
            # Both strategies have no signal evidence linked
            for sid_str in [str(s_no_sig.id), str(s_no_sig2.id)]:
                assert sid_str in gaps
                assert "Signal evidence" in gaps[sid_str]
        finally:
            db.delete(s_no_sig)
            db.delete(s_no_sig2)
            db.flush()

    def test_rankings_all_dimensions_present(self, client, db):
        from app.models.project import Project

        project = db.query(Project).first()
        s1 = _make_strategy(db, project.id, suffix="rank1")
        s2 = _make_strategy(db, project.id, suffix="rank2")
        _make_run(db, s1.id, run_name="Rank Run 1")
        _make_run(db, s2.id, run_name="Rank Run 2")
        try:
            resp = client.post(
                "/api/strategies/runs/compare-multi",
                json={"strategy_ids": [str(s1.id), str(s2.id)]},
            )
            assert resp.status_code == 200
            rankings = resp.json()["rankings"]
            for dim in (
                "by_backtest_trust",
                "by_data_health",
                "by_signal_quality",
                "by_reliability",
                "by_evidence_completeness",
            ):
                assert dim in rankings, f"missing ranking dimension: {dim}"
                assert len(rankings[dim]) == 2
        finally:
            db.delete(s1)
            db.delete(s2)
            db.flush()

    def test_item_evidence_fields_present(self, client, db):
        from app.models.project import Project

        project = db.query(Project).first()
        s1 = _make_strategy(db, project.id, suffix="itm1")
        s2 = _make_strategy(db, project.id, suffix="itm2")
        _make_run(db, s1.id, run_name="Item Run 1")
        _make_run(db, s2.id, run_name="Item Run 2")
        try:
            resp = client.post(
                "/api/strategies/runs/compare-multi",
                json={"strategy_ids": [str(s1.id), str(s2.id)]},
            )
            assert resp.status_code == 200
            items = resp.json()["items"]
            assert len(items) == 2
            for item in items:
                assert "evidence" in item
                assert "run_health_label" in item["evidence"]
                assert "metrics" in item
                assert "assumptions" in item
                assert "strategy_name" in item
                assert "run_name" in item
        finally:
            db.delete(s1)
            db.delete(s2)
            db.flush()
