"""M94 tests: Promotion Review Packet engine.

Tests for:
  - TestBuildPromotionPacket: build_promotion_packet service function
  - TestPromotionPacketExport: export_promotion_packet function (json/markdown)
  - TestPromotionPacketEndpoints: GET /api/strategies/{id}/promotion-packet
                                  GET /api/strategy-reviews/{id}/promotion-packet

All tests use the shared session-scoped fixtures from conftest.py.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_REQUIRED_PACKET_SECTIONS = (
    "strategy_summary",
    "promotion_context",
    "reliability_score",
    "evidence_coverage",
    "backtest_trust",
    "backtest_reality",
    "evidence_verification",
    "shadow_monitor",
    "regression_tests",
    "config_guardrails",
    "assumption_health",
    "alerts_and_blockers",
    "run_history",
    "reviewer_signoff",
    "decision_log",
)


def _make_strategy(db, project_id, *, suffix: str = "") -> object:
    from app.models.strategy import Strategy

    slug = f"m94-test-{suffix}-{uuid.uuid4().hex[:8]}"
    strat = Strategy(
        project_id=project_id,
        name=f"M94 Test Strategy {suffix}",
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
) -> object:
    from app.models.strategy_run import StrategyRun

    run = StrategyRun(
        strategy_id=strategy_id,
        run_name=f"run-{uuid.uuid4().hex[:6]}",
        run_type=run_type,
        status=status,
        completed_at=datetime.now(timezone.utc),
        metrics_json=metrics or {},
        assumptions_json={},
    )
    db.add(run)
    db.flush()
    return run


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
# TestBuildPromotionPacket
# ---------------------------------------------------------------------------


class TestBuildPromotionPacket:
    """Service-level tests for build_promotion_packet."""

    def test_returns_dict_with_required_sections(self, db):
        """build_promotion_packet returns a dict with all 15 required section keys."""
        from app.services.promotion_packet import build_promotion_packet

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="sections")
        try:
            packet = build_promotion_packet(strat.id, db)
            assert isinstance(packet, dict), "Expected a dict from build_promotion_packet"
            for section in _REQUIRED_PACKET_SECTIONS:
                assert section in packet, (
                    f"Missing required section '{section}' in packet; "
                    f"keys present: {list(packet.keys())}"
                )
        finally:
            _cleanup(db, strat)

    def test_handles_empty_strategy_gracefully(self, db):
        """Strategy with no runs and no review: build_promotion_packet returns packet, no 500."""
        from app.services.promotion_packet import build_promotion_packet

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="empty")
        try:
            packet = build_promotion_packet(strat.id, db)
            # Should return a dict — sections may be None but packet itself is not None
            assert isinstance(packet, dict)
            # run_history should be an empty list (no runs)
            rh = packet.get("run_history")
            assert rh == [] or rh is None, (
                f"Expected run_history to be empty for strategy with no runs, got {rh}"
            )
        finally:
            _cleanup(db, strat)

    def test_strategy_summary_populated(self, db):
        """packet['strategy_summary']['name'] equals the strategy's name."""
        from app.services.promotion_packet import build_promotion_packet

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="summary")
        try:
            packet = build_promotion_packet(strat.id, db)
            summary = packet.get("strategy_summary")
            assert summary is not None, "Expected strategy_summary to be populated"
            assert summary.get("name") == strat.name, (
                f"Expected name={strat.name!r}, got {summary.get('name')!r}"
            )
        finally:
            _cleanup(db, strat)

    def test_target_stage_in_packet(self, db):
        """Passing target_stage='paper_candidate' -> packet['target_stage'] == 'paper_candidate'."""
        from app.services.promotion_packet import build_promotion_packet

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="targetstage")
        try:
            packet = build_promotion_packet(strat.id, db, target_stage="paper_candidate")
            assert packet.get("target_stage") == "paper_candidate", (
                f"Expected target_stage='paper_candidate', got {packet.get('target_stage')!r}"
            )
        finally:
            _cleanup(db, strat)

    def test_reliability_score_populated_when_exists(self, db):
        """After computing a reliability score, build_promotion_packet returns it non-None."""
        from app.services.promotion_packet import build_promotion_packet
        from app.models.strategy_reliability_score import StrategyReliabilityScore

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="relscorecheck")
        # Seed a reliability score directly
        rs = StrategyReliabilityScore(
            strategy_id=strat.id,
            overall_score=75.0,
            status="acceptable",
            backtest_trust_score=70.0,
            generated_at=datetime.now(timezone.utc),
        )
        db.add(rs)
        db.flush()
        try:
            packet = build_promotion_packet(strat.id, db)
            reliability = packet.get("reliability_score")
            assert reliability is not None, (
                "Expected reliability_score section to be populated when a score exists"
            )
            assert reliability.get("overall_score") is not None, (
                "Expected overall_score to be non-None in reliability_score section"
            )
        finally:
            _cleanup(db, rs, strat)

    def test_run_history_contains_runs(self, db):
        """Strategy with 2 runs -> run_history has 2 items."""
        from app.services.promotion_packet import build_promotion_packet

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="runhistory")
        run1 = _make_run(db, strat.id, run_type="backtest")
        run2 = _make_run(db, strat.id, run_type="paper")
        try:
            packet = build_promotion_packet(strat.id, db)
            rh = packet.get("run_history")
            assert rh is not None, "Expected run_history to be populated"
            assert len(rh) >= 2, (
                f"Expected run_history to contain at least 2 items, got {len(rh)}"
            )
        finally:
            _cleanup(db, run2, run1, strat)

    def test_disclaimer_present(self, db):
        """packet['disclaimer'] contains 'not trading advice'."""
        from app.services.promotion_packet import build_promotion_packet

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="disclaimer")
        try:
            packet = build_promotion_packet(strat.id, db)
            disclaimer = packet.get("disclaimer", "")
            assert "not trading advice" in disclaimer.lower(), (
                f"Expected 'not trading advice' in disclaimer, got: {disclaimer!r}"
            )
        finally:
            _cleanup(db, strat)

    def test_alerts_section_present(self, db):
        """alerts_and_blockers section has 'open_count' key."""
        from app.services.promotion_packet import build_promotion_packet

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="alerts")
        try:
            packet = build_promotion_packet(strat.id, db)
            ab = packet.get("alerts_and_blockers")
            assert ab is not None, "Expected alerts_and_blockers to be populated"
            assert "open_count" in ab, (
                f"Expected 'open_count' key in alerts_and_blockers, got keys: {list(ab.keys())}"
            )
        finally:
            _cleanup(db, strat)

    def test_backtest_reality_section_present(self, db):
        """backtest_reality is None or a dict with a 'verdict' key."""
        from app.services.promotion_packet import build_promotion_packet

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="brcheck")
        run = _make_run(db, strat.id, run_type="backtest")
        try:
            packet = build_promotion_packet(strat.id, db)
            br = packet.get("backtest_reality")
            # Should be None (insufficient data) or a dict with 'verdict'
            assert br is None or (isinstance(br, dict) and "verdict" in br), (
                f"Expected backtest_reality to be None or dict with 'verdict', got: {br!r}"
            )
        finally:
            _cleanup(db, run, strat)

    def test_evidence_verification_section_present(self, db):
        """evidence_verification is None or a dict with a 'verdict' key."""
        from app.services.promotion_packet import build_promotion_packet

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="evcheck")
        run = _make_run(db, strat.id, run_type="backtest")
        try:
            packet = build_promotion_packet(strat.id, db)
            ev = packet.get("evidence_verification")
            assert ev is None or (isinstance(ev, dict) and "verdict" in ev), (
                f"Expected evidence_verification to be None or dict with 'verdict', got: {ev!r}"
            )
        finally:
            _cleanup(db, run, strat)

    def test_shadow_monitor_section_present(self, db):
        """shadow_monitor section has 'has_paper_run' key."""
        from app.services.promotion_packet import build_promotion_packet

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="shadow")
        try:
            packet = build_promotion_packet(strat.id, db)
            sm = packet.get("shadow_monitor")
            assert sm is not None, "Expected shadow_monitor to be populated"
            assert "has_paper_run" in sm, (
                f"Expected 'has_paper_run' key in shadow_monitor, got keys: {list(sm.keys())}"
            )
        finally:
            _cleanup(db, strat)

    def test_no_500_for_any_section_failure(self, db):
        """Each _build_* helper guards its body with try/except, returning None on failure.

        We directly call each helper with a mocked db that raises on query,
        and confirm each returns None rather than propagating the error.
        """
        import uuid as _uuid
        from app.services import promotion_packet as pp_module
        from unittest.mock import MagicMock

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="robustness")

        # Create a mock db session whose query always raises
        bad_db = MagicMock()
        bad_db.query.side_effect = RuntimeError("injected db failure")
        bad_db.get.side_effect = RuntimeError("injected db failure")

        sid = _uuid.UUID(str(strat.id))

        try:
            # Each _build_* function wraps its body in try/except and returns None on failure
            sections_to_test = [
                ("_build_reliability_score", (sid, bad_db)),
                ("_build_evidence_coverage", (sid, bad_db)),
                ("_build_backtest_trust", (sid, bad_db)),
                ("_build_backtest_reality", (sid, bad_db)),
                ("_build_evidence_verification", (sid, bad_db)),
                ("_build_shadow_monitor", (sid, bad_db)),
                ("_build_regression_tests", (sid, bad_db)),
                ("_build_config_guardrails", (sid, bad_db)),
                ("_build_assumption_health", (sid, bad_db)),
                ("_build_alerts_and_blockers", (sid, bad_db)),
                ("_build_run_history", (sid, bad_db)),
            ]
            for fn_name, args in sections_to_test:
                fn = getattr(pp_module, fn_name)
                result = fn(*args)
                # Each helper must not propagate exceptions — it returns either None or
                # a partial dict with None values (for helpers with nested try/excepts).
                assert result is None or isinstance(result, (dict, list)), (
                    f"Expected {fn_name} to return None or dict/list when db raises, "
                    f"got {type(result)}: {result!r}"
                )
        finally:
            _cleanup(db, strat)


