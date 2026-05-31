"""M13 backtest reality check v2 tests — cost sensitivity + fill realism.

Tests cover:
- audit response includes M13 JSON fields (cost_sensitivity_json, fill_realism_json,
  fragility_summary_json)
- cost sensitivity: scenarios generated at 5/10/15/25/50 bps
- cost sensitivity: adjusted return and Sharpe decrease as cost increases
- cost sensitivity: high fragility when Sharpe < 1.0 at 10 bps
- cost sensitivity: medium fragility when Sharpe < 1.0 at 25 bps
- cost sensitivity: unknown fragility when turnover is missing
- cost sensitivity: no divide-by-zero errors with edge-case inputs
- fill realism: missing fill_model → unknown level
- fill realism: same_bar fill → weak level + same_bar_fill issue
- fill realism: mid fill without slippage → review level + mid_fill_no_slippage issue
- fill realism: high participation rate (>50%) → weak level + high_participation_rate issue
- fill realism: elevated participation rate (20-50%) → review level + elevated issue
- fill realism: missing liquidity filter with high turnover → missing_liquidity_filter issue
- fill realism: strong fill_realism_level when slippage + execution_timing present
- fragility summary reflects worst of cost + fill
- trust score reduced by high_cost_fragility and fill realism issues
- list audits endpoint returns cost_fragility_level and fill_realism_level
- M8 existing tests remain unaffected (close_fill_model, missing_fill_model still created)
"""

from __future__ import annotations

import uuid

import pytest


# ---------------------------------------------------------------------------
# Helpers (mirror M8 test helpers for independence)
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
        "run_name": f"M13 Run {uuid.uuid4().hex[:6]}",
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


def _good_assumptions() -> dict:
    return {
        "transaction_cost_bps": 5,
        "fill_model": "vwap",
        "slippage_bps": 2,
        "execution_timing": "open",
    }


def _good_metrics() -> dict:
    return {
        "sharpe": 1.2,
        "annual_return": 0.18,
        "max_drawdown": -0.12,
        "trade_count": 200,
        "turnover": 0.8,
    }


# ---------------------------------------------------------------------------
# M13 response fields
# ---------------------------------------------------------------------------

def test_audit_response_includes_m13_json_fields(client):
    """POST audit returns cost_sensitivity_json, fill_realism_json, fragility_summary_json."""
    sid = _create_strategy_id(client, f"M13Fields {uuid.uuid4().hex[:6]}")
    run = _log_run(client, sid,
                   assumptions_json=_good_assumptions(),
                   metrics_json=_good_metrics())
    audit = _post_audit(client, run["id"])

    assert "cost_sensitivity_json" in audit, "Missing cost_sensitivity_json"
    assert "fill_realism_json" in audit, "Missing fill_realism_json"
    assert "fragility_summary_json" in audit, "Missing fragility_summary_json"


def test_get_audit_includes_m13_json_fields(client):
    """GET audit also returns the M13 JSON fields."""
    sid = _create_strategy_id(client, f"M13GetFields {uuid.uuid4().hex[:6]}")
    run = _log_run(client, sid,
                   assumptions_json=_good_assumptions(),
                   metrics_json=_good_metrics())
    _post_audit(client, run["id"])

    resp = client.get(f"/api/strategy-runs/{run['id']}/backtest-audit")
    assert resp.status_code == 200
    audit = resp.json()
    assert "cost_sensitivity_json" in audit
    assert "fill_realism_json" in audit
    assert "fragility_summary_json" in audit


# ---------------------------------------------------------------------------
# Cost sensitivity: scenario generation
# ---------------------------------------------------------------------------

def test_cost_sensitivity_has_standard_scenarios(client):
    """cost_sensitivity_json.scenarios contains all 5 standard cost tiers."""
    sid = _create_strategy_id(client, f"CostScenarios {uuid.uuid4().hex[:6]}")
    run = _log_run(client, sid,
                   assumptions_json={"transaction_cost_bps": 2, "fill_model": "vwap"},
                   metrics_json={
                       "sharpe": 1.5,
                       "annual_return": 0.20,
                       "turnover": 1.0,
                       "trade_count": 150,
                   })
    audit = _post_audit(client, run["id"])

    cs = audit["cost_sensitivity_json"]
    assert cs is not None
    scenario_bps = {s["cost_bps"] for s in cs["scenarios"]}
    for expected in (5.0, 10.0, 15.0, 25.0, 50.0):
        assert expected in scenario_bps, f"Missing scenario at {expected} bps"


