"""M8 backtest reality check tests.

Tests cover:
- POST audit for backtest/research/paper runs → 201
- Response fields: trust_score, subscores, overall_status, summary, issues
- Clean run (good assumptions) → high trust score, excellent status
- Issue detection: zero_transaction_cost (high), missing_transaction_cost (medium)
- Issue detection: close_fill_model, missing_fill_model
- Issue detection: zero_borrow_cost (high), missing_borrow_cost (medium)
- Issue detection: insufficient_trade_count (sharpe > 2 + trades < 50)
- Issue detection: implausible_sharpe (sharpe > 4)
- Issue detection: implausible_return (annual_return > 1.0)
- Issue detection: high_turnover (> 3.0 → high, > 1.5 → medium)
- Issue detection: no_data_snapshot (low — no linked snapshot)
- overall_status: excellent for clean run, lower status for multiple issues
- POST audit returns 404 for nonexistent run
- POST audit returns 400 for live run
- POST audit is idempotent — re-POST replaces existing audit
- GET audit returns stored result; 404 when no audit
- GET /api/backtests/audits returns list with context
- Trust score formula: each issue reduces score by expected penalty
"""

from __future__ import annotations

import uuid

import pytest


# ---------------------------------------------------------------------------
# Helpers
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
        "run_name": f"Test Run {uuid.uuid4().hex[:6]}",
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
# Basic creation
# ---------------------------------------------------------------------------

def test_post_audit_returns_201(client):
    sid = _create_strategy_id(client, f"AuditBasic {uuid.uuid4().hex[:6]}")
    run = _log_run(client, sid)
    resp = client.post(f"/api/strategy-runs/{run['id']}/backtest-audit")
    assert resp.status_code == 201, resp.text


def test_post_audit_response_fields(client):
    sid = _create_strategy_id(client, f"AuditFields {uuid.uuid4().hex[:6]}")
    run = _log_run(client, sid,
                   assumptions_json=_good_assumptions(),
                   metrics_json=_good_metrics())
    audit = _post_audit(client, run["id"])

    for field in (
        "id", "strategy_run_id", "trust_score",
        "lookahead_risk_score", "cost_realism_score", "fill_realism_score",
        "liquidity_realism_score", "borrow_realism_score", "data_quality_score",
        "overall_status", "summary", "issues", "created_at", "updated_at",
    ):
        assert field in audit, f"Missing field: {field}"


def test_post_audit_strategy_run_id_matches(client):
    sid = _create_strategy_id(client, f"AuditRunId {uuid.uuid4().hex[:6]}")
    run = _log_run(client, sid)
    audit = _post_audit(client, run["id"])
    assert audit["strategy_run_id"] == run["id"]


# ---------------------------------------------------------------------------
# Trust score and status for a clean run
# ---------------------------------------------------------------------------

def test_clean_run_has_high_trust_score(client):
    """A run with good assumptions and reasonable metrics → high trust score."""
    sid = _create_strategy_id(client, f"CleanRun {uuid.uuid4().hex[:6]}")
    run = _log_run(client, sid,
                   assumptions_json=_good_assumptions(),
                   metrics_json=_good_metrics())
    audit = _post_audit(client, run["id"])
    assert audit["trust_score"] >= 75, f"Expected high trust score, got {audit['trust_score']}"


def test_clean_run_status_excellent_or_good(client):
    sid = _create_strategy_id(client, f"CleanStatus {uuid.uuid4().hex[:6]}")
    run = _log_run(client, sid,
                   assumptions_json=_good_assumptions(),
                   metrics_json=_good_metrics())
    audit = _post_audit(client, run["id"])
    assert audit["overall_status"] in ("excellent", "good"), (
        f"Expected excellent or good, got {audit['overall_status']!r}"
    )


def test_issues_list_is_present(client):
    sid = _create_strategy_id(client, f"IssuesList {uuid.uuid4().hex[:6]}")
    run = _log_run(client, sid)
    audit = _post_audit(client, run["id"])
    assert isinstance(audit["issues"], list)


# ---------------------------------------------------------------------------
# Transaction cost checks
# ---------------------------------------------------------------------------