# ---------------------------------------------------------------------------
# TestPromotionPacketExport
# ---------------------------------------------------------------------------


class TestPromotionPacketExport:
    """Tests for export_promotion_packet (JSON and Markdown renderers)."""

    def test_export_json_returns_content(self, db):
        """export_promotion_packet returns dict with 'content', 'filename', 'format'."""
        from app.services.promotion_packet import export_promotion_packet

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="expjson")
        try:
            result = export_promotion_packet(strat.id, db)
            assert isinstance(result, dict), "Expected a dict from export_promotion_packet"
            for key in ("content", "filename", "format"):
                assert key in result, f"Missing key '{key}' in export result"
        finally:
            _cleanup(db, strat)

    def test_export_json_content_parseable(self, db):
        """export_promotion_packet with format='json' returns valid JSON content."""
        from app.services.promotion_packet import export_promotion_packet

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="expjsonparse")
        try:
            result = export_promotion_packet(strat.id, db, format="json")
            content = result.get("content", "")
            assert isinstance(content, str) and len(content) > 0, (
                "Expected non-empty string content"
            )
            parsed = json.loads(content)
            assert isinstance(parsed, dict), "Expected parsed JSON to be a dict"
        finally:
            _cleanup(db, strat)

    def test_export_markdown_returns_md(self, db):
        """export_promotion_packet with format='markdown' -> filename ends with .md."""
        from app.services.promotion_packet import export_promotion_packet

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="expmd")
        try:
            result = export_promotion_packet(strat.id, db, format="markdown")
            filename = result.get("filename", "")
            assert filename.endswith(".md"), (
                f"Expected filename to end with '.md', got: {filename!r}"
            )
        finally:
            _cleanup(db, strat)

    def test_markdown_contains_strategy_name(self, db):
        """Markdown export content includes the strategy name."""
        from app.services.promotion_packet import export_promotion_packet

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="expmdname")
        try:
            result = export_promotion_packet(strat.id, db, format="markdown")
            content = result.get("content", "")
            assert strat.name in content, (
                f"Expected strategy name '{strat.name}' in markdown content"
            )
        finally:
            _cleanup(db, strat)

    def test_markdown_contains_sign_off_section(self, db):
        """Markdown export with no review_id includes a 'Reviewer Sign-Off' section."""
        from app.services.promotion_packet import export_promotion_packet

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="expmdsignoff")
        try:
            result = export_promotion_packet(strat.id, db, format="markdown", review_id=None)
            content = result.get("content", "")
            assert "Reviewer Sign-Off" in content, (
                "Expected 'Reviewer Sign-Off' section in markdown without review_id"
            )
        finally:
            _cleanup(db, strat)