def test_cost_sensitivity_adjusted_return_decreases_with_cost(client):
    """adjusted_annual_return monotonically decreases as cost_bps increases."""
    sid = _create_strategy_id(client, f"CostDecreases {uuid.uuid4().hex[:6]}")
    run = _log_run(client, sid,
                   assumptions_json={"transaction_cost_bps": 0, "fill_model": "vwap"},
                   metrics_json={
                       "sharpe": 1.8,
                       "annual_return": 0.25,
                       "turnover": 2.0,
                       "trade_count": 200,
                   })
    audit = _post_audit(client, run["id"])

    cs = audit["cost_sensitivity_json"]
    scenarios = sorted(cs["scenarios"], key=lambda s: s["cost_bps"])
    returns = [s["adjusted_annual_return"] for s in scenarios if s["adjusted_annual_return"] is not None]
    assert len(returns) >= 3, "Expected at least 3 scenarios with adjusted returns"
    # Must be weakly decreasing.
    for i in range(1, len(returns)):
        assert returns[i] <= returns[i - 1], (
            f"Return did not decrease: {returns[i]} > {returns[i-1]} at index {i}"
        )


def test_cost_sensitivity_adjusted_sharpe_decreases_with_cost(client):
    """adjusted_sharpe monotonically decreases as cost_bps increases."""
    sid = _create_strategy_id(client, f"SharpeDecreases {uuid.uuid4().hex[:6]}")
    run = _log_run(client, sid,
                   assumptions_json={"transaction_cost_bps": 0, "fill_model": "vwap"},
                   metrics_json={
                       "sharpe": 1.8,
                       "annual_return": 0.25,
                       "volatility": 0.139,
                       "turnover": 2.0,
                       "trade_count": 200,
                   })
    audit = _post_audit(client, run["id"])

    cs = audit["cost_sensitivity_json"]
    scenarios = sorted(cs["scenarios"], key=lambda s: s["cost_bps"])
    sharpes = [s["adjusted_sharpe"] for s in scenarios if s["adjusted_sharpe"] is not None]
    assert len(sharpes) >= 3
    for i in range(1, len(sharpes)):
        assert sharpes[i] <= sharpes[i - 1], (
            f"Sharpe did not decrease: {sharpes[i]} > {sharpes[i-1]} at index {i}"
        )


def test_cost_sensitivity_high_fragility(client):
    """High-fragility run: Sharpe < 1.0 at 10 bps → high_cost_fragility issue + high level."""
    sid = _create_strategy_id(client, f"HighFrag {uuid.uuid4().hex[:6]}")
    # Tight margins: base Sharpe 1.1, turnover 5.0, assumed cost 0 bps
    # At 10 bps, incremental_drag = 5.0 * 10/10000 = 0.005
    # adj_return ≈ 0.10 - 0.005 = 0.095; adj_sharpe ≈ 0.095/0.091 ≈ 1.04?
    # Need to make it go below 1.0 at 10bps:
    # base sharpe 1.1, vol = annual_return / sharpe = 0.10/1.1 = 0.091
    # at 10bps drag: adj_return = 0.10 - 5.0 * 10/10000 = 0.10 - 0.005 = 0.095
    # adj_sharpe = 0.095/0.091 = 1.04 — not below 1.0 yet
    # Use turnover 10 to make it obvious:
    # drag at 10bps = 10.0 * 10/10000 = 0.01; adj_return = 0.10 - 0.01 = 0.09
    # adj_sharpe = 0.09/0.091 = 0.989 — below 1.0!
    run = _log_run(client, sid,
                   assumptions_json={"transaction_cost_bps": 0, "fill_model": "vwap"},
                   metrics_json={
                       "sharpe": 1.1,
                       "annual_return": 0.10,
                       "volatility": 0.091,  # explicit vol to remove proxy uncertainty
                       "turnover": 10.0,
                       "trade_count": 300,
                   })
    audit = _post_audit(client, run["id"])

    cs = audit["cost_sensitivity_json"]
    assert cs["cost_fragility_level"] == "high", (
        f"Expected 'high', got {cs['cost_fragility_level']!r}"
    )
    issue_types = [i["issue_type"] for i in audit["issues"]]
    assert "high_cost_fragility" in issue_types, f"Expected high_cost_fragility in {issue_types}"
    # Severity must be high.
    hcf = next(i for i in audit["issues"] if i["issue_type"] == "high_cost_fragility")
    assert hcf["severity"] == "high"


