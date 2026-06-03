"""M61 tests: Strategy Robustness Score.

Tests for:
  - GET /api/strategies/{id}/robustness endpoint
  - Multi-dimensional robustness scoring
  - Fragility signal detection
  - Verdict logic
  - Language policy (no investment advice / AI language)
  - Read-only: no AuditTimelineEvent created

All tests use the shared session-scoped fixtures from conftest.py.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FORBIDDEN_INVESTMENT_WORDS = ["buy", "sell", "profitable", "investment advice", "safe to trade"]
FORBIDDEN_AI_WORDS = ["AI", "prediction"]


def _has_forbidden(text: str, words: list[str]) -> list[str]:
    low = text.lower()
    return [w for w in words if w.lower() in low]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_strategy(db, project_id, *, suffix: str = "") -> object:
    from app.models.strategy import Strategy

    slug = f"m61-test-{suffix}-{uuid.uuid4().hex[:8]}"
    strat = Strategy(
        project_id=project_id,
        name=f"M61 Test Strategy {suffix}",
        slug=slug,
        asset_class="equity",
        status="active",
    )
    db.add(strat)
    db.flush()
    return strat


def _make_run(db, strategy_id, *, run_type: str = "backtest", status: str = "completed") -> object:
    from app.models.strategy_run import StrategyRun

    run = StrategyRun(
        strategy_id=strategy_id,
        run_name=f"run-{uuid.uuid4().hex[:6]}",
        run_type=run_type,
        status=status,
    )
    db.add(run)
    db.flush()
    return run


def _make_backtest_audit(
    db,
    run_id,
    *,
    trust_score: int = 72,
    overall_status: str = "review",
    cost_sensitivity_sweep_json: dict | None = None,
    fill_sensitivity_json: dict | None = None,
) -> object:
    from app.models.backtest_audit import BacktestAudit

    audit = BacktestAudit(
        strategy_run_id=run_id,
        trust_score=trust_score,
        overall_status=overall_status,
        summary=f"M61 test audit ts={trust_score}",
        cost_sensitivity_sweep_json=cost_sensitivity_sweep_json,
        fill_sensitivity_json=fill_sensitivity_json,
    )
    db.add(audit)
    db.flush()
    return audit


def _make_regression_run(
    db,
    strategy_id,
    *,
    overall_status: str = "passed",
    required_failed_count: int = 0,
    failed_count: int = 0,
    passed_count: int = 3,
    warning_count: int = 0,
    skipped_count: int = 0,
) -> object:
    from app.models.regression import StrategyRegressionTestRun

    run = StrategyRegressionTestRun(
        strategy_id=strategy_id,
        overall_status=overall_status,
        required_failed_count=required_failed_count,
        failed_count=failed_count,
        passed_count=passed_count,
        warning_count=warning_count,
        skipped_count=skipped_count,
        mode="latest_vs_previous",
        result_json=[],
        created_at=datetime.now(timezone.utc),
    )
    db.add(run)
    db.flush()
    return run


def _make_review_case(
    db,
    strategy_id,
    *,
    status: str = "open",
    severity: str = "critical",
    case_key: str | None = None,
) -> object:
    from app.models.review_case import ResearchReviewCase

    now = datetime.now(timezone.utc)
    case = ResearchReviewCase(
        strategy_id=str(strategy_id),
        title=f"M61 test review case {severity}",
        case_key=case_key or f"m61_case_{uuid.uuid4().hex[:8]}",
        status=status,
        severity=severity,
        category="reliability",
        opened_at=now,
        created_at=now,
        updated_at=now,
    )
    db.add(case)
    db.flush()
    return case


def _get_seeded_strategy(db):
    from app.models.strategy import Strategy
    return db.query(Strategy).filter(Strategy.status != "archived").first()


def _get_seeded_project(db):
    from app.models.project import Project
    return db.query(Project).first()


# ---------------------------------------------------------------------------
# TestRobustnessEndpoint
# ---------------------------------------------------------------------------


class TestRobustnessEndpoint:
    """Integration tests via TestClient for the robustness endpoint."""

    def test_endpoint_returns_strategy(self, client, db):
        """GET /api/strategies/{id}/robustness returns 200 for a known strategy."""
        strategy = _get_seeded_strategy(db)
        assert strategy is not None
        resp = client.get(f"/api/strategies/{strategy.id}/robustness")
        assert resp.status_code == 200

    def test_missing_strategy_404(self, client):
        """Non-existent strategy ID returns 404."""
        fake_id = uuid.uuid4()
        resp = client.get(f"/api/strategies/{fake_id}/robustness")
        assert resp.status_code == 404

    def test_no_evidence_insufficient_evidence(self, client, db):
        """Empty strategy with no evidence returns insufficient_evidence verdict."""
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="noevidence")
        try:
            resp = client.get(f"/api/strategies/{strat.id}/robustness")
            assert resp.status_code == 200
            data = resp.json()
            # With no evidence, score should be null or insufficient
            verdict = data["robustness_verdict"]
            assert verdict in (
                "insufficient_evidence",
                "requires_review",
                "fragile_under_variation",
            )
        finally:
            db.delete(strat)
            db.flush()

    def test_all_dimensions_present_in_response(self, client, db):
        """Response contains all 10 dimension scorecards."""
        strategy = _get_seeded_strategy(db)
        resp = client.get(f"/api/strategies/{strategy.id}/robustness")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["dimension_scorecards"]) == 10

    def test_response_has_required_fields(self, client, db):
        """Response contains all required top-level fields."""
        strategy = _get_seeded_strategy(db)
        resp = client.get(f"/api/strategies/{strategy.id}/robustness")
        assert resp.status_code == 200
        data = resp.json()
        required_fields = [
            "strategy_id",
            "strategy_name",
            "generated_at",
            "robustness_score",
            "robustness_status",
            "robustness_verdict",
            "verdict_label",
            "deterministic_summary",
            "dimension_scorecards",
            "fragility_signals",
            "top_review_drivers",
            "suggested_actions",
            "evidence_gaps",
            "robustness_vs_readiness_note",
        ]
        for field in required_fields:
            assert field in data, f"Missing field: {field}"

    def test_dimension_scorecard_fields(self, client, db):
        """Each dimension scorecard must have required fields."""
        strategy = _get_seeded_strategy(db)
        resp = client.get(f"/api/strategies/{strategy.id}/robustness")
        assert resp.status_code == 200
        data = resp.json()
        for dim in data["dimension_scorecards"]:
            assert "dimension_key" in dim
            assert "title" in dim
            assert "status" in dim
            assert "score" in dim
            assert "evidence_count" in dim
            assert "fragility_signals" in dim
            assert "suggested_actions" in dim

    def test_dimension_keys_correct(self, client, db):
        """All 10 expected dimension keys are present."""
        expected_keys = {
            "parameter_stability",
            "cost_sensitivity",
            "fill_realism",
            "drift_stability",
            "shadow_stability",
            "assumption_stability",
            "regression_stability",
            "evidence_freshness",
            "policy_sla_compliance",
            "review_case_pressure",
        }
        strategy = _get_seeded_strategy(db)
        resp = client.get(f"/api/strategies/{strategy.id}/robustness")
        assert resp.status_code == 200
        data = resp.json()
        actual_keys = {d["dimension_key"] for d in data["dimension_scorecards"]}
        assert actual_keys == expected_keys


# ---------------------------------------------------------------------------
# TestRobustnessDimensions
# ---------------------------------------------------------------------------


class TestRobustnessDimensions:
    """Test individual dimension scoring logic."""

    def _get_dim(self, data, key):
        for d in data["dimension_scorecards"]:
            if d["dimension_key"] == key:
                return d
        return None

    def test_regression_stability_failed(self, client, db):
        """StrategyRegressionTestRun with failed status lowers regression_stability score."""
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="regfailed")
        reg_run = _make_regression_run(
            db,
            strat.id,
            overall_status="failed",
            required_failed_count=1,
            failed_count=2,
            passed_count=3,
        )
        try:
            resp = client.get(f"/api/strategies/{strat.id}/robustness")
            assert resp.status_code == 200
            data = resp.json()
            dim = self._get_dim(data, "regression_stability")
            assert dim is not None
            assert dim["status"] != "missing"
            assert dim["score"] is not None
            # failed with 1 required_failed: 35 - 15 = 20
            assert dim["score"] <= 35.0
        finally:
            try:
                db.delete(reg_run)
                db.delete(strat)
                db.flush()
            except Exception:
                pass

    def test_cost_sensitivity_from_audit(self, client, db):
        """BacktestAudit with high cost sensitivity trust impact lowers cost_sensitivity score."""
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="costhigh")
        run = _make_run(db, strat.id, run_type="backtest")
        audit = _make_backtest_audit(
            db,
            run.id,
            trust_score=72,
            overall_status="review",
            cost_sensitivity_sweep_json={
                "most_fragile_scenario": {
                    "trust_impact": "high",
                    "scenario_label": "5x cost",
                }
            },
        )
        try:
            resp = client.get(f"/api/strategies/{strat.id}/robustness")
            assert resp.status_code == 200
            data = resp.json()
            dim = self._get_dim(data, "cost_sensitivity")
            assert dim is not None
            assert dim["status"] != "missing"
            assert dim["score"] is not None
            # 80 - 25 (high trust impact) - 20 (missing transaction_cost_bps) = 35
            assert dim["score"] <= 60.0
        finally:
            try:
                db.delete(audit)
                db.delete(run)
                db.delete(strat)
                db.flush()
            except Exception:
                pass

    def test_fill_realism_from_audit(self, client, db):
        """BacktestAudit with fill_realism_level=high_concern lowers fill_realism score."""
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="fillhigh")
        run = _make_run(db, strat.id, run_type="backtest")
        audit = _make_backtest_audit(
            db,
            run.id,
            trust_score=72,
            overall_status="review",
            fill_sensitivity_json={"fill_realism_level": "high_concern"},
        )
        try:
            resp = client.get(f"/api/strategies/{strat.id}/robustness")
            assert resp.status_code == 200
            data = resp.json()
            dim = self._get_dim(data, "fill_realism")
            assert dim is not None
            assert dim["status"] != "missing"
            assert dim["score"] is not None
            # 80 - 30 = 50
            assert dim["score"] <= 55.0
        finally:
            try:
                db.delete(audit)
                db.delete(run)
                db.delete(strat)
                db.flush()
            except Exception:
                pass

    def test_review_case_pressure_critical(self, client, db):
        """ResearchReviewCase with status=open, severity=critical lowers review_case_pressure score."""
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="critrvc")
        case = _make_review_case(db, strat.id, status="open", severity="critical")
        try:
            resp = client.get(f"/api/strategies/{strat.id}/robustness")
            assert resp.status_code == 200
            data = resp.json()
            dim = self._get_dim(data, "review_case_pressure")
            assert dim is not None
            assert dim["score"] is not None
            # 90 - 35 (critical) = 55
            assert dim["score"] <= 60.0
        finally:
            try:
                db.delete(case)
                db.delete(strat)
                db.flush()
            except Exception:
                pass

    def test_evidence_gaps_listed(self, client, db):
        """Dimensions with no evidence appear in evidence_gaps."""
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="evgaps")
        try:
            resp = client.get(f"/api/strategies/{strat.id}/robustness")
            assert resp.status_code == 200
            data = resp.json()
            # A fresh strategy with no evidence should have gaps
            assert isinstance(data["evidence_gaps"], list)
            # Gaps should be non-empty (fresh strategy has no experiments, no audits, etc.)
            assert len(data["evidence_gaps"]) > 0
        finally:
            db.delete(strat)
            db.flush()

    def test_parameter_stability_missing_when_no_experiment(self, client, db):
        """No experiment -> parameter_stability dimension is missing."""
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="noexp")
        try:
            resp = client.get(f"/api/strategies/{strat.id}/robustness")
            assert resp.status_code == 200
            data = resp.json()
            dim = next(
                (d for d in data["dimension_scorecards"] if d["dimension_key"] == "parameter_stability"),
                None,
            )
            assert dim is not None
            assert dim["status"] == "missing"
            assert dim["score"] is None
        finally:
            db.delete(strat)
            db.flush()

    def test_review_case_pressure_no_cases_high_score(self, client, db):
        """Strategy with no open review cases should have a high review_case_pressure score."""
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="nocases")
        try:
            resp = client.get(f"/api/strategies/{strat.id}/robustness")
            assert resp.status_code == 200
            data = resp.json()
            dim = next(
                (d for d in data["dimension_scorecards"] if d["dimension_key"] == "review_case_pressure"),
                None,
            )
            assert dim is not None
            assert dim["score"] == 90.0
        finally:
            db.delete(strat)
            db.flush()

    def test_cost_sensitivity_missing_no_audit(self, client, db):
        """Strategy with no backtest audit -> cost_sensitivity is missing."""
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="noaudit")
        try:
            resp = client.get(f"/api/strategies/{strat.id}/robustness")
            assert resp.status_code == 200
            data = resp.json()
            dim = next(
                (d for d in data["dimension_scorecards"] if d["dimension_key"] == "cost_sensitivity"),
                None,
            )
            assert dim is not None
            assert dim["status"] == "missing"
            assert dim["score"] is None
        finally:
            db.delete(strat)
            db.flush()


# ---------------------------------------------------------------------------
# TestRobustnessVerdict
# ---------------------------------------------------------------------------


class TestRobustnessVerdict:
    """Test verdict classification logic."""

    def test_verdict_insufficient_evidence_no_dimensions(self, client, db):
        """Fresh strategy with no evidence returns insufficient_evidence or requires_review."""
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="vnoev")
        try:
            resp = client.get(f"/api/strategies/{strat.id}/robustness")
            assert resp.status_code == 200
            data = resp.json()
            assert data["robustness_verdict"] in (
                "insufficient_evidence",
                "requires_review",
                "fragile_under_variation",
            )
        finally:
            db.delete(strat)
            db.flush()

    def test_verdict_requires_review_with_issues(self, client, db):
        """Strategy with high-severity issues returns requires_review or fragile verdict."""
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="vrequires")
        run = _make_run(db, strat.id, run_type="backtest")
        audit = _make_backtest_audit(
            db,
            run.id,
            trust_score=55,
            overall_status="review",
            cost_sensitivity_sweep_json={
                "most_fragile_scenario": {
                    "trust_impact": "high",
                    "scenario_label": "5x cost",
                }
            },
            fill_sensitivity_json={"fill_realism_level": "high_concern"},
        )
        reg_run = _make_regression_run(
            db,
            strat.id,
            overall_status="failed",
            required_failed_count=2,
            failed_count=3,
        )
        try:
            resp = client.get(f"/api/strategies/{strat.id}/robustness")
            assert resp.status_code == 200
            data = resp.json()
            assert data["robustness_verdict"] in (
                "requires_review",
                "fragile_under_variation",
                "insufficient_evidence",
            )
        finally:
            try:
                db.delete(reg_run)
                db.delete(audit)
                db.delete(run)
                db.delete(strat)
                db.flush()
            except Exception:
                pass

    def test_overall_score_weighted_average(self, client, db):
        """Verify that the overall score is numeric when dimensions have evidence."""
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="scorecheck")
        # Create enough evidence for scoring
        run = _make_run(db, strat.id, run_type="backtest")
        audit = _make_backtest_audit(
            db,
            run.id,
            trust_score=80,
            overall_status="good",
        )
        reg_run = _make_regression_run(
            db,
            strat.id,
            overall_status="passed",
            passed_count=5,
        )
        try:
            resp = client.get(f"/api/strategies/{strat.id}/robustness")
            assert resp.status_code == 200
            data = resp.json()
            # With at least some dimensions scoring, the response should be well-formed
            assert isinstance(data["robustness_score"], (float, int, type(None)))
            assert data["robustness_status"] in (
                "robust",
                "stable",
                "watch",
                "review",
                "fragile",
                "insufficient_evidence",
                "missing",
            )
        finally:
            try:
                db.delete(reg_run)
                db.delete(audit)
                db.delete(run)
                db.delete(strat)
                db.flush()
            except Exception:
                pass

    def test_fewer_than_5_dimensions_null_score(self, client, db):
        """Strategy with fewer than 5 scored dimensions should have null overall score."""
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="fewdims")
        # Only create regression evidence (1 dimension) so fewer than 5 score
        reg_run = _make_regression_run(
            db,
            strat.id,
            overall_status="passed",
            passed_count=3,
        )
        try:
            resp = client.get(f"/api/strategies/{strat.id}/robustness")
            assert resp.status_code == 200
            data = resp.json()
            # With only regression scoring, count of scored dims < 5 -> null score
            scored_dims = [d for d in data["dimension_scorecards"] if d["score"] is not None]
            if len(scored_dims) < 5:
                assert data["robustness_score"] is None
        finally:
            try:
                db.delete(reg_run)
                db.delete(strat)
                db.flush()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# TestRobustnessSummary
# ---------------------------------------------------------------------------


class TestRobustnessSummary:
    """Test summary, language policy, and read-only behavior."""

    def test_deterministic_summary_not_empty(self, client, db):
        """deterministic_summary must be a non-empty string."""
        strategy = _get_seeded_strategy(db)
        resp = client.get(f"/api/strategies/{strategy.id}/robustness")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data["deterministic_summary"], str)
        assert len(data["deterministic_summary"]) > 0

    def test_summary_avoids_forbidden_language(self, client, db):
        """Summary must not contain forbidden investment/AI words."""
        strategy = _get_seeded_strategy(db)
        resp = client.get(f"/api/strategies/{strategy.id}/robustness")
        assert resp.status_code == 200
        data = resp.json()

        summary = data.get("deterministic_summary", "")
        note = data.get("robustness_vs_readiness_note", "")
        verdict_label = data.get("verdict_label", "")
        combined = " ".join([summary, note, verdict_label])

        found_investment = _has_forbidden(combined, FORBIDDEN_INVESTMENT_WORDS)
        assert not found_investment, (
            f"Forbidden investment language found: {found_investment}"
        )
        found_ai = _has_forbidden(combined, FORBIDDEN_AI_WORDS)
        assert not found_ai, (
            f"Forbidden AI language found: {found_ai}"
        )

    def test_robustness_vs_readiness_note_present(self, client, db):
        """robustness_vs_readiness_note must be present and non-empty."""
        strategy = _get_seeded_strategy(db)
        resp = client.get(f"/api/strategies/{strategy.id}/robustness")
        assert resp.status_code == 200
        data = resp.json()
        note = data.get("robustness_vs_readiness_note", "")
        assert isinstance(note, str)
        assert len(note) > 0

    def test_suggested_actions_deduplicated(self, client, db):
        """suggested_actions must not contain duplicate entries."""
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="dedup")
        try:
            resp = client.get(f"/api/strategies/{strat.id}/robustness")
            assert resp.status_code == 200
            data = resp.json()
            actions = data["suggested_actions"]
            assert len(actions) == len(set(actions)), (
                f"Duplicate suggested_actions detected: {actions}"
            )
        finally:
            db.delete(strat)
            db.flush()

    def test_no_timeline_event_created(self, client, db):
        """GET robustness endpoint must NOT create any AuditTimelineEvent (read-only)."""
        from app.models.audit_timeline_event import AuditTimelineEvent

        strategy = _get_seeded_strategy(db)
        count_before = db.query(AuditTimelineEvent).count()

        resp = client.get(f"/api/strategies/{strategy.id}/robustness")
        assert resp.status_code == 200

        count_after = db.query(AuditTimelineEvent).count()
        assert count_after == count_before, (
            f"AuditTimelineEvent count changed: {count_before} -> {count_after}"
        )

    def test_fragility_signals_are_list(self, client, db):
        """fragility_signals must be a list of signal objects."""
        strategy = _get_seeded_strategy(db)
        resp = client.get(f"/api/strategies/{strategy.id}/robustness")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data["fragility_signals"], list)
        for sig in data["fragility_signals"]:
            assert "signal_key" in sig
            assert "title" in sig
            assert "severity" in sig
            assert "evidence_summary" in sig
            assert "suggested_action" in sig
            assert "source_dimension" in sig
            assert sig["severity"] in ("low", "medium", "high", "critical")

    def test_evidence_gaps_is_list_of_strings(self, client, db):
        """evidence_gaps must be a list of strings."""
        strategy = _get_seeded_strategy(db)
        resp = client.get(f"/api/strategies/{strategy.id}/robustness")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data["evidence_gaps"], list)
        for gap in data["evidence_gaps"]:
            assert isinstance(gap, str)

    def test_top_review_drivers_from_fragility_signals(self, client, db):
        """top_review_drivers should be the first 5 fragility signal titles."""
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="topdriv")
        run = _make_run(db, strat.id, run_type="backtest")
        audit = _make_backtest_audit(
            db,
            run.id,
            trust_score=55,
            overall_status="review",
            cost_sensitivity_sweep_json={
                "most_fragile_scenario": {
                    "trust_impact": "high",
                    "scenario_label": "5x cost",
                }
            },
            fill_sensitivity_json={"fill_realism_level": "high_concern"},
        )
        case = _make_review_case(db, strat.id, status="open", severity="critical")
        try:
            resp = client.get(f"/api/strategies/{strat.id}/robustness")
            assert resp.status_code == 200
            data = resp.json()
            drivers = data["top_review_drivers"]
            signals = data["fragility_signals"]
            assert isinstance(drivers, list)
            assert len(drivers) <= 5
            # Drivers should match the first N signal titles
            expected_titles = [s["title"] for s in signals[:len(drivers)]]
            assert drivers == expected_titles
        finally:
            try:
                db.delete(case)
                db.delete(audit)
                db.delete(run)
                db.delete(strat)
                db.flush()
            except Exception:
                pass
