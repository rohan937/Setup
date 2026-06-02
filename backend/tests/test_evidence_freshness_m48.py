"""M48 tests: Evidence Freshness.

Tests for:
  - GET /api/strategies/{id}/freshness endpoint
  - Evidence freshness status computation (fresh/aging/stale/missing)
  - Overall freshness score calculation
  - Suggested refresh order
  - Language policy (no investment advice language)

All tests use the shared session-scoped fixtures from conftest.py.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FORBIDDEN_INVESTMENT_WORDS = ["buy", "sell", "profit", "investment advice"]
FORBIDDEN_AI_WORDS = ["AI", "prediction"]


def _has_forbidden(text: str, words: list[str]) -> list[str]:
    low = text.lower()
    return [w for w in words if w.lower() in low]


def _make_strategy(db, project_id, *, suffix: str = "") -> object:
    from app.models.strategy import Strategy

    slug = f"m48-test-{suffix}-{uuid.uuid4().hex[:8]}"
    strat = Strategy(
        project_id=project_id,
        name=f"M48 Test Strategy {suffix}",
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


def _make_signal_snapshot(db, strategy_id) -> object:
    from app.models.signal_snapshot import SignalSnapshot
    import hashlib, json

    rows = [{"symbol": "AAPL", "value": 1.0}]
    sig_hash = hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()
    snap = SignalSnapshot(
        strategy_id=strategy_id,
        label=f"sig-{uuid.uuid4().hex[:6]}",
        rows_json=rows,
        row_count=1,
        symbol_count=1,
        symbols_json=["AAPL"],
        signal_hash=sig_hash,
        quality_score=90,
    )
    db.add(snap)
    db.flush()
    return snap


def _make_reliability_score(db, strategy_id) -> object:
    from app.models.strategy_reliability_score import StrategyReliabilityScore

    score = StrategyReliabilityScore(
        strategy_id=strategy_id,
        overall_score=80.0,
        status="good",
        generated_at=datetime.now(timezone.utc),
    )
    db.add(score)
    db.flush()
    return score


def _make_backtest_audit(db, strategy_run_id) -> object:
    from app.models.backtest_audit import BacktestAudit

    audit = BacktestAudit(
        strategy_run_id=strategy_run_id,
        trust_score=85,
        overall_status="good",
        summary="No major issues.",
    )
    db.add(audit)
    db.flush()
    return audit


def _get_seeded_project(db):
    from app.models.project import Project

    return db.query(Project).first()


def _old_dt(days: int = 60) -> datetime:
    """Return a timezone-aware datetime that is `days` days in the past."""
    return datetime.now(timezone.utc) - timedelta(days=days)


# ---------------------------------------------------------------------------
# TestFreshnessEndpoint
# ---------------------------------------------------------------------------


class TestFreshnessEndpoint:
    """Integration tests via TestClient for the freshness endpoint."""

    def test_endpoint_returns_200(self, client, db):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="ep200")
        _make_run(db, strat.id)
        db.commit()

        try:
            resp = client.get(f"/api/strategies/{strat.id}/freshness")
            assert resp.status_code == 200
        finally:
            from app.models.strategy_run import StrategyRun
            from app.models.strategy import Strategy

            for r in db.query(StrategyRun).filter(StrategyRun.strategy_id == strat.id).all():
                db.delete(r)
            db.delete(db.query(Strategy).get(strat.id))
            db.commit()

    def test_response_fields(self, client, db):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="fields")
        _make_run(db, strat.id)
        db.commit()

        try:
            resp = client.get(f"/api/strategies/{strat.id}/freshness")
            assert resp.status_code == 200
            data = resp.json()
            assert "evidence_items" in data
            assert "overall_freshness_score" in data
            assert "freshness_status" in data
            assert "suggested_refresh_order" in data
            assert "strategy_id" in data
            assert "strategy_name" in data
            assert "deterministic_summary" in data
            assert "stale_count" in data
            assert "missing_count" in data
            assert "aging_count" in data
            assert "fresh_count" in data
        finally:
            from app.models.strategy_run import StrategyRun
            from app.models.strategy import Strategy

            for r in db.query(StrategyRun).filter(StrategyRun.strategy_id == strat.id).all():
                db.delete(r)
            db.delete(db.query(Strategy).get(strat.id))
            db.commit()

    def test_unknown_strategy_404(self, client, db):
        fake_id = uuid.uuid4()
        resp = client.get(f"/api/strategies/{fake_id}/freshness")
        assert resp.status_code == 404

    def test_evidence_items_count(self, client, db):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="items10")
        db.commit()

        try:
            resp = client.get(f"/api/strategies/{strat.id}/freshness")
            assert resp.status_code == 200
            data = resp.json()
            # Should have exactly 10 evidence types
            assert len(data["evidence_items"]) == 10
            types = {item["evidence_type"] for item in data["evidence_items"]}
            assert "strategy_runs" in types
            assert "dataset_snapshots" in types
            assert "signal_snapshots" in types
            assert "universe_snapshots" in types
            assert "config_snapshots" in types
            assert "backtest_audits" in types
            assert "reliability_scores" in types
            assert "reports" in types
            assert "timeline_events" in types
            assert "alerts" in types
        finally:
            from app.models.strategy import Strategy

            db.delete(db.query(Strategy).get(strat.id))
            db.commit()


# ---------------------------------------------------------------------------
# TestFreshnessItemStatus
# ---------------------------------------------------------------------------


class TestFreshnessItemStatus:
    """Unit-level tests that check per-item freshness status."""

    def test_fresh_run_status(self, client, db):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="freshrun")
        # Run created now → should be fresh
        _make_run(db, strat.id)
        db.commit()

        try:
            resp = client.get(f"/api/strategies/{strat.id}/freshness")
            assert resp.status_code == 200
            data = resp.json()
            run_item = next(i for i in data["evidence_items"] if i["evidence_type"] == "strategy_runs")
            assert run_item["status"] == "fresh"
        finally:
            from app.models.strategy_run import StrategyRun
            from app.models.strategy import Strategy

            for r in db.query(StrategyRun).filter(StrategyRun.strategy_id == strat.id).all():
                db.delete(r)
            db.delete(db.query(Strategy).get(strat.id))
            db.commit()

    def test_stale_run_status(self, client, db):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="stalerun")
        run = _make_run(db, strat.id)
        # Set created_at to >30 days ago to make it stale
        from app.models.strategy_run import StrategyRun

        db.query(StrategyRun).filter(StrategyRun.id == run.id).update(
            {"created_at": _old_dt(45)}
        )
        db.commit()

        try:
            resp = client.get(f"/api/strategies/{strat.id}/freshness")
            assert resp.status_code == 200
            data = resp.json()
            run_item = next(i for i in data["evidence_items"] if i["evidence_type"] == "strategy_runs")
            assert run_item["status"] == "stale"
        finally:
            for r in db.query(StrategyRun).filter(StrategyRun.strategy_id == strat.id).all():
                db.delete(r)
            from app.models.strategy import Strategy

            db.delete(db.query(Strategy).get(strat.id))
            db.commit()

    def test_missing_run(self, client, db):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="missingrun")
        db.commit()

        try:
            resp = client.get(f"/api/strategies/{strat.id}/freshness")
            assert resp.status_code == 200
            data = resp.json()
            run_item = next(i for i in data["evidence_items"] if i["evidence_type"] == "strategy_runs")
            assert run_item["status"] == "missing"
            assert run_item["count"] == 0
        finally:
            from app.models.strategy import Strategy

            db.delete(db.query(Strategy).get(strat.id))
            db.commit()

    def test_fresh_signal_snapshot(self, client, db):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="freshsig")
        _make_signal_snapshot(db, strat.id)
        db.commit()

        try:
            resp = client.get(f"/api/strategies/{strat.id}/freshness")
            assert resp.status_code == 200
            data = resp.json()
            sig_item = next(i for i in data["evidence_items"] if i["evidence_type"] == "signal_snapshots")
            assert sig_item["status"] == "fresh"
        finally:
            from app.models.signal_snapshot import SignalSnapshot
            from app.models.strategy import Strategy

            for s in db.query(SignalSnapshot).filter(SignalSnapshot.strategy_id == strat.id).all():
                db.delete(s)
            db.delete(db.query(Strategy).get(strat.id))
            db.commit()

    def test_missing_signal(self, client, db):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="missingsig")
        db.commit()

        try:
            resp = client.get(f"/api/strategies/{strat.id}/freshness")
            assert resp.status_code == 200
            data = resp.json()
            sig_item = next(i for i in data["evidence_items"] if i["evidence_type"] == "signal_snapshots")
            assert sig_item["status"] == "missing"
            assert sig_item["count"] == 0
        finally:
            from app.models.strategy import Strategy

            db.delete(db.query(Strategy).get(strat.id))
            db.commit()

    def test_fresh_reliability_score(self, client, db):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="freshrel")
        _make_reliability_score(db, strat.id)
        db.commit()

        try:
            resp = client.get(f"/api/strategies/{strat.id}/freshness")
            assert resp.status_code == 200
            data = resp.json()
            rel_item = next(i for i in data["evidence_items"] if i["evidence_type"] == "reliability_scores")
            assert rel_item["status"] == "fresh"
        finally:
            from app.models.strategy_reliability_score import StrategyReliabilityScore
            from app.models.strategy import Strategy

            for s in db.query(StrategyReliabilityScore).filter(StrategyReliabilityScore.strategy_id == strat.id).all():
                db.delete(s)
            db.delete(db.query(Strategy).get(strat.id))
            db.commit()

    def test_stale_reliability_score(self, client, db):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="stalerel")
        score = _make_reliability_score(db, strat.id)
        from app.models.strategy_reliability_score import StrategyReliabilityScore

        db.query(StrategyReliabilityScore).filter(
            StrategyReliabilityScore.id == score.id
        ).update({"generated_at": _old_dt(35)})
        db.commit()

        try:
            resp = client.get(f"/api/strategies/{strat.id}/freshness")
            assert resp.status_code == 200
            data = resp.json()
            rel_item = next(i for i in data["evidence_items"] if i["evidence_type"] == "reliability_scores")
            assert rel_item["status"] == "stale"
        finally:
            for s in db.query(StrategyReliabilityScore).filter(StrategyReliabilityScore.strategy_id == strat.id).all():
                db.delete(s)
            from app.models.strategy import Strategy

            db.delete(db.query(Strategy).get(strat.id))
            db.commit()

    def test_alert_missing_no_penalty(self, client, db):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="alertmissing")
        db.commit()

        try:
            resp = client.get(f"/api/strategies/{strat.id}/freshness")
            assert resp.status_code == 200
            data = resp.json()
            alert_item = next(i for i in data["evidence_items"] if i["evidence_type"] == "alerts")
            # No alerts → missing, but severity should be info (not penalizing)
            assert alert_item["status"] == "missing"
            assert alert_item["severity"] == "info"
        finally:
            from app.models.strategy import Strategy

            db.delete(db.query(Strategy).get(strat.id))
            db.commit()


# ---------------------------------------------------------------------------
# TestOverallScore
# ---------------------------------------------------------------------------


class TestOverallScore:
    """Tests for overall freshness score computation."""

    def test_all_fresh_gives_high_score(self, client, db):
        import hashlib
        import json as json_mod
        from app.models.strategy_run import StrategyRun
        from app.models.signal_snapshot import SignalSnapshot
        from app.models.universe_snapshot import UniverseSnapshot
        from app.models.strategy_config_snapshot import StrategyConfigSnapshot
        from app.models.strategy_reliability_score import StrategyReliabilityScore
        from app.models.backtest_audit import BacktestAudit
        from app.models.report import Report
        from app.models.audit_timeline_event import AuditTimelineEvent
        from app.models.strategy import Strategy

        project = _get_seeded_project(db)
        org_id = project.organization_id
        strat = _make_strategy(db, project.id, suffix="allfresh")

        # Create fresh evidence for all high-weight types
        run = _make_run(db, strat.id)
        _make_backtest_audit(db, run.id)
        _make_signal_snapshot(db, strat.id)
        _make_reliability_score(db, strat.id)

        # Universe snapshot — provide universe_hash (required NOT NULL)
        symbols = ["AAPL", "MSFT"]
        uni_hash = hashlib.sha256(json_mod.dumps(sorted(symbols)).encode()).hexdigest()
        uni = UniverseSnapshot(
            strategy_id=strat.id,
            label="uni-test",
            symbol_count=len(symbols),
            symbols_json=symbols,
            universe_hash=uni_hash,
        )
        db.add(uni)

        # Config snapshot — provide config_hash (required NOT NULL)
        cfg_data = {"param": 1}
        cfg_hash = hashlib.sha256(json_mod.dumps(cfg_data, sort_keys=True).encode()).hexdigest()
        cfg_snap = StrategyConfigSnapshot(
            strategy_id=strat.id,
            label="cfg-test",
            config_json=cfg_data,
            config_hash=cfg_hash,
            param_count=1,
            assumption_count=0,
        )
        db.add(cfg_snap)

        # Report (fresh) — needed to avoid dragging score below 85
        rep = Report(
            organization_id=org_id,
            project_id=project.id,
            strategy_id=strat.id,
            report_type="strategy_reliability",
            title="Test Report",
            status="generated",
            summary="Test summary",
            generated_at=datetime.now(timezone.utc),
        )
        db.add(rep)

        # Timeline event (fresh)
        tl = AuditTimelineEvent(
            organization_id=org_id,
            project_id=project.id,
            strategy_id=strat.id,
            event_type="strategy_run_created",
            title="Test event",
            severity="info",
            event_time=datetime.now(timezone.utc),
        )
        db.add(tl)

        db.flush()
        db.commit()

        try:
            resp = client.get(f"/api/strategies/{strat.id}/freshness")
            assert resp.status_code == 200
            data = resp.json()
            score = data["overall_freshness_score"]
            assert score is not None
            assert score >= 85
            assert data["freshness_status"] == "fresh"
        finally:
            try:
                for obj in db.query(BacktestAudit).join(
                    StrategyRun, BacktestAudit.strategy_run_id == StrategyRun.id
                ).filter(StrategyRun.strategy_id == strat.id).all():
                    db.delete(obj)
                for r in db.query(StrategyRun).filter(StrategyRun.strategy_id == strat.id).all():
                    db.delete(r)
                for s in db.query(SignalSnapshot).filter(SignalSnapshot.strategy_id == strat.id).all():
                    db.delete(s)
                for u in db.query(UniverseSnapshot).filter(UniverseSnapshot.strategy_id == strat.id).all():
                    db.delete(u)
                for c in db.query(StrategyConfigSnapshot).filter(StrategyConfigSnapshot.strategy_id == strat.id).all():
                    db.delete(c)
                for sc in db.query(StrategyReliabilityScore).filter(StrategyReliabilityScore.strategy_id == strat.id).all():
                    db.delete(sc)
                for rp in db.query(Report).filter(Report.strategy_id == strat.id).all():
                    db.delete(rp)
                for te in db.query(AuditTimelineEvent).filter(AuditTimelineEvent.strategy_id == strat.id).all():
                    db.delete(te)
                db.delete(db.query(Strategy).get(strat.id))
                db.commit()
            except Exception:
                db.rollback()

    def test_stale_evidence_lowers_score(self, client, db):
        from app.models.strategy_run import StrategyRun
        from app.models.backtest_audit import BacktestAudit
        from app.models.strategy_reliability_score import StrategyReliabilityScore
        from app.models.signal_snapshot import SignalSnapshot
        from app.models.strategy import Strategy

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="stalescore")

        run = _make_run(db, strat.id)
        audit = _make_backtest_audit(db, run.id)
        score_obj = _make_reliability_score(db, strat.id)
        sig = _make_signal_snapshot(db, strat.id)

        # Make runs and audits stale
        db.query(StrategyRun).filter(StrategyRun.id == run.id).update(
            {"created_at": _old_dt(60)}
        )
        db.query(BacktestAudit).filter(BacktestAudit.id == audit.id).update(
            {"created_at": _old_dt(60)}
        )
        db.query(StrategyReliabilityScore).filter(
            StrategyReliabilityScore.id == score_obj.id
        ).update({"generated_at": _old_dt(60)})
        db.commit()

        try:
            resp = client.get(f"/api/strategies/{strat.id}/freshness")
            assert resp.status_code == 200
            data = resp.json()
            score = data["overall_freshness_score"]
            assert score is not None
            assert score < 85
        finally:
            for a in db.query(BacktestAudit).join(
                StrategyRun, BacktestAudit.strategy_run_id == StrategyRun.id
            ).filter(StrategyRun.strategy_id == strat.id).all():
                db.delete(a)
            for r in db.query(StrategyRun).filter(StrategyRun.strategy_id == strat.id).all():
                db.delete(r)
            for s in db.query(SignalSnapshot).filter(SignalSnapshot.strategy_id == strat.id).all():
                db.delete(s)
            for sc in db.query(StrategyReliabilityScore).filter(StrategyReliabilityScore.strategy_id == strat.id).all():
                db.delete(sc)
            db.delete(db.query(Strategy).get(strat.id))
            db.commit()

    def test_missing_evidence_returns_null(self, client, db):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="nullscore")
        # Create only 1 evidence type — should be < 3 non-missing → null score
        _make_run(db, strat.id)
        db.commit()

        try:
            resp = client.get(f"/api/strategies/{strat.id}/freshness")
            assert resp.status_code == 200
            data = resp.json()
            # With only strategy_runs filled in, < 3 meaningful types → null score
            assert data["overall_freshness_score"] is None
            assert data["freshness_status"] == "missing_evidence"
        finally:
            from app.models.strategy_run import StrategyRun
            from app.models.strategy import Strategy

            for r in db.query(StrategyRun).filter(StrategyRun.strategy_id == strat.id).all():
                db.delete(r)
            db.delete(db.query(Strategy).get(strat.id))
            db.commit()

    def test_refresh_order_stale_first(self, client, db):
        from app.models.strategy_run import StrategyRun
        from app.models.signal_snapshot import SignalSnapshot
        from app.models.strategy import Strategy

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="refreshorder")

        # Fresh signal snapshot + stale run
        run = _make_run(db, strat.id)
        sig = _make_signal_snapshot(db, strat.id)
        db.query(StrategyRun).filter(StrategyRun.id == run.id).update(
            {"created_at": _old_dt(45)}
        )
        db.commit()

        try:
            resp = client.get(f"/api/strategies/{strat.id}/freshness")
            assert resp.status_code == 200
            data = resp.json()
            refresh_order = data["suggested_refresh_order"]
            # Strategy Runs (stale) should appear before any aging items
            if "Strategy Runs" in refresh_order:
                idx_runs = refresh_order.index("Strategy Runs")
                # All items before Strategy Runs should also be stale
                for item_label in refresh_order[:idx_runs]:
                    item = next(
                        i for i in data["evidence_items"] if i["label"] == item_label
                    )
                    assert item["status"] in ("stale",), (
                        f"{item_label} before stale run but status={item['status']}"
                    )
        finally:
            for r in db.query(StrategyRun).filter(StrategyRun.strategy_id == strat.id).all():
                db.delete(r)
            for s in db.query(SignalSnapshot).filter(SignalSnapshot.strategy_id == strat.id).all():
                db.delete(s)
            db.delete(db.query(Strategy).get(strat.id))
            db.commit()


# ---------------------------------------------------------------------------
# TestSummaryLanguage
# ---------------------------------------------------------------------------


class TestSummaryLanguage:
    """Tests for language policy in deterministic_summary."""

    def test_no_ai_language(self, client, db):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="lang1")
        db.commit()

        try:
            resp = client.get(f"/api/strategies/{strat.id}/freshness")
            assert resp.status_code == 200
            summary = resp.json()["deterministic_summary"]
            found = _has_forbidden(summary, FORBIDDEN_AI_WORDS)
            assert not found, f"AI language found in summary: {found}"
        finally:
            from app.models.strategy import Strategy

            db.delete(db.query(Strategy).get(strat.id))
            db.commit()

    def test_no_investment_language(self, client, db):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="lang2")
        db.commit()

        try:
            resp = client.get(f"/api/strategies/{strat.id}/freshness")
            assert resp.status_code == 200
            summary = resp.json()["deterministic_summary"]
            found = _has_forbidden(summary, FORBIDDEN_INVESTMENT_WORDS)
            assert not found, f"Investment language found in summary: {found}"
        finally:
            from app.models.strategy import Strategy

            db.delete(db.query(Strategy).get(strat.id))
            db.commit()

    def test_no_timeline_event(self, client, db):
        from app.models.audit_timeline_event import AuditTimelineEvent

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="notimeline")
        _make_run(db, strat.id)
        db.commit()

        before_count = (
            db.query(AuditTimelineEvent)
            .filter(AuditTimelineEvent.strategy_id == strat.id)
            .count()
        )

        try:
            resp = client.get(f"/api/strategies/{strat.id}/freshness")
            assert resp.status_code == 200

            after_count = (
                db.query(AuditTimelineEvent)
                .filter(AuditTimelineEvent.strategy_id == strat.id)
                .count()
            )
            assert after_count == before_count, (
                "Freshness endpoint should not create AuditTimelineEvents"
            )
        finally:
            from app.models.strategy_run import StrategyRun
            from app.models.strategy import Strategy

            for r in db.query(StrategyRun).filter(StrategyRun.strategy_id == strat.id).all():
                db.delete(r)
            db.delete(db.query(Strategy).get(strat.id))
            db.commit()
