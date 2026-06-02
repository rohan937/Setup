"""M35 tests: Strategy Version Lineage.

Coverage:
  - GET /api/strategies/{strategy_id}/version-lineage endpoint
  - Per-version evidence counts and scores
  - Score thresholds and lineage_status labels
  - Summary fields (most/least instrumented, averages, missing counts)
  - Transitions between versions (hash change detection)
  - No AuditTimelineEvent side-effects

All tests use the shared session-scoped fixtures from conftest.py.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone

import pytest

from app.models.audit_timeline_event import AuditTimelineEvent
from app.models.backtest_audit import BacktestAudit
from app.models.dataset import Dataset
from app.models.dataset_snapshot import DatasetSnapshot
from app.models.organization import Organization
from app.models.project import Project
from app.models.signal_snapshot import SignalSnapshot
from app.models.strategy import Strategy
from app.models.strategy_config_snapshot import StrategyConfigSnapshot
from app.models.strategy_run import StrategyRun
from app.models.strategy_version import StrategyVersion
from app.models.universe_snapshot import UniverseSnapshot


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_org(db):
    return db.query(Organization).first()


def _get_project(db):
    return db.query(Project).first()


def _make_strategy(db, org, project, name=None):
    slug = (name or f"m35-{uuid.uuid4().hex[:8]}").lower().replace(" ", "-")
    s = Strategy(
        project_id=project.id,
        name=name or f"M35 Strategy {uuid.uuid4().hex[:6]}",
        slug=slug,
        asset_class="equity",
        status="active",
    )
    db.add(s)
    db.flush()
    return s


def _make_version(db, strategy, version_label="v1.0", git_commit=None, signal_name=None):
    v = StrategyVersion(
        strategy_id=strategy.id,
        version_label=version_label,
        git_commit=git_commit,
        signal_name=signal_name,
    )
    db.add(v)
    db.flush()
    return v


def _make_run(db, strategy, version=None, run_type="backtest"):
    r = StrategyRun(
        strategy_id=strategy.id,
        strategy_version_id=version.id if version else None,
        run_name=f"run-{uuid.uuid4().hex[:6]}",
        run_type=run_type,
        status="completed",
    )
    db.add(r)
    db.flush()
    return r


def _make_config_snapshot(db, strategy, version):
    cfg_data = {"mode": "test", "param": uuid.uuid4().hex[:8]}
    cfg_hash = hashlib.sha256(
        json.dumps(cfg_data, sort_keys=True).encode()
    ).hexdigest()
    snap = StrategyConfigSnapshot(
        strategy_id=strategy.id,
        strategy_version_id=version.id,
        label=f"cfg-{uuid.uuid4().hex[:6]}",
        config_json=cfg_data,
        config_hash=cfg_hash,
    )
    db.add(snap)
    db.flush()
    return snap


def _make_universe_snapshot(db, strategy, version):
    symbols = ["AAPL", "GOOG"]
    uni_hash = hashlib.sha256(
        json.dumps(sorted(symbols)).encode()
    ).hexdigest()
    snap = UniverseSnapshot(
        strategy_id=strategy.id,
        strategy_version_id=version.id,
        label=f"uni-{uuid.uuid4().hex[:6]}",
        symbols_json=symbols,
        symbol_count=len(symbols),
        universe_hash=uni_hash,
    )
    db.add(snap)
    db.flush()
    return snap


def _make_signal_snapshot(db, strategy, version, quality_score=85):
    rows = [{"symbol": "AAPL", "signal": 1.0}]
    sig_hash = hashlib.sha256(
        json.dumps(rows, sort_keys=True).encode()
    ).hexdigest()
    snap = SignalSnapshot(
        strategy_id=strategy.id,
        strategy_version_id=version.id,
        label=f"sig-{uuid.uuid4().hex[:6]}",
        rows_json=rows,
        row_count=len(rows),
        signal_hash=sig_hash,
        quality_score=quality_score,
    )
    db.add(snap)
    db.flush()
    return snap


def _make_dataset_snapshot(db):
    project = _get_project(db)
    dataset = Dataset(
        project_id=project.id,
        name=f"DS-{uuid.uuid4().hex[:6]}",
    )
    db.add(dataset)
    db.flush()
    snap = DatasetSnapshot(
        dataset_id=dataset.id,
        version_label="v1",
        row_count=100,
        health_score=90,
    )
    db.add(snap)
    db.flush()
    return dataset, snap


def _make_backtest_audit(db, run):
    audit = BacktestAudit(
        strategy_run_id=run.id,
        trust_score=80,
        overall_status="good",
        summary="Test audit",
    )
    db.add(audit)
    db.flush()
    return audit


def _teardown(db, objs):
    """Delete objects in reverse order to respect FK constraints."""
    for obj in reversed(objs):
        try:
            db.delete(obj)
        except Exception:
            pass
    try:
        db.commit()
    except Exception:
        db.rollback()


# ---------------------------------------------------------------------------
# TestVersionLineageEndpoint
# ---------------------------------------------------------------------------


class TestVersionLineageEndpoint:
    def test_lineage_returns_200(self, client, db):
        org = _get_org(db)
        project = _get_project(db)
        strategy = _make_strategy(db, org, project)
        db.commit()

        try:
            resp = client.get(f"/api/strategies/{strategy.id}/version-lineage")
            assert resp.status_code == 200
        finally:
            db.delete(strategy)
            db.commit()

    def test_lineage_response_fields(self, client, db):
        org = _get_org(db)
        project = _get_project(db)
        strategy = _make_strategy(db, org, project)
        db.commit()

        try:
            resp = client.get(f"/api/strategies/{strategy.id}/version-lineage")
            assert resp.status_code == 200
            data = resp.json()
            assert "summary" in data
            assert "versions" in data
            assert "transitions" in data
            assert isinstance(data["versions"], list)
            assert isinstance(data["transitions"], list)
            assert "strategy_id" in data["summary"]
            assert "version_count" in data["summary"]
        finally:
            db.delete(strategy)
            db.commit()

    def test_unknown_strategy_404(self, client):
        fake_id = str(uuid.uuid4())
        resp = client.get(f"/api/strategies/{fake_id}/version-lineage")
        assert resp.status_code == 404

    def test_strategy_with_no_versions(self, client, db):
        org = _get_org(db)
        project = _get_project(db)
        strategy = _make_strategy(db, org, project)
        db.commit()

        try:
            resp = client.get(f"/api/strategies/{strategy.id}/version-lineage")
            assert resp.status_code == 200
            data = resp.json()
            assert data["summary"]["version_count"] == 0
            assert data["versions"] == []
            assert data["transitions"] == []
        finally:
            db.delete(strategy)
            db.commit()

    def test_seeded_strategy_returns_lineage(self, client, db):
        strategy = db.query(Strategy).filter(Strategy.slug == "aapl-mean-reversion-v1").first()
        if strategy is None:
            pytest.skip("Seeded AAPL strategy not present")
        resp = client.get(f"/api/strategies/{strategy.id}/version-lineage")
        assert resp.status_code == 200
        data = resp.json()
        assert data["summary"]["version_count"] >= 1
        assert len(data["versions"]) >= 1


# ---------------------------------------------------------------------------
# TestVersionEvidenceCounts
# ---------------------------------------------------------------------------


class TestVersionEvidenceCounts:
    def test_run_count_correct(self, client, db):
        org = _get_org(db)
        project = _get_project(db)
        strategy = _make_strategy(db, org, project)
        version = _make_version(db, strategy, "v1.0")
        run1 = _make_run(db, strategy, version)
        run2 = _make_run(db, strategy, version)
        db.commit()

        try:
            resp = client.get(f"/api/strategies/{strategy.id}/version-lineage")
            assert resp.status_code == 200
            versions = resp.json()["versions"]
            v = next(v for v in versions if v["version_label"] == "v1.0")
            assert v["run_count"] == 2
        finally:
            _teardown(db, [run1, run2, version, strategy])

    def test_config_count_correct(self, client, db):
        org = _get_org(db)
        project = _get_project(db)
        strategy = _make_strategy(db, org, project)
        version = _make_version(db, strategy, "v-cfg")
        cfg = _make_config_snapshot(db, strategy, version)
        db.commit()

        try:
            resp = client.get(f"/api/strategies/{strategy.id}/version-lineage")
            assert resp.status_code == 200
            versions = resp.json()["versions"]
            v = next(v for v in versions if v["version_label"] == "v-cfg")
            assert v["config_snapshot_count"] == 1
            assert v["has_config"] is True
        finally:
            _teardown(db, [cfg, version, strategy])

    def test_universe_count_correct(self, client, db):
        org = _get_org(db)
        project = _get_project(db)
        strategy = _make_strategy(db, org, project)
        version = _make_version(db, strategy, "v-uni")
        uni = _make_universe_snapshot(db, strategy, version)
        db.commit()

        try:
            resp = client.get(f"/api/strategies/{strategy.id}/version-lineage")
            assert resp.status_code == 200
            versions = resp.json()["versions"]
            v = next(v for v in versions if v["version_label"] == "v-uni")
            assert v["universe_snapshot_count"] == 1
            assert v["has_universe"] is True
        finally:
            _teardown(db, [uni, version, strategy])

    def test_signal_count_correct(self, client, db):
        org = _get_org(db)
        project = _get_project(db)
        strategy = _make_strategy(db, org, project)
        version = _make_version(db, strategy, "v-sig")
        sig = _make_signal_snapshot(db, strategy, version)
        db.commit()

        try:
            resp = client.get(f"/api/strategies/{strategy.id}/version-lineage")
            assert resp.status_code == 200
            versions = resp.json()["versions"]
            v = next(v for v in versions if v["version_label"] == "v-sig")
            assert v["signal_snapshot_count"] == 1
            assert v["has_signal"] is True
        finally:
            _teardown(db, [sig, version, strategy])

    def test_dataset_linked_run_count(self, client, db):
        org = _get_org(db)
        project = _get_project(db)
        strategy = _make_strategy(db, org, project)
        version = _make_version(db, strategy, "v-ds-linked")
        dataset, ds_snap = _make_dataset_snapshot(db)
        run = _make_run(db, strategy, version)
        run.dataset_snapshot_id = ds_snap.id
        db.flush()
        db.commit()

        try:
            resp = client.get(f"/api/strategies/{strategy.id}/version-lineage")
            assert resp.status_code == 200
            versions = resp.json()["versions"]
            v = next(v for v in versions if v["version_label"] == "v-ds-linked")
            assert v["dataset_linked_run_count"] >= 1
            assert v["has_dataset_linked_runs"] is True
        finally:
            _teardown(db, [run, ds_snap, dataset, version, strategy])

    def test_version_evidence_score_with_all(self, client, db):
        """All 6 evidence types present → score == 100."""
        org = _get_org(db)
        project = _get_project(db)
        strategy = _make_strategy(db, org, project)
        version = _make_version(db, strategy, "v-all")
        cfg = _make_config_snapshot(db, strategy, version)
        uni = _make_universe_snapshot(db, strategy, version)
        sig = _make_signal_snapshot(db, strategy, version)
        dataset, ds_snap = _make_dataset_snapshot(db)
        run = _make_run(db, strategy, version)
        run.dataset_snapshot_id = ds_snap.id
        db.flush()
        audit = _make_backtest_audit(db, run)
        db.commit()

        try:
            resp = client.get(f"/api/strategies/{strategy.id}/version-lineage")
            assert resp.status_code == 200
            versions = resp.json()["versions"]
            v = next(v for v in versions if v["version_label"] == "v-all")
            assert v["version_evidence_score"] == 100.0
        finally:
            _teardown(db, [audit, run, ds_snap, dataset, sig, uni, cfg, version, strategy])

    def test_version_evidence_score_partial(self, client, db):
        """Config (15) + runs (20) only → score == 35."""
        org = _get_org(db)
        project = _get_project(db)
        strategy = _make_strategy(db, org, project)
        version = _make_version(db, strategy, "v-partial")
        cfg = _make_config_snapshot(db, strategy, version)
        run = _make_run(db, strategy, version)
        db.commit()

        try:
            resp = client.get(f"/api/strategies/{strategy.id}/version-lineage")
            assert resp.status_code == 200
            versions = resp.json()["versions"]
            v = next(v for v in versions if v["version_label"] == "v-partial")
            assert v["version_evidence_score"] == 35.0
        finally:
            _teardown(db, [run, cfg, version, strategy])

    def test_version_evidence_score_nothing(self, client, db):
        """No evidence → score == 0."""
        org = _get_org(db)
        project = _get_project(db)
        strategy = _make_strategy(db, org, project)
        version = _make_version(db, strategy, "v-empty")
        db.commit()

        try:
            resp = client.get(f"/api/strategies/{strategy.id}/version-lineage")
            assert resp.status_code == 200
            versions = resp.json()["versions"]
            v = next(v for v in versions if v["version_label"] == "v-empty")
            assert v["version_evidence_score"] == 0.0
        finally:
            _teardown(db, [version, strategy])

    def test_lineage_status_thresholds(self, db):
        """Test status labels directly from the service."""
        from app.services.version_lineage import (
            _compute_version_item,
            StrategyVersionLineageItemData,
        )

        org = _get_org(db)
        project = _get_project(db)

        def _score_to_status(score_to_achieve):
            """Create a version with given score and return lineage_status."""
            strategy = _make_strategy(db, org, project)
            version = _make_version(db, strategy, f"v-thresh-{uuid.uuid4().hex[:4]}")
            objs = [version, strategy]

            # Build up evidence to reach target score
            remaining = score_to_achieve
            if remaining >= 15:
                cfg = _make_config_snapshot(db, strategy, version)
                objs.insert(0, cfg)
                remaining -= 15
            if remaining >= 15:
                uni = _make_universe_snapshot(db, strategy, version)
                objs.insert(0, uni)
                remaining -= 15
            if remaining >= 20:
                sig = _make_signal_snapshot(db, strategy, version)
                objs.insert(0, sig)
                objs.insert(0, sig)
                remaining -= 20
            if remaining >= 20:
                run = _make_run(db, strategy, version)
                objs.insert(0, run)
                remaining -= 20

            db.flush()
            item = _compute_version_item(version, strategy.id, db)
            _teardown(db, objs)
            return item.lineage_status, item.version_evidence_score

        # score 0 → under_instrumented
        status, score = _score_to_status(0)
        assert status == "under_instrumented", f"Expected under_instrumented, got {status} (score={score})"

        # score 35 (config+runs = 15+20) → partial (>=30, <60)
        status, score = _score_to_status(35)
        assert status == "partial", f"Expected partial, got {status} (score={score})"

        # score 70 (config+uni+sig+runs = 15+15+20+20) → usable (>=60, <80)
        # We can't reach exactly 50 cleanly but 70 is cleanly usable
        strategy_u = _make_strategy(db, org, project)
        version_u = _make_version(db, strategy_u, f"v-usable-{uuid.uuid4().hex[:4]}")
        cfg_u = _make_config_snapshot(db, strategy_u, version_u)
        uni_u = _make_universe_snapshot(db, strategy_u, version_u)
        sig_u = _make_signal_snapshot(db, strategy_u, version_u)
        run_u = _make_run(db, strategy_u, version_u)
        db.flush()
        db.commit()
        try:
            item_u = _compute_version_item(version_u, strategy_u.id, db)
            assert item_u.version_evidence_score == 70.0
            assert item_u.lineage_status == "usable", f"Expected usable, got {item_u.lineage_status}"
        finally:
            _teardown(db, [run_u, sig_u, uni_u, cfg_u, version_u, strategy_u])

        # config+uni+sig+runs+ds_linked = 15+15+20+20+15 = 85 → well_instrumented (>=80)
        strategy = _make_strategy(db, org, project)
        version = _make_version(db, strategy, f"v-well-{uuid.uuid4().hex[:4]}")
        cfg = _make_config_snapshot(db, strategy, version)
        uni = _make_universe_snapshot(db, strategy, version)
        sig = _make_signal_snapshot(db, strategy, version)
        dataset, ds_snap = _make_dataset_snapshot(db)
        run = _make_run(db, strategy, version)
        run.dataset_snapshot_id = ds_snap.id
        db.flush()
        db.commit()
        try:
            item = _compute_version_item(version, strategy.id, db)
            assert item.lineage_status == "well_instrumented", f"Expected well_instrumented, got {item.lineage_status} (score={item.version_evidence_score})"
            assert item.version_evidence_score >= 80
        finally:
            _teardown(db, [run, ds_snap, dataset, sig, uni, cfg, version, strategy])


# ---------------------------------------------------------------------------
# TestVersionLineageSummary
# ---------------------------------------------------------------------------


class TestVersionLineageSummary:
    def test_most_instrumented_version(self, client, db):
        org = _get_org(db)
        project = _get_project(db)
        strategy = _make_strategy(db, org, project)
        # Rich version: config+run
        v_rich = _make_version(db, strategy, "v-rich")
        cfg = _make_config_snapshot(db, strategy, v_rich)
        run = _make_run(db, strategy, v_rich)
        # Poor version: no evidence
        v_poor = _make_version(db, strategy, "v-poor")
        db.commit()

        try:
            resp = client.get(f"/api/strategies/{strategy.id}/version-lineage")
            assert resp.status_code == 200
            summary = resp.json()["summary"]
            most_id = summary["most_instrumented_version_id"]
            assert most_id == str(v_rich.id)
        finally:
            _teardown(db, [run, cfg, v_rich, v_poor, strategy])

    def test_versions_missing_signal_count(self, client, db):
        org = _get_org(db)
        project = _get_project(db)
        strategy = _make_strategy(db, org, project)
        # One version with no signal
        v_no_sig = _make_version(db, strategy, "v-no-sig")
        db.commit()

        try:
            resp = client.get(f"/api/strategies/{strategy.id}/version-lineage")
            assert resp.status_code == 200
            summary = resp.json()["summary"]
            assert summary["versions_missing_signal"] >= 1
        finally:
            _teardown(db, [v_no_sig, strategy])

    def test_suggested_checks_for_missing_evidence(self, client, db):
        org = _get_org(db)
        project = _get_project(db)
        strategy = _make_strategy(db, org, project)
        version = _make_version(db, strategy, "v-no-evidence")
        db.commit()

        try:
            resp = client.get(f"/api/strategies/{strategy.id}/version-lineage")
            assert resp.status_code == 200
            versions = resp.json()["versions"]
            v = next(v for v in versions if v["version_label"] == "v-no-evidence")
            assert len(v["suggested_checks"]) > 0
        finally:
            _teardown(db, [version, strategy])

    def test_deterministic_summary_no_ai_language(self, client, db):
        org = _get_org(db)
        project = _get_project(db)
        strategy = _make_strategy(db, org, project)
        _make_version(db, strategy, "v1.0")
        db.commit()

        forbidden = ["AI", "investment", "profit", "buy", "sell"]
        try:
            resp = client.get(f"/api/strategies/{strategy.id}/version-lineage")
            assert resp.status_code == 200
            summary_text = resp.json()["summary"]["deterministic_summary"]
            for word in forbidden:
                assert word.lower() not in summary_text.lower(), (
                    f"Forbidden word '{word}' found in summary: {summary_text}"
                )
        finally:
            versions = db.query(StrategyVersion).filter(
                StrategyVersion.strategy_id == strategy.id
            ).all()
            for v in versions:
                db.delete(v)
            db.delete(strategy)
            db.commit()

    def test_no_timeline_event_created(self, client, db):
        org = _get_org(db)
        project = _get_project(db)
        strategy = _make_strategy(db, org, project)
        db.commit()

        count_before = (
            db.query(AuditTimelineEvent)
            .filter(AuditTimelineEvent.source_id == str(strategy.id))
            .count()
        )

        try:
            resp = client.get(f"/api/strategies/{strategy.id}/version-lineage")
            assert resp.status_code == 200
            count_after = (
                db.query(AuditTimelineEvent)
                .filter(AuditTimelineEvent.source_id == str(strategy.id))
                .count()
            )
            assert count_after == count_before
        finally:
            db.delete(strategy)
            db.commit()


# ---------------------------------------------------------------------------
# TestVersionTransitions
# ---------------------------------------------------------------------------


class TestVersionTransitions:
    def test_transitions_between_two_versions(self, client, db):
        org = _get_org(db)
        project = _get_project(db)
        strategy = _make_strategy(db, org, project)
        v1 = _make_version(db, strategy, "v1.0")
        v2 = _make_version(db, strategy, "v2.0")
        db.commit()

        try:
            resp = client.get(f"/api/strategies/{strategy.id}/version-lineage")
            assert resp.status_code == 200
            transitions = resp.json()["transitions"]
            assert len(transitions) == 1
            t = transitions[0]
            assert t["from_version_label"] == "v1.0"
            assert t["to_version_label"] == "v2.0"
        finally:
            _teardown(db, [v1, v2, strategy])

    def test_transition_detects_git_change(self, client, db):
        org = _get_org(db)
        project = _get_project(db)
        strategy = _make_strategy(db, org, project)
        v1 = _make_version(db, strategy, "v1.0", git_commit="abc123")
        v2 = _make_version(db, strategy, "v2.0", git_commit="def456")
        db.commit()

        try:
            resp = client.get(f"/api/strategies/{strategy.id}/version-lineage")
            assert resp.status_code == 200
            transitions = resp.json()["transitions"]
            assert len(transitions) == 1
            assert transitions[0]["git_commit_changed"] is True
        finally:
            _teardown(db, [v1, v2, strategy])

    def test_transition_detects_signal_name_change(self, client, db):
        org = _get_org(db)
        project = _get_project(db)
        strategy = _make_strategy(db, org, project)
        v1 = _make_version(db, strategy, "v1.0", signal_name="MeanReversion")
        v2 = _make_version(db, strategy, "v2.0", signal_name="Momentum")
        db.commit()

        try:
            resp = client.get(f"/api/strategies/{strategy.id}/version-lineage")
            assert resp.status_code == 200
            transitions = resp.json()["transitions"]
            assert len(transitions) == 1
            assert transitions[0]["signal_name_changed"] is True
        finally:
            _teardown(db, [v1, v2, strategy])

    def test_config_hash_changed_when_different(self, client, db):
        org = _get_org(db)
        project = _get_project(db)
        strategy = _make_strategy(db, org, project)
        v1 = _make_version(db, strategy, "v1.0")
        v2 = _make_version(db, strategy, "v2.0")

        # Give each version a distinct config snapshot
        cfg_data_1 = {"mode": "conservative"}
        cfg_hash_1 = hashlib.sha256(json.dumps(cfg_data_1, sort_keys=True).encode()).hexdigest()
        cfg1 = StrategyConfigSnapshot(
            strategy_id=strategy.id,
            strategy_version_id=v1.id,
            label="cfg-v1",
            config_json=cfg_data_1,
            config_hash=cfg_hash_1,
        )
        cfg_data_2 = {"mode": "aggressive"}
        cfg_hash_2 = hashlib.sha256(json.dumps(cfg_data_2, sort_keys=True).encode()).hexdigest()
        cfg2 = StrategyConfigSnapshot(
            strategy_id=strategy.id,
            strategy_version_id=v2.id,
            label="cfg-v2",
            config_json=cfg_data_2,
            config_hash=cfg_hash_2,
        )
        db.add(cfg1)
        db.add(cfg2)
        db.flush()
        db.commit()

        try:
            resp = client.get(f"/api/strategies/{strategy.id}/version-lineage")
            assert resp.status_code == 200
            transitions = resp.json()["transitions"]
            assert len(transitions) == 1
            assert transitions[0]["config_hash_changed"] is True
        finally:
            _teardown(db, [cfg1, cfg2, v1, v2, strategy])
