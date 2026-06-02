"""Strategy Regression Tests service (M53).

Deterministic — no AI, no live market data, no external calls.
Creates an AuditTimelineEvent when a test run is executed.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.regression import (
    StrategyRegressionTest,
    StrategyRegressionTestRun,
    StrategyRegressionTestResult,
)
from app.models.strategy_run import StrategyRun
from app.services.strategy_run_history import _load_run_evidence


# ---------------------------------------------------------------------------
# Default test definitions
# ---------------------------------------------------------------------------

DEFAULT_TESTS: list[dict[str, Any]] = [
    # Metric delta tests
    {
        "name": "Sharpe Drop Limit",
        "test_key": "sharpe_drop_limit",
        "test_type": "metric_delta",
        "metric_key": "sharpe",
        "operator": "max_drop_pct",
        "threshold_value": 0.20,
        "threshold_json": None,
        "severity": "high",
        "is_required": True,
        "description": "Sharpe must not drop more than 20%",
    },
    {
        "name": "Sharpe Absolute Drop Limit",
        "test_key": "sharpe_absolute_drop_limit",
        "test_type": "metric_delta",
        "metric_key": "sharpe",
        "operator": "max_absolute_drop",
        "threshold_value": 0.5,
        "threshold_json": None,
        "severity": "high",
        "is_required": True,
        "description": "Sharpe must not drop more than 0.5 absolute",
    },
    {
        "name": "Drawdown Worsening Limit",
        "test_key": "drawdown_worsening_limit",
        "test_type": "metric_delta",
        "metric_key": "max_drawdown",
        "operator": "max_increase_pct",
        "threshold_value": 0.15,
        "threshold_json": None,
        "severity": "high",
        "is_required": True,
        "description": "Max drawdown must not worsen by more than 15%",
    },
    {
        "name": "Turnover Increase Limit",
        "test_key": "turnover_increase_limit",
        "test_type": "metric_delta",
        "metric_key": "turnover",
        "operator": "max_increase_pct",
        "threshold_value": 0.50,
        "threshold_json": None,
        "severity": "medium",
        "is_required": False,
        "description": "Turnover must not increase by more than 50%",
    },
    {
        "name": "Volatility Increase Limit",
        "test_key": "volatility_increase_limit",
        "test_type": "metric_delta",
        "metric_key": "volatility",
        "operator": "max_increase_pct",
        "threshold_value": 0.30,
        "threshold_json": None,
        "severity": "medium",
        "is_required": False,
        "description": "Volatility must not increase by more than 30%",
    },
    # Threshold tests
    {
        "name": "Dataset Health Minimum",
        "test_key": "dataset_health_minimum",
        "test_type": "evidence_score_threshold",
        "metric_key": "dataset_health",
        "operator": "gte",
        "threshold_value": 75.0,
        "threshold_json": None,
        "severity": "high",
        "is_required": True,
        "description": "Latest linked dataset health must be >= 75",
    },
    {
        "name": "Signal Quality Minimum",
        "test_key": "signal_quality_minimum",
        "test_type": "evidence_score_threshold",
        "metric_key": "signal_quality",
        "operator": "gte",
        "threshold_value": 75.0,
        "threshold_json": None,
        "severity": "high",
        "is_required": True,
        "description": "Latest linked signal quality must be >= 75",
    },
    {
        "name": "Backtest Trust Minimum",
        "test_key": "backtest_trust_minimum",
        "test_type": "backtest_trust",
        "metric_key": None,
        "operator": "gte",
        "threshold_value": 70.0,
        "threshold_json": None,
        "severity": "high",
        "is_required": True,
        "description": "Backtest trust score must be >= 70",
    },
    {
        "name": "Evidence Coverage Minimum",
        "test_key": "evidence_coverage_minimum",
        "test_type": "evidence_score_threshold",
        "metric_key": "evidence_coverage",
        "operator": "gte",
        "threshold_value": 70.0,
        "threshold_json": None,
        "severity": "medium",
        "is_required": True,
        "description": "Evidence coverage must be >= 70",
    },
    # State checks
    {
        "name": "No High/Critical Alerts",
        "test_key": "no_high_critical_alerts",
        "test_type": "alert_state",
        "metric_key": None,
        "operator": "status_not_in",
        "threshold_value": None,
        "threshold_json": ["high", "critical"],
        "severity": "high",
        "is_required": True,
        "description": "No high/critical alerts open",
    },
    {
        "name": "Freshness Not Stale",
        "test_key": "freshness_not_stale",
        "test_type": "freshness_status",
        "metric_key": None,
        "operator": "status_not_in",
        "threshold_value": None,
        "threshold_json": ["stale", "missing_evidence"],
        "severity": "medium",
        "is_required": False,
        "description": "Evidence must not be stale",
    },
    {
        "name": "Readiness Not Blocked",
        "test_key": "readiness_not_blocked",
        "test_type": "readiness_verdict",
        "metric_key": None,
        "operator": "status_not_in",
        "threshold_value": None,
        "threshold_json": ["blocked", "under_instrumented"],
        "severity": "high",
        "is_required": True,
        "description": "Readiness must not be blocked",
    },
    {
        "name": "Drift Not Severe",
        "test_key": "drift_not_severe",
        "test_type": "drift_status",
        "metric_key": None,
        "operator": "status_not_in",
        "threshold_value": None,
        "threshold_json": ["severe"],
        "severity": "high",
        "is_required": False,
        "description": "Drift must not be severe",
    },
    {
        "name": "Shadow Monitor Not Severe",
        "test_key": "shadow_not_severe",
        "test_type": "shadow_status",
        "metric_key": None,
        "operator": "status_not_in",
        "threshold_value": None,
        "threshold_json": ["severe"],
        "severity": "medium",
        "is_required": False,
        "description": "Shadow monitor must not be severe",
    },
    {
        "name": "Assumption Health Not Weak",
        "test_key": "assumption_health_not_weak",
        "test_type": "assumption_health",
        "metric_key": None,
        "operator": "status_not_in",
        "threshold_value": None,
        "threshold_json": ["weak"],
        "severity": "high",
        "is_required": True,
        "description": "Assumption health must not be weak",
    },
]


# ---------------------------------------------------------------------------
# Create default tests
# ---------------------------------------------------------------------------

def create_default_regression_tests(
    strategy_id: uuid.UUID,
    db: Session,
) -> list[StrategyRegressionTest]:
    """Create default regression tests for a strategy if they don't exist yet.

    Returns all regression tests for the strategy (existing + newly created).
    """
    now = datetime.now(timezone.utc)

    existing_keys = {
        row.test_key
        for row in db.query(StrategyRegressionTest.test_key)
        .filter(StrategyRegressionTest.strategy_id == strategy_id)
        .all()
    }

    for spec in DEFAULT_TESTS:
        if spec["test_key"] in existing_keys:
            continue
        test = StrategyRegressionTest(
            strategy_id=strategy_id,
            name=spec["name"],
            test_key=spec["test_key"],
            test_type=spec["test_type"],
            metric_key=spec.get("metric_key"),
            operator=spec["operator"],
            threshold_value=spec.get("threshold_value"),
            threshold_json=spec.get("threshold_json"),
            severity=spec["severity"],
            is_required=spec["is_required"],
            is_enabled=True,
            description=spec.get("description"),
            created_at=now,
            updated_at=now,
        )
        db.add(test)
        db.flush()

    return (
        db.query(StrategyRegressionTest)
        .filter(StrategyRegressionTest.strategy_id == strategy_id)
        .all()
    )


# ---------------------------------------------------------------------------
# Run selection
# ---------------------------------------------------------------------------

def _select_runs(
    strategy_id: uuid.UUID,
    mode: str,
    baseline_run_id: uuid.UUID | None,
    comparison_run_id: uuid.UUID | None,
    db: Session,
) -> tuple[StrategyRun | None, StrategyRun | None, str | None]:
    """Select baseline and comparison runs for evaluation.

    Returns (baseline, comparison, error_message|None).
    """
    if mode == "latest_vs_previous":
        runs = (
            db.query(StrategyRun)
            .filter(StrategyRun.strategy_id == strategy_id)
            .order_by(StrategyRun.created_at.desc())
            .limit(2)
            .all()
        )
        if len(runs) < 2:
            return None, None, "Need at least 2 runs for latest_vs_previous comparison"
        # Most recent is comparison, earlier is baseline
        return runs[1], runs[0], None

    elif mode == "selected_runs":
        if baseline_run_id is None or comparison_run_id is None:
            return None, None, "baseline_run_id and comparison_run_id are required for selected_runs mode"
        baseline = db.query(StrategyRun).filter(
            StrategyRun.id == baseline_run_id,
            StrategyRun.strategy_id == strategy_id,
        ).first()
        if baseline is None:
            return None, None, f"Baseline run {baseline_run_id} not found for this strategy"
        comparison = db.query(StrategyRun).filter(
            StrategyRun.id == comparison_run_id,
            StrategyRun.strategy_id == strategy_id,
        ).first()
        if comparison is None:
            return None, None, f"Comparison run {comparison_run_id} not found for this strategy"
        return baseline, comparison, None

    elif mode == "latest_backtest_vs_latest_shadow":
        backtest_run = (
            db.query(StrategyRun)
            .filter(
                StrategyRun.strategy_id == strategy_id,
                StrategyRun.run_type == "backtest",
            )
            .order_by(StrategyRun.created_at.desc())
            .first()
        )
        shadow_run = (
            db.query(StrategyRun)
            .filter(
                StrategyRun.strategy_id == strategy_id,
                StrategyRun.run_type.in_(["paper", "live"]),
            )
            .order_by(StrategyRun.created_at.desc())
            .first()
        )
        if backtest_run is None or shadow_run is None:
            return (
                None,
                None,
                "Need at least one backtest and one paper/live run for this mode",
            )
        return backtest_run, shadow_run, None

    else:
        return None, None, f"Unknown mode: {mode}"


# ---------------------------------------------------------------------------
# Test evaluation
# ---------------------------------------------------------------------------

def _get_metric(metrics_json: dict | None, key: str) -> float | None:
    if not metrics_json:
        return None
    val = metrics_json.get(key)
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _eval_test(
    test: StrategyRegressionTest,
    baseline_item: Any,
    comparison_item: Any,
    db: Session,
    strategy_id: uuid.UUID,
) -> dict:
    """Evaluate a single regression test.

    Returns a result dict with all required fields.
    """
    now = datetime.now(timezone.utc)

    base_result: dict[str, Any] = {
        "test_key": test.test_key,
        "title": test.name,
        "status": "skipped",
        "severity": test.severity,
        "is_required": test.is_required,
        "observed_value": None,
        "expected_value": None,
        "baseline_value": None,
        "comparison_value": None,
        "suggested_action": None,
        "evidence_json": None,
        "regression_test_id": test.id,
        "created_at": now,
    }

    try:
        if test.test_type == "metric_delta":
            if baseline_item is None or comparison_item is None:
                base_result["status"] = "skipped"
                base_result["suggested_action"] = "Insufficient runs for delta comparison"
                return base_result

            base_val = _get_metric(
                baseline_item.metrics_json if baseline_item else None,
                test.metric_key or "",
            )
            comp_val = _get_metric(
                comparison_item.metrics_json if comparison_item else None,
                test.metric_key or "",
            )

            if base_val is None or comp_val is None:
                base_result["status"] = "skipped"
                base_result["suggested_action"] = (
                    f"Metric '{test.metric_key}' not found in run metrics"
                )
                return base_result

            base_result["baseline_value"] = str(round(base_val, 4))
            base_result["comparison_value"] = str(round(comp_val, 4))
            threshold = test.threshold_value or 0.0

            if test.operator == "max_drop_pct":
                if base_val == 0:
                    base_result["status"] = "skipped"
                    return base_result
                change_pct = (comp_val - base_val) / abs(base_val)
                base_result["observed_value"] = f"{change_pct:.4f}"
                base_result["expected_value"] = f">= -{threshold}"
                if change_pct < -threshold:
                    base_result["status"] = "failed"
                    base_result["suggested_action"] = (
                        f"Metric '{test.metric_key}' dropped {abs(change_pct):.1%}, "
                        f"exceeding the {threshold:.0%} limit"
                    )
                else:
                    base_result["status"] = "passed"

            elif test.operator == "max_increase_pct":
                if base_val == 0:
                    base_result["status"] = "skipped"
                    return base_result
                change_pct = (comp_val - base_val) / abs(base_val)
                base_result["observed_value"] = f"{change_pct:.4f}"
                base_result["expected_value"] = f"<= {threshold}"
                if change_pct > threshold:
                    base_result["status"] = "failed"
                    base_result["suggested_action"] = (
                        f"Metric '{test.metric_key}' increased {change_pct:.1%}, "
                        f"exceeding the {threshold:.0%} limit"
                    )
                else:
                    base_result["status"] = "passed"

            elif test.operator == "max_absolute_drop":
                delta = comp_val - base_val
                base_result["observed_value"] = str(round(delta, 4))
                base_result["expected_value"] = f">= -{threshold}"
                if delta < -threshold:
                    base_result["status"] = "failed"
                    base_result["suggested_action"] = (
                        f"Metric '{test.metric_key}' dropped by {abs(delta):.4f}, "
                        f"exceeding the {threshold} absolute limit"
                    )
                else:
                    base_result["status"] = "passed"
            else:
                base_result["status"] = "skipped"

        elif test.test_type == "evidence_score_threshold":
            if comparison_item is None:
                base_result["status"] = "skipped"
                base_result["suggested_action"] = "No comparison run available"
                return base_result

            threshold = test.threshold_value or 0.0
            value: float | None = None

            if test.metric_key == "dataset_health":
                if (
                    comparison_item.dataset_evidence is not None
                    and comparison_item.dataset_evidence.health_score is not None
                ):
                    value = float(comparison_item.dataset_evidence.health_score)
            elif test.metric_key == "signal_quality":
                if (
                    comparison_item.signal_evidence is not None
                    and comparison_item.signal_evidence.quality_score is not None
                ):
                    value = float(comparison_item.signal_evidence.quality_score)
            elif test.metric_key == "evidence_coverage":
                try:
                    from app.services.evidence_coverage import (
                        _compute_row,
                    )
                    from app.models.strategy import Strategy

                    strat = db.query(Strategy).filter(Strategy.id == strategy_id).first()
                    if strat is not None:
                        row = _compute_row(strat, db)
                        value = float(row.coverage_score)
                except Exception:
                    value = None

            if value is None:
                base_result["status"] = "skipped"
                base_result["suggested_action"] = (
                    f"Score for '{test.metric_key}' not available"
                )
                return base_result

            base_result["observed_value"] = str(round(value, 2))
            base_result["expected_value"] = f">= {threshold}"
            if test.operator == "gte":
                base_result["status"] = "passed" if value >= threshold else "failed"
                if value < threshold:
                    base_result["suggested_action"] = (
                        f"{test.metric_key} score {value:.1f} is below threshold {threshold}"
                    )

        elif test.test_type == "backtest_trust":
            if comparison_item is None:
                base_result["status"] = "skipped"
                base_result["suggested_action"] = "No comparison run available"
                return base_result

            threshold = test.threshold_value or 0.0
            value = None
            if (
                comparison_item.backtest_audit is not None
                and comparison_item.backtest_audit.trust_score is not None
            ):
                value = float(comparison_item.backtest_audit.trust_score)

            if value is None:
                base_result["status"] = "skipped"
                base_result["suggested_action"] = "No backtest audit available for comparison run"
                return base_result

            base_result["observed_value"] = str(round(value, 2))
            base_result["expected_value"] = f">= {threshold}"
            if test.operator == "gte":
                base_result["status"] = "passed" if value >= threshold else "failed"
                if value < threshold:
                    base_result["suggested_action"] = (
                        f"Backtest trust score {value:.1f} is below threshold {threshold}"
                    )

        elif test.test_type == "alert_state":
            from app.models.alert import Alert

            threshold_list = test.threshold_json or []
            open_statuses = ["open", "acknowledged", "snoozed"]
            open_alerts = (
                db.query(Alert)
                .filter(
                    Alert.strategy_id == str(strategy_id),
                    Alert.status.in_(open_statuses),
                )
                .all()
            )
            if test.operator == "status_not_in":
                matching = [a for a in open_alerts if a.severity in threshold_list]
                if matching:
                    base_result["status"] = "failed"
                    base_result["observed_value"] = f"{len(matching)} open alert(s)"
                    base_result["expected_value"] = f"No alerts with severity in {threshold_list}"
                    base_result["suggested_action"] = (
                        f"{len(matching)} open alert(s) with severity in {threshold_list} — "
                        "review and resolve before proceeding"
                    )
                else:
                    base_result["status"] = "passed"
                    base_result["observed_value"] = "0 matching open alerts"

        elif test.test_type == "freshness_status":
            try:
                from app.services.evidence_freshness import compute_evidence_freshness

                freshness = compute_evidence_freshness(strategy_id, db)
                status_val = freshness.freshness_status
                threshold_list = test.threshold_json or []
                base_result["observed_value"] = status_val
                base_result["expected_value"] = f"Not in {threshold_list}"
                if test.operator == "status_not_in":
                    if status_val in threshold_list:
                        base_result["status"] = "failed"
                        base_result["suggested_action"] = (
                            f"Evidence freshness is '{status_val}' — refresh evidence"
                        )
                    else:
                        base_result["status"] = "passed"
            except Exception:
                base_result["status"] = "skipped"
                base_result["suggested_action"] = "Could not compute evidence freshness"

        elif test.test_type == "readiness_verdict":
            try:
                from app.services.strategy_readiness import compute_strategy_readiness

                readiness = compute_strategy_readiness(strategy_id, db)
                verdict = readiness.readiness_verdict
                threshold_list = test.threshold_json or []
                base_result["observed_value"] = verdict
                base_result["expected_value"] = f"Not in {threshold_list}"
                if test.operator == "status_not_in":
                    if verdict in threshold_list:
                        base_result["status"] = "failed"
                        base_result["suggested_action"] = (
                            f"Strategy readiness is '{verdict}' — address blockers"
                        )
                    else:
                        base_result["status"] = "passed"
            except Exception:
                base_result["status"] = "skipped"
                base_result["suggested_action"] = "Could not compute strategy readiness"

        elif test.test_type == "drift_status":
            try:
                from app.services.strategy_drift import compute_strategy_drift

                drift = compute_strategy_drift(strategy_id, db)
                status_val = drift.drift_status
                threshold_list = test.threshold_json or []
                base_result["observed_value"] = status_val
                base_result["expected_value"] = f"Not in {threshold_list}"
                if test.operator == "status_not_in":
                    if status_val in threshold_list:
                        base_result["status"] = "failed"
                        base_result["suggested_action"] = (
                            f"Strategy drift is '{status_val}' — investigate metric divergence"
                        )
                    else:
                        base_result["status"] = "passed"
            except Exception:
                base_result["status"] = "skipped"
                base_result["suggested_action"] = "Could not compute strategy drift"

        elif test.test_type == "shadow_status":
            try:
                from app.services.shadow_production import compute_shadow_production_monitor

                monitor = compute_shadow_production_monitor(strategy_id, db)
                status_val = monitor.monitor_status
                threshold_list = test.threshold_json or []
                base_result["observed_value"] = status_val
                base_result["expected_value"] = f"Not in {threshold_list}"
                if test.operator == "status_not_in":
                    if status_val in threshold_list:
                        base_result["status"] = "failed"
                        base_result["suggested_action"] = (
                            f"Shadow monitor status is '{status_val}' — review shadow run deviation"
                        )
                    else:
                        base_result["status"] = "passed"
            except Exception:
                base_result["status"] = "skipped"
                base_result["suggested_action"] = "Could not compute shadow production monitor"

        elif test.test_type == "assumption_health":
            try:
                from app.services.assumption_health import compute_assumption_health

                health = compute_assumption_health(strategy_id, db)
                status_val = health.get("status", "unknown")
                threshold_list = test.threshold_json or []
                base_result["observed_value"] = status_val
                base_result["expected_value"] = f"Not in {threshold_list}"
                if test.operator == "status_not_in":
                    if status_val in threshold_list:
                        base_result["status"] = "failed"
                        base_result["suggested_action"] = (
                            f"Assumption health is '{status_val}' — address weak assumptions"
                        )
                    else:
                        base_result["status"] = "passed"
            except Exception:
                base_result["status"] = "skipped"
                base_result["suggested_action"] = "Could not compute assumption health"

        else:
            base_result["status"] = "skipped"
            base_result["suggested_action"] = f"Unknown test_type: {test.test_type}"

    except Exception as exc:
        base_result["status"] = "skipped"
        base_result["suggested_action"] = f"Evaluation error: {exc}"

    return base_result


# ---------------------------------------------------------------------------
# Run regression tests
# ---------------------------------------------------------------------------

def run_regression_tests(
    strategy_id: uuid.UUID,
    db: Session,
    *,
    mode: str = "latest_vs_previous",
    baseline_run_id: uuid.UUID | None = None,
    comparison_run_id: uuid.UUID | None = None,
    suite_label: str | None = None,
) -> StrategyRegressionTestRun:
    """Execute all enabled regression tests for a strategy and persist the results.

    Returns a StrategyRegressionTestRun with results loaded.
    """
    from app.models.audit_timeline_event import AuditTimelineEvent
    from app.models.strategy import Strategy
    from app.core.constants import EventType, Severity

    now = datetime.now(timezone.utc)

    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if strategy is None:
        raise ValueError(f"Strategy {strategy_id} not found")

    # Get enabled tests
    tests = (
        db.query(StrategyRegressionTest)
        .filter(
            StrategyRegressionTest.strategy_id == strategy_id,
            StrategyRegressionTest.is_enabled.is_(True),
        )
        .all()
    )

    # Select runs
    baseline_run, comparison_run, run_error = _select_runs(
        strategy_id, mode, baseline_run_id, comparison_run_id, db
    )

    if run_error is not None or (baseline_run is None and comparison_run is None):
        # Insufficient evidence
        test_run = StrategyRegressionTestRun(
            strategy_id=strategy_id,
            suite_label=suite_label,
            mode=mode,
            baseline_run_id=baseline_run_id,
            comparison_run_id=comparison_run_id,
            overall_status="insufficient_evidence",
            passed_count=0,
            failed_count=0,
            warning_count=0,
            skipped_count=len(tests),
            required_failed_count=0,
            result_json={"error": run_error},
            deterministic_summary=(
                f"Regression test suite could not run: {run_error}. "
                "Ensure the strategy has sufficient runs before re-running."
            ),
            created_at=now,
            updated_at=now,
        )
        db.add(test_run)
        db.flush()

        # Create results as skipped
        for test in tests:
            result = StrategyRegressionTestResult(
                test_run_id=test_run.id,
                regression_test_id=test.id,
                test_key=test.test_key,
                title=test.name,
                status="skipped",
                severity=test.severity,
                is_required=test.is_required,
                suggested_action=run_error,
                created_at=now,
            )
            db.add(result)
        db.flush()

        # Timeline event
        _create_timeline_event(strategy, test_run, db, now)
        db.commit()
        return test_run

    # Load run evidence
    baseline_item = _load_run_evidence(baseline_run, db) if baseline_run else None
    comparison_item = _load_run_evidence(comparison_run, db) if comparison_run else None

    # Evaluate each test
    result_dicts = []
    for test in tests:
        result_dict = _eval_test(test, baseline_item, comparison_item, db, strategy_id)
        result_dicts.append(result_dict)

    # Tally counts
    passed_count = sum(1 for r in result_dicts if r["status"] == "passed")
    failed_count = sum(1 for r in result_dicts if r["status"] == "failed")
    warning_count = sum(1 for r in result_dicts if r["status"] == "warning")
    skipped_count = sum(1 for r in result_dicts if r["status"] == "skipped")
    required_failed_count = sum(
        1 for r in result_dicts if r["status"] == "failed" and r["is_required"]
    )

    # Determine overall status
    if required_failed_count > 0:
        overall_status = "failed"
    elif failed_count > 0:
        overall_status = "warning"
    elif skipped_count == len(tests):
        overall_status = "insufficient_evidence"
    else:
        overall_status = "passed"

    # Build deterministic summary
    total = len(tests)
    summary_parts = [
        f"Regression suite ({mode}): {passed_count}/{total} passed, "
        f"{failed_count} failed, {skipped_count} skipped.",
    ]
    if required_failed_count > 0:
        summary_parts.append(
            f"{required_failed_count} required test(s) failed — review and address before proceeding."
        )
    elif overall_status == "passed":
        summary_parts.append("All required checks passed.")
    elif overall_status == "warning":
        summary_parts.append("Optional tests have failures — review is recommended.")
    deterministic_summary = " ".join(summary_parts)

    # Create the test run
    actual_baseline_id = baseline_run.id if baseline_run else None
    actual_comparison_id = comparison_run.id if comparison_run else None

    test_run = StrategyRegressionTestRun(
        strategy_id=strategy_id,
        suite_label=suite_label,
        mode=mode,
        baseline_run_id=actual_baseline_id,
        comparison_run_id=actual_comparison_id,
        overall_status=overall_status,
        passed_count=passed_count,
        failed_count=failed_count,
        warning_count=warning_count,
        skipped_count=skipped_count,
        required_failed_count=required_failed_count,
        result_json={
            "mode": mode,
            "total": total,
            "passed": passed_count,
            "failed": failed_count,
            "skipped": skipped_count,
        },
        deterministic_summary=deterministic_summary,
        created_at=now,
        updated_at=now,
    )
    db.add(test_run)
    db.flush()

    # Create test result records
    for result_dict in result_dicts:
        result = StrategyRegressionTestResult(
            test_run_id=test_run.id,
            regression_test_id=result_dict.get("regression_test_id"),
            test_key=result_dict["test_key"],
            title=result_dict["title"],
            status=result_dict["status"],
            severity=result_dict["severity"],
            is_required=result_dict["is_required"],
            observed_value=result_dict.get("observed_value"),
            expected_value=result_dict.get("expected_value"),
            baseline_value=result_dict.get("baseline_value"),
            comparison_value=result_dict.get("comparison_value"),
            evidence_json=result_dict.get("evidence_json"),
            suggested_action=result_dict.get("suggested_action"),
            created_at=result_dict["created_at"],
        )
        db.add(result)
    db.flush()

    # Create audit timeline event
    _create_timeline_event(strategy, test_run, db, now)
    db.commit()

    return test_run


def _create_timeline_event(
    strategy: Any,
    test_run: StrategyRegressionTestRun,
    db: Session,
    now: datetime,
) -> None:
    """Create an AuditTimelineEvent for the regression test run."""
    from app.models.audit_timeline_event import AuditTimelineEvent
    from app.core.constants import EventType, Severity

    event = AuditTimelineEvent(
        organization_id=strategy.project.organization_id,
        project_id=strategy.project_id,
        strategy_id=strategy.id,
        event_type=EventType.regression_tests_run,
        title=(
            f"Regression tests ran: {test_run.overall_status} "
            f"({test_run.passed_count} passed, {test_run.failed_count} failed)"
        ),
        description=test_run.deterministic_summary,
        source_type="strategy_regression_test_run",
        source_id=str(test_run.id),
        severity=(
            Severity.high
            if test_run.overall_status == "failed"
            else (
                Severity.medium
                if test_run.overall_status == "warning"
                else Severity.info
            )
        ),
        metadata_json={
            "mode": test_run.mode,
            "overall_status": test_run.overall_status,
            "passed_count": test_run.passed_count,
            "failed_count": test_run.failed_count,
            "skipped_count": test_run.skipped_count,
            "required_failed_count": test_run.required_failed_count,
        },
    )
    db.add(event)


# ---------------------------------------------------------------------------
# Read helpers
# ---------------------------------------------------------------------------

def get_regression_tests(
    strategy_id: uuid.UUID,
    db: Session,
) -> list[StrategyRegressionTest]:
    """Return all regression tests for a strategy."""
    return (
        db.query(StrategyRegressionTest)
        .filter(StrategyRegressionTest.strategy_id == strategy_id)
        .order_by(StrategyRegressionTest.created_at)
        .all()
    )


def get_regression_test_runs(
    strategy_id: uuid.UUID,
    db: Session,
    limit: int = 20,
    offset: int = 0,
) -> list[StrategyRegressionTestRun]:
    """Return recent regression test runs for a strategy."""
    return (
        db.query(StrategyRegressionTestRun)
        .filter(StrategyRegressionTestRun.strategy_id == strategy_id)
        .order_by(StrategyRegressionTestRun.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


def get_regression_test_run(
    test_run_id: uuid.UUID,
    db: Session,
) -> StrategyRegressionTestRun | None:
    """Return a single regression test run with its results loaded."""
    run = (
        db.query(StrategyRegressionTestRun)
        .filter(StrategyRegressionTestRun.id == test_run_id)
        .first()
    )
    if run is not None:
        # Eagerly load results
        _ = run.results
    return run
