"""Assumption Health service — M41.

Computes a deterministic, evidence-based scorecard for each assumption category
(transaction costs, slippage, fill realism, borrow/shorting, liquidity/capacity,
risk controls, data evidence linkage).

No AI, no live market data, no AuditTimelineEvent created.
Language is hedged: "may affect", "requires review" — no investment advice.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FILL_MODEL_RISK: dict[str, str] = {
    "close": "high",
    "same_close": "high",
    "same_bar": "high",
    "exact_price": "high",
    "prev_close": "high",
    "open": "medium",
    "mid": "medium",
    "vwap": "medium",
    "twap": "medium",
    "next_bar_open": "low",
    "next_close": "low",
    "conservative": "low",
    "mid_plus_5bps": "low",
    "slippage_adjusted": "low",
}

CATEGORY_WEIGHTS: dict[str, float] = {
    "transaction_costs": 0.20,
    "slippage": 0.15,
    "fill_realism": 0.20,
    "borrow_shorting": 0.10,
    "liquidity_capacity": 0.15,
    "risk_controls": 0.10,
    "data_evidence_linkage": 0.10,
}


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _get_assumption(d: dict, *keys: str) -> Any:
    """Extract value from dict using multiple possible keys."""
    for key in keys:
        if d.get(key) is not None:
            return d[key]
    return None


def _safe_float(v: Any) -> float | None:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Category scorecard helper
# ---------------------------------------------------------------------------

def _compute_category(
    evidence_sources: list,
    positives: list,
    review_items: list,
    weakening_items: list,
    hi_audit_issues: int = 0,
    med_audit_issues: int = 0,
) -> tuple[int | None, str]:
    """Return (score, status) for one assumption category."""
    if not evidence_sources:
        return None, "missing"
    score = 70
    score += min(len(positives), 3) * 10
    score -= len(weakening_items) * 20
    score -= hi_audit_issues * 20
    score -= med_audit_issues * 10
    score -= len(review_items) * 5
    score = max(0, min(100, score))
    if score >= 85:
        status = "strong"
    elif score >= 70:
        status = "acceptable"
    elif score >= 50:
        status = "review"
    else:
        status = "weak"
    return score, status


# ---------------------------------------------------------------------------
# Evidence gathering
# ---------------------------------------------------------------------------

def _gather_assumption_evidence(strategy_id: uuid.UUID, db: Session) -> dict:
    from app.models.strategy_run import StrategyRun
    from app.models.backtest_audit import BacktestAudit
    from app.models.strategy_config_snapshot import StrategyConfigSnapshot

    # Latest 5 runs
    runs = (
        db.query(StrategyRun)
        .filter(StrategyRun.strategy_id == strategy_id)
        .order_by(StrategyRun.created_at.desc())
        .limit(5)
        .all()
    )

    # Latest backtest audit (from most recent run with an audit)
    latest_audit = None
    for run in runs:
        audit = (
            db.query(BacktestAudit)
            .filter(BacktestAudit.strategy_run_id == run.id)
            .first()
        )
        if audit:
            latest_audit = audit
            break

    # Config snapshots (most recent first)
    config_snaps = (
        db.query(StrategyConfigSnapshot)
        .filter(StrategyConfigSnapshot.strategy_id == strategy_id)
        .order_by(StrategyConfigSnapshot.created_at.desc())
        .limit(10)
        .all()
    )

    # Extract latest assumptions_json from runs
    latest_assumptions: dict = {}
    for run in runs:
        if run.assumptions_json:
            latest_assumptions = run.assumptions_json
            break

    # Extract latest config assumptions and params
    config_assumptions: dict = {}
    config_params: dict = {}
    if config_snaps:
        cfg = config_snaps[0].config_json or {}
        config_assumptions = cfg.get("assumptions") or {}
        config_params = cfg.get("params") or {}

    # Merged assumptions (run assumptions take precedence over config assumptions)
    merged = {**config_assumptions, **latest_assumptions}

    # Runs with dataset evidence
    dataset_linked_count = sum(
        1 for r in runs if r.dataset_snapshot_id is not None
    )

    return {
        "runs": runs,
        "latest_audit": latest_audit,
        "config_snaps": config_snaps,
        "latest_assumptions": latest_assumptions,
        "config_assumptions": config_assumptions,
        "config_params": config_params,
        "merged": merged,
        "dataset_linked_count": dataset_linked_count,
    }


# ---------------------------------------------------------------------------
# Per-category scorecard functions
# ---------------------------------------------------------------------------

def _transaction_cost_category(ev: dict, config_diff: dict | None) -> dict:
    merged = ev["merged"]
    cost = _safe_float(
        _get_assumption(merged, "transaction_cost_bps", "cost_bps", "commission_bps", "tc_bps")
    )
    audit = ev["latest_audit"]
    evidence_sources: list = []
    positives: list = []
    review_items: list = []
    weakening: list = []
    checks: list = []

    if cost is not None:
        evidence_sources.append(f"transaction_cost_bps={cost}")
        if cost > 0:
            positives.append(f"Cost assumption is explicit ({cost:.0f} bps)")
        else:
            review_items.append("Cost assumption is zero — verify intentionality")
    else:
        review_items.append("transaction_cost_bps not found in assumptions or config")
        checks.append("Add explicit transaction_cost_bps to assumptions_json.")

    if audit:
        evidence_sources.append("backtest_audit")
        if audit.cost_sensitivity_sweep_json:
            sw = audit.cost_sensitivity_sweep_json
            fragility = sw.get("most_fragile_scenario")
            if fragility in ("3x_cost", "5x_cost"):
                review_items.append(f"Cost sweep shows fragility at {fragility}")

    if config_diff:
        for chg in (config_diff.get("assumptions_diff") or {}).get("changes", []):
            k = chg.get("key", "").lower()
            if any(c in k for c in ("cost", "commission", "tc_")):
                if chg.get("impact_level") == "weakening":
                    weakening.append(
                        f"{chg['key']}: {chg.get('impact_reason', '')[:60]}"
                    )
                elif chg.get("impact_level") == "positive":
                    positives.append(
                        f"Config change: {chg['key']} {chg.get('impact_reason', '')[:40]}"
                    )

    score, status = _compute_category(evidence_sources, positives, review_items, weakening)
    return {
        "category_key": "transaction_costs",
        "title": "Transaction Costs",
        "score": score,
        "status": status,
        "evidence_count": len(evidence_sources),
        "positive_evidence": positives,
        "review_items": review_items,
        "weakening_changes": weakening,
        "suggested_checks": checks,
    }


def _slippage_category(ev: dict, config_diff: dict | None) -> dict:
    merged = ev["merged"]
    slippage = _safe_float(_get_assumption(merged, "slippage_bps", "market_impact_bps"))
    evidence_sources: list = []
    positives: list = []
    review_items: list = []
    weakening: list = []
    checks: list = []

    if slippage is not None:
        evidence_sources.append(f"slippage_bps={slippage}")
        if slippage > 0:
            positives.append(f"Slippage assumption explicit ({slippage:.0f} bps)")
        else:
            review_items.append("Slippage is zero — verify intentionality")
    else:
        review_items.append("slippage_bps not found in assumptions or config")
        checks.append("Add slippage_bps to assumptions_json for realistic fill modeling.")

    if config_diff:
        for chg in (config_diff.get("assumptions_diff") or {}).get("changes", []):
            k = chg.get("key", "").lower()
            if "slippage" in k or "market_impact" in k:
                if chg.get("impact_level") == "weakening":
                    weakening.append(f"{chg['key']}: {chg.get('impact_reason', '')[:60]}")
                elif chg.get("impact_level") == "positive":
                    positives.append(f"Config: {chg['key']}")

    score, status = _compute_category(evidence_sources, positives, review_items, weakening)
    return {
        "category_key": "slippage",
        "title": "Slippage",
        "score": score,
        "status": status,
        "evidence_count": len(evidence_sources),
        "positive_evidence": positives,
        "review_items": review_items,
        "weakening_changes": weakening,
        "suggested_checks": checks,
    }


def _fill_realism_category(ev: dict, config_diff: dict | None) -> dict:
    merged = ev["merged"]
    fill_model = _get_assumption(merged, "fill_model", "fill_strategy", "execution_fill")
    audit = ev["latest_audit"]
    evidence_sources: list = []
    positives: list = []
    review_items: list = []
    weakening: list = []
    checks: list = []

    if fill_model:
        evidence_sources.append(f"fill_model={fill_model}")
        risk_lvl = FILL_MODEL_RISK.get(str(fill_model).lower(), "unknown")
        if risk_lvl == "low":
            positives.append(f"Fill model {fill_model!r} is conservative")
        elif risk_lvl == "high":
            weakening.append(f"Fill model {fill_model!r} may overstate performance")
            checks.append(
                f"Replace {fill_model} fill with next_bar_open or slippage_adjusted."
            )
        else:
            review_items.append(f"Fill model {fill_model!r} is moderately conservative")
    else:
        review_items.append("fill_model not found — assumes idealized fills")
        checks.append("Add fill_model to assumptions_json.")

    if audit:
        evidence_sources.append("backtest_audit")
        if audit.fill_realism_json:
            level = audit.fill_realism_json.get("fill_realism_level") or audit.fill_realism_json.get("level")
            if level in ("high_concern",):
                weakening.append("Backtest audit: fill realism high concern")
        if audit.fill_sensitivity_json:
            fr_level = audit.fill_sensitivity_json.get("fill_realism_level", "")
            if fr_level == "high_concern":
                review_items.append(f"Fill sensitivity: {fr_level}")

    if config_diff:
        for chg in (config_diff.get("assumptions_diff") or {}).get("changes", []):
            k = chg.get("key", "").lower()
            if "fill" in k or "execution" in k:
                if chg.get("impact_level") == "weakening":
                    weakening.append(f"{chg['key']}: {chg.get('impact_reason', '')[:60]}")
                elif chg.get("impact_level") == "positive":
                    positives.append(f"Config: {chg['key']}")

    score, status = _compute_category(evidence_sources, positives, review_items, weakening)
    return {
        "category_key": "fill_realism",
        "title": "Fill Realism",
        "score": score,
        "status": status,
        "evidence_count": len(evidence_sources),
        "positive_evidence": positives,
        "review_items": review_items,
        "weakening_changes": weakening,
        "suggested_checks": checks,
    }


def _borrow_shorting_category(ev: dict, config_diff: dict | None) -> dict:
    merged = ev["merged"]
    short_enabled = merged.get("short_enabled") or merged.get("allow_short")
    borrow_cost = _safe_float(
        _get_assumption(merged, "borrow_cost_bps", "borrow_rate_bps")
    )
    evidence_sources: list = []
    positives: list = []
    review_items: list = []
    weakening: list = []
    checks: list = []

    if short_enabled is True:
        evidence_sources.append("short_enabled=True")
        if borrow_cost is not None and borrow_cost > 0:
            positives.append(f"Borrow cost explicit ({borrow_cost:.0f} bps) when shorting")
        else:
            review_items.append("short_enabled=True but no borrow_cost_bps set")
            checks.append("Add borrow_cost_bps when short_enabled=True.")
    elif short_enabled is False:
        evidence_sources.append("short_enabled=False (long-only)")
        positives.append("Long-only strategy — borrow cost not required")
    else:
        review_items.append("short_enabled not specified — unclear if shorting occurs")
        checks.append("Add short_enabled=True or False to assumptions_json.")

    if config_diff:
        for chg in (config_diff.get("assumptions_diff") or {}).get("changes", []):
            k = chg.get("key", "").lower()
            if "borrow" in k or "short" in k:
                if chg.get("impact_level") == "weakening":
                    weakening.append(f"{chg['key']}: {chg.get('impact_reason', '')[:60]}")
                elif chg.get("impact_level") == "positive":
                    positives.append(f"Config: {chg['key']}")

    score, status = _compute_category(evidence_sources, positives, review_items, weakening)
    return {
        "category_key": "borrow_shorting",
        "title": "Borrow / Shorting",
        "score": score,
        "status": status,
        "evidence_count": len(evidence_sources),
        "positive_evidence": positives,
        "review_items": review_items,
        "weakening_changes": weakening,
        "suggested_checks": checks,
    }


def _liquidity_category(ev: dict, config_diff: dict | None) -> dict:
    merged = ev["merged"]
    runs = ev["runs"]
    liq_filter = _get_assumption(
        merged, "liquidity_filter", "adv_filter", "min_adv_usd", "volume_filter"
    )
    turnover: float | None = None
    for r in runs:
        t = (r.metrics_json or {}).get("turnover") or (r.metrics_json or {}).get("annual_turnover")
        if t is not None:
            turnover = _safe_float(t)
            break

    evidence_sources: list = []
    positives: list = []
    review_items: list = []
    weakening: list = []
    checks: list = []

    if liq_filter is not None:
        evidence_sources.append("liquidity_filter set")
        positives.append("Liquidity filter is explicit")
    else:
        review_items.append("No liquidity filter — verify universe is tradable")
        checks.append("Add liquidity_filter or adv_filter to assumptions_json.")

    if turnover is not None:
        evidence_sources.append(f"turnover={turnover:.2f}")
        if turnover > 2.0:
            review_items.append(
                f"High turnover ({turnover:.1f}x) — verify liquidity assumptions"
            )
        else:
            positives.append(f"Turnover ({turnover:.1f}x) is within reasonable range")

    if config_diff:
        for chg in (config_diff.get("assumptions_diff") or {}).get("changes", []):
            k = chg.get("key", "").lower()
            if any(c in k for c in ("liquidity", "adv", "volume", "capacity")):
                if chg.get("impact_level") == "weakening":
                    weakening.append(f"{chg['key']}: {chg.get('impact_reason', '')[:60]}")
                elif chg.get("impact_level") == "positive":
                    positives.append(f"Config: {chg['key']}")

    score, status = _compute_category(evidence_sources, positives, review_items, weakening)
    return {
        "category_key": "liquidity_capacity",
        "title": "Liquidity / Capacity",
        "score": score,
        "status": status,
        "evidence_count": len(evidence_sources),
        "positive_evidence": positives,
        "review_items": review_items,
        "weakening_changes": weakening,
        "suggested_checks": checks,
    }


def _risk_controls_category(ev: dict, config_diff: dict | None) -> dict:
    merged = ev["merged"]
    config_params = ev["config_params"]
    combined = {**config_params, **merged}
    risk_keys = {
        "max_position_weight",
        "max_leverage",
        "stop_loss",
        "position_limit",
        "max_sector_weight",
        "trailing_stop",
    }
    found_limits = {
        k: combined[k]
        for k in risk_keys
        if k in combined and combined[k] is not None
    }
    evidence_sources: list = []
    positives: list = []
    review_items: list = []
    weakening: list = []
    checks: list = []

    if found_limits:
        evidence_sources.append(f"{len(found_limits)} risk limit(s) found")
        for k, v in list(found_limits.items())[:3]:
            positives.append(f"{k}={v}")
    else:
        review_items.append(
            "No explicit risk limits (max_position_weight, max_leverage, etc.)"
        )
        checks.append(
            "Consider adding max_position_weight and max_leverage to assumptions/params."
        )

    if config_diff:
        all_chgs = (config_diff.get("params_diff") or {}).get("changes", []) + (
            config_diff.get("assumptions_diff") or {}
        ).get("changes", [])
        for chg in all_chgs:
            k = chg.get("key", "").lower()
            if any(c in k for c in ("leverage", "position", "stop", "risk")):
                if chg.get("impact_level") == "weakening":
                    weakening.append(f"{chg['key']}: {chg.get('impact_reason', '')[:60]}")
                elif chg.get("impact_level") == "positive":
                    positives.append(f"Config: {chg['key']}")

    score, status = _compute_category(evidence_sources, positives, review_items, weakening)
    return {
        "category_key": "risk_controls",
        "title": "Risk Controls",
        "score": score,
        "status": status,
        "evidence_count": len(evidence_sources),
        "positive_evidence": positives,
        "review_items": review_items,
        "weakening_changes": weakening,
        "suggested_checks": checks,
    }


def _data_linkage_category(ev: dict) -> dict:
    runs = ev["runs"]
    dataset_linked = ev["dataset_linked_count"]
    total_runs = len(runs)
    evidence_sources: list = []
    positives: list = []
    review_items: list = []
    checks: list = []

    if total_runs == 0:
        review_items.append("No strategy runs logged")
        checks.append(
            "Log at least one strategy run to assess data evidence linkage."
        )
    elif dataset_linked > 0:
        evidence_sources.append(
            f"{dataset_linked}/{total_runs} runs linked to dataset snapshots"
        )
        rate = dataset_linked / total_runs
        if rate >= 0.8:
            positives.append(
                f"{dataset_linked}/{total_runs} runs have linked dataset evidence"
            )
        else:
            review_items.append(
                f"Only {dataset_linked}/{total_runs} runs linked to dataset evidence"
            )
            checks.append(
                "Link dataset snapshots to strategy runs for data quality verification."
            )
    else:
        evidence_sources.append(f"{total_runs} run(s) with no dataset snapshot")
        review_items.append("No runs linked to dataset snapshots")
        checks.append("Link dataset snapshots to strategy runs.")

    score, status = _compute_category(evidence_sources, positives, review_items, [])
    return {
        "category_key": "data_evidence_linkage",
        "title": "Data Evidence Linkage",
        "score": score,
        "status": status,
        "evidence_count": len(evidence_sources),
        "positive_evidence": positives,
        "review_items": review_items,
        "weakening_changes": [],
        "suggested_checks": checks,
    }


# ---------------------------------------------------------------------------
# Main public function
# ---------------------------------------------------------------------------

def compute_assumption_health(strategy_id: uuid.UUID, db: Session) -> dict:
    """Return a deterministic assumption health dict for the given strategy.

    Raises ValueError if the strategy does not exist.
    No timeline event is created — this is a read-only computation.
    """
    from app.models.strategy import Strategy

    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if strategy is None:
        raise ValueError(f"Strategy {strategy_id} not found")

    now = datetime.now(timezone.utc)
    ev = _gather_assumption_evidence(strategy_id, db)

    # Config diff (requires at least 2 snapshots)
    config_diff: dict | None = None
    config_diff_summary: dict
    config_snaps = ev["config_snaps"]
    if len(config_snaps) >= 2:
        from app.services.config_snapshots import compare_config_snapshots_enriched

        diff_result = compare_config_snapshots_enriched(config_snaps[0], config_snaps[1])
        config_diff = diff_result
        config_diff_summary = {
            "snapshot_a_label": config_snaps[1].label,
            "snapshot_b_label": config_snaps[0].label,
            "total_changes": diff_result.get("total_changes", 0),
            "positive_change_count": len(diff_result.get("positive_changes", [])),
            "weakening_change_count": len(diff_result.get("weakening_changes", [])),
            "review_change_count": len(diff_result.get("review_changes", [])),
            "key_assumption_changes": diff_result.get("all_changes", [])[:10],
        }
    else:
        config_diff_summary = {
            "warning": (
                "At least two config snapshots are needed to assess assumption changes."
            )
        }

    # Backtest audit summary
    audit = ev["latest_audit"]
    audit_summary: dict | None = None
    if audit:
        audit_summary = {
            "backtest_audit_id": str(audit.id),
            "trust_score": audit.trust_score,
            "overall_status": audit.overall_status,
            "cost_fragility_level": (
                audit.cost_sensitivity_sweep_json or {}
            ).get("most_fragile_scenario"),
            "fill_realism_level": (
                audit.fill_sensitivity_json or {}
            ).get("fill_realism_level"),
            "largest_penalty_category": (
                audit.penalty_attribution_json or {}
            ).get("largest_penalty_category"),
            "top_improvement_checks": (audit.improvement_checks_json or [])[:5],
        }

    # Category scorecards
    cats = [
        _transaction_cost_category(ev, config_diff),
        _slippage_category(ev, config_diff),
        _fill_realism_category(ev, config_diff),
        _borrow_shorting_category(ev, config_diff),
        _liquidity_category(ev, config_diff),
        _risk_controls_category(ev, config_diff),
        _data_linkage_category(ev),
    ]

    # Overall weighted score (need at least 3 scored categories)
    scored = [
        (c, CATEGORY_WEIGHTS[c["category_key"]])
        for c in cats
        if c["score"] is not None
    ]
    if len(scored) < 3:
        overall_score: float | None = None
        overall_status = "missing_evidence"
    else:
        total_w = sum(w for _, w in scored)
        overall_score = round(
            sum(c["score"] * w for c, w in scored) / total_w, 1
        )
        if overall_score >= 85:
            overall_status = "strong"
        elif overall_score >= 70:
            overall_status = "acceptable"
        elif overall_score >= 50:
            overall_status = "review"
        else:
            overall_status = "weak"

    # Aggregate suggested checks (deduplicated)
    all_checks: list[str] = []
    for c in cats:
        for chk in c.get("suggested_checks", []):
            all_checks.append(chk)
    if audit_summary and audit_summary.get("top_improvement_checks"):
        for chk in audit_summary["top_improvement_checks"]:
            title = chk.get("title") if isinstance(chk, dict) else str(chk)
            if title:
                all_checks.append(title)
    checks_deduped = list(dict.fromkeys(all_checks))[:10]

    # Deterministic summary text (no investment advice, no AI language)
    weak_cats = [c["title"] for c in cats if c["status"] == "weak"]
    review_cats = [c["title"] for c in cats if c["status"] == "review"]
    if overall_status == "missing_evidence":
        summary = (
            f"Insufficient evidence to assess assumption health for {strategy.name}."
        )
    else:
        parts = [
            f"Assumption health for {strategy.name} is {overall_status}"
            f" (score: {overall_score:.0f}/100)."
        ]
        if weak_cats:
            parts.append(f"Weak areas: {', '.join(weak_cats)}.")
        if review_cats:
            parts.append(f"Review areas: {', '.join(review_cats)}.")
        if (
            isinstance(config_diff_summary, dict)
            and config_diff_summary.get("weakening_change_count", 0) > 0
        ):
            parts.append(
                f"Latest config has"
                f" {config_diff_summary['weakening_change_count']}"
                f" weakening assumption change(s)."
            )
        parts.append(
            "This is a deterministic evidence summary, not a trading recommendation."
        )
        summary = " ".join(parts)

    return {
        "strategy_id": str(strategy_id),
        "strategy_name": strategy.name,
        "generated_at": now,
        "overall_assumption_score": overall_score,
        "status": overall_status,
        "category_scorecards": cats,
        "latest_config_diff_summary": config_diff_summary,
        "latest_backtest_audit_summary": audit_summary,
        "key_assumption_changes": (
            config_diff_summary.get("key_assumption_changes", [])
            if isinstance(config_diff_summary, dict)
            else []
        ),
        "weakening_change_count": (
            config_diff_summary.get("weakening_change_count", 0)
            if isinstance(config_diff_summary, dict)
            else 0
        ),
        "positive_change_count": (
            config_diff_summary.get("positive_change_count", 0)
            if isinstance(config_diff_summary, dict)
            else 0
        ),
        "review_change_count": (
            config_diff_summary.get("review_change_count", 0)
            if isinstance(config_diff_summary, dict)
            else 0
        ),
        "suggested_checks": checks_deduped,
        "deterministic_summary": summary,
    }