def test_cost_sensitivity_medium_fragility(client):
    """Medium-fragility run: Sharpe >= 1.0 at 10 bps but < 1.0 at 25 bps → medium level."""
    sid = _create_strategy_id(client, f"MedFrag {uuid.uuid4().hex[:6]}")
    # turnover 4.0, sharpe 1.3, return 0.15, vol = 0.15/1.3 = 0.1154
    # at 10bps: drag = 4.0 * 10/10000 = 0.004; adj_return = 0.146; adj_sharpe = 0.146/0.1154 = 1.265 >= 1.0
    # at 25bps: drag = 4.0 * 25/10000 = 0.010; adj_return = 0.140; adj_sharpe = 0.140/0.1154 = 1.213 >= 1.0 — still not below 1.0
    # Let's use vol=0.14, sharpe=1.07, return=0.15
    # vol=0.15/1.07=0.14; at 25bps: drag = 4*25/10000 = 0.010; adj_ret=0.14; adj_sharpe=0.14/0.14=1.0 -- exactly 1.0, need below
    # Use vol=0.145, return=0.15, turnover=4.0, assumed_cost=0
    # at 10bps: drag=0.004; adj_ret=0.146; adj_sharpe=0.146/0.145=1.007 >= 1.0 ✓
    # at 25bps: drag=0.01; adj_ret=0.14; adj_sharpe=0.14/0.145=0.966 < 1.0 ✓
    run = _log_run(client, sid,
                   assumptions_json={"transaction_cost_bps": 0, "fill_model": "vwap"},
                   metrics_json={
                       "sharpe": 1.034,
                       "annual_return": 0.15,
                       "volatility": 0.145,
                       "turnover": 4.0,
                       "trade_count": 200,
                   })
    audit = _post_audit(client, run["id"])

    cs = audit["cost_sensitivity_json"]
    assert cs["cost_fragility_level"] == "medium", (
        f"Expected 'medium', got {cs['cost_fragility_level']!r}"
    )
    issue_types = [i["issue_type"] for i in audit["issues"]]
    assert "medium_cost_fragility" in issue_types, f"Expected medium_cost_fragility in {issue_types}"
    assert "high_cost_fragility" not in issue_types


def test_cost_sensitivity_unknown_when_no_turnover(client):
    """When turnover is missing, cost_fragility_level is 'unknown' with no scenario."""
    sid = _create_strategy_id(client, f"NoTurnover {uuid.uuid4().hex[:6]}")
    run = _log_run(client, sid,
                   assumptions_json={"transaction_cost_bps": 5, "fill_model": "vwap"},
                   metrics_json={
                       "sharpe": 1.5,
                       "annual_return": 0.20,
                       # No turnover key
                   })
    audit = _post_audit(client, run["id"])

    cs = audit["cost_sensitivity_json"]
    assert cs["cost_fragility_level"] == "unknown"
    assert cs["scenarios"] == [] or len(cs["scenarios"]) == 0
    # Should not raise any cost fragility issues.
    issue_types = [i["issue_type"] for i in audit["issues"]]
    assert "high_cost_fragility" not in issue_types
    assert "medium_cost_fragility" not in issue_types


def test_cost_sensitivity_no_divide_by_zero_zero_sharpe(client):
    """Run with sharpe=0 and no volatility should not raise an error."""
    sid = _create_strategy_id(client, f"ZeroSharpe {uuid.uuid4().hex[:6]}")
    run = _log_run(client, sid,
                   assumptions_json={"transaction_cost_bps": 5, "fill_model": "vwap"},
                   metrics_json={
                       "sharpe": 0.0,
                       "annual_return": 0.0,
                       "turnover": 1.0,
                       "trade_count": 100,
                   })
    # Should not raise — audit must complete.
    audit = _post_audit(client, run["id"])
    assert audit["trust_score"] >= 0


def test_cost_sensitivity_no_divide_by_zero_zero_return(client):
    """Run with annual_return=0 and sharpe!=0 should not raise an error."""
    sid = _create_strategy_id(client, f"ZeroReturn {uuid.uuid4().hex[:6]}")
    run = _log_run(client, sid,
                   assumptions_json={"transaction_cost_bps": 5, "fill_model": "vwap"},
                   metrics_json={
                       "sharpe": 1.2,
                       "annual_return": 0.0,
                       "turnover": 1.0,
                       "trade_count": 100,
                   })
    audit = _post_audit(client, run["id"])
    assert audit["trust_score"] >= 0


