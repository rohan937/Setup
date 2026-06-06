"""M99 tests: Score Explainability layer.

Tests for app.services.score_explainability:
  - TestExplainReliability: explain_reliability_score (exact reconstruction)
  - TestExplainBacktestTrust: explain_backtest_trust (audit + issues)
  - TestExplainBacktestReality: explain_backtest_reality (wraps reality check)
  - TestExplainEvidenceVerification: explain_evidence_verification
  - TestExplainReadiness: explain_readiness_score
  - TestExplainStrategyScores: explain_strategy_scores (full multi-card)
  - TestReports: generate_score_explainability_report (JSON / Markdown)
  - TestEndpoints: GET score-explainability endpoints

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

    slug = f"m99-test-{suffix}-{uuid.uuid4().hex[:8]}"
    strat = Strategy(
        project_id=project_id,
        name=f"M99 Test Strategy {suffix}",
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


def _make_reliability_score(
    db,
    strategy_id,
    *,
    overall_score: float = 88.8,
    status: str = "good",
    data_evidence_score: float | None = 90,
    signal_evidence_score: float | None = 85,
    backtest_trust_score: float | None = 80,
    universe_evidence_score: float | None = 92,
    config_evidence_score: float | None = 95,
    strategy_activity_score: float | None = 95,
    alert_penalty_score: float | None = 100,
    report_coverage_score: float | None = None,
    missing_evidence_json: list | None = None,
    suggested_checks_json: list | None = None,
) -> object:
    """Insert a StrategyReliabilityScore row directly via db.

    With all seven WEIGHTS components populated the weighted average reconstructs
    to ~88.95, which is within the test's rounding tolerance of overall_score
    (88.8).
    """
    from app.models.strategy_reliability_score import StrategyReliabilityScore

    if missing_evidence_json is None:
        missing_evidence_json = ["No strategy_reliability report generated yet."]
    if suggested_checks_json is None:
        suggested_checks_json = [
            "Log at least one more strategy run to improve evidence.",
            "Generate a reliability report for this strategy.",
        ]

    score = StrategyReliabilityScore(
        strategy_id=strategy_id,
        overall_score=overall_score,
        status=status,
        data_evidence_score=data_evidence_score,
        signal_evidence_score=signal_evidence_score,
        backtest_trust_score=backtest_trust_score,
        universe_evidence_score=universe_evidence_score,
        config_evidence_score=config_evidence_score,
        strategy_activity_score=strategy_activity_score,
        alert_penalty_score=alert_penalty_score,
        report_coverage_score=report_coverage_score,
        missing_evidence_json=missing_evidence_json,
        suggested_checks_json=suggested_checks_json,
        generated_at=datetime.now(timezone.utc),
    )
    db.add(score)
    db.flush()
    return score


def _make_audit_with_issue(
    db,
    run_id,
    *,
    trust_score: int = 70,
    severity: str = "high",
    issue_type: str = "zero_transaction_cost",
    title: str = "Zero cost",
) -> tuple:
    """Create a BacktestAudit + one BacktestIssue row directly via db."""
    from app.models.backtest_audit import BacktestAudit
    from app.models.backtest_issue import BacktestIssue

    audit = BacktestAudit(
        strategy_run_id=run_id,
        trust_score=trust_score,
        lookahead_risk_score=90,
        cost_realism_score=50,
        fill_realism_score=90,
        liquidity_realism_score=90,
        borrow_realism_score=90,
        data_quality_score=90,
        overall_status="review",
        summary="Test audit",
    )
    db.add(audit)
    db.flush()
    issue = BacktestIssue(
        backtest_audit_id=audit.id,
        issue_type=issue_type,
        severity=severity,
        title=title,
        description="Backtest assumed zero transaction costs.",
        suggested_check="Add realistic transaction costs.",
    )
    db.add(issue)
    db.flush()
    return audit, issue


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
# TestExplainReliability
# ---------------------------------------------------------------------------


class TestExplainReliability:
    """Tests for explain_reliability_score (exact weighted-average reconstruction)."""

    def test_returns_positive_and_negative_items(self, db):
        from app.services.score_explainability import explain_reliability_score

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="rel-posneg")
        score = _make_reliability_score(db, strat.id)
        try:
            card = explain_reliability_score(strat.id, db)
            directions = {i.direction for i in card.items}
            assert "positive" in directions, (
                f"Expected a positive item, got directions: {directions}"
            )
            assert "negative" in directions, (
                f"Expected a negative item, got directions: {directions}"
            )
        finally:
            _cleanup(db, score, strat)

    def test_missing_report_is_negative(self, db):
        from app.services.score_explainability import explain_reliability_score

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="rel-noreport")
        score = _make_reliability_score(db, strat.id)
        try:
            card = explain_reliability_score(strat.id, db)
            neg = [i for i in card.items if i.direction == "negative"]
            assert any(
                "report" in (i.explanation or "").lower()
                or "report" in (i.label or "").lower()
                for i in neg
            ), f"Expected a report-related negative item, got: {[i.label for i in neg]}"
        finally:
            _cleanup(db, score, strat)

    def test_one_run_condition_negative(self, db):
        from app.services.score_explainability import explain_reliability_score

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="rel-onerun")
        score = _make_reliability_score(
            db,
            strat.id,
            suggested_checks_json=[
                "Log at least one more strategy run to improve evidence.",
            ],
        )
        try:
            card = explain_reliability_score(strat.id, db)
            neg = [i for i in card.items if i.direction == "negative"]
            assert any(
                "run" in (i.explanation or "").lower()
                and ("one" in (i.explanation or "").lower()
                     or "additional" in (i.explanation or "").lower())
                for i in neg
            ) or any(i.key == "only_one_run" for i in neg), (
                f"Expected a one-run negative item, got: {[i.key for i in neg]}"
            )
        finally:
            _cleanup(db, score, strat)

    def test_strong_data_evidence_positive(self, db):
        from app.services.score_explainability import explain_reliability_score

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="rel-data")
        score = _make_reliability_score(db, strat.id, data_evidence_score=90)
        try:
            card = explain_reliability_score(strat.id, db)
            pos = [i for i in card.items if i.direction == "positive"]
            assert any(
                i.category == "data_evidence_score" or "data" in (i.label or "").lower()
                for i in pos
            ), f"Expected a data-evidence positive item, got: {[i.label for i in pos]}"
        finally:
            _cleanup(db, score, strat)

    def test_contributions_reconstruct_score(self, db):
        from app.services.score_explainability import explain_reliability_score

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="rel-recon")
        score = _make_reliability_score(db, strat.id, overall_score=88.8)
        try:
            card = explain_reliability_score(strat.id, db)
            from app.services.strategy_reliability import WEIGHTS

            component_contrib = sum(
                i.points for i in card.items if i.category in WEIGHTS
            )
            assert card.score is not None
            assert abs(component_contrib - card.score) <= 2.0, (
                f"Sum of component contributions ({component_contrib}) should "
                f"reconstruct overall_score ({card.score}) within 2.0"
            )
        finally:
            _cleanup(db, score, strat)

    def test_no_score_insufficient_data(self, db):
        from app.services.score_explainability import explain_reliability_score

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="rel-noscore")
        try:
            card = explain_reliability_score(strat.id, db)
            assert card.verdict == "insufficient_data", (
                f"Expected insufficient_data, got {card.verdict}"
            )
            assert card.score is None, f"Expected score None, got {card.score}"
        finally:
            _cleanup(db, strat)


# ---------------------------------------------------------------------------
# TestExplainBacktestTrust
# ---------------------------------------------------------------------------


class TestExplainBacktestTrust:
    """Tests for explain_backtest_trust."""

    def test_issue_appears_as_negative(self, db):
        from app.services.score_explainability import explain_backtest_trust

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="bt-issue")
        run = _make_run(db, strat.id, run_type="backtest")
        audit, issue = _make_audit_with_issue(
            db,
            run.id,
            trust_score=70,
            severity="high",
            issue_type="zero_transaction_cost",
            title="Zero cost",
        )
        try:
            card = explain_backtest_trust(strat.id, db)
            neg = [i for i in card.items if i.direction == "negative"]
            assert any(
                i.key == "zero_transaction_cost"
                or "zero cost" in (i.label or "").lower()
                or i.evidence_id == str(issue.id)
                for i in neg
            ), f"Expected a negative item for the issue, got: {[i.key for i in neg]}"
        finally:
            _cleanup(db, issue, audit, run, strat)

    def test_no_audit_insufficient(self, db):
        from app.services.score_explainability import explain_backtest_trust

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="bt-noaudit")
        run = _make_run(db, strat.id, run_type="backtest")
        try:
            card = explain_backtest_trust(strat.id, db)
            assert card.verdict == "insufficient_data", (
                f"Expected insufficient_data, got {card.verdict}"
            )
        finally:
            _cleanup(db, run, strat)


# ---------------------------------------------------------------------------
# TestExplainBacktestReality
# ---------------------------------------------------------------------------


class TestExplainBacktestReality:
    """Tests for explain_backtest_reality."""

    def test_reality_card_has_items(self, db):
        from app.services.score_explainability import explain_backtest_reality

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="rty-items")
        run = _make_run(
            db,
            strat.id,
            run_type="backtest",
            assumptions={"transaction_cost_bps": 5, "fill_model": "vwap"},
            metrics={"sharpe": 1.4, "annual_return": 0.15, "trade_count": 120},
        )
        try:
            card = explain_backtest_reality(strat.id, db)
            assert isinstance(card.items, list)
            assert card.verdict, "Expected a non-empty verdict"
        finally:
            _cleanup(db, run, strat)

    def test_reality_verdict_present(self, db):
        from app.services.score_explainability import explain_backtest_reality

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="rty-verdict")
        run = _make_run(db, strat.id, run_type="backtest")
        try:
            card = explain_backtest_reality(strat.id, db)
            assert isinstance(card.verdict, str) and len(card.verdict) > 0, (
                f"Expected non-empty verdict, got {card.verdict!r}"
            )
        finally:
            _cleanup(db, run, strat)


# ---------------------------------------------------------------------------
# TestExplainEvidenceVerification
# ---------------------------------------------------------------------------


class TestExplainEvidenceVerification:
    """Tests for explain_evidence_verification."""

    def test_verification_card(self, db):
        from app.services.score_explainability import explain_evidence_verification

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="ev-card")
        run = _make_run(db, strat.id, run_type="backtest")
        try:
            card = explain_evidence_verification(strat.id, db)
            assert isinstance(card.verdict, str) and len(card.verdict) > 0, (
                f"Expected non-empty verdict, got {card.verdict!r}"
            )
            # If warnings produced negative items, they must be marked negative.
            for i in card.items:
                assert i.direction in ("positive", "negative", "neutral")
        finally:
            _cleanup(db, run, strat)


# ---------------------------------------------------------------------------
# TestExplainReadiness
# ---------------------------------------------------------------------------


class TestExplainReadiness:
    """Tests for explain_readiness_score."""

    def test_readiness_blockers_negative(self, db):
        from app.services.score_explainability import explain_readiness_score

        project = _get_seeded_project(db)
        # A bare strategy with no runs/reports should have blockers for promotion.
        strat = _make_strategy(db, project.id, suffix="rdy-block")
        try:
            card = explain_readiness_score(strat.id, db)
            negatives = [i for i in card.items if i.direction == "negative"]
            recs = [i for i in card.items if i.recommended_action]
            assert negatives or recs, (
                "Expected readiness card to surface negative items (blockers) or "
                f"recommended actions; got items: {[i.key for i in card.items]}"
            )
        finally:
            _cleanup(db, strat)


# ---------------------------------------------------------------------------
# TestExplainStrategyScores
# ---------------------------------------------------------------------------


class TestExplainStrategyScores:
    """Tests for the top-level explain_strategy_scores."""

    def test_returns_all_scorecards(self, db):
        from app.services.score_explainability import explain_strategy_scores

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="all-cards")
        run = _make_run(
            db,
            strat.id,
            run_type="backtest",
            assumptions={"transaction_cost_bps": 5, "fill_model": "vwap"},
            metrics={"sharpe": 1.4, "annual_return": 0.15, "trade_count": 120},
        )
        score = _make_reliability_score(db, strat.id)
        try:
            data = explain_strategy_scores(strat.id, db)
            keys = {c.score_key for c in data.scorecards}
            expected = {
                "reliability",
                "backtest_trust",
                "backtest_reality",
                "evidence_verification",
                "readiness",
                "shadow_monitor",
            }
            present = expected & keys
            assert len(present) >= 5, (
                f"Expected at least 5 of {expected}, got: {keys}"
            )
        finally:
            _cleanup(db, score, run, strat)

    def test_no_strategy_data_graceful(self, db):
        from app.services.score_explainability import explain_strategy_scores

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="minimal")
        try:
            data = explain_strategy_scores(strat.id, db)
            assert data.scorecards, "Expected scorecards even for minimal strategy"
            # At least one card should be insufficient_data given no evidence.
            verdicts = {c.verdict for c in data.scorecards}
            assert "insufficient_data" in verdicts, (
                f"Expected an insufficient_data verdict, got: {verdicts}"
            )
        finally:
            _cleanup(db, strat)

    def test_deterministic_output(self, db):
        from app.services.score_explainability import explain_strategy_scores

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="determ")
        score = _make_reliability_score(db, strat.id)
        try:
            a = explain_strategy_scores(strat.id, db)
            b = explain_strategy_scores(strat.id, db)
            assert len(a.scorecards) == len(b.scorecards), (
                "Expected the same number of scorecards across calls"
            )
            a_rel = next(c for c in a.scorecards if c.score_key == "reliability")
            b_rel = next(c for c in b.scorecards if c.score_key == "reliability")
            assert a_rel.score == b_rel.score, (
                f"Reliability score not deterministic: {a_rel.score} vs {b_rel.score}"
            )
        finally:
            _cleanup(db, score, strat)

    def test_has_disclaimer(self, db):
        from app.services.score_explainability import explain_strategy_scores

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="disc")
        try:
            data = explain_strategy_scores(strat.id, db)
            assert "not trading advice" in data.disclaimer.lower(), (
                f"Expected 'not trading advice' in disclaimer, got: {data.disclaimer!r}"
            )
        finally:
            _cleanup(db, strat)


# ---------------------------------------------------------------------------
# TestReports
# ---------------------------------------------------------------------------


class TestReports:
    """Tests for generate_score_explainability_report."""

    def test_json_report_parseable(self, db):
        from app.services.score_explainability import (
            generate_score_explainability_report,
        )

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="rep-json")
        score = _make_reliability_score(db, strat.id)
        try:
            content = generate_score_explainability_report(
                strat.id, db, format="json"
            )
            parsed = json.loads(content)
            assert isinstance(parsed, dict)
            assert "scorecards" in parsed
        finally:
            _cleanup(db, score, strat)

    def test_markdown_report_has_header(self, db):
        from app.services.score_explainability import (
            generate_score_explainability_report,
        )

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="rep-md")
        score = _make_reliability_score(db, strat.id)
        try:
            content = generate_score_explainability_report(
                strat.id, db, format="markdown"
            )
            assert "# Score Explainability" in content, (
                "Expected '# Score Explainability' header in markdown report"
            )
        finally:
            _cleanup(db, score, strat)


# ---------------------------------------------------------------------------
# TestEndpoints
# ---------------------------------------------------------------------------


class TestEndpoints:
    """Integration tests via TestClient for the M99 endpoints."""

    def test_overview_endpoint_200(self, client, db):
        strategy = _get_seeded_strategy(db)
        assert strategy is not None
        resp = client.get(f"/api/strategies/{strategy.id}/score-explainability")
        assert resp.status_code == 200, (
            f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        )
        data = resp.json()
        assert "scorecards" in data, f"Missing 'scorecards': {list(data.keys())}"

    def test_unknown_strategy_404(self, client):
        fake_id = uuid.uuid4()
        resp = client.get(f"/api/strategies/{fake_id}/score-explainability")
        assert resp.status_code == 404

    def test_reliability_endpoint_200(self, client, db):
        strategy = _get_seeded_strategy(db)
        resp = client.get(
            f"/api/strategies/{strategy.id}/score-explainability/reliability"
        )
        assert resp.status_code == 200, (
            f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        )

    def test_backtest_reality_endpoint_200(self, client, db):
        strategy = _get_seeded_strategy(db)
        resp = client.get(
            f"/api/strategies/{strategy.id}/score-explainability/backtest-reality"
        )
        assert resp.status_code == 200, (
            f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        )

    def test_evidence_verification_endpoint_200(self, client, db):
        strategy = _get_seeded_strategy(db)
        resp = client.get(
            f"/api/strategies/{strategy.id}/score-explainability/evidence-verification"
        )
        assert resp.status_code == 200, (
            f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        )

    def test_readiness_endpoint_200(self, client, db):
        strategy = _get_seeded_strategy(db)
        resp = client.get(
            f"/api/strategies/{strategy.id}/score-explainability/readiness"
        )
        assert resp.status_code == 200, (
            f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        )

    def test_report_json_200(self, client, db):
        strategy = _get_seeded_strategy(db)
        resp = client.get(
            f"/api/strategies/{strategy.id}/score-explainability/report?format=json"
        )
        assert resp.status_code == 200, (
            f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        )

    def test_report_markdown_200(self, client, db):
        strategy = _get_seeded_strategy(db)
        resp = client.get(
            f"/api/strategies/{strategy.id}/score-explainability/report?format=markdown"
        )
        assert resp.status_code == 200, (
            f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        )

    def test_report_invalid_format_400(self, client, db):
        strategy = _get_seeded_strategy(db)
        resp = client.get(
            f"/api/strategies/{strategy.id}/score-explainability/report?format=xml"
        )
        assert resp.status_code == 400