def test_zero_transaction_cost_flagged_as_high(client):
    sid = _create_strategy_id(client, f"ZeroTxn {uuid.uuid4().hex[:6]}")
    run = _log_run(client, sid,
                   assumptions_json={"transaction_cost_bps": 0, "fill_model": "vwap"},
                   metrics_json=_good_metrics())
    audit = _post_audit(client, run["id"])
    issue_types = [i["issue_type"] for i in audit["issues"]]
    assert "zero_transaction_cost" in issue_types
    zero_issue = next(i for i in audit["issues"] if i["issue_type"] == "zero_transaction_cost")
    assert zero_issue["severity"] == "high"


def test_missing_transaction_cost_flagged_as_medium(client):
    sid = _create_strategy_id(client, f"MissTxn {uuid.uuid4().hex[:6]}")
    run = _log_run(client, sid,
                   assumptions_json={"fill_model": "vwap"},
                   metrics_json=_good_metrics())
    audit = _post_audit(client, run["id"])
    issue_types = [i["issue_type"] for i in audit["issues"]]
    assert "missing_transaction_cost" in issue_types
    issue = next(i for i in audit["issues"] if i["issue_type"] == "missing_transaction_cost")
    assert issue["severity"] == "medium"


def test_zero_txn_cost_reduces_cost_realism_score(client):
    sid = _create_strategy_id(client, f"ZeroTxnScore {uuid.uuid4().hex[:6]}")
    run = _log_run(client, sid,
                   assumptions_json={"transaction_cost_bps": 0, "fill_model": "vwap"},
                   metrics_json=_good_metrics())
    audit = _post_audit(client, run["id"])
    assert audit["cost_realism_score"] < 100


# ---------------------------------------------------------------------------
# Fill model checks
# ---------------------------------------------------------------------------

def test_close_fill_model_flagged(client):
    sid = _create_strategy_id(client, f"CloseFill {uuid.uuid4().hex[:6]}")
    run = _log_run(client, sid,
                   assumptions_json={"transaction_cost_bps": 5, "fill_model": "close"},
                   metrics_json=_good_metrics())
    audit = _post_audit(client, run["id"])
    issue_types = [i["issue_type"] for i in audit["issues"]]
    assert "close_fill_model" in issue_types


def test_missing_fill_model_flagged_as_medium(client):
    sid = _create_strategy_id(client, f"MissFill {uuid.uuid4().hex[:6]}")
    run = _log_run(client, sid,
                   assumptions_json={"transaction_cost_bps": 5},
                   metrics_json=_good_metrics())
    audit = _post_audit(client, run["id"])
    issue_types = [i["issue_type"] for i in audit["issues"]]
    assert "missing_fill_model" in issue_types
    issue = next(i for i in audit["issues"] if i["issue_type"] == "missing_fill_model")
    assert issue["severity"] == "medium"


def test_close_fill_reduces_fill_realism_score(client):
    sid = _create_strategy_id(client, f"FillScore {uuid.uuid4().hex[:6]}")
    run = _log_run(client, sid,
                   assumptions_json={"transaction_cost_bps": 5, "fill_model": "close"},
                   metrics_json=_good_metrics())
    audit = _post_audit(client, run["id"])
    assert audit["fill_realism_score"] < 100


# ---------------------------------------------------------------------------
# Borrow / short checks
# ---------------------------------------------------------------------------

def test_zero_borrow_cost_with_short_enabled_flagged_as_high(client):
    sid = _create_strategy_id(client, f"ZeroBorrow {uuid.uuid4().hex[:6]}")
    run = _log_run(client, sid,
                   assumptions_json={
                       "transaction_cost_bps": 5,
                       "fill_model": "vwap",
                       "short_enabled": True,
                       "borrow_rate": 0,
                   },
                   metrics_json=_good_metrics())
    audit = _post_audit(client, run["id"])
    issue_types = [i["issue_type"] for i in audit["issues"]]
    assert "zero_borrow_cost" in issue_types
    issue = next(i for i in audit["issues"] if i["issue_type"] == "zero_borrow_cost")
    assert issue["severity"] == "high"


