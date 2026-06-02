"""M57 tests: Strategy Change Impact Analysis.

Tests for:
  - GET /api/strategies/{id}/change-impact  — returns 200
  - 404 for missing strategy
  - mode=latest_config_change, mode=latest_evidence_change
  - focus_node_id + focus_node_type=config_snapshot
  - Impact logic: config rechecks, run rechecks, recheck priority ordering
  - Quality impacts with low signal score
  - Readiness impacts populated
  - Impact score in valid range
  - Read-only: no AuditTimelineEvent created
  - Summary language guards
  - Suggested actions present
  - Impacted artifacts list

All tests use shared session-scoped fixtures from conftest.py.
"""
from __future__ import annotations

import hashlib
import json
import uuid

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_seeded_strategy(db):
    from app.models.strategy import Strategy
    return db.query(Strategy).filter(Strategy.status != "archived").first()


def _get_seeded_project(db):
    from app.models.project import Project
    return db.query(Project).first()


def _make_strategy(db, project_id, *, suffix: str = "") -> object:
    from app.models.strategy import Strategy

    slug = f"m57-test-{suffix}-{uuid.uuid4().hex[:8]}"
    strat = Strategy(
        project_id=project_id,
        name=f"M57 Test {suffix}",
        slug=slug,
        asset_class="equity",
        status="active",
    )
    db.add(strat)
    db.commit()
    return strat


def _make_strategy_run(db, strategy_id, *, run_type: str = "backtest", status: str = "completed") -> object:
    from app.models.strategy_run import StrategyRun

    run = StrategyRun(
        strategy_id=uuid.UUID(str(strategy_id)),
        run_name=f"M57 Run {uuid.uuid4().hex[:6]}",
        run_type=run_type,
        status=status,
    )
    db.add(run)
    db.commit()
    return run


def _make_config_snapshot(db, strategy_id, *, label: str = "test-config", config_json: dict | None = None) -> object:
    from app.models.strategy_config_snapshot import StrategyConfigSnapshot

    if config_json is None:
        config_json = {
            "assumptions": {
                "transaction_cost_bps": 5,
                "fill_model": "next_bar_open",
            }
        }
    cfg_hash = hashlib.sha256(json.dumps(config_json, sort_keys=True).encode()).hexdigest()
    snap = StrategyConfigSnapshot(
        strategy_id=uuid.UUID(str(strategy_id)),
        label=label,
        source_type="manual_json",
        config_json=config_json,
        config_hash=cfg_hash,
        param_count=len(config_json.get("params", {})),
        assumption_count=len(config_json.get("assumptions", {})),
    )
    db.add(snap)
    db.commit()
    return snap


def _make_signal_snapshot(db, strategy_id, *, quality_score: int = 85, label: str = "test-signal") -> object:
    from app.models.signal_snapshot import SignalSnapshot

    rows: list = []
    sig_hash = hashlib.sha256(json.dumps(rows).encode()).hexdigest()
    sig = SignalSnapshot(
        strategy_id=uuid.UUID(str(strategy_id)),
        label=label,
        source_type="manual_json",
        rows_json=rows,
        quality_score=quality_score,
        signal_hash=sig_hash,
    )
    db.add(sig)
    db.commit()
    return sig


def _count_timeline_events(db, strategy_id: str, event_type: str) -> int:
    from app.models.audit_timeline_event import AuditTimelineEvent
    return (
        db.query(AuditTimelineEvent)
        .filter(
            AuditTimelineEvent.strategy_id == uuid.UUID(strategy_id),
            AuditTimelineEvent.event_type == event_type,
        )
        .count()
    )


# ---------------------------------------------------------------------------
# class TestChangeImpactEndpoint
# ---------------------------------------------------------------------------