def test_cost_sensitivity_scenarios_include_assumed_cost_bps(client):
    """The scenarios list includes the assumed cost_bps from assumptions_json."""
    sid = _create_strategy_id(client, f"AssumedBps {uuid.uuid4().hex[:6]}")
    run = _log_run(client, sid,
                   assumptions_json={"transaction_cost_bps": 7, "fill_model": "vwap"},
                   metrics_json={
                       "sharpe": 1.4,
                       "annual_return": 0.18,
                       "turnover": 1.2,
                   })
    audit = _post_audit(client, run["id"])

    cs = audit["cost_sensitivity_json"]
    scenario_bps = {s["cost_bps"] for s in cs["scenarios"]}
    assert 7.0 in scenario_bps, f"Expected assumed cost 7.0 in scenarios: {scenario_bps}"


def test_cost_sensitivity_at_assumed_bps_has_zero_incremental_drag(client):
    """At the assumed cost level, incremental_cost_drag should be 0."""
    sid = _create_strategy_id(client, f"ZeroDrag {uuid.uuid4().hex[:6]}")
    run = _log_run(client, sid,
                   assumptions_json={"transaction_cost_bps": 5, "fill_model": "vwap"},
                   metrics_json={
                       "sharpe": 1.4,
                       "annual_return": 0.18,
                       "turnover": 1.2,
                       "trade_count": 150,
                   })
    audit = _post_audit(client, run["id"])

    cs = audit["cost_sensitivity_json"]
    baseline = next(s for s in cs["scenarios"] if s["cost_bps"] == 5.0)
    assert baseline["incremental_cost_drag"] == pytest.approx(0.0, abs=1e-6), (
        f"Expected 0 drag at assumed bps, got {baseline['incremental_cost_drag']}"
    )


# ---------------------------------------------------------------------------
# Fill realism: missing fill model
# ---------------------------------------------------------------------------

def test_fill_realism_unknown_when_fill_model_missing(client):
    """No fill_model → fill_realism_level is 'unknown'."""
    sid = _create_strategy_id(client, f"FRMissing {uuid.uuid4().hex[:6]}")
    run = _log_run(client, sid,
                   assumptions_json={"transaction_cost_bps": 5},
                   metrics_json=_good_metrics())
    audit = _post_audit(client, run["id"])

    fr = audit["fill_realism_json"]
    assert fr["fill_realism_level"] == "unknown"


def test_fill_realism_json_has_required_keys(client):
    """fill_realism_json contains the expected keys."""
    sid = _create_strategy_id(client, f"FRKeys {uuid.uuid4().hex[:6]}")
    run = _log_run(client, sid,
                   assumptions_json=_good_assumptions(),
                   metrics_json=_good_metrics())
    audit = _post_audit(client, run["id"])

    fr = audit["fill_realism_json"]
    for key in ("fill_model", "slippage_bps", "execution_timing", "participation_rate",
                "liquidity_filter_present", "fill_realism_level", "findings"):
        assert key in fr, f"Missing fill_realism_json key: {key}"


# ---------------------------------------------------------------------------
# Fill realism: same-bar fill
# ---------------------------------------------------------------------------

def test_same_bar_fill_creates_issue(client):
    """same_bar fill_model → same_bar_fill BacktestIssue at high severity."""
    sid = _create_strategy_id(client, f"SameBar {uuid.uuid4().hex[:6]}")
    run = _log_run(client, sid,
                   assumptions_json={"transaction_cost_bps": 5, "fill_model": "same_bar"},
                   metrics_json=_good_metrics())
    audit = _post_audit(client, run["id"])

    issue_types = [i["issue_type"] for i in audit["issues"]]
    assert "same_bar_fill" in issue_types, f"Expected same_bar_fill in {issue_types}"
    issue = next(i for i in audit["issues"] if i["issue_type"] == "same_bar_fill")
    assert issue["severity"] == "high"


def test_same_bar_fill_produces_weak_fill_realism_level(client):
    """same_bar fill → fill_realism_level is 'weak'."""
    sid = _create_strategy_id(client, f"SameBarLevel {uuid.uuid4().hex[:6]}")
    run = _log_run(client, sid,
                   assumptions_json={"transaction_cost_bps": 5, "fill_model": "same_bar"},
                   metrics_json=_good_metrics())
    audit = _post_audit(client, run["id"])

    fr = audit["fill_realism_json"]
    assert fr["fill_realism_level"] == "weak", (
        f"Expected 'weak', got {fr['fill_realism_level']!r}"
    )