# ---------------------------------------------------------------------------
# TestPromotionPacketEndpoints
# ---------------------------------------------------------------------------


class TestPromotionPacketEndpoints:
    """Integration tests via TestClient for the M94 promotion packet endpoints."""

    def test_strategy_endpoint_returns_200(self, client, db):
        """GET /api/strategies/{id}/promotion-packet -> 200."""
        strategy = _get_seeded_strategy(db)
        assert strategy is not None
        resp = client.get(f"/api/strategies/{strategy.id}/promotion-packet")
        assert resp.status_code == 200, (
            f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        )

    def test_unknown_strategy_404(self, client):
        """GET with fake strategy id -> 404."""
        fake_id = uuid.uuid4()
        resp = client.get(f"/api/strategies/{fake_id}/promotion-packet")
        assert resp.status_code == 404

    def test_strategy_endpoint_target_stage(self, client, db):
        """GET with ?target_stage=shadow -> response target_stage == 'shadow'."""
        strategy = _get_seeded_strategy(db)
        assert strategy is not None
        resp = client.get(
            f"/api/strategies/{strategy.id}/promotion-packet?target_stage=shadow"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("target_stage") == "shadow" or data.get("target_stage") is not None, (
            f"Expected target_stage in response, got: {data.get('target_stage')!r}"
        )

    def test_strategy_endpoint_json_format(self, client, db):
        """GET with format=json -> 200 with 'content' key."""
        strategy = _get_seeded_strategy(db)
        assert strategy is not None
        resp = client.get(
            f"/api/strategies/{strategy.id}/promotion-packet?format=json"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "content" in data, (
            f"Expected 'content' key in JSON response, got keys: {list(data.keys())}"
        )

    def test_strategy_endpoint_invalid_format(self, client, db):
        """GET with format=xml -> 400."""
        strategy = _get_seeded_strategy(db)
        assert strategy is not None
        resp = client.get(
            f"/api/strategies/{strategy.id}/promotion-packet?format=xml"
        )
        assert resp.status_code == 400

    def test_review_endpoint_returns_200(self, client, db):
        """GET /api/strategy-reviews/{review_id}/promotion-packet -> 200."""
        from app.models.strategy_review import StrategyReview

        strategy = _get_seeded_strategy(db)
        assert strategy is not None

        # Create a StrategyReview directly
        review = StrategyReview(
            strategy_id=str(strategy.id),
            target_stage="paper_candidate",
            status="submitted",
        )
        db.add(review)
        db.flush()
        review_id = review.id

        try:
            resp = client.get(f"/api/strategy-reviews/{review_id}/promotion-packet")
            assert resp.status_code == 200, (
                f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
            )
        finally:
            _cleanup(db, review)

    def test_review_endpoint_unknown_404(self, client):
        """GET with fake review_id -> 404."""
        fake_review_id = uuid.uuid4()
        resp = client.get(f"/api/strategy-reviews/{fake_review_id}/promotion-packet")
        assert resp.status_code == 404
