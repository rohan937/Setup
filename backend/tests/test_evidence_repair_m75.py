"""M75 tests: Evidence Repair Flows + Basic Strategy Management.

Covers:
  - GET  /api/strategies/{id}/repair-options
  - PATCH /api/strategies/{id}/runs/{run_id}/links (dataset/signal/universe/version)
  - cross-strategy / cross-project link rejection
  - timeline event creation (run_evidence_linked)
  - PATCH /api/strategies/{id} (update)
  - DELETE /api/strategies/{id} (archive, confirm guard, RBAC, list filter)
  - action-queue link item disappears after repair

Shared session fixtures (client/db) are permissive (no token → owner). A small
isolated-DB section exercises the viewer-403 path.
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


# ---------------------------------------------------------------------------
# Helpers (shared seeded DB)
# ---------------------------------------------------------------------------

def _seeded_org(db):
    from app.models.organization import Organization
    return db.query(Organization).first()


def _seeded_project(db):
    from app.models.project import Project
    return db.query(Project).first()


def _mk_strategy(db, project_id, suffix="") -> object:
    from app.models.strategy import Strategy
    s = Strategy(
        project_id=project_id,
        name=f"M75 Strategy {suffix}",
        slug=f"m75-{suffix}-{uuid.uuid4().hex[:8]}",
        asset_class="equity",
        status="active",
    )
    db.add(s)
    db.flush()
    return s


def _mk_project(db, org_id, suffix="") -> object:
    from app.models.project import Project
    p = Project(
        organization_id=org_id,
        name=f"M75 Project {suffix}",
        slug=f"m75-proj-{suffix}-{uuid.uuid4().hex[:8]}",
    )
    db.add(p)
    db.flush()
    return p


def _mk_run(db, strategy_id, **links) -> object:
    from app.models.strategy_run import StrategyRun
    r = StrategyRun(
        strategy_id=strategy_id,
        run_name=f"run-{uuid.uuid4().hex[:6]}",
        run_type="backtest",
        status="completed",
        **links,
    )
    db.add(r)
    db.flush()
    return r


def _mk_dataset_snapshot(db, project_id, *, health=88, rows=500) -> object:
    from app.models.dataset import Dataset
    from app.models.dataset_snapshot import DatasetSnapshot
    ds = Dataset(project_id=project_id, name=f"DS-{uuid.uuid4().hex[:6]}")
    db.add(ds)
    db.flush()
    snap = DatasetSnapshot(
        dataset_id=ds.id, version_label="v1", row_count=rows, health_score=health,
    )
    db.add(snap)
    db.flush()
    return snap


def _mk_signal(db, strategy_id, *, quality=77) -> object:
    from app.models.signal_snapshot import SignalSnapshot
    snap = SignalSnapshot(
        strategy_id=strategy_id,
        label=f"sig-{uuid.uuid4().hex[:6]}",
        rows_json=[],
        symbols_json=[],
        signal_hash=uuid.uuid4().hex,
        quality_score=quality,
        symbol_count=12,
    )
    db.add(snap)
    db.flush()
    return snap


def _mk_universe(db, strategy_id, *, symbols=20) -> object:
    from app.models.universe_snapshot import UniverseSnapshot
    snap = UniverseSnapshot(
        strategy_id=strategy_id,
        label=f"uni-{uuid.uuid4().hex[:6]}",
        symbols_json=[],
        universe_hash=uuid.uuid4().hex,
        symbol_count=symbols,
    )
    db.add(snap)
    db.flush()
    return snap


def _mk_version(db, strategy_id) -> object:
    from app.models.strategy_version import StrategyVersion
    v = StrategyVersion(strategy_id=strategy_id, version_label=f"v{uuid.uuid4().hex[:4]}")
    db.add(v)
    db.flush()
    return v


# ---------------------------------------------------------------------------
# Repair options
# ---------------------------------------------------------------------------

class TestRepairOptions:
    def test_returns_compatible_evidence(self, client, db):
        proj = _seeded_project(db)
        strat = _mk_strategy(db, proj.id, "opts")
        _mk_dataset_snapshot(db, proj.id)
        _mk_signal(db, strat.id)
        _mk_universe(db, strat.id)
        _mk_version(db, strat.id)
        _mk_run(db, strat.id)  # missing all links
        db.flush()
        data = client.get(f"/api/strategies/{strat.id}/repair-options").json()
        assert len(data["dataset_snapshots"]) >= 1
        assert len(data["signal_snapshots"]) >= 1
        assert len(data["universe_snapshots"]) >= 1
        assert len(data["strategy_versions"]) >= 1
        assert len(data["runs_missing_links"]) >= 1
        # recommendation flag on the latest option
        assert data["signal_snapshots"][0]["recommended"] is True
        assert "dataset" in data["runs_missing_links"][0]["missing"]

    def test_unknown_strategy_404(self, client):
        resp = client.get(f"/api/strategies/{uuid.uuid4()}/repair-options")
        assert resp.status_code == 404

    def test_signal_options_scoped_to_strategy(self, client, db):
        proj = _seeded_project(db)
        a = _mk_strategy(db, proj.id, "scopeA")
        b = _mk_strategy(db, proj.id, "scopeB")
        sig_b = _mk_signal(db, b.id)
        db.flush()
        data = client.get(f"/api/strategies/{a.id}/repair-options").json()
        ids = {o["id"] for o in data["signal_snapshots"]}
        assert str(sig_b.id) not in ids


# ---------------------------------------------------------------------------
# Run link updates
# ---------------------------------------------------------------------------

class TestRunLinkUpdates:
    def test_link_dataset(self, client, db):
        proj = _seeded_project(db)
        strat = _mk_strategy(db, proj.id, "lds")
        run = _mk_run(db, strat.id)
        snap = _mk_dataset_snapshot(db, proj.id)
        db.flush()
        resp = client.patch(
            f"/api/strategies/{strat.id}/runs/{run.id}/links",
            json={"dataset_snapshot_id": str(snap.id)},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["dataset_snapshot_id"] == str(snap.id)
        assert "dataset_snapshot_id" in body["linked_fields"]
        db.refresh(run)
        assert str(run.dataset_snapshot_id) == str(snap.id)

    def test_link_signal(self, client, db):
        proj = _seeded_project(db)
        strat = _mk_strategy(db, proj.id, "lsig")
        run = _mk_run(db, strat.id)
        snap = _mk_signal(db, strat.id)
        db.flush()
        resp = client.patch(
            f"/api/strategies/{strat.id}/runs/{run.id}/links",
            json={"signal_snapshot_id": str(snap.id)},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["signal_snapshot_id"] == str(snap.id)

    def test_link_universe(self, client, db):
        proj = _seeded_project(db)
        strat = _mk_strategy(db, proj.id, "luni")
        run = _mk_run(db, strat.id)
        snap = _mk_universe(db, strat.id)
        db.flush()
        resp = client.patch(
            f"/api/strategies/{strat.id}/runs/{run.id}/links",
            json={"universe_snapshot_id": str(snap.id)},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["universe_snapshot_id"] == str(snap.id)

    def test_link_version(self, client, db):
        proj = _seeded_project(db)
        strat = _mk_strategy(db, proj.id, "lver")
        run = _mk_run(db, strat.id)
        ver = _mk_version(db, strat.id)
        db.flush()
        resp = client.patch(
            f"/api/strategies/{strat.id}/runs/{run.id}/links",
            json={"strategy_version_id": str(ver.id)},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["strategy_version_id"] == str(ver.id)

    def test_partial_multi_link(self, client, db):
        proj = _seeded_project(db)
        strat = _mk_strategy(db, proj.id, "lmulti")
        run = _mk_run(db, strat.id)
        ds = _mk_dataset_snapshot(db, proj.id)
        sig = _mk_signal(db, strat.id)
        db.flush()
        resp = client.patch(
            f"/api/strategies/{strat.id}/runs/{run.id}/links",
            json={"dataset_snapshot_id": str(ds.id), "signal_snapshot_id": str(sig.id)},
        )
        assert resp.status_code == 200, resp.text
        assert set(resp.json()["linked_fields"]) == {"dataset_snapshot_id", "signal_snapshot_id"}

    def test_empty_body_rejected(self, client, db):
        proj = _seeded_project(db)
        strat = _mk_strategy(db, proj.id, "lempty")
        run = _mk_run(db, strat.id)
        db.flush()
        resp = client.patch(
            f"/api/strategies/{strat.id}/runs/{run.id}/links", json={},
        )
        assert resp.status_code == 400

    def test_run_from_other_strategy_rejected(self, client, db):
        proj = _seeded_project(db)
        a = _mk_strategy(db, proj.id, "ownerA")
        b = _mk_strategy(db, proj.id, "ownerB")
        run_b = _mk_run(db, b.id)
        snap = _mk_dataset_snapshot(db, proj.id)
        db.flush()
        # Try to link via strategy A's URL but run belongs to B.
        resp = client.patch(
            f"/api/strategies/{a.id}/runs/{run_b.id}/links",
            json={"dataset_snapshot_id": str(snap.id)},
        )
        assert resp.status_code == 400

    def test_incompatible_project_dataset_rejected(self, client, db):
        org = _seeded_org(db)
        proj_a = _seeded_project(db)
        proj_b = _mk_project(db, org.id, "other")
        strat = _mk_strategy(db, proj_a.id, "xproj")
        run = _mk_run(db, strat.id)
        foreign_ds = _mk_dataset_snapshot(db, proj_b.id)  # different project
        db.flush()
        resp = client.patch(
            f"/api/strategies/{strat.id}/runs/{run.id}/links",
            json={"dataset_snapshot_id": str(foreign_ds.id)},
        )
        assert resp.status_code == 400

    def test_signal_from_other_strategy_rejected(self, client, db):
        proj = _seeded_project(db)
        a = _mk_strategy(db, proj.id, "sigA")
        b = _mk_strategy(db, proj.id, "sigB")
        run = _mk_run(db, a.id)
        foreign_sig = _mk_signal(db, b.id)
        db.flush()
        resp = client.patch(
            f"/api/strategies/{a.id}/runs/{run.id}/links",
            json={"signal_snapshot_id": str(foreign_sig.id)},
        )
        assert resp.status_code == 400

    def test_creates_timeline_event(self, client, db):
        from app.models.audit_timeline_event import AuditTimelineEvent
        proj = _seeded_project(db)
        strat = _mk_strategy(db, proj.id, "tl")
        run = _mk_run(db, strat.id)
        snap = _mk_dataset_snapshot(db, proj.id)
        db.flush()
        client.patch(
            f"/api/strategies/{strat.id}/runs/{run.id}/links",
            json={"dataset_snapshot_id": str(snap.id)},
        )
        ev = (
            db.query(AuditTimelineEvent)
            .filter(
                AuditTimelineEvent.strategy_id == strat.id,
                AuditTimelineEvent.event_type == "run_evidence_linked",
            )
            .first()
        )
        assert ev is not None
        assert ev.source_id == str(run.id)


# ---------------------------------------------------------------------------
# Action-queue integration
# ---------------------------------------------------------------------------

class TestActionQueueAfterRepair:
    def test_link_item_disappears_after_repair(self, client, db):
        proj = _seeded_project(db)
        strat = _mk_strategy(db, proj.id, "aq")
        run = _mk_run(db, strat.id)  # missing all four links
        ds = _mk_dataset_snapshot(db, proj.id)
        sig = _mk_signal(db, strat.id)
        uni = _mk_universe(db, strat.id)
        ver = _mk_version(db, strat.id)
        db.flush()

        before = client.get(f"/api/strategies/{strat.id}/action-queue?limit=50").json()
        keys_before = {i["id"].split(":", 1)[1] for i in before["items"]}
        assert "link_run_evidence" in keys_before

        resp = client.patch(
            f"/api/strategies/{strat.id}/runs/{run.id}/links",
            json={
                "dataset_snapshot_id": str(ds.id),
                "signal_snapshot_id": str(sig.id),
                "universe_snapshot_id": str(uni.id),
                "strategy_version_id": str(ver.id),
            },
        )
        assert resp.status_code == 200, resp.text

        after = client.get(f"/api/strategies/{strat.id}/action-queue?limit=50").json()
        keys_after = {i["id"].split(":", 1)[1] for i in after["items"]}
        assert "link_run_evidence" not in keys_after


# ---------------------------------------------------------------------------
# Strategy management (update / archive)
# ---------------------------------------------------------------------------

class TestStrategyManagement:
    def test_update_name_and_asset_class(self, client, db):
        proj = _seeded_project(db)
        strat = _mk_strategy(db, proj.id, "upd")
        db.flush()
        resp = client.patch(
            f"/api/strategies/{strat.id}",
            json={"name": "Renamed Strategy", "asset_class": "crypto"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["name"] == "Renamed Strategy"
        assert body["asset_class"] == "crypto"
        db.refresh(strat)
        assert strat.name == "Renamed Strategy"

    def test_update_invalid_status_rejected(self, client, db):
        proj = _seeded_project(db)
        strat = _mk_strategy(db, proj.id, "badstatus")
        db.flush()
        resp = client.patch(
            f"/api/strategies/{strat.id}", json={"status": "not_a_status"},
        )
        assert resp.status_code == 400

    def test_update_empty_body_rejected(self, client, db):
        proj = _seeded_project(db)
        strat = _mk_strategy(db, proj.id, "noop")
        db.flush()
        resp = client.patch(f"/api/strategies/{strat.id}", json={})
        assert resp.status_code == 400

    def test_archive_requires_confirm(self, client, db):
        proj = _seeded_project(db)
        strat = _mk_strategy(db, proj.id, "noconfirm")
        db.flush()
        resp = client.delete(f"/api/strategies/{strat.id}")
        assert resp.status_code == 400

    def test_archive_soft_deletes(self, client, db):
        proj = _seeded_project(db)
        strat = _mk_strategy(db, proj.id, "arch")
        db.flush()
        resp = client.delete(f"/api/strategies/{strat.id}?confirm=true")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["archived"] is True
        assert body["status"] == "archived"
        # Soft delete: row still exists.
        db.refresh(strat)
        assert strat.status == "archived"

    def test_archived_excluded_from_active_list(self, client, db):
        proj = _seeded_project(db)
        strat = _mk_strategy(db, proj.id, "listfilter")
        db.flush()
        client.delete(f"/api/strategies/{strat.id}?confirm=true")
        active = client.get("/api/strategies?status=active").json()
        active_ids = {s["id"] for s in active}
        assert str(strat.id) not in active_ids
        archived = client.get("/api/strategies?status=archived").json()
        archived_ids = {s["id"] for s in archived}
        assert str(strat.id) in archived_ids

    def test_archive_creates_timeline_event(self, client, db):
        from app.models.audit_timeline_event import AuditTimelineEvent
        proj = _seeded_project(db)
        strat = _mk_strategy(db, proj.id, "archtl")
        db.flush()
        client.delete(f"/api/strategies/{strat.id}?confirm=true")
        ev = (
            db.query(AuditTimelineEvent)
            .filter(
                AuditTimelineEvent.strategy_id == strat.id,
                AuditTimelineEvent.event_type == "strategy_archived",
            )
            .first()
        )
        assert ev is not None


# ---------------------------------------------------------------------------
# RBAC — viewer cannot manage (isolated DB)
# ---------------------------------------------------------------------------

_DB_URL = "sqlite+pysqlite:///:memory:"


@pytest.fixture()
def rbac_engine():
    engine = create_engine(
        _DB_URL, connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture()
def rbac_db(rbac_engine):
    session = Session(rbac_engine)
    yield session
    session.close()


@pytest.fixture()
def rbac_setup(rbac_db):
    """Org + project + strategy in the isolated DB."""
    from app.models.organization import Organization
    from app.models.project import Project
    from app.models.strategy import Strategy
    now = datetime.now(timezone.utc)
    org = Organization(name="M75 WS", slug="m75-ws", created_at=now, updated_at=now)
    rbac_db.add(org)
    rbac_db.commit()
    proj = Project(organization_id=org.id, name="M75 P", slug="m75-p",
                   created_at=now, updated_at=now)
    rbac_db.add(proj)
    rbac_db.commit()
    strat = Strategy(project_id=proj.id, name="M75 Managed", slug="m75-managed",
                     asset_class="equity", status="active")
    rbac_db.add(strat)
    rbac_db.commit()
    return org, proj, strat


@pytest.fixture()
def rbac_client(rbac_db, rbac_setup):  # noqa: ARG001
    def _override():
        yield rbac_db
    # Save the prior override (the shared session client sets one) and restore it
    # on teardown so this isolated-DB fixture cannot leak into other test files.
    prior = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = _override
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    if prior is not None:
        app.dependency_overrides[get_db] = prior
    else:
        app.dependency_overrides.pop(get_db, None)


def _viewer_token(client, db) -> str:
    from app.models.workspace_member import WorkspaceMember
    email = f"viewer-{uuid.uuid4().hex[:8]}@test.com"
    # First registered user becomes owner; register a second as viewer.
    client.post("/api/auth/register", json={
        "email": f"owner-{uuid.uuid4().hex[:6]}@test.com",
        "display_name": "Owner", "password": "password123",
    })
    resp = client.post("/api/auth/register", json={
        "email": email, "display_name": "Viewer", "password": "password123",
    })
    assert resp.status_code == 200, resp.text
    member = db.query(WorkspaceMember).filter(WorkspaceMember.email == email).first()
    member.role = "viewer"
    db.commit()
    return resp.json()["access_token"]


class TestManagementRBAC:
    def test_viewer_cannot_archive(self, rbac_client, rbac_db, rbac_setup):
        _, _, strat = rbac_setup
        token = _viewer_token(rbac_client, rbac_db)
        resp = rbac_client.delete(
            f"/api/strategies/{strat.id}?confirm=true",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403, resp.text

    def test_viewer_cannot_update(self, rbac_client, rbac_db, rbac_setup):
        _, _, strat = rbac_setup
        token = _viewer_token(rbac_client, rbac_db)
        resp = rbac_client.patch(
            f"/api/strategies/{strat.id}",
            json={"name": "Hacked"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403, resp.text

    def test_viewer_cannot_link_evidence(self, rbac_client, rbac_db, rbac_setup):
        from app.models.strategy_run import StrategyRun
        _, _, strat = rbac_setup
        run = StrategyRun(strategy_id=strat.id, run_name="r", run_type="backtest",
                          status="completed")
        rbac_db.add(run)
        rbac_db.commit()
        token = _viewer_token(rbac_client, rbac_db)
        resp = rbac_client.patch(
            f"/api/strategies/{strat.id}/runs/{run.id}/links",
            json={"strategy_version_id": str(uuid.uuid4())},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403, resp.text
