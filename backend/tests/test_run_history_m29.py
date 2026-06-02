"""M29 tests: Strategy Run History and Timeline Drilldown.

Tests for:
  - GET /api/strategies/{id}/run-history endpoint
  - GET /api/strategies/{id}/timeline/drilldown endpoint
  - Evidence enrichment per run
  - Run health label computation
  - Filtering by run_type, status, evidence_status
  - Timeline drilldown filtering and evidence_category
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from app.models.audit_timeline_event import AuditTimelineEvent
from app.models.backtest_audit import BacktestAudit
from app.models.backtest_issue import BacktestIssue
from app.models.dataset import Dataset
from app.models.dataset_snapshot import DatasetSnapshot
from app.models.organization import Organization
from app.models.project import Project
from app.models.strategy import Strategy
from app.models.strategy_run import StrategyRun
from app.models.strategy_version import StrategyVersion


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_strategy(db, org, project, *, name=None, asset_class="equity", status="active"):
    slug = (name or f"test-{uuid.uuid4().hex[:6]}").lower().replace(" ", "-")
    s = Strategy(
        project_id=project.id,
        name=name or f"TestStrat-{uuid.uuid4().hex[:6]}",
        slug=slug,
        asset_class=asset_class,
        status=status,
    )
    db.add(s)
    db.flush()
    return s


def _make_run(db, strategy, *, run_type="backtest", status="completed"):
    r = StrategyRun(
        strategy_id=strategy.id,
        run_name=f"run-{uuid.uuid4().hex[:6]}",
        run_type=run_type,
        status=status,
    )
    db.add(r)
    db.flush()
    return r


def _get_seeded_org(db):
    return db.query(Organization).first()


def _get_seeded_project(db):
    return db.query(Project).first()


# ---------------------------------------------------------------------------
# TestRunHistoryEndpoint
# ---------------------------------------------------------------------------


class TestRunHistoryEndpoint:
    """Integration tests via TestClient for run-history endpoint."""

    def test_run_history_200(self, client, db):
        org = _get_seeded_org(db)
        project = _get_seeded_project(db)
        strategy = _make_strategy(db, org, project)
        _make_run(db, strategy)
        db.commit()

        try:
            resp = client.get(f"/api/strategies/{strategy.id}/run-history")
            assert resp.status_code == 200
        finally:
            runs = db.query(StrategyRun).filter(StrategyRun.strategy_id == strategy.id).all()
            for r in runs:
                db.delete(r)
            db.delete(strategy)
            db.commit()

    def test_run_history_response_fields(self, client, db):
        org = _get_seeded_org(db)
        project = _get_seeded_project(db)
        strategy = _make_strategy(db, org, project)
        _make_run(db, strategy)
        db.commit()

        try:
            resp = client.get(f"/api/strategies/{strategy.id}/run-history")
            data = resp.json()
            assert "items" in data
            assert "total" in data
            assert "limit" in data
            assert "offset" in data
            assert "summary" in data
        finally:
            runs = db.query(StrategyRun).filter(StrategyRun.strategy_id == strategy.id).all()
            for r in runs:
                db.delete(r)
            db.delete(strategy)
            db.commit()

    def test_run_history_newest_first(self, client, db):
        org = _get_seeded_org(db)
        project = _get_seeded_project(db)
        strategy = _make_strategy(db, org, project)
        r1 = _make_run(db, strategy)
        r2 = _make_run(db, strategy)
        db.commit()

        try:
            resp = client.get(f"/api/strategies/{strategy.id}/run-history")
            assert resp.status_code == 200
            data = resp.json()
            items = data["items"]
            assert len(items) >= 2
            # Newest should be first (r2 was created after r1)
            run_ids = [i["run_id"] for i in items]
            assert str(r2.id) in run_ids
            assert str(r1.id) in run_ids
            idx_r2 = run_ids.index(str(r2.id))
            idx_r1 = run_ids.index(str(r1.id))
            assert idx_r2 < idx_r1
        finally:
            runs = db.query(StrategyRun).filter(StrategyRun.strategy_id == strategy.id).all()
            for r in runs:
                db.delete(r)
            db.delete(strategy)
            db.commit()

    def test_run_history_404_unknown(self, client):
        fake_id = uuid.uuid4()
        resp = client.get(f"/api/strategies/{fake_id}/run-history")
        assert resp.status_code == 404

    def test_run_history_filter_by_run_type(self, client, db):
        org = _get_seeded_org(db)
        project = _get_seeded_project(db)
        strategy = _make_strategy(db, org, project)
        _make_run(db, strategy, run_type="backtest")
        _make_run(db, strategy, run_type="paper")
        db.commit()

        try:
            resp = client.get(f"/api/strategies/{strategy.id}/run-history?run_type=backtest")
            assert resp.status_code == 200
            data = resp.json()
            for item in data["items"]:
                assert item["run_type"] == "backtest"
        finally:
            runs = db.query(StrategyRun).filter(StrategyRun.strategy_id == strategy.id).all()
            for r in runs:
                db.delete(r)
            db.delete(strategy)
            db.commit()

    def test_run_history_filter_missing_dataset(self, client, db):
        org = _get_seeded_org(db)
        project = _get_seeded_project(db)
        strategy = _make_strategy(db, org, project)
        # Run without dataset (no dataset_snapshot_id)
        _make_run(db, strategy)
        db.commit()

        try:
            resp = client.get(
                f"/api/strategies/{strategy.id}/run-history?evidence_status=missing_dataset"
            )
            assert resp.status_code == 200
            data = resp.json()
            for item in data["items"]:
                assert item["has_dataset_evidence"] is False
        finally:
            runs = db.query(StrategyRun).filter(StrategyRun.strategy_id == strategy.id).all()
            for r in runs:
                db.delete(r)
            db.delete(strategy)
            db.commit()

    def test_run_history_filter_missing_audit(self, client, db):
        org = _get_seeded_org(db)
        project = _get_seeded_project(db)
        strategy = _make_strategy(db, org, project)
        _make_run(db, strategy)
        db.commit()

        try:
            resp = client.get(
                f"/api/strategies/{strategy.id}/run-history?evidence_status=missing_audit"
            )
            assert resp.status_code == 200
            data = resp.json()
            for item in data["items"]:
                assert item["has_backtest_audit"] is False
        finally:
            runs = db.query(StrategyRun).filter(StrategyRun.strategy_id == strategy.id).all()
            for r in runs:
                db.delete(r)
            db.delete(strategy)
            db.commit()

    def test_run_history_summary_has_counts(self, client, db):
        org = _get_seeded_org(db)
        project = _get_seeded_project(db)
        strategy = _make_strategy(db, org, project)
        _make_run(db, strategy)
        db.commit()

        try:
            resp = client.get(f"/api/strategies/{strategy.id}/run-history")
            assert resp.status_code == 200
            summary = resp.json()["summary"]
            assert "strong_count" in summary
            assert "review_count" in summary
            assert "weak_count" in summary
            assert "total_runs" in summary
            assert "runs_missing_dataset" in summary
            assert "runs_missing_audit" in summary
        finally:
            runs = db.query(StrategyRun).filter(StrategyRun.strategy_id == strategy.id).all()
            for r in runs:
                db.delete(r)
            db.delete(strategy)
            db.commit()


# ---------------------------------------------------------------------------
# TestRunHistoryEnrichment
# ---------------------------------------------------------------------------


class TestRunHistoryEnrichment:
    """Unit tests for evidence enrichment and health label logic."""

    def test_has_dataset_evidence_when_linked(self, client, db):
        org = _get_seeded_org(db)
        project = _get_seeded_project(db)
        strategy = _make_strategy(db, org, project)

        # Create a dataset and snapshot
        dataset = Dataset(
            project_id=project.id,
            name=f"ds-{uuid.uuid4().hex[:6]}",
            dataset_type="ohlcv",
            source_type="manual",
        )
        db.add(dataset)
        db.flush()

        snapshot = DatasetSnapshot(
            dataset_id=dataset.id,
            version_label="v1",
            row_count=100,
            health_score=90,
        )
        db.add(snapshot)
        db.flush()

        run = StrategyRun(
            strategy_id=strategy.id,
            run_name=f"run-{uuid.uuid4().hex[:6]}",
            run_type="backtest",
            status="completed",
            dataset_snapshot_id=snapshot.id,
        )
        db.add(run)
        db.commit()

        try:
            resp = client.get(f"/api/strategies/{strategy.id}/run-history")
            assert resp.status_code == 200
            items = resp.json()["items"]
            assert len(items) == 1
            assert items[0]["has_dataset_evidence"] is True
            assert items[0]["dataset_evidence"] is not None
        finally:
            db.delete(run)
            db.flush()
            db.delete(snapshot)
            db.flush()
            db.delete(dataset)
            db.flush()
            db.delete(strategy)
            db.commit()

    def test_no_dataset_evidence_when_not_linked(self, client, db):
        org = _get_seeded_org(db)
        project = _get_seeded_project(db)
        strategy = _make_strategy(db, org, project)
        run = _make_run(db, strategy)
        db.commit()

        try:
            resp = client.get(f"/api/strategies/{strategy.id}/run-history")
            assert resp.status_code == 200
            items = resp.json()["items"]
            assert len(items) == 1
            assert items[0]["has_dataset_evidence"] is False
            assert items[0]["dataset_evidence"] is None
        finally:
            db.delete(run)
            db.flush()
            db.delete(strategy)
            db.commit()

    def test_has_backtest_audit_when_present(self, client, db):
        org = _get_seeded_org(db)
        project = _get_seeded_project(db)
        strategy = _make_strategy(db, org, project)
        run = _make_run(db, strategy)

        audit = BacktestAudit(
            strategy_run_id=run.id,
            trust_score=85,
            overall_status="good",
            summary="Test audit",
        )
        db.add(audit)
        db.commit()

        try:
            resp = client.get(f"/api/strategies/{strategy.id}/run-history")
            assert resp.status_code == 200
            items = resp.json()["items"]
            assert len(items) == 1
            assert items[0]["has_backtest_audit"] is True
            assert items[0]["backtest_audit"] is not None
            assert items[0]["backtest_audit"]["trust_score"] == 85
        finally:
            db.delete(audit)
            db.flush()
            db.delete(run)
            db.flush()
            db.delete(strategy)
            db.commit()

    def test_health_label_insufficient_nothing(self, client, db):
        org = _get_seeded_org(db)
        project = _get_seeded_project(db)
        strategy = _make_strategy(db, org, project)
        run = _make_run(db, strategy)
        db.commit()

        try:
            resp = client.get(f"/api/strategies/{strategy.id}/run-history")
            assert resp.status_code == 200
            items = resp.json()["items"]
            assert len(items) == 1
            # No evidence at all -> insufficient_evidence
            assert items[0]["run_health_label"] == "insufficient_evidence"
        finally:
            db.delete(run)
            db.flush()
            db.delete(strategy)
            db.commit()

    def test_health_label_review_missing_major(self, client, db):
        """A run with a strategy_version but no dataset and no audit -> review."""
        org = _get_seeded_org(db)
        project = _get_seeded_project(db)
        strategy = _make_strategy(db, org, project)

        version = StrategyVersion(
            strategy_id=strategy.id,
            version_label=f"v-{uuid.uuid4().hex[:6]}",
        )
        db.add(version)
        db.flush()

        run = StrategyRun(
            strategy_id=strategy.id,
            run_name=f"run-{uuid.uuid4().hex[:6]}",
            run_type="backtest",
            status="completed",
            strategy_version_id=version.id,
        )
        db.add(run)
        db.commit()

        try:
            resp = client.get(f"/api/strategies/{strategy.id}/run-history")
            assert resp.status_code == 200
            items = resp.json()["items"]
            assert len(items) == 1
            # Has version but no dataset and no audit -> review
            assert items[0]["run_health_label"] == "review"
        finally:
            db.delete(run)
            db.flush()
            db.delete(version)
            db.flush()
            db.delete(strategy)
            db.commit()

    def test_health_label_weak_low_trust(self, client, db):
        """Run with audit trust_score=40 -> weak."""
        org = _get_seeded_org(db)
        project = _get_seeded_project(db)
        strategy = _make_strategy(db, org, project)
        run = _make_run(db, strategy)

        audit = BacktestAudit(
            strategy_run_id=run.id,
            trust_score=40,
            overall_status="poor",
            summary="Low trust",
        )
        db.add(audit)
        db.commit()

        try:
            resp = client.get(f"/api/strategies/{strategy.id}/run-history")
            assert resp.status_code == 200
            items = resp.json()["items"]
            assert len(items) == 1
            assert items[0]["run_health_label"] == "weak"
        finally:
            db.delete(audit)
            db.flush()
            db.delete(run)
            db.flush()
            db.delete(strategy)
            db.commit()


# ---------------------------------------------------------------------------
# TestTimelineDrilldown
# ---------------------------------------------------------------------------


class TestTimelineDrilldown:
    """Integration tests for timeline drilldown endpoint."""

    def _make_event(self, db, org, project, strategy, *, event_type="strategy_run_logged", source_type="strategy_run"):
        e = AuditTimelineEvent(
            organization_id=org.id,
            project_id=project.id,
            strategy_id=strategy.id,
            event_type=event_type,
            title=f"Test event {event_type}",
            description="Test description",
            source_type=source_type,
            source_id=str(uuid.uuid4()),
            severity="info",
            event_time=datetime.now(timezone.utc),
        )
        db.add(e)
        db.flush()
        return e

    def test_drilldown_200(self, client, db):
        org = _get_seeded_org(db)
        project = _get_seeded_project(db)
        strategy = _make_strategy(db, org, project)
        ev = self._make_event(db, org, project, strategy)
        db.commit()

        try:
            resp = client.get(f"/api/strategies/{strategy.id}/timeline/drilldown")
            assert resp.status_code == 200
        finally:
            db.delete(ev)
            db.flush()
            db.delete(strategy)
            db.commit()

    def test_drilldown_response_fields(self, client, db):
        org = _get_seeded_org(db)
        project = _get_seeded_project(db)
        strategy = _make_strategy(db, org, project)
        ev = self._make_event(db, org, project, strategy)
        db.commit()

        try:
            resp = client.get(f"/api/strategies/{strategy.id}/timeline/drilldown")
            assert resp.status_code == 200
            data = resp.json()
            assert "items" in data
            assert "total" in data
            assert "summary" in data
            summary = data["summary"]
            assert "event_type_counts" in summary
            assert "total_events" in summary
        finally:
            db.delete(ev)
            db.flush()
            db.delete(strategy)
            db.commit()

    def test_drilldown_evidence_category(self, client, db):
        org = _get_seeded_org(db)
        project = _get_seeded_project(db)
        strategy = _make_strategy(db, org, project)
        ev = self._make_event(db, org, project, strategy, event_type="strategy_run_logged")
        db.commit()

        try:
            resp = client.get(f"/api/strategies/{strategy.id}/timeline/drilldown")
            assert resp.status_code == 200
            data = resp.json()
            items = data["items"]
            assert len(items) >= 1
            # Find our event
            match = [i for i in items if i["event_type"] == "strategy_run_logged"]
            assert len(match) >= 1
            assert match[0]["evidence_category"] == "run"
        finally:
            db.delete(ev)
            db.flush()
            db.delete(strategy)
            db.commit()

    def test_drilldown_source_label(self, client, db):
        org = _get_seeded_org(db)
        project = _get_seeded_project(db)
        strategy = _make_strategy(db, org, project)
        ev = self._make_event(db, org, project, strategy, source_type="strategy_run")
        db.commit()

        try:
            resp = client.get(f"/api/strategies/{strategy.id}/timeline/drilldown")
            assert resp.status_code == 200
            data = resp.json()
            items = data["items"]
            match = [i for i in items if i.get("source_type") == "strategy_run"]
            assert len(match) >= 1
            assert match[0]["source_label"] == "Strategy Run"
        finally:
            db.delete(ev)
            db.flush()
            db.delete(strategy)
            db.commit()

    def test_drilldown_filter_event_type(self, client, db):
        org = _get_seeded_org(db)
        project = _get_seeded_project(db)
        strategy = _make_strategy(db, org, project)
        ev1 = self._make_event(db, org, project, strategy, event_type="strategy_run_logged")
        ev2 = self._make_event(db, org, project, strategy, event_type="strategy_version_created", source_type="strategy_version")
        db.commit()

        try:
            resp = client.get(
                f"/api/strategies/{strategy.id}/timeline/drilldown?event_type=strategy_run_logged"
            )
            assert resp.status_code == 200
            data = resp.json()
            for item in data["items"]:
                assert item["event_type"] == "strategy_run_logged"
        finally:
            db.delete(ev1)
            db.delete(ev2)
            db.flush()
            db.delete(strategy)
            db.commit()

    def test_drilldown_filter_source_type(self, client, db):
        org = _get_seeded_org(db)
        project = _get_seeded_project(db)
        strategy = _make_strategy(db, org, project)
        ev1 = self._make_event(db, org, project, strategy, source_type="strategy_run")
        ev2 = self._make_event(db, org, project, strategy, event_type="backtest_audit_computed", source_type="backtest_audit")
        db.commit()

        try:
            resp = client.get(
                f"/api/strategies/{strategy.id}/timeline/drilldown?source_type=strategy_run"
            )
            assert resp.status_code == 200
            data = resp.json()
            for item in data["items"]:
                assert item["source_type"] == "strategy_run"
        finally:
            db.delete(ev1)
            db.delete(ev2)
            db.flush()
            db.delete(strategy)
            db.commit()
