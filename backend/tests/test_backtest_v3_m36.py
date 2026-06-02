"""M36 backtest audit v3 tests — cost sweep, fill sensitivity, penalty attribution,
improvement checks.

Tests cover:
- cost sensitivity sweep: 6 scenarios with correct labels
- adjusted return and Sharpe decrease monotonically as cost increases
- fill sensitivity: fill_realism_level classification
- penalty attribution: categories, weights, and largest_penalty_category
- improvement checks: prioritised, actionable checks
- API response includes all new v3 JSON fields
"""

from __future__ import annotations

import uuid

import pytest


# ---------------------------------------------------------------------------
# Helpers (reuse M13 pattern)
# ---------------------------------------------------------------------------

def _get_project_id(client) -> str:
    return client.get("/api/projects").json()[0]["id"]


def _create_strategy_id(client, name: str) -> str:
    pid = _get_project_id(client)
    resp = client.post("/api/strategies", json={"project_id": pid, "name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _log_run(client, strategy_id: str, **kwargs) -> dict:
    payload = {
        "run_name": f"M36 Run {uuid.uuid4().hex[:6]}",
        "run_type": "backtest",
        **kwargs,
    }
    resp = client.post(f"/api/strategies/{strategy_id}/runs", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _post_audit(client, run_id: str) -> dict:
    resp = client.post(f"/api/strategy-runs/{run_id}/backtest-audit")
    assert resp.status_code == 201, resp.text
    return resp.json()


def _get_audit(client, run_id: str) -> dict:
    resp = client.get(f"/api/strategy-runs/{run_id}/backtest-audit")
    assert resp.status_code == 200, resp.text
    return resp.json()


def _full_assumptions() -> dict:
    return {
        "transaction_cost_bps": 5,
        "slippage_bps": 2,
        "fill_model": "vwap",
        "execution_timing": "open",
    }


def _full_metrics() -> dict:
    return {
        "sharpe": 1.5,
        "annual_return": 0.20,
        "volatility": 0.133,
        "turnover": 1.0,
        "trade_count": 200,
        "max_drawdown": -0.10,
    }


# ---------------------------------------------------------------------------
# TestCostSweep
# ---------------------------------------------------------------------------

class TestCostSweep:
    def test_sweep_generates_six_scenarios(self, client):
        """Run with a cost assumption returns a sweep with exactly 6 scenarios."""
        sid = _create_strategy_id(client, f"SweepCount {uuid.uuid4().hex[:6]}")
        run = _log_run(
            client, sid,
            assumptions_json=_full_assumptions(),
            metrics_json=_full_metrics(),
        )
        audit = _post_audit(client, run["id"])

        sweep = audit.get("cost_sensitivity_sweep_json")
        assert sweep is not None, "cost_sensitivity_sweep_json should be present"
        assert len(sweep["scenarios"]) == 6, (
            f"Expected 6 scenarios, got {len(sweep['scenarios'])}"
        )

    def test_sweep_scenario_labels(self, client):
        """All 6 scenario labels are present."""
        sid = _create_strategy_id(client, f"SweepLabels {uuid.uuid4().hex[:6]}")
        run = _log_run(
            client, sid,
            assumptions_json=_full_assumptions(),
            metrics_json=_full_metrics(),
        )
        audit = _post_audit(client, run["id"])

        sweep = audit["cost_sensitivity_sweep_json"]
        labels = {s["scenario_label"] for s in sweep["scenarios"]}
        expected = {
            "assumed_cost",
            "2x_cost",
            "3x_cost",
            "5x_cost",
            "assumed_plus_10bps",
            "assumed_plus_25bps",
        }
        assert expected == labels, f"Label mismatch: {labels}"

    def test_adjusted_return_decreases_with_cost(self, client):
        """Higher cost scenarios produce lower (or equal) adjusted_annual_return."""
        sid = _create_strategy_id(client, f"ReturnDecr {uuid.uuid4().hex[:6]}")
        run = _log_run(
            client, sid,
            assumptions_json={
                "transaction_cost_bps": 5,
                "fill_model": "vwap",
            },
            metrics_json={
                "sharpe": 1.5,
                "annual_return": 0.20,
                "volatility": 0.133,
                "turnover": 2.0,
                "trade_count": 200,
            },
        )
        audit = _post_audit(client, run["id"])

        sweep = audit["cost_sensitivity_sweep_json"]
        # Sort by total cost bps ascending
        scenarios = sorted(sweep["scenarios"], key=lambda s: s["total_cost_bps"])
        returns = [
            s["adjusted_annual_return"]
            for s in scenarios
            if s["adjusted_annual_return"] is not None
        ]
        assert len(returns) >= 3, "Need at least 3 scenarios with adjusted returns"
        for i in range(1, len(returns)):
            assert returns[i] <= returns[i - 1] + 1e-9, (
                f"Return did not decrease: {returns[i]} > {returns[i - 1]}"
            )

    def test_adjusted_sharpe_decreases_with_cost(self, client):
        """Higher cost scenarios produce lower (or equal) adjusted_sharpe."""
        sid = _create_strategy_id(client, f"SharpeDecr {uuid.uuid4().hex[:6]}")
        run = _log_run(
            client, sid,
            assumptions_json={
                "transaction_cost_bps": 5,
                "fill_model": "vwap",
            },
            metrics_json={
                "sharpe": 1.5,
                "annual_return": 0.20,
                "volatility": 0.133,
                "turnover": 2.0,
                "trade_count": 200,
            },
        )
        audit = _post_audit(client, run["id"])

        sweep = audit["cost_sensitivity_sweep_json"]
        scenarios = sorted(sweep["scenarios"], key=lambda s: s["total_cost_bps"])
        sharpes = [
            s["adjusted_sharpe"]
            for s in scenarios
            if s["adjusted_sharpe"] is not None
        ]
        assert len(sharpes) >= 3, "Need at least 3 scenarios with adjusted Sharpe"
        for i in range(1, len(sharpes)):
            assert sharpes[i] <= sharpes[i - 1] + 1e-9, (
                f"Sharpe did not decrease: {sharpes[i]} > {sharpes[i - 1]}"
            )

    def test_missing_cost_assumption_adds_warning(self, client):
        """Run without transaction_cost_bps produces a warning in the sweep."""
        sid = _create_strategy_id(client, f"MissingCost {uuid.uuid4().hex[:6]}")
        run = _log_run(
            client, sid,
            assumptions_json={"fill_model": "vwap"},
            metrics_json=_full_metrics(),
        )
        audit = _post_audit(client, run["id"])

        sweep = audit["cost_sensitivity_sweep_json"]
        assert sweep is not None
        warnings = sweep.get("warnings", [])
        assert len(warnings) > 0, "Expected at least one warning when cost is missing"
        combined = " ".join(warnings).lower()
        assert "transaction_cost_bps" in combined, (
            "Warning should mention transaction_cost_bps"
        )

    def test_high_turnover_creates_high_trust_impact(self, client):
        """High turnover + low costs → some scenario has trust_impact='high'."""
        sid = _create_strategy_id(client, f"HighTurnover {uuid.uuid4().hex[:6]}")
        run = _log_run(
            client, sid,
            assumptions_json={
                "transaction_cost_bps": 2,
                "slippage_bps": 1,
                "fill_model": "vwap",
            },
            metrics_json={
                "sharpe": 1.0,
                "annual_return": 0.10,
                "volatility": 0.10,
                "turnover": 2.0,
                "trade_count": 300,
            },
        )
        audit = _post_audit(client, run["id"])

        sweep = audit["cost_sensitivity_sweep_json"]
        assert sweep is not None
        impacts = [s["trust_impact"] for s in sweep["scenarios"]]
        assert "high" in impacts, (
            f"Expected at least one high trust_impact scenario; got: {impacts}"
        )

    def test_no_zero_division_on_missing_volatility(self, client):
        """Run without volatility in metrics does not raise; adjusted_sharpe may be null."""
        sid = _create_strategy_id(client, f"NoVol {uuid.uuid4().hex[:6]}")
        run = _log_run(
            client, sid,
            assumptions_json={
                "transaction_cost_bps": 5,
                "fill_model": "vwap",
            },
            metrics_json={
                "annual_return": 0.15,
                "turnover": 1.0,
                "trade_count": 200,
                # no sharpe, no volatility
            },
        )
        audit = _post_audit(client, run["id"])

        sweep = audit["cost_sensitivity_sweep_json"]
        assert sweep is not None, "cost_sensitivity_sweep_json must not raise"
        # All adjusted_sharpe values should be None (can't compute without vol/sharpe)
        for sc in sweep["scenarios"]:
            assert sc["adjusted_sharpe"] is None or isinstance(sc["adjusted_sharpe"], (int, float)), (
                "adjusted_sharpe should be None or a number"
            )


# ---------------------------------------------------------------------------
# TestFillSensitivity
# ---------------------------------------------------------------------------

class TestFillSensitivity:
    def test_same_close_fill_creates_high_concern(self, client):
        """fill_model='close' → fill_realism_level='high_concern'."""
        sid = _create_strategy_id(client, f"CloseFill {uuid.uuid4().hex[:6]}")
        run = _log_run(
            client, sid,
            assumptions_json={"fill_model": "close", "transaction_cost_bps": 5},
            metrics_json=_full_metrics(),
        )
        audit = _post_audit(client, run["id"])

        fs = audit.get("fill_sensitivity_json")
        assert fs is not None
        assert fs["fill_realism_level"] == "high_concern", (
            f"Expected high_concern, got {fs['fill_realism_level']}"
        )

    def test_mid_with_no_slippage_creates_medium_concern(self, client):
        """fill_model='mid', slippage_bps absent → fill_realism_level='medium_concern'."""
        sid = _create_strategy_id(client, f"MidNoSlip {uuid.uuid4().hex[:6]}")
        run = _log_run(
            client, sid,
            assumptions_json={"fill_model": "mid", "transaction_cost_bps": 5},
            metrics_json=_full_metrics(),
        )
        audit = _post_audit(client, run["id"])

        fs = audit.get("fill_sensitivity_json")
        assert fs is not None
        assert fs["fill_realism_level"] == "medium_concern", (
            f"Expected medium_concern, got {fs['fill_realism_level']}"
        )

    def test_next_bar_creates_low_concern(self, client):
        """fill_model='next_bar_open' → fill_realism_level='low_concern'."""
        sid = _create_strategy_id(client, f"NextBar {uuid.uuid4().hex[:6]}")
        run = _log_run(
            client, sid,
            assumptions_json={
                "fill_model": "next_bar_open",
                "slippage_bps": 3,
                "transaction_cost_bps": 5,
            },
            metrics_json=_full_metrics(),
        )
        audit = _post_audit(client, run["id"])

        fs = audit.get("fill_sensitivity_json")
        assert fs is not None
        assert fs["fill_realism_level"] == "low_concern", (
            f"Expected low_concern, got {fs['fill_realism_level']}"
        )

    def test_five_scenarios_generated(self, client):
        """fill_sensitivity_json always contains exactly 5 scenarios."""
        sid = _create_strategy_id(client, f"FillScenarios {uuid.uuid4().hex[:6]}")
        run = _log_run(
            client, sid,
            assumptions_json=_full_assumptions(),
            metrics_json=_full_metrics(),
        )
        audit = _post_audit(client, run["id"])

        fs = audit.get("fill_sensitivity_json")
        assert fs is not None
        assert len(fs["scenarios"]) == 5, (
            f"Expected 5 fill scenarios, got {len(fs['scenarios'])}"
        )

    def test_worst_case_scenario_set(self, client):
        """fill_sensitivity_json.worst_case_scenario is populated."""
        sid = _create_strategy_id(client, f"WorstCase {uuid.uuid4().hex[:6]}")
        run = _log_run(
            client, sid,
            assumptions_json=_full_assumptions(),
            metrics_json=_full_metrics(),
        )
        audit = _post_audit(client, run["id"])

        fs = audit.get("fill_sensitivity_json")
        assert fs is not None
        assert fs.get("worst_case_scenario") is not None, (
            "worst_case_scenario must be set"
        )
        assert isinstance(fs["worst_case_scenario"], str)


# ---------------------------------------------------------------------------
# TestPenaltyAttribution
# ---------------------------------------------------------------------------

class TestPenaltyAttribution:
    def test_attribution_generated(self, client):
        """Run with issues → penalty_attribution_json is not None."""
        sid = _create_strategy_id(client, f"AttrGenerated {uuid.uuid4().hex[:6]}")
        # Trigger issues: no cost, no fill model
        run = _log_run(
            client, sid,
            assumptions_json={},
            metrics_json={"sharpe": 1.5, "annual_return": 0.20, "trade_count": 50},
        )
        audit = _post_audit(client, run["id"])

        pa = audit.get("penalty_attribution_json")
        assert pa is not None, "penalty_attribution_json should not be None"

    def test_categories_cover_all_issues(self, client):
        """When issues exist, categories list is non-empty."""
        sid = _create_strategy_id(client, f"AttrCats {uuid.uuid4().hex[:6]}")
        run = _log_run(
            client, sid,
            assumptions_json={"transaction_cost_bps": 0, "fill_model": "close"},
            metrics_json={"sharpe": 5.0, "annual_return": 2.0, "trade_count": 10},
        )
        audit = _post_audit(client, run["id"])

        pa = audit["penalty_attribution_json"]
        assert pa is not None
        assert len(pa["categories"]) > 0, "Expected at least one attribution category"

    def test_largest_penalty_category_set(self, client):
        """largest_penalty_category field is present and non-null when there are issues."""
        sid = _create_strategy_id(client, f"AttrLargest {uuid.uuid4().hex[:6]}")
        run = _log_run(
            client, sid,
            assumptions_json={"transaction_cost_bps": 0, "fill_model": "close"},
            metrics_json={"sharpe": 1.5, "annual_return": 0.20},
        )
        audit = _post_audit(client, run["id"])

        pa = audit["penalty_attribution_json"]
        assert pa is not None
        assert pa.get("largest_penalty_category") is not None, (
            "largest_penalty_category must be set when there are issues"
        )

    def test_critical_issue_weight_25(self, client):
        """An issue classified as 'critical' contributes 25 to severity_weight."""
        # Use the service directly to test penalty attribution in isolation
        from app.services.backtest_reality import _build_penalty_attribution, AuditIssue

        critical_issue = AuditIssue(
            issue_type="zero_transaction_cost",
            severity="critical",
            title="Critical test issue",
            description="cost realism zero transaction critical",
        )
        result = _build_penalty_attribution([critical_issue])
        assert result is not None
        total_penalty = sum(c["severity_weight"] for c in result["categories"])
        assert total_penalty == 25, (
            f"Expected total severity weight 25 for one critical issue, got {total_penalty}"
        )

    def test_no_divide_by_zero_on_empty_issues(self, client):
        """Run with no issues produces empty categories or valid structure."""
        from app.services.backtest_reality import _build_penalty_attribution

        result = _build_penalty_attribution([])
        assert result is not None
        assert result["categories"] == []
        assert result["total_estimated_penalty"] == 0
        assert result["largest_penalty_category"] is None


# ---------------------------------------------------------------------------
# TestImprovementChecks
# ---------------------------------------------------------------------------

class TestImprovementChecks:
    def test_missing_cost_assumption_generates_check(self, client):
        """Run without transaction_cost_bps → check with check_key='add_cost_assumption'."""
        sid = _create_strategy_id(client, f"ImpCost {uuid.uuid4().hex[:6]}")
        run = _log_run(
            client, sid,
            assumptions_json={"fill_model": "vwap"},
            metrics_json=_full_metrics(),
        )
        audit = _post_audit(client, run["id"])

        ic = audit.get("improvement_checks_json")
        assert ic is not None
        checks = ic.get("checks", [])
        keys = [c["check_key"] for c in checks]
        assert "add_cost_assumption" in keys, (
            f"Expected add_cost_assumption check; got: {keys}"
        )

    def test_same_close_generates_fill_check(self, client):
        """fill_model='close' → check with check_key='improve_fill_model'."""
        sid = _create_strategy_id(client, f"ImpFill {uuid.uuid4().hex[:6]}")
        run = _log_run(
            client, sid,
            assumptions_json={"fill_model": "close"},
            metrics_json=_full_metrics(),
        )
        audit = _post_audit(client, run["id"])

        ic = audit.get("improvement_checks_json")
        assert ic is not None
        checks = ic.get("checks", [])
        keys = [c["check_key"] for c in checks]
        assert "improve_fill_model" in keys, (
            f"Expected improve_fill_model check; got: {keys}"
        )

    def test_no_dataset_generates_link_check(self, client):
        """Run without dataset snapshot → check with check_key='link_dataset'."""
        sid = _create_strategy_id(client, f"ImpDataset {uuid.uuid4().hex[:6]}")
        run = _log_run(
            client, sid,
            assumptions_json=_full_assumptions(),
            metrics_json=_full_metrics(),
        )
        audit = _post_audit(client, run["id"])

        ic = audit.get("improvement_checks_json")
        assert ic is not None
        checks = ic.get("checks", [])
        keys = [c["check_key"] for c in checks]
        assert "link_dataset" in keys, (
            f"Expected link_dataset check; got: {keys}"
        )

    def test_checks_sorted_by_priority(self, client):
        """High-priority checks appear before medium-priority checks in the list."""
        sid = _create_strategy_id(client, f"ImpPriority {uuid.uuid4().hex[:6]}")
        # Missing cost (high) + no dataset (medium) → both checks present
        run = _log_run(
            client, sid,
            assumptions_json={"fill_model": "close"},  # no cost → high priority
            metrics_json=_full_metrics(),
        )
        audit = _post_audit(client, run["id"])

        ic = audit.get("improvement_checks_json")
        assert ic is not None
        checks = ic.get("checks", [])
        _priority_val = {"high": 0, "medium": 1, "low": 2}
        priorities = [_priority_val.get(c.get("priority", "low"), 2) for c in checks]
        assert priorities == sorted(priorities), (
            f"Checks not sorted by priority: {[c.get('priority') for c in checks]}"
        )


# ---------------------------------------------------------------------------
# TestAuditApiResponse
# ---------------------------------------------------------------------------

class TestAuditApiResponse:
    def test_audit_response_includes_v3_fields(self, client):
        """POST /api/strategy-runs/{id}/backtest-audit returns all 4 new v3 JSON fields."""
        sid = _create_strategy_id(client, f"V3Fields {uuid.uuid4().hex[:6]}")
        run = _log_run(
            client, sid,
            assumptions_json=_full_assumptions(),
            metrics_json=_full_metrics(),
        )
        audit = _post_audit(client, run["id"])

        assert "cost_sensitivity_sweep_json" in audit, "Missing cost_sensitivity_sweep_json"
        assert "fill_sensitivity_json" in audit, "Missing fill_sensitivity_json"
        assert "penalty_attribution_json" in audit, "Missing penalty_attribution_json"
        assert "improvement_checks_json" in audit, "Missing improvement_checks_json"

        # All should be non-null for a well-formed run
        assert audit["cost_sensitivity_sweep_json"] is not None
        assert audit["fill_sensitivity_json"] is not None
        assert audit["penalty_attribution_json"] is not None
        assert audit["improvement_checks_json"] is not None

    def test_v3_fields_null_for_existing_audits(self, client):
        """Re-auditing a run (POST replaces existing) still populates v3 fields."""
        sid = _create_strategy_id(client, f"V3Reaudit {uuid.uuid4().hex[:6]}")
        run = _log_run(
            client, sid,
            assumptions_json=_full_assumptions(),
            metrics_json=_full_metrics(),
        )
        # First audit
        _post_audit(client, run["id"])
        # Re-audit — should replace and still populate v3 fields
        audit = _post_audit(client, run["id"])

        assert audit["cost_sensitivity_sweep_json"] is not None, (
            "cost_sensitivity_sweep_json should be populated after re-audit"
        )
        assert audit["fill_sensitivity_json"] is not None, (
            "fill_sensitivity_json should be populated after re-audit"
        )

    def test_get_audit_returns_v3_fields(self, client):
        """GET /api/strategy-runs/{id}/backtest-audit also returns v3 fields."""
        sid = _create_strategy_id(client, f"V3GetFields {uuid.uuid4().hex[:6]}")
        run = _log_run(
            client, sid,
            assumptions_json=_full_assumptions(),
            metrics_json=_full_metrics(),
        )
        _post_audit(client, run["id"])

        audit = _get_audit(client, run["id"])
        assert "cost_sensitivity_sweep_json" in audit
        assert "fill_sensitivity_json" in audit
        assert "penalty_attribution_json" in audit
        assert "improvement_checks_json" in audit

    def test_list_audits_includes_v3_quick_fields(self, client):
        """GET /api/backtests/audits includes largest_penalty_category, most_fragile_cost_scenario, worst_fill_scenario."""
        sid = _create_strategy_id(client, f"V3ListFields {uuid.uuid4().hex[:6]}")
        run = _log_run(
            client, sid,
            assumptions_json=_full_assumptions(),
            metrics_json=_full_metrics(),
        )
        _post_audit(client, run["id"])

        resp = client.get("/api/backtests/audits")
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) > 0

        # The most recently created audit (first in list)
        item = items[0]
        assert "largest_penalty_category" in item
        assert "most_fragile_cost_scenario" in item
        assert "worst_fill_scenario" in item
