"""M53 tests: Strategy Regression Tests.

Tests for:
  - POST /api/strategies/{id}/regression-tests/defaults — create default tests (idempotent)
  - GET  /api/strategies/{id}/regression-tests          — list tests
  - POST /api/strategies/{id}/regression-tests/run      — run tests
  - GET  /api/strategies/{id}/regression-tests/runs     — list runs
  - GET  /api/regression-test-runs/{id}                 — get run detail
  - Evaluation logic for metric delta, alert_state, evidence thresholds
  - Language policy: no AI/strategy-failed/do-not-trade language
  - AuditTimelineEvent created on run

All tests use shared session-scoped fixtures from conftest.py.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_seeded_strategy(db):
    from app.models.strategy import Strategy

    return db.query(Strategy).filter(Strategy.status != "archived").first()


def _get_seeded_org(db):
    from app.models.organization import Organization

    return db.query(Organization).first()


def _get_seeded_project(db):
    from app.models.project import Project

    return db.query(Project).first()


def _make_strategy(db, project_id, *, suffix: str = "") -> object:
    from app.models.strategy import Strategy

    slug = f"m53-test-{suffix}-{uuid.uuid4().hex[:8]}"
    strat = Strategy(
        project_id=project_id,
        name=f"M53 Test {suffix}",
        slug=slug,
        asset_class="equity",
        status="active",
    )
    db.add(strat)
    db.flush()
    return strat


def _make_run(
    db, strategy_id, *, run_type: str = "backtest", metrics_json: dict | None = None
) -> object:
    from app.models.strategy_run import StrategyRun

    run = StrategyRun(
        strategy_id=strategy_id,
        run_name=f"run-{uuid.uuid4().hex[:6]}",
        run_type=run_type,
        status="completed",
        metrics_json=metrics_json,
    )
    db.add(run)
    db.flush()
    return run


def _make_alert(
    db, org_id, strategy_id, *, severity: str = "high", status: str = "open"
) -> object:
    from app.models.alert import Alert

    a = Alert(
        organization_id=str(org_id),
        strategy_id=str(strategy_id),
        rule_type="test_m53_rule",
        status=status,
        severity=severity,
        title=f"M53 test alert {severity}",
        triggered_at=datetime.now(timezone.utc),
    )
    db.add(a)
    db.flush()
    return a


def _make_backtest_audit(db, run_id, *, trust_score: int = 80) -> object:
    from app.models.backtest_audit import BacktestAudit

    audit = BacktestAudit(
        strategy_run_id=run_id,
        trust_score=trust_score,
        overall_status="good" if trust_score >= 70 else "weak",
        summary=f"M53 test audit ts={trust_score}",
    )
    db.add(audit)
    db.flush()
    return audit


def _make_dataset_snapshot(db, strategy_id, dataset_id, *, health_score: int = 85) -> object:
    from app.models.dataset_snapshot import DatasetSnapshot

    snap = DatasetSnapshot(
        dataset_id=dataset_id,
        version_label=f"v{uuid.uuid4().hex[:6]}",
        health_score=health_score,
        row_count=1000,
    )
    db.add(snap)
    db.flush()
    return snap


def _get_or_create_dataset(db, project_id):
    from app.models.dataset import Dataset

    ds = db.query(Dataset).first()
    if ds is None:
        ds = Dataset(
            project_id=project_id,
            name="M53 Test Dataset",
            dataset_type="ohlcv",
            source_type="manual",
        )
        db.add(ds)
        db.flush()
    return ds


# ---------------------------------------------------------------------------
# TestRegressionTestSetup
# ---------------------------------------------------------------------------


class TestRegressionTestSetup:
    """Test creation and listing of regression test definitions."""

    def test_defaults_endpoint_creates_tests(self, client, db):
        strategy = _get_seeded_strategy(db)
        assert strategy is not None
        resp = client.post(
            f"/api/strategies/{strategy.id}/regression-tests/defaults"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 10, f"Expected >= 10 default tests, got {len(data)}"
        keys = {t["test_key"] for t in data}
        assert "sharpe_drop_limit" in keys
        assert "no_high_critical_alerts" in keys
        assert "readiness_not_blocked" in keys

    def test_defaults_idempotent(self, client, db):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="idempotent")
        try:
            resp1 = client.post(
                f"/api/strategies/{strat.id}/regression-tests/defaults"
            )
            assert resp1.status_code == 200
            count1 = len(resp1.json())

            resp2 = client.post(
                f"/api/strategies/{strat.id}/regression-tests/defaults"
            )
            assert resp2.status_code == 200
            count2 = len(resp2.json())

            assert count1 == count2, "Second call should return same count as first"
        finally:
            from app.models.regression import StrategyRegressionTest
            db.query(StrategyRegressionTest).filter(
                StrategyRegressionTest.strategy_id == strat.id
            ).delete()
            db.delete(strat)
            db.flush()

    def test_list_tests(self, client, db):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="list-tests")
        try:
            # Create defaults first
            client.post(f"/api/strategies/{strat.id}/regression-tests/defaults")
            # List them
            resp = client.get(f"/api/strategies/{strat.id}/regression-tests")
            assert resp.status_code == 200
            data = resp.json()
            assert isinstance(data, list)
            assert len(data) >= 10
        finally:
            from app.models.regression import StrategyRegressionTest
            db.query(StrategyRegressionTest).filter(
                StrategyRegressionTest.strategy_id == strat.id
            ).delete()
            db.delete(strat)
            db.flush()

    def test_unknown_strategy_404(self, client):
        fake_id = uuid.uuid4()
        resp = client.post(f"/api/strategies/{fake_id}/regression-tests/defaults")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# TestRegressionTestRun
# ---------------------------------------------------------------------------


class TestRegressionTestRun:
    """Test running regression tests and verifying results."""

    def test_run_insufficient_evidence_no_runs(self, client, db):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="no-runs")
        try:
            client.post(f"/api/strategies/{strat.id}/regression-tests/defaults")
            resp = client.post(
                f"/api/strategies/{strat.id}/regression-tests/run",
                json={"mode": "latest_vs_previous"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["overall_status"] == "insufficient_evidence"
        finally:
            _cleanup_strategy(db, strat.id)

    def test_run_latest_vs_previous_success(self, client, db):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="two-runs")
        run1 = run2 = None
        try:
            run1 = _make_run(
                db, strat.id,
                metrics_json={"sharpe": 1.2, "max_drawdown": 0.10},
            )
            run2 = _make_run(
                db, strat.id,
                metrics_json={"sharpe": 1.1, "max_drawdown": 0.11},
            )
            client.post(f"/api/strategies/{strat.id}/regression-tests/defaults")
            resp = client.post(
                f"/api/strategies/{strat.id}/regression-tests/run",
                json={"mode": "latest_vs_previous"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["overall_status"] in (
                "passed", "failed", "warning", "insufficient_evidence"
            )
            assert isinstance(data["results"], list)
        finally:
            _cleanup_strategy(db, strat.id)

    def test_run_selected_validates_ownership(self, client, db):
        project = _get_seeded_project(db)
        strat_a = _make_strategy(db, project.id, suffix="owner-a")
        strat_b = _make_strategy(db, project.id, suffix="owner-b")
        run_b = None
        try:
            # Create defaults for strat_a
            client.post(f"/api/strategies/{strat_a.id}/regression-tests/defaults")
            # Create a run for strat_b
            run_b = _make_run(db, strat_b.id)
            run_a = _make_run(db, strat_a.id)
            # Try to run strat_a tests with a run from strat_b
            resp = client.post(
                f"/api/strategies/{strat_a.id}/regression-tests/run",
                json={
                    "mode": "selected_runs",
                    "baseline_run_id": str(run_b.id),
                    "comparison_run_id": str(run_a.id),
                },
            )
            # Should return 200 but with insufficient_evidence (run not found for strategy)
            # OR 400 — either is acceptable
            assert resp.status_code in (200, 400)
            if resp.status_code == 200:
                assert resp.json()["overall_status"] == "insufficient_evidence"
        finally:
            _cleanup_strategy(db, strat_a.id)
            _cleanup_strategy(db, strat_b.id)

    def test_run_timeline_event_created(self, client, db):
        from app.models.audit_timeline_event import AuditTimelineEvent

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="timeline-evt")
        try:
            client.post(f"/api/strategies/{strat.id}/regression-tests/defaults")
            before = (
                db.query(AuditTimelineEvent)
                .filter(
                    AuditTimelineEvent.strategy_id == strat.id,
                    AuditTimelineEvent.event_type == "regression_tests_run",
                )
                .count()
            )
            resp = client.post(
                f"/api/strategies/{strat.id}/regression-tests/run",
                json={"mode": "latest_vs_previous"},
            )
            assert resp.status_code == 200
            # Must expire/refresh to pick up committed changes
            db.expire_all()
            after = (
                db.query(AuditTimelineEvent)
                .filter(
                    AuditTimelineEvent.strategy_id == strat.id,
                    AuditTimelineEvent.event_type == "regression_tests_run",
                )
                .count()
            )
            assert after == before + 1, "Expected one new regression_tests_run timeline event"
        finally:
            _cleanup_strategy(db, strat.id)

    def test_run_persists_results(self, client, db):
        from app.models.regression import StrategyRegressionTestRun, StrategyRegressionTestResult

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="persist-results")
        try:
            _make_run(db, strat.id)
            _make_run(db, strat.id)
            client.post(f"/api/strategies/{strat.id}/regression-tests/defaults")
            resp = client.post(
                f"/api/strategies/{strat.id}/regression-tests/run",
                json={"mode": "latest_vs_previous"},
            )
            assert resp.status_code == 200
            run_id = resp.json()["id"]
            db.expire_all()
            results = (
                db.query(StrategyRegressionTestResult)
                .join(
                    StrategyRegressionTestRun,
                    StrategyRegressionTestResult.test_run_id == StrategyRegressionTestRun.id,
                )
                .filter(StrategyRegressionTestRun.id == uuid.UUID(run_id))
                .all()
            )
            assert len(results) > 0, "Expected persisted test results"
        finally:
            _cleanup_strategy(db, strat.id)


# ---------------------------------------------------------------------------
# TestRegressionEvaluation
# ---------------------------------------------------------------------------


class TestRegressionEvaluation:
    """Test evaluation logic for specific tests."""

    def test_sharpe_drop_fails(self, client, db):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="sharpe-fail")
        try:
            # baseline sharpe=2.0, comparison sharpe=1.0 → drop > 20%
            _make_run(db, strat.id, metrics_json={"sharpe": 2.0})
            _make_run(db, strat.id, metrics_json={"sharpe": 1.0})
            client.post(f"/api/strategies/{strat.id}/regression-tests/defaults")
            resp = client.post(
                f"/api/strategies/{strat.id}/regression-tests/run",
                json={"mode": "latest_vs_previous"},
            )
            assert resp.status_code == 200
            data = resp.json()
            results = data["results"]
            sharpe_result = next(
                (r for r in results if r["test_key"] == "sharpe_drop_limit"), None
            )
            assert sharpe_result is not None
            assert sharpe_result["status"] == "failed", (
                f"Expected sharpe_drop_limit to fail, got {sharpe_result['status']}"
            )
        finally:
            _cleanup_strategy(db, strat.id)

    def test_sharpe_stable_passes(self, client, db):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="sharpe-pass")
        try:
            # baseline sharpe=2.0, comparison sharpe=1.95 → drop < 20%
            _make_run(db, strat.id, metrics_json={"sharpe": 2.0})
            _make_run(db, strat.id, metrics_json={"sharpe": 1.95})
            client.post(f"/api/strategies/{strat.id}/regression-tests/defaults")
            resp = client.post(
                f"/api/strategies/{strat.id}/regression-tests/run",
                json={"mode": "latest_vs_previous"},
            )
            assert resp.status_code == 200
            data = resp.json()
            results = data["results"]
            sharpe_result = next(
                (r for r in results if r["test_key"] == "sharpe_drop_limit"), None
            )
            assert sharpe_result is not None
            assert sharpe_result["status"] == "passed", (
                f"Expected sharpe_drop_limit to pass, got {sharpe_result['status']}"
            )
        finally:
            _cleanup_strategy(db, strat.id)

    def test_high_alert_fails_alert_test(self, client, db):
        project = _get_seeded_project(db)
        org = _get_seeded_org(db)
        strat = _make_strategy(db, project.id, suffix="alert-fail")
        alert = None
        try:
            _make_run(db, strat.id)
            _make_run(db, strat.id)
            alert = _make_alert(db, org.id, strat.id, severity="high", status="open")
            client.post(f"/api/strategies/{strat.id}/regression-tests/defaults")
            resp = client.post(
                f"/api/strategies/{strat.id}/regression-tests/run",
                json={"mode": "latest_vs_previous"},
            )
            assert resp.status_code == 200
            data = resp.json()
            results = data["results"]
            alert_result = next(
                (r for r in results if r["test_key"] == "no_high_critical_alerts"), None
            )
            assert alert_result is not None
            assert alert_result["status"] == "failed", (
                f"Expected no_high_critical_alerts to fail, got {alert_result['status']}"
            )
        finally:
            if alert:
                db.delete(alert)
                db.flush()
            _cleanup_strategy(db, strat.id)

    def test_no_alerts_passes(self, client, db):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="no-alert-pass")
        try:
            _make_run(db, strat.id)
            _make_run(db, strat.id)
            client.post(f"/api/strategies/{strat.id}/regression-tests/defaults")
            resp = client.post(
                f"/api/strategies/{strat.id}/regression-tests/run",
                json={"mode": "latest_vs_previous"},
            )
            assert resp.status_code == 200
            data = resp.json()
            results = data["results"]
            alert_result = next(
                (r for r in results if r["test_key"] == "no_high_critical_alerts"), None
            )
            assert alert_result is not None
            assert alert_result["status"] == "passed", (
                f"Expected no_high_critical_alerts to pass, got {alert_result['status']}"
            )
        finally:
            _cleanup_strategy(db, strat.id)

    def test_dataset_health_threshold(self, client, db):
        """Run with low dataset health → dataset_health_minimum fails."""
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="ds-health-fail")
        try:
            ds = _get_or_create_dataset(db, project.id)
            snap = _make_dataset_snapshot(db, strat.id, ds.id, health_score=40)
            run1 = _make_run(db, strat.id)
            run2 = _make_run(db, strat.id)
            # Link low-health snapshot to run2 (comparison)
            run2.dataset_snapshot_id = snap.id
            db.flush()
            client.post(f"/api/strategies/{strat.id}/regression-tests/defaults")
            resp = client.post(
                f"/api/strategies/{strat.id}/regression-tests/run",
                json={"mode": "latest_vs_previous"},
            )
            assert resp.status_code == 200
            data = resp.json()
            results = data["results"]
            ds_result = next(
                (r for r in results if r["test_key"] == "dataset_health_minimum"), None
            )
            assert ds_result is not None
            assert ds_result["status"] == "failed", (
                f"Expected dataset_health_minimum to fail with score 40, got {ds_result['status']}"
            )
        finally:
            _cleanup_strategy(db, strat.id)

    def test_backtest_trust_threshold(self, client, db):
        """Run with low backtest trust → backtest_trust_minimum fails."""
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="bt-trust-fail")
        try:
            run1 = _make_run(db, strat.id)
            run2 = _make_run(db, strat.id)
            # Add low-trust audit to run2 (comparison = most recent)
            _make_backtest_audit(db, run2.id, trust_score=40)
            client.post(f"/api/strategies/{strat.id}/regression-tests/defaults")
            resp = client.post(
                f"/api/strategies/{strat.id}/regression-tests/run",
                json={"mode": "latest_vs_previous"},
            )
            assert resp.status_code == 200
            data = resp.json()
            results = data["results"]
            bt_result = next(
                (r for r in results if r["test_key"] == "backtest_trust_minimum"), None
            )
            assert bt_result is not None
            assert bt_result["status"] == "failed", (
                f"Expected backtest_trust_minimum to fail with trust_score=40, got {bt_result['status']}"
            )
        finally:
            _cleanup_strategy(db, strat.id)


# ---------------------------------------------------------------------------
# TestRegressionRunAPI
# ---------------------------------------------------------------------------


class TestRegressionRunAPI:
    """Test list/detail API endpoints for regression test runs."""

    def test_list_runs(self, client, db):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="list-runs")
        try:
            client.post(f"/api/strategies/{strat.id}/regression-tests/defaults")
            client.post(
                f"/api/strategies/{strat.id}/regression-tests/run",
                json={"mode": "latest_vs_previous"},
            )
            resp = client.get(f"/api/strategies/{strat.id}/regression-tests/runs")
            assert resp.status_code == 200
            data = resp.json()
            assert "items" in data
            assert "total" in data
            assert isinstance(data["items"], list)
            assert data["total"] >= 1
        finally:
            _cleanup_strategy(db, strat.id)

    def test_get_run_detail(self, client, db):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="get-detail")
        try:
            client.post(f"/api/strategies/{strat.id}/regression-tests/defaults")
            run_resp = client.post(
                f"/api/strategies/{strat.id}/regression-tests/run",
                json={"mode": "latest_vs_previous"},
            )
            assert run_resp.status_code == 200
            run_id = run_resp.json()["id"]

            detail_resp = client.get(f"/api/regression-test-runs/{run_id}")
            assert detail_resp.status_code == 200
            detail = detail_resp.json()
            assert detail["id"] == run_id
            assert "results" in detail
            assert isinstance(detail["results"], list)
        finally:
            _cleanup_strategy(db, strat.id)

    def test_run_overall_status_failed(self, client, db):
        """A required test that fails should set overall_status to 'failed'."""
        project = _get_seeded_project(db)
        org = _get_seeded_org(db)
        strat = _make_strategy(db, project.id, suffix="status-failed")
        alert = None
        try:
            _make_run(db, strat.id, metrics_json={"sharpe": 2.0})
            _make_run(db, strat.id, metrics_json={"sharpe": 1.0})
            # Required test: no_high_critical_alerts
            alert = _make_alert(db, org.id, strat.id, severity="high", status="open")
            client.post(f"/api/strategies/{strat.id}/regression-tests/defaults")
            resp = client.post(
                f"/api/strategies/{strat.id}/regression-tests/run",
                json={"mode": "latest_vs_previous"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["overall_status"] == "failed", (
                f"Expected 'failed', got {data['overall_status']!r}"
            )
            assert data["required_failed_count"] > 0
        finally:
            if alert:
                db.delete(alert)
                db.flush()
            _cleanup_strategy(db, strat.id)

    def test_run_overall_status_passed(self, client, db):
        """All required tests passing → overall_status passed (or warning for optional)."""
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="status-pass")
        try:
            # Runs with stable metrics
            _make_run(db, strat.id, metrics_json={"sharpe": 1.5, "max_drawdown": 0.10})
            _make_run(db, strat.id, metrics_json={"sharpe": 1.5, "max_drawdown": 0.10})
            client.post(f"/api/strategies/{strat.id}/regression-tests/defaults")
            resp = client.post(
                f"/api/strategies/{strat.id}/regression-tests/run",
                json={"mode": "latest_vs_previous"},
            )
            assert resp.status_code == 200
            data = resp.json()
            # With stable metrics and no alerts, required tests should pass
            assert data["overall_status"] in ("passed", "warning", "insufficient_evidence"), (
                f"Got unexpected status: {data['overall_status']!r}"
            )
        finally:
            _cleanup_strategy(db, strat.id)

    def test_no_forbidden_language(self, client, db):
        """deterministic_summary must not contain forbidden AI/trading language."""
        forbidden = ["AI", "strategy failed", "do not trade"]
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="no-forbidden")
        try:
            client.post(f"/api/strategies/{strat.id}/regression-tests/defaults")
            resp = client.post(
                f"/api/strategies/{strat.id}/regression-tests/run",
                json={"mode": "latest_vs_previous"},
            )
            assert resp.status_code == 200
            data = resp.json()
            summary = (data.get("deterministic_summary") or "").lower()
            for phrase in forbidden:
                assert phrase.lower() not in summary, (
                    f"Forbidden phrase '{phrase}' found in summary: {summary!r}"
                )
        finally:
            _cleanup_strategy(db, strat.id)


# ---------------------------------------------------------------------------
# Cleanup helper
# ---------------------------------------------------------------------------


def _cleanup_strategy(db, strategy_id):
    """Remove all regression test data and the strategy itself."""
    from app.models.regression import (
        StrategyRegressionTest,
        StrategyRegressionTestRun,
        StrategyRegressionTestResult,
    )
    from app.models.strategy_run import StrategyRun
    from app.models.strategy import Strategy
    from app.models.audit_timeline_event import AuditTimelineEvent

    try:
        # Results are cascade-deleted with test runs
        db.query(StrategyRegressionTestResult).filter(
            StrategyRegressionTestResult.test_run_id.in_(
                db.query(StrategyRegressionTestRun.id).filter(
                    StrategyRegressionTestRun.strategy_id == strategy_id
                )
            )
        ).delete(synchronize_session=False)
        db.query(StrategyRegressionTestRun).filter(
            StrategyRegressionTestRun.strategy_id == strategy_id
        ).delete()
        db.query(StrategyRegressionTest).filter(
            StrategyRegressionTest.strategy_id == strategy_id
        ).delete()
        db.query(AuditTimelineEvent).filter(
            AuditTimelineEvent.strategy_id == strategy_id
        ).delete()
        strat = db.query(Strategy).filter(Strategy.id == strategy_id).first()
        if strat is not None:
            db.delete(strat)
        db.flush()
    except Exception:
        db.rollback()
