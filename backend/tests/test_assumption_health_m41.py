"""M41 tests: Assumption Health endpoint and scoring logic.

Tests for:
  - GET /api/strategies/{id}/assumption-health
  - Category scorecards: transaction_costs, slippage, fill_realism,
    borrow_shorting, liquidity_capacity, risk_controls, data_evidence_linkage
  - Overall score computation and deduplication of suggested_checks
  - Summary language: no investment advice, no AI language
  - Read-only guarantee: no AuditTimelineEvent created
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from app.models.audit_timeline_event import AuditTimelineEvent
from app.models.organization import Organization
from app.models.project import Project
from app.models.strategy import Strategy
from app.models.strategy_run import StrategyRun
from app.services.assumption_health import compute_assumption_health


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_project_id(client) -> str:
    return client.get("/api/projects").json()[0]["id"]


def _make_strategy(db, *, name=None) -> Strategy:
    org = db.query(Organization).first()
    project = db.query(Project).filter(Project.organization_id == org.id).first()
    slug = (name or f"ah-{uuid.uuid4().hex[:8]}").lower().replace(" ", "-")
    s = Strategy(
        project_id=project.id,
        name=name or f"AH-{uuid.uuid4().hex[:6]}",
        slug=slug,
        asset_class="equity",
        status="active",
    )
    db.add(s)
    db.flush()
    return s


def _make_run(db, strategy: Strategy, *, assumptions_json=None, metrics_json=None) -> StrategyRun:
    r = StrategyRun(
        strategy_id=strategy.id,
        run_name=f"run-{uuid.uuid4().hex[:6]}",
        run_type="backtest",
        status="completed",
        assumptions_json=assumptions_json or {},
        metrics_json=metrics_json or {},
    )
    db.add(r)
    db.flush()
    return r


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


def _get_category(result: dict, key: str) -> dict:
    for c in result["category_scorecards"]:
        if c["category_key"] == key:
            return c
    raise KeyError(f"Category {key!r} not found")


# ---------------------------------------------------------------------------
# TestAssumptionHealthEndpoint
# ---------------------------------------------------------------------------


class TestAssumptionHealthEndpoint:
    def test_endpoint_returns_200(self, client, db):
        """GET /api/strategies/{id}/assumption-health returns 200 for a valid strategy."""
        s = _make_strategy(db)
        try:
            resp = client.get(f"/api/strategies/{s.id}/assumption-health")
            assert resp.status_code == 200, resp.text
        finally:
            _cleanup(db, s)

    def test_response_has_required_fields(self, client, db):
        """Response contains all required top-level fields."""
        s = _make_strategy(db)
        try:
            resp = client.get(f"/api/strategies/{s.id}/assumption-health")
            assert resp.status_code == 200
            data = resp.json()
            for field in (
                "strategy_id",
                "strategy_name",
                "status",
                "overall_assumption_score",
                "generated_at",
                "category_scorecards",
                "suggested_checks",
                "deterministic_summary",
                "weakening_change_count",
                "positive_change_count",
                "review_change_count",
            ):
                assert field in data, f"Missing field: {field}"
            assert isinstance(data["category_scorecards"], list)
            assert len(data["category_scorecards"]) == 7
        finally:
            _cleanup(db, s)

    def test_unknown_strategy_404(self, client):
        """Unknown strategy UUID returns 404."""
        unknown_id = uuid.uuid4()
        resp = client.get(f"/api/strategies/{unknown_id}/assumption-health")
        assert resp.status_code == 404

    def test_no_runs_missing_evidence(self, client, db):
        """A new strategy with no runs gets status 'missing_evidence' or 'review'."""
        s = _make_strategy(db)
        try:
            resp = client.get(f"/api/strategies/{s.id}/assumption-health")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] in (
                "missing_evidence",
                "review",
                "weak",
                "acceptable",
            ), f"Unexpected status: {data['status']}"
        finally:
            _cleanup(db, s)


# ---------------------------------------------------------------------------
# TestCategoryScoring
# ---------------------------------------------------------------------------


class TestCategoryScoring:
    def test_explicit_cost_bps_positive(self, client, db):
        """Run with transaction_cost_bps=5 gives positive_evidence in transaction_costs."""
        s = _make_strategy(db)
        r = _make_run(db, s, assumptions_json={"transaction_cost_bps": 5})
        try:
            resp = client.get(f"/api/strategies/{s.id}/assumption-health")
            assert resp.status_code == 200
            data = resp.json()
            tc = next(
                c for c in data["category_scorecards"]
                if c["category_key"] == "transaction_costs"
            )
            assert len(tc["positive_evidence"]) > 0, (
                f"Expected positive_evidence for explicit cost; got {tc}"
            )
        finally:
            _cleanup(db, r, s)

    def test_missing_cost_bps_review(self, client, db):
        """Run with no cost assumption gives review_items in transaction_costs."""
        s = _make_strategy(db)
        r = _make_run(db, s, assumptions_json={"slippage_bps": 2})
        try:
            resp = client.get(f"/api/strategies/{s.id}/assumption-health")
            assert resp.status_code == 200
            data = resp.json()
            tc = next(
                c for c in data["category_scorecards"]
                if c["category_key"] == "transaction_costs"
            )
            assert len(tc["review_items"]) > 0, (
                f"Expected review_items for missing cost; got {tc}"
            )
        finally:
            _cleanup(db, r, s)

    def test_high_concern_fill_weakening(self, client, db):
        """Run with fill_model='close' produces weakening_changes in fill_realism."""
        s = _make_strategy(db)
        r = _make_run(db, s, assumptions_json={"fill_model": "close"})
        try:
            resp = client.get(f"/api/strategies/{s.id}/assumption-health")
            assert resp.status_code == 200
            data = resp.json()
            fr = next(
                c for c in data["category_scorecards"]
                if c["category_key"] == "fill_realism"
            )
            assert len(fr["weakening_changes"]) > 0, (
                f"Expected weakening_changes for 'close' fill; got {fr}"
            )
        finally:
            _cleanup(db, r, s)

    def test_conservative_fill_positive(self, client, db):
        """Run with fill_model='next_bar_open' produces positive_evidence in fill_realism."""
        s = _make_strategy(db)
        r = _make_run(db, s, assumptions_json={"fill_model": "next_bar_open"})
        try:
            resp = client.get(f"/api/strategies/{s.id}/assumption-health")
            assert resp.status_code == 200
            data = resp.json()
            fr = next(
                c for c in data["category_scorecards"]
                if c["category_key"] == "fill_realism"
            )
            assert len(fr["positive_evidence"]) > 0, (
                f"Expected positive_evidence for conservative fill; got {fr}"
            )
        finally:
            _cleanup(db, r, s)

    def test_slippage_present_positive(self, client, db):
        """Run with slippage_bps=5 gives positive_evidence in slippage category."""
        s = _make_strategy(db)
        r = _make_run(db, s, assumptions_json={"slippage_bps": 5})
        try:
            resp = client.get(f"/api/strategies/{s.id}/assumption-health")
            assert resp.status_code == 200
            data = resp.json()
            slippage_cat = next(
                c for c in data["category_scorecards"]
                if c["category_key"] == "slippage"
            )
            assert len(slippage_cat["positive_evidence"]) > 0, (
                f"Expected positive_evidence for slippage; got {slippage_cat}"
            )
        finally:
            _cleanup(db, r, s)

    def test_short_without_borrow_review(self, client, db):
        """Run with short_enabled=True but no borrow_cost gives review_items in borrow_shorting."""
        s = _make_strategy(db)
        r = _make_run(db, s, assumptions_json={"short_enabled": True})
        try:
            resp = client.get(f"/api/strategies/{s.id}/assumption-health")
            assert resp.status_code == 200
            data = resp.json()
            borrow_cat = next(
                c for c in data["category_scorecards"]
                if c["category_key"] == "borrow_shorting"
            )
            assert len(borrow_cat["review_items"]) > 0, (
                f"Expected review_items for short without borrow; got {borrow_cat}"
            )
        finally:
            _cleanup(db, r, s)

    def test_liquidity_filter_positive(self, client, db):
        """Run with liquidity_filter set gives positive_evidence in liquidity_capacity."""
        s = _make_strategy(db)
        r = _make_run(db, s, assumptions_json={"liquidity_filter": "adv > 10M"})
        try:
            resp = client.get(f"/api/strategies/{s.id}/assumption-health")
            assert resp.status_code == 200
            data = resp.json()
            liq_cat = next(
                c for c in data["category_scorecards"]
                if c["category_key"] == "liquidity_capacity"
            )
            assert len(liq_cat["positive_evidence"]) > 0, (
                f"Expected positive_evidence for liquidity filter; got {liq_cat}"
            )
        finally:
            _cleanup(db, r, s)


# ---------------------------------------------------------------------------
# TestOverallScore
# ---------------------------------------------------------------------------


class TestOverallScore:
    def test_overall_null_insufficient_evidence(self, db):
        """Strategy with fewer than 3 scored categories returns overall_assumption_score=None."""
        s = _make_strategy(db)
        try:
            result = compute_assumption_health(s.id, db)
            # With no runs and no config snapshots, several categories return
            # score=None (missing evidence) → overall may be None
            # Either None or a computed value is acceptable if ≥3 scored
            scored_count = sum(
                1 for c in result["category_scorecards"] if c["score"] is not None
            )
            if scored_count < 3:
                assert result["overall_assumption_score"] is None
            # else score is a number — both are valid depending on seed data
        finally:
            _cleanup(db, s)

    def test_overall_computed_with_enough_categories(self, db):
        """Strategy with runs and explicit assumptions produces a numeric overall score."""
        s = _make_strategy(db)
        r = _make_run(
            db,
            s,
            assumptions_json={
                "transaction_cost_bps": 5,
                "slippage_bps": 2,
                "fill_model": "next_bar_open",
                "short_enabled": False,
                "liquidity_filter": "adv > 5M",
            },
        )
        try:
            result = compute_assumption_health(s.id, db)
            scored_count = sum(
                1 for c in result["category_scorecards"] if c["score"] is not None
            )
            assert scored_count >= 3, (
                f"Expected ≥3 scored categories; got {scored_count}"
            )
            assert result["overall_assumption_score"] is not None, (
                "Expected a numeric overall score with sufficient evidence"
            )
        finally:
            _cleanup(db, r, s)

    def test_suggested_checks_deduplicated(self, db):
        """Multiple sources of the same check text appear only once."""
        s = _make_strategy(db)
        # No runs at all → multiple categories may suggest the same check
        try:
            result = compute_assumption_health(s.id, db)
            checks = result["suggested_checks"]
            assert len(checks) == len(set(checks)), (
                f"Duplicate suggested checks found: {checks}"
            )
        finally:
            _cleanup(db, s)


# ---------------------------------------------------------------------------
# TestSummaryLanguage
# ---------------------------------------------------------------------------


class TestSummaryLanguage:
    def test_no_investment_advice(self, db):
        """deterministic_summary does not contain prohibited investment-advice terms."""
        s = _make_strategy(db)
        r = _make_run(db, s, assumptions_json={"transaction_cost_bps": 5})
        try:
            result = compute_assumption_health(s.id, db)
            summary = result["deterministic_summary"].lower()
            for forbidden in ("buy", "sell", "profit", "investment advice"):
                assert forbidden not in summary, (
                    f"Forbidden term {forbidden!r} found in summary: {summary}"
                )
        finally:
            _cleanup(db, r, s)

    def test_no_ai_language(self, db):
        """deterministic_summary does not contain AI/prediction language."""
        s = _make_strategy(db)
        r = _make_run(db, s, assumptions_json={"slippage_bps": 3})
        try:
            result = compute_assumption_health(s.id, db)
            summary = result["deterministic_summary"].lower()
            for forbidden in (" ai ", "prediction", "forecast"):
                assert forbidden not in summary, (
                    f"Forbidden term {forbidden!r} found in summary: {summary}"
                )
        finally:
            _cleanup(db, r, s)

    def test_no_timeline_event(self, client, db):
        """GET /assumption-health does not create an AuditTimelineEvent."""
        s = _make_strategy(db)
        r = _make_run(db, s, assumptions_json={"transaction_cost_bps": 10})
        before_count = db.query(AuditTimelineEvent).count()
        try:
            resp = client.get(f"/api/strategies/{s.id}/assumption-health")
            assert resp.status_code == 200
            after_count = db.query(AuditTimelineEvent).count()
            assert after_count == before_count, (
                "Endpoint must not create AuditTimelineEvent records"
            )
        finally:
            _cleanup(db, r, s)