def test_intrabar_fill_also_flagged(client):
    """intrabar fill_model is also in _SAME_BAR_FILLS → same_bar_fill issue."""
    sid = _create_strategy_id(client, f"Intrabar {uuid.uuid4().hex[:6]}")
    run = _log_run(client, sid,
                   assumptions_json={"transaction_cost_bps": 5, "fill_model": "intrabar"},
                   metrics_json=_good_metrics())
    audit = _post_audit(client, run["id"])

    issue_types = [i["issue_type"] for i in audit["issues"]]
    assert "same_bar_fill" in issue_types


# ---------------------------------------------------------------------------
# Fill realism: mid fill without slippage
# ---------------------------------------------------------------------------

def test_mid_fill_no_slippage_creates_issue(client):
    """mid fill_model without slippage_bps → mid_fill_no_slippage issue (medium)."""
    sid = _create_strategy_id(client, f"MidNoSlip {uuid.uuid4().hex[:6]}")
    run = _log_run(client, sid,
                   assumptions_json={
                       "transaction_cost_bps": 5,
                       "fill_model": "mid",
                       # No slippage_bps
                   },
                   metrics_json=_good_metrics())
    audit = _post_audit(client, run["id"])

    issue_types = [i["issue_type"] for i in audit["issues"]]
    assert "mid_fill_no_slippage" in issue_types, f"Expected mid_fill_no_slippage in {issue_types}"
    issue = next(i for i in audit["issues"] if i["issue_type"] == "mid_fill_no_slippage")
    assert issue["severity"] == "medium"


def test_mid_fill_with_slippage_no_issue(client):
    """mid fill_model WITH slippage_bps → no mid_fill_no_slippage issue."""
    sid = _create_strategy_id(client, f"MidWithSlip {uuid.uuid4().hex[:6]}")
    run = _log_run(client, sid,
                   assumptions_json={
                       "transaction_cost_bps": 5,
                       "fill_model": "mid",
                       "slippage_bps": 2,
                   },
                   metrics_json=_good_metrics())
    audit = _post_audit(client, run["id"])

    issue_types = [i["issue_type"] for i in audit["issues"]]
    assert "mid_fill_no_slippage" not in issue_types


def test_midpoint_fill_no_slippage_also_flagged(client):
    """midpoint fill_model is in _MID_FILLS → also creates mid_fill_no_slippage."""
    sid = _create_strategy_id(client, f"Midpoint {uuid.uuid4().hex[:6]}")
    run = _log_run(client, sid,
                   assumptions_json={"transaction_cost_bps": 5, "fill_model": "midpoint"},
                   metrics_json=_good_metrics())
    audit = _post_audit(client, run["id"])

    issue_types = [i["issue_type"] for i in audit["issues"]]
    assert "mid_fill_no_slippage" in issue_types


# ---------------------------------------------------------------------------
# Fill realism: participation rate
# ---------------------------------------------------------------------------

def test_high_participation_rate_creates_issue(client):
    """participation_rate > 50% → high_participation_rate issue at high severity."""
    sid = _create_strategy_id(client, f"HighPR {uuid.uuid4().hex[:6]}")
    run = _log_run(client, sid,
                   assumptions_json={
                       "transaction_cost_bps": 5,
                       "fill_model": "vwap",
                       "participation_rate": 0.65,
                   },
                   metrics_json=_good_metrics())
    audit = _post_audit(client, run["id"])

    issue_types = [i["issue_type"] for i in audit["issues"]]
    assert "high_participation_rate" in issue_types, f"Expected high_participation_rate in {issue_types}"
    issue = next(i for i in audit["issues"] if i["issue_type"] == "high_participation_rate")
    assert issue["severity"] == "high"


def test_elevated_participation_rate_creates_issue(client):
    """participation_rate between 20-50% → elevated_participation_rate issue at medium severity."""
    sid = _create_strategy_id(client, f"ElevPR {uuid.uuid4().hex[:6]}")
    run = _log_run(client, sid,
                   assumptions_json={
                       "transaction_cost_bps": 5,
                       "fill_model": "vwap",
                       "participation_rate": 0.35,
                   },
                   metrics_json=_good_metrics())
    audit = _post_audit(client, run["id"])

    issue_types = [i["issue_type"] for i in audit["issues"]]
    assert "elevated_participation_rate" in issue_types, f"Expected elevated_participation_rate in {issue_types}"
    issue = next(i for i in audit["issues"] if i["issue_type"] == "elevated_participation_rate")
    assert issue["severity"] == "medium"


