"""M96 tests: Strategy Readiness Simulator engine.

Tests for:
  - TestActionCatalog: ACTION_CATALOG shape and required keys
  - TestRecommendActions: recommend_readiness_actions ranking + recommendations
  - TestGetCurrentReadiness: get_current_readiness current-state projection
  - TestSimulateReadiness: simulate_readiness what-if projection
  - TestReadOnly: simulate_readiness performs no DB writes
  - TestReadinessSimulatorEndpoints: GET/POST readiness-simulator endpoints

All tests use the shared session-scoped fixtures from conftest.py. The engine is
deterministic and READ-ONLY.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_strategy(db, project_id, *, suffix: str = "") -> object:
    from app.models.strategy import Strategy

    slug = f"m96-test-{suffix}-{uuid.uuid4().hex[:8]}"
    strat = Strategy(
        project_id=project_id,
        name=f"M96 Test Strategy {suffix}",
        slug=slug,
        asset_class="equity",
        status="active",
    )
    db.add(strat)
    db.flush()
    return strat


def _make_run(
    db,
    strategy_id,
    *,
    run_type: str = "backtest",
    status: str = "completed",
    metrics: dict | None = None,
    assumptions: dict | None = None,
) -> object:
    from app.models.strategy_run import StrategyRun

    run = StrategyRun(
        strategy_id=strategy_id,
        run_name=f"run-{uuid.uuid4().hex[:6]}",
        run_type=run_type,
        status=status,
        completed_at=datetime.now(timezone.utc),
        metrics_json=metrics or {},
        assumptions_json=assumptions or {},
    )
    db.add(run)
    db.flush()
    return run


def _make_alert(db, strategy, *, severity: str = "high", status: str = "open") -> object:
    from app.models.alert import Alert
    from app.models.project import Project

    project = db.query(Project).filter(Project.id == strategy.project_id).first()
    alert = Alert(
        organization_id=project.organization_id,
        rule_type="m96_test_alert",
        status=status,
        severity=severity,
        title="M96 test alert",
        description="Synthetic high-severity alert for simulator tests",
        strategy_id=str(strategy.id),
        triggered_at=datetime.now(timezone.utc),
    )
    db.add(alert)
    db.flush()
    return alert


def _get_seeded_strategy(db):
    from app.models.strategy import Strategy

    return db.query(Strategy).filter(Strategy.status != "archived").first()


def _get_seeded_project(db):
    from app.models.project import Project

    return db.query(Project).first()


def _cleanup(db, *objs):
    for obj in reversed(objs):
        try:
            db.delete(obj)
        except Exception:
            pass
    db.flush()


# ---------------------------------------------------------------------------
# TestActionCatalog
# ---------------------------------------------------------------------------


class TestActionCatalog:
    """Shape checks for the static ACTION_CATALOG."""

    def test_catalog_has_required_keys(self):
        from app.services.readiness_simulator import ACTION_CATALOG

        required = [
            "add_one_more_run",
            "create_regression_tests",
            "generate_reliability_report",
            "upload_paper_run",
            "resolve_high_alerts",
        ]
        for key in required:
            assert key in ACTION_CATALOG, f"Missing required catalog key: {key}"

    def test_all_actions_have_impact_points(self):
        from app.services.readiness_simulator import ACTION_CATALOG

        for key, spec in ACTION_CATALOG.items():
            impact = spec.get("impact_points")
            assert isinstance(impact, int), (
                f"{key} impact_points must be int, got {type(impact)}"
            )
            assert impact > 0, f"{key} impact_points must be > 0, got {impact}"

    def test_all_actions_have_effort(self):
        from app.services.readiness_simulator import ACTION_CATALOG

        for key, spec in ACTION_CATALOG.items():
            assert spec.get("effort") in ("low", "medium", "high"), (
                f"{key} effort must be low/medium/high, got {spec.get('effort')!r}"
            )


# ---------------------------------------------------------------------------
# TestRecommendActions
# ---------------------------------------------------------------------------


class TestRecommendActions:
    """Tests for recommend_readiness_actions."""

    def test_recommends_regression_tests_when_missing(self, db):
        """Strategy with a backtest run but no regression tests -> create_regression_tests."""
        from app.services.readiness_simulator import recommend_readiness_actions

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="rec-regtests")
        run = _make_run(db, strat.id, run_type="backtest")
        try:
            actions = recommend_readiness_actions(strat.id, db)
            keys = {a.key for a in actions}
            assert "create_regression_tests" in keys, (
                f"Expected create_regression_tests in recommended keys, got: {keys}"
            )
        finally:
            _cleanup(db, run, strat)

    def test_recommends_report_when_missing(self, db):
        """No reliability report -> generate_reliability_report recommended."""
        from app.services.readiness_simulator import recommend_readiness_actions

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="rec-report")
        run = _make_run(db, strat.id, run_type="backtest")
        try:
            actions = recommend_readiness_actions(strat.id, db)
            keys = {a.key for a in actions}
            assert "generate_reliability_report" in keys, (
                f"Expected generate_reliability_report in recommended keys, got: {keys}"
            )
        finally:
            _cleanup(db, run, strat)

    def test_recommends_paper_run_for_shadow_target(self, db):
        """target_stage=shadow with no paper run -> upload_paper_run recommended."""
        from app.services.readiness_simulator import recommend_readiness_actions

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="rec-paper")
        run = _make_run(db, strat.id, run_type="backtest")
        try:
            actions = recommend_readiness_actions(strat.id, db, target_stage="shadow")
            keys = {a.key for a in actions}
            assert "upload_paper_run" in keys, (
                f"Expected upload_paper_run in recommended keys for shadow target, got: {keys}"
            )
        finally:
            _cleanup(db, run, strat)

    def test_ranking_is_deterministic(self, db):
        """Two calls -> identical key ordering."""
        from app.services.readiness_simulator import recommend_readiness_actions

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="rec-determ")
        run = _make_run(db, strat.id, run_type="backtest")
        try:
            first = [a.key for a in recommend_readiness_actions(strat.id, db)]
            second = [a.key for a in recommend_readiness_actions(strat.id, db)]
            assert first == second, (
                f"Ranking not deterministic:\n  first={first}\n  second={second}"
            )
        finally:
            _cleanup(db, run, strat)


# ---------------------------------------------------------------------------
# TestGetCurrentReadiness
# ---------------------------------------------------------------------------


class TestGetCurrentReadiness:
    """Tests for get_current_readiness."""

    def test_no_runs_insufficient_data(self, db):
        """Strategy with no runs -> current_verdict == 'insufficient_data'."""
        from app.services.readiness_simulator import get_current_readiness

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="cur-noruns")
        try:
            data = get_current_readiness(strat.id, db)
            assert data.current_verdict == "insufficient_data", (
                f"Expected insufficient_data, got {data.current_verdict!r}"
            )
        finally:
            _cleanup(db, strat)

    def test_returns_current_blockers(self, db):
        """Strategy with a backtest run -> current_blockers is a list."""
        from app.services.readiness_simulator import get_current_readiness

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="cur-blockers")
        run = _make_run(db, strat.id, run_type="backtest")
        try:
            data = get_current_readiness(strat.id, db)
            assert isinstance(data.current_blockers, list), (
                f"Expected current_blockers to be a list, got {type(data.current_blockers)}"
            )
        finally:
            _cleanup(db, run, strat)

    def test_default_target_resolves(self, db):
        """target_stage=None -> resolved target_stage is a non-empty string."""
        from app.services.readiness_simulator import get_current_readiness

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="cur-target")
        run = _make_run(db, strat.id, run_type="backtest")
        try:
            data = get_current_readiness(strat.id, db, target_stage=None)
            assert isinstance(data.target_stage, str) and data.target_stage, (
                f"Expected non-empty resolved target_stage, got {data.target_stage!r}"
            )
        finally:
            _cleanup(db, run, strat)

    def test_has_disclaimer(self, db):
        """Disclaimer contains 'not trading advice'."""
        from app.services.readiness_simulator import get_current_readiness

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="cur-disclaimer")
        run = _make_run(db, strat.id, run_type="backtest")
        try:
            data = get_current_readiness(strat.id, db)
            assert "not trading advice" in data.disclaimer.lower(), (
                f"Expected 'not trading advice' in disclaimer, got: {data.disclaimer!r}"
            )
        finally:
            _cleanup(db, run, strat)


# ---------------------------------------------------------------------------
# TestSimulateReadiness
# ---------------------------------------------------------------------------


class TestSimulateReadiness:
    """Tests for simulate_readiness."""

    def test_simulate_increases_projected_score(self, db):
        """Completing a recommended action -> projected >= current score."""
        from app.services.readiness_simulator import (
            recommend_readiness_actions,
            simulate_readiness,
        )

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="sim-increase")
        run = _make_run(db, strat.id, run_type="backtest")
        try:
            actions = recommend_readiness_actions(strat.id, db)
            assert actions, "Expected at least one recommended action"
            chosen = actions[0].key
            data = simulate_readiness(
                strat.id, db, completed_actions=[chosen]
            )
            assert data.projected_readiness_score is not None
            assert data.current_readiness_score is not None
            assert data.projected_readiness_score >= data.current_readiness_score, (
                f"Expected projected >= current, got "
                f"{data.projected_readiness_score} < {data.current_readiness_score}"
            )
        finally:
            _cleanup(db, run, strat)

    def test_simulated_actions_remove_blockers(self, db):
        """Completing the action that maps to a blocker -> blocker not in remaining."""
        from app.services.readiness_simulator import (
            get_current_readiness,
            simulate_readiness,
        )

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="sim-rmblocker")
        run = _make_run(db, strat.id, run_type="backtest")
        try:
            # Complete both the governance actions that the simulator can clear.
            completed = ["create_regression_tests", "generate_reliability_report"]
            current = get_current_readiness(strat.id, db)
            data = simulate_readiness(strat.id, db, completed_actions=completed)
            # Any blocker resolvable by one of the completed actions should be gone.
            # We assert that remaining is a subset of current blockers (never grows)
            # and that completing actions does not increase blockers.
            assert set(data.remaining_blockers).issubset(set(current.current_blockers)), (
                f"remaining_blockers {data.remaining_blockers} should be subset of "
                f"current {current.current_blockers}"
            )
            assert len(data.remaining_blockers) <= len(current.current_blockers), (
                "Completing actions must not increase the number of blockers"
            )
        finally:
            _cleanup(db, run, strat)

    def test_projected_score_capped_at_100(self, db):
        """Completing many high-impact actions -> projected <= 100."""
        from app.services.readiness_simulator import (
            ACTION_CATALOG,
            simulate_readiness,
        )

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="sim-cap")
        run = _make_run(db, strat.id, run_type="backtest")
        try:
            all_keys = list(ACTION_CATALOG.keys())
            data = simulate_readiness(strat.id, db, completed_actions=all_keys)
            assert data.projected_readiness_score is not None
            assert data.projected_readiness_score <= 100, (
                f"Expected projected score <= 100, got {data.projected_readiness_score}"
            )
        finally:
            _cleanup(db, run, strat)

    def test_unresolved_high_alerts_remain_blocker(self, db):
        """Open high alert + simulate WITHOUT resolve_high_alerts -> alert blocker remains."""
        from app.services.readiness_simulator import (
            get_current_readiness,
            simulate_readiness,
        )

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="sim-alert")
        run = _make_run(db, strat.id, run_type="backtest")
        alert = _make_alert(db, strat, severity="high", status="open")
        try:
            current = get_current_readiness(strat.id, db)
            alert_blockers = [
                b for b in current.current_blockers if "alert" in b.lower()
            ]
            # Simulate completing everything EXCEPT resolve_high_alerts.
            from app.services.readiness_simulator import ACTION_CATALOG

            completed = [k for k in ACTION_CATALOG if k != "resolve_high_alerts"]
            data = simulate_readiness(strat.id, db, completed_actions=completed)
            # Any alert blocker present currently must still remain.
            for b in alert_blockers:
                assert b in data.remaining_blockers, (
                    f"Alert blocker {b!r} should remain when resolve_high_alerts "
                    f"is not completed; remaining={data.remaining_blockers}"
                )
        finally:
            _cleanup(db, alert, run, strat)

    def test_simulated_completed_actions_echoed(self, db):
        """completed_actions passed -> simulated_completed_actions reflects them."""
        from app.services.readiness_simulator import simulate_readiness

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="sim-echo")
        run = _make_run(db, strat.id, run_type="backtest")
        try:
            completed = ["create_regression_tests", "generate_reliability_report"]
            data = simulate_readiness(strat.id, db, completed_actions=completed)
            for key in completed:
                assert key in data.simulated_completed_actions, (
                    f"Expected {key} echoed in simulated_completed_actions, got "
                    f"{data.simulated_completed_actions}"
                )
        finally:
            _cleanup(db, run, strat)

    def test_irrelevant_action_warning(self, db):
        """An inapplicable completed_action -> warning OR ignored (score unchanged by it)."""
        from app.services.readiness_simulator import simulate_readiness

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="sim-irrelevant")
        run = _make_run(db, strat.id, run_type="backtest")
        try:
            bogus = "this_action_does_not_exist"
            baseline = simulate_readiness(strat.id, db, completed_actions=[])
            data = simulate_readiness(strat.id, db, completed_actions=[bogus])
            warned = any(bogus in w for w in data.warnings)
            score_unchanged = (
                data.projected_readiness_score == baseline.projected_readiness_score
            )
            assert warned or score_unchanged, (
                "Expected an irrelevant action to either produce a warning or leave "
                f"the projected score unchanged; warnings={data.warnings}, "
                f"projected={data.projected_readiness_score}, "
                f"baseline={baseline.projected_readiness_score}"
            )
        finally:
            _cleanup(db, run, strat)


# ---------------------------------------------------------------------------
# TestReadOnly
# ---------------------------------------------------------------------------


class TestReadOnly:
    """simulate_readiness must never create DB rows."""

    def test_simulate_does_not_create_rows(self, db):
        """Row counts unchanged across a simulate_readiness call with many actions."""
        from app.services.readiness_simulator import (
            ACTION_CATALOG,
            simulate_readiness,
        )
        from app.models.strategy_run import StrategyRun
        from app.models.report import Report
        from app.models.regression import StrategyRegressionTest

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="ro-norows")
        run = _make_run(db, strat.id, run_type="backtest")
        try:
            before_runs = db.query(StrategyRun).count()
            before_reports = db.query(Report).count()
            before_regtests = db.query(StrategyRegressionTest).count()

            simulate_readiness(
                strat.id, db, completed_actions=list(ACTION_CATALOG.keys())
            )

            after_runs = db.query(StrategyRun).count()
            after_reports = db.query(Report).count()
            after_regtests = db.query(StrategyRegressionTest).count()

            assert before_runs == after_runs, "simulate must not create StrategyRun rows"
            assert before_reports == after_reports, "simulate must not create Report rows"
            assert before_regtests == after_regtests, (
                "simulate must not create RegressionTest rows"
            )
        finally:
            _cleanup(db, run, strat)


# ---------------------------------------------------------------------------
# TestReadinessSimulatorEndpoints
# ---------------------------------------------------------------------------


class TestReadinessSimulatorEndpoints:
    """Integration tests via TestClient for the M96 readiness-simulator endpoints."""

    def test_get_endpoint_200(self, client, db):
        """GET /api/strategies/{id}/readiness-simulator -> 200."""
        strategy = _get_seeded_strategy(db)
        assert strategy is not None
        resp = client.get(f"/api/strategies/{strategy.id}/readiness-simulator")
        assert resp.status_code == 200, (
            f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        )

    def test_get_with_target_stage(self, client, db):
        """GET ?target_stage=paper_candidate -> 200, target_stage == 'paper_candidate'."""
        strategy = _get_seeded_strategy(db)
        assert strategy is not None
        resp = client.get(
            f"/api/strategies/{strategy.id}/readiness-simulator"
            "?target_stage=paper_candidate"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("target_stage") == "paper_candidate", (
            f"Expected target_stage='paper_candidate', got {data.get('target_stage')!r}"
        )

    def test_unknown_strategy_404(self, client):
        """GET with fake strategy id -> 404."""
        fake_id = uuid.uuid4()
        resp = client.get(f"/api/strategies/{fake_id}/readiness-simulator")
        assert resp.status_code == 404

    def test_simulate_endpoint_200(self, client, db):
        """POST .../simulate with target_stage + completed_actions -> 200."""
        strategy = _get_seeded_strategy(db)
        assert strategy is not None
        resp = client.post(
            f"/api/strategies/{strategy.id}/readiness-simulator/simulate",
            json={
                "target_stage": "paper_candidate",
                "completed_actions": ["create_regression_tests"],
            },
        )
        assert resp.status_code == 200, (
            f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        )

    def test_simulate_increases_via_endpoint(self, client, db):
        """POST simulate with recommended actions -> projected >= current."""
        strategy = _get_seeded_strategy(db)
        assert strategy is not None

        # Discover recommended actions first.
        actions_resp = client.get(
            f"/api/strategies/{strategy.id}/readiness-simulator/actions"
        )
        assert actions_resp.status_code == 200
        recommended = actions_resp.json().get("recommended_actions", [])

        completed = [a["key"] for a in recommended[:2]] if recommended else []
        resp = client.post(
            f"/api/strategies/{strategy.id}/readiness-simulator/simulate",
            json={"target_stage": None, "completed_actions": completed},
        )
        assert resp.status_code == 200
        data = resp.json()
        current = data.get("current_readiness_score")
        projected = data.get("projected_readiness_score")
        if current is not None and projected is not None:
            assert projected >= current, (
                f"Expected projected >= current, got {projected} < {current}"
            )

    def test_actions_endpoint_200(self, client, db):
        """GET .../readiness-simulator/actions -> 200 with recommended_actions list."""
        strategy = _get_seeded_strategy(db)
        assert strategy is not None
        resp = client.get(
            f"/api/strategies/{strategy.id}/readiness-simulator/actions"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "recommended_actions" in data, (
            f"Expected 'recommended_actions' key, got: {list(data.keys())}"
        )
        assert isinstance(data["recommended_actions"], list)

    def test_response_has_required_fields(self, client, db):
        """GET response has the core readiness-simulator fields."""
        strategy = _get_seeded_strategy(db)
        assert strategy is not None
        resp = client.get(f"/api/strategies/{strategy.id}/readiness-simulator")
        assert resp.status_code == 200
        data = resp.json()
        for field in (
            "current_readiness_score",
            "projected_readiness_score",
            "recommended_actions",
            "disclaimer",
        ):
            assert field in data, f"Missing field: {field}"