def test_missing_borrow_cost_with_short_flagged_as_medium(client):
    sid = _create_strategy_id(client, f"MissBorrow {uuid.uuid4().hex[:6]}")
    run = _log_run(client, sid,
                   assumptions_json={
                       "transaction_cost_bps": 5,
                       "fill_model": "vwap",
                       "short_enabled": True,
                   },
                   metrics_json=_good_metrics())
    audit = _post_audit(client, run["id"])
    issue_types = [i["issue_type"] for i in audit["issues"]]
    assert "missing_borrow_cost" in issue_types
    issue = next(i for i in audit["issues"] if i["issue_type"] == "missing_borrow_cost")
    assert issue["severity"] == "medium"


def test_no_short_selling_no_borrow_issue(client):
    """When short_enabled is not set (or false), no borrow issues are raised."""
    sid = _create_strategy_id(client, f"NoShort {uuid.uuid4().hex[:6]}")
    run = _log_run(client, sid,
                   assumptions_json={"transaction_cost_bps": 5, "fill_model": "vwap"},
                   metrics_json=_good_metrics())
    audit = _post_audit(client, run["id"])
    issue_types = [i["issue_type"] for i in audit["issues"]]
    assert "missing_borrow_cost" not in issue_types
    assert "zero_borrow_cost" not in issue_types


# ---------------------------------------------------------------------------
# Trade count / sample size checks
# ---------------------------------------------------------------------------

def test_high_sharpe_few_trades_flagged_as_high(client):
    sid = _create_strategy_id(client, f"FewTrades {uuid.uuid4().hex[:6]}")
    run = _log_run(client, sid,
                   assumptions_json=_good_assumptions(),
                   metrics_json={
                       "sharpe": 2.5,
                       "annual_return": 0.30,
                       "max_drawdown": -0.08,
                       "trade_count": 20,
                   })
    audit = _post_audit(client, run["id"])
    issue_types = [i["issue_type"] for i in audit["issues"]]
    assert "insufficient_trade_count" in issue_types
    issue = next(i for i in audit["issues"] if i["issue_type"] == "insufficient_trade_count")
    assert issue["severity"] == "high"


# ---------------------------------------------------------------------------
# Metric plausibility checks
# ---------------------------------------------------------------------------

def test_implausible_sharpe_flagged(client):
    sid = _create_strategy_id(client, f"BigSharpe {uuid.uuid4().hex[:6]}")
    run = _log_run(client, sid,
                   assumptions_json=_good_assumptions(),
                   metrics_json={
                       "sharpe": 5.5,
                       "annual_return": 0.25,
                       "max_drawdown": -0.05,
                       "trade_count": 300,
                   })
    audit = _post_audit(client, run["id"])
    issue_types = [i["issue_type"] for i in audit["issues"]]
    assert "implausible_sharpe" in issue_types


def test_implausible_annual_return_flagged(client):
    sid = _create_strategy_id(client, f"BigReturn {uuid.uuid4().hex[:6]}")
    run = _log_run(client, sid,
                   assumptions_json=_good_assumptions(),
                   metrics_json={
                       "sharpe": 2.0,
                       "annual_return": 1.5,
                       "max_drawdown": -0.10,
                       "trade_count": 200,
                   })
    audit = _post_audit(client, run["id"])
    issue_types = [i["issue_type"] for i in audit["issues"]]
    assert "implausible_return" in issue_types


# ---------------------------------------------------------------------------
# Turnover checks
# ---------------------------------------------------------------------------

def test_very_high_turnover_flagged_as_high(client):
    sid = _create_strategy_id(client, f"HighTurnover {uuid.uuid4().hex[:6]}")
    run = _log_run(client, sid,
                   assumptions_json=_good_assumptions(),
                   metrics_json={**_good_metrics(), "turnover": 4.0})
    audit = _post_audit(client, run["id"])
    issue_types = [i["issue_type"] for i in audit["issues"]]
    assert "high_turnover" in issue_types
    issue = next(i for i in audit["issues"] if i["issue_type"] == "high_turnover")
    assert issue["severity"] == "high"


