"""Tests for clean_realistic_demo seed mode.

Verifies:
  - clean_realistic_demo endpoint returns 200 and creates exactly 3 strategies
  - Artifacts exist: runs, snapshots, audits, reliability scores, alerts, review cases
  - AAPL is healthy/well-instrumented state
  - Global Futures Trend Model is review state (missing paper/shadow validation)
  - Crypto is weak/under-instrumented state
  - Dashboard summary shows reasonable (not thousands) of records
  - Seed is idempotent: running extend twice does not duplicate strategies
  - No test-looking strategy names (M13*, CostScenarios*, etc.)
  - Auth/RBAC still protects seed endpoint
  - Mode validation: confirm_reset required for clean_realistic_demo
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.organization import Organization
from app.models.project import Project
from app.models.strategy import Strategy
from app.services.demo_seed import (
    DEMO_ORG_NAME,
    DEMO_PROJECT_NAME,
    DEMO_STRATEGIES,
    seed_demo_data,
    get_demo_status,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_SEED_DB_URL = "sqlite+pysqlite:///:memory:"


@pytest.fixture()
def seed_engine():
    engine = create_engine(
        _SEED_DB_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture()
def seed_db(seed_engine):
    session = Session(seed_engine)
    yield session
    session.close()


@pytest.fixture()
def seed_client(seed_db):
    def _override():
        yield seed_db

    app.dependency_overrides[get_db] = _override
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.pop(get_db, None)


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _seed_clean(db: Session, **kwargs) -> dict:
    """Helper: run clean_realistic_demo mode in-process (no HTTP overhead)."""
    return seed_demo_data(
        db,
        mode="clean_realistic_demo",
        confirm_reset=True,
        include_reports=False,
        include_alerts=True,
        include_backtest_audits=True,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Service-level tests (in-process, no HTTP)
# ---------------------------------------------------------------------------


class TestCleanRealisticDemoService:
    def test_requires_confirm_reset(self, seed_db):
        with pytest.raises(ValueError, match="confirm_reset"):
            seed_demo_data(seed_db, mode="clean_realistic_demo", confirm_reset=False)

    def test_creates_demo_org_with_correct_name(self, seed_db):
        _seed_clean(seed_db)
        org = seed_db.query(Organization).filter(Organization.name == DEMO_ORG_NAME).first()
        assert org is not None, f"Expected org '{DEMO_ORG_NAME}'"

    def test_creates_demo_project_with_correct_name(self, seed_db):
        _seed_clean(seed_db)
        org = seed_db.query(Organization).filter(Organization.name == DEMO_ORG_NAME).first()
        proj = seed_db.query(Project).filter(Project.organization_id == org.id).first()
        assert proj is not None
        assert proj.name == DEMO_PROJECT_NAME

    def test_creates_exactly_3_strategies(self, seed_db):
        result = _seed_clean(seed_db)
        assert len(result["strategy_ids"]) == 3
        strats = seed_db.query(Strategy).all()
        assert len(strats) == 3

    def test_strategy_names_match_spec(self, seed_db):
        _seed_clean(seed_db)
        names = {s.name for s in seed_db.query(Strategy).all()}
        for spec in DEMO_STRATEGIES:
            assert spec["name"] in names, f"'{spec['name']}' not in DB"

    def test_no_test_artifact_names(self, seed_db):
        _seed_clean(seed_db)
        strats = seed_db.query(Strategy).all()
        forbidden = {"M13", "M18", "CostScenarios", "CostDecreases", "SharpeDecreases",
                     "HighFrag", "MedFrag", "FRMissing", "ZeroSharpe", "FRKeys",
                     "SameBar", "AssumedBps"}
        for s in strats:
            for bad in forbidden:
                assert not s.name.startswith(bad), f"Test artifact name found: {s.name!r}"

    def test_run_count_is_small(self, seed_db):
        _seed_clean(seed_db)
        from app.models.strategy_run import StrategyRun
        count = seed_db.query(StrategyRun).count()
        assert count <= 10, f"Expected ≤10 runs, got {count}"
        assert count >= 3, f"Expected ≥3 runs, got {count}"

    def test_snapshot_counts_are_small(self, seed_db):
        _seed_clean(seed_db)
        from app.models.dataset_snapshot import DatasetSnapshot
        from app.models.signal_snapshot import SignalSnapshot
        from app.models.universe_snapshot import UniverseSnapshot
        from app.models.strategy_config_snapshot import StrategyConfigSnapshot

        assert seed_db.query(DatasetSnapshot).count() <= 6
        assert seed_db.query(SignalSnapshot).count() <= 6
        assert seed_db.query(UniverseSnapshot).count() <= 6
        assert seed_db.query(StrategyConfigSnapshot).count() <= 8

    def test_no_warnings(self, seed_db):
        result = _seed_clean(seed_db)
        assert not result["warnings"], f"Unexpected warnings: {result['warnings']}"

    def test_returns_all_3_strategy_ids(self, seed_db):
        result = _seed_clean(seed_db)
        assert len(result["strategy_ids"]) == 3
        for sid in result["strategy_ids"]:
            # Each ID should be a valid UUID string
            assert len(sid) in (32, 36), f"Unexpected ID format: {sid!r}"

    def test_result_has_workspace_and_project_id(self, seed_db):
        result = _seed_clean(seed_db)
        assert result["organization_id"] is not None
        assert result["project_id"] is not None


# ---------------------------------------------------------------------------
# Idempotency tests
# ---------------------------------------------------------------------------


class TestCleanDemoIdempotency:
    def test_extend_twice_does_not_double_strategies(self, seed_db):
        _seed_clean(seed_db)
        seed_data_extend = seed_demo_data(
            seed_db, mode="extend", include_reports=False,
            include_alerts=False, include_backtest_audits=False,
        )
        count = seed_db.query(Strategy).count()
        assert count == 3, f"Extend doubled strategies: found {count}"
        assert seed_data_extend["reused_counts"].get("strategies", 0) == 3

    def test_clean_twice_still_gives_3_strategies(self, seed_db):
        _seed_clean(seed_db)
        _seed_clean(seed_db)
        count = seed_db.query(Strategy).count()
        assert count == 3, f"Double clean gave {count} strategies"


# ---------------------------------------------------------------------------
# Strategy state tests
# ---------------------------------------------------------------------------


class TestDemoStrategyStates:
    def _get_strategy(self, db: Session, slug: str) -> Strategy:
        s = db.query(Strategy).filter(Strategy.slug == slug).first()
        assert s is not None, f"Strategy '{slug}' not found"
        return s

    def test_aapl_has_multiple_runs(self, seed_db):
        _seed_clean(seed_db)
        from app.models.strategy_run import StrategyRun
        s = self._get_strategy(seed_db, "aapl-mean-reversion-v1")
        runs = seed_db.query(StrategyRun).filter(StrategyRun.strategy_id == s.id).all()
        assert len(runs) >= 2, f"AAPL should have ≥2 runs, got {len(runs)}"

    def test_aapl_has_backtest_audit(self, seed_db):
        _seed_clean(seed_db)
        from app.models.strategy_run import StrategyRun
        from app.models.backtest_audit import BacktestAudit
        s = self._get_strategy(seed_db, "aapl-mean-reversion-v1")
        runs = seed_db.query(StrategyRun).filter(StrategyRun.strategy_id == s.id).all()
        audits = sum(1 for r in runs
                     if seed_db.query(BacktestAudit).filter(BacktestAudit.strategy_run_id == r.id).count() > 0)
        assert audits >= 1, "AAPL should have at least 1 backtest audit"

    def test_aapl_has_universe_snapshot(self, seed_db):
        _seed_clean(seed_db)
        from app.models.universe_snapshot import UniverseSnapshot
        s = self._get_strategy(seed_db, "aapl-mean-reversion-v1")
        u = seed_db.query(UniverseSnapshot).filter(UniverseSnapshot.strategy_id == s.id).first()
        assert u is not None
        assert "AAPL" in (u.symbols_json or []) or "aapl" in str(u.symbols_json or []).lower()

    def test_aapl_has_signal_snapshot(self, seed_db):
        _seed_clean(seed_db)
        from app.models.signal_snapshot import SignalSnapshot
        s = self._get_strategy(seed_db, "aapl-mean-reversion-v1")
        sig = seed_db.query(SignalSnapshot).filter(SignalSnapshot.strategy_id == s.id).first()
        assert sig is not None
        assert sig.signal_name == "mean_reversion_zscore"

    def test_aapl_has_reliability_score(self, seed_db):
        _seed_clean(seed_db)
        from app.models.strategy_reliability_score import StrategyReliabilityScore
        s = self._get_strategy(seed_db, "aapl-mean-reversion-v1")
        score = seed_db.query(StrategyReliabilityScore).filter(
            StrategyReliabilityScore.strategy_id == s.id
        ).first()
        assert score is not None

    def test_futures_has_trend_signal_label(self, seed_db):
        _seed_clean(seed_db)
        from app.models.signal_snapshot import SignalSnapshot
        s = self._get_strategy(seed_db, "global-futures-trend-model")
        sig = seed_db.query(SignalSnapshot).filter(SignalSnapshot.strategy_id == s.id).first()
        assert sig is not None
        assert "trend" in sig.label.lower() or "futures" in sig.label.lower()

    def test_futures_has_review_case(self, seed_db):
        _seed_clean(seed_db)
        from app.models.review_case import ResearchReviewCase
        s = self._get_strategy(seed_db, "global-futures-trend-model")
        rc = seed_db.query(ResearchReviewCase).filter(
            ResearchReviewCase.strategy_id == s.id.hex
        ).first()
        assert rc is not None
        assert "paper" in rc.title.lower() or "shadow" in rc.title.lower()

    def test_crypto_has_one_run(self, seed_db):
        _seed_clean(seed_db)
        from app.models.strategy_run import StrategyRun
        s = self._get_strategy(seed_db, "crypto-momentum-intraday")
        runs = seed_db.query(StrategyRun).filter(StrategyRun.strategy_id == s.id).all()
        assert len(runs) == 1

    def test_crypto_has_review_case(self, seed_db):
        _seed_clean(seed_db)
        from app.models.review_case import ResearchReviewCase
        s = self._get_strategy(seed_db, "crypto-momentum-intraday")
        rc = seed_db.query(ResearchReviewCase).filter(
            ResearchReviewCase.strategy_id == s.id.hex
        ).first()
        assert rc is not None
        assert "reliability" in rc.title.lower() or "backtest" in rc.title.lower()

    def test_crypto_run_has_zero_cost_assumptions(self, seed_db):
        _seed_clean(seed_db)
        from app.models.strategy_run import StrategyRun
        s = self._get_strategy(seed_db, "crypto-momentum-intraday")
        run = seed_db.query(StrategyRun).filter(StrategyRun.strategy_id == s.id).first()
        assert run is not None
        assumptions = run.assumptions_json or {}
        cost = assumptions.get("transaction_cost_bps", None)
        assert cost == 0 or cost is None, f"Crypto should have zero/missing cost, got {cost}"

    def test_crypto_run_has_inflated_sharpe(self, seed_db):
        _seed_clean(seed_db)
        from app.models.strategy_run import StrategyRun
        s = self._get_strategy(seed_db, "crypto-momentum-intraday")
        run = seed_db.query(StrategyRun).filter(StrategyRun.strategy_id == s.id).first()
        assert run is not None
        metrics = run.metrics_json or {}
        sharpe = metrics.get("sharpe", 0)
        assert sharpe is not None and sharpe > 2.0, f"Crypto Sharpe should be inflated (>2.0), got {sharpe}"


# ---------------------------------------------------------------------------
# HTTP endpoint tests (via TestClient)
# ---------------------------------------------------------------------------


class TestCleanDemoEndpoint:
    """HTTP endpoint tests.

    These use the no-auth path (pseudo-owner permissive mode for local-dev)
    so they don't depend on the workspace_member/org setup that auth tests need.
    RBAC protection is verified separately in TestRBACProtection.
    """

    def test_seed_endpoint_returns_200(self, seed_client):
        resp = seed_client.post(
            "/api/admin/seed-demo",
            json={"mode": "clean_realistic_demo", "confirm_reset": True,
                  "include_reports": False, "include_alerts": True, "include_backtest_audits": True},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert len(data["strategy_ids"]) == 3

    def test_seed_response_has_expected_structure(self, seed_client):
        resp = seed_client.post(
            "/api/admin/seed-demo",
            json={"mode": "clean_realistic_demo", "confirm_reset": True,
                  "include_reports": False, "include_alerts": False, "include_backtest_audits": False},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["mode"] == "clean_realistic_demo"
        assert data["organization_id"] is not None
        assert data["project_id"] is not None
        assert len(data["strategy_ids"]) == 3
        assert not data["warnings"], f"Unexpected warnings: {data['warnings']}"

    def test_demo_status_after_seed(self, seed_client):
        seed_client.post(
            "/api/admin/seed-demo",
            json={"mode": "clean_realistic_demo", "confirm_reset": True,
                  "include_reports": False, "include_alerts": False, "include_backtest_audits": False},
        )
        resp = seed_client.get("/api/admin/demo-status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["demo_org_exists"] is True
        assert data["strategy_count"] == 3

    def test_extend_mode_does_not_double_strategies(self, seed_client):
        seed_client.post(
            "/api/admin/seed-demo",
            json={"mode": "clean_realistic_demo", "confirm_reset": True,
                  "include_reports": False, "include_alerts": False, "include_backtest_audits": False},
        )
        seed_client.post(
            "/api/admin/seed-demo",
            json={"mode": "extend", "include_reports": False,
                  "include_alerts": False, "include_backtest_audits": False},
        )
        status = seed_client.get("/api/admin/demo-status").json()
        assert status["strategy_count"] == 3, f"After extend, expected 3, got {status['strategy_count']}"

    def test_missing_confirm_reset_returns_400(self, seed_client):
        resp = seed_client.post(
            "/api/admin/seed-demo",
            json={"mode": "clean_realistic_demo", "confirm_reset": False,
                  "include_reports": False},
        )
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"


class TestRBACProtection:
    """RBAC: viewer-role users cannot access the seed endpoint."""

    @pytest.fixture()
    def rbac_engine(self):
        from sqlalchemy import create_engine, event as sa_event
        from sqlalchemy.pool import StaticPool
        engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        yield engine
        Base.metadata.drop_all(engine)
        engine.dispose()

    @pytest.fixture()
    def rbac_db(self, rbac_engine):
        s = Session(rbac_engine)
        yield s
        s.close()

    @pytest.fixture()
    def rbac_org(self, rbac_db):
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        org = Organization(name="RBAC Test Org", slug="rbac-test-org", created_at=now, updated_at=now)
        rbac_db.add(org)
        rbac_db.commit()
        rbac_db.refresh(org)
        return org

    @pytest.fixture()
    def rbac_client(self, rbac_db, rbac_org):  # noqa: ARG001
        def _override():
            yield rbac_db
        app.dependency_overrides[get_db] = _override
        with TestClient(app, raise_server_exceptions=True) as c:
            yield c
        app.dependency_overrides.pop(get_db, None)

    def _make_user(self, client: TestClient, db: Session, role: str) -> str:
        email = f"{role}-{uuid.uuid4().hex[:8]}@test.com"
        resp = client.post(
            "/api/auth/register",
            json={"email": email, "display_name": role, "password": "password123"},
        )
        assert resp.status_code == 200, resp.text
        # Force the role
        from app.models.workspace_member import WorkspaceMember
        member = db.query(WorkspaceMember).filter(WorkspaceMember.email == email).first()
        if member:
            member.role = role
            db.commit()
        return resp.json()["access_token"]

    def test_viewer_cannot_seed(self, rbac_client, rbac_db):
        token = self._make_user(rbac_client, rbac_db, "viewer")
        resp = rbac_client.post(
            "/api/admin/seed-demo",
            json={"mode": "clean_realistic_demo", "confirm_reset": True,
                  "include_reports": False},
            headers=_auth(token),
        )
        assert resp.status_code == 403, f"Expected 403 for viewer, got {resp.status_code}"

    def test_admin_can_seed(self, rbac_client, rbac_db):
        token = self._make_user(rbac_client, rbac_db, "admin")
        resp = rbac_client.post(
            "/api/admin/seed-demo",
            json={"mode": "clean_realistic_demo", "confirm_reset": True,
                  "include_reports": False, "include_alerts": False, "include_backtest_audits": False},
            headers=_auth(token),
        )
        assert resp.status_code == 200, resp.text


# ---------------------------------------------------------------------------
# Dashboard summary sanity check
# ---------------------------------------------------------------------------


class TestDashboardAfterCleanSeed:
    def test_dashboard_shows_reasonable_strategy_count(self, seed_client):
        seed_client.post(
            "/api/admin/seed-demo",
            json={"mode": "clean_realistic_demo", "confirm_reset": True,
                  "include_reports": False, "include_alerts": True, "include_backtest_audits": True},
        )
        resp = seed_client.get("/api/dashboard/summary")
        assert resp.status_code == 200
        data = resp.json()
        counts = data.get("counts", {})
        total_strats = counts.get("total_strategies", 0)
        total_runs = counts.get("total_runs", 0)
        assert total_strats == 3, f"Expected 3 strategies on dashboard, got {total_strats}"
        assert total_runs <= 10, f"Expected ≤10 runs on dashboard, got {total_runs}"
        assert total_runs >= 3, f"Expected ≥3 runs on dashboard, got {total_runs}"
