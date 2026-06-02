"""M33 Evidence Quality Alert tests.

Tests cover:
- POST /api/alerts/generate returns 200 with created/skipped counts
- Evidence coverage below threshold creates alert
- Strategy health critical/review creates alert
- Stale strategy run (> 90 days) creates medium alert
- No strategy runs creates stale_strategy_run alert
- Missing signal snapshot with a run creates missing_signal_evidence alert
- Missing universe snapshot with a run creates missing_universe_evidence alert
- Missing config snapshot with a run creates missing_config_evidence alert
- Deduplication: second generate does not create duplicate open alerts
- Resolved alert can be re-triggered on next generate
- Evidence quality alerts have metadata_json with suggested_check
- Backtest trust < 40 creates critical backtest_trust_deteriorating alert
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest


# ---------------------------------------------------------------------------
# Helpers (mirror test_alerts_m11.py patterns)
# ---------------------------------------------------------------------------

def _get_project_id(client) -> str:
    return client.get("/api/projects").json()[0]["id"]


def _create_strategy(client, name: str | None = None) -> dict:
    pid = _get_project_id(client)
    resp = client.post("/api/strategies", json={
        "project_id": pid,
        "name": name or f"M33TestStrategy {uuid.uuid4().hex[:6]}",
    })
    assert resp.status_code == 201, resp.text
    return resp.json()


def _log_run(client, strategy_id: str, run_type: str = "backtest",
             dataset_snapshot_id: str | None = None) -> dict:
    payload: dict = {
        "run_name": f"M33Run {uuid.uuid4().hex[:6]}",
        "run_type": run_type,
        "assumptions_json": {"transaction_cost_bps": 5, "fill_model": "vwap"},
        "metrics_json": {
            "sharpe": 1.5,
            "annual_return": 0.20,
            "max_drawdown": -0.12,
            "trade_count": 200,
        },
    }
    if dataset_snapshot_id:
        payload["dataset_snapshot_id"] = dataset_snapshot_id
    resp = client.post(f"/api/strategies/{strategy_id}/runs", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _generate(client) -> dict:
    resp = client.post("/api/alerts/generate")
    assert resp.status_code == 200, resp.text
    return resp.json()


def _list_alerts_by_rule(client, rule_type: str, strategy_id: str | None = None) -> list:
    url = f"/api/alerts?rule_type={rule_type}&limit=200"
    if strategy_id:
        url += f"&strategy_id={strategy_id}"
    resp = client.get(url)
    assert resp.status_code == 200
    return resp.json()["items"]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestEvidenceQualityAlerts:

    def test_generate_alerts_includes_evidence_checks(self, client):
        """POST /api/alerts/generate returns correct shape including new M33 evidence checks."""
        result = _generate(client)
        assert "alerts_created" in result
        assert "alerts_skipped_duplicate" in result
        assert "total_alerts_open" in result
        assert isinstance(result["alerts_created"], int)
        assert isinstance(result["alerts_skipped_duplicate"], int)
        assert isinstance(result["total_alerts_open"], int)

    def test_coverage_low_creates_alert(self, client):
        """Strategy with no evidence should produce evidence_coverage_below_threshold alert."""
        strat = _create_strategy(client)

        # Generate — new strategy with zero evidence → coverage = 0 → high alert
        result = _generate(client)
        assert result["alerts_created"] >= 1

        alerts = _list_alerts_by_rule(
            client, "evidence_coverage_below_threshold", strategy_id=strat["id"]
        )
        assert len(alerts) >= 1
        severities = {a["severity"] for a in alerts}
        assert severities & {"high", "medium", "critical"}

    def test_no_runs_stale_alert(self, client):
        """Strategy with no runs gets a stale_strategy_run alert."""
        strat = _create_strategy(client)

        _generate(client)

        alerts = _list_alerts_by_rule(
            client, "stale_strategy_run", strategy_id=strat["id"]
        )
        assert len(alerts) >= 1
        # No runs → medium severity
        severities = {a["severity"] for a in alerts}
        assert "medium" in severities or "low" in severities

    def test_stale_run_medium_alert(self, client, db):
        """Strategy run older than 90 days creates a stale_strategy_run alert."""
        from app.models.strategy_run import StrategyRun

        strat = _create_strategy(client)
        run = _log_run(client, strat["id"])
        run_id = run["id"]

        # Force the run's created_at to be far in the past
        old_date_naive = datetime(2020, 1, 1)  # SQLite stores naive
        run_uuid = uuid.UUID(run_id)
        try:
            db.execute(
                StrategyRun.__table__.update()
                .where(StrategyRun.__table__.c.id == run_uuid)
                .values(created_at=old_date_naive)
            )
            db.flush()

            _generate(client)

            alerts = _list_alerts_by_rule(
                client, "stale_strategy_run", strategy_id=strat["id"]
            )
            assert len(alerts) >= 1
            severities = {a["severity"] for a in alerts}
            # > 90 days → medium; > 30 days → low
            assert severities & {"medium", "low"}
        finally:
            # Restore to present so other tests don't break
            db.execute(
                StrategyRun.__table__.update()
                .where(StrategyRun.__table__.c.id == run_uuid)
                .values(created_at=datetime.now())
            )
            db.flush()

    def test_missing_signal_with_run(self, client):
        """Strategy with a run but no signal snapshots gets missing_signal_evidence alert."""
        strat = _create_strategy(client)
        _log_run(client, strat["id"])

        _generate(client)

        alerts = _list_alerts_by_rule(
            client, "missing_signal_evidence", strategy_id=strat["id"]
        )
        assert len(alerts) >= 1
        for a in alerts:
            assert a["severity"] == "low"

    def test_missing_universe_with_run(self, client):
        """Strategy with a run but no universe snapshots gets missing_universe_evidence alert."""
        strat = _create_strategy(client)
        _log_run(client, strat["id"])

        _generate(client)

        alerts = _list_alerts_by_rule(
            client, "missing_universe_evidence", strategy_id=strat["id"]
        )
        assert len(alerts) >= 1
        for a in alerts:
            assert a["severity"] == "low"

    def test_missing_config_with_run(self, client):
        """Strategy with a run but no config snapshots gets missing_config_evidence alert."""
        strat = _create_strategy(client)
        _log_run(client, strat["id"])

        _generate(client)

        alerts = _list_alerts_by_rule(
            client, "missing_config_evidence", strategy_id=strat["id"]
        )
        assert len(alerts) >= 1
        for a in alerts:
            assert a["severity"] == "low"

    def test_dedup_prevents_duplicate(self, client):
        """Calling generate twice for the same strategy does not create duplicate open alerts."""
        strat = _create_strategy(client)
        _log_run(client, strat["id"])

        # First generate — creates alerts
        result1 = _generate(client)
        first_created = result1["alerts_created"]

        # Second generate — all existing alerts should be deduped
        result2 = _generate(client)
        assert result2["alerts_created"] == 0
        assert result2["alerts_skipped_duplicate"] >= first_created

        # No duplicate open alerts for this strategy
        alerts_open = client.get(
            f"/api/alerts?strategy_id={strat['id']}&status=open&limit=200"
        ).json()["items"]
        # Count rule_types; each should appear at most once
        rule_counts: dict[str, int] = {}
        for a in alerts_open:
            rule_counts[a["rule_type"]] = rule_counts.get(a["rule_type"], 0) + 1
        for rt, count in rule_counts.items():
            assert count == 1, f"Duplicate open alert for rule_type={rt!r}"

    def test_resolved_alert_regenerated(self, client):
        """After resolving an evidence alert it gets re-created on the next generate."""
        strat = _create_strategy(client)
        _log_run(client, strat["id"])

        # First generate
        _generate(client)

        # Find a missing_signal_evidence alert for this strategy
        alerts = _list_alerts_by_rule(
            client, "missing_signal_evidence", strategy_id=strat["id"]
        )
        assert len(alerts) >= 1, "Expected missing_signal_evidence alert"
        target = alerts[0]

        # Resolve it
        patch = client.patch(f"/api/alerts/{target['id']}", json={"status": "resolved"})
        assert patch.status_code == 200
        assert patch.json()["status"] == "resolved"

        # Second generate → new alert created for same strategy
        result2 = _generate(client)
        assert result2["alerts_created"] >= 1

        # New open alert exists for the same rule
        new_alerts = _list_alerts_by_rule(
            client, "missing_signal_evidence", strategy_id=strat["id"]
        )
        open_alerts = [a for a in new_alerts if a["status"] == "open"]
        assert len(open_alerts) >= 1

    def test_evidence_json_populated(self, client):
        """Generated evidence quality alerts carry metadata_json with suggested_check."""
        strat = _create_strategy(client)

        _generate(client)

        # Check various rule types for suggested_check in metadata
        for rule_type in (
            "evidence_coverage_below_threshold",
            "stale_strategy_run",
        ):
            alerts = _list_alerts_by_rule(client, rule_type, strategy_id=strat["id"])
            for a in alerts:
                full = client.get(f"/api/alerts/{a['id']}").json()
                meta = full.get("metadata_json") or {}
                assert "suggested_check" in meta, (
                    f"Alert {rule_type} missing suggested_check in metadata_json"
                )

    def test_backtest_trust_below_40_creates_critical(self, client, db):
        """Backtest audit with trust_score < 40 triggers a critical backtest_trust_deteriorating alert."""
        from app.models.backtest_audit import BacktestAudit
        from app.models.strategy_run import StrategyRun

        strat = _create_strategy(client)

        # Log a run with implausible metrics and no cost model to get low trust
        resp = client.post(f"/api/strategies/{strat['id']}/runs", json={
            "run_name": f"LowTrustRun {uuid.uuid4().hex[:6]}",
            "run_type": "backtest",
            "assumptions_json": {},
            "metrics_json": {
                "sharpe": 15.0,        # implausible_sharpe: high (-15)
                "annual_return": 5.0,  # implausible_return: high (-15)
                "max_drawdown": -0.001,
                "trade_count": 5,      # insufficient_trade_count
            },
        })
        assert resp.status_code == 201
        run = resp.json()

        # Run backtest audit
        audit_resp = client.post(f"/api/strategy-runs/{run['id']}/backtest-audit")
        assert audit_resp.status_code in (200, 201)
        audit = audit_resp.json()

        # If trust_score < 40, force it; otherwise set directly in DB
        audit_id = audit["id"]
        audit_uuid = uuid.UUID(audit_id)
        if audit["trust_score"] >= 40:
            # Manually set trust_score to 30 in the DB
            db.execute(
                BacktestAudit.__table__.update()
                .where(BacktestAudit.__table__.c.id == audit_uuid)
                .values(trust_score=30)
            )
            db.flush()

        _generate(client)

        alerts = _list_alerts_by_rule(
            client, "backtest_trust_deteriorating", strategy_id=strat["id"]
        )
        critical_alerts = [a for a in alerts if a["severity"] == "critical"]
        assert len(critical_alerts) >= 1, (
            f"Expected critical backtest_trust_deteriorating alert; got {alerts}"
        )