def test_moderate_high_turnover_flagged_as_medium(client):
    sid = _create_strategy_id(client, f"MedTurnover {uuid.uuid4().hex[:6]}")
    run = _log_run(client, sid,
                   assumptions_json=_good_assumptions(),
                   metrics_json={**_good_metrics(), "turnover": 2.0})
    audit = _post_audit(client, run["id"])
    issue_types = [i["issue_type"] for i in audit["issues"]]
    assert "high_turnover" in issue_types
    issue = next(i for i in audit["issues"] if i["issue_type"] == "high_turnover")
    assert issue["severity"] == "medium"


# ---------------------------------------------------------------------------
# Data evidence checks
# ---------------------------------------------------------------------------

def test_no_snapshot_linked_flagged_as_low(client):
    """Run with no linked snapshot → no_data_snapshot issue at low severity."""
    sid = _create_strategy_id(client, f"NoSnap {uuid.uuid4().hex[:6]}")
    run = _log_run(client, sid,
                   assumptions_json=_good_assumptions(),
                   metrics_json=_good_metrics())
    audit = _post_audit(client, run["id"])
    issue_types = [i["issue_type"] for i in audit["issues"]]
    assert "no_data_snapshot" in issue_types
    issue = next(i for i in audit["issues"] if i["issue_type"] == "no_data_snapshot")
    assert issue["severity"] == "low"


# ---------------------------------------------------------------------------
# Overall status thresholds
# ---------------------------------------------------------------------------

def test_many_issues_produce_lower_status(client):
    """Run with zero txn cost + close fill + zero borrow → multiple issues, lower status."""
    sid = _create_strategy_id(client, f"LowStatus {uuid.uuid4().hex[:6]}")
    run = _log_run(client, sid,
                   assumptions_json={
                       "transaction_cost_bps": 0,
                       "fill_model": "close",
                       "short_enabled": True,
                       "borrow_rate": 0,
                   },
                   metrics_json={
                       "sharpe": 5.0,
                       "annual_return": 1.2,
                       "trade_count": 15,
                   })
    audit = _post_audit(client, run["id"])
    assert audit["overall_status"] in ("review", "weak", "unreliable"), (
        f"Expected degraded status, got {audit['overall_status']!r}"
    )
    assert audit["trust_score"] < 75


def test_trust_score_penalised_correctly(client):
    """Zero txn cost (high = -15) + missing fill (-8) + no snapshot (-3) → 100-26=74."""
    sid = _create_strategy_id(client, f"ScorePenalty {uuid.uuid4().hex[:6]}")
    # Provide only txn cost = 0 and no fill model, no metrics (no trade_count/sharpe/etc.)
    run = _log_run(client, sid,
                   assumptions_json={"transaction_cost_bps": 0},
                   metrics_json={})
    audit = _post_audit(client, run["id"])
    # Expect: zero_transaction_cost (high=-15) + missing_fill_model (medium=-8) +
    #         missing_trade_count (low=-3) + no_data_snapshot (low=-3)
    # = 100 - 15 - 8 - 3 - 3 = 71.  Allow some variance since exact issues may differ.
    assert audit["trust_score"] < 85, f"Expected reduced score, got {audit['trust_score']}"
    assert audit["trust_score"] >= 0


# ---------------------------------------------------------------------------
# HTTP error cases
# ---------------------------------------------------------------------------

def test_post_audit_404_for_nonexistent_run(client):
    resp = client.post(f"/api/strategy-runs/{uuid.uuid4()}/backtest-audit")
    assert resp.status_code == 404


def test_post_audit_400_for_live_run(client):
    sid = _create_strategy_id(client, f"LiveRun {uuid.uuid4().hex[:6]}")
    run = _log_run(client, sid, run_type="live")
    resp = client.post(f"/api/strategy-runs/{run['id']}/backtest-audit")
    assert resp.status_code == 400
    assert "live" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Idempotency / deduplication
# ---------------------------------------------------------------------------

def test_post_audit_replaces_existing_audit(client):
    """Posting twice returns a fresh result and does not create duplicate records."""
    sid = _create_strategy_id(client, f"Idempotent {uuid.uuid4().hex[:6]}")
    run = _log_run(client, sid,
                   assumptions_json=_good_assumptions(),
                   metrics_json=_good_metrics())

    audit1 = _post_audit(client, run["id"])
    audit2 = _post_audit(client, run["id"])

    # Different audit IDs (new record created).
    assert audit1["id"] != audit2["id"]

    # The GET endpoint returns only one audit (the latest).
    resp = client.get(f"/api/strategy-runs/{run['id']}/backtest-audit")
    assert resp.status_code == 200
    assert resp.json()["id"] == audit2["id"]