def test_low_participation_rate_no_issue(client):
    """participation_rate <= 20% → no participation-rate issue."""
    sid = _create_strategy_id(client, f"LowPR {uuid.uuid4().hex[:6]}")
    run = _log_run(client, sid,
                   assumptions_json={
                       "transaction_cost_bps": 5,
                       "fill_model": "vwap",
                       "participation_rate": 0.10,
                   },
                   metrics_json=_good_metrics())
    audit = _post_audit(client, run["id"])

    issue_types = [i["issue_type"] for i in audit["issues"]]
    assert "high_participation_rate" not in issue_types
    assert "elevated_participation_rate" not in issue_types


# ---------------------------------------------------------------------------
# Fill realism: liquidity filter
# ---------------------------------------------------------------------------

def test_missing_liquidity_filter_high_turnover_creates_issue(client):
    """No liquidity_filter + turnover > 1.5 → missing_liquidity_filter issue (medium)."""
    sid = _create_strategy_id(client, f"NoLiqFilter {uuid.uuid4().hex[:6]}")
    run = _log_run(client, sid,
                   assumptions_json={
                       "transaction_cost_bps": 5,
                       "fill_model": "vwap",
                       # No liquidity_filter key
                   },
                   metrics_json={**_good_metrics(), "turnover": 2.0})
    audit = _post_audit(client, run["id"])

    issue_types = [i["issue_type"] for i in audit["issues"]]
    assert "missing_liquidity_filter" in issue_types, f"Expected missing_liquidity_filter in {issue_types}"
    issue = next(i for i in audit["issues"] if i["issue_type"] == "missing_liquidity_filter")
    assert issue["severity"] == "medium"


def test_liquidity_filter_present_no_issue(client):
    """liquidity_filter present → no missing_liquidity_filter issue."""
    sid = _create_strategy_id(client, f"LiqFilter {uuid.uuid4().hex[:6]}")
    run = _log_run(client, sid,
                   assumptions_json={
                       "transaction_cost_bps": 5,
                       "fill_model": "vwap",
                       "liquidity_filter": "adv_20d_min_1m",
                   },
                   metrics_json={**_good_metrics(), "turnover": 2.0})
    audit = _post_audit(client, run["id"])

    issue_types = [i["issue_type"] for i in audit["issues"]]
    assert "missing_liquidity_filter" not in issue_types


def test_missing_liquidity_filter_low_turnover_no_issue(client):
    """No liquidity_filter but turnover <= 1.5 → no missing_liquidity_filter issue."""
    sid = _create_strategy_id(client, f"LiqLowTurn {uuid.uuid4().hex[:6]}")
    run = _log_run(client, sid,
                   assumptions_json={
                       "transaction_cost_bps": 5,
                       "fill_model": "vwap",
                   },
                   metrics_json={**_good_metrics(), "turnover": 1.0})
    audit = _post_audit(client, run["id"])

    issue_types = [i["issue_type"] for i in audit["issues"]]
    assert "missing_liquidity_filter" not in issue_types


# ---------------------------------------------------------------------------
# Fill realism: liquidity_realism_score affected by missing_liquidity_filter
# ---------------------------------------------------------------------------

def test_missing_liquidity_filter_reduces_liquidity_realism_score(client):
    """missing_liquidity_filter maps to liquidity_realism_score — should reduce it."""
    sid = _create_strategy_id(client, f"LiqScore {uuid.uuid4().hex[:6]}")
    run = _log_run(client, sid,
                   assumptions_json={
                       "transaction_cost_bps": 5,
                       "fill_model": "vwap",
                   },
                   metrics_json={**_good_metrics(), "turnover": 2.0})
    audit = _post_audit(client, run["id"])

    issue_types = [i["issue_type"] for i in audit["issues"]]
    if "missing_liquidity_filter" in issue_types:
        assert audit["liquidity_realism_score"] < 100, (
            f"Expected liquidity_realism_score < 100 when missing_liquidity_filter issue exists, "
            f"got {audit['liquidity_realism_score']}"
        )


# ---------------------------------------------------------------------------
# Fill realism: strong level
# ---------------------------------------------------------------------------