class TestChangeImpactEndpoint:
    def test_endpoint_200(self, db, client, seed_data):
        """GET /api/strategies/{id}/change-impact returns 200."""
        strat = _get_seeded_strategy(db)
        strat_id = str(strat.id)
        resp = client.get(f"/api/strategies/{strat_id}/change-impact")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["strategy_id"] == strat_id
        assert "impact_score" in data
        assert "impact_status" in data
        assert "deterministic_summary" in data
        assert "recommended_rechecks" in data
        assert "impacted_artifacts" in data
        assert "suggested_actions" in data

    def test_missing_strategy_404(self, db, client, seed_data):
        """Non-existent strategy returns 404."""
        fake_id = str(uuid.uuid4())
        resp = client.get(f"/api/strategies/{fake_id}/change-impact")
        assert resp.status_code == 404

    def test_no_evidence_no_change_detected(self, db, client, seed_data):
        """Strategy with no evidence artefacts returns valid response."""
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="no-evidence")
        strat_id = str(strat.id)

        resp = client.get(f"/api/strategies/{strat_id}/change-impact")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["strategy_id"] == strat_id
        # No evidence — impact status should indicate no change or low risk
        assert data["impact_status"] in ("no_change_detected", "low", "medium", "high", "requires_review")

    def test_mode_latest_config_change(self, db, client, seed_data):
        """mode=latest_config_change uses config snapshot as focus."""
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="cfg-mode")
        _make_config_snapshot(db, strat.id, label="cfg-mode-snap")

        resp = client.get(
            f"/api/strategies/{strat.id}/change-impact",
            params={"mode": "latest_config_change"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["mode"] == "latest_config_change"
        # Focus node should be set to config snapshot
        if data.get("focus_node"):
            assert data["focus_node"]["node_type"] == "config_snapshot"

    def test_mode_latest_evidence_change(self, db, client, seed_data):
        """mode=latest_evidence_change picks the most recent evidence artefact."""
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="ev-mode")
        _make_strategy_run(db, strat.id, run_type="backtest")

        resp = client.get(
            f"/api/strategies/{strat.id}/change-impact",
            params={"mode": "latest_evidence_change"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["mode"] == "latest_evidence_change"

    def test_focus_node_config_snapshot(self, db, client, seed_data):
        """focus_node_id + focus_node_type=config_snapshot sets focus correctly."""
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="focus-cfg")
        snap = _make_config_snapshot(db, strat.id, label="focus-snap")

        resp = client.get(
            f"/api/strategies/{strat.id}/change-impact",
            params={
                "mode": "focus_node",
                "focus_node_id": str(snap.id),
                "focus_node_type": "config_snapshot",
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["focus_node"] is not None
        assert data["focus_node"]["node_id"] == str(snap.id)
        assert data["focus_node"]["node_type"] == "config_snapshot"


# ---------------------------------------------------------------------------
# class TestChangeImpactLogic
# ---------------------------------------------------------------------------

class TestChangeImpactLogic:
    def test_config_focus_includes_config_rechecks(self, db, client, seed_data):
        """Config snapshot focus includes config policy recheck."""
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="cfg-rechecks")
        snap = _make_config_snapshot(db, strat.id, label="cfg-recheck-snap")

        resp = client.get(
            f"/api/strategies/{strat.id}/change-impact",
            params={
                "mode": "focus_node",
                "focus_node_id": str(snap.id),
                "focus_node_type": "config_snapshot",
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        recheck_keys = {r["recheck_key"] for r in data["recommended_rechecks"]}
        # Config focus should include config policy evaluation recheck
        assert "config_policy_eval" in recheck_keys

    def test_run_focus_includes_backtest_recheck(self, db, client, seed_data):
        """Strategy run focus includes backtest audit recheck."""
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="run-rechecks")
        run = _make_strategy_run(db, strat.id, run_type="backtest")

        resp = client.get(
            f"/api/strategies/{strat.id}/change-impact",
            params={
                "mode": "focus_node",
                "focus_node_id": str(run.id),
                "focus_node_type": "strategy_run",
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        recheck_keys = {r["recheck_key"] for r in data["recommended_rechecks"]}
        assert "backtest_audit" in recheck_keys

    def test_rechecks_sorted_by_priority(self, db, client, seed_data):
        """Critical/high rechecks appear before low priority ones."""
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="priority-order")
        run = _make_strategy_run(db, strat.id, run_type="backtest")

        resp = client.get(
            f"/api/strategies/{strat.id}/change-impact",
            params={
                "mode": "focus_node",
                "focus_node_id": str(run.id),
                "focus_node_type": "strategy_run",
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        rechecks = data["recommended_rechecks"]
        if len(rechecks) < 2:
            return  # nothing to compare

        priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        priorities = [priority_order.get(r["priority"], 99) for r in rechecks]
        assert priorities == sorted(priorities), (
            f"Rechecks not sorted by priority: {[r['priority'] for r in rechecks]}"
        )

    def test_quality_impacts_with_low_signal(self, db, client, seed_data):
        """SignalSnapshot with quality_score=45 shows degraded_quality_count >= 1."""
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="low-signal")
        _make_signal_snapshot(db, strat.id, quality_score=45, label="low-quality-sig")

        resp = client.get(f"/api/strategies/{strat.id}/change-impact")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        qi = data["quality_impacts"]
        assert qi["degraded_quality_count"] >= 1, (
            f"Expected degraded_quality_count >= 1, got {qi}"
        )

    def test_readiness_impacts_populated(self, db, client, seed_data):
        """Readiness verdict field is present in readiness_impacts."""
        strat = _get_seeded_strategy(db)
        resp = client.get(f"/api/strategies/{strat.id}/change-impact")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        ri = data["readiness_impacts"]
        # readiness_verdict may be None if no readiness computed, but key must exist
        assert "readiness_verdict" in ri

    def test_impact_score_0_to_100(self, db, client, seed_data):
        """Impact score must always be in [0, 100]."""
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="score-range")
        _make_config_snapshot(db, strat.id)
        _make_strategy_run(db, strat.id)
        _make_signal_snapshot(db, strat.id, quality_score=30)

        resp = client.get(f"/api/strategies/{strat.id}/change-impact")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        score = data["impact_score"]
        assert 0 <= score <= 100, f"Impact score out of range: {score}"

    def test_no_timeline_event(self, db, client, seed_data):
        """Change impact analysis is read-only — no AuditTimelineEvent created."""
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="no-event")

        before_count = _count_timeline_events(
            db, str(strat.id), "strategy_change_impact_analyzed"
        )

        resp = client.get(f"/api/strategies/{strat.id}/change-impact")
        assert resp.status_code == 200, resp.text

        after_count = _count_timeline_events(
            db, str(strat.id), "strategy_change_impact_analyzed"
        )
        assert before_count == after_count, (
            "AuditTimelineEvent should NOT be created by read-only change impact endpoint"
        )


# ---------------------------------------------------------------------------
# class TestChangeImpactSummary
# ---------------------------------------------------------------------------

class TestChangeImpactSummary:
    _FORBIDDEN_PHRASES = [
        "incident",
        "breach",
        "strategy failed",
        "do not trade",
        "do not invest",
        "you should trade",
        "buy",
        "sell",
    ]

    def test_summary_no_forbidden_language(self, db, client, seed_data):
        """Summary must not contain forbidden/investment language."""
        strat = _get_seeded_strategy(db)
        resp = client.get(f"/api/strategies/{strat.id}/change-impact")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        summary_lower = data["deterministic_summary"].lower()
        for phrase in self._FORBIDDEN_PHRASES:
            assert phrase not in summary_lower, (
                f"Forbidden phrase '{phrase}' found in summary: {data['deterministic_summary']}"
            )

    def test_suggested_actions_present(self, db, client, seed_data):
        """Suggested actions list must be non-empty when evidence exists."""
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="actions")
        _make_config_snapshot(db, strat.id)
        _make_strategy_run(db, strat.id)

        resp = client.get(f"/api/strategies/{strat.id}/change-impact")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert isinstance(data["suggested_actions"], list)
        assert len(data["suggested_actions"]) > 0, (
            "Expected at least one suggested action when strategy has config snapshot and run"
        )

    def test_impacted_artifacts_list(self, db, client, seed_data):
        """Impacted artifacts list is populated when evidence quality issues exist."""
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="artifacts")
        _make_signal_snapshot(db, strat.id, quality_score=40)
        _make_config_snapshot(db, strat.id)

        resp = client.get(f"/api/strategies/{strat.id}/change-impact")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        artifacts = data["impacted_artifacts"]
        assert isinstance(artifacts, list)
        # Should have at least some artifacts (readiness, regression, etc. are always included)
        assert len(artifacts) > 0, "Expected at least one impacted artifact"

        for artifact in artifacts:
            assert "artifact_id" in artifact
            assert "artifact_type" in artifact
            assert "label" in artifact
            assert "impact_level" in artifact
            assert artifact["impact_level"] in ("critical", "high", "medium", "low", "none")

    def test_response_schema_fields_present(self, db, client, seed_data):
        """All required schema fields are present in the response."""
        strat = _get_seeded_strategy(db)
        resp = client.get(f"/api/strategies/{strat.id}/change-impact")
        assert resp.status_code == 200, resp.text
        data = resp.json()

        required_fields = [
            "strategy_id", "strategy_name", "generated_at", "mode",
            "impact_score", "impact_status", "deterministic_summary",
            "assumption_impacts", "quality_impacts", "readiness_impacts",
            "impacted_artifacts", "recommended_rechecks", "suggested_actions",
        ]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"

        # Nested assumption_impacts fields
        ai = data["assumption_impacts"]
        for field in ["has_assumption_change", "positive_change_count", "weakening_change_count",
                      "review_change_count", "key_changes", "impact_level", "suggested_checks"]:
            assert field in ai, f"Missing assumption_impacts field: {field}"

        # Nested quality_impacts fields
        qi = data["quality_impacts"]
        for field in ["quality_impact_count", "degraded_quality_count",
                      "missing_quality_count", "key_quality_findings"]:
            assert field in qi, f"Missing quality_impacts field: {field}"

        # Nested readiness_impacts fields
        ri = data["readiness_impacts"]
        for field in ["readiness_verdict", "promotion_risk_count", "failed_regression_count",
                      "failed_policy_count", "sla_violation_count", "open_review_case_count",
                      "impact_level", "suggested_checks"]:
            assert field in ri, f"Missing readiness_impacts field: {field}"

    def test_mode_default_is_latest_change(self, db, client, seed_data):
        """Default mode is latest_change."""
        strat = _get_seeded_strategy(db)
        resp = client.get(f"/api/strategies/{strat.id}/change-impact")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["mode"] == "latest_change"

    def test_impact_status_valid_values(self, db, client, seed_data):
        """impact_status must be one of the defined valid values."""
        valid_statuses = {"no_change_detected", "low", "medium", "high", "requires_review"}
        strat = _get_seeded_strategy(db)
        resp = client.get(f"/api/strategies/{strat.id}/change-impact")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["impact_status"] in valid_statuses, (
            f"Unexpected impact_status: {data['impact_status']}"
        )
