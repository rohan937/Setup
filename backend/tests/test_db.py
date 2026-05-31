"""M2 database and API endpoint tests.

Tests cover:
- Schema creation (tables exist)
- Seed data loads correctly
- Seed is idempotent (re-running does not duplicate)
- All 5 read-only endpoints return expected data
- JSON fields round-trip correctly
"""

from __future__ import annotations

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.models.organization import Organization
from app.models.project import Project
from app.models.strategy import Strategy
from app.models.strategy_run import StrategyRun
from app.models.strategy_version import StrategyVersion
from app.models.audit_timeline_event import AuditTimelineEvent


# ---------------------------------------------------------------------------
# Schema / table existence
# ---------------------------------------------------------------------------

class TestSchema:
    EXPECTED_TABLES = [
        "organizations",
        "users",
        "projects",
        "strategies",
        "strategy_versions",
        "strategy_runs",
        "audit_timeline_events",
    ]

    def test_all_tables_exist(self, test_engine):
        inspector = inspect(test_engine)
        existing = inspector.get_table_names()
        for table in self.EXPECTED_TABLES:
            assert table in existing, f"Table '{table}' missing from schema"

    def test_organizations_columns(self, test_engine):
        inspector = inspect(test_engine)
        cols = {c["name"] for c in inspector.get_columns("organizations")}
        assert {"id", "name", "slug", "created_at", "updated_at"}.issubset(cols)

    def test_strategy_runs_json_columns(self, test_engine):
        inspector = inspect(test_engine)
        cols = {c["name"] for c in inspector.get_columns("strategy_runs")}
        assert {"params_json", "assumptions_json", "metrics_json"}.issubset(cols)

    def test_audit_timeline_events_columns(self, test_engine):
        inspector = inspect(test_engine)
        cols = {c["name"] for c in inspector.get_columns("audit_timeline_events")}
        assert {"event_type", "title", "severity", "event_time", "metadata_json"}.issubset(cols)


# ---------------------------------------------------------------------------
# Seed data correctness
# ---------------------------------------------------------------------------

class TestSeedData:
    def test_organization_created(self, db: Session):
        org = db.query(Organization).filter_by(slug="quantfidelity-demo").first()
        assert org is not None
        assert org.name == "QuantFidelity Demo"

    def test_project_created(self, db: Session):
        project = db.query(Project).filter_by(slug="alpha-reliability-lab").first()
        assert project is not None
        assert project.name == "Alpha Reliability Lab"

    def test_strategy_created(self, db: Session):
        strategy = db.query(Strategy).filter_by(
            slug="aapl-mean-reversion-v1"
        ).first()
        assert strategy is not None
        assert strategy.name == "AAPL Mean Reversion v1"
        assert strategy.asset_class == "equity"
        assert strategy.status == "active"

    def test_strategy_version_created(self, db: Session):
        strategy = db.query(Strategy).filter_by(
            slug="aapl-mean-reversion-v1"
        ).first()
        assert strategy is not None
        version = (
            db.query(StrategyVersion)
            .filter_by(strategy_id=strategy.id, version_label="v1.0")
            .first()
        )
        assert version is not None
        assert version.signal_name == "return_zscore_mean_reversion"

    def test_strategy_run_created(self, db: Session):
        strategy = db.query(Strategy).filter_by(
            slug="aapl-mean-reversion-v1"
        ).first()
        assert strategy is not None
        run = (
            db.query(StrategyRun)
            .filter_by(strategy_id=strategy.id, run_name="Baseline Backtest Run")
            .first()
        )
        assert run is not None
        assert run.run_type == "backtest"
        assert run.status == "completed"

    def test_json_fields_round_trip(self, db: Session):
        strategy = db.query(Strategy).filter_by(
            slug="aapl-mean-reversion-v1"
        ).first()
        assert strategy is not None
        run = db.query(StrategyRun).filter_by(strategy_id=strategy.id).first()
        assert run is not None
        assert run.params_json == {"lookback_days": 20, "zscore_entry": 2.0}
        assert run.assumptions_json == {
            "transaction_cost_bps": 5,
            "fill_model": "mid_plus_5bps",
        }
        assert run.metrics_json == {
            "sharpe": 1.6,
            "turnover": 0.42,
            "max_drawdown": 0.11,
        }

    def test_timeline_events_created(self, db: Session):
        events = db.query(AuditTimelineEvent).all()
        assert len(events) >= 2
        titles = [e.title for e in events]
        assert any("Strategy created" in t for t in titles)
        assert any("Baseline run logged" in t for t in titles)