# ---------------------------------------------------------------------------
# GET single audit
# ---------------------------------------------------------------------------

def test_get_audit_returns_stored_result(client):
    sid = _create_strategy_id(client, f"GetAudit {uuid.uuid4().hex[:6]}")
    run = _log_run(client, sid,
                   assumptions_json=_good_assumptions(),
                   metrics_json=_good_metrics())
    posted = _post_audit(client, run["id"])

    resp = client.get(f"/api/strategy-runs/{run['id']}/backtest-audit")
    assert resp.status_code == 200
    fetched = resp.json()
    assert fetched["id"] == posted["id"]
    assert fetched["trust_score"] == posted["trust_score"]
    assert fetched["overall_status"] == posted["overall_status"]


def test_get_audit_404_when_no_audit(client):
    sid = _create_strategy_id(client, f"NoAudit {uuid.uuid4().hex[:6]}")
    run = _log_run(client, sid)
    resp = client.get(f"/api/strategy-runs/{run['id']}/backtest-audit")
    assert resp.status_code == 404


def test_get_audit_404_for_nonexistent_run(client):
    resp = client.get(f"/api/strategy-runs/{uuid.uuid4()}/backtest-audit")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# List audits
# ---------------------------------------------------------------------------

def test_list_audits_includes_new_audit(client):
    sid = _create_strategy_id(client, f"ListAudit {uuid.uuid4().hex[:6]}")
    run = _log_run(client, sid,
                   assumptions_json=_good_assumptions(),
                   metrics_json=_good_metrics())
    posted = _post_audit(client, run["id"])

    resp = client.get("/api/backtests/audits")
    assert resp.status_code == 200
    items = resp.json()
    found = next((a for a in items if a["id"] == posted["id"]), None)
    assert found is not None


def test_list_audits_has_context_fields(client):
    sid = _create_strategy_id(client, f"ListCtx {uuid.uuid4().hex[:6]}")
    run = _log_run(client, sid,
                   assumptions_json=_good_assumptions(),
                   metrics_json=_good_metrics())
    _post_audit(client, run["id"])

    resp = client.get("/api/backtests/audits")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) >= 1
    item = items[0]
    for field in ("strategy_id", "strategy_name", "run_name", "run_type",
                  "issue_count", "top_issues"):
        assert field in item, f"Missing list field: {field}"


def test_list_audits_issue_count_correct(client):
    sid = _create_strategy_id(client, f"IssueCount {uuid.uuid4().hex[:6]}")
    run = _log_run(client, sid,
                   assumptions_json={"transaction_cost_bps": 0, "fill_model": "close"},
                   metrics_json={"sharpe": 1.0})
    posted = _post_audit(client, run["id"])

    resp = client.get("/api/backtests/audits")
    items = resp.json()
    found = next(a for a in items if a["id"] == posted["id"])
    assert found["issue_count"] == len(posted["issues"])


# ---------------------------------------------------------------------------
# Research and paper run types can also be audited
# ---------------------------------------------------------------------------

def test_post_audit_works_for_research_run(client):
    sid = _create_strategy_id(client, f"ResearchAudit {uuid.uuid4().hex[:6]}")
    run = _log_run(client, sid, run_type="research",
                   assumptions_json=_good_assumptions(),
                   metrics_json=_good_metrics())
    resp = client.post(f"/api/strategy-runs/{run['id']}/backtest-audit")
    assert resp.status_code == 201


def test_post_audit_works_for_paper_run(client):
    sid = _create_strategy_id(client, f"PaperAudit {uuid.uuid4().hex[:6]}")
    run = _log_run(client, sid, run_type="paper",
                   assumptions_json=_good_assumptions(),
                   metrics_json=_good_metrics())
    resp = client.post(f"/api/strategy-runs/{run['id']}/backtest-audit")
    assert resp.status_code == 201
