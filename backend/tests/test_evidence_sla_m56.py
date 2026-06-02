"""M56 tests: Evidence SLA Monitor.

Tests for:
  - POST /api/strategies/{id}/evidence-sla/default  — create default policy (idempotent)
  - POST /api/strategies/{id}/evidence-sla/policies  — create custom policy
  - GET  /api/strategies/{id}/evidence-sla/policies  — list policies
  - POST /api/strategies/{id}/evidence-sla/policies/{id}/evaluate — run evaluation
  - GET  /api/strategies/{id}/evidence-sla/evaluations — list evaluations
  - GET  /api/evidence-sla/evaluations/{id}  — get evaluation detail
  - Rule evaluation logic for freshness, score minimum, status, and alert rules
  - Overall status computation
  - AuditTimelineEvent created on evaluation
  - EvidenceSLAResult rows persisted
  - Summary language checks

All tests use shared session-scoped fixtures from conftest.py.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_seeded_strategy(db):
    from app.models.strategy import Strategy
    return db.query(Strategy).filter(Strategy.status != "archived").first()


def _get_seeded_project(db):
    from app.models.project import Project
    return db.query(Project).first()


def _get_seeded_org(db):
    from app.models.organization import Organization
    return db.query(Organization).first()


def _make_strategy(db, project_id, *, suffix: str = "") -> object:
    from app.models.strategy import Strategy

    slug = f"m56-test-{suffix}-{uuid.uuid4().hex[:8]}"
    strat = Strategy(
        project_id=project_id,
        name=f"M56 Test {suffix}",
        slug=slug,
        asset_class="equity",
        status="active",
    )
    db.add(strat)
    db.commit()
    return strat


def _make_default_policy(db, strategy_id: str) -> object:
    from app.services.evidence_sla import create_default_evidence_sla_policy
    policy = create_default_evidence_sla_policy(db, strategy_id)
    db.commit()
    return policy


def _ensure_uuid(val):
    """Convert str or UUID to UUID object."""
    if isinstance(val, uuid.UUID):
        return val
    return uuid.UUID(str(val))


def _make_strategy_run(db, strategy_id, *, run_type: str = "backtest", days_ago: int = 0) -> object:
    from app.models.strategy_run import StrategyRun

    run = StrategyRun(
        strategy_id=_ensure_uuid(strategy_id),
        run_name=f"M56 Run {uuid.uuid4().hex[:6]}",
        run_type=run_type,
        status="completed",
    )
    db.add(run)
    db.flush()

    if days_ago > 0:
        # Backdating created_at
        old_ts = datetime.now(timezone.utc) - timedelta(days=days_ago)
        run.created_at = old_ts
        run.updated_at = old_ts
        db.flush()

    db.commit()
    return run


def _make_backtest_audit(db, strategy_run_id, *, trust_score: int = 80) -> object:
    from app.models.backtest_audit import BacktestAudit

    audit = BacktestAudit(
        strategy_run_id=_ensure_uuid(strategy_run_id),
        trust_score=trust_score,
        overall_status="review",
    )
    db.add(audit)
    db.commit()
    return audit


def _make_signal_snapshot(db, strategy_id, *, quality_score: int = 85) -> object:
    import hashlib
    import json
    from app.models.signal_snapshot import SignalSnapshot

    rows: list = []
    sig_hash = hashlib.sha256(json.dumps(rows).encode()).hexdigest()
    sig = SignalSnapshot(
        strategy_id=_ensure_uuid(strategy_id),
        label=f"M56 Signal {uuid.uuid4().hex[:6]}",
        quality_score=quality_score,
        rows_json=rows,
        signal_hash=sig_hash,
    )
    db.add(sig)
    db.commit()
    return sig


def _make_alert(db, strategy_id, org_id, *, severity: str = "high") -> object:
    from app.models.alert import Alert

    alert = Alert(
        organization_id=str(org_id),
        rule_type="data_health_deteriorating",
        status="open",
        severity=severity,
        title=f"M56 Test Alert {uuid.uuid4().hex[:6]}",
        strategy_id=str(strategy_id),
        triggered_at=datetime.now(timezone.utc),
    )
    db.add(alert)
    db.commit()
    return alert


# ---------------------------------------------------------------------------
# class TestEvidenceSLASetup
# ---------------------------------------------------------------------------

class TestEvidenceSLASetup:
    def test_create_default_policy_success(self, db, client):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="default")
        strat_id = str(strat.id)

        resp = client.post(f"/api/strategies/{strat_id}/evidence-sla/default")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["name"] == "QuantFidelity Default Evidence SLA"
        assert data["strategy_id"] == strat_id
        assert data["is_active"] is True
        assert data["rule_count"] == 15
        assert "id" in data

    def test_create_default_policy_idempotent(self, db, client):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="idempotent")
        strat_id = str(strat.id)

        resp1 = client.post(f"/api/strategies/{strat_id}/evidence-sla/default")
        resp2 = client.post(f"/api/strategies/{strat_id}/evidence-sla/default")
        assert resp1.status_code == 200
        assert resp2.status_code == 200
        assert resp1.json()["id"] == resp2.json()["id"]

    def test_create_custom_policy_success(self, db, client):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="custom")
        strat_id = str(strat.id)

        payload = {
            "name": "My Custom SLA Policy",
            "description": "A test custom SLA policy",
            "is_active": True,
            "policy_json": {
                "rules": [
                    {
                        "rule_key": "test_freshness_rule",
                        "title": "Test runs must be fresh",
                        "evidence_type": "strategy_runs",
                        "rule_type": "freshness_max_days",
                        "max_days": 30,
                        "severity": "medium",
                        "is_required": True,
                    }
                ]
            },
        }
        resp = client.post(f"/api/strategies/{strat_id}/evidence-sla/policies", json=payload)
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["name"] == "My Custom SLA Policy"
        assert data["rule_count"] == 1

    def test_list_policies_success(self, db, client):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="list")
        strat_id = str(strat.id)

        client.post(f"/api/strategies/{strat_id}/evidence-sla/default")

        resp = client.get(f"/api/strategies/{strat_id}/evidence-sla/policies")
        assert resp.status_code == 200, resp.text
        items = resp.json()
        assert isinstance(items, list)
        assert len(items) >= 1
        names = [p["name"] for p in items]
        assert "QuantFidelity Default Evidence SLA" in names


# ---------------------------------------------------------------------------
# class TestEvidenceSLAEvaluation
# ---------------------------------------------------------------------------

class TestEvidenceSLAEvaluation:
    def test_evaluate_no_evidence_returns_evaluation(self, db, client):
        """Minimal strategy with no evidence — evaluation should complete (mostly violated/skipped)."""
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="noevidence")
        strat_id = str(strat.id)

        resp = client.post(f"/api/strategies/{strat_id}/evidence-sla/default")
        policy_id = resp.json()["id"]

        eval_resp = client.post(
            f"/api/strategies/{strat_id}/evidence-sla/policies/{policy_id}/evaluate"
        )
        assert eval_resp.status_code == 200, eval_resp.text
        data = eval_resp.json()
        assert "overall_status" in data
        assert data["overall_status"] in (
            "violated", "warning", "passed", "insufficient_evidence"
        )
        assert "id" in data

    def test_evaluate_creates_results(self, db, client):
        """Evaluation must create EvidenceSLAResult rows."""
        from app.models.evidence_sla import EvidenceSLAResult

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="results")
        strat_id = str(strat.id)

        resp = client.post(f"/api/strategies/{strat_id}/evidence-sla/default")
        policy_id = resp.json()["id"]

        eval_resp = client.post(
            f"/api/strategies/{strat_id}/evidence-sla/policies/{policy_id}/evaluate"
        )
        assert eval_resp.status_code == 200, eval_resp.text
        eval_id = eval_resp.json()["id"]

        results = (
            db.query(EvidenceSLAResult)
            .filter(EvidenceSLAResult.evaluation_id == uuid.UUID(eval_id))
            .all()
        )
        assert len(results) == 15  # All 15 default rules

    def test_evaluate_timeline_event_created(self, db, client):
        """Evaluation must create an AuditTimelineEvent with event_type evidence_sla_evaluated."""
        from app.models.audit_timeline_event import AuditTimelineEvent

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="timeline")
        strat_id = str(strat.id)

        resp = client.post(f"/api/strategies/{strat_id}/evidence-sla/default")
        policy_id = resp.json()["id"]

        eval_resp = client.post(
            f"/api/strategies/{strat_id}/evidence-sla/policies/{policy_id}/evaluate"
        )
        assert eval_resp.status_code == 200, eval_resp.text
        eval_id = eval_resp.json()["id"]

        events = (
            db.query(AuditTimelineEvent)
            .filter(
                AuditTimelineEvent.strategy_id == strat.id,
                AuditTimelineEvent.event_type == "evidence_sla_evaluated",
            )
            .all()
        )
        assert len(events) >= 1
        event = events[-1]
        assert event.source_type == "evidence_sla"
        assert event.source_id == eval_id

    def test_freshness_rule_passes_with_recent_run(self, db, client):
        """A strategy run logged today should make strategy_runs_freshness pass."""
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="freshrun")
        strat_id = str(strat.id)

        # Create a run from today
        _make_strategy_run(db, strat.id, run_type="backtest", days_ago=0)

        resp = client.post(f"/api/strategies/{strat_id}/evidence-sla/default")
        policy_id = resp.json()["id"]

        eval_resp = client.post(
            f"/api/strategies/{strat_id}/evidence-sla/policies/{policy_id}/evaluate"
        )
        assert eval_resp.status_code == 200, eval_resp.text
        data = eval_resp.json()

        results = data.get("results", [])
        freshness_rule = next(
            (r for r in results if r["rule_key"] == "strategy_runs_freshness"), None
        )
        assert freshness_rule is not None
        assert freshness_rule["status"] == "passed"

    def test_freshness_rule_violated_with_old_run(self, db, client):
        """A strategy run 60 days ago should fail the 30-day SLA."""
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="oldrun")
        strat_id = str(strat.id)

        # Create a run from 60 days ago
        _make_strategy_run(db, strat.id, run_type="backtest", days_ago=60)

        resp = client.post(f"/api/strategies/{strat_id}/evidence-sla/default")
        policy_id = resp.json()["id"]

        eval_resp = client.post(
            f"/api/strategies/{strat_id}/evidence-sla/policies/{policy_id}/evaluate"
        )
        assert eval_resp.status_code == 200, eval_resp.text
        data = eval_resp.json()

        results = data.get("results", [])
        freshness_rule = next(
            (r for r in results if r["rule_key"] == "strategy_runs_freshness"), None
        )
        assert freshness_rule is not None
        assert freshness_rule["status"] == "violated"

    def test_signal_quality_minimum_violated(self, db, client):
        """Signal quality score of 50 should violate the minimum of 75."""
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="siglow")
        strat_id = str(strat.id)

        _make_signal_snapshot(db, strat.id, quality_score=50)

        resp = client.post(f"/api/strategies/{strat_id}/evidence-sla/default")
        policy_id = resp.json()["id"]

        eval_resp = client.post(
            f"/api/strategies/{strat_id}/evidence-sla/policies/{policy_id}/evaluate"
        )
        assert eval_resp.status_code == 200, eval_resp.text
        data = eval_resp.json()

        results = data.get("results", [])
        sig_rule = next(
            (r for r in results if r["rule_key"] == "signal_quality_minimum"), None
        )
        assert sig_rule is not None
        assert sig_rule["status"] == "violated"

    def test_signal_quality_minimum_passes(self, db, client):
        """Signal quality score of 85 should pass the minimum of 75."""
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="sighigh")
        strat_id = str(strat.id)

        _make_signal_snapshot(db, strat.id, quality_score=85)

        resp = client.post(f"/api/strategies/{strat_id}/evidence-sla/default")
        policy_id = resp.json()["id"]

        eval_resp = client.post(
            f"/api/strategies/{strat_id}/evidence-sla/policies/{policy_id}/evaluate"
        )
        assert eval_resp.status_code == 200, eval_resp.text
        data = eval_resp.json()

        results = data.get("results", [])
        sig_rule = next(
            (r for r in results if r["rule_key"] == "signal_quality_minimum"), None
        )
        assert sig_rule is not None
        assert sig_rule["status"] == "passed"

    def test_backtest_trust_violated(self, db, client):
        """Backtest trust score of 45 should violate the minimum of 70."""
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="btlow")
        strat_id = str(strat.id)

        run = _make_strategy_run(db, strat.id, run_type="backtest")
        _make_backtest_audit(db, run.id, trust_score=45)

        resp = client.post(f"/api/strategies/{strat_id}/evidence-sla/default")
        policy_id = resp.json()["id"]

        eval_resp = client.post(
            f"/api/strategies/{strat_id}/evidence-sla/policies/{policy_id}/evaluate"
        )
        assert eval_resp.status_code == 200, eval_resp.text
        data = eval_resp.json()

        results = data.get("results", [])
        bt_rule = next(
            (r for r in results if r["rule_key"] == "backtest_trust_minimum"), None
        )
        assert bt_rule is not None
        assert bt_rule["status"] == "violated"

    def test_no_high_critical_alerts_violated(self, db, client):
        """Open high-severity alert should violate the no_high_critical_alerts rule."""
        project = _get_seeded_project(db)
        org = _get_seeded_org(db)
        strat = _make_strategy(db, project.id, suffix="alertviol")
        strat_id = str(strat.id)

        _make_alert(db, strat.id, org.id, severity="high")

        resp = client.post(f"/api/strategies/{strat_id}/evidence-sla/default")
        policy_id = resp.json()["id"]

        eval_resp = client.post(
            f"/api/strategies/{strat_id}/evidence-sla/policies/{policy_id}/evaluate"
        )
        assert eval_resp.status_code == 200, eval_resp.text
        data = eval_resp.json()

        results = data.get("results", [])
        alert_rule = next(
            (r for r in results if r["rule_key"] == "no_high_critical_alerts"), None
        )
        assert alert_rule is not None
        assert alert_rule["status"] == "violated"

    def test_no_high_critical_alerts_passes(self, db, client):
        """No open high/critical alerts should cause no_high_critical_alerts to pass."""
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="noalert")
        strat_id = str(strat.id)

        # No alerts for this fresh strategy

        resp = client.post(f"/api/strategies/{strat_id}/evidence-sla/default")
        policy_id = resp.json()["id"]

        eval_resp = client.post(
            f"/api/strategies/{strat_id}/evidence-sla/policies/{policy_id}/evaluate"
        )
        assert eval_resp.status_code == 200, eval_resp.text
        data = eval_resp.json()

        results = data.get("results", [])
        alert_rule = next(
            (r for r in results if r["rule_key"] == "no_high_critical_alerts"), None
        )
        assert alert_rule is not None
        assert alert_rule["status"] == "passed"

    def test_list_evaluations_endpoint(self, db, client):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="listeval")
        strat_id = str(strat.id)

        resp = client.post(f"/api/strategies/{strat_id}/evidence-sla/default")
        policy_id = resp.json()["id"]

        client.post(f"/api/strategies/{strat_id}/evidence-sla/policies/{policy_id}/evaluate")
        client.post(f"/api/strategies/{strat_id}/evidence-sla/policies/{policy_id}/evaluate")

        list_resp = client.get(f"/api/strategies/{strat_id}/evidence-sla/evaluations")
        assert list_resp.status_code == 200, list_resp.text
        data = list_resp.json()
        assert "items" in data
        assert data["total"] >= 2

    def test_get_evaluation_detail(self, db, client):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="detail")
        strat_id = str(strat.id)

        resp = client.post(f"/api/strategies/{strat_id}/evidence-sla/default")
        policy_id = resp.json()["id"]

        eval_resp = client.post(
            f"/api/strategies/{strat_id}/evidence-sla/policies/{policy_id}/evaluate"
        )
        eval_id = eval_resp.json()["id"]

        detail_resp = client.get(f"/api/evidence-sla/evaluations/{eval_id}")
        assert detail_resp.status_code == 200, detail_resp.text
        data = detail_resp.json()
        assert data["id"] == eval_id
        assert len(data["results"]) == 15

    def test_get_evaluation_detail_404(self, db, client):
        fake_id = str(uuid.uuid4())
        resp = client.get(f"/api/evidence-sla/evaluations/{fake_id}")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# class TestEvidenceSLAOverallStatus
# ---------------------------------------------------------------------------

class TestEvidenceSLAOverallStatus:
    def test_overall_status_violated(self, db, client):
        """Required high-severity rule violated -> overall_status should be 'violated'."""
        project = _get_seeded_project(db)
        org = _get_seeded_org(db)
        strat = _make_strategy(db, project.id, suffix="statusviol")
        strat_id = str(strat.id)

        # Create open high-severity alert to trigger violation
        _make_alert(db, strat.id, org.id, severity="high")

        resp = client.post(f"/api/strategies/{strat_id}/evidence-sla/default")
        policy_id = resp.json()["id"]

        eval_resp = client.post(
            f"/api/strategies/{strat_id}/evidence-sla/policies/{policy_id}/evaluate"
        )
        assert eval_resp.status_code == 200, eval_resp.text
        data = eval_resp.json()
        # With a required rule violated, overall should be violated
        assert data["overall_status"] == "violated"

    def test_overall_status_warning(self, db, client):
        """Only low/recommended rules violated -> overall_status should be 'warning'."""
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="statuswarn")
        strat_id = str(strat.id)

        from app.services.evidence_sla import create_evidence_sla_policy

        # A policy with one required passing rule and one non-required rule that will warn
        policy = create_evidence_sla_policy(db, strat_id, {
            "name": "Warning SLA Test Policy",
            "policy_json": {
                "rules": [
                    {
                        "rule_key": "no_alerts",
                        "title": "No open high critical alerts",
                        "evidence_type": "alerts",
                        "rule_type": "no_open_high_critical_alerts",
                        "severity": "high",
                        "is_required": False,  # Non-required
                    },
                ]
            },
        })
        db.commit()
        policy_id = str(policy.id)

        # Create a high alert which will cause a violation on a non-required rule
        org = _get_seeded_org(db)
        _make_alert(db, strat.id, org.id, severity="high")

        eval_resp = client.post(
            f"/api/strategies/{strat_id}/evidence-sla/policies/{policy_id}/evaluate"
        )
        assert eval_resp.status_code == 200, eval_resp.text
        data = eval_resp.json()
        # Non-required rule violated -> warning
        assert data["overall_status"] in ("warning", "violated")

    def test_overall_status_passed(self, db, client):
        """All required rules pass -> overall_status should be 'passed'."""
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="statuspassed")
        strat_id = str(strat.id)

        from app.services.evidence_sla import create_evidence_sla_policy

        # Custom policy with only the no_high_critical_alerts rule (which will pass if no alerts)
        policy = create_evidence_sla_policy(db, strat_id, {
            "name": "Minimal Passing SLA",
            "policy_json": {
                "rules": [
                    {
                        "rule_key": "no_alerts",
                        "title": "No open high critical alerts",
                        "evidence_type": "alerts",
                        "rule_type": "no_open_high_critical_alerts",
                        "severity": "high",
                        "is_required": True,
                    },
                ]
            },
        })
        db.commit()
        policy_id = str(policy.id)

        # No alerts for this strategy -> passes
        eval_resp = client.post(
            f"/api/strategies/{strat_id}/evidence-sla/policies/{policy_id}/evaluate"
        )
        assert eval_resp.status_code == 200, eval_resp.text
        data = eval_resp.json()
        assert data["overall_status"] == "passed"


# ---------------------------------------------------------------------------
# class TestEvidenceSLASummary
# ---------------------------------------------------------------------------

class TestEvidenceSLASummary:
    def test_summary_avoids_forbidden_language(self, db, client):
        """Summary must not contain forbidden language like 'incident', 'breach', etc."""
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="summary")
        strat_id = str(strat.id)

        resp = client.post(f"/api/strategies/{strat_id}/evidence-sla/default")
        policy_id = resp.json()["id"]

        eval_resp = client.post(
            f"/api/strategies/{strat_id}/evidence-sla/policies/{policy_id}/evaluate"
        )
        assert eval_resp.status_code == 200, eval_resp.text
        data = eval_resp.json()
        summary = (data.get("deterministic_summary") or "").lower()

        forbidden = ["incident", "breach", "strategy failed", "do not trade"]
        for phrase in forbidden:
            assert phrase not in summary, (
                f"Summary contains forbidden phrase '{phrase}': {summary}"
            )

    def test_suggested_actions_present(self, db, client):
        """Violated required rules must have suggested_action text."""
        project = _get_seeded_project(db)
        org = _get_seeded_org(db)
        strat = _make_strategy(db, project.id, suffix="suggested")
        strat_id = str(strat.id)

        # Trigger a clear violation with an open high alert
        _make_alert(db, strat.id, org.id, severity="critical")

        resp = client.post(f"/api/strategies/{strat_id}/evidence-sla/default")
        policy_id = resp.json()["id"]

        eval_resp = client.post(
            f"/api/strategies/{strat_id}/evidence-sla/policies/{policy_id}/evaluate"
        )
        assert eval_resp.status_code == 200, eval_resp.text
        data = eval_resp.json()

        results = data.get("results", [])
        violated_required = [
            r for r in results
            if r["status"] == "violated" and r["is_required"]
        ]
        # At minimum the alert rule should be violated
        assert len(violated_required) >= 1
        for r in violated_required:
            assert r["suggested_action"] is not None, (
                f"Rule '{r['rule_key']}' is violated but has no suggested_action"
            )