# ---------------------------------------------------------------------------
# Seed idempotency
# ---------------------------------------------------------------------------

class TestSeedIdempotency:
    def test_second_seed_does_not_duplicate(self, db: Session):
        """Running seed twice must not create duplicate records."""
        from app.services.seed import run_seed

        before_orgs = db.query(Organization).count()
        before_projects = db.query(Project).count()
        before_strategies = db.query(Strategy).count()
        before_runs = db.query(StrategyRun).count()

        run_seed(db)

        assert db.query(Organization).count() == before_orgs
        assert db.query(Project).count() == before_projects
        assert db.query(Strategy).count() == before_strategies
        assert db.query(StrategyRun).count() == before_runs


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------

class TestApiProjects:
    def test_get_projects_returns_200(self, client):
        resp = client.get("/api/projects")
        assert resp.status_code == 200

    def test_get_projects_returns_list(self, client):
        resp = client.get("/api/projects")
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_project_has_expected_fields(self, client):
        data = client.get("/api/projects").json()
        project = data[0]
        assert "id" in project
        assert "name" in project
        assert "slug" in project
        assert project["name"] == "Alpha Reliability Lab"


class TestApiStrategies:
    def test_get_strategies_returns_200(self, client):
        resp = client.get("/api/strategies")
        assert resp.status_code == 200

    def test_get_strategies_returns_list(self, client):
        data = client.get("/api/strategies").json()
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_strategy_has_expected_fields(self, client):
        data = client.get("/api/strategies").json()
        s = data[0]
        assert s["name"] == "AAPL Mean Reversion v1"
        assert s["asset_class"] == "equity"
        assert s["status"] == "active"

    def test_get_strategy_by_id(self, client):
        strategies = client.get("/api/strategies").json()
        sid = strategies[0]["id"]
        resp = client.get(f"/api/strategies/{sid}")
        assert resp.status_code == 200
        detail = resp.json()
        assert detail["id"] == sid
        assert "versions" in detail
        assert len(detail["versions"]) >= 1

    def test_strategy_version_signal_fields(self, client):
        strategies = client.get("/api/strategies").json()
        sid = strategies[0]["id"]
        detail = client.get(f"/api/strategies/{sid}").json()
        v = detail["versions"][0]
        assert v["version_label"] == "v1.0"
        assert v["signal_name"] == "return_zscore_mean_reversion"

    def test_get_strategy_not_found(self, client):
        import uuid
        resp = client.get(f"/api/strategies/{uuid.uuid4()}")
        assert resp.status_code == 404

    def test_get_strategy_runs(self, client):
        strategies = client.get("/api/strategies").json()
        sid = strategies[0]["id"]
        resp = client.get(f"/api/strategies/{sid}/runs")
        assert resp.status_code == 200
        runs = resp.json()
        assert isinstance(runs, list)
        assert len(runs) >= 1

    def test_run_json_fields_in_response(self, client):
        strategies = client.get("/api/strategies").json()
        sid = strategies[0]["id"]
        runs = client.get(f"/api/strategies/{sid}/runs").json()
        run = runs[0]
        assert run["run_type"] == "backtest"
        assert run["status"] == "completed"
        assert run["params_json"]["lookback_days"] == 20
        assert run["metrics_json"]["sharpe"] == 1.6

    def test_runs_for_missing_strategy_returns_404(self, client):
        import uuid
        resp = client.get(f"/api/strategies/{uuid.uuid4()}/runs")
        assert resp.status_code == 404


class TestApiTimeline:
    def test_get_timeline_returns_200(self, client):
        resp = client.get("/api/timeline")
        assert resp.status_code == 200

    def test_get_timeline_returns_paginated_response(self, client):
        data = client.get("/api/timeline").json()
        # M10: response is now a paginated envelope, not a bare list.
        assert "items" in data
        assert "total" in data
        assert "limit" in data
        assert "offset" in data
        assert isinstance(data["items"], list)
        assert len(data["items"]) >= 2

    def test_timeline_event_has_expected_fields(self, client):
        events = client.get("/api/timeline").json()["items"]
        e = events[0]
        assert "event_type" in e
        assert "title" in e
        assert "severity" in e
        assert "event_time" in e

    def test_timeline_limit_param(self, client):
        resp = client.get("/api/timeline?limit=1")
        assert resp.status_code == 200
        assert len(resp.json()["items"]) <= 1
