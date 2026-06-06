"""M95 tests: Strategy Lineage Diff engine.

Tests for:
  - TestListComparableVersions: list_comparable_versions service function
  - TestBuildVersionProfile: build_version_evidence_profile service function
  - TestCompareStrategyVersions: compare_strategy_versions service function
  - TestRenderLineageDiffReport: render_lineage_diff_report rendering
  - TestLineageDiffEndpoints: GET /api/strategies/{id}/lineage/versions,
                              GET /api/strategies/{id}/lineage/diff,
                              GET /api/strategies/{id}/lineage/diff/report

All tests use the shared session-scoped fixtures from conftest.py.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone

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


def _cleanup(db, *objs):
    for obj in reversed(objs):
        try:
            db.delete(obj)
        except Exception:
            pass
    db.flush()


def _make_strategy(db, project_id, *, suffix: str = "") -> object:
    from app.models.strategy import Strategy

    slug = f"m95-test-{suffix}-{uuid.uuid4().hex[:8]}"
    strat = Strategy(
        project_id=project_id,
        name=f"M95 Test Strategy {suffix}",
        slug=slug,
        asset_class="equity",
        status="active",
    )
    db.add(strat)
    db.flush()
    return strat


def _make_version(db, strategy_id, label: str) -> object:
    from app.models.strategy_version import StrategyVersion

    v = StrategyVersion(
        strategy_id=strategy_id,
        version_label=label,
        git_commit=f"abc{uuid.uuid4().hex[:6]}",
        branch_name="main",
    )
    db.add(v)
    db.flush()
    return v


def _make_run(
    db,
    strategy_id,
    version_id=None,
    run_type: str = "backtest",
    metrics: dict | None = None,
) -> object:
    from app.models.strategy_run import StrategyRun

    run = StrategyRun(
        strategy_id=strategy_id,
        strategy_version_id=version_id,
        run_name=f"run-{uuid.uuid4().hex[:6]}",
        run_type=run_type,
        status="completed",
        completed_at=datetime.now(timezone.utc),
        metrics_json=metrics or {},
        assumptions_json={},
    )
    db.add(run)
    db.flush()
    return run


def _make_config_snapshot(db, strategy_id, version_id, config_json: dict, label: str = "cfg") -> object:
    from app.models.strategy_config_snapshot import StrategyConfigSnapshot

    raw = json.dumps(config_json, sort_keys=True).encode()
    cfg_hash = hashlib.sha256(raw).hexdigest()
    cfg = StrategyConfigSnapshot(
        strategy_id=strategy_id,
        strategy_version_id=version_id,
        label=label,
        config_json=config_json,
        config_hash=cfg_hash,
    )
    db.add(cfg)
    db.flush()
    return cfg


# ---------------------------------------------------------------------------
# TestListComparableVersions
# ---------------------------------------------------------------------------


class TestListComparableVersions:
    """Service-level tests for list_comparable_versions."""

    def test_returns_empty_for_no_versions(self, db):
        """Strategy with no versions -> []."""
        from app.services.strategy_lineage_diff import list_comparable_versions

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="lcv-empty")
        try:
            result = list_comparable_versions(strat.id, db)
            assert result == [], f"Expected [], got {result}"
        finally:
            _cleanup(db, strat)

    def test_returns_versions_for_instrumented_strategy(self, db):
        """Strategy with seeded versions -> list has items."""
        from app.services.strategy_lineage_diff import list_comparable_versions

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="lcv-instrumented")
        v1 = _make_version(db, strat.id, "v1.0")
        v2 = _make_version(db, strat.id, "v2.0")
        try:
            result = list_comparable_versions(strat.id, db)
            assert len(result) >= 2, f"Expected at least 2 versions, got {len(result)}"
        finally:
            _cleanup(db, v2, v1, strat)

    def test_versions_have_required_fields(self, db):
        """Each version item has version_id, version_label, created_at."""
        from app.services.strategy_lineage_diff import list_comparable_versions

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="lcv-fields")
        v1 = _make_version(db, strat.id, "v1.0")
        try:
            result = list_comparable_versions(strat.id, db)
            assert len(result) >= 1
            for item in result:
                assert "version_id" in item, f"Missing version_id in {item}"
                assert "version_label" in item, f"Missing version_label in {item}"
                assert "created_at" in item, f"Missing created_at in {item}"
        finally:
            _cleanup(db, v1, strat)


# ---------------------------------------------------------------------------
# TestBuildVersionProfile
# ---------------------------------------------------------------------------


class TestBuildVersionProfile:
    """Service-level tests for build_version_evidence_profile."""

    def test_returns_profile_for_existing_version(self, db):
        """create version -> profile['found'] == True."""
        from app.services.strategy_lineage_diff import build_version_evidence_profile

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="bvp-found")
        v = _make_version(db, strat.id, "v1.0")
        try:
            profile = build_version_evidence_profile(strat.id, "v1.0", db)
            assert profile["found"] is True, f"Expected found=True, got {profile['found']}"
        finally:
            _cleanup(db, v, strat)

    def test_returns_not_found_for_missing_version(self, db):
        """Unknown label -> profile['found'] == False."""
        from app.services.strategy_lineage_diff import build_version_evidence_profile

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="bvp-notfound")
        try:
            profile = build_version_evidence_profile(strat.id, "v99.0", db)
            assert profile["found"] is False, f"Expected found=False, got {profile['found']}"
        finally:
            _cleanup(db, strat)

    def test_profile_has_version_metadata(self, db):
        """Profile has version_label and version_id when found."""
        from app.services.strategy_lineage_diff import build_version_evidence_profile

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="bvp-meta")
        v = _make_version(db, strat.id, "v2.5")
        try:
            profile = build_version_evidence_profile(strat.id, "v2.5", db)
            assert profile["found"] is True
            assert profile["version_label"] == "v2.5", (
                f"Expected version_label='v2.5', got {profile['version_label']!r}"
            )
            assert profile["version_id"] == str(v.id), (
                f"Expected version_id={str(v.id)!r}, got {profile['version_id']!r}"
            )
        finally:
            _cleanup(db, v, strat)

    def test_profile_has_run_data_when_run_exists(self, db):
        """Create run with metrics -> profile metrics_json is not None."""
        from app.services.strategy_lineage_diff import build_version_evidence_profile

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="bvp-rundata")
        v = _make_version(db, strat.id, "v3.0")
        run = _make_run(
            db, strat.id, version_id=v.id, run_type="backtest",
            metrics={"sharpe": 1.2, "annual_return": 0.15, "trade_count": 100},
        )
        try:
            profile = build_version_evidence_profile(strat.id, "v3.0", db)
            assert profile["found"] is True
            assert profile.get("metrics_json") is not None, (
                "Expected metrics_json to be non-None when a backtest run exists"
            )
        finally:
            _cleanup(db, run, v, strat)


# ---------------------------------------------------------------------------
# TestCompareStrategyVersions
# ---------------------------------------------------------------------------


class TestCompareStrategyVersions:
    """Service-level tests for compare_strategy_versions."""

    def test_insufficient_data_with_one_version(self, db):
        """Only one version with no run -> verdict=='insufficient_data'."""
        from app.services.strategy_lineage_diff import compare_strategy_versions

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="csv-onevs")
        v1 = _make_version(db, strat.id, "v1.0")
        # No run attached to v1
        try:
            result = compare_strategy_versions(strat.id, "v1.0", "v2.0", db)
            assert result["verdict"] == "insufficient_data", (
                f"Expected insufficient_data, got {result['verdict']}"
            )
        finally:
            _cleanup(db, v1, strat)

    def test_insufficient_data_with_missing_version(self, db):
        """Base version not found -> verdict=='insufficient_data'."""
        from app.services.strategy_lineage_diff import compare_strategy_versions

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="csv-missingvs")
        try:
            result = compare_strategy_versions(strat.id, "nonexistent-v1", "nonexistent-v2", db)
            assert result["verdict"] == "insufficient_data", (
                f"Expected insufficient_data, got {result['verdict']}"
            )
        finally:
            _cleanup(db, strat)

    def test_config_params_added_detected(self, db):
        """v1 has no params, v2 has params -> config section has 'changed' items."""
        from app.services.strategy_lineage_diff import compare_strategy_versions

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="csv-cfgadded")
        v1 = _make_version(db, strat.id, "v1.0")
        v2 = _make_version(db, strat.id, "v2.0")
        run1 = _make_run(
            db, strat.id, version_id=v1.id, run_type="backtest",
            metrics={"sharpe": 0.8, "trade_count": 50},
        )
        run2 = _make_run(
            db, strat.id, version_id=v2.id, run_type="backtest",
            metrics={"sharpe": 1.0, "trade_count": 60},
        )
        cfg1 = _make_config_snapshot(db, strat.id, v1.id, {"params": {}, "assumptions": {}}, "cfg-v1")
        cfg2 = _make_config_snapshot(
            db, strat.id, v2.id,
            {"params": {"lookback": 20, "threshold": 0.5}, "assumptions": {}},
            "cfg-v2",
        )
        try:
            result = compare_strategy_versions(strat.id, "v1.0", "v2.0", db)
            cfg_section = next(
                (s for s in result["sections"] if s["key"] == "config_diff"), None
            )
            assert cfg_section is not None, "Expected config_diff section"
            changed_items = [it for it in cfg_section["items"] if it["status"] in ("added", "removed", "changed")]
            assert len(changed_items) > 0, (
                f"Expected changed config items, got: {[it['status'] for it in cfg_section['items']]}"
            )
        finally:
            _cleanup(db, cfg2, cfg1, run2, run1, v2, v1, strat)

    def test_config_assumption_removed_detected(self, db):
        """v1 has cost_bps=5, v2 has no cost -> blocker_introduced present."""
        from app.services.strategy_lineage_diff import compare_strategy_versions

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="csv-costremoved")
        v1 = _make_version(db, strat.id, "v1.0")
        v2 = _make_version(db, strat.id, "v2.0")
        run1 = _make_run(
            db, strat.id, version_id=v1.id, run_type="backtest",
            metrics={"sharpe": 0.9, "trade_count": 50},
        )
        run2 = _make_run(
            db, strat.id, version_id=v2.id, run_type="backtest",
            metrics={"sharpe": 1.1, "trade_count": 55},
        )
        cfg1 = _make_config_snapshot(
            db, strat.id, v1.id,
            {"params": {}, "assumptions": {"transaction_cost_bps": 5}},
            "cfg-v1",
        )
        cfg2 = _make_config_snapshot(
            db, strat.id, v2.id,
            {"params": {}, "assumptions": {}},
            "cfg-v2",
        )
        try:
            result = compare_strategy_versions(strat.id, "v1.0", "v2.0", db)
            # The blocker_diff section should show config_cost_missing introduced
            blocker_section = next(
                (s for s in result["sections"] if s["key"] == "blocker_diff"), None
            )
            assert blocker_section is not None, "Expected blocker_diff section"
            cost_blocker = next(
                (it for it in blocker_section["items"] if it["key"] == "config_cost_missing"),
                None,
            )
            assert cost_blocker is not None, "Expected config_cost_missing blocker item"
            assert cost_blocker["status"] == "introduced", (
                f"Expected config_cost_missing to be 'introduced', got {cost_blocker['status']}"
            )
        finally:
            _cleanup(db, cfg2, cfg1, run2, run1, v2, v1, strat)

    def test_universe_symbols_added(self, db):
        """v1 has ['SPY'], v2 has ['SPY','QQQ'] -> universe section changed."""
        from app.services.strategy_lineage_diff import compare_strategy_versions
        from app.models.universe_snapshot import UniverseSnapshot

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="csv-uniadded")
        v1 = _make_version(db, strat.id, "v1.0")
        v2 = _make_version(db, strat.id, "v2.0")
        run1 = _make_run(
            db, strat.id, version_id=v1.id, run_type="backtest",
            metrics={"sharpe": 0.9, "trade_count": 50},
        )
        run2 = _make_run(
            db, strat.id, version_id=v2.id, run_type="backtest",
            metrics={"sharpe": 1.0, "trade_count": 55},
        )
        uni1 = UniverseSnapshot(
            strategy_id=strat.id,
            strategy_version_id=v1.id,
            label="uni-v1",
            universe_hash=hashlib.sha256(b"SPY").hexdigest(),
            symbol_count=1,
            symbols_json=["SPY"],
        )
        db.add(uni1)
        uni2 = UniverseSnapshot(
            strategy_id=strat.id,
            strategy_version_id=v2.id,
            label="uni-v2",
            universe_hash=hashlib.sha256(b"SPYQQQ").hexdigest(),
            symbol_count=2,
            symbols_json=["SPY", "QQQ"],
        )
        db.add(uni2)
        db.flush()
        try:
            result = compare_strategy_versions(strat.id, "v1.0", "v2.0", db)
            uni_section = next(
                (s for s in result["sections"] if s["key"] == "universe_diff"), None
            )
            assert uni_section is not None, "Expected universe_diff section"
            assert uni_section["status"] == "changed", (
                f"Expected universe_diff status='changed', got {uni_section['status']!r}"
            )
            added_item = next(
                (it for it in uni_section["items"] if it["key"] == "universe_added_symbols"), None
            )
            assert added_item is not None
            assert added_item["status"] == "changed", (
                f"Expected added_symbols status='changed', got {added_item['status']!r}"
            )
        finally:
            _cleanup(db, uni2, uni1, run2, run1, v2, v1, strat)

    def test_universe_symbols_removed(self, db):
        """v1 has ['SPY','QQQ'], v2 has ['SPY'] -> universe section changed with removed symbol."""
        from app.services.strategy_lineage_diff import compare_strategy_versions
        from app.models.universe_snapshot import UniverseSnapshot

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="csv-uniremoved")
        v1 = _make_version(db, strat.id, "v1.0")
        v2 = _make_version(db, strat.id, "v2.0")
        run1 = _make_run(
            db, strat.id, version_id=v1.id, run_type="backtest",
            metrics={"sharpe": 1.0, "trade_count": 60},
        )
        run2 = _make_run(
            db, strat.id, version_id=v2.id, run_type="backtest",
            metrics={"sharpe": 0.9, "trade_count": 55},
        )
        uni1 = UniverseSnapshot(
            strategy_id=strat.id,
            strategy_version_id=v1.id,
            label="uni-v1",
            universe_hash=hashlib.sha256(b"SPYQQQ").hexdigest(),
            symbol_count=2,
            symbols_json=["SPY", "QQQ"],
        )
        db.add(uni1)
        uni2 = UniverseSnapshot(
            strategy_id=strat.id,
            strategy_version_id=v2.id,
            label="uni-v2",
            universe_hash=hashlib.sha256(b"SPY").hexdigest(),
            symbol_count=1,
            symbols_json=["SPY"],
        )
        db.add(uni2)
        db.flush()
        try:
            result = compare_strategy_versions(strat.id, "v1.0", "v2.0", db)
            uni_section = next(
                (s for s in result["sections"] if s["key"] == "universe_diff"), None
            )
            assert uni_section is not None, "Expected universe_diff section"
            assert uni_section["status"] == "changed", (
                f"Expected universe_diff status='changed', got {uni_section['status']!r}"
            )
            removed_item = next(
                (it for it in uni_section["items"] if it["key"] == "universe_removed_symbols"), None
            )
            assert removed_item is not None
            assert removed_item["status"] == "changed", (
                f"Expected removed_symbols status='changed', got {removed_item['status']!r}"
            )
            assert "QQQ" in removed_item.get("base_value", []), (
                f"Expected QQQ in removed symbols base_value, got {removed_item.get('base_value')}"
            )
        finally:
            _cleanup(db, uni2, uni1, run2, run1, v2, v1, strat)

    def test_run_metrics_delta_sharpe(self, db):
        """v1 sharpe=0.82, v2 sharpe=1.14 -> metric delta detected as improved."""
        from app.services.strategy_lineage_diff import compare_strategy_versions

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="csv-sharpedelta")
        v1 = _make_version(db, strat.id, "v1.0")
        v2 = _make_version(db, strat.id, "v2.0")
        run1 = _make_run(
            db, strat.id, version_id=v1.id, run_type="backtest",
            metrics={"sharpe": 0.82, "trade_count": 80},
        )
        run2 = _make_run(
            db, strat.id, version_id=v2.id, run_type="backtest",
            metrics={"sharpe": 1.14, "trade_count": 80},
        )
        try:
            result = compare_strategy_versions(strat.id, "v1.0", "v2.0", db)
            metric_deltas = result.get("metric_deltas", [])
            sharpe_delta = next(
                (m for m in metric_deltas if m["key"] == "sharpe"), None
            )
            assert sharpe_delta is not None, "Expected sharpe in metric_deltas"
            assert sharpe_delta["status"] == "improved", (
                f"Expected sharpe status='improved', got {sharpe_delta['status']!r}"
            )
            assert sharpe_delta["delta"] is not None and sharpe_delta["delta"] > 0, (
                f"Expected positive sharpe delta, got {sharpe_delta['delta']}"
            )
        finally:
            _cleanup(db, run2, run1, v2, v1, strat)

    def test_run_metrics_turnover_increase_flagged(self, db):
        """v1 turnover=0.4, v2 turnover=0.7 -> worsened metric in deltas."""
        from app.services.strategy_lineage_diff import compare_strategy_versions

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="csv-turnoverworse")
        v1 = _make_version(db, strat.id, "v1.0")
        v2 = _make_version(db, strat.id, "v2.0")
        run1 = _make_run(
            db, strat.id, version_id=v1.id, run_type="backtest",
            metrics={"sharpe": 1.0, "turnover": 0.4, "trade_count": 50},
        )
        run2 = _make_run(
            db, strat.id, version_id=v2.id, run_type="backtest",
            metrics={"sharpe": 1.0, "turnover": 0.7, "trade_count": 50},
        )
        try:
            result = compare_strategy_versions(strat.id, "v1.0", "v2.0", db)
            metric_deltas = result.get("metric_deltas", [])
            turnover_delta = next(
                (m for m in metric_deltas if m["key"] == "turnover"), None
            )
            assert turnover_delta is not None, "Expected turnover in metric_deltas"
            assert turnover_delta["status"] == "worsened", (
                f"Expected turnover status='worsened' (higher turnover is worse), "
                f"got {turnover_delta['status']!r}"
            )
        finally:
            _cleanup(db, run2, run1, v2, v1, strat)

    def test_verdict_improved_when_metrics_improve(self, db):
        """Clean profile improvements -> verdict in ('improved', 'mixed')."""
        from app.services.strategy_lineage_diff import compare_strategy_versions

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="csv-verdimproved")
        v1 = _make_version(db, strat.id, "v1.0")
        v2 = _make_version(db, strat.id, "v2.0")
        run1 = _make_run(
            db, strat.id, version_id=v1.id, run_type="backtest",
            metrics={"sharpe": 0.5, "annual_return": 0.08, "trade_count": 50},
        )
        run2 = _make_run(
            db, strat.id, version_id=v2.id, run_type="backtest",
            metrics={"sharpe": 1.5, "annual_return": 0.25, "trade_count": 150},
        )
        try:
            result = compare_strategy_versions(strat.id, "v1.0", "v2.0", db)
            assert result["verdict"] in ("improved", "mixed"), (
                f"Expected verdict in ('improved', 'mixed'), got {result['verdict']!r}"
            )
        finally:
            _cleanup(db, run2, run1, v2, v1, strat)

    def test_verdict_worse_when_blockers_introduced(self, db):
        """Cost removed + metrics unchanged -> verdict in ('worse', 'mixed')."""
        from app.services.strategy_lineage_diff import compare_strategy_versions

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="csv-verdworse")
        v1 = _make_version(db, strat.id, "v1.0")
        v2 = _make_version(db, strat.id, "v2.0")
        run1 = _make_run(
            db, strat.id, version_id=v1.id, run_type="backtest",
            metrics={"sharpe": 1.0, "trade_count": 100},
        )
        run2 = _make_run(
            db, strat.id, version_id=v2.id, run_type="backtest",
            metrics={"sharpe": 1.0, "trade_count": 100},
        )
        cfg1 = _make_config_snapshot(
            db, strat.id, v1.id,
            {"params": {}, "assumptions": {"transaction_cost_bps": 5}},
            "cfg-v1",
        )
        cfg2 = _make_config_snapshot(
            db, strat.id, v2.id,
            {"params": {}, "assumptions": {}},
            "cfg-v2",
        )
        try:
            result = compare_strategy_versions(strat.id, "v1.0", "v2.0", db)
            assert result["verdict"] in ("worse", "mixed"), (
                f"Expected verdict in ('worse', 'mixed') when blocker introduced, "
                f"got {result['verdict']!r}"
            )
        finally:
            _cleanup(db, cfg2, cfg1, run2, run1, v2, v1, strat)

    def test_same_version_label_returns_unchanged(self, db):
        """Compare v1 vs v1 -> all sections unchanged, verdict=='unchanged'."""
        from app.services.strategy_lineage_diff import compare_strategy_versions

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="csv-sameversion")
        v1 = _make_version(db, strat.id, "v1.0")
        run1 = _make_run(
            db, strat.id, version_id=v1.id, run_type="backtest",
            metrics={"sharpe": 1.0, "trade_count": 100, "annual_return": 0.15},
        )
        try:
            result = compare_strategy_versions(strat.id, "v1.0", "v1.0", db)
            assert result["verdict"] == "unchanged", (
                f"Expected verdict='unchanged' when comparing same version, "
                f"got {result['verdict']!r}"
            )
            for section in result.get("sections", []):
                assert section["status"] in ("unchanged", "missing"), (
                    f"Expected section {section['key']} to be 'unchanged', "
                    f"got {section['status']!r}"
                )
        finally:
            _cleanup(db, run1, v1, strat)

    def test_diff_has_disclaimer(self, db):
        """Disclaimer not empty and contains 'not trading advice'."""
        from app.services.strategy_lineage_diff import compare_strategy_versions

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="csv-disclaimer")
        v1 = _make_version(db, strat.id, "v1.0")
        v2 = _make_version(db, strat.id, "v2.0")
        run1 = _make_run(
            db, strat.id, version_id=v1.id, run_type="backtest",
            metrics={"sharpe": 0.9, "trade_count": 50},
        )
        run2 = _make_run(
            db, strat.id, version_id=v2.id, run_type="backtest",
            metrics={"sharpe": 1.1, "trade_count": 60},
        )
        try:
            result = compare_strategy_versions(strat.id, "v1.0", "v2.0", db)
            disclaimer = result.get("disclaimer", "")
            assert disclaimer, "Expected non-empty disclaimer"
            assert "not trading advice" in disclaimer.lower(), (
                f"Expected 'not trading advice' in disclaimer, got: {disclaimer!r}"
            )
        finally:
            _cleanup(db, run2, run1, v2, v1, strat)

    def test_diff_has_generated_at(self, db):
        """generated_at is not None."""
        from app.services.strategy_lineage_diff import compare_strategy_versions

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="csv-generatedat")
        v1 = _make_version(db, strat.id, "v1.0")
        v2 = _make_version(db, strat.id, "v2.0")
        run1 = _make_run(
            db, strat.id, version_id=v1.id, run_type="backtest",
            metrics={"sharpe": 1.0, "trade_count": 50},
        )
        run2 = _make_run(
            db, strat.id, version_id=v2.id, run_type="backtest",
            metrics={"sharpe": 1.1, "trade_count": 55},
        )
        try:
            result = compare_strategy_versions(strat.id, "v1.0", "v2.0", db)
            assert result.get("generated_at") is not None, (
                "Expected generated_at to be set in diff result"
            )
        finally:
            _cleanup(db, run2, run1, v2, v1, strat)


# ---------------------------------------------------------------------------
# TestRenderLineageDiffReport
# ---------------------------------------------------------------------------


class TestRenderLineageDiffReport:
    """Tests for render_lineage_diff_report formatting."""

    def _make_sample_diff(self) -> dict:
        """Build a minimal diff dict for rendering tests."""
        return {
            "strategy_id": str(uuid.uuid4()),
            "base_version": "v1.0",
            "comparison_version": "v2.0",
            "verdict": "improved",
            "trust_delta": 5.0,
            "primary_change": "Sharpe improved by 39.0%.",
            "primary_risk": None,
            "summary": "Sharpe improved by 39%.",
            "sections": [
                {
                    "key": "config_diff",
                    "title": "Config Diff",
                    "status": "unchanged",
                    "items": [],
                },
                {
                    "key": "universe_diff",
                    "title": "Universe Diff",
                    "status": "unchanged",
                    "items": [],
                },
                {
                    "key": "signal_diff",
                    "title": "Signal Diff",
                    "status": "unchanged",
                    "items": [],
                },
                {
                    "key": "trust_diff",
                    "title": "Trust and Evidence Diff",
                    "status": "improved",
                    "items": [
                        {
                            "key": "trust_score",
                            "label": "Backtest Trust Score",
                            "base_value": 60.0,
                            "comparison_value": 70.0,
                            "delta": 10.0,
                            "status": "improved",
                            "explanation": "Backtest Trust Score changed by +10.0.",
                        }
                    ],
                },
            ],
            "metric_deltas": [
                {
                    "key": "sharpe",
                    "label": "Sharpe",
                    "base_value": 0.82,
                    "comparison_value": 1.14,
                    "delta": 0.32,
                    "percent_delta": 39.0,
                    "status": "improved",
                    "significant": True,
                    "explanation": "Sharpe increased by 39.0%.",
                }
            ],
            "blockers_introduced": [],
            "blockers_resolved": [],
            "suggested_actions": ["Evidence improved. Consider logging a new reliability score."],
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "disclaimer": "Strategy lineage diff is a deterministic research evidence comparison. It is not trading advice.",
        }

    def test_json_report_parseable(self):
        """render format=json -> valid json.loads()."""
        from app.services.strategy_lineage_diff import render_lineage_diff_report

        diff = self._make_sample_diff()
        result = render_lineage_diff_report(diff, "Test Strategy", format="json")
        parsed = json.loads(result)
        assert isinstance(parsed, dict), "Expected parsed JSON to be a dict"

    def test_markdown_report_contains_header(self):
        """render format=markdown -> contains '# Strategy Lineage Diff'."""
        from app.services.strategy_lineage_diff import render_lineage_diff_report

        diff = self._make_sample_diff()
        result = render_lineage_diff_report(diff, "Test Strategy", format="markdown")
        assert "# Strategy Lineage Diff" in result, (
            f"Expected '# Strategy Lineage Diff' in markdown output"
        )

    def test_markdown_contains_verdict(self):
        """Markdown contains verdict string."""
        from app.services.strategy_lineage_diff import render_lineage_diff_report

        diff = self._make_sample_diff()
        result = render_lineage_diff_report(diff, "Test Strategy", format="markdown")
        assert "improved" in result.lower(), (
            f"Expected verdict 'improved' to appear in markdown"
        )

    def test_markdown_contains_sign_convention(self):
        """Markdown has base_version and comparison_version labels."""
        from app.services.strategy_lineage_diff import render_lineage_diff_report

        diff = self._make_sample_diff()
        result = render_lineage_diff_report(diff, "Test Strategy", format="markdown")
        assert "v1.0" in result, "Expected base_version label 'v1.0' in markdown"
        assert "v2.0" in result, "Expected comparison_version label 'v2.0' in markdown"


# ---------------------------------------------------------------------------
# TestLineageDiffEndpoints
# ---------------------------------------------------------------------------


class TestLineageDiffEndpoints:
    """Integration tests via TestClient for M95 lineage diff endpoints."""

    def test_versions_endpoint_200(self, client, db):
        """GET /api/strategies/{id}/lineage/versions -> 200."""
        strategy = _get_seeded_strategy(db)
        assert strategy is not None
        resp = client.get(f"/api/strategies/{strategy.id}/lineage/versions")
        assert resp.status_code == 200, (
            f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        )

    def test_versions_unknown_strategy_404(self, client):
        """GET with fake strategy id -> 404."""
        fake_id = uuid.uuid4()
        resp = client.get(f"/api/strategies/{fake_id}/lineage/versions")
        assert resp.status_code == 404

    def test_diff_endpoint_200(self, client, db):
        """GET /api/strategies/{id}/lineage/diff?base_version=...&comparison_version=... -> 200."""
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="ep-diff200")
        v1 = _make_version(db, strat.id, "v1.0")
        v2 = _make_version(db, strat.id, "v2.0")
        run1 = _make_run(
            db, strat.id, version_id=v1.id, run_type="backtest",
            metrics={"sharpe": 0.9, "trade_count": 50},
        )
        run2 = _make_run(
            db, strat.id, version_id=v2.id, run_type="backtest",
            metrics={"sharpe": 1.1, "trade_count": 60},
        )
        try:
            resp = client.get(
                f"/api/strategies/{strat.id}/lineage/diff"
                "?base_version=v1.0&comparison_version=v2.0"
            )
            assert resp.status_code == 200, (
                f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
            )
        finally:
            _cleanup(db, run2, run1, v2, v1, strat)

    def test_diff_endpoint_404_unknown(self, client):
        """GET with fake strategy -> 404."""
        fake_id = uuid.uuid4()
        resp = client.get(
            f"/api/strategies/{fake_id}/lineage/diff"
            "?base_version=v1.0&comparison_version=v2.0"
        )
        assert resp.status_code == 404

    def test_diff_report_json_200(self, client, db):
        """GET .../diff/report?format=json&base_version=...&comparison_version=... -> 200."""
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="ep-reportjson")
        v1 = _make_version(db, strat.id, "v1.0")
        v2 = _make_version(db, strat.id, "v2.0")
        run1 = _make_run(
            db, strat.id, version_id=v1.id, run_type="backtest",
            metrics={"sharpe": 0.9, "trade_count": 50},
        )
        run2 = _make_run(
            db, strat.id, version_id=v2.id, run_type="backtest",
            metrics={"sharpe": 1.1, "trade_count": 60},
        )
        try:
            resp = client.get(
                f"/api/strategies/{strat.id}/lineage/diff/report"
                "?format=json&base_version=v1.0&comparison_version=v2.0"
            )
            assert resp.status_code == 200, (
                f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
            )
            data = resp.json()
            assert "content" in data, f"Expected 'content' key in response, got {list(data.keys())}"
        finally:
            _cleanup(db, run2, run1, v2, v1, strat)

    def test_diff_report_markdown_200(self, client, db):
        """GET .../diff/report?format=markdown -> 200 with text content."""
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="ep-reportmd")
        v1 = _make_version(db, strat.id, "v1.0")
        v2 = _make_version(db, strat.id, "v2.0")
        run1 = _make_run(
            db, strat.id, version_id=v1.id, run_type="backtest",
            metrics={"sharpe": 0.9, "trade_count": 50},
        )
        run2 = _make_run(
            db, strat.id, version_id=v2.id, run_type="backtest",
            metrics={"sharpe": 1.1, "trade_count": 60},
        )
        try:
            resp = client.get(
                f"/api/strategies/{strat.id}/lineage/diff/report"
                "?format=markdown&base_version=v1.0&comparison_version=v2.0"
            )
            assert resp.status_code == 200, (
                f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
            )
            assert len(resp.text) > 0, "Expected non-empty markdown response"
        finally:
            _cleanup(db, run2, run1, v2, v1, strat)

    def test_diff_report_invalid_format_400(self, client, db):
        """GET .../diff/report?format=xml -> 400."""
        strategy = _get_seeded_strategy(db)
        resp = client.get(
            f"/api/strategies/{strategy.id}/lineage/diff/report"
            "?format=xml&base_version=v1.0&comparison_version=v2.0"
        )
        assert resp.status_code == 400, (
            f"Expected 400 for invalid format, got {resp.status_code}"
        )
