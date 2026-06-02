"""M54 tests: Strategy Config Policy Engine.

Tests for:
  - POST /api/strategies/{id}/config-policies/default  — create default policy (idempotent)
  - POST /api/strategies/{id}/config-policies           — create custom policy
  - GET  /api/strategies/{id}/config-policies           — list policies
  - POST /api/strategies/{id}/config-policies/{id}/evaluate — run evaluation
  - GET  /api/strategies/{id}/config-policy-evaluations — list evaluations
  - GET  /api/config-policy-evaluations/{id}            — get evaluation detail
  - Rule evaluation logic for all operators
  - Overall status computation
  - AuditTimelineEvent created on evaluation
  - StrategyConfigPolicyResult rows persisted

All tests use shared session-scoped fixtures from conftest.py.
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone

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


def _make_strategy(db, project_id, *, suffix: str = "") -> object:
    from app.models.strategy import Strategy

    slug = f"m54-test-{suffix}-{uuid.uuid4().hex[:8]}"
    strat = Strategy(
        project_id=project_id,
        name=f"M54 Test {suffix}",
        slug=slug,
        asset_class="equity",
        status="active",
    )
    db.add(strat)
    db.commit()
    return strat


def _make_config_snapshot(db, strategy_id, config_json: dict | None = None) -> object:
    from app.models.strategy_config_snapshot import StrategyConfigSnapshot

    cfg = config_json or {"param": "value"}
    import json
    raw = json.dumps(cfg, sort_keys=True).encode()
    h = hashlib.sha256(raw).hexdigest()
    snap = StrategyConfigSnapshot(
        strategy_id=strategy_id,
        label=f"M54 Config {h[:8]}",
        config_hash=h,
        config_json=cfg,
    )
    db.add(snap)
    db.commit()
    return snap


def _make_default_policy(db, strategy_id: str) -> object:
    from app.services.config_policies import create_default_config_policy
    policy = create_default_config_policy(db, strategy_id)
    db.commit()
    return policy


# ---------------------------------------------------------------------------
# class TestConfigPolicySetup
# ---------------------------------------------------------------------------

class TestConfigPolicySetup:
    def test_create_default_policy_success(self, db, client):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="default")
        strat_id = str(strat.id)

        resp = client.post(f"/api/strategies/{strat_id}/config-policies/default")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["name"] == "QuantFidelity Default Assumption Guardrails"
        assert data["strategy_id"] == strat_id
        assert data["is_active"] is True
        assert data["rule_count"] == 15
        assert "id" in data

    def test_create_default_policy_idempotent(self, db, client):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="idempotent")
        strat_id = str(strat.id)

        resp1 = client.post(f"/api/strategies/{strat_id}/config-policies/default")
        resp2 = client.post(f"/api/strategies/{strat_id}/config-policies/default")
        assert resp1.status_code == 200
        assert resp2.status_code == 200
        assert resp1.json()["id"] == resp2.json()["id"]

    def test_create_custom_policy_success(self, db, client):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="custom")
        strat_id = str(strat.id)

        payload = {
            "name": "My Custom Policy",
            "description": "A test custom policy",
            "is_active": True,
            "policy_json": {
                "rules": [
                    {
                        "rule_key": "test_rule",
                        "title": "Test Rule",
                        "key_path": "params.lookback_days",
                        "operator": "exists",
                        "severity": "low",
                        "is_required": False,
                    }
                ]
            },
        }
        resp = client.post(f"/api/strategies/{strat_id}/config-policies", json=payload)
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["name"] == "My Custom Policy"
        assert data["rule_count"] == 1

    def test_list_policies_success(self, db, client):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="list")
        strat_id = str(strat.id)

        # Create default
        client.post(f"/api/strategies/{strat_id}/config-policies/default")

        resp = client.get(f"/api/strategies/{strat_id}/config-policies")
        assert resp.status_code == 200, resp.text
        items = resp.json()
        assert isinstance(items, list)
        assert len(items) >= 1
        names = [p["name"] for p in items]
        assert "QuantFidelity Default Assumption Guardrails" in names

    def test_404_on_nonexistent_strategy(self, db, client):
        fake_id = str(uuid.uuid4())
        resp = client.post(f"/api/strategies/{fake_id}/config-policies/default")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# class TestConfigPolicyEvaluation
# ---------------------------------------------------------------------------

class TestConfigPolicyEvaluation:
    def test_evaluate_no_config_snapshot_returns_insufficient(self, db, client):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="nosnap")
        strat_id = str(strat.id)

        policy_resp = client.post(f"/api/strategies/{strat_id}/config-policies/default")
        policy_id = policy_resp.json()["id"]

        resp = client.post(f"/api/strategies/{strat_id}/config-policies/{policy_id}/evaluate")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["overall_status"] == "insufficient_evidence"

    def test_evaluate_with_clean_config(self, db, client):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="clean")
        strat_id = str(strat.id)

        # Config that satisfies most required rules
        cfg = {
            "assumptions": {
                "transaction_cost_bps": 5,
                "slippage_bps": 2,
                "fill_model": "next_open",
                "execution_timing": "next_open",
                "liquidity_filter": True,
                "dataset_version": "v2",
            },
            "params": {"lookback_days": 252},
            "portfolio": {"max_position_weight": 0.10},
        }
        _make_config_snapshot(db, strat.id, config_json=cfg)

        policy = _make_default_policy(db, strat_id)
        policy_id = str(policy.id)

        resp = client.post(f"/api/strategies/{strat_id}/config-policies/{policy_id}/evaluate")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["overall_status"] in ("passed", "warning")
        assert data["passed_count"] > 0

    def test_evaluate_same_close_fill_model_fails(self, db, client):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="sameclose")
        strat_id = str(strat.id)

        cfg = {
            "assumptions": {
                "transaction_cost_bps": 5,
                "fill_model": "same_close",  # This should fail
            },
        }
        _make_config_snapshot(db, strat.id, config_json=cfg)
        policy = _make_default_policy(db, strat_id)
        policy_id = str(policy.id)

        resp = client.post(f"/api/strategies/{strat_id}/config-policies/{policy_id}/evaluate")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["overall_status"] == "failed"
        # Check fill_model_not_same_close rule failed
        results = data["results"]
        fill_result = next((r for r in results if r["rule_key"] == "fill_model_not_same_close"), None)
        assert fill_result is not None
        assert fill_result["status"] == "failed"

    def test_evaluate_missing_transaction_cost_fails(self, db, client):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="notxcost")
        strat_id = str(strat.id)

        cfg = {
            "assumptions": {
                "fill_model": "next_open",
            },
        }
        _make_config_snapshot(db, strat.id, config_json=cfg)
        policy = _make_default_policy(db, strat_id)
        policy_id = str(policy.id)

        resp = client.post(f"/api/strategies/{strat_id}/config-policies/{policy_id}/evaluate")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["overall_status"] == "failed"
        results = data["results"]
        tx_result = next((r for r in results if r["rule_key"] == "transaction_cost_required"), None)
        assert tx_result is not None
        assert tx_result["status"] == "failed"
        assert tx_result["severity"] == "high"

    def test_evaluate_max_leverage_over_limit(self, db, client):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="leverage")
        strat_id = str(strat.id)

        cfg = {
            "assumptions": {
                "transaction_cost_bps": 5,
                "fill_model": "next_open",
                "max_leverage": 5.0,  # Over 2x limit
            },
        }
        _make_config_snapshot(db, strat.id, config_json=cfg)
        policy = _make_default_policy(db, strat_id)
        policy_id = str(policy.id)

        resp = client.post(f"/api/strategies/{strat_id}/config-policies/{policy_id}/evaluate")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        results = data["results"]
        lev_result = next((r for r in results if r["rule_key"] == "leverage_limit"), None)
        assert lev_result is not None
        assert lev_result["status"] in ("failed", "warning")

    def test_evaluate_borrow_cost_skipped_when_not_short(self, db, client):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="noshort")
        strat_id = str(strat.id)

        cfg = {
            "assumptions": {
                "transaction_cost_bps": 5,
                "fill_model": "next_open",
                "short_enabled": False,
                # no borrow_cost_bps — but condition says short_enabled must be True
            },
        }
        _make_config_snapshot(db, strat.id, config_json=cfg)
        policy = _make_default_policy(db, strat_id)
        policy_id = str(policy.id)

        resp = client.post(f"/api/strategies/{strat_id}/config-policies/{policy_id}/evaluate")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        results = data["results"]
        borrow_result = next((r for r in results if r["rule_key"] == "borrow_cost_when_short"), None)
        assert borrow_result is not None
        assert borrow_result["status"] == "skipped"

    def test_evaluate_borrow_cost_fails_when_short_no_borrow(self, db, client):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="shortnoborrow")
        strat_id = str(strat.id)

        cfg = {
            "assumptions": {
                "transaction_cost_bps": 5,
                "fill_model": "next_open",
                "short_enabled": True,
                # no borrow_cost_bps
            },
        }
        _make_config_snapshot(db, strat.id, config_json=cfg)
        policy = _make_default_policy(db, strat_id)
        policy_id = str(policy.id)

        resp = client.post(f"/api/strategies/{strat_id}/config-policies/{policy_id}/evaluate")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        results = data["results"]
        borrow_result = next((r for r in results if r["rule_key"] == "borrow_cost_when_short"), None)
        assert borrow_result is not None
        assert borrow_result["status"] == "failed"

    def test_evaluate_selected_config_snapshot(self, db, client):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="selsnap")
        strat_id = str(strat.id)

        # Make two snapshots
        cfg1 = {"assumptions": {"fill_model": "next_open", "transaction_cost_bps": 5}}
        cfg2 = {"assumptions": {"fill_model": "same_close"}}  # Should fail
        snap1 = _make_config_snapshot(db, strat.id, config_json=cfg1)
        snap2 = _make_config_snapshot(db, strat.id, config_json=cfg2)  # noqa: F841

        policy = _make_default_policy(db, strat_id)
        policy_id = str(policy.id)

        # Evaluate with snap1 explicitly
        resp = client.post(
            f"/api/strategies/{strat_id}/config-policies/{policy_id}/evaluate",
            json={"config_snapshot_id": str(snap1.id)},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["config_snapshot_id"] == str(snap1.id)

    def test_evaluate_persists_results(self, db, client):
        from app.models.config_policy import StrategyConfigPolicyResult

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="persist")
        strat_id = str(strat.id)

        cfg = {"assumptions": {"fill_model": "next_open", "transaction_cost_bps": 5}}
        _make_config_snapshot(db, strat.id, config_json=cfg)
        policy = _make_default_policy(db, strat_id)
        policy_id = str(policy.id)

        resp = client.post(f"/api/strategies/{strat_id}/config-policies/{policy_id}/evaluate")
        assert resp.status_code == 200, resp.text
        eval_id = resp.json()["id"]

        # Check DB
        results = (
            db.query(StrategyConfigPolicyResult)
            .filter(StrategyConfigPolicyResult.evaluation_id == uuid.UUID(eval_id))
            .all()
        )
        assert len(results) == 15  # All 15 default rules

    def test_evaluate_timeline_event_created(self, db, client):
        from app.models.audit_timeline_event import AuditTimelineEvent

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="timeline")
        strat_id = str(strat.id)

        cfg = {"assumptions": {"fill_model": "next_open", "transaction_cost_bps": 5}}
        _make_config_snapshot(db, strat.id, config_json=cfg)
        policy = _make_default_policy(db, strat_id)
        policy_id = str(policy.id)

        resp = client.post(f"/api/strategies/{strat_id}/config-policies/{policy_id}/evaluate")
        assert resp.status_code == 200, resp.text
        eval_id = resp.json()["id"]

        events = (
            db.query(AuditTimelineEvent)
            .filter(
                AuditTimelineEvent.strategy_id == strat.id,
                AuditTimelineEvent.event_type == "config_policy_evaluated",
            )
            .all()
        )
        assert len(events) >= 1
        event = events[-1]
        assert event.source_type == "config_policy"
        assert event.source_id == eval_id

    def test_list_evaluations(self, db, client):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="listeval")
        strat_id = str(strat.id)

        cfg = {"assumptions": {"fill_model": "next_open", "transaction_cost_bps": 5}}
        _make_config_snapshot(db, strat.id, config_json=cfg)
        policy = _make_default_policy(db, strat_id)
        policy_id = str(policy.id)

        client.post(f"/api/strategies/{strat_id}/config-policies/{policy_id}/evaluate")
        client.post(f"/api/strategies/{strat_id}/config-policies/{policy_id}/evaluate")

        resp = client.get(f"/api/strategies/{strat_id}/config-policy-evaluations")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "items" in data
        assert data["total"] >= 2

    def test_get_evaluation_detail(self, db, client):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="detail")
        strat_id = str(strat.id)

        cfg = {"assumptions": {"fill_model": "next_open", "transaction_cost_bps": 5}}
        _make_config_snapshot(db, strat.id, config_json=cfg)
        policy = _make_default_policy(db, strat_id)
        policy_id = str(policy.id)

        eval_resp = client.post(f"/api/strategies/{strat_id}/config-policies/{policy_id}/evaluate")
        eval_id = eval_resp.json()["id"]

        resp = client.get(f"/api/config-policy-evaluations/{eval_id}")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["id"] == eval_id
        assert len(data["results"]) == 15

    def test_get_evaluation_404(self, db, client):
        fake_id = str(uuid.uuid4())
        resp = client.get(f"/api/config-policy-evaluations/{fake_id}")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# class TestConfigPolicyOverallStatus
# ---------------------------------------------------------------------------

class TestConfigPolicyOverallStatus:
    def test_overall_status_passed(self, db, client):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="statpassed")
        strat_id = str(strat.id)

        # Config satisfying all required rules
        cfg = {
            "assumptions": {
                "transaction_cost_bps": 5,
                "fill_model": "next_open",
                "slippage_bps": 2,
            },
        }
        _make_config_snapshot(db, strat.id, config_json=cfg)

        # Custom policy with only the required-and-satisfied rules
        from app.services.config_policies import create_config_policy
        policy = create_config_policy(db, strat_id, {
            "name": "Minimal Passing Policy",
            "policy_json": {
                "rules": [
                    {
                        "rule_key": "tx_cost",
                        "title": "Tx cost",
                        "key_path": "assumptions.transaction_cost_bps",
                        "operator": "exists",
                        "severity": "high",
                        "is_required": True,
                    },
                    {
                        "rule_key": "fill_model",
                        "title": "Fill model",
                        "key_path": "assumptions.fill_model",
                        "operator": "exists",
                        "severity": "high",
                        "is_required": True,
                    },
                ]
            },
        })
        db.commit()
        policy_id = str(policy.id)

        resp = client.post(f"/api/strategies/{strat_id}/config-policies/{policy_id}/evaluate")
        assert resp.status_code == 200
        data = resp.json()
        assert data["overall_status"] == "passed"

    def test_overall_status_failed(self, db, client):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="statfailed")
        strat_id = str(strat.id)

        # Config missing required fill_model
        cfg = {"assumptions": {"transaction_cost_bps": 5}}
        _make_config_snapshot(db, strat.id, config_json=cfg)
        policy = _make_default_policy(db, strat_id)
        policy_id = str(policy.id)

        resp = client.post(f"/api/strategies/{strat_id}/config-policies/{policy_id}/evaluate")
        assert resp.status_code == 200
        data = resp.json()
        assert data["overall_status"] == "failed"

    def test_overall_status_warning(self, db, client):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="statwarn")
        strat_id = str(strat.id)

        cfg = {
            "assumptions": {
                "transaction_cost_bps": 5,
                "fill_model": "next_open",
            }
        }
        _make_config_snapshot(db, strat.id, config_json=cfg)

        # Custom policy: one non-required, medium severity rule that will fail
        from app.services.config_policies import create_config_policy
        policy = create_config_policy(db, strat_id, {
            "name": "Warning Policy",
            "policy_json": {
                "rules": [
                    {
                        "rule_key": "fill_exists",
                        "title": "Fill model exists",
                        "key_path": "assumptions.fill_model",
                        "operator": "exists",
                        "severity": "high",
                        "is_required": True,
                    },
                    {
                        "rule_key": "slippage_exists",
                        "title": "Slippage recommended",
                        "key_path": "assumptions.slippage_bps",
                        "operator": "exists",
                        "severity": "medium",
                        "is_required": False,
                    },
                ]
            },
        })
        db.commit()
        policy_id = str(policy.id)

        resp = client.post(f"/api/strategies/{strat_id}/config-policies/{policy_id}/evaluate")
        assert resp.status_code == 200
        data = resp.json()
        assert data["overall_status"] in ("warning", "passed")

    def test_overall_status_insufficient_evidence(self, db, client):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="statinsuf")
        strat_id = str(strat.id)

        # No config snapshot created
        policy = _make_default_policy(db, strat_id)
        policy_id = str(policy.id)

        resp = client.post(f"/api/strategies/{strat_id}/config-policies/{policy_id}/evaluate")
        assert resp.status_code == 200
        data = resp.json()
        assert data["overall_status"] == "insufficient_evidence"


# ---------------------------------------------------------------------------
# class TestConfigPolicyOperators
# ---------------------------------------------------------------------------

class TestConfigPolicyOperators:
    """Direct unit tests for the _eval_rule and _eval_rule_with_compound functions."""

    def test_operator_exists_pass(self):
        from app.services.config_policies import _eval_rule

        rule = {
            "rule_key": "key_present",
            "title": "Key present",
            "key_path": "assumptions.fill_model",
            "operator": "exists",
            "severity": "high",
            "is_required": True,
        }
        flat = {"assumptions.fill_model": "next_open"}
        result = _eval_rule(rule, flat)
        assert result["status"] == "passed"

    def test_operator_exists_fail(self):
        from app.services.config_policies import _eval_rule

        rule = {
            "rule_key": "key_missing",
            "title": "Key missing",
            "key_path": "assumptions.fill_model",
            "operator": "exists",
            "severity": "high",
            "is_required": True,
        }
        flat = {}
        result = _eval_rule(rule, flat)
        assert result["status"] == "failed"
        assert result["suggested_action"] is not None

    def test_operator_not_in_pass(self):
        from app.services.config_policies import _eval_rule

        rule = {
            "rule_key": "not_bad_fill",
            "title": "Not bad fill",
            "key_path": "assumptions.fill_model",
            "operator": "not_in",
            "expected_value": ["same_close", "exact_close"],
            "severity": "high",
            "is_required": True,
        }
        flat = {"assumptions.fill_model": "next_open"}
        result = _eval_rule(rule, flat)
        assert result["status"] == "passed"

    def test_operator_not_in_fail(self):
        from app.services.config_policies import _eval_rule

        rule = {
            "rule_key": "not_bad_fill",
            "title": "Not bad fill",
            "key_path": "assumptions.fill_model",
            "operator": "not_in",
            "expected_value": ["same_close", "exact_close"],
            "severity": "high",
            "is_required": True,
        }
        flat = {"assumptions.fill_model": "same_close"}
        result = _eval_rule(rule, flat)
        assert result["status"] == "failed"

    def test_operator_gte_pass(self):
        from app.services.config_policies import _eval_rule

        rule = {
            "rule_key": "cost_positive",
            "title": "Cost positive",
            "key_path": "assumptions.transaction_cost_bps",
            "operator": "gte",
            "expected_value": 1,
            "severity": "medium",
            "is_required": False,
        }
        flat = {"assumptions.transaction_cost_bps": 5}
        result = _eval_rule(rule, flat)
        assert result["status"] == "passed"

    def test_operator_lte_fail(self):
        from app.services.config_policies import _eval_rule

        rule = {
            "rule_key": "leverage_ok",
            "title": "Leverage ok",
            "key_path": "assumptions.max_leverage",
            "operator": "lte",
            "expected_value": 2.0,
            "severity": "medium",
            "is_required": False,
        }
        flat = {"assumptions.max_leverage": 5.0}
        result = _eval_rule(rule, flat)
        assert result["status"] in ("failed", "warning")

    def test_flatten_nested(self):
        from app.services.config_policies import _flatten_config

        cfg = {
            "assumptions": {
                "transaction_cost_bps": 5,
                "fill_model": "next_open",
            },
            "params": {"lookback_days": 252},
            "tags": ["equity", "factor"],
        }
        flat = _flatten_config(cfg)
        assert flat["assumptions.transaction_cost_bps"] == 5
        assert flat["assumptions.fill_model"] == "next_open"
        assert flat["params.lookback_days"] == 252
        assert flat["tags"] == ["equity", "factor"]

    def test_conditional_rule_skipped(self):
        from app.services.config_policies import _eval_rule_with_compound

        rule = {
            "rule_key": "borrow_cost_when_short",
            "title": "Borrow cost required when shorting is enabled",
            "key_path": "assumptions.borrow_cost_bps",
            "operator": "exists",
            "severity": "high",
            "is_required": True,
            "condition_json": {
                "key_path": "assumptions.short_enabled",
                "operator": "eq",
                "expected_value": True,
            },
        }
        flat = {"assumptions.short_enabled": False}  # condition not met
        result = _eval_rule_with_compound(rule, flat)
        assert result["status"] == "skipped"

    def test_conditional_rule_evaluated_when_condition_met(self):
        from app.services.config_policies import _eval_rule_with_compound

        rule = {
            "rule_key": "borrow_cost_when_short",
            "title": "Borrow cost required when shorting is enabled",
            "key_path": "assumptions.borrow_cost_bps",
            "operator": "exists",
            "severity": "high",
            "is_required": True,
            "condition_json": {
                "key_path": "assumptions.short_enabled",
                "operator": "eq",
                "expected_value": True,
            },
        }
        flat = {"assumptions.short_enabled": True}  # condition met, but no borrow_cost_bps
        result = _eval_rule_with_compound(rule, flat)
        assert result["status"] == "failed"

    def test_compound_rule_passes_when_any_present(self):
        from app.services.config_policies import _eval_rule_with_compound

        rule = {
            "rule_key": "risk_controls_present",
            "title": "Risk controls recommended",
            "key_path": "__compound__risk_controls",
            "operator": "__compound__",
            "compound_keys": ["risk.stop_loss", "risk.max_drawdown_limit"],
            "severity": "medium",
            "is_required": False,
        }
        flat = {"risk.stop_loss": 0.15}
        result = _eval_rule_with_compound(rule, flat)
        assert result["status"] == "passed"

    def test_compound_rule_warns_when_none_present(self):
        from app.services.config_policies import _eval_rule_with_compound

        rule = {
            "rule_key": "risk_controls_present",
            "title": "Risk controls recommended",
            "key_path": "__compound__risk_controls",
            "operator": "__compound__",
            "compound_keys": ["risk.stop_loss", "risk.max_drawdown_limit"],
            "severity": "medium",
            "is_required": False,
        }
        flat = {}
        result = _eval_rule_with_compound(rule, flat)
        assert result["status"] == "warning"

    def test_operator_eq_pass(self):
        from app.services.config_policies import _eval_rule

        rule = {
            "rule_key": "status_check",
            "title": "Status check",
            "key_path": "assumptions.mode",
            "operator": "eq",
            "expected_value": "live",
            "severity": "low",
            "is_required": False,
        }
        flat = {"assumptions.mode": "live"}
        result = _eval_rule(rule, flat)
        assert result["status"] == "passed"

    def test_operator_neq_pass(self):
        from app.services.config_policies import _eval_rule

        rule = {
            "rule_key": "timing_check",
            "title": "Timing not same bar",
            "key_path": "assumptions.execution_timing",
            "operator": "neq",
            "expected_value": "same_bar",
            "severity": "medium",
            "is_required": False,
        }
        flat = {"assumptions.execution_timing": "next_open"}
        result = _eval_rule(rule, flat)
        assert result["status"] == "passed"

    def test_operator_contains_pass(self):
        from app.services.config_policies import _eval_rule

        rule = {
            "rule_key": "name_contains",
            "title": "Name contains equity",
            "key_path": "params.name",
            "operator": "contains",
            "expected_value": "equity",
            "severity": "low",
            "is_required": False,
        }
        flat = {"params.name": "us-equity-momentum"}
        result = _eval_rule(rule, flat)
        assert result["status"] == "passed"

    def test_non_numeric_lte_skips(self):
        from app.services.config_policies import _eval_rule

        rule = {
            "rule_key": "leverage_limit",
            "title": "Leverage limit",
            "key_path": "assumptions.max_leverage",
            "operator": "lte",
            "expected_value": 2.0,
            "severity": "medium",
            "is_required": False,
        }
        flat = {"assumptions.max_leverage": "not-a-number"}
        result = _eval_rule(rule, flat)
        assert result["status"] == "skipped"