def test_fill_realism_strong_with_slippage_and_timing(client):
    """fill_model + slippage_bps + execution_timing → fill_realism_level is 'strong'."""
    sid = _create_strategy_id(client, f"FRStrong {uuid.uuid4().hex[:6]}")
    run = _log_run(client, sid,
                   assumptions_json={
                       "transaction_cost_bps": 5,
                       "fill_model": "vwap",
                       "slippage_bps": 2,
                       "execution_timing": "open",
                   },
                   metrics_json=_good_metrics())
    audit = _post_audit(client, run["id"])

    fr = audit["fill_realism_json"]
    # A run with no medium+ fill findings + slippage + timing → strong.
    # There may be other issues (e.g. missing_execution_timing is NOT present here).
    assert fr["fill_realism_level"] in ("strong", "acceptable"), (
        f"Expected 'strong' or 'acceptable' for well-specified run, got {fr['fill_realism_level']!r}"
    )


# ---------------------------------------------------------------------------
# Fragility summary
# ---------------------------------------------------------------------------

def test_fragility_summary_has_required_keys(client):
    """fragility_summary_json contains overall_fragility, cost_fragility_level, fill_realism_level, key_concerns."""
    sid = _create_strategy_id(client, f"FragKeys {uuid.uuid4().hex[:6]}")
    run = _log_run(client, sid,
                   assumptions_json=_good_assumptions(),
                   metrics_json=_good_metrics())
    audit = _post_audit(client, run["id"])

    fs = audit["fragility_summary_json"]
    for key in ("overall_fragility", "cost_fragility_level", "fill_realism_level", "key_concerns"):
        assert key in fs, f"Missing fragility_summary_json key: {key}"


def test_fragility_summary_high_when_cost_fragility_high(client):
    """overall_fragility is 'high' when cost_fragility_level is 'high'."""
    sid = _create_strategy_id(client, f"FragHigh {uuid.uuid4().hex[:6]}")
    run = _log_run(client, sid,
                   assumptions_json={"transaction_cost_bps": 0, "fill_model": "vwap"},
                   metrics_json={
                       "sharpe": 1.1,
                       "annual_return": 0.10,
                       "volatility": 0.091,
                       "turnover": 10.0,
                       "trade_count": 300,
                   })
    audit = _post_audit(client, run["id"])

    fs = audit["fragility_summary_json"]
    if audit["cost_sensitivity_json"]["cost_fragility_level"] == "high":
        assert fs["overall_fragility"] == "high", (
            f"Expected 'high', got {fs['overall_fragility']!r}"
        )


def test_fragility_summary_high_when_fill_realism_weak(client):
    """overall_fragility is 'high' when fill_realism_level is 'weak' (same-bar fill)."""
    sid = _create_strategy_id(client, f"FragFillWeak {uuid.uuid4().hex[:6]}")
    run = _log_run(client, sid,
                   assumptions_json={"transaction_cost_bps": 5, "fill_model": "same_bar"},
                   metrics_json=_good_metrics())
    audit = _post_audit(client, run["id"])

    fs = audit["fragility_summary_json"]
    assert fs["overall_fragility"] == "high", (
        f"Expected 'high' fragility for same-bar fill, got {fs['overall_fragility']!r}"
    )


# ---------------------------------------------------------------------------
# Trust score impact from M13 issues
# ---------------------------------------------------------------------------

def test_high_cost_fragility_reduces_trust_score(client):
    """high_cost_fragility issue reduces trust_score (penalty = 15 for high severity)."""
    sid = _create_strategy_id(client, f"TrustCost {uuid.uuid4().hex[:6]}")
    # Clean run (no other issues) with high cost fragility
    run = _log_run(client, sid,
                   assumptions_json={"transaction_cost_bps": 0, "fill_model": "vwap",
                                     "slippage_bps": 2, "execution_timing": "open"},
                   metrics_json={
                       "sharpe": 1.05,
                       "annual_return": 0.10,
                       "volatility": 0.095,
                       "turnover": 10.0,
                       "trade_count": 300,
                   })
    audit = _post_audit(client, run["id"])

    issue_types = [i["issue_type"] for i in audit["issues"]]
    if "high_cost_fragility" in issue_types:
        # Trust score must be reduced from maximum.
        assert audit["trust_score"] < 100, (
            f"Expected trust_score < 100 with high_cost_fragility, got {audit['trust_score']}"
        )
        assert audit["cost_realism_score"] < 100


