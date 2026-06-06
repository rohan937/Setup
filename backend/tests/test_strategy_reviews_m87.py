"""M87 Strategy Review — backend test suite.

Covers the M87 governance promotion-review workflow: creating reviews
(draft/submitted), the deterministic approval checklist, submit/approve/reject/
request-changes transitions, lifecycle advancement on approval, comments + the
immutable event log, the JSON/Markdown review packet, the portfolio
pending/decisions feeds, RBAC + email-verification gates, the self-approval
policy, and active-review dedup.

Implementation under test:
  app/services/strategy_reviews.py   submit/approve/reject/request_changes,
                                     build_review_checklist, BlockedApproval,
                                     STAGE_ORDER + per-target-stage required
                                     checks, packet (json/markdown)
  app/api/routes/strategy_reviews.py endpoints + RBAC
  app/schemas/strategy_reviews.py    response models
  app/core/rbac.py                   require_workspace_write_access /
                                     require_workspace_admin /
                                     require_verified_email

Determinism notes
-----------------
* Approval SUCCEEDS deterministically by targeting an EARLY stage whose required
  checks are easy to satisfy. Per the policy, target ``backtest_review`` requires
  only ``[has_backtest_run, reliability_score_exists]`` — so we seed one
  StrategyRun(run_type='backtest') and one StrategyReliabilityScore and the
  checklist's ``can_approve`` is True.
* Approval is BLOCKED by targeting ``paper_candidate`` on a bare strategy: its
  promotion gates / evidence / freshness required checks fail, producing a 400
  with a non-empty blockers list and leaving ``lifecycle_stage`` unchanged.

Self-approval policy (test #15)
-------------------------------
``approve_strategy_review`` forbids the submitter from approving their OWN review
unless they are a workspace owner. A non-owner admin who submitted a review gets
403; a DIFFERENT admin may approve it -> 2xx. Owners may override (covered by the
permissive owner path elsewhere).

In-memory SQLite TestClient pattern (StaticPool + create_all + get_db override).
Fixtures are prefixed ``m87_`` to avoid colliding with conftest fixtures.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 — register all mappers
from app.db.base import Base
from app.db.session import get_db
from app.main import app

from app.models.auth_user import AuthUser
from app.models.strategy import Strategy
from app.models.strategy_reliability_score import StrategyReliabilityScore
from app.models.strategy_review import StrategyReview
from app.models.strategy_run import StrategyRun
from app.models.workspace_member import WorkspaceMember

_URL = "sqlite+pysqlite:///:memory:"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def m87_engine():
    eng = create_engine(
        _URL, connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture()
def m87_db(m87_engine):
    s = Session(m87_engine)
    yield s
    s.close()


@pytest.fixture()
def m87_client(m87_db):
    def _override():
        yield m87_db

    prior = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = _override
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    if prior is not None:
        app.dependency_overrides[get_db] = prior
    else:
        app.dependency_overrides.pop(get_db, None)


def _register(client, email, name="User"):
    return client.post(
        "/api/auth/register",
        json={"email": email, "display_name": name, "password": "password123"},
    )


def _verify(db, email):
    user = db.query(AuthUser).filter(AuthUser.email == email).first()
    user.email_verified = True
    db.commit()


def _set_role(db, email, role):
    member = (
        db.query(WorkspaceMember).filter(WorkspaceMember.email == email).first()
    )
    member.role = role
    db.commit()


@pytest.fixture()
def m87_strategy(m87_client, m87_db):
    """Register the first (owner) user with a verified email and create a fresh
    strategy via the public API.

    Returns ``(strategy_id_str, owner_token, owner_email)``.
    """
    resp = _register(m87_client, "m87-owner@test.com", "M87 Owner")
    assert resp.status_code == 200, resp.text
    tok = resp.json()["access_token"]
    _verify(m87_db, "m87-owner@test.com")

    H = {"Authorization": f"Bearer {tok}"}
    pid = m87_client.get("/api/projects", headers=H).json()[0]["id"]
    sid = m87_client.post(
        "/api/strategies",
        json={
            "project_id": pid,
            "name": "M87 Strat",
            "asset_class": "equity",
            "status": "active",
        },
        headers=H,
    ).json()["id"]
    return sid, tok, "m87-owner@test.com"


# ---------------------------------------------------------------------------
# Seed helpers (direct ORM)
# ---------------------------------------------------------------------------

def _seed_backtest_run(db, sid):
    now = datetime.now(timezone.utc)
    run = StrategyRun(
        strategy_id=uuid.UUID(str(sid)),
        run_name="m87-bt-run",
        run_type="backtest",
        status="completed",
        created_at=now,
        updated_at=now,
    )
    db.add(run)
    db.flush()
    return run


def _seed_reliability_score(db, sid, score=82.0):
    now = datetime.now(timezone.utc)
    rs = StrategyReliabilityScore(
        strategy_id=uuid.UUID(str(sid)),
        overall_score=score,
        status="acceptable",
        backtest_trust_score=80.0,
        generated_at=now,
        created_at=now,
        updated_at=now,
    )
    db.add(rs)
    db.flush()
    return rs


def _seed_backtest_review_evidence(db, sid):
    """Seed the minimal evidence that makes a ``backtest_review`` target
    approvable: one backtest run + one reliability score."""
    _seed_backtest_run(db, sid)
    _seed_reliability_score(db, sid)
    db.commit()


def _events(db, review_id):
    from app.models.strategy_review import StrategyReviewEvent

    return (
        db.query(StrategyReviewEvent)
        .filter(StrategyReviewEvent.review_id == str(review_id))
        .all()
    )


def _create_review(client, sid, tok, target_stage, as_draft=False):
    return client.post(
        f"/api/strategies/{sid}/reviews",
        json={"target_stage": target_stage, "as_draft": as_draft},
        headers={"Authorization": f"Bearer {tok}"},
    )


# ===========================================================================
# 1-3: Create / draft / checklist / submit
# ===========================================================================

class TestCreateAndSubmit:
    def test_create_review_is_submitted(self, m87_client, m87_strategy):
        """1. POST /api/strategies/{id}/reviews creates a 'submitted' review."""
        sid, tok, _ = m87_strategy
        r = _create_review(m87_client, sid, tok, "backtest_review")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "submitted"
        assert body["target_stage"] == "backtest_review"
        assert body["submitted_at"] is not None

    def test_create_draft_review(self, m87_client, m87_strategy):
        """1. as_draft=True creates a 'draft' review (no submitted_at)."""
        sid, tok, _ = m87_strategy
        r = _create_review(m87_client, sid, tok, "backtest_review", as_draft=True)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "draft"
        assert body["submitted_at"] is None

    def test_checklist_json_has_required_fields(self, m87_client, m87_strategy):
        """2. The created review's checklist_json AND GET-detail's checklist carry
        items with key/status/required plus can_approve + blockers."""
        sid, tok, _ = m87_strategy
        r = _create_review(m87_client, sid, tok, "backtest_review")
        assert r.status_code == 200, r.text
        review_id = r.json()["id"]

        checklist = r.json()["checklist_json"]
        assert checklist is not None
        assert "can_approve" in checklist
        assert "blockers" in checklist
        assert isinstance(checklist["items"], list) and checklist["items"]
        for item in checklist["items"]:
            assert "key" in item and "status" in item and "required" in item

        # GET detail's checklist exposes the same fields.
        detail = m87_client.get(f"/api/strategy-reviews/{review_id}").json()
        dcl = detail["checklist"]
        assert "can_approve" in dcl and "blockers" in dcl
        for item in dcl["items"]:
            assert "key" in item and "status" in item and "required" in item

    def test_submit_transitions_draft_to_submitted(self, m87_client, m87_strategy):
        """3. POST .../submit transitions a draft review to 'submitted'."""
        sid, tok, _ = m87_strategy
        rid = _create_review(
            m87_client, sid, tok, "backtest_review", as_draft=True
        ).json()["id"]
        H = {"Authorization": f"Bearer {tok}"}
        r = m87_client.post(f"/api/strategy-reviews/{rid}/submit", headers=H)
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "submitted"
        assert r.json()["submitted_at"] is not None


# ===========================================================================
# 4-6: Approval blocking / success / lifecycle advancement
# ===========================================================================

class TestApprovalGating:
    def test_approval_blocked_on_bare_strategy(self, m87_client, m87_db, m87_strategy):
        """4. Approving a 'paper_candidate' review on a bare strategy is blocked:
        400 with a non-empty blockers list; lifecycle_stage stays None."""
        sid, tok, _ = m87_strategy
        H = {"Authorization": f"Bearer {tok}"}
        rid = _create_review(m87_client, sid, tok, "paper_candidate").json()["id"]

        r = m87_client.post(f"/api/strategy-reviews/{rid}/approve", headers=H)
        assert r.status_code == 400, r.text
        detail = r.json()["detail"]
        assert isinstance(detail, dict), detail
        assert detail.get("blockers"), "blockers list must be non-empty"

        m87_db.expire_all()
        strat = m87_db.query(Strategy).filter(Strategy.id == uuid.UUID(sid)).first()
        assert strat.lifecycle_stage is None, "lifecycle must not advance on block"

    def test_approval_succeeds_with_evidence(self, m87_client, m87_db, m87_strategy):
        """5. With a backtest run + reliability score seeded, approving a
        'backtest_review' review succeeds -> 2xx, status 'approved',
        decision 'approved'."""
        sid, tok, _ = m87_strategy
        _seed_backtest_review_evidence(m87_db, sid)
        H = {"Authorization": f"Bearer {tok}"}
        rid = _create_review(m87_client, sid, tok, "backtest_review").json()["id"]

        r = m87_client.post(f"/api/strategy-reviews/{rid}/approve", headers=H)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "approved"
        assert body["decision"] == "approved"
        assert body["decided_at"] is not None

    def test_approval_advances_lifecycle(self, m87_client, m87_db, m87_strategy):
        """6. After a successful approval the Strategy row's lifecycle_stage ==
        'backtest_review' and GET /lifecycle reflects it."""
        sid, tok, _ = m87_strategy
        _seed_backtest_review_evidence(m87_db, sid)
        H = {"Authorization": f"Bearer {tok}"}
        rid = _create_review(m87_client, sid, tok, "backtest_review").json()["id"]
        r = m87_client.post(f"/api/strategy-reviews/{rid}/approve", headers=H)
        assert r.status_code == 200, r.text

        m87_db.expire_all()
        strat = m87_db.query(Strategy).filter(Strategy.id == uuid.UUID(sid)).first()
        assert strat.lifecycle_stage == "backtest_review"

        lc = m87_client.get(f"/api/strategies/{sid}/lifecycle")
        assert lc.status_code == 200, lc.text
        assert lc.json()["current_stage"] == "backtest_review"


# ===========================================================================
# 7-8: reject / request-changes keep lifecycle unchanged
# ===========================================================================

class TestNonApprovingDecisions:
    def test_reject_keeps_lifecycle_unchanged(self, m87_client, m87_db, m87_strategy):
        """7. Reject -> status 'rejected', lifecycle still None, an immutable
        'rejected' event recorded."""
        sid, tok, _ = m87_strategy
        H = {"Authorization": f"Bearer {tok}"}
        rid = _create_review(m87_client, sid, tok, "backtest_review").json()["id"]

        r = m87_client.post(
            f"/api/strategy-reviews/{rid}/reject",
            json={"note": "not yet"},
            headers=H,
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "rejected"
        assert r.json()["decision"] == "rejected"

        m87_db.expire_all()
        strat = m87_db.query(Strategy).filter(Strategy.id == uuid.UUID(sid)).first()
        assert strat.lifecycle_stage is None
        actions = {e.action for e in _events(m87_db, rid)}
        assert "rejected" in actions, actions

    def test_request_changes_keeps_lifecycle_unchanged(
        self, m87_client, m87_db, m87_strategy
    ):
        """8. Request-changes -> status 'changes_requested', no lifecycle change."""
        sid, tok, _ = m87_strategy
        H = {"Authorization": f"Bearer {tok}"}
        rid = _create_review(m87_client, sid, tok, "backtest_review").json()["id"]

        r = m87_client.post(
            f"/api/strategy-reviews/{rid}/request-changes",
            json={"note": "tighten evidence"},
            headers=H,
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "changes_requested"

        m87_db.expire_all()
        strat = m87_db.query(Strategy).filter(Strategy.id == uuid.UUID(sid)).first()
        assert strat.lifecycle_stage is None
        actions = {e.action for e in _events(m87_db, rid)}
        assert "changes_requested" in actions, actions


# ===========================================================================
# 9: comments persist + event recorded
# ===========================================================================

class TestComments:
    def test_comment_persists_and_records_event(
        self, m87_client, m87_db, m87_strategy
    ):
        """9. POST a comment -> appears in GET detail comments; a 'commented'
        event is recorded."""
        sid, tok, _ = m87_strategy
        H = {"Authorization": f"Bearer {tok}"}
        rid = _create_review(m87_client, sid, tok, "backtest_review").json()["id"]

        r = m87_client.post(
            f"/api/strategy-reviews/{rid}/comments",
            json={"comment": "Looks reasonable to me."},
            headers=H,
        )
        assert r.status_code == 200, r.text

        detail = m87_client.get(f"/api/strategy-reviews/{rid}").json()
        comments = detail["comments"]
        assert any(c["comment"] == "Looks reasonable to me." for c in comments)

        actions = {e.action for e in _events(m87_db, rid)}
        assert "commented" in actions, actions


# ===========================================================================
# 10: review packet (json + markdown)
# ===========================================================================

class TestReviewPacket:
    def test_packet_json(self, m87_client, m87_db, m87_strategy):
        """10. GET .../packet?format=json -> valid JSON containing the checklist
        and the decision log."""
        sid, tok, _ = m87_strategy
        _seed_backtest_review_evidence(m87_db, sid)
        H = {"Authorization": f"Bearer {tok}"}
        rid = _create_review(m87_client, sid, tok, "backtest_review").json()["id"]
        m87_client.post(f"/api/strategy-reviews/{rid}/approve", headers=H)

        r = m87_client.get(f"/api/strategy-reviews/{rid}/packet?format=json")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["format"] == "json"
        parsed = json.loads(body["content"])
        assert "checklist" in parsed
        assert "decision_log" in parsed
        assert isinstance(parsed["decision_log"], list)

    def test_packet_markdown(self, m87_client, m87_strategy):
        """10. format=markdown -> contains the disclaimer text and a heading."""
        sid, tok, _ = m87_strategy
        H = {"Authorization": f"Bearer {tok}"}
        rid = _create_review(m87_client, sid, tok, "backtest_review").json()["id"]

        r = m87_client.get(f"/api/strategy-reviews/{rid}/packet?format=markdown")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["format"] == "markdown"
        content = body["content"]
        assert content.startswith("# ") or "\n# " in content, "expected a heading"
        assert "not trading advice" in content, "expected the disclaimer text"


# ===========================================================================
# 11: pending / decisions feeds
# ===========================================================================

class TestPortfolioFeeds:
    def test_pending_and_decisions(self, m87_client, m87_db, m87_strategy):
        """11. /pending returns submitted/changes_requested reviews; /decisions
        returns decided ones."""
        sid, tok, _ = m87_strategy
        H = {"Authorization": f"Bearer {tok}"}

        # One that stays submitted (pending).
        pending_id = _create_review(m87_client, sid, tok, "paper_candidate").json()[
            "id"
        ]
        # One we decide (reject -> decisions).
        decided_id = _create_review(m87_client, sid, tok, "backtest_review").json()[
            "id"
        ]
        m87_client.post(
            f"/api/strategy-reviews/{decided_id}/reject",
            json={"note": "no"},
            headers=H,
        )

        pending = m87_client.get("/api/strategy-reviews/pending").json()["items"]
        pending_ids = {p["id"] for p in pending}
        assert pending_id in pending_ids
        assert decided_id not in pending_ids

        decisions = m87_client.get("/api/strategy-reviews/decisions").json()["items"]
        decision_ids = {d["id"] for d in decisions}
        assert decided_id in decision_ids
        assert pending_id not in decision_ids


# ===========================================================================
# 12-14: RBAC + email verification
# ===========================================================================

class TestRBAC:
    def test_viewer_can_read_but_not_mutate(self, m87_client, m87_db, m87_strategy):
        """12. A viewer member can GET reviews (200) but cannot POST a review or
        approve (403)."""
        sid, owner_tok, _ = m87_strategy
        # Existing submitted review (owner-created) to target with approve.
        rid = _create_review(
            m87_client, sid, owner_tok, "backtest_review"
        ).json()["id"]

        viewer_email = "m87-viewer@test.com"
        resp = _register(m87_client, viewer_email, "Viewer")
        assert resp.status_code == 200, resp.text
        viewer_tok = resp.json()["access_token"]
        _set_role(m87_db, viewer_email, "viewer")
        _verify(m87_db, viewer_email)  # isolate the RBAC gate from the email gate
        VH = {"Authorization": f"Bearer {viewer_tok}"}

        # GET reads are allowed for viewers.
        assert (
            m87_client.get(f"/api/strategies/{sid}/reviews", headers=VH).status_code
            == 200
        )
        assert (
            m87_client.get(f"/api/strategy-reviews/{rid}", headers=VH).status_code
            == 200
        )

        # Writes are denied.
        r_create = _create_review(m87_client, sid, viewer_tok, "backtest_review")
        assert r_create.status_code == 403, r_create.text
        r_approve = m87_client.post(
            f"/api/strategy-reviews/{rid}/approve", headers=VH
        )
        assert r_approve.status_code == 403, r_approve.text

    def test_unverified_user_cannot_mutate(self, m87_client, m87_db, m87_strategy):
        """13. A JWT user with an UNVERIFIED email cannot submit/approve/comment
        -> 403 'Email verification required.'"""
        sid, owner_tok, _ = m87_strategy
        rid = _create_review(
            m87_client, sid, owner_tok, "backtest_review"
        ).json()["id"]

        unv_email = "m87-unverified@test.com"
        resp = _register(m87_client, unv_email, "Unverified")
        assert resp.status_code == 200, resp.text
        unv_tok = resp.json()["access_token"]
        # Grant write/admin access so the 403 is the email gate, not RBAC.
        _set_role(m87_db, unv_email, "admin")
        user = m87_db.query(AuthUser).filter(AuthUser.email == unv_email).first()
        assert user.email_verified is False
        UH = {"Authorization": f"Bearer {unv_tok}"}

        r_create = _create_review(m87_client, sid, unv_tok, "paper_candidate")
        assert r_create.status_code == 403, r_create.text
        assert r_create.json()["detail"] == "Email verification required."

        r_approve = m87_client.post(
            f"/api/strategy-reviews/{rid}/approve", headers=UH
        )
        assert r_approve.status_code == 403, r_approve.text
        assert r_approve.json()["detail"] == "Email verification required."

        r_comment = m87_client.post(
            f"/api/strategy-reviews/{rid}/comments",
            json={"comment": "hi"},
            headers=UH,
        )
        assert r_comment.status_code == 403, r_comment.text
        assert r_comment.json()["detail"] == "Email verification required."

    def test_owner_can_approve_and_reject(self, m87_client, m87_db, m87_strategy):
        """14. The owner (admin access + verified email) can approve and reject
        reviews -> 2xx."""
        sid, tok, _ = m87_strategy
        _seed_backtest_review_evidence(m87_db, sid)
        H = {"Authorization": f"Bearer {tok}"}

        approve_id = _create_review(
            m87_client, sid, tok, "backtest_review"
        ).json()["id"]
        r_app = m87_client.post(
            f"/api/strategy-reviews/{approve_id}/approve", headers=H
        )
        assert r_app.status_code == 200, r_app.text
        assert r_app.json()["status"] == "approved"

        # A separate review to reject (paper_candidate stays active for the owner
        # to reject).
        reject_id = _create_review(
            m87_client, sid, tok, "paper_candidate"
        ).json()["id"]
        r_rej = m87_client.post(
            f"/api/strategy-reviews/{reject_id}/reject",
            json={"note": "later"},
            headers=H,
        )
        assert r_rej.status_code == 200, r_rej.text
        assert r_rej.json()["status"] == "rejected"


# ===========================================================================
# 15: self-approval policy
# ===========================================================================

class TestSelfApprovalPolicy:
    def test_self_approval_blocked_other_admin_allowed(
        self, m87_client, m87_db, m87_strategy
    ):
        """15. Self-approval policy: a non-owner admin who SUBMITTED a review
        cannot approve their own review (403); a DIFFERENT admin can (2xx).

        Policy (see app/services/strategy_reviews.approve_strategy_review): the
        submitter may not approve their own review unless they are a workspace
        owner. Owners may override. Two distinct non-owner admins are set up so
        the reviewer differs from the submitter.
        """
        sid, _owner_tok, _ = m87_strategy
        _seed_backtest_review_evidence(m87_db, sid)

        # Admin A — submitter.
        a_email = "m87-admin-a@test.com"
        a_tok = _register(m87_client, a_email, "Admin A").json()["access_token"]
        _set_role(m87_db, a_email, "admin")
        _verify(m87_db, a_email)
        AH = {"Authorization": f"Bearer {a_tok}"}

        # Admin B — a different reviewer.
        b_email = "m87-admin-b@test.com"
        b_tok = _register(m87_client, b_email, "Admin B").json()["access_token"]
        _set_role(m87_db, b_email, "admin")
        _verify(m87_db, b_email)
        BH = {"Authorization": f"Bearer {b_tok}"}

        # Admin A submits the review.
        rid = _create_review(m87_client, sid, a_tok, "backtest_review").json()["id"]

        # Admin A cannot approve their own review.
        r_self = m87_client.post(f"/api/strategy-reviews/{rid}/approve", headers=AH)
        assert r_self.status_code == 403, r_self.text

        # Admin B (different reviewer) can approve.
        r_other = m87_client.post(f"/api/strategy-reviews/{rid}/approve", headers=BH)
        assert r_other.status_code == 200, r_other.text
        assert r_other.json()["status"] == "approved"


# ===========================================================================
# 16: active-review dedup
# ===========================================================================

class TestDedup:
    def test_duplicate_active_review_conflict(self, m87_client, m87_strategy):
        """16. Submitting a second review for the same strategy+target while one
        is already active -> 409."""
        sid, tok, _ = m87_strategy
        first = _create_review(m87_client, sid, tok, "backtest_review")
        assert first.status_code == 200, first.text

        second = _create_review(m87_client, sid, tok, "backtest_review")
        assert second.status_code == 409, second.text
