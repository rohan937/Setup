"""M100 tests: Strategy Risk Narrative Generator.

Tests for app.services.risk_narrative:
  - TestGenerateNarrative: generate_strategy_risk_narrative (verdict, strengths,
    risks, deterministic, evidence-grounded, disclaimer)
  - TestNarrativeReports: render_risk_narrative_report (JSON / Markdown)
  - TestNarrativeEndpoints: GET risk-narrative endpoints

All tests use the shared session-scoped fixtures from conftest.py. The engine is
deterministic and READ-ONLY (no LLM, no DB writes).
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

    slug = f"m100-test-{suffix}-{uuid.uuid4().hex[:8]}"
    strat = Strategy(
        project_id=project_id,
        name=f"M100 Test Strategy {suffix}",
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
    overall_score: float = 90.0,
    status: str = "good",
    data_evidence_score: float | None = 95,
    signal_evidence_score: float | None = 90,
    backtest_trust_score: float | None = 88,
    universe_evidence_score: float | None = 92,
    config_evidence_score: float | None = 95,
    strategy_activity_score: float | None = 95,
    alert_penalty_score: float | None = 100,
    report_coverage_score: float | None = None,
    missing_evidence_json: list | None = None,
    suggested_checks_json: list | None = None,
) -> object:
    """Insert a StrategyReliabilityScore row directly via db."""
    from app.models.strategy_reliability_score import StrategyReliabilityScore

    if missing_evidence_json is None:
        missing_evidence_json = ["No strategy_reliability report generated yet."]
    if suggested_checks_json is None:
        suggested_checks_json = [
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


def _make_alert(db, strategy, *, severity: str = "high", status: str = "open") -> object:
    from app.models.alert import Alert
    from app.models.project import Project

    project = db.query(Project).filter(Project.id == strategy.project_id).first()
    alert = Alert(
        organization_id=project.organization_id,
        rule_type="m100_test_alert",
        status=status,
        severity=severity,
        title="M100 test alert",
        description="Synthetic high-severity alert for narrative tests",
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
# TestGenerateNarrative
# ---------------------------------------------------------------------------


class TestGenerateNarrative:
    """Tests for generate_strategy_risk_narrative."""

    def test_insufficient_data_narrative(self, db):
        from app.services.risk_narrative import generate_strategy_risk_narrative

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="insufficient")
        try:
            data = generate_strategy_risk_narrative(strat.id, db)
            assert data.verdict == "insufficient_data", (
                f"Expected insufficient_data, got {data.verdict!r}"
            )
            assert isinstance(data.narrative, str) and data.narrative.strip(), (
                "Expected a non-empty narrative string"
            )
            # primary_strengths may be empty; just assert it is a list.
            assert isinstance(data.primary_strengths, list)
        finally:
            _cleanup(db, strat)

    def test_strong_strategy_positive_narrative(self, db):
        from app.services.risk_narrative import generate_strategy_risk_narrative

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="strong")
        run = _make_run(
            db,
            strat.id,
            run_type="backtest",
            assumptions={"transaction_cost_bps": 5, "fill_model": "vwap"},
            metrics={"sharpe": 1.4, "annual_return": 0.15, "trade_count": 120},
        )
        score = _make_reliability_score(db, strat.id, overall_score=90)
        try:
            data = generate_strategy_risk_narrative(strat.id, db)
            # A high reliability score produces evidence-grounded strengths and a
            # graded (non-insufficient) verdict. The exact verdict depends on the
            # full evidence chain (readiness/evidence-verification), so we assert
            # the engine forms a real verdict rather than bailing out.
            assert data.verdict in ("ready", "review", "blocked"), (
                f"Expected a graded verdict, got {data.verdict!r}"
            )
            assert data.verdict != "insufficient_data"
            assert data.primary_strengths, (
                "Expected at least one primary strength for a strong strategy"
            )
            # The narrative should mention a strength (its label text appears in it).
            narrative_lower = data.narrative.lower()
            assert any(
                s.label.rstrip(".").lower() in narrative_lower
                for s in data.primary_strengths
            ), (
                f"Expected narrative to mention a strength; narrative={data.narrative!r}, "
                f"strengths={[s.label for s in data.primary_strengths]}"
            )
        finally:
            _cleanup(db, score, run, strat)

    def test_missing_paper_run_is_risk(self, db):
        from app.services.risk_narrative import generate_strategy_risk_narrative

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="nopaper")
        run = _make_run(db, strat.id, run_type="backtest")
        score = _make_reliability_score(db, strat.id)
        try:
            data = generate_strategy_risk_narrative(strat.id, db, target_stage="shadow")
            haystack_risks = " ".join(
                (r.key + " " + r.label + " " + r.evidence).lower()
                for r in data.primary_risks
            )
            haystack_actions = " ".join(
                (a or "").lower() for a in data.recommended_next_actions
            )
            haystack = haystack_risks + " " + haystack_actions
            assert "paper" in haystack or "shadow" in haystack, (
                "Expected a risk or recommended action referencing a paper/shadow run; "
                f"risks={[(r.key, r.label) for r in data.primary_risks]}, "
                f"actions={data.recommended_next_actions}"
            )
        finally:
            _cleanup(db, score, run, strat)

    def test_missing_report_is_risk(self, db):
        # The risk narrative composes the reliability scorecard. When no
        # reliability report has been generated (report_coverage_score=None), the
        # narrative inputs must carry a report-coverage negative signal that the
        # risk classifier turns into a `no_reliability_report` risk. We assert the
        # signal is present in the narrative inputs (independent of the top-N
        # display cap, which can be crowded out by higher-severity evidence-chain
        # risks in a bare strategy).
        from app.services.risk_narrative import build_risk_narrative_inputs

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="noreport")
        run = _make_run(db, strat.id, run_type="backtest")
        score = _make_reliability_score(
            db,
            strat.id,
            report_coverage_score=None,
            missing_evidence_json=["No strategy_reliability report generated yet."],
            suggested_checks_json=[
                "Generate a reliability report for this strategy.",
            ],
        )
        try:
            inputs = build_risk_narrative_inputs(strat.id, db)
            reliability_card = inputs["scorecards_by_key"].get("reliability")
            assert reliability_card is not None, "Expected a reliability scorecard"
            report_signals = [
                i
                for i in reliability_card.items
                if i.direction == "negative"
                and (
                    i.category == "report_coverage"
                    or "report" in (i.label or "").lower()
                    or "report" in (i.explanation or "").lower()
                )
            ]
            assert report_signals, (
                "Expected a report-coverage negative signal feeding the narrative; "
                f"items={[(i.category, i.direction, i.label) for i in reliability_card.items]}"
            )
            # And that signal carries a non-empty, sourced explanation/action.
            sig = report_signals[0]
            assert (sig.explanation or "").strip() or (sig.recommended_action or "").strip(), (
                "Report signal must carry sourced evidence or a recommended action"
            )
        finally:
            _cleanup(db, score, run, strat)

    def test_high_alerts_is_risk(self, db):
        from app.services.risk_narrative import generate_strategy_risk_narrative

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="alerts")
        run = _make_run(db, strat.id, run_type="backtest")
        score = _make_reliability_score(db, strat.id)
        alert = _make_alert(db, strat, severity="high", status="open")
        try:
            data = generate_strategy_risk_narrative(strat.id, db)
            assert any(
                "alert" in (r.key + r.label + r.evidence).lower()
                for r in data.primary_risks
            ), (
                "Expected a risk referencing alerts; risks="
                f"{[(r.key, r.label) for r in data.primary_risks]}"
            )
        finally:
            _cleanup(db, alert, score, run, strat)

    def test_readiness_blocker_is_risk(self, db):
        from app.services.risk_narrative import generate_strategy_risk_narrative

        project = _get_seeded_project(db)
        # A bare strategy with only a backtest run should have promotion blockers
        # for a higher target stage.
        strat = _make_strategy(db, project.id, suffix="blocker")
        run = _make_run(db, strat.id, run_type="backtest")
        score = _make_reliability_score(db, strat.id)
        try:
            data = generate_strategy_risk_narrative(
                strat.id, db, target_stage="shadow"
            )
            assert data.primary_risks or data.recommended_next_actions, (
                "Expected blockers to surface as primary_risks or "
                "recommended_next_actions"
            )
        finally:
            _cleanup(db, score, run, strat)

    def test_recommended_actions_deterministic(self, db):
        from app.services.risk_narrative import generate_strategy_risk_narrative

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="determ-actions")
        run = _make_run(db, strat.id, run_type="backtest")
        score = _make_reliability_score(db, strat.id)
        try:
            a = generate_strategy_risk_narrative(strat.id, db)
            b = generate_strategy_risk_narrative(strat.id, db)
            assert a.recommended_next_actions == b.recommended_next_actions, (
                "recommended_next_actions not deterministic:\n"
                f"  first={a.recommended_next_actions}\n"
                f"  second={b.recommended_next_actions}"
            )
        finally:
            _cleanup(db, score, run, strat)

    def test_source_scores_present(self, db):
        from app.services.risk_narrative import generate_strategy_risk_narrative

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="scores")
        run = _make_run(db, strat.id, run_type="backtest")
        score = _make_reliability_score(db, strat.id)
        try:
            data = generate_strategy_risk_narrative(strat.id, db)
            expected_keys = {
                "reliability_score",
                "backtest_reality_score",
                "evidence_verification_score",
                "readiness_score",
                "shadow_drift_score",
            }
            missing = expected_keys - set(data.source_scores.keys())
            assert not missing, (
                f"Missing source_scores keys: {missing}; "
                f"present: {set(data.source_scores.keys())}"
            )
        finally:
            _cleanup(db, score, run, strat)

    def test_has_disclaimer(self, db):
        from app.services.risk_narrative import generate_strategy_risk_narrative

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="disclaimer")
        try:
            data = generate_strategy_risk_narrative(strat.id, db)
            assert "not trading advice" in data.disclaimer.lower(), (
                f"Expected 'not trading advice' in disclaimer, got: {data.disclaimer!r}"
            )
        finally:
            _cleanup(db, strat)

    def test_no_hallucinated_evidence(self, db):
        from app.services.risk_narrative import generate_strategy_risk_narrative

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="nohallucinate")
        run = _make_run(db, strat.id, run_type="backtest")
        score = _make_reliability_score(db, strat.id)
        alert = _make_alert(db, strat, severity="high", status="open")
        try:
            data = generate_strategy_risk_narrative(strat.id, db, target_stage="shadow")
            for s in data.primary_strengths:
                assert isinstance(s.evidence, str) and s.evidence.strip(), (
                    f"Strength {s.key!r} has empty evidence"
                )
            for r in data.primary_risks:
                assert isinstance(r.evidence, str) and r.evidence.strip(), (
                    f"Risk {r.key!r} has empty evidence"
                )
            # Deterministic / sourced: the narrative must not advertise AI.
            assert "ai" not in data.narrative.lower().split(), (
                f"Narrative should not contain the word 'AI'; narrative={data.narrative!r}"
            )
            assert "AI" not in data.narrative, (
                f"Narrative should not contain 'AI'; narrative={data.narrative!r}"
            )
        finally:
            _cleanup(db, alert, score, run, strat)

    def test_deterministic_output(self, db):
        from app.services.risk_narrative import generate_strategy_risk_narrative

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="determ-output")
        run = _make_run(db, strat.id, run_type="backtest")
        score = _make_reliability_score(db, strat.id)
        try:
            a = generate_strategy_risk_narrative(strat.id, db)
            b = generate_strategy_risk_narrative(strat.id, db)
            assert a.verdict == b.verdict, (
                f"verdict not deterministic: {a.verdict} vs {b.verdict}"
            )
            assert a.headline == b.headline, (
                f"headline not deterministic:\n  {a.headline}\n  {b.headline}"
            )
            assert len(a.primary_risks) == len(b.primary_risks), (
                f"number of risks not deterministic: "
                f"{len(a.primary_risks)} vs {len(b.primary_risks)}"
            )
        finally:
            _cleanup(db, score, run, strat)


# ---------------------------------------------------------------------------
# TestNarrativeReports
# ---------------------------------------------------------------------------


class TestNarrativeReports:
    """Tests for render_risk_narrative_report."""

    def test_json_report_parseable(self, db):
        from app.services.risk_narrative import render_risk_narrative_report

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="rep-json")
        run = _make_run(db, strat.id, run_type="backtest")
        score = _make_reliability_score(db, strat.id)
        try:
            content = render_risk_narrative_report(strat.id, db, format="json")
            parsed = json.loads(content)
            assert isinstance(parsed, dict)
            assert "narrative" in parsed, f"Missing 'narrative': {list(parsed.keys())}"
            assert "verdict" in parsed, f"Missing 'verdict': {list(parsed.keys())}"
        finally:
            _cleanup(db, score, run, strat)

    def test_markdown_report_has_header(self, db):
        from app.services.risk_narrative import render_risk_narrative_report

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="rep-md")
        run = _make_run(db, strat.id, run_type="backtest")
        score = _make_reliability_score(db, strat.id)
        try:
            content = render_risk_narrative_report(strat.id, db, format="markdown")
            assert "# Research Risk Narrative" in content, (
                "Expected '# Research Risk Narrative' header in markdown report"
            )
        finally:
            _cleanup(db, score, run, strat)

    def test_markdown_contains_narrative_paragraph(self, db):
        from app.services.risk_narrative import (
            generate_strategy_risk_narrative,
            render_risk_narrative_report,
        )

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="rep-md-para")
        run = _make_run(db, strat.id, run_type="backtest")
        score = _make_reliability_score(db, strat.id)
        try:
            data = generate_strategy_risk_narrative(strat.id, db)
            content = render_risk_narrative_report(strat.id, db, format="markdown")
            assert data.narrative in content, (
                "Expected markdown report to include the narrative paragraph"
            )
        finally:
            _cleanup(db, score, run, strat)


# ---------------------------------------------------------------------------
# TestNarrativeEndpoints
# ---------------------------------------------------------------------------


class TestNarrativeEndpoints:
    """Integration tests via TestClient for the M100 risk-narrative endpoints."""

    def test_narrative_endpoint_200(self, client, db):
        strategy = _get_seeded_strategy(db)
        assert strategy is not None
        resp = client.get(f"/api/strategies/{strategy.id}/risk-narrative")
        assert resp.status_code == 200, (
            f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        )
        data = resp.json()
        assert "headline" in data, f"Missing 'headline': {list(data.keys())}"
        assert "verdict" in data, f"Missing 'verdict': {list(data.keys())}"
        assert "narrative" in data, f"Missing 'narrative': {list(data.keys())}"

    def test_unknown_strategy_404(self, client):
        fake_id = uuid.uuid4()
        resp = client.get(f"/api/strategies/{fake_id}/risk-narrative")
        assert resp.status_code == 404

    def test_narrative_target_stage(self, client, db):
        strategy = _get_seeded_strategy(db)
        assert strategy is not None
        resp = client.get(
            f"/api/strategies/{strategy.id}/risk-narrative?target_stage=shadow"
        )
        assert resp.status_code == 200, (
            f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        )

    def test_report_json_200(self, client, db):
        strategy = _get_seeded_strategy(db)
        assert strategy is not None
        resp = client.get(
            f"/api/strategies/{strategy.id}/risk-narrative/report?format=json"
        )
        assert resp.status_code == 200, (
            f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        )

    def test_report_markdown_200(self, client, db):
        strategy = _get_seeded_strategy(db)
        assert strategy is not None
        resp = client.get(
            f"/api/strategies/{strategy.id}/risk-narrative/report?format=markdown"
        )
        assert resp.status_code == 200, (
            f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        )

    def test_report_invalid_format_400(self, client, db):
        strategy = _get_seeded_strategy(db)
        assert strategy is not None
        resp = client.get(
            f"/api/strategies/{strategy.id}/risk-narrative/report?format=xml"
        )
        assert resp.status_code == 400
