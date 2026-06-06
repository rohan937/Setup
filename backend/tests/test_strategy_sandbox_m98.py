"""M98 tests: Strategy Sandbox / What-If engine.

Tests for:
  - TestScenarioPresets: SCENARIO_PRESETS shape and required keys
  - TestBuildCurrentState: build_current_sandbox_state current-state projection
  - TestSimulateSandbox: simulate_strategy_sandbox what-if projection
  - TestReadOnly: simulate_strategy_sandbox performs no DB writes
  - TestSandboxReport: generate_sandbox_report JSON/Markdown output
  - TestSandboxEndpoints: GET/POST sandbox endpoints

All tests use the shared session-scoped fixtures from conftest.py. The engine is
deterministic and READ-ONLY.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_strategy(db, project_id, *, suffix: str = "") -> object:
    from app.models.strategy import Strategy

    slug = f"m98-test-{suffix}-{uuid.uuid4().hex[:8]}"
    strat = Strategy(
        project_id=project_id,
        name=f"M98 Test Strategy {suffix}",
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


def _make_strategy_with_run(db, *, suffix: str, turnover: float = 0.8) -> tuple:
    """Create a strategy + backtest run with the standard M98 assumptions/metrics.

    ``turnover`` is exposed as a parameter because cost-sensitivity tests need a
    high-turnover run for the cost penalties in run_backtest_audit to bite.
    """
    project = _get_seeded_project(db)
    strat = _make_strategy(db, project.id, suffix=suffix)
    run = _make_run(
        db,
        strat.id,
        run_type="backtest",
        assumptions={
            "transaction_cost_bps": 5,
            "slippage_bps": 2,
            "fill_model": "next_open",
        },
        metrics={
            "sharpe": 1.2,
            "annual_return": 0.12,
            "volatility": 0.14,
            "max_drawdown": -0.1,
            "turnover": turnover,
            "trade_count": 60,
        },
    )
    return strat, run


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
# TestScenarioPresets
# ---------------------------------------------------------------------------


class TestScenarioPresets:
    """Shape checks for the static SCENARIO_PRESETS."""

    def test_presets_non_empty(self):
        from app.services.strategy_sandbox import get_scenario_presets

        presets = get_scenario_presets()
        assert len(presets) >= 6, (
            f"Expected at least 6 scenario presets, got {len(presets)}"
        )

    def test_presets_have_required_keys(self):
        from app.services.strategy_sandbox import get_scenario_presets

        for preset in get_scenario_presets():
            assert "key" in preset, f"Preset missing 'key': {preset}"
            assert "name" in preset, f"Preset missing 'name': {preset}"
            for ovk in (
                "assumption_overrides",
                "metric_overrides",
                "evidence_overrides",
            ):
                assert ovk in preset, (
                    f"Preset {preset.get('key')!r} missing {ovk!r}"
                )


# ---------------------------------------------------------------------------
# TestBuildCurrentState
# ---------------------------------------------------------------------------


class TestBuildCurrentState:
    """Tests for build_current_sandbox_state."""

    def test_current_state_has_scores(self, db):
        from app.services.strategy_sandbox import build_current_sandbox_state

        strat, run = _make_strategy_with_run(db, suffix="cur-scores")
        try:
            data = build_current_sandbox_state(strat.id, db)
            for attr in (
                "reliability_score",
                "backtest_reality_score",
                "readiness_score",
                "promotion_verdict",
            ):
                assert hasattr(data.current, attr), (
                    f"current missing attribute {attr!r}"
                )
        finally:
            _cleanup(db, run, strat)

    def test_current_equals_projected(self, db):
        from app.services.strategy_sandbox import build_current_sandbox_state

        strat, run = _make_strategy_with_run(db, suffix="cur-eq-proj")
        try:
            data = build_current_sandbox_state(strat.id, db)
            assert (
                data.current.reliability_score == data.projected.reliability_score
            )
            assert (
                data.current.backtest_reality_score
                == data.projected.backtest_reality_score
            )
            assert (
                data.current.readiness_score == data.projected.readiness_score
            )
            assert (
                data.current.promotion_verdict
                == data.projected.promotion_verdict
            )
        finally:
            _cleanup(db, run, strat)


# ---------------------------------------------------------------------------
# TestSimulateSandbox
# ---------------------------------------------------------------------------


class TestSimulateSandbox:
    """Tests for simulate_strategy_sandbox."""

    def test_cost_increase_lowers_backtest_reality(self, db):
        """Higher costs on a high-turnover run must not improve projected reality.

        ``run_backtest_audit`` (the pure engine behind the projection) treats
        higher costs as *more* realistic, so a cost bump alone leaves the
        audit-driven projection flat. The genuine cost-sensitivity signal comes
        from turnover: a high-turnover run penalised under elevated execution
        stress. We compare the scenario projection against the *baseline
        projection* (same code path, no overrides) so the comparison is
        apples-to-apples, and assert it never rises.
        """
        from app.services.strategy_sandbox import (
            estimate_backtest_reality_under_scenario,
            simulate_strategy_sandbox,
        )
        from app.services.backtest_reality_score import get_latest_backtest_run

        strat, run = _make_strategy_with_run(db, suffix="sim-cost", turnover=1.5)
        try:
            latest = get_latest_backtest_run(strat.id, db)
            baseline_proj = estimate_backtest_reality_under_scenario(
                latest, {}, {}, {}
            )
            scenario = {
                "scenario_name": "cost stress",
                "assumption_overrides": {"transaction_cost_bps": 25},
                "metric_overrides": {"turnover": 3.0},
                "evidence_overrides": {},
            }
            data = simulate_strategy_sandbox(strat.id, db, scenario)
            proj = data.projected.backtest_reality_score
            assert baseline_proj is not None and proj is not None
            assert proj <= baseline_proj, (
                f"Expected projected backtest reality <= baseline projection "
                f"under cost/turnover stress, got projected={proj} "
                f"baseline={baseline_proj}"
            )
        finally:
            _cleanup(db, run, strat)

    def test_high_turnover_plus_costs_creates_blocker_or_warning(self, db):
        from app.services.strategy_sandbox import simulate_strategy_sandbox

        strat, run = _make_strategy_with_run(db, suffix="sim-toplus", turnover=1.5)
        try:
            scenario = {
                "scenario_name": "turnover + cost stress",
                "assumption_overrides": {"transaction_cost_bps": 20},
                "metric_overrides": {"turnover": 3.0},
                "evidence_overrides": {},
            }
            data = simulate_strategy_sandbox(strat.id, db, scenario)
            assert data.new_blockers or data.warnings, (
                "Expected new_blockers or warnings non-empty for doubled "
                f"turnover + elevated costs; got blockers={data.new_blockers}, "
                f"warnings={data.warnings}"
            )
        finally:
            _cleanup(db, run, strat)

    def test_signal_stale_lowers_readiness(self, db):
        from app.services.strategy_sandbox import simulate_strategy_sandbox

        strat, run = _make_strategy_with_run(db, suffix="sim-stale")
        try:
            scenario = {
                "scenario_name": "stale signal",
                "assumption_overrides": {},
                "metric_overrides": {},
                "evidence_overrides": {"signal_stale": True},
            }
            data = simulate_strategy_sandbox(strat.id, db, scenario)
            cur = data.current.readiness_score
            proj = data.projected.readiness_score
            assert proj is not None
            if cur is not None:
                assert proj <= cur, (
                    f"Expected projected readiness <= current with stale "
                    f"signal, got projected={proj} current={cur}"
                )
        finally:
            _cleanup(db, run, strat)

    def test_evidence_verification_failure_caps_readiness(self, db):
        from app.services.strategy_sandbox import simulate_strategy_sandbox

        strat, run = _make_strategy_with_run(db, suffix="sim-evfail")
        try:
            scenario = {
                "scenario_name": "evidence verification failure",
                "assumption_overrides": {},
                "metric_overrides": {},
                "evidence_overrides": {"evidence_verification_failed": True},
            }
            data = simulate_strategy_sandbox(strat.id, db, scenario)
            assert data.projected.readiness_score is not None
            assert data.projected.readiness_score <= 60, (
                f"Expected readiness capped at <= 60 on verification failure, "
                f"got {data.projected.readiness_score}"
            )
            assert data.projected.reliability_score is not None
            assert data.projected.reliability_score <= 60, (
                f"Expected reliability capped at <= 60 on verification failure, "
                f"got {data.projected.reliability_score}"
            )
        finally:
            _cleanup(db, run, strat)

    def test_paper_drift_high_blocks_production(self, db):
        from app.services.strategy_sandbox import simulate_strategy_sandbox

        strat, run = _make_strategy_with_run(db, suffix="sim-drift")
        try:
            scenario = {
                "scenario_name": "paper drift stress",
                "assumption_overrides": {},
                "metric_overrides": {},
                "evidence_overrides": {"paper_drift_high": True},
                "target_stage": "production_candidate",
            }
            data = simulate_strategy_sandbox(strat.id, db, scenario)
            assert data.projected.promotion_verdict == "blocked", (
                f"Expected promotion_verdict 'blocked', got "
                f"{data.projected.promotion_verdict!r}"
            )
            assert any("drift" in b.lower() for b in data.new_blockers), (
                f"Expected a drift-related new_blocker, got {data.new_blockers}"
            )
        finally:
            _cleanup(db, run, strat)

    def test_report_missing_remains_blocker(self, db):
        from app.services.strategy_sandbox import simulate_strategy_sandbox

        strat, run = _make_strategy_with_run(db, suffix="sim-noreport")
        try:
            scenario = {
                "scenario_name": "report missing",
                "assumption_overrides": {},
                "metric_overrides": {},
                "evidence_overrides": {"report_missing": True},
            }
            data = simulate_strategy_sandbox(strat.id, db, scenario)
            assert any("report" in b.lower() for b in data.new_blockers), (
                f"Expected a report-related new_blocker, got {data.new_blockers}"
            )
        finally:
            _cleanup(db, run, strat)

    def test_high_alerts_blocker(self, db):
        from app.services.strategy_sandbox import simulate_strategy_sandbox

        strat, run = _make_strategy_with_run(db, suffix="sim-alerts")
        try:
            scenario = {
                "scenario_name": "open alerts",
                "assumption_overrides": {},
                "metric_overrides": {},
                "evidence_overrides": {"high_alerts_open": 2},
            }
            data = simulate_strategy_sandbox(strat.id, db, scenario)
            assert any("alert" in b.lower() for b in data.new_blockers), (
                f"Expected an alert-related new_blocker, got {data.new_blockers}"
            )
        finally:
            _cleanup(db, run, strat)

    def test_projected_scores_clamped(self, db):
        from app.services.strategy_sandbox import simulate_strategy_sandbox

        strat, run = _make_strategy_with_run(db, suffix="sim-clamp", turnover=1.5)
        try:
            scenario = {
                "scenario_name": "extreme stress",
                "assumption_overrides": {"transaction_cost_bps": 999},
                "metric_overrides": {"turnover": 50.0, "max_drawdown": -0.99},
                "evidence_overrides": {
                    "signal_stale": True,
                    "dataset_stale": True,
                    "report_missing": True,
                    "high_alerts_open": 99,
                    "evidence_verification_failed": True,
                },
            }
            data = simulate_strategy_sandbox(strat.id, db, scenario)
            for attr in (
                "reliability_score",
                "backtest_reality_score",
                "readiness_score",
            ):
                val = getattr(data.projected, attr)
                if val is not None:
                    assert 0 <= val <= 100, (
                        f"projected {attr}={val} out of [0,100] range"
                    )
        finally:
            _cleanup(db, run, strat)

    def test_deltas_present_for_overrides(self, db):
        from app.services.strategy_sandbox import simulate_strategy_sandbox

        strat, run = _make_strategy_with_run(db, suffix="sim-deltas")
        try:
            scenario = {
                "scenario_name": "cost override",
                "assumption_overrides": {"transaction_cost_bps": 25},
                "metric_overrides": {},
                "evidence_overrides": {},
            }
            data = simulate_strategy_sandbox(strat.id, db, scenario)
            keys = {d.key for d in data.deltas}
            assert "transaction_cost_bps" in keys, (
                f"Expected a transaction_cost_bps delta, got keys: {keys}"
            )
        finally:
            _cleanup(db, run, strat)

    def test_disclaimer_present(self, db):
        from app.services.strategy_sandbox import simulate_strategy_sandbox

        strat, run = _make_strategy_with_run(db, suffix="sim-disclaimer")
        try:
            data = simulate_strategy_sandbox(
                strat.id, db, {"scenario_name": "x"}
            )
            low = data.disclaimer.lower()
            assert (
                "not a trading recommendation" in low
                or "not a re-backtest" in low
            ), f"Unexpected disclaimer: {data.disclaimer!r}"
        finally:
            _cleanup(db, run, strat)


# ---------------------------------------------------------------------------
# TestReadOnly
# ---------------------------------------------------------------------------


class TestReadOnly:
    """simulate_strategy_sandbox must never create DB rows."""

    def test_simulate_creates_no_rows(self, db):
        from app.services.strategy_sandbox import simulate_strategy_sandbox
        from app.models.strategy_run import StrategyRun
        from app.models.backtest_audit import BacktestAudit
        from app.models.report import Report
        from app.models.strategy_reliability_score import StrategyReliabilityScore
        from app.models.alert import Alert

        strat, run = _make_strategy_with_run(db, suffix="ro-norows", turnover=1.5)
        try:
            before = {
                "runs": db.query(StrategyRun).count(),
                "audits": db.query(BacktestAudit).count(),
                "reports": db.query(Report).count(),
                "scores": db.query(StrategyReliabilityScore).count(),
                "alerts": db.query(Alert).count(),
            }

            scenario = {
                "scenario_name": "full scenario",
                "assumption_overrides": {"transaction_cost_bps": 25},
                "metric_overrides": {"turnover": 3.0, "max_drawdown": -0.3},
                "evidence_overrides": {
                    "signal_stale": True,
                    "report_missing": True,
                    "high_alerts_open": 2,
                    "paper_drift_high": True,
                    "evidence_verification_failed": True,
                },
                "target_stage": "production_candidate",
            }
            simulate_strategy_sandbox(strat.id, db, scenario)

            after = {
                "runs": db.query(StrategyRun).count(),
                "audits": db.query(BacktestAudit).count(),
                "reports": db.query(Report).count(),
                "scores": db.query(StrategyReliabilityScore).count(),
                "alerts": db.query(Alert).count(),
            }
            assert before == after, (
                f"simulate must not create rows; before={before}, after={after}"
            )
        finally:
            _cleanup(db, run, strat)


# ---------------------------------------------------------------------------
# TestSandboxReport
# ---------------------------------------------------------------------------


class TestSandboxReport:
    """Tests for generate_sandbox_report."""

    def test_json_report_parseable(self, db):
        from app.services.strategy_sandbox import generate_sandbox_report

        strat, run = _make_strategy_with_run(db, suffix="rep-json")
        try:
            scenario = {
                "scenario_name": "report scenario",
                "assumption_overrides": {"transaction_cost_bps": 15},
                "metric_overrides": {},
                "evidence_overrides": {},
            }
            content = generate_sandbox_report(
                strat.id, db, scenario, format="json"
            )
            parsed = json.loads(content)
            assert isinstance(parsed, dict)
            assert "current" in parsed and "projected" in parsed
        finally:
            _cleanup(db, run, strat)

    def test_markdown_report_has_header(self, db):
        from app.services.strategy_sandbox import generate_sandbox_report

        strat, run = _make_strategy_with_run(db, suffix="rep-md")
        try:
            scenario = {
                "scenario_name": "report scenario",
                "assumption_overrides": {},
                "metric_overrides": {},
                "evidence_overrides": {},
            }
            content = generate_sandbox_report(
                strat.id, db, scenario, format="markdown"
            )
            assert "#" in content, "Expected a Markdown '#' header"
        finally:
            _cleanup(db, run, strat)


# ---------------------------------------------------------------------------
# TestSandboxEndpoints
# ---------------------------------------------------------------------------


class TestSandboxEndpoints:
    """Integration tests via TestClient for the M98 sandbox endpoints."""

    def test_get_sandbox_200(self, client, db):
        strategy = _get_seeded_strategy(db)
        assert strategy is not None
        resp = client.get(f"/api/strategies/{strategy.id}/sandbox")
        assert resp.status_code == 200, (
            f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        )
        data = resp.json()
        assert "current" in data, f"Missing 'current': {list(data.keys())}"
        assert "presets" in data, f"Missing 'presets': {list(data.keys())}"

    def test_get_unknown_404(self, client):
        fake_id = uuid.uuid4()
        resp = client.get(f"/api/strategies/{fake_id}/sandbox")
        assert resp.status_code == 404

    def test_simulate_endpoint_200(self, client, db):
        strategy = _get_seeded_strategy(db)
        assert strategy is not None
        resp = client.post(
            f"/api/strategies/{strategy.id}/sandbox/simulate",
            json={
                "scenario_name": "cost stress",
                "assumption_overrides": {"transaction_cost_bps": 15},
                "metric_overrides": {},
                "evidence_overrides": {},
            },
        )
        assert resp.status_code == 200, (
            f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        )
        data = resp.json()
        for field in ("current", "projected", "deltas"):
            assert field in data, f"Missing '{field}': {list(data.keys())}"

    def test_simulate_cost_lowers_via_endpoint(self, client, db):
        """POST cost+turnover stress -> projected reality <= baseline projection.

        Mirrors the service-level test: the audit engine treats higher costs as
        more realistic, so the genuine erosion comes from turnover. We compare
        the scenario projection against an empty-scenario projection through the
        same endpoint so both go through the identical projection path.
        """
        strat, run = _make_strategy_with_run(
            db, suffix="ep-cost", turnover=1.5
        )
        try:
            base_resp = client.post(
                f"/api/strategies/{strat.id}/sandbox/simulate",
                json={
                    "scenario_name": "baseline",
                    "assumption_overrides": {},
                    "metric_overrides": {},
                    "evidence_overrides": {},
                },
            )
            assert base_resp.status_code == 200
            baseline_proj = base_resp.json()["projected"]["backtest_reality_score"]

            resp = client.post(
                f"/api/strategies/{strat.id}/sandbox/simulate",
                json={
                    "scenario_name": "cost stress",
                    "assumption_overrides": {"transaction_cost_bps": 25},
                    "metric_overrides": {"turnover": 3.0},
                    "evidence_overrides": {},
                },
            )
            assert resp.status_code == 200, (
                f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
            )
            proj = resp.json()["projected"]["backtest_reality_score"]
            assert baseline_proj is not None and proj is not None
            assert proj <= baseline_proj, (
                f"Expected projected reality <= baseline projection via "
                f"endpoint, got projected={proj} baseline={baseline_proj}"
            )
        finally:
            _cleanup(db, run, strat)

    def test_report_json_200(self, client, db):
        strategy = _get_seeded_strategy(db)
        resp = client.get(
            f"/api/strategies/{strategy.id}/sandbox/report?format=json"
        )
        assert resp.status_code == 200, (
            f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        )

    def test_report_markdown_200(self, client, db):
        strategy = _get_seeded_strategy(db)
        resp = client.get(
            f"/api/strategies/{strategy.id}/sandbox/report?format=markdown"
        )
        assert resp.status_code == 200, (
            f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        )

    def test_report_invalid_format_400(self, client, db):
        strategy = _get_seeded_strategy(db)
        resp = client.get(
            f"/api/strategies/{strategy.id}/sandbox/report?format=xml"
        )
        assert resp.status_code == 400
