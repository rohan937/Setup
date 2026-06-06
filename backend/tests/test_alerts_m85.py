"""M85 Alerts Engine — candidate/reconcile lifecycle test suite.

Covers the M85 alert lifecycle: candidate detection, reconcile (create / skip
duplicate / auto-resolve / snooze-expiry reactivation), the HTTP lifecycle
mutations (acknowledge / resolve / snooze) with their AlertHistory audit rows,
the strategy alert summary, and the RBAC + email-verification gates on the
mutation endpoints.

Implementation under test:
  app/services/alerts.py          generate_alerts / generate_alerts_for_strategy /
                                  reconcile_alerts / get_strategy_alert_summary /
                                  record_alert_history / candidate collectors
  app/services/alert_catalog.py   recommended_fix_for
  app/api/routes/alerts.py        endpoints + RBAC + email verification
  app/core/rbac.py                require_workspace_write_access / require_verified_email

Strategy state is seeded by the most reliable available path:
  * the public API registers a user and creates the org/project/strategy;
  * underlying evidence rows (regression runs, reliability scores, backtest
    audits, runs, reports, SLA evaluations) are inserted directly with the ORM;
  * detection is driven via ``generate_alerts_for_strategy`` (service) or the
    HTTP generate endpoint.

Fixtures are prefixed ``m85_`` to avoid colliding with conftest's
session-scoped fixtures.
"""
from __future__ import annotations

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

from app.core.constants import AlertRuleType, AlertStatus
from app.models.alert import Alert
from app.models.alert_history import AlertHistory
from app.models.auth_user import AuthUser
from app.models.backtest_audit import BacktestAudit
from app.models.organization import Organization
from app.models.project import Project
from app.models.report import Report
from app.models.regression import StrategyRegressionTestRun
from app.models.strategy import Strategy
from app.models.strategy_reliability_score import StrategyReliabilityScore
from app.models.strategy_run import StrategyRun
from app.models.workspace_member import WorkspaceMember
from app.services.alerts import (
    generate_alerts_for_strategy,
    get_strategy_alert_summary,
)

