"""M22 tests: Evidence Ingestion Bundle.

Tests for:
  - POST /api/strategies/{strategy_id}/evidence-bundles
  - GET  /api/strategies/{strategy_id}/evidence-bundles/example
  - Service-level unit tests for ingest_evidence_bundle()
  - Section reuse logic (version, dataset)
  - Actions (audit, reliability score, report)
  - Validation errors
  - Response schema completeness
  - Bundle-level timeline event
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from app.models.alert import Alert
from app.models.audit_timeline_event import AuditTimelineEvent
from app.models.backtest_audit import BacktestAudit
from app.models.dataset import Dataset
from app.models.dataset_snapshot import DatasetSnapshot
from app.models.organization import Organization
from app.models.project import Project
from app.models.report import Report
from app.models.signal_snapshot import SignalSnapshot
from app.models.strategy import Strategy
from app.models.strategy_config_snapshot import StrategyConfigSnapshot
from app.models.strategy_reliability_score import StrategyReliabilityScore
from app.models.strategy_run import StrategyRun
from app.models.strategy_version import StrategyVersion
from app.models.universe_snapshot import UniverseSnapshot
from app.services.evidence_ingestion import ingest_evidence_bundle
from app.schemas.evidence_ingestion import EvidenceBundleRequest


# ---------------------------------------------------------------------------
# Helpers (same pattern as test_evidence_m21.py)
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


def _cleanup(db, strategy):
    """Delete a strategy (cascades to runs, versions, snapshots, etc.)."""
    from sqlalchemy import inspect as sa_inspect
    state = sa_inspect(strategy)
    if state.detached or state.deleted:
        # Reload a fresh reference
        from app.models.strategy import Strategy as _S
        fresh = db.query(_S).filter(_S.id == strategy.id).first()
        if fresh is not None:
            db.delete(fresh)
            db.commit()
        return
    if not state.transient:
        try:
            db.delete(strategy)
            db.commit()
        except Exception:
            db.rollback()


def _get_org_project(db):
    org = db.query(Organization).first()
    project = db.query(Project).filter(Project.organization_id == org.id).first()
    return org, project


_MINIMAL_RUN_PAYLOAD = {
    "strategy_run": {
        "run_name": "test-run-minimal",
        "run_type": "backtest",
        "status": "completed",
        "params_json": {"lookback": 10},
        "assumptions_json": {"transaction_cost_bps": 5},
        "metrics_json": {"sharpe": 1.2, "num_trades": 50},
    }
}

_FULL_BUNDLE_PAYLOAD = {
    "strategy_version": {
        "version_label": "v1.0.0",
        "git_commit": "deadbeef",
        "branch_name": "main",
    },
    "config_snapshot": {
        "label": "config-v1",
        "source_type": "manual_json",
        "config_json": {
            "params": {"lookback": 20, "entry_z": 2.0},
            "assumptions": {"transaction_cost_bps": 5, "fill_model": "next_open"},
        },
    },
    "universe_snapshot": {
        "label": "universe-test",
        "symbols": ["AAPL", "MSFT", "GOOGL"],
    },
    "signal_snapshot": {
        "label": "signals-test",
        "signal_column": "signal",
        "rows": [
            {"symbol": "AAPL", "timestamp": "2024-01-02", "signal": 1.5},
            {"symbol": "MSFT", "timestamp": "2024-01-02", "signal": -0.8},
        ],
    },
    "dataset": {
        "name": "Test Dataset M22",
        "description": "Dataset for M22 tests",
        "dataset_type": "equity_prices",
        "source_type": "csv_upload",
    },
    "dataset_snapshot": {
        "snapshot_label": "snap-v1",
        "rows": [
            {
                "symbol": "AAPL",
                "timestamp": "2024-01-02",
                "open": 185.0,
                "high": 188.0,
                "low": 184.5,
                "close": 187.2,
                "volume": 50000000,
            },
        ],
    },
    "strategy_run": {
        "run_name": "backtest-full",
        "run_type": "backtest",
        "status": "completed",
        "params_json": {"lookback": 20},
        "assumptions_json": {"transaction_cost_bps": 5, "fill_model": "next_open"},
        "metrics_json": {"sharpe": 1.4, "num_trades": 100},
    },
    "actions": {
        "run_backtest_audit": False,
        "compute_reliability_score": False,
        "generate_strategy_report": False,
        "generate_alerts": False,
    },
}


# ---------------------------------------------------------------------------
# 1. Minimal bundle — only strategy_run
# ---------------------------------------------------------------------------


class TestEvidenceBundleMinimal:
    def test_post_minimal_bundle_returns_201(self, client, db):
        org, project = _get_org_project(db)
        strategy = _make_strategy(db, org, project)
        try:
            payload = dict(_MINIMAL_RUN_PAYLOAD)
            resp = client.post(
                f"/api/strategies/{strategy.id}/evidence-bundles",
                json=payload,
            )
            assert resp.status_code == 201, resp.text
            data = resp.json()
            assert data["created_count"] >= 1
            assert "strategy_run" in data["objects"]
            assert data["objects"]["strategy_run"]["status"] == "created"
        finally:
            _cleanup(db, strategy)

    def test_post_minimal_bundle_creates_run_in_db(self, client, db):
        org, project = _get_org_project(db)
        strategy = _make_strategy(db, org, project)
        try:
            payload = dict(_MINIMAL_RUN_PAYLOAD)
            resp = client.post(
                f"/api/strategies/{strategy.id}/evidence-bundles",
                json=payload,
            )
            assert resp.status_code == 201
            data = resp.json()
            run_id = uuid.UUID(data["objects"]["strategy_run"]["id"])
            run = db.query(StrategyRun).filter(StrategyRun.id == run_id).first()
            assert run is not None
            assert run.run_name == "test-run-minimal"
        finally:
            _cleanup(db, strategy)

    def test_post_unknown_strategy_returns_404(self, client, db):
        resp = client.post(
            f"/api/strategies/{uuid.uuid4()}/evidence-bundles",
            json=_MINIMAL_RUN_PAYLOAD,
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 2. Version reuse
# ---------------------------------------------------------------------------


class TestEvidenceBundleVersionReuse:
    def test_version_reused_when_label_exists(self, client, db):
        org, project = _get_org_project(db)
        strategy = _make_strategy(db, org, project)
        try:
            # Create version first time
            payload = {
                "strategy_version": {
                    "version_label": "v2.0.0",
                    "git_commit": "abc123",
                }
            }
            resp1 = client.post(
                f"/api/strategies/{strategy.id}/evidence-bundles",
                json=payload,
            )
            assert resp1.status_code == 201
            assert resp1.json()["objects"]["strategy_version"]["status"] == "created"
            v1_id = resp1.json()["objects"]["strategy_version"]["id"]

            # Submit same label again → should reuse
            resp2 = client.post(
                f"/api/strategies/{strategy.id}/evidence-bundles",
                json=payload,
            )
            assert resp2.status_code == 201
            data2 = resp2.json()
            assert data2["objects"]["strategy_version"]["status"] == "reused"
            assert data2["objects"]["strategy_version"]["id"] == v1_id
            assert data2["reused_count"] >= 1
        finally:
            _cleanup(db, strategy)

    def test_version_created_when_new_label(self, client, db):
        org, project = _get_org_project(db)
        strategy = _make_strategy(db, org, project)
        try:
            resp = client.post(
                f"/api/strategies/{strategy.id}/evidence-bundles",
                json={"strategy_version": {"version_label": "v-unique-001"}},
            )
            assert resp.status_code == 201
            assert resp.json()["objects"]["strategy_version"]["status"] == "created"
            assert resp.json()["created_count"] >= 1
        finally:
            _cleanup(db, strategy)


# ---------------------------------------------------------------------------
# 3. Dataset reuse
# ---------------------------------------------------------------------------


class TestEvidenceBundleDatasetReuse:
    def test_dataset_reused_when_name_exists(self, client, db):
        org, project = _get_org_project(db)
        strategy = _make_strategy(db, org, project)
        try:
            payload = {
                "dataset": {
                    "name": f"Reuse Dataset {uuid.uuid4().hex[:6]}",
                    "dataset_type": "equity_prices",
                    "source_type": "csv_upload",
                }
            }
            resp1 = client.post(
                f"/api/strategies/{strategy.id}/evidence-bundles",
                json=payload,
            )
            assert resp1.status_code == 201
            d1_id = resp1.json()["objects"]["dataset"]["id"]
            assert resp1.json()["objects"]["dataset"]["status"] == "created"

            resp2 = client.post(
                f"/api/strategies/{strategy.id}/evidence-bundles",
                json=payload,
            )
            assert resp2.status_code == 201
            assert resp2.json()["objects"]["dataset"]["status"] == "reused"
            assert resp2.json()["objects"]["dataset"]["id"] == d1_id
        finally:
            _cleanup(db, strategy)

    def test_dataset_snapshot_skipped_without_dataset(self, client, db):
        org, project = _get_org_project(db)
        strategy = _make_strategy(db, org, project)
        try:
            payload = {
                "dataset_snapshot": {
                    "snapshot_label": "orphan-snap",
                    "rows": [
                        {
                            "symbol": "AAPL",
                            "timestamp": "2024-01-02",
                            "open": 185.0,
                            "high": 188.0,
                            "low": 184.5,
                            "close": 187.2,
                            "volume": 50000000,
                        }
                    ],
                }
            }
            resp = client.post(
                f"/api/strategies/{strategy.id}/evidence-bundles",
                json=payload,
            )
            assert resp.status_code == 201
            data = resp.json()
            # Should warn, not fail
            assert any("dataset_snapshot" in w for w in data["warnings"])
        finally:
            _cleanup(db, strategy)


# ---------------------------------------------------------------------------
# 4. Full bundle
# ---------------------------------------------------------------------------


class TestEvidenceBundleFullBundle:
    def test_full_bundle_creates_all_objects(self, client, db):
        org, project = _get_org_project(db)
        # Use unique names to avoid collisions
        suffix = uuid.uuid4().hex[:6]
        payload = {
            **_FULL_BUNDLE_PAYLOAD,
            "strategy_version": {
                "version_label": f"v-full-{suffix}",
            },
            "dataset": {
                "name": f"Full Bundle DS {suffix}",
                "dataset_type": "equity_prices",
                "source_type": "csv_upload",
            },
            "strategy_run": {
                "run_name": f"run-full-{suffix}",
                "run_type": "backtest",
                "status": "completed",
                "params_json": {"lookback": 20},
                "assumptions_json": {"transaction_cost_bps": 5},
                "metrics_json": {"sharpe": 1.4, "num_trades": 100},
            },
        }
        strategy = _make_strategy(db, org, project)
        try:
            resp = client.post(
                f"/api/strategies/{strategy.id}/evidence-bundles",
                json=payload,
            )
            assert resp.status_code == 201, resp.text
            data = resp.json()
            objs = data["objects"]
            assert "strategy_version" in objs
            assert "config_snapshot" in objs
            assert "universe_snapshot" in objs
            assert "signal_snapshot" in objs
            assert "dataset" in objs
            assert "dataset_snapshot" in objs
            assert "strategy_run" in objs
            # All should be created (unique names)
            for key, obj in objs.items():
                if obj is not None:
                    assert obj["status"] in ("created", "reused"), f"{key}: {obj}"
        finally:
            _cleanup(db, strategy)

    def test_full_bundle_links_run_to_snapshots(self, client, db):
        org, project = _get_org_project(db)
        suffix = uuid.uuid4().hex[:6]
        payload = {
            "universe_snapshot": {
                "label": f"univ-link-{suffix}",
                "symbols": ["AAPL", "MSFT"],
            },
            "strategy_run": {
                "run_name": f"run-linked-{suffix}",
                "run_type": "backtest",
                "status": "completed",
            },
        }
        strategy = _make_strategy(db, org, project)
        try:
            resp = client.post(
                f"/api/strategies/{strategy.id}/evidence-bundles",
                json=payload,
            )
            assert resp.status_code == 201
            data = resp.json()
            run_id = uuid.UUID(data["objects"]["strategy_run"]["id"])
            us_id = uuid.UUID(data["objects"]["universe_snapshot"]["id"])

            run = db.query(StrategyRun).filter(StrategyRun.id == run_id).first()
            assert run is not None
            assert run.universe_snapshot_id == us_id
        finally:
            _cleanup(db, strategy)


# ---------------------------------------------------------------------------
# 5. Actions
# ---------------------------------------------------------------------------


class TestEvidenceBundleActions:
    def test_run_backtest_audit_action(self, client, db):
        org, project = _get_org_project(db)
        strategy = _make_strategy(db, org, project)
        suffix = uuid.uuid4().hex[:6]
        try:
            payload = {
                "strategy_run": {
                    "run_name": f"run-audit-{suffix}",
                    "run_type": "backtest",
                    "status": "completed",
                    "params_json": {"lookback": 20},
                    "assumptions_json": {
                        "transaction_cost_bps": 5,
                        "fill_model": "next_open",
                    },
                    "metrics_json": {
                        "sharpe": 1.4,
                        "annual_return": 0.18,
                        "max_drawdown": -0.12,
                        "num_trades": 124,
                    },
                },
                "actions": {
                    "run_backtest_audit": True,
                    "compute_reliability_score": False,
                    "generate_strategy_report": False,
                    "generate_alerts": False,
                },
            }
            resp = client.post(
                f"/api/strategies/{strategy.id}/evidence-bundles",
                json=payload,
            )
            assert resp.status_code == 201, resp.text
            data = resp.json()
            assert "run_backtest_audit" in data["actions_run"]
            assert "backtest_audit" in data["objects"]
            assert data["objects"]["backtest_audit"] is not None
        finally:
            _cleanup(db, strategy)

    def test_compute_reliability_score_action(self, client, db):
        org, project = _get_org_project(db)
        strategy = _make_strategy(db, org, project)
        suffix = uuid.uuid4().hex[:6]
        try:
            payload = {
                "strategy_run": {
                    "run_name": f"run-rel-{suffix}",
                    "run_type": "backtest",
                    "status": "completed",
                },
                "actions": {
                    "run_backtest_audit": False,
                    "compute_reliability_score": True,
                    "generate_strategy_report": False,
                    "generate_alerts": False,
                },
            }
            resp = client.post(
                f"/api/strategies/{strategy.id}/evidence-bundles",
                json=payload,
            )
            assert resp.status_code == 201, resp.text
            data = resp.json()
            assert "compute_reliability_score" in data["actions_run"]
            assert "reliability_score" in data["objects"]
            assert data["objects"]["reliability_score"] is not None
        finally:
            _cleanup(db, strategy)

    def test_generate_strategy_report_action(self, client, db):
        org, project = _get_org_project(db)
        strategy = _make_strategy(db, org, project)
        suffix = uuid.uuid4().hex[:6]
        try:
            payload = {
                "strategy_run": {
                    "run_name": f"run-report-{suffix}",
                    "run_type": "backtest",
                    "status": "completed",
                },
                "actions": {
                    "run_backtest_audit": False,
                    "compute_reliability_score": False,
                    "generate_strategy_report": True,
                    "generate_alerts": False,
                },
            }
            resp = client.post(
                f"/api/strategies/{strategy.id}/evidence-bundles",
                json=payload,
            )
            assert resp.status_code == 201, resp.text
            data = resp.json()
            assert "generate_strategy_report" in data["actions_run"]
            assert "report" in data["objects"]
            assert data["objects"]["report"] is not None
        finally:
            _cleanup(db, strategy)


# ---------------------------------------------------------------------------
# 6. Validation
# ---------------------------------------------------------------------------


class TestEvidenceBundleValidation:
    def test_empty_bundle_returns_201_with_zero_counts(self, client, db):
        org, project = _get_org_project(db)
        strategy = _make_strategy(db, org, project)
        try:
            resp = client.post(
                f"/api/strategies/{strategy.id}/evidence-bundles",
                json={},
            )
            assert resp.status_code == 201
            data = resp.json()
            assert data["created_count"] == 0
            assert data["reused_count"] == 0
        finally:
            _cleanup(db, strategy)

    def test_missing_run_name_returns_422(self, client, db):
        org, project = _get_org_project(db)
        strategy = _make_strategy(db, org, project)
        try:
            payload = {
                "strategy_run": {
                    # run_name is required but missing
                    "run_type": "backtest",
                }
            }
            resp = client.post(
                f"/api/strategies/{strategy.id}/evidence-bundles",
                json=payload,
            )
            assert resp.status_code == 422
        finally:
            _cleanup(db, strategy)

    def test_empty_symbols_returns_422(self, client, db):
        org, project = _get_org_project(db)
        strategy = _make_strategy(db, org, project)
        try:
            payload = {
                "universe_snapshot": {
                    "label": "bad-universe",
                    "symbols": [],  # min_length=1
                }
            }
            resp = client.post(
                f"/api/strategies/{strategy.id}/evidence-bundles",
                json=payload,
            )
            assert resp.status_code == 422
        finally:
            _cleanup(db, strategy)

    def test_empty_signal_rows_returns_422(self, client, db):
        org, project = _get_org_project(db)
        strategy = _make_strategy(db, org, project)
        try:
            payload = {
                "signal_snapshot": {
                    "label": "bad-signals",
                    "rows": [],  # min_length=1
                }
            }
            resp = client.post(
                f"/api/strategies/{strategy.id}/evidence-bundles",
                json=payload,
            )
            assert resp.status_code == 422
        finally:
            _cleanup(db, strategy)


# ---------------------------------------------------------------------------
# 7. Response schema completeness
# ---------------------------------------------------------------------------


class TestEvidenceBundleResponse:
    def test_response_has_all_required_fields(self, client, db):
        org, project = _get_org_project(db)
        strategy = _make_strategy(db, org, project)
        try:
            resp = client.post(
                f"/api/strategies/{strategy.id}/evidence-bundles",
                json=_MINIMAL_RUN_PAYLOAD,
            )
            assert resp.status_code == 201
            data = resp.json()
            required_keys = [
                "strategy_id",
                "created_count",
                "reused_count",
                "actions_run",
                "objects",
                "alerts_generated",
                "warnings",
                "summary",
                "timeline_events_created",
                "generated_at",
            ]
            for key in required_keys:
                assert key in data, f"Missing key: {key}"
        finally:
            _cleanup(db, strategy)

    def test_object_ref_has_id_name_type_status(self, client, db):
        org, project = _get_org_project(db)
        strategy = _make_strategy(db, org, project)
        try:
            resp = client.post(
                f"/api/strategies/{strategy.id}/evidence-bundles",
                json=_MINIMAL_RUN_PAYLOAD,
            )
            assert resp.status_code == 201
            data = resp.json()
            obj = data["objects"]["strategy_run"]
            assert obj is not None
            assert "id" in obj
            assert "name" in obj
            assert "type" in obj
            assert "status" in obj
            assert obj["type"] == "strategy_run"
            assert obj["status"] == "created"
        finally:
            _cleanup(db, strategy)

    def test_strategy_id_in_response(self, client, db):
        org, project = _get_org_project(db)
        strategy = _make_strategy(db, org, project)
        try:
            resp = client.post(
                f"/api/strategies/{strategy.id}/evidence-bundles",
                json=_MINIMAL_RUN_PAYLOAD,
            )
            assert resp.status_code == 201
            data = resp.json()
            assert uuid.UUID(data["strategy_id"]) == strategy.id
        finally:
            _cleanup(db, strategy)

    def test_example_endpoint_returns_dict(self, client, db):
        org, project = _get_org_project(db)
        strategy = _make_strategy(db, org, project)
        try:
            resp = client.get(
                f"/api/strategies/{strategy.id}/evidence-bundles/example"
            )
            assert resp.status_code == 200
            data = resp.json()
            assert isinstance(data, dict)
            # Example should have at minimum strategy_run and actions
            assert "strategy_run" in data
            assert "actions" in data
        finally:
            _cleanup(db, strategy)


# ---------------------------------------------------------------------------
# 8. Timeline event
# ---------------------------------------------------------------------------


class TestEvidenceBundleTimeline:
    def test_bundle_event_created_in_timeline(self, client, db):
        org, project = _get_org_project(db)
        strategy = _make_strategy(db, org, project)
        try:
            # Count events before
            before = (
                db.query(AuditTimelineEvent)
                .filter(
                    AuditTimelineEvent.strategy_id == strategy.id,
                    AuditTimelineEvent.event_type == "evidence_bundle_ingested",
                )
                .count()
            )

            resp = client.post(
                f"/api/strategies/{strategy.id}/evidence-bundles",
                json=_MINIMAL_RUN_PAYLOAD,
            )
            assert resp.status_code == 201

            after = (
                db.query(AuditTimelineEvent)
                .filter(
                    AuditTimelineEvent.strategy_id == strategy.id,
                    AuditTimelineEvent.event_type == "evidence_bundle_ingested",
                )
                .count()
            )
            assert after == before + 1
        finally:
            _cleanup(db, strategy)

    def test_timeline_events_created_count_in_response(self, client, db):
        org, project = _get_org_project(db)
        strategy = _make_strategy(db, org, project)
        try:
            resp = client.post(
                f"/api/strategies/{strategy.id}/evidence-bundles",
                json=_MINIMAL_RUN_PAYLOAD,
            )
            assert resp.status_code == 201
            data = resp.json()
            # At minimum: 1 for strategy_run + 1 for bundle itself
            assert data["timeline_events_created"] >= 2
        finally:
            _cleanup(db, strategy)

    def test_summary_string_is_non_empty(self, client, db):
        org, project = _get_org_project(db)
        strategy = _make_strategy(db, org, project)
        try:
            resp = client.post(
                f"/api/strategies/{strategy.id}/evidence-bundles",
                json=_MINIMAL_RUN_PAYLOAD,
            )
            assert resp.status_code == 201
            assert resp.json()["summary"]  # non-empty string
        finally:
            _cleanup(db, strategy)