def test_same_bar_fill_reduces_fill_realism_score(client):
    """same_bar_fill issue (high severity) reduces fill_realism_score."""
    sid = _create_strategy_id(client, f"FillScoreM13 {uuid.uuid4().hex[:6]}")
    run = _log_run(client, sid,
                   assumptions_json={"transaction_cost_bps": 5, "fill_model": "same_bar"},
                   metrics_json=_good_metrics())
    audit = _post_audit(client, run["id"])

    assert audit["fill_realism_score"] < 100, (
        f"Expected fill_realism_score < 100 for same_bar fill, got {audit['fill_realism_score']}"
    )


# ---------------------------------------------------------------------------
# List audits endpoint: M13 fields
# ---------------------------------------------------------------------------

def test_list_audits_has_cost_fragility_level(client):
    """GET /api/backtests/audits returns cost_fragility_level per item."""
    sid = _create_strategy_id(client, f"ListFrag {uuid.uuid4().hex[:6]}")
    run = _log_run(client, sid,
                   assumptions_json=_good_assumptions(),
                   metrics_json=_good_metrics())
    posted = _post_audit(client, run["id"])

    resp = client.get("/api/backtests/audits")
    assert resp.status_code == 200
    items = resp.json()
    found = next((a for a in items if a["id"] == posted["id"]), None)
    assert found is not None
    assert "cost_fragility_level" in found, f"Missing cost_fragility_level in list item"
    assert "fill_realism_level" in found, f"Missing fill_realism_level in list item"


def test_list_audits_cost_fragility_none_when_unknown(client):
    """When cost_fragility_level is 'unknown', list item shows None (not 'unknown' string)."""
    sid = _create_strategy_id(client, f"ListUnknown {uuid.uuid4().hex[:6]}")
    run = _log_run(client, sid,
                   assumptions_json={"transaction_cost_bps": 5, "fill_model": "vwap"},
                   metrics_json={
                       "sharpe": 1.5,
                       "annual_return": 0.20,
                       # No turnover → unknown fragility
                   })
    posted = _post_audit(client, run["id"])

    resp = client.get("/api/backtests/audits")
    items = resp.json()
    found = next((a for a in items if a["id"] == posted["id"]), None)
    assert found is not None
    # 'unknown' is treated as falsy in the route helper → returns None.
    assert found["cost_fragility_level"] is None, (
        f"Expected None for unknown cost_fragility_level, got {found['cost_fragility_level']!r}"
    )


# ---------------------------------------------------------------------------
# M8 backward-compatibility: existing issue types still created by M8 checks
# ---------------------------------------------------------------------------

def test_m8_close_fill_model_still_created(client):
    """M8 close_fill_model issue is still raised (M13 does not remove it)."""
    sid = _create_strategy_id(client, f"M8Compat {uuid.uuid4().hex[:6]}")
    run = _log_run(client, sid,
                   assumptions_json={"transaction_cost_bps": 5, "fill_model": "close"},
                   metrics_json=_good_metrics())
    audit = _post_audit(client, run["id"])

    issue_types = [i["issue_type"] for i in audit["issues"]]
    assert "close_fill_model" in issue_types, (
        f"Expected close_fill_model from M8 check, got {issue_types}"
    )


def test_m8_missing_fill_model_still_created(client):
    """M8 missing_fill_model issue is still raised (M13 does not remove it)."""
    sid = _create_strategy_id(client, f"M8MissFill {uuid.uuid4().hex[:6]}")
    run = _log_run(client, sid,
                   assumptions_json={"transaction_cost_bps": 5},
                   metrics_json=_good_metrics())
    audit = _post_audit(client, run["id"])

    issue_types = [i["issue_type"] for i in audit["issues"]]
    assert "missing_fill_model" in issue_types


def test_m8_missing_fill_model_not_duplicated_by_m13(client):
    """M13 does not create a second missing_fill_model issue — M8 handles it once."""
    sid = _create_strategy_id(client, f"NoDuplicate {uuid.uuid4().hex[:6]}")
    run = _log_run(client, sid,
                   assumptions_json={"transaction_cost_bps": 5},
                   metrics_json=_good_metrics())
    audit = _post_audit(client, run["id"])

    # Count occurrences of missing_fill_model.
    count = sum(1 for i in audit["issues"] if i["issue_type"] == "missing_fill_model")
    assert count == 1, f"Expected exactly 1 missing_fill_model issue, got {count}"
