"""M86 Portfolio Reliability — backend test suite.

Covers the portfolio reliability aggregation service and its 4 endpoints:
  GET  /api/portfolio/reliability                       (read; viewers allowed)
  GET  /api/portfolio/reliability/export                (read; json | markdown)
  POST /api/portfolio/reliability/refresh               (write + verified email)
  POST /api/portfolio/reliability/weekly-review-pack    (write + verified email)

Implementation under test:
  app/services/portfolio_reliability.py  build_portfolio_reliability /
                                         render_portfolio_reliability_markdown /
                                         refresh_portfolio_reliability /
                                         health_classification rules
  app/api/routes/portfolio.py            the 4 endpoints + RBAC
  app/schemas/portfolio_reliability.py   response models

Setup pattern: register an owner via the public API (this also bootstraps the
default org + project), then insert evidence rows (reliability scores, runs,
reports, alerts) directly with the ORM against the same in-memory session to
construct deterministic conditions.  ``commit()`` is issued between setup and
the assertion read so the read path sees the seeded rows.

Fixtures are prefixed ``m86_`` to avoid colliding with conftest's
session-scoped fixtures.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 — register all mappers
from app.db.base import Base
from app.db.session import get_db
from app.main import app

from app.core.constants import AlertStatus
from app.models.alert import Alert
from app.models.auth_user import AuthUser
from app.models.organization import Organization
from app.models.report import Report
from app.models.strategy import Strategy
from app.models.strategy_reliability_score import StrategyReliabilityScore
from app.models.strategy_run import StrategyRun
from app.models.workspace_member import WorkspaceMember

_URL = "sqlite+pysqlite:///:memory:"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def m86_engine():
    eng = create_engine(_URL, connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture()
def m86_db(m86_engine):
    s = Session(m86_engine)
    yield s
    s.close()


@pytest.fixture()
def m86_client(m86_db):
    def _override():
        yield m86_db

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


@pytest.fixture()
def m86_owner(m86_client, m86_db):
    """Register the first (owner) user, verify their email, and return
    ``(token, project_id, org_id)``.  Verifying the email means the write
    endpoints exercise RBAC, not the M84 email-verification gate."""
    resp = _register(m86_client, "m86-owner@test.com", "M86 Owner")
    assert resp.status_code == 200, resp.text
    tok = resp.json()["access_token"]

    owner = m86_db.query(AuthUser).filter(AuthUser.email == "m86-owner@test.com").first()
    owner.email_verified = True
    m86_db.commit()

    H = {"Authorization": f"Bearer {tok}"}
    pid = m86_client.get("/api/projects", headers=H).json()[0]["id"]
    org_id = str(m86_db.query(Organization).first().id)
    return tok, pid, org_id


# ---------------------------------------------------------------------------
# Seed helpers (direct ORM)
# ---------------------------------------------------------------------------

def _make_strategy(db, project_id, name, *, asset_class="equity", status="active"):
    s = Strategy(
        project_id=uuid.UUID(str(project_id)),
        name=name,
        slug=name.lower().replace(" ", "-"),
        asset_class=asset_class,
        status=status,
    )
    db.add(s)
    db.flush()
    return s


def _seed_score(db, sid, score, *, generated_at, status="review"):
    rs = StrategyReliabilityScore(
        strategy_id=uuid.UUID(str(sid)),
        overall_score=score,
        status=status,
        generated_at=generated_at,
        created_at=generated_at,
        updated_at=generated_at,
    )
    db.add(rs)
    db.flush()
    return rs


def _seed_run(db, sid, *, run_name="run-1", created_at=None):
    now = created_at or datetime.now(timezone.utc)
    run = StrategyRun(
        strategy_id=uuid.UUID(str(sid)),
        run_name=run_name,
        run_type="backtest",
        status="completed",
        created_at=now,
        updated_at=now,
    )
    db.add(run)
    db.flush()
    return run


def _seed_report(db, org_id, sid, *, generated_at, report_type="strategy_reliability"):
    rep = Report(
        organization_id=uuid.UUID(str(org_id)),
        strategy_id=uuid.UUID(str(sid)),
        report_type=report_type,
        title="Reliability report",
        status="generated",
        summary="seeded",
        generated_at=generated_at,
        created_at=generated_at,
        updated_at=generated_at,
    )
    db.add(rep)
    db.flush()
    return rep


def _seed_alert(db, org_id, sid, *, severity, status=str(AlertStatus.open), rule_type="regression_test_failed"):
    now = datetime.now(timezone.utc)
    a = Alert(
        organization_id=str(org_id),
        rule_type=rule_type,
        status=status,
        severity=severity,
        title=f"{severity} alert",
        source_type="strategy",
        source_id=str(sid),
        strategy_id=uuid.UUID(str(sid)).hex,
        triggered_at=now,
    )
    db.add(a)
    db.flush()
    return a


def _row_for(body, sid):
    for r in body["strategies"]:
        if r["strategy_id"] == str(sid):
            return r
    return None


def _H(tok):
    return {"Authorization": f"Bearer {tok}"}


# ===========================================================================
# 1. Basic shape
# ===========================================================================

class TestPortfolioReliabilityBasic:
    def test_returns_200_with_summary_and_nonempty_strategies(self, m86_client, m86_db, m86_owner):
        tok, pid, _org = m86_owner
        _make_strategy(m86_db, pid, "Alpha")
        _make_strategy(m86_db, pid, "Beta")
        m86_db.commit()

        r = m86_client.get("/api/portfolio/reliability", headers=_H(tok))
        assert r.status_code == 200, r.text
        body = r.json()
        assert isinstance(body["summary"], dict)
        assert body["summary"]["total_strategies"] == 2
        assert len(body["strategies"]) == 2
        assert body["disclaimer"]


# ===========================================================================
# 2. Ranking by reliability score descending (None last)
# ===========================================================================

class TestRanking:
    def test_strategies_ranked_by_score_desc_none_last(self, m86_client, m86_db, m86_owner):
        tok, pid, _org = m86_owner
        now = datetime.now(timezone.utc)
        s_high = _make_strategy(m86_db, pid, "HighScore")
        s_mid = _make_strategy(m86_db, pid, "MidScore")
        s_none = _make_strategy(m86_db, pid, "NoScore")
        _seed_score(m86_db, s_high.id, 90.0, generated_at=now)
        _seed_score(m86_db, s_mid.id, 50.0, generated_at=now)
        # s_none has no score row.
        m86_db.commit()

        body = m86_client.get("/api/portfolio/reliability", headers=_H(tok)).json()
        order = [r["strategy_id"] for r in body["strategies"]]
        assert order[0] == str(s_high.id), body["strategies"]
        assert order[1] == str(s_mid.id)
        # None-scored strategy ranks last.
        assert order[-1] == str(s_none.id)


# ===========================================================================
# 3. Health classification (blocked / review / healthy) + internal consistency
# ===========================================================================

class TestHealthClassification:
    def test_forced_blocker_classifies_blocked_and_counts_consistent(self, m86_client, m86_db, m86_owner):
        """A strategy with a forced blocking condition (open critical alert)
        classifies as 'blocked'.  The summary healthy/review/blocked counts must
        partition the total exactly (sum == total) and every row's
        classification must be one of the three valid buckets.

        The review/blocked distinction is exercised end-to-end in
        ``test_under_instrumented_is_review_not_blocked`` below (under-
        instrumented strategies are 'review', genuine hard problems are
        'blocked').
        """
        tok, pid, org = m86_owner

        s_blocked = _make_strategy(m86_db, pid, "Blocked One")
        _seed_alert(m86_db, org, s_blocked.id, severity="critical")

        s_other = _make_strategy(m86_db, pid, "Other One")
        _seed_alert(
            m86_db, org, s_other.id, severity="low",
            rule_type="data_health_below_threshold",
        )
        m86_db.commit()

        body = m86_client.get("/api/portfolio/reliability", headers=_H(tok)).json()

        assert _row_for(body, s_blocked.id)["health_classification"] == "blocked"
        for r in body["strategies"]:
            assert r["health_classification"] in ("blocked", "review", "healthy"), r

        s = body["summary"]
        assert (
            s["healthy_count"] + s["review_count"] + s["blocked_count"]
            == s["total_strategies"]
        ), s
        assert s["blocked_count"] >= 1

    def test_under_instrumented_is_review_not_blocked(self, m86_client, m86_db, m86_owner):
        """Drives the REAL service classifier end-to-end.

        An early / under-instrumented strategy (no evidence yet) reports
        critical health, unmet promotion gates, and an under_instrumented
        readiness verdict — but that is a 'needs work to progress' state, NOT a
        hard block, so it must classify as 'review'. A strategy with a genuine
        hard problem (an open critical alert) classifies as 'blocked'. This is
        the behaviour that makes the 3-way manager view meaningful — otherwise
        every minimally-evidenced strategy would read as 'blocked'.
        """
        tok, pid, org = m86_owner

        bare = _make_strategy(m86_db, pid, "Under Instrumented")
        blocked = _make_strategy(m86_db, pid, "Hard Blocked")
        _seed_alert(m86_db, org, blocked.id, severity="critical")
        m86_db.commit()

        body = m86_client.get("/api/portfolio/reliability", headers=_H(tok)).json()

        # The key fix: under-instrumented -> review, not blocked.
        assert _row_for(body, bare.id)["health_classification"] == "review"
        # A genuine hard problem (open critical alert) -> blocked.
        assert _row_for(body, blocked.id)["health_classification"] == "blocked"

        # Partition invariant still holds.
        s = body["summary"]
        assert (
            s["healthy_count"] + s["review_count"] + s["blocked_count"]
            == s["total_strategies"]
        ), s
        assert s["review_count"] >= 1 and s["blocked_count"] >= 1


# ===========================================================================
# 4. Stale evidence counts
# ===========================================================================

class TestStaleEvidence:
    def test_stale_evidence_surfaces_in_row_section_and_summary(self, m86_client, m86_db, m86_owner):
        """A strategy with a run but no supporting evidence types has missing
        evidence -> stale_evidence_count > 0 (compute_evidence_freshness counts
        missing evidence types).  It must appear in the stale_evidence section
        and the summary tally."""
        tok, pid, _org = m86_owner
        s = _make_strategy(m86_db, pid, "StaleStrat")
        _seed_run(m86_db, s.id, run_name="run-stale")
        m86_db.commit()

        body = m86_client.get("/api/portfolio/reliability", headers=_H(tok)).json()
        row = _row_for(body, s.id)
        assert row is not None
        assert row["stale_evidence_count"] > 0, row

        ids = {e["strategy_id"] for e in body["stale_evidence"]}
        assert str(s.id) in ids
        assert body["summary"]["strategies_with_stale_evidence"] >= 1


# ===========================================================================
# 5. Missing report detection
# ===========================================================================

class TestMissingReport:
    def test_run_without_report_is_missing_with_report_is_not(self, m86_client, m86_db, m86_owner):
        tok, pid, org = m86_owner
        now = datetime.now(timezone.utc)

        # Missing: a run but no strategy_reliability report.
        s_missing = _make_strategy(m86_db, pid, "MissingReport")
        _seed_run(m86_db, s_missing.id, run_name="r-missing", created_at=now - timedelta(days=2))

        # Present: a run with a reliability report generated AFTER the run.
        s_present = _make_strategy(m86_db, pid, "HasReport")
        _seed_run(m86_db, s_present.id, run_name="r-present", created_at=now - timedelta(days=2))
        _seed_report(m86_db, org, s_present.id, generated_at=now - timedelta(days=1))
        m86_db.commit()

        body = m86_client.get("/api/portfolio/reliability", headers=_H(tok)).json()
        assert _row_for(body, s_missing.id)["missing_report"] is True
        assert _row_for(body, s_present.id)["missing_report"] is False

        missing_ids = {m["strategy_id"] for m in body["missing_reports"]}
        assert str(s_missing.id) in missing_ids
        assert str(s_present.id) not in missing_ids


# ===========================================================================
# 6. Open alert counts
# ===========================================================================

class TestOpenAlertCounts:
    def test_open_alert_counts_in_row_and_summary(self, m86_client, m86_db, m86_owner):
        tok, pid, org = m86_owner
        s = _make_strategy(m86_db, pid, "Alerted")
        _seed_alert(m86_db, org, s.id, severity="high")
        _seed_alert(m86_db, org, s.id, severity="critical")
        # A resolved alert must not count toward open totals.
        _seed_alert(m86_db, org, s.id, severity="high", status=str(AlertStatus.resolved))
        m86_db.commit()

        body = m86_client.get("/api/portfolio/reliability", headers=_H(tok)).json()
        row = _row_for(body, s.id)
        assert row["open_alert_count"] == 2, row
        # org-wide open high/critical tally: 1 high + 1 critical open = 2.
        assert body["summary"]["open_high_critical_alerts"] == 2, body["summary"]


# ===========================================================================
# 7. Recent score change
# ===========================================================================

class TestRecentScoreChange:
    def test_delta_computed_with_two_scores_none_with_one(self, m86_client, m86_db, m86_owner):
        tok, pid, _org = m86_owner
        now = datetime.now(timezone.utc)

        # Two scores: previous 60 -> latest 75 (delta +15, up).
        s_two = _make_strategy(m86_db, pid, "TwoScores")
        _seed_score(m86_db, s_two.id, 60.0, generated_at=now - timedelta(days=2))
        _seed_score(m86_db, s_two.id, 75.0, generated_at=now - timedelta(days=1))

        # One score only -> recent_score_change None.
        s_one = _make_strategy(m86_db, pid, "OneScore")
        _seed_score(m86_db, s_one.id, 80.0, generated_at=now - timedelta(days=1))
        m86_db.commit()

        body = m86_client.get("/api/portfolio/reliability", headers=_H(tok)).json()

        change = _row_for(body, s_two.id)["recent_score_change"]
        assert change is not None
        assert change["delta"] == 15.0, change
        assert change["latest"] == 75.0
        assert change["previous"] == 60.0
        assert change["direction"] == "up"

        assert _row_for(body, s_one.id)["recent_score_change"] is None

        changed_ids = {c["strategy_id"] for c in body["recent_score_changes"]}
        assert str(s_two.id) in changed_ids
        assert str(s_one.id) not in changed_ids


# ===========================================================================
# 8-9. Export JSON / Markdown
# ===========================================================================

class TestExport:
    def test_export_json(self, m86_client, m86_db, m86_owner):
        tok, pid, _org = m86_owner
        _make_strategy(m86_db, pid, "ExportJson")
        m86_db.commit()

        r = m86_client.get(
            "/api/portfolio/reliability/export", params={"format": "json"}, headers=_H(tok)
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["format"] == "json"
        parsed = json.loads(body["content"])
        assert "summary" in parsed
        assert parsed["summary"]["total_strategies"] == 1

    def test_export_markdown(self, m86_client, m86_db, m86_owner):
        tok, pid, _org = m86_owner
        _make_strategy(m86_db, pid, "ExportMd")
        m86_db.commit()

        r = m86_client.get(
            "/api/portfolio/reliability/export", params={"format": "markdown"}, headers=_H(tok)
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["format"] == "markdown"
        assert "## Portfolio Summary" in body["content"]
        assert "not trading advice" in body["content"]


# ===========================================================================
# 10. Empty portfolio
# ===========================================================================

class TestEmptyPortfolio:
    def test_empty_portfolio_returns_200_with_zero_totals(self, m86_client, m86_owner):
        tok, _pid, _org = m86_owner
        # No strategies created.
        r = m86_client.get("/api/portfolio/reliability", headers=_H(tok))
        assert r.status_code == 200, r.text
        body = r.json()
        s = body["summary"]
        assert s["total_strategies"] == 0
        assert s["healthy_count"] == 0
        assert s["review_count"] == 0
        assert s["blocked_count"] == 0
        assert body["strategies"] == []
        assert body["worst_blockers"] == []
        assert body["stale_evidence"] == []
        assert body["missing_reports"] == []
        assert body["recent_score_changes"] == []


# ===========================================================================
# 11. RBAC
# ===========================================================================

class TestRBAC:
    def test_viewer_can_read_reliability(self, m86_client, m86_db, m86_owner):
        tok, pid, _org = m86_owner
        _make_strategy(m86_db, pid, "ViewerReadable")
        m86_db.commit()

        # Register a second user and downgrade to viewer (RBAC enabled by default).
        viewer_email = "m86-viewer@test.com"
        resp = _register(m86_client, viewer_email, "Viewer")
        assert resp.status_code == 200, resp.text
        viewer_tok = resp.json()["access_token"]
        member = (
            m86_db.query(WorkspaceMember)
            .filter(WorkspaceMember.email == viewer_email)
            .first()
        )
        member.role = "viewer"
        m86_db.commit()

        r = m86_client.get("/api/portfolio/reliability", headers=_H(viewer_tok))
        assert r.status_code == 200, r.text
        assert r.json()["summary"]["total_strategies"] == 1

    def test_unverified_user_blocked_from_writes(self, m86_client, m86_db, m86_owner):
        # Owner exists+verified from fixture; register a second, unverified user
        # with write access (default member role) -> blocked by the email gate.
        _tok, _pid, _org = m86_owner
        unverified_email = "m86-unverified@test.com"
        resp = _register(m86_client, unverified_email, "Unverified")
        assert resp.status_code == 200, resp.text
        unverified_tok = resp.json()["access_token"]
        user = m86_db.query(AuthUser).filter(AuthUser.email == unverified_email).first()
        assert user.email_verified is False
        member = (
            m86_db.query(WorkspaceMember)
            .filter(WorkspaceMember.email == unverified_email)
            .first()
        )
        member.role = "member"
        m86_db.commit()

        UH = _H(unverified_tok)
        r_refresh = m86_client.post("/api/portfolio/reliability/refresh", headers=UH)
        assert r_refresh.status_code == 403, r_refresh.text
        assert r_refresh.json()["detail"] == "Email verification required.", r_refresh.text

        r_pack = m86_client.post("/api/portfolio/reliability/weekly-review-pack", headers=UH)
        assert r_pack.status_code == 403, r_pack.text
        assert r_pack.json()["detail"] == "Email verification required.", r_pack.text

    def test_verified_owner_can_write(self, m86_client, m86_db, m86_owner):
        tok, pid, _org = m86_owner
        _make_strategy(m86_db, pid, "RefreshMe")
        m86_db.commit()

        H = _H(tok)
        r_refresh = m86_client.post("/api/portfolio/reliability/refresh", headers=H)
        assert r_refresh.status_code // 100 == 2, r_refresh.text
        assert r_refresh.json()["strategies_refreshed"] >= 1

        r_pack = m86_client.post("/api/portfolio/reliability/weekly-review-pack", headers=H)
        assert r_pack.status_code // 100 == 2, r_pack.text
        assert r_pack.json()["format"] == "markdown"
