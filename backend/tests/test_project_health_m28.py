"""M28 tests: Project Health Service, Endpoints, and Scoped API Key Enforcement.

Tests for:
  - GET /api/projects/{id}/health
  - GET /api/projects/health (list)
  - ProjectHealthSnapshot aggregation logic
  - Project-scoped API key enforcement on POST evidence-bundles
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from app.models.alert import Alert
from app.models.api_key import ApiKey
from app.models.organization import Organization
from app.models.project import Project
from app.models.strategy import Strategy
from app.services.api_keys import generate_api_key, hash_api_key


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


def _cleanup_strategy(db, strategy):
    from sqlalchemy import inspect as sa_inspect
    state = sa_inspect(strategy)
    if state.detached or state.deleted:
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


def _cleanup_key(db, key_id):
    if isinstance(key_id, str):
        key_id = uuid.UUID(key_id)
    key = db.query(ApiKey).filter(ApiKey.id == key_id).first()
    if key is not None:
        db.delete(key)
        db.commit()


def _get_org_project(db):
    org = db.query(Organization).first()
    project = db.query(Project).filter(Project.organization_id == org.id).first()
    return org, project


def _make_api_key(db, org, *, project_id=None, scopes=None, name=None):
    """Create an API key in the DB and return (key_obj, raw_key)."""
    from app.core.config import get_settings
    settings = get_settings()
    raw_key, key_prefix = generate_api_key(env=settings.qf_api_key_env)
    key_hash = hash_api_key(raw_key, settings.qf_api_key_hash_secret)
    key = ApiKey(
        organization_id=str(org.id),
        project_id=str(project_id) if project_id is not None else None,
        name=name or f"test-key-{uuid.uuid4().hex[:6]}",
        key_prefix=key_prefix,
        key_hash=key_hash,
        scopes_json=scopes if scopes is not None else ["evidence:write"],
        status="active",
    )
    db.add(key)
    db.commit()
    db.refresh(key)
    return key, raw_key


_MINIMAL_BUNDLE = {
    "strategy_run": {
        "run_name": "m28-test-run",
        "run_type": "backtest",
        "status": "completed",
        "params_json": {"lookback": 10},
        "assumptions_json": {"transaction_cost_bps": 5},
        "metrics_json": {"sharpe": 1.1, "num_trades": 40},
    }
}


# ---------------------------------------------------------------------------
# TestProjectHealthEndpoint
# ---------------------------------------------------------------------------

class TestProjectHealthEndpoint:
    def test_project_health_seeded_project(self, client, db):
        """GET /api/projects/{id}/health returns 200 for a known project."""
        org, project = _get_org_project(db)
        resp = client.get(f"/api/projects/{project.id}/health")
        assert resp.status_code == 200

    def test_project_health_response_fields(self, client, db):
        """All required fields are present in the health response."""
        org, project = _get_org_project(db)
        resp = client.get(f"/api/projects/{project.id}/health")
        assert resp.status_code == 200
        data = resp.json()
        required = [
            "project_id", "project_name", "organization_id",
            "health_score", "health_status",
            "strategy_count",
            "healthy_strategy_count", "watch_strategy_count",
            "review_strategy_count", "critical_strategy_count",
            "insufficient_evidence_strategy_count",
            "average_strategy_health_score",
            "average_reliability_score",
            "average_evidence_coverage_score",
            "open_alert_count", "high_critical_alert_count",
            "recent_failed_ingestion_count",
            "latest_activity_at",
            "primary_concern", "suggested_checks",
            "generated_at",
        ]
        for field in required:
            assert field in data, f"Missing field: {field}"

    def test_project_health_unknown_404(self, client):
        """GET /api/projects/{unknown}/health returns 404."""
        resp = client.get(f"/api/projects/{uuid.uuid4()}/health")
        assert resp.status_code == 404

    def test_project_health_list_200(self, client):
        """GET /api/projects/health returns 200."""
        resp = client.get("/api/projects/health")
        assert resp.status_code == 200

    def test_project_health_list_total_gte_1(self, client):
        """total >= 1 after seeding."""
        resp = client.get("/api/projects/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "total" in data
        assert data["total"] >= 1
        assert "items" in data
        assert len(data["items"]) >= 1

    def test_project_health_list_status_filter(self, client):
        """?status= filter returns only projects with matching health_status."""
        # Get a real status from the seeded data
        resp = client.get("/api/projects/health")
        assert resp.status_code == 200
        items = resp.json()["items"]
        if not items:
            pytest.skip("No projects in health list")
        real_status = items[0]["health_status"]
        resp2 = client.get(f"/api/projects/health?status={real_status}")
        assert resp2.status_code == 200
        for item in resp2.json()["items"]:
            assert item["health_status"] == real_status


# ---------------------------------------------------------------------------
# TestProjectHealthAggregation
# ---------------------------------------------------------------------------

class TestProjectHealthAggregation:
    def test_no_strategies_insufficient(self, client, db):
        """A project with no strategies should have insufficient_evidence status."""
        org, _ = _get_org_project(db)
        # Create a fresh isolated project
        proj = Project(
            organization_id=org.id,
            name=f"EmptyProj-{uuid.uuid4().hex[:6]}",
            slug=f"emptyproj-{uuid.uuid4().hex[:6]}",
        )
        db.add(proj)
        db.commit()
        db.refresh(proj)
        try:
            resp = client.get(f"/api/projects/{proj.id}/health")
            assert resp.status_code == 200
            data = resp.json()
            assert data["strategy_count"] == 0
            assert data["health_status"] == "insufficient_evidence"
        finally:
            db.delete(proj)
            db.commit()

    def test_critical_strategy_makes_project_critical(self, client, db):
        """Adding a critical-severity alert to a project strategy makes health critical."""
        org, _ = _get_org_project(db)
        proj = Project(
            organization_id=org.id,
            name=f"CritProj-{uuid.uuid4().hex[:6]}",
            slug=f"critproj-{uuid.uuid4().hex[:6]}",
        )
        db.add(proj)
        db.commit()
        db.refresh(proj)
        strategy = None
        alert = None
        try:
            strategy = _make_strategy(db, org, proj)
            alert = Alert(
                organization_id=str(org.id),
                strategy_id=str(strategy.id),
                rule_type="test_critical",
                severity="critical",
                status="open",
                title="Critical test alert",
                triggered_at=datetime.now(timezone.utc),
            )
            db.add(alert)
            db.commit()

            resp = client.get(f"/api/projects/{proj.id}/health")
            assert resp.status_code == 200
            data = resp.json()
            assert data["health_status"] == "critical"
            assert data["high_critical_alert_count"] >= 1
        finally:
            if alert is not None:
                try:
                    db.delete(alert)
                    db.commit()
                except Exception:
                    db.rollback()
            if strategy is not None:
                _cleanup_strategy(db, strategy)
            try:
                db.delete(proj)
                db.commit()
            except Exception:
                db.rollback()

    def test_strategy_counts_correct(self, client, db):
        """strategy_count reflects the number of strategies in the project."""
        org, _ = _get_org_project(db)
        proj = Project(
            organization_id=org.id,
            name=f"CountProj-{uuid.uuid4().hex[:6]}",
            slug=f"countproj-{uuid.uuid4().hex[:6]}",
        )
        db.add(proj)
        db.commit()
        db.refresh(proj)
        s1 = s2 = None
        try:
            s1 = _make_strategy(db, org, proj, name=f"strat-a-{uuid.uuid4().hex[:4]}")
            s2 = _make_strategy(db, org, proj, name=f"strat-b-{uuid.uuid4().hex[:4]}")
            db.commit()

            resp = client.get(f"/api/projects/{proj.id}/health")
            assert resp.status_code == 200
            data = resp.json()
            assert data["strategy_count"] == 2
        finally:
            for s in [s1, s2]:
                if s is not None:
                    _cleanup_strategy(db, s)
            try:
                db.delete(proj)
                db.commit()
            except Exception:
                db.rollback()

    def test_average_health_score_computed(self, client, db):
        """average_strategy_health_score is a float or null (no server error)."""
        org, project = _get_org_project(db)
        resp = client.get(f"/api/projects/{project.id}/health")
        assert resp.status_code == 200
        data = resp.json()
        # Must be float or null — just ensure no exception
        val = data["average_strategy_health_score"]
        assert val is None or isinstance(val, (int, float))

    def test_recent_failed_ingestion_counted(self, client, db):
        """If no failed ingestion batches exist, recent_failed_ingestion_count == 0 for new project."""
        org, _ = _get_org_project(db)
        proj = Project(
            organization_id=org.id,
            name=f"FreshProj-{uuid.uuid4().hex[:6]}",
            slug=f"freshproj-{uuid.uuid4().hex[:6]}",
        )
        db.add(proj)
        db.commit()
        db.refresh(proj)
        try:
            resp = client.get(f"/api/projects/{proj.id}/health")
            assert resp.status_code == 200
            data = resp.json()
            assert data["recent_failed_ingestion_count"] == 0
        finally:
            db.delete(proj)
            db.commit()


# ---------------------------------------------------------------------------
# TestProjectScopedApiKey
# ---------------------------------------------------------------------------

class TestProjectScopedApiKey:
    """Tests for project-scoped API key enforcement on evidence ingestion."""

    def test_project_scoped_key_can_ingest_matching_project(self, client, db):
        """API key scoped to project A can ingest into a strategy in project A."""
        org, _ = _get_org_project(db)
        proj = Project(
            organization_id=org.id,
            name=f"ScopedA-{uuid.uuid4().hex[:6]}",
            slug=f"scopeda-{uuid.uuid4().hex[:6]}",
        )
        db.add(proj)
        db.commit()
        db.refresh(proj)
        strategy = key = None
        try:
            strategy = _make_strategy(db, org, proj)
            key, raw_key = _make_api_key(db, org, project_id=proj.id, scopes=["evidence:write"])
            with patch("app.core.auth.get_settings") as mock_settings:
                mock_settings.return_value.qf_require_api_key_for_ingestion = True
                mock_settings.return_value.qf_api_key_hash_secret = __import__("app.core.config", fromlist=["get_settings"]).get_settings().qf_api_key_hash_secret
                resp = client.post(
                    f"/api/strategies/{strategy.id}/evidence-bundles",
                    json=_MINIMAL_BUNDLE,
                    headers={"Authorization": f"Bearer {raw_key}"},
                )
            # 201 expected — key is scoped to the same project
            assert resp.status_code == 201, resp.text
        finally:
            if key is not None:
                _cleanup_key(db, key.id)
            if strategy is not None:
                _cleanup_strategy(db, strategy)
            try:
                db.delete(proj)
                db.commit()
            except Exception:
                db.rollback()

    def test_project_scoped_key_blocked_for_different_project(self, client, db):
        """API key scoped to project A cannot ingest into a strategy in project B."""
        org, _ = _get_org_project(db)
        proj_a = Project(
            organization_id=org.id,
            name=f"ProjA-{uuid.uuid4().hex[:6]}",
            slug=f"proja-{uuid.uuid4().hex[:6]}",
        )
        proj_b = Project(
            organization_id=org.id,
            name=f"ProjB-{uuid.uuid4().hex[:6]}",
            slug=f"projb-{uuid.uuid4().hex[:6]}",
        )
        db.add(proj_a)
        db.add(proj_b)
        db.commit()
        db.refresh(proj_a)
        db.refresh(proj_b)
        strategy = key = None
        try:
            # Strategy lives in proj_b
            strategy = _make_strategy(db, org, proj_b)
            # Key is scoped to proj_a
            key, raw_key = _make_api_key(db, org, project_id=proj_a.id, scopes=["evidence:write"])
            with patch("app.core.auth.get_settings") as mock_settings:
                mock_settings.return_value.qf_require_api_key_for_ingestion = True
                mock_settings.return_value.qf_api_key_hash_secret = __import__("app.core.config", fromlist=["get_settings"]).get_settings().qf_api_key_hash_secret
                resp = client.post(
                    f"/api/strategies/{strategy.id}/evidence-bundles",
                    json=_MINIMAL_BUNDLE,
                    headers={"Authorization": f"Bearer {raw_key}"},
                )
            assert resp.status_code == 403, resp.text
            assert "different project" in resp.json()["detail"]
        finally:
            if key is not None:
                _cleanup_key(db, key.id)
            if strategy is not None:
                _cleanup_strategy(db, strategy)
            for p in [proj_a, proj_b]:
                try:
                    db.delete(p)
                    db.commit()
                except Exception:
                    db.rollback()

    def test_org_level_key_can_ingest_any_project(self, client, db):
        """Org-level key (project_id=None) can ingest into any strategy."""
        org, _ = _get_org_project(db)
        proj = Project(
            organization_id=org.id,
            name=f"OrgKeyProj-{uuid.uuid4().hex[:6]}",
            slug=f"orgkeyproj-{uuid.uuid4().hex[:6]}",
        )
        db.add(proj)
        db.commit()
        db.refresh(proj)
        strategy = key = None
        try:
            strategy = _make_strategy(db, org, proj)
            # project_id=None means org-level
            key, raw_key = _make_api_key(db, org, project_id=None, scopes=["evidence:write"])
            with patch("app.core.auth.get_settings") as mock_settings:
                mock_settings.return_value.qf_require_api_key_for_ingestion = True
                mock_settings.return_value.qf_api_key_hash_secret = __import__("app.core.config", fromlist=["get_settings"]).get_settings().qf_api_key_hash_secret
                resp = client.post(
                    f"/api/strategies/{strategy.id}/evidence-bundles",
                    json=_MINIMAL_BUNDLE,
                    headers={"Authorization": f"Bearer {raw_key}"},
                )
            assert resp.status_code == 201, resp.text
        finally:
            if key is not None:
                _cleanup_key(db, key.id)
            if strategy is not None:
                _cleanup_strategy(db, strategy)
            try:
                db.delete(proj)
                db.commit()
            except Exception:
                db.rollback()

    def test_key_missing_evidence_write_scope_rejected(self, client, db):
        """Key with only ['read'] scope is rejected with 403 when auth is required."""
        org, _ = _get_org_project(db)
        proj = Project(
            organization_id=org.id,
            name=f"ReadOnlyProj-{uuid.uuid4().hex[:6]}",
            slug=f"readonlyproj-{uuid.uuid4().hex[:6]}",
        )
        db.add(proj)
        db.commit()
        db.refresh(proj)
        strategy = key = None
        try:
            strategy = _make_strategy(db, org, proj)
            key, raw_key = _make_api_key(db, org, project_id=None, scopes=["read"])
            with patch("app.core.auth.get_settings") as mock_settings:
                mock_settings.return_value.qf_require_api_key_for_ingestion = True
                mock_settings.return_value.qf_api_key_hash_secret = __import__("app.core.config", fromlist=["get_settings"]).get_settings().qf_api_key_hash_secret
                resp = client.post(
                    f"/api/strategies/{strategy.id}/evidence-bundles",
                    json=_MINIMAL_BUNDLE,
                    headers={"Authorization": f"Bearer {raw_key}"},
                )
            assert resp.status_code == 403, resp.text
            assert "evidence:write" in resp.json()["detail"]
        finally:
            if key is not None:
                _cleanup_key(db, key.id)
            if strategy is not None:
                _cleanup_strategy(db, strategy)
            try:
                db.delete(proj)
                db.commit()
            except Exception:
                db.rollback()

    def test_empty_scopes_allowed(self, client, db):
        """Key with empty/null scopes_json is backward-compatible (no 403 on scope check)."""
        org, _ = _get_org_project(db)
        proj = Project(
            organization_id=org.id,
            name=f"EmptyScopeProj-{uuid.uuid4().hex[:6]}",
            slug=f"emptyscopeproj-{uuid.uuid4().hex[:6]}",
        )
        db.add(proj)
        db.commit()
        db.refresh(proj)
        strategy = key = None
        try:
            strategy = _make_strategy(db, org, proj)
            key, raw_key = _make_api_key(db, org, project_id=None, scopes=[])
            with patch("app.core.auth.get_settings") as mock_settings:
                mock_settings.return_value.qf_require_api_key_for_ingestion = True
                mock_settings.return_value.qf_api_key_hash_secret = __import__("app.core.config", fromlist=["get_settings"]).get_settings().qf_api_key_hash_secret
                resp = client.post(
                    f"/api/strategies/{strategy.id}/evidence-bundles",
                    json=_MINIMAL_BUNDLE,
                    headers={"Authorization": f"Bearer {raw_key}"},
                )
            # Empty scopes = no scope restriction → should pass scope check, get 201
            assert resp.status_code == 201, resp.text
        finally:
            if key is not None:
                _cleanup_key(db, key.id)
            if strategy is not None:
                _cleanup_strategy(db, strategy)
            try:
                db.delete(proj)
                db.commit()
            except Exception:
                db.rollback()

    def test_infer_org_from_project_on_create(self, client, db):
        """POST /api/api-keys with project_id but no org_id infers the org from the project."""
        org, _ = _get_org_project(db)
        proj = Project(
            organization_id=org.id,
            name=f"InferOrgProj-{uuid.uuid4().hex[:6]}",
            slug=f"inferorgproj-{uuid.uuid4().hex[:6]}",
        )
        db.add(proj)
        db.commit()
        db.refresh(proj)
        key_id = None
        try:
            resp = client.post(
                "/api/api-keys",
                json={
                    "name": f"infer-org-key-{uuid.uuid4().hex[:6]}",
                    "project_id": str(proj.id),
                    # organization_id intentionally omitted
                },
            )
            assert resp.status_code == 201, resp.text
            data = resp.json()
            key_id = data["api_key"]["id"]
            assert data["api_key"]["project_id"] == str(proj.id)
            # org should have been inferred
            assert data["api_key"]["organization_id"] == str(org.id)
        finally:
            if key_id is not None:
                _cleanup_key(db, key_id)
            try:
                db.delete(proj)
                db.commit()
            except Exception:
                db.rollback()
