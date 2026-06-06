"""M104 tests: Lifecycle pipeline stage summary (read-only).

Covers:
  - TestLifecycleStageSummary: get_lifecycle_stage_summary aggregation shape
  - TestStrategyLifecyclePipeline: get_strategy_lifecycle_pipeline per-strategy reshape
  - TestPipelineSummaryEndpoint: GET /api/strategies/lifecycle/pipeline-summary

The engine is deterministic and READ-ONLY. Uses the shared session-scoped
fixtures (client/db) from conftest.py.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

# Registered endpoint path. The strategies router has no internal prefix, so the
# "/lifecycle/pipeline-summary" route resolves under the "/api" include prefix
# (NOT under "/api/strategies").
PIPELINE_SUMMARY_PATH = "/api/lifecycle/pipeline-summary"

_DISPLAY_KEYS = {
    "research",
    "backtest_review",
    "paper_candidate",
    "shadow",
    "production_candidate",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_seeded_project(db):
    from app.models.project import Project

    return db.query(Project).first()


def _make_strategy(db, project_id, *, suffix: str = "") -> object:
    from app.models.strategy import Strategy

    slug = f"m104-{suffix}-{uuid.uuid4().hex[:8]}"
    strat = Strategy(
        project_id=project_id,
        name=f"M104 Test Strategy {suffix}",
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
        completed_at=datetime.now(timezone.utc),
    )
    db.add(run)
    db.flush()
    return run


def _cleanup(db, *objs):
    for obj in reversed(objs):
        try:
            db.delete(obj)
        except Exception:
            pass
    db.flush()


# ---------------------------------------------------------------------------
# TestLifecycleStageSummary
# ---------------------------------------------------------------------------


class TestLifecycleStageSummary:
    """Aggregation shape checks for get_lifecycle_stage_summary."""

    def test_summary_has_five_stages(self, db):
        from app.services.lifecycle_pipeline import get_lifecycle_stage_summary

        summary = get_lifecycle_stage_summary(db)
        stages = summary["stages"]
        assert len(stages) == 5, f"Expected exactly 5 stages, got {len(stages)}"
        keys = {s["key"] for s in stages}
        assert keys == _DISPLAY_KEYS, (
            f"Expected stage keys {_DISPLAY_KEYS}, got {keys}"
        )

    def test_summary_counts_are_ints(self, db):
        from app.services.lifecycle_pipeline import get_lifecycle_stage_summary

        summary = get_lifecycle_stage_summary(db)
        for stage in summary["stages"]:
            assert isinstance(stage["count"], int), (
                f"{stage['key']} count must be int, got {type(stage['count'])}"
            )
            assert stage["count"] >= 0, f"{stage['key']} count must be >= 0"
            assert isinstance(stage["blocked_count"], int), (
                f"{stage['key']} blocked_count must be int, got "
                f"{type(stage['blocked_count'])}"
            )
            assert stage["blocked_count"] >= 0, (
                f"{stage['key']} blocked_count must be >= 0"
            )

    def test_total_matches_sum(self, db):
        from app.services.lifecycle_pipeline import get_lifecycle_stage_summary

        summary = get_lifecycle_stage_summary(db)
        stage_sum = sum(s["count"] for s in summary["stages"])
        assert summary["total_strategies"] == stage_sum, (
            f"total_strategies {summary['total_strategies']} != "
            f"sum of stage counts {stage_sum}"
        )

    def test_empty_org_zero_counts(self, db):
        """A project_id with no strategies -> all-zero counts, no crash."""
        from app.services.lifecycle_pipeline import get_lifecycle_stage_summary

        empty_project_id = uuid.uuid4()
        summary = get_lifecycle_stage_summary(db, project_id=empty_project_id)
        assert summary["total_strategies"] == 0
        assert summary["blocked_total"] == 0
        for stage in summary["stages"]:
            assert stage["count"] == 0, (
                f"Expected 0 count for empty project, got {stage}"
            )
            assert stage["blocked_count"] == 0

    def test_backtest_collapses_to_backtest_review(self, db):
        """A strategy inferred at the 'backtest' stage counts under 'backtest_review'."""
        from app.services.lifecycle_pipeline import get_lifecycle_stage_summary
        from app.services.strategy_lifecycle import compute_strategy_lifecycle

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="collapse")
        run = _make_run(db, strat.id, run_type="backtest")
        try:
            lifecycle = compute_strategy_lifecycle(strat.id, db)
            # Only meaningful if the raw inferred stage is "backtest".
            if lifecycle.get("current_stage") != "backtest":
                import pytest

                pytest.skip(
                    "Seeded inference did not place strategy at raw 'backtest' stage; "
                    f"got {lifecycle.get('current_stage')!r}"
                )

            before = get_lifecycle_stage_summary(db, project_id=project.id)
            review_before = next(
                s["count"] for s in before["stages"] if s["key"] == "backtest_review"
            )
            # Our strategy is already in `before`; assert it is reflected in review.
            assert review_before >= 1, (
                "Strategy at raw 'backtest' must count under display "
                f"'backtest_review'; stages={before['stages']}"
            )
        finally:
            _cleanup(db, run, strat)

    def test_has_disclaimer(self, db):
        from app.services.lifecycle_pipeline import get_lifecycle_stage_summary

        summary = get_lifecycle_stage_summary(db)
        assert "not trading advice" in summary["disclaimer"].lower(), (
            f"Expected 'not trading advice' in disclaimer, got: "
            f"{summary['disclaimer']!r}"
        )


# ---------------------------------------------------------------------------
# TestStrategyLifecyclePipeline
# ---------------------------------------------------------------------------


class TestStrategyLifecyclePipeline:
    """Per-strategy reshape into 5 display stages."""

    def test_pipeline_five_stages(self, db):
        from app.services.lifecycle_pipeline import get_strategy_lifecycle_pipeline

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="pipe5")
        run = _make_run(db, strat.id, run_type="backtest")
        try:
            data = get_strategy_lifecycle_pipeline(strat.id, db)
            stages = data["stages"]
            assert len(stages) == 5, f"Expected 5 stages, got {len(stages)}"
            allowed = {"complete", "current", "next", "blocked", "locked"}
            for stage in stages:
                assert stage["status"] in allowed, (
                    f"Stage {stage['key']} has invalid status {stage['status']!r}"
                )
        finally:
            _cleanup(db, run, strat)

    def test_current_stage_present(self, db):
        from app.services.lifecycle_pipeline import get_strategy_lifecycle_pipeline

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="curstage")
        run = _make_run(db, strat.id, run_type="backtest")
        try:
            data = get_strategy_lifecycle_pipeline(strat.id, db)
            assert isinstance(data["current_stage"], str) and data["current_stage"], (
                f"Expected non-empty current_stage, got {data['current_stage']!r}"
            )
        finally:
            _cleanup(db, run, strat)


# ---------------------------------------------------------------------------
# TestPipelineSummaryEndpoint
# ---------------------------------------------------------------------------


class TestPipelineSummaryEndpoint:
    """Integration tests via TestClient for the M104 pipeline-summary endpoint."""

    def test_endpoint_200(self, client):
        resp = client.get(PIPELINE_SUMMARY_PATH)
        assert resp.status_code == 200, (
            f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        )
        data = resp.json()
        for field in ("stages", "total_strategies", "disclaimer"):
            assert field in data, f"Missing field: {field}"

    def test_endpoint_stages_count_5(self, client):
        resp = client.get(PIPELINE_SUMMARY_PATH)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["stages"]) == 5, (
            f"Expected 5 stages in response, got {len(data['stages'])}"
        )
