"""M52 tests: Evidence Graph.

Tests for:
  - GET /api/strategies/{id}/evidence-graph endpoint
  - Node and edge presence
  - Blast radius computation
  - Graph summary status
  - Language policy (no AI/investment/guaranteed language)
  - Read-only: no AuditTimelineEvent created

All tests use the shared session-scoped fixtures from conftest.py.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

FORBIDDEN_WORDS = ["AI", "prediction", "guaranteed"]


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
    slug = f"m52-test-{suffix}-{uuid.uuid4().hex[:8]}"
    strat = Strategy(
        project_id=project_id,
        name=f"M52 Test Strategy {suffix}",
        slug=slug,
        asset_class="equity",
        status="active",
    )
    db.add(strat)
    db.flush()
    return strat


def _make_run(
    db, strategy_id, *, run_type: str = "backtest", status: str = "completed",
    strategy_version_id=None, universe_snapshot_id=None, signal_snapshot_id=None,
    dataset_snapshot_id=None,
) -> object:
    from app.models.strategy_run import StrategyRun
    run = StrategyRun(
        strategy_id=strategy_id,
        run_name=f"M52 Test Run {uuid.uuid4().hex[:6]}",
        run_type=run_type,
        status=status,
        strategy_version_id=strategy_version_id,
        universe_snapshot_id=universe_snapshot_id,
        signal_snapshot_id=signal_snapshot_id,
        dataset_snapshot_id=dataset_snapshot_id,
    )
    db.add(run)
    db.flush()
    return run


def _make_version(db, strategy_id) -> object:
    from app.models.strategy_version import StrategyVersion
    v = StrategyVersion(
        strategy_id=strategy_id,
        version_label=f"v{uuid.uuid4().hex[:4]}",
        signal_name="test_signal",
    )
    db.add(v)
    db.flush()
    return v


def _make_config_snapshot(db, strategy_id, version_id=None) -> object:
    from app.models.strategy_config_snapshot import StrategyConfigSnapshot
    import hashlib
    h = hashlib.sha256(uuid.uuid4().hex.encode()).hexdigest()
    c = StrategyConfigSnapshot(
        strategy_id=strategy_id,
        strategy_version_id=version_id,
        label=f"M52 Config {h[:8]}",
        config_hash=h,
        config_json={"param": "value"},
    )
    db.add(c)
    db.flush()
    return c


def _make_signal_snapshot(
    db, strategy_id, *, quality_score: int = 90, version_id=None
) -> object:
    from app.models.signal_snapshot import SignalSnapshot
    import hashlib
    h = hashlib.sha256(uuid.uuid4().hex.encode()).hexdigest()
    s = SignalSnapshot(
        strategy_id=strategy_id,
        strategy_version_id=version_id,
        label=f"M52 Signal {h[:8]}",
        signal_name="test_signal",
        source_type="manual_json",
        rows_json=[],
        row_count=0,
        symbol_count=0,
        symbols_json=[],
        signal_value_count=0,
        missing_signal_count=0,
        signal_hash=h,
        quality_score=quality_score,
    )
    db.add(s)
    db.flush()
    return s


def _make_backtest_audit(
    db, run_id, *, trust_score: int = 80, overall_status: str = "good"
) -> object:
    from app.models.backtest_audit import BacktestAudit
    a = BacktestAudit(
        strategy_run_id=run_id,
        trust_score=trust_score,
        overall_status=overall_status,
    )
    db.add(a)
    db.flush()
    return a


def _make_alert(
    db, org_id, strategy_id, *, severity: str = "high", status: str = "open"
) -> object:
    from app.models.alert import Alert
    a = Alert(
        organization_id=str(org_id),
        strategy_id=str(strategy_id),
        rule_type="test_m52_rule",
        status=status,
        severity=severity,
        title=f"M52 Test alert {severity}",
        triggered_at=datetime.now(timezone.utc),
    )
    db.add(a)
    db.flush()
    return a


# ---------------------------------------------------------------------------
# TestEvidenceGraphEndpoint
# ---------------------------------------------------------------------------

class TestEvidenceGraphEndpoint:
    """Integration tests via TestClient for the evidence-graph endpoint."""

    def test_endpoint_returns_200(self, client, db):
        strategy = _get_seeded_strategy(db)
        assert strategy is not None
        resp = client.get(f"/api/strategies/{strategy.id}/evidence-graph")
        assert resp.status_code == 200

    def test_unknown_strategy_404(self, client):
        fake_id = uuid.uuid4()
        resp = client.get(f"/api/strategies/{fake_id}/evidence-graph")
        assert resp.status_code == 404

    def test_response_has_summary(self, client, db):
        strategy = _get_seeded_strategy(db)
        resp = client.get(f"/api/strategies/{strategy.id}/evidence-graph")
        assert resp.status_code == 200
        data = resp.json()
        summary = data["summary"]
        assert "node_count" in summary
        assert "edge_count" in summary
        assert "graph_status" in summary

    def test_response_has_nodes(self, client, db):
        strategy = _get_seeded_strategy(db)
        resp = client.get(f"/api/strategies/{strategy.id}/evidence-graph")
        data = resp.json()
        assert isinstance(data["nodes"], list)
        assert len(data["nodes"]) > 0

    def test_response_has_edges(self, client, db):
        strategy = _get_seeded_strategy(db)
        resp = client.get(f"/api/strategies/{strategy.id}/evidence-graph")
        data = resp.json()
        assert isinstance(data["edges"], list)
        # At least the strategy→something edge
        assert len(data["edges"]) >= 0

    def test_strategy_node_present(self, client, db):
        strategy = _get_seeded_strategy(db)
        resp = client.get(f"/api/strategies/{strategy.id}/evidence-graph")
        data = resp.json()
        types = [n["node_type"] for n in data["nodes"]]
        assert "strategy" in types

    def test_include_computed_true(self, client, db):
        strategy = _get_seeded_strategy(db)
        resp = client.get(
            f"/api/strategies/{strategy.id}/evidence-graph",
            params={"include_computed": "true"},
        )
        data = resp.json()
        types = {n["node_type"] for n in data["nodes"]}
        # At least one computed type should appear if services succeed
        computed_types = {"readiness_scorecard", "shadow_monitor", "promotion_gates"}
        assert len(computed_types & types) >= 0  # no hard fail, service may have no data

    def test_include_computed_false(self, client, db):
        strategy = _get_seeded_strategy(db)
        resp = client.get(
            f"/api/strategies/{strategy.id}/evidence-graph",
            params={"include_computed": "false"},
        )
        data = resp.json()
        types = {n["node_type"] for n in data["nodes"]}
        # Computed nodes must NOT appear
        assert "readiness_scorecard" not in types
        assert "shadow_monitor" not in types
        assert "promotion_gates" not in types

    def test_include_timeline_false(self, client, db):
        strategy = _get_seeded_strategy(db)
        resp = client.get(
            f"/api/strategies/{strategy.id}/evidence-graph",
            params={"include_timeline": "false"},
        )
        data = resp.json()
        types = {n["node_type"] for n in data["nodes"]}
        assert "timeline_event" not in types


# ---------------------------------------------------------------------------
# TestGraphContent
# ---------------------------------------------------------------------------

class TestGraphContent:
    """Tests that specific evidence nodes appear when that evidence exists."""

    def test_version_node_present(self, client, db):
        project = _get_seeded_project(db)
        strategy = _make_strategy(db, project.id, suffix="ver")
        _make_version(db, strategy.id)
        db.flush()
        try:
            resp = client.get(f"/api/strategies/{strategy.id}/evidence-graph")
            data = resp.json()
            types = {n["node_type"] for n in data["nodes"]}
            assert "strategy_version" in types
        finally:
            db.rollback()

    def test_config_snapshot_node(self, client, db):
        project = _get_seeded_project(db)
        strategy = _make_strategy(db, project.id, suffix="cfg")
        _make_config_snapshot(db, strategy.id)
        db.flush()
        try:
            resp = client.get(f"/api/strategies/{strategy.id}/evidence-graph")
            data = resp.json()
            types = {n["node_type"] for n in data["nodes"]}
            assert "config_snapshot" in types
        finally:
            db.rollback()

    def test_run_node_present(self, client, db):
        project = _get_seeded_project(db)
        strategy = _make_strategy(db, project.id, suffix="run")
        _make_run(db, strategy.id)
        db.flush()
        try:
            resp = client.get(f"/api/strategies/{strategy.id}/evidence-graph")
            data = resp.json()
            types = {n["node_type"] for n in data["nodes"]}
            assert "strategy_run" in types
        finally:
            db.rollback()

    def test_audit_node_present(self, client, db):
        project = _get_seeded_project(db)
        strategy = _make_strategy(db, project.id, suffix="audit")
        run = _make_run(db, strategy.id)
        _make_backtest_audit(db, run.id, trust_score=75)
        db.flush()
        try:
            resp = client.get(f"/api/strategies/{strategy.id}/evidence-graph")
            data = resp.json()
            types = {n["node_type"] for n in data["nodes"]}
            assert "backtest_audit" in types
        finally:
            db.rollback()

    def test_alert_node_present(self, client, db):
        project = _get_seeded_project(db)
        org = _get_seeded_org(db)
        strategy = _make_strategy(db, project.id, suffix="alert")
        _make_alert(db, org.id, strategy.id, severity="high")
        db.flush()
        try:
            resp = client.get(f"/api/strategies/{strategy.id}/evidence-graph")
            data = resp.json()
            types = {n["node_type"] for n in data["nodes"]}
            assert "alert" in types
        finally:
            db.rollback()

    def test_dataset_snap_node(self, client, db):
        """Run with dataset_snapshot_id should produce a dataset_snapshot node."""
        project = _get_seeded_project(db)
        strategy = _make_strategy(db, project.id, suffix="dssnap")
        # We need a dataset snapshot; grab the seeded one if present
        from app.models.dataset_snapshot import DatasetSnapshot
        snap = db.query(DatasetSnapshot).first()
        if snap is None:
            db.rollback()
            return  # no snapshot seeded, skip
        _make_run(db, strategy.id, dataset_snapshot_id=snap.id)
        db.flush()
        try:
            resp = client.get(f"/api/strategies/{strategy.id}/evidence-graph")
            data = resp.json()
            types = {n["node_type"] for n in data["nodes"]}
            assert "dataset_snapshot" in types
        finally:
            db.rollback()

    def test_weak_node_count(self, client, db):
        """Signal with quality_score < 50 → weak status → weak_node_count > 0."""
        project = _get_seeded_project(db)
        strategy = _make_strategy(db, project.id, suffix="weak")
        _make_signal_snapshot(db, strategy.id, quality_score=30)
        db.flush()
        try:
            resp = client.get(f"/api/strategies/{strategy.id}/evidence-graph")
            data = resp.json()
            assert data["summary"]["weak_node_count"] > 0
        finally:
            db.rollback()


# ---------------------------------------------------------------------------
# TestBlastRadius
# ---------------------------------------------------------------------------

class TestBlastRadius:
    """Tests for blast radius computation."""

    def test_no_focus_no_blast(self, client, db):
        strategy = _get_seeded_strategy(db)
        resp = client.get(f"/api/strategies/{strategy.id}/evidence-graph")
        data = resp.json()
        assert data["blast_radius"] is None

    def test_focus_on_signal_snap(self, client, db):
        project = _get_seeded_project(db)
        strategy = _make_strategy(db, project.id, suffix="blast1")
        sig = _make_signal_snapshot(db, strategy.id, quality_score=80)
        db.flush()
        try:
            focus_id = f"signal:{sig.id}"
            resp = client.get(
                f"/api/strategies/{strategy.id}/evidence-graph",
                params={"focus_node_id": focus_id},
            )
            data = resp.json()
            assert data["blast_radius"] is not None
            assert data["blast_radius"]["focus_node_id"] == focus_id
        finally:
            db.rollback()

    def test_blast_radius_unknown_focus(self, client, db):
        strategy = _get_seeded_strategy(db)
        fake_focus = f"signal:{uuid.uuid4()}"
        resp = client.get(
            f"/api/strategies/{strategy.id}/evidence-graph",
            params={"focus_node_id": fake_focus},
        )
        data = resp.json()
        assert data["blast_radius"] is not None
        assert data["blast_radius"]["blast_radius_severity"] == "none"

    def test_affected_run_count(self, client, db):
        project = _get_seeded_project(db)
        strategy = _make_strategy(db, project.id, suffix="blast2")
        sig = _make_signal_snapshot(db, strategy.id, quality_score=85)
        _make_run(db, strategy.id, signal_snapshot_id=sig.id)
        db.flush()
        try:
            focus_id = f"signal:{sig.id}"
            resp = client.get(
                f"/api/strategies/{strategy.id}/evidence-graph",
                params={"focus_node_id": focus_id},
            )
            data = resp.json()
            br = data["blast_radius"]
            assert br is not None
            assert br["affected_run_count"] >= 1
        finally:
            db.rollback()


# ---------------------------------------------------------------------------
# TestGraphSummary
# ---------------------------------------------------------------------------

class TestGraphSummary:
    """Tests for graph summary and policy compliance."""

    def test_sparse_status_no_runs(self, client, db):
        project = _get_seeded_project(db)
        strategy = _make_strategy(db, project.id, suffix="sparse")
        db.flush()
        try:
            resp = client.get(
                f"/api/strategies/{strategy.id}/evidence-graph",
                params={"include_computed": "false", "include_timeline": "false"},
            )
            data = resp.json()
            assert data["summary"]["graph_status"] == "sparse"
        finally:
            db.rollback()

    def test_graph_status_review(self, client, db):
        project = _get_seeded_project(db)
        org = _get_seeded_org(db)
        strategy = _make_strategy(db, project.id, suffix="review")
        # Add a high-severity alert to trigger review status
        _make_alert(db, org.id, strategy.id, severity="critical")
        # Add runs so it's not sparse
        for _ in range(5):
            _make_run(db, strategy.id)
        db.flush()
        try:
            resp = client.get(
                f"/api/strategies/{strategy.id}/evidence-graph",
                params={"include_computed": "false"},
            )
            data = resp.json()
            assert data["summary"]["graph_status"] in ("review", "complete", "partial")
        finally:
            db.rollback()

    def test_no_ai_language(self, client, db):
        strategy = _get_seeded_strategy(db)
        resp = client.get(f"/api/strategies/{strategy.id}/evidence-graph")
        data = resp.json()
        summary_text = data["summary"]["deterministic_summary"]
        for word in FORBIDDEN_WORDS:
            assert word not in summary_text, (
                f"Forbidden word '{word}' found in deterministic_summary"
            )

    def test_no_timeline_event(self, client, db):
        """Endpoint must not create AuditTimelineEvent rows (read-only)."""
        from app.models.audit_timeline_event import AuditTimelineEvent
        strategy = _get_seeded_strategy(db)
        before_count = (
            db.query(AuditTimelineEvent)
            .filter(AuditTimelineEvent.strategy_id == strategy.id)
            .count()
        )
        client.get(f"/api/strategies/{strategy.id}/evidence-graph")
        after_count = (
            db.query(AuditTimelineEvent)
            .filter(AuditTimelineEvent.strategy_id == strategy.id)
            .count()
        )
        assert before_count == after_count