_URL = "sqlite+pysqlite:///:memory:"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def m85_engine():
    eng = create_engine(_URL, connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture()
def m85_db(m85_engine):
    s = Session(m85_engine)
    yield s
    s.close()


@pytest.fixture()
def m85_client(m85_db):
    def _override():
        yield m85_db

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
def m85_strategy(m85_client, m85_db):
    """Register the first (owner) user, verify their email, and create a fresh
    strategy via the public API.

    Returns ``(strategy_id_str, token, owner_email)``.  The owner's email is
    verified so write-mutations exercise the RBAC gate rather than M84.
    """
    resp = _register(m85_client, "m85-owner@test.com", "M85 Owner")
    assert resp.status_code == 200, resp.text
    tok = resp.json()["access_token"]

    # Verify the owner's email so alert mutations pass require_verified_email.
    owner = m85_db.query(AuthUser).filter(AuthUser.email == "m85-owner@test.com").first()
    owner.email_verified = True
    m85_db.commit()

    H = {"Authorization": f"Bearer {tok}"}
    pid = m85_client.get("/api/projects", headers=H).json()[0]["id"]
    sid = m85_client.post(
        "/api/strategies",
        json={"project_id": pid, "name": "M85 Strat", "asset_class": "equity", "status": "active"},
        headers=H,
    ).json()["id"]
    return sid, tok, "m85-owner@test.com"


# ---------------------------------------------------------------------------
# Seed helpers (direct ORM)
# ---------------------------------------------------------------------------

def _open_alerts(db, sid, rule_type=None):
    sid_hex = uuid.UUID(str(sid)).hex
    q = db.query(Alert).filter(
        Alert.strategy_id == sid_hex,
        Alert.status == str(AlertStatus.open),
    )
    if rule_type is not None:
        q = q.filter(Alert.rule_type == str(rule_type))
    return q.all()


def _seed_run(db, sid, *, run_name="run-1", created_at=None, run_type="backtest"):
    now = created_at or datetime.now(timezone.utc)
    run = StrategyRun(
        strategy_id=uuid.UUID(str(sid)),
        run_name=run_name,
        run_type=run_type,
        status="completed",
        created_at=now,
        updated_at=now,
    )
    db.add(run)
    db.flush()
    return run


def _seed_failed_regression_run(db, sid, *, created_at=None):
    now = created_at or datetime.now(timezone.utc)
    rtr = StrategyRegressionTestRun(
        strategy_id=uuid.UUID(str(sid)),
        suite_label="M85 suite",
        mode="latest_vs_baseline",
        overall_status="failed",
        passed_count=2,
        failed_count=3,
        required_failed_count=2,
        created_at=now,
        updated_at=now,
    )
    db.add(rtr)
    db.flush()
    return rtr


def _seed_reliability_score(db, sid, score, *, generated_at):
    rs = StrategyReliabilityScore(
        strategy_id=uuid.UUID(str(sid)),
        overall_score=score,
        status="review",
        generated_at=generated_at,
        created_at=generated_at,
        updated_at=generated_at,
    )
    db.add(rs)
    db.flush()
    return rs


def _seed_backtest_audit(db, sid, trust_score, *, created_at, run_name="bt-run"):
    run = _seed_run(db, sid, run_name=run_name, created_at=created_at)
    audit = BacktestAudit(
        strategy_run_id=run.id,
        trust_score=trust_score,
        overall_status="weak",
        summary="Seeded low backtest trust.",
        created_at=created_at,
        updated_at=created_at,
    )
    db.add(audit)
    db.flush()
    return run, audit


# ===========================================================================
# 1-5: Alert generation per condition
# ===========================================================================

class TestAlertGenerationConditions:
    def test_regression_test_failed_alert(self, m85_strategy, m85_db):
        """1. A failed regression run yields an open regression_test_failed alert
        with a non-empty recommended_fix."""
        sid, _tok, _ = m85_strategy
        _seed_failed_regression_run(m85_db, sid)
        m85_db.commit()

        generate_alerts_for_strategy(m85_db, str(sid))
        m85_db.commit()

        alerts = _open_alerts(m85_db, sid, AlertRuleType.regression_test_failed)
        assert len(alerts) == 1, "expected exactly one regression_test_failed alert"
        assert alerts[0].recommended_fix, "recommended_fix must be non-empty"

    def test_evidence_sla_breached_alert(self, m85_strategy, m85_db):
        """2. A breached SLA evaluation yields an open evidence_sla_breached alert.

        We insert an EvidenceSLAEvaluation row in 'breach' status directly so the
        candidate check reads it as the latest evaluation.
        """
        from app.models.evidence_sla import EvidenceSLAPolicy, EvidenceSLAEvaluation

        sid, _tok, _ = m85_strategy
        now = datetime.now(timezone.utc)
        policy = EvidenceSLAPolicy(
            strategy_id=uuid.UUID(str(sid)),
            name="M85 SLA",
            is_active=True,
            policy_json={"rules": []},
            created_at=now,
            updated_at=now,
        )
        m85_db.add(policy)
        m85_db.flush()
        ev = EvidenceSLAEvaluation(
            strategy_id=uuid.UUID(str(sid)),
            policy_id=policy.id,
            overall_status="breach",
            passed_count=0,
            warning_count=0,
            violated_count=2,
            critical_violation_count=1,
            created_at=now,
        )
        m85_db.add(ev)
        m85_db.commit()

        generate_alerts_for_strategy(m85_db, str(sid))
        m85_db.commit()

        alerts = _open_alerts(m85_db, sid, AlertRuleType.evidence_sla_breached)
        assert len(alerts) == 1, "expected one evidence_sla_breached alert"
        assert alerts[0].recommended_fix

    def test_report_missing_after_latest_run_alert(self, m85_strategy, m85_db):
        """3. A strategy with a run but no strategy_reliability report after it
        yields a reliability_report_missing alert."""
        sid, _tok, _ = m85_strategy
        _seed_run(m85_db, sid, run_name="latest-run")
        m85_db.commit()

        generate_alerts_for_strategy(m85_db, str(sid))
        m85_db.commit()

        alerts = _open_alerts(m85_db, sid, AlertRuleType.reliability_report_missing)
        assert len(alerts) == 1, "expected one reliability_report_missing alert"
        assert alerts[0].recommended_fix

    def test_reliability_score_drop_alert(self, m85_strategy, m85_db):
        """4. Two reliability scores with a downward delta (>= 15) yield a
        reliability_score_deteriorating alert."""
        sid, _tok, _ = m85_strategy
        now = datetime.now(timezone.utc)
        _seed_reliability_score(m85_db, sid, 85.0, generated_at=now - timedelta(days=2))
        _seed_reliability_score(m85_db, sid, 60.0, generated_at=now - timedelta(days=1))
        m85_db.commit()

        generate_alerts_for_strategy(m85_db, str(sid))
        m85_db.commit()

        alerts = _open_alerts(m85_db, sid, AlertRuleType.reliability_score_deteriorating)
        assert len(alerts) == 1, "expected one reliability_score_deteriorating alert"
        assert alerts[0].recommended_fix

    def test_backtest_trust_drop_alert(self, m85_strategy, m85_db):
        """5. A low latest backtest trust score yields a
        backtest_trust_deteriorating alert."""
        sid, _tok, _ = m85_strategy
        now = datetime.now(timezone.utc)
        # Earlier higher audit, then a lower latest one (declining + below 40).
        _seed_backtest_audit(m85_db, sid, 80, created_at=now - timedelta(days=2), run_name="bt-old")
        _seed_backtest_audit(m85_db, sid, 30, created_at=now - timedelta(days=1), run_name="bt-new")
        m85_db.commit()

        generate_alerts_for_strategy(m85_db, str(sid))
        m85_db.commit()

        alerts = _open_alerts(m85_db, sid, AlertRuleType.backtest_trust_deteriorating)
        assert len(alerts) == 1, "expected one backtest_trust_deteriorating alert"
        assert alerts[0].recommended_fix


# ===========================================================================
# 6: No duplicate open alerts on repeated generation
# ===========================================================================

class TestNoDuplicateAlerts:
    def test_repeated_generation_no_duplicates(self, m85_strategy, m85_db):
        sid, _tok, _ = m85_strategy
        _seed_failed_regression_run(m85_db, sid)
        m85_db.commit()

        first = generate_alerts_for_strategy(m85_db, str(sid))
        m85_db.commit()
        assert first["alerts_created"] >= 1
        open_after_first = len(_open_alerts(m85_db, sid))

        second = generate_alerts_for_strategy(m85_db, str(sid))
        m85_db.commit()
        open_after_second = len(_open_alerts(m85_db, sid))

        # The already-firing regression condition must not create a new alert.
        reg_open = _open_alerts(m85_db, sid, AlertRuleType.regression_test_failed)
        assert len(reg_open) == 1, "regression alert must not be duplicated"
        assert second["alerts_skipped_duplicate"] >= 1
        assert open_after_second == open_after_first, "total open count must be stable"


# ===========================================================================
# 7-8: acknowledge / resolve write timestamps + history
# ===========================================================================

class TestAcknowledgeResolve:
    def _make_alert(self, m85_db, sid):
        _seed_failed_regression_run(m85_db, sid)
        m85_db.commit()
        generate_alerts_for_strategy(m85_db, str(sid))
        m85_db.commit()
        return _open_alerts(m85_db, sid, AlertRuleType.regression_test_failed)[0]

    def test_acknowledge_sets_status_and_history(self, m85_strategy, m85_db, m85_client):
        sid, tok, _ = m85_strategy
        alert = self._make_alert(m85_db, sid)
        H = {"Authorization": f"Bearer {tok}"}

        r = m85_client.post(
            f"/api/alerts/{alert.id}/acknowledge", json={"note": "looking into it"}, headers=H
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "acknowledged"
        assert body["acknowledged_at"] is not None

        m85_db.expire_all()
        hist = (
            m85_db.query(AlertHistory)
            .filter(AlertHistory.alert_id == str(alert.id))
            .all()
        )
        actions = {h.action for h in hist}
        assert "acknowledged" in actions, f"history actions: {actions}"

    def test_resolve_sets_status_and_history(self, m85_strategy, m85_db, m85_client):
        sid, tok, _ = m85_strategy
        alert = self._make_alert(m85_db, sid)
        H = {"Authorization": f"Bearer {tok}"}

        r = m85_client.post(
            f"/api/alerts/{alert.id}/resolve", json={"note": "fixed"}, headers=H
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "resolved"
        assert body["resolved_at"] is not None

        m85_db.expire_all()
        hist = (
            m85_db.query(AlertHistory)
            .filter(AlertHistory.alert_id == str(alert.id))
            .all()
        )
        actions = {h.action for h in hist}
        assert "resolved" in actions, f"history actions: {actions}"


# ===========================================================================
# 9: snooze -> not active in summary -> reactivate on expiry
# ===========================================================================

class TestSnoozeLifecycle:
    def test_snooze_then_expiry_reactivates(self, m85_strategy, m85_db, m85_client):
        sid, tok, _ = m85_strategy
        _seed_failed_regression_run(m85_db, sid)
        m85_db.commit()
        generate_alerts_for_strategy(m85_db, str(sid))
        m85_db.commit()
        alert = _open_alerts(m85_db, sid, AlertRuleType.regression_test_failed)[0]
        H = {"Authorization": f"Bearer {tok}"}

        # A single failed regression run may also trigger other lifecycle alerts
        # (e.g. reliability_report_missing); count open BEFORE snoozing so we can
        # assert the snoozed alert specifically drops out of the open tally.
        open_before = get_strategy_alert_summary(m85_db, str(sid))["open"]

        # Snooze 48h into the future.
        future = (datetime.now(timezone.utc) + timedelta(hours=48)).isoformat()
        r = m85_client.post(
            f"/api/alerts/{alert.id}/snooze",
            json={"snoozed_until": future, "note": "snooze"},
            headers=H,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "snoozed"
        assert body["snoozed_until"] is not None
        snoozed_until = datetime.fromisoformat(body["snoozed_until"].replace("Z", "+00:00"))
        if snoozed_until.tzinfo is None:
            snoozed_until = snoozed_until.replace(tzinfo=timezone.utc)
        assert snoozed_until > datetime.now(timezone.utc)

        # Summary must NOT count the future-snoozed alert as open; the open count
        # drops by exactly one and the snoozed bucket holds it.
        summary = get_strategy_alert_summary(m85_db, str(sid))
        assert summary["open"] == open_before - 1, (
            f"snoozing must remove the alert from the open tally "
            f"(before={open_before}, after={summary['open']})"
        )
        assert summary["snoozed"] == 1, summary
        m85_db.expire_all()
        snoozed_alert = m85_db.query(Alert).filter(Alert.id == alert.id).first()
        assert str(snoozed_alert.status) == str(AlertStatus.snoozed)

        # Backdate snoozed_until into the past, then regenerate (condition still
        # firing) -> alert reactivates to open + a snooze_expired history row.
        m85_db.expire_all()
        db_alert = m85_db.query(Alert).filter(Alert.id == alert.id).first()
        db_alert.snoozed_until = datetime.now(timezone.utc) - timedelta(hours=1)
        m85_db.commit()

        generate_alerts_for_strategy(m85_db, str(sid))
        m85_db.commit()

        m85_db.expire_all()
        db_alert = m85_db.query(Alert).filter(Alert.id == alert.id).first()
        assert str(db_alert.status) == str(AlertStatus.open), "expired snooze must reactivate to open"

        hist = (
            m85_db.query(AlertHistory)
            .filter(AlertHistory.alert_id == str(alert.id))
            .all()
        )
        actions = {h.action for h in hist}
        assert "snooze_expired" in actions, f"history actions: {actions}"


# ===========================================================================
# 10-11: RBAC on mutation (viewer cannot, owner can)
# ===========================================================================

class TestMutationRBAC:
    def test_viewer_cannot_mutate_alert(self, m85_client, m85_db, m85_strategy):
        """10. A genuine viewer member (RBAC enabled by default) is rejected with
        403 when acknowledging/resolving an alert.

        Approach: rbac_enabled defaults to True, so we register a second user and
        downgrade their linked WorkspaceMember to 'viewer'. Their JWT resolves to
        that viewer membership; require_workspace_write_access then denies the
        mutation with 403 BEFORE the alert is even looked up.
        """
        sid, _owner_tok, _ = m85_strategy
        # Build a real open alert to target.
        _seed_failed_regression_run(m85_db, sid)
        m85_db.commit()
        generate_alerts_for_strategy(m85_db, str(sid))
        m85_db.commit()
        alert = _open_alerts(m85_db, sid, AlertRuleType.regression_test_failed)[0]

        # Register a viewer (owner already exists from m85_strategy bootstrap).
        viewer_email = "m85-viewer@test.com"
        resp = _register(m85_client, viewer_email, "Viewer")
        assert resp.status_code == 200, resp.text
        viewer_tok = resp.json()["access_token"]
        member = (
            m85_db.query(WorkspaceMember)
            .filter(WorkspaceMember.email == viewer_email)
            .first()
        )
        member.role = "viewer"
        # Verify the viewer's email too so the 403 is unambiguously the RBAC
        # write-access gate (not the email-verification gate).
        viewer_user = m85_db.query(AuthUser).filter(AuthUser.email == viewer_email).first()
        viewer_user.email_verified = True
        m85_db.commit()

        VH = {"Authorization": f"Bearer {viewer_tok}"}
        r_ack = m85_client.post(f"/api/alerts/{alert.id}/acknowledge", json={}, headers=VH)
        assert r_ack.status_code == 403, r_ack.text
        r_res = m85_client.post(f"/api/alerts/{alert.id}/resolve", json={}, headers=VH)
        assert r_res.status_code == 403, r_res.text

    def test_owner_can_mutate_alert(self, m85_client, m85_db, m85_strategy):
        """11. The owner (write access + verified email) can acknowledge and
        resolve an alert -> 2xx."""
        sid, tok, _ = m85_strategy
        _seed_failed_regression_run(m85_db, sid)
        m85_db.commit()
        generate_alerts_for_strategy(m85_db, str(sid))
        m85_db.commit()
        alert = _open_alerts(m85_db, sid, AlertRuleType.regression_test_failed)[0]

        H = {"Authorization": f"Bearer {tok}"}
        r_ack = m85_client.post(f"/api/alerts/{alert.id}/acknowledge", json={}, headers=H)
        assert r_ack.status_code == 200, r_ack.text
        r_res = m85_client.post(f"/api/alerts/{alert.id}/resolve", json={}, headers=H)
        assert r_res.status_code == 200, r_res.text


# ===========================================================================
# 12: strategy alert summary counts
# ===========================================================================

class TestStrategyAlertSummary:
    def test_summary_counts(self, m85_client, m85_db, m85_strategy):
        """12. GET /api/strategies/{id}/alerts/summary returns correct status and
        severity counts."""
        sid, tok, _ = m85_strategy
        H = {"Authorization": f"Bearer {tok}"}
        now = datetime.now(timezone.utc)
        sid_hex = uuid.UUID(str(sid)).hex
        org_id = str(m85_db.query(Organization).first().id)

        def _alert(status, severity, **extra):
            a = Alert(
                organization_id=org_id,
                rule_type=str(AlertRuleType.regression_test_failed),
                status=status,
                severity=severity,
                title=f"{status}/{severity}",
                source_type="strategy",
                source_id=str(sid),
                strategy_id=sid_hex,
                triggered_at=now,
                **extra,
            )
            m85_db.add(a)
            return a

        # 2 open (1 high, 1 medium), 1 acknowledged, 1 snoozed, 1 resolved.
        _alert(str(AlertStatus.open), "high")
        _alert(str(AlertStatus.open), "medium")
        _alert(str(AlertStatus.acknowledged), "high")
        _alert(str(AlertStatus.snoozed), "low", snoozed_until=now + timedelta(hours=10))
        _alert(str(AlertStatus.resolved), "critical", resolved_at=now)
        m85_db.commit()

        r = m85_client.get(f"/api/strategies/{sid}/alerts/summary", headers=H)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["open"] == 2, body
        assert body["acknowledged"] == 1, body
        assert body["snoozed"] == 1, body
        assert body["resolved"] == 1, body
        assert body["by_severity"]["high"] == 1, body
        assert body["by_severity"]["medium"] == 1, body
        # Severity is only counted for OPEN alerts.
        assert body["by_severity"]["critical"] == 0, body
        assert body["by_severity"]["low"] == 0, body


# ===========================================================================
# 13: auto-resolve when condition fixed
# ===========================================================================

class TestAutoResolve:
    def test_auto_resolve_on_fix(self, m85_strategy, m85_db):
        """13. A previously-firing condition that is later repaired causes the open
        alert to auto-resolve (status 'resolved' + AlertHistory 'auto_resolved')."""
        sid, _tok, _ = m85_strategy
        rtr = _seed_failed_regression_run(m85_db, sid)
        m85_db.commit()

        generate_alerts_for_strategy(m85_db, str(sid))
        m85_db.commit()
        alert = _open_alerts(m85_db, sid, AlertRuleType.regression_test_failed)[0]
        alert_id = str(alert.id)

        # Repair the underlying state: the regression run now passes.
        m85_db.expire_all()
        db_rtr = m85_db.query(StrategyRegressionTestRun).filter(
            StrategyRegressionTestRun.id == rtr.id
        ).first()
        db_rtr.overall_status = "passed"
        db_rtr.failed_count = 0
        db_rtr.required_failed_count = 0
        m85_db.commit()

        generate_alerts_for_strategy(m85_db, str(sid))
        m85_db.commit()

        m85_db.expire_all()
        resolved = m85_db.query(Alert).filter(Alert.id == alert_id).first()
        assert str(resolved.status) == str(AlertStatus.resolved), "alert must auto-resolve"
        assert resolved.resolved_at is not None

        hist = m85_db.query(AlertHistory).filter(AlertHistory.alert_id == alert_id).all()
        actions = {h.action for h in hist}
        assert "auto_resolved" in actions, f"history actions: {actions}"


# ===========================================================================
# 14: unverified user blocked from mutation
# ===========================================================================

class TestEmailVerificationGate:
    def test_unverified_user_blocked(self, m85_client, m85_db, m85_strategy):
        """14. A JWT-authenticated user with an UNVERIFIED email is blocked from
        mutating an alert -> 403 'Email verification required.'

        The bootstrap owner from m85_strategy is verified and has write access; we
        register a SECOND user, grant them write access (member role, which they
        already have by default), but leave their email unverified. The mutation
        must fail the require_verified_email gate.
        """
        sid, _owner_tok, _ = m85_strategy
        _seed_failed_regression_run(m85_db, sid)
        m85_db.commit()
        generate_alerts_for_strategy(m85_db, str(sid))
        m85_db.commit()
        alert = _open_alerts(m85_db, sid, AlertRuleType.regression_test_failed)[0]

        # Second user: default role is 'member' (write access), email unverified.
        unverified_email = "m85-unverified@test.com"
        resp = _register(m85_client, unverified_email, "Unverified")
        assert resp.status_code == 200, resp.text
        unverified_tok = resp.json()["access_token"]
        user = m85_db.query(AuthUser).filter(AuthUser.email == unverified_email).first()
        assert user.email_verified is False, "second user should be unverified by default"
        member = (
            m85_db.query(WorkspaceMember)
            .filter(WorkspaceMember.email == unverified_email)
            .first()
        )
        # Ensure write access so the 403 is the email gate, not the RBAC gate.
        member.role = "member"
        m85_db.commit()

        H = {"Authorization": f"Bearer {unverified_tok}"}
        r = m85_client.post(f"/api/alerts/{alert.id}/acknowledge", json={}, headers=H)
        assert r.status_code == 403, r.text
        assert r.json()["detail"] == "Email verification required.", r.text
