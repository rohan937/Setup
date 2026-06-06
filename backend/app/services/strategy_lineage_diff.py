"""Strategy Lineage Diff service (M95).

Produces version-to-version diffs of strategy evidence: config, universe,
signal, run metrics, trust scores, and blockers.

Language policy:
  Use: "logged", "observed", "noted", "not declared"
  Never: "fraud", "falsified", "better strategy", "should trade"
  Always include disclaimer.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

# ---------------------------------------------------------------------------
# Disclaimer
# ---------------------------------------------------------------------------

DISCLAIMER = (
    "Strategy lineage diff is a deterministic research evidence comparison. "
    "It is not trading advice."
)

# ---------------------------------------------------------------------------
# Verdict ordering (higher index = worse)
# ---------------------------------------------------------------------------

_REALITY_VERDICT_ORDER = ["realistic", "acceptable", "review", "weak", "insufficient_data"]
_VERIFICATION_VERDICT_ORDER = ["verified", "review", "warning", "failed", "insufficient_data"]


def _reality_rank(verdict: str | None) -> int:
    if verdict is None:
        return -1
    try:
        return _REALITY_VERDICT_ORDER.index(verdict)
    except ValueError:
        return -1


def _verification_rank(verdict: str | None) -> int:
    if verdict is None:
        return -1
    try:
        return _VERIFICATION_VERDICT_ORDER.index(verdict)
    except ValueError:
        return -1


# ---------------------------------------------------------------------------
# FUNCTION 1: list_comparable_versions
# ---------------------------------------------------------------------------


def list_comparable_versions(strategy_id: uuid.UUID, db: Session) -> list[dict]:
    """Return all strategy versions ordered by created_at ascending.

    Each entry: {version_id, version_label, created_at, git_commit}.
    Returns empty list if no versions found.
    """
    try:
        from app.models.strategy_version import StrategyVersion

        versions = (
            db.query(StrategyVersion)
            .filter(StrategyVersion.strategy_id == strategy_id)
            .order_by(StrategyVersion.created_at.asc())
            .all()
        )
        result = []
        for v in versions:
            result.append(
                {
                    "version_id": str(v.id),
                    "version_label": v.version_label,
                    "created_at": v.created_at.isoformat() if v.created_at else None,
                    "git_commit": v.git_commit,
                }
            )
        return result
    except Exception:
        return []


# ---------------------------------------------------------------------------
# FUNCTION 2: build_version_evidence_profile
# ---------------------------------------------------------------------------


def build_version_evidence_profile(
    strategy_id: uuid.UUID,
    version_label: str,
    db: Session,
) -> dict:
    """Collect all evidence for one strategy version.

    Returns a dict with all evidence fields. Sets found=False and nulls
    when the version does not exist.
    """
    from app.models.strategy_version import StrategyVersion

    version = (
        db.query(StrategyVersion)
        .filter(
            StrategyVersion.strategy_id == strategy_id,
            StrategyVersion.version_label == version_label,
        )
        .first()
    )

    if version is None:
        return {
            "version_label": version_label,
            "found": False,
            "version_id": None,
            "git_commit": None,
            "branch_name": None,
            "code_path": None,
            "signal_name": None,
            "created_at": None,
            # Config
            "config_label": None,
            "config_hash": None,
            "config_params": None,
            "config_assumptions": None,
            "transaction_cost_bps": None,
            "slippage_bps": None,
            "fill_model": None,
            "short_enabled": None,
            "leverage_limit": None,
            # Universe
            "universe_label": None,
            "universe_hash": None,
            "universe_symbol_count": None,
            "universe_symbols": None,
            # Signal
            "signal_label": None,
            "signal_hash": None,
            "signal_row_count": None,
            "signal_symbols": None,
            "signal_metadata": None,
            # Run
            "run_name": None,
            "run_id": None,
            "metrics_json": None,
            "dataset_row_count": None,
            # Audit
            "trust_score": None,
            "overall_status": None,
            # Reality check
            "backtest_reality_score": None,
            "reality_verdict": None,
            # Evidence verification
            "verification_score": None,
            "verification_verdict": None,
            "chain_status": None,
            # Reliability
            "reliability_score": None,
            "reliability_status": None,
        }

    profile: dict[str, Any] = {
        "version_label": version.version_label,
        "found": True,
    }

    # --- a) Version metadata ---
    try:
        profile["version_id"] = str(version.id)
        profile["git_commit"] = version.git_commit
        profile["branch_name"] = version.branch_name
        profile["code_path"] = version.code_path
        profile["signal_name"] = version.signal_name
        profile["created_at"] = (
            version.created_at.isoformat() if version.created_at else None
        )
    except Exception:
        profile.setdefault("version_id", None)
        profile.setdefault("git_commit", None)
        profile.setdefault("branch_name", None)
        profile.setdefault("code_path", None)
        profile.setdefault("signal_name", None)
        profile.setdefault("created_at", None)

    # --- b) Config snapshot ---
    try:
        from app.models.strategy_config_snapshot import StrategyConfigSnapshot

        cfg = (
            db.query(StrategyConfigSnapshot)
            .filter(StrategyConfigSnapshot.strategy_version_id == version.id)
            .order_by(StrategyConfigSnapshot.created_at.desc())
            .first()
        )
        if cfg:
            profile["config_label"] = cfg.label
            profile["config_hash"] = cfg.config_hash
            raw_cfg = cfg.config_json or {}
            profile["config_params"] = raw_cfg.get("params", {}) if isinstance(raw_cfg, dict) else {}
            profile["config_assumptions"] = raw_cfg.get("assumptions", {}) if isinstance(raw_cfg, dict) else {}
            assumptions = profile["config_assumptions"]
            profile["transaction_cost_bps"] = assumptions.get("transaction_cost_bps")
            profile["slippage_bps"] = assumptions.get("slippage_bps")
            profile["fill_model"] = assumptions.get("fill_model")
            profile["short_enabled"] = assumptions.get("short_enabled")
            profile["leverage_limit"] = assumptions.get("leverage_limit")
        else:
            profile["config_label"] = None
            profile["config_hash"] = None
            profile["config_params"] = None
            profile["config_assumptions"] = None
            profile["transaction_cost_bps"] = None
            profile["slippage_bps"] = None
            profile["fill_model"] = None
            profile["short_enabled"] = None
            profile["leverage_limit"] = None
    except Exception:
        for k in ["config_label", "config_hash", "config_params", "config_assumptions",
                  "transaction_cost_bps", "slippage_bps", "fill_model", "short_enabled",
                  "leverage_limit"]:
            profile.setdefault(k, None)

    # --- c) Universe snapshot ---
    try:
        from app.models.universe_snapshot import UniverseSnapshot

        uni = (
            db.query(UniverseSnapshot)
            .filter(UniverseSnapshot.strategy_version_id == version.id)
            .order_by(UniverseSnapshot.created_at.desc())
            .first()
        )
        if uni:
            profile["universe_label"] = uni.label
            profile["universe_hash"] = uni.universe_hash
            profile["universe_symbol_count"] = uni.symbol_count
            profile["universe_symbols"] = uni.symbols_json or []
        else:
            profile["universe_label"] = None
            profile["universe_hash"] = None
            profile["universe_symbol_count"] = None
            profile["universe_symbols"] = None
    except Exception:
        for k in ["universe_label", "universe_hash", "universe_symbol_count", "universe_symbols"]:
            profile.setdefault(k, None)

    # --- d) Signal snapshot ---
    try:
        from app.models.signal_snapshot import SignalSnapshot

        sig = (
            db.query(SignalSnapshot)
            .filter(SignalSnapshot.strategy_version_id == version.id)
            .order_by(SignalSnapshot.created_at.desc())
            .first()
        )
        if sig:
            profile["signal_label"] = sig.label
            profile["signal_hash"] = sig.signal_hash
            profile["signal_row_count"] = sig.row_count
            profile["signal_symbols"] = sig.symbols_json or []
            profile["signal_metadata"] = sig.metadata_json
        else:
            profile["signal_label"] = None
            profile["signal_hash"] = None
            profile["signal_row_count"] = None
            profile["signal_symbols"] = None
            profile["signal_metadata"] = None
    except Exception:
        for k in ["signal_label", "signal_hash", "signal_row_count", "signal_symbols", "signal_metadata"]:
            profile.setdefault(k, None)

    # --- e) Latest backtest run ---
    run = None
    try:
        from app.models.strategy_run import StrategyRun

        run = (
            db.query(StrategyRun)
            .filter(
                StrategyRun.strategy_version_id == version.id,
                StrategyRun.run_type == "backtest",
            )
            .order_by(StrategyRun.created_at.desc())
            .first()
        )
        if run:
            profile["run_name"] = run.run_name
            profile["run_id"] = str(run.id)
            metrics = run.metrics_json or {}
            profile["metrics_json"] = metrics
            # Dataset row count
            try:
                if run.snapshot:
                    profile["dataset_row_count"] = run.snapshot.row_count
                else:
                    profile["dataset_row_count"] = None
            except Exception:
                profile["dataset_row_count"] = None
        else:
            profile["run_name"] = None
            profile["run_id"] = None
            profile["metrics_json"] = None
            profile["dataset_row_count"] = None
    except Exception:
        for k in ["run_name", "run_id", "metrics_json", "dataset_row_count"]:
            profile.setdefault(k, None)

    # --- f) Backtest audit ---
    try:
        audit = None
        if run and hasattr(run, "backtest_audits") and run.backtest_audits:
            audit = run.backtest_audits[0]
        if audit:
            profile["trust_score"] = audit.trust_score
            profile["overall_status"] = audit.overall_status
        else:
            profile["trust_score"] = None
            profile["overall_status"] = None
    except Exception:
        profile.setdefault("trust_score", None)
        profile.setdefault("overall_status", None)

    # --- g) Backtest reality check (M93) ---
    try:
        from app.services.backtest_reality_score import compute_backtest_reality_check

        run_id_arg = uuid.UUID(profile["run_id"]) if profile.get("run_id") else None
        reality = compute_backtest_reality_check(strategy_id, db, run_id=run_id_arg)
        profile["backtest_reality_score"] = reality.backtest_reality_score
        profile["reality_verdict"] = reality.verdict
    except Exception:
        profile.setdefault("backtest_reality_score", None)
        profile.setdefault("reality_verdict", None)

    # --- h) Evidence verification (M92) ---
    try:
        from app.services.evidence_verification import verify_strategy_evidence

        verification = verify_strategy_evidence(strategy_id, db)
        profile["verification_score"] = verification.verification_score
        profile["verification_verdict"] = verification.verdict
        profile["chain_status"] = getattr(verification, "chain_status", None)
    except Exception:
        profile.setdefault("verification_score", None)
        profile.setdefault("verification_verdict", None)
        profile.setdefault("chain_status", None)

    # --- i) Reliability score ---
    try:
        from app.models.strategy_reliability_score import StrategyReliabilityScore

        rel = (
            db.query(StrategyReliabilityScore)
            .filter(StrategyReliabilityScore.strategy_id == strategy_id)
            .order_by(StrategyReliabilityScore.generated_at.desc())
            .first()
        )
        if rel:
            profile["reliability_score"] = rel.overall_score
            profile["reliability_status"] = rel.status
        else:
            profile["reliability_score"] = None
            profile["reliability_status"] = None
    except Exception:
        profile.setdefault("reliability_score", None)
        profile.setdefault("reliability_status", None)

    return profile


# ---------------------------------------------------------------------------
# Internal diff helpers
# ---------------------------------------------------------------------------

_HIGHER_BETTER = {"sharpe", "annual_return", "win_rate", "trade_count"}
_LOWER_BETTER = {"volatility", "max_drawdown", "turnover"}
_ALL_METRICS = ["sharpe", "annual_return", "volatility", "max_drawdown",
                "turnover", "trade_count", "win_rate"]


def _safe_float(val: Any) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _classify_metric(key: str, base_val: float | None, comp_val: float | None) -> dict:
    """Return a DiffItem dict for a single metric."""
    if base_val is None and comp_val is None:
        return {
            "key": key,
            "label": key.replace("_", " ").title(),
            "base_value": None,
            "comparison_value": None,
            "delta": None,
            "percent_delta": None,
            "status": "missing",
            "significant": False,
            "explanation": "Metric not available in either version.",
        }

    absolute_delta: float | None = None
    percent_delta: float | None = None
    status = "unchanged"

    if base_val is not None and comp_val is not None:
        absolute_delta = comp_val - base_val
        if base_val != 0:
            percent_delta = (absolute_delta / abs(base_val)) * 100
        else:
            percent_delta = None

        if percent_delta is not None and abs(percent_delta) > 0.1:
            if key in _HIGHER_BETTER:
                status = "improved" if absolute_delta > 0 else "worsened"
            elif key in _LOWER_BETTER:
                # max_drawdown: more negative = worse; larger absolute = worse
                if key == "max_drawdown":
                    status = "improved" if absolute_delta > 0 else "worsened"
                else:
                    status = "improved" if absolute_delta < 0 else "worsened"
            else:
                status = "changed"
        else:
            status = "unchanged"

    significant = (
        percent_delta is not None and abs(percent_delta) > 20
    )

    explanation_parts = []
    if base_val is None:
        explanation_parts.append("Not available in base version.")
    elif comp_val is None:
        explanation_parts.append("Not available in comparison version.")
    elif percent_delta is not None:
        direction = "increased" if absolute_delta > 0 else "decreased"
        explanation_parts.append(
            f"{key.replace('_', ' ').title()} {direction} by {abs(percent_delta):.1f}%."
        )
    else:
        explanation_parts.append(f"Base: {base_val}. Comparison: {comp_val}.")

    return {
        "key": key,
        "label": key.replace("_", " ").title(),
        "base_value": base_val,
        "comparison_value": comp_val,
        "delta": absolute_delta,
        "percent_delta": percent_delta,
        "status": status,
        "significant": significant,
        "explanation": " ".join(explanation_parts),
    }


def _section_metric_status(items: list[dict]) -> str:
    statuses = [it["status"] for it in items if it["status"] != "missing"]
    if not statuses:
        return "missing"
    improved = sum(1 for s in statuses if s == "improved")
    worsened = sum(1 for s in statuses if s == "worsened")
    if improved > worsened:
        return "improved"
    if worsened > improved:
        return "worse"
    if improved > 0 or worsened > 0:
        return "mixed"
    return "unchanged"


# ---------------------------------------------------------------------------
# FUNCTION 3: compare_strategy_versions
# ---------------------------------------------------------------------------


def compare_strategy_versions(
    strategy_id: uuid.UUID,
    base_version_label: str,
    comparison_version_label: str,
    db: Session,
) -> dict:
    """Compute a full evidence diff between two strategy versions."""
    now = datetime.now(timezone.utc)

    base_profile = build_version_evidence_profile(strategy_id, base_version_label, db)
    comp_profile = build_version_evidence_profile(strategy_id, comparison_version_label, db)

    # Insufficient data guard
    if not base_profile.get("found") or not comp_profile.get("found"):
        missing = []
        if not base_profile.get("found"):
            missing.append(base_version_label)
        if not comp_profile.get("found"):
            missing.append(comparison_version_label)
        return {
            "strategy_id": str(strategy_id),
            "base_version": base_version_label,
            "comparison_version": comparison_version_label,
            "verdict": "insufficient_data",
            "trust_delta": None,
            "primary_change": None,
            "primary_risk": f"Version(s) not found: {', '.join(missing)}",
            "summary": f"Cannot compare: version(s) not found: {', '.join(missing)}.",
            "sections": [],
            "metric_deltas": [],
            "blockers_introduced": [],
            "blockers_resolved": [],
            "suggested_actions": [f"Log evidence for version(s): {', '.join(missing)}."],
            "generated_at": now.isoformat(),
            "disclaimer": DISCLAIMER,
        }

    base_has_run = base_profile.get("run_id") is not None
    comp_has_run = comp_profile.get("run_id") is not None

    if not base_has_run or not comp_has_run:
        missing_runs = []
        if not base_has_run:
            missing_runs.append(base_version_label)
        if not comp_has_run:
            missing_runs.append(comparison_version_label)
        return {
            "strategy_id": str(strategy_id),
            "base_version": base_version_label,
            "comparison_version": comparison_version_label,
            "verdict": "insufficient_data",
            "trust_delta": None,
            "primary_change": None,
            "primary_risk": f"No backtest run logged for version(s): {', '.join(missing_runs)}",
            "summary": f"Cannot compare: no backtest run for {', '.join(missing_runs)}.",
            "sections": [],
            "metric_deltas": [],
            "blockers_introduced": [],
            "blockers_resolved": [],
            "suggested_actions": [
                f"Log a backtest run for version(s): {', '.join(missing_runs)}."
            ],
            "generated_at": now.isoformat(),
            "disclaimer": DISCLAIMER,
        }

    sections = []

    # ------------------------------------------------------------------
    # SECTION A: version_metadata
    # ------------------------------------------------------------------
    meta_items = []
    for field_key, label in [
        ("git_commit", "Git Commit"),
        ("branch_name", "Branch Name"),
        ("signal_name", "Signal Name"),
    ]:
        bv = base_profile.get(field_key)
        cv = comp_profile.get(field_key)
        changed = bv != cv
        meta_items.append(
            {
                "key": field_key,
                "label": label,
                "base_value": bv,
                "comparison_value": cv,
                "delta": None,
                "status": "changed" if changed else "unchanged",
                "explanation": f"{label} changed from {bv!r} to {cv!r}." if changed else f"{label} unchanged.",
            }
        )
    section_a_status = "changed" if any(it["status"] == "changed" for it in meta_items) else "unchanged"
    sections.append(
        {
            "key": "version_metadata",
            "title": "Version Metadata",
            "status": section_a_status,
            "items": meta_items,
        }
    )

    # ------------------------------------------------------------------
    # SECTION B: config_diff
    # ------------------------------------------------------------------
    config_items = []
    high_risk_changes = False

    base_params = base_profile.get("config_params") or {}
    comp_params = comp_profile.get("config_params") or {}
    all_param_keys = set(base_params) | set(comp_params)
    for pk in sorted(all_param_keys):
        bv = base_params.get(pk)
        cv = comp_params.get(pk)
        if pk not in base_params:
            status = "added"
            explanation = f"Param {pk!r} added in comparison (value: {cv})."
        elif pk not in comp_params:
            status = "removed"
            explanation = f"Param {pk!r} removed in comparison (was: {bv})."
        elif bv != cv:
            status = "changed"
            explanation = f"Param {pk!r} changed: {bv} -> {cv}."
        else:
            status = "unchanged"
            explanation = f"Param {pk!r} unchanged ({bv})."
        config_items.append(
            {
                "key": f"param_{pk}",
                "label": f"Param: {pk}",
                "base_value": bv,
                "comparison_value": cv,
                "delta": None,
                "status": status,
                "explanation": explanation,
            }
        )

    _KEY_ASSUMPTIONS = [
        "transaction_cost_bps",
        "slippage_bps",
        "fill_model",
        "short_enabled",
        "leverage_limit",
    ]
    base_assumptions = base_profile.get("config_assumptions") or {}
    comp_assumptions = comp_profile.get("config_assumptions") or {}

    for ak in _KEY_ASSUMPTIONS:
        bv = base_assumptions.get(ak)
        cv = comp_assumptions.get(ak)
        if bv is None and cv is None:
            continue
        if ak not in base_assumptions and cv is not None:
            status = "added"
            explanation = f"Assumption {ak!r} added in comparison (value: {cv})."
        elif ak in base_assumptions and ak not in comp_assumptions:
            status = "removed"
            explanation = f"Assumption {ak!r} removed in comparison (was: {bv})."
            # Cost removed or zeroed is high-risk
            if ak in ("transaction_cost_bps", "slippage_bps"):
                high_risk_changes = True
                explanation += " HIGH RISK: cost assumption removed."
        elif bv != cv:
            status = "changed"
            explanation = f"Assumption {ak!r} changed: {bv} -> {cv}."
            # Cost dropped to zero or near zero
            if ak in ("transaction_cost_bps", "slippage_bps"):
                bv_f = _safe_float(bv)
                cv_f = _safe_float(cv)
                if cv_f is not None and bv_f is not None and cv_f < bv_f and cv_f == 0:
                    high_risk_changes = True
                    explanation += " HIGH RISK: cost zeroed."
            # short_enabled changes
            if ak == "short_enabled" and bv != cv:
                high_risk_changes = True
                explanation += " HIGH RISK: short_enabled changed."
        else:
            status = "unchanged"
            explanation = f"Assumption {ak!r} unchanged ({bv})."
        config_items.append(
            {
                "key": f"assumption_{ak}",
                "label": f"Assumption: {ak}",
                "base_value": bv,
                "comparison_value": cv,
                "delta": None,
                "status": status,
                "explanation": explanation,
            }
        )

    changed_cfg = any(it["status"] in ("added", "removed", "changed") for it in config_items)
    if high_risk_changes:
        section_b_status = "worse"
    elif changed_cfg:
        section_b_status = "changed"
    else:
        section_b_status = "unchanged"

    sections.append(
        {
            "key": "config_diff",
            "title": "Config Diff",
            "status": section_b_status,
            "items": config_items,
        }
    )

    # ------------------------------------------------------------------
    # SECTION C: universe_diff
    # ------------------------------------------------------------------
    uni_items = []
    base_syms = set(base_profile.get("universe_symbols") or [])
    comp_syms = set(comp_profile.get("universe_symbols") or [])
    added_syms = sorted(comp_syms - base_syms)
    removed_syms = sorted(base_syms - comp_syms)
    overlap = base_syms & comp_syms
    overlap_pct = (
        round(len(overlap) / len(base_syms | comp_syms) * 100, 1)
        if (base_syms or comp_syms)
        else 100.0
    )
    base_sc = base_profile.get("universe_symbol_count")
    comp_sc = comp_profile.get("universe_symbol_count")
    sc_delta = (comp_sc - base_sc) if (base_sc is not None and comp_sc is not None) else None

    uni_items.append(
        {
            "key": "universe_added_symbols",
            "label": "Added Symbols",
            "base_value": [],
            "comparison_value": added_syms,
            "delta": len(added_syms),
            "status": "changed" if added_syms else "unchanged",
            "explanation": f"{len(added_syms)} symbol(s) added." if added_syms else "No symbols added.",
        }
    )
    uni_items.append(
        {
            "key": "universe_removed_symbols",
            "label": "Removed Symbols",
            "base_value": removed_syms,
            "comparison_value": [],
            "delta": -len(removed_syms),
            "status": "changed" if removed_syms else "unchanged",
            "explanation": f"{len(removed_syms)} symbol(s) removed." if removed_syms else "No symbols removed.",
        }
    )
    uni_items.append(
        {
            "key": "universe_symbol_count",
            "label": "Symbol Count",
            "base_value": base_sc,
            "comparison_value": comp_sc,
            "delta": sc_delta,
            "status": "changed" if sc_delta and sc_delta != 0 else "unchanged",
            "explanation": f"Symbol count delta: {sc_delta}." if sc_delta is not None else "Symbol count unchanged.",
        }
    )
    uni_items.append(
        {
            "key": "universe_overlap_pct",
            "label": "Symbol Overlap %",
            "base_value": None,
            "comparison_value": overlap_pct,
            "delta": None,
            "status": "unchanged" if overlap_pct == 100 else "changed",
            "explanation": f"Symbol overlap between versions: {overlap_pct}%.",
        }
    )

    symbols_differ = bool(added_syms or removed_syms)
    section_c_status = "changed" if symbols_differ else "unchanged"
    sections.append(
        {
            "key": "universe_diff",
            "title": "Universe Diff",
            "status": section_c_status,
            "items": uni_items,
        }
    )

    # ------------------------------------------------------------------
    # SECTION D: signal_diff
    # ------------------------------------------------------------------
    sig_items = []
    base_sig_name = base_profile.get("signal_name")
    comp_sig_name = comp_profile.get("signal_name")
    sig_name_changed = base_sig_name != comp_sig_name
    sig_items.append(
        {
            "key": "signal_name",
            "label": "Signal Name",
            "base_value": base_sig_name,
            "comparison_value": comp_sig_name,
            "delta": None,
            "status": "changed" if sig_name_changed else "unchanged",
            "explanation": (
                f"Signal name changed: {base_sig_name!r} -> {comp_sig_name!r}."
                if sig_name_changed
                else f"Signal name unchanged ({base_sig_name!r})."
            ),
        }
    )
    base_src = base_profile.get("signal_row_count")
    comp_src = comp_profile.get("signal_row_count")
    src_delta = (comp_src - base_src) if (base_src is not None and comp_src is not None) else None
    sig_items.append(
        {
            "key": "signal_row_count",
            "label": "Signal Row Count",
            "base_value": base_src,
            "comparison_value": comp_src,
            "delta": src_delta,
            "status": "changed" if src_delta and src_delta != 0 else "unchanged",
            "explanation": f"Signal row count delta: {src_delta}." if src_delta is not None else "Row count unchanged.",
        }
    )
    base_sig_syms = base_profile.get("signal_symbols") or []
    comp_sig_syms = comp_profile.get("signal_symbols") or []
    sig_sym_delta = len(comp_sig_syms) - len(base_sig_syms)
    sig_items.append(
        {
            "key": "signal_symbol_count",
            "label": "Signal Symbol Count",
            "base_value": len(base_sig_syms),
            "comparison_value": len(comp_sig_syms),
            "delta": sig_sym_delta,
            "status": "changed" if sig_sym_delta != 0 else "unchanged",
            "explanation": f"Signal symbol count delta: {sig_sym_delta}.",
        }
    )
    base_sh = base_profile.get("signal_hash")
    comp_sh = comp_profile.get("signal_hash")
    sig_hash_changed = (base_sh is not None or comp_sh is not None) and base_sh != comp_sh
    sig_items.append(
        {
            "key": "signal_hash",
            "label": "Signal Hash",
            "base_value": base_sh,
            "comparison_value": comp_sh,
            "delta": None,
            "status": "changed" if sig_hash_changed else "unchanged",
            "explanation": (
                "Signal data changed (hash differs)."
                if sig_hash_changed
                else "Signal data unchanged."
            ),
        }
    )
    section_d_status = "changed" if sig_hash_changed else "unchanged"
    sections.append(
        {
            "key": "signal_diff",
            "title": "Signal Diff",
            "status": section_d_status,
            "items": sig_items,
        }
    )

    # ------------------------------------------------------------------
    # SECTION E: dataset_diff
    # ------------------------------------------------------------------
    ds_items = []
    base_ds_rc = base_profile.get("dataset_row_count")
    comp_ds_rc = comp_profile.get("dataset_row_count")
    ds_delta = (
        comp_ds_rc - base_ds_rc
        if (base_ds_rc is not None and comp_ds_rc is not None)
        else None
    )
    ds_pct = (
        abs(ds_delta / base_ds_rc * 100) if (ds_delta is not None and base_ds_rc not in (None, 0)) else None
    )
    ds_changed = ds_delta is not None and ds_delta != 0 and (ds_pct is None or ds_pct > 5)
    ds_items.append(
        {
            "key": "dataset_row_count",
            "label": "Dataset Row Count",
            "base_value": base_ds_rc,
            "comparison_value": comp_ds_rc,
            "delta": ds_delta,
            "status": "changed" if ds_changed else "unchanged",
            "explanation": (
                f"Dataset row count delta: {ds_delta} ({ds_pct:.1f}%)."
                if (ds_delta is not None and ds_pct is not None)
                else (f"Dataset row count delta: {ds_delta}." if ds_delta is not None else "Dataset row count unchanged.")
            ),
        }
    )
    section_e_status = "changed" if ds_changed else "unchanged"
    sections.append(
        {
            "key": "dataset_diff",
            "title": "Dataset Diff",
            "status": section_e_status,
            "items": ds_items,
        }
    )

    # ------------------------------------------------------------------
    # SECTION F: run_metric_diff
    # ------------------------------------------------------------------
    metric_items = []
    base_metrics = base_profile.get("metrics_json") or {}
    comp_metrics = comp_profile.get("metrics_json") or {}
    for metric_key in _ALL_METRICS:
        bv = _safe_float(base_metrics.get(metric_key))
        cv = _safe_float(comp_metrics.get(metric_key))
        metric_items.append(_classify_metric(metric_key, bv, cv))
    section_f_status = _section_metric_status(metric_items)
    sections.append(
        {
            "key": "run_metric_diff",
            "title": "Run Metric Diff",
            "status": section_f_status,
            "items": metric_items,
        }
    )

    # ------------------------------------------------------------------
    # SECTION G: trust_diff
    # ------------------------------------------------------------------
    trust_items = []
    THRESHOLD = 5.0

    def _trust_item(key: str, label: str, bv: Any, cv: Any) -> dict:
        bv_f = _safe_float(bv)
        cv_f = _safe_float(cv)
        if bv_f is None and cv_f is None:
            return {
                "key": key, "label": label,
                "base_value": None, "comparison_value": None,
                "delta": None, "status": "missing",
                "explanation": f"{label} not available.",
            }
        delta = (cv_f - bv_f) if (bv_f is not None and cv_f is not None) else None
        if delta is None:
            status = "missing"
        elif delta >= THRESHOLD:
            status = "improved"
        elif delta <= -THRESHOLD:
            status = "worsened"
        else:
            status = "unchanged"
        return {
            "key": key, "label": label,
            "base_value": bv_f, "comparison_value": cv_f,
            "delta": delta, "status": status,
            "explanation": (
                f"{label} changed by {delta:+.1f}." if delta is not None else f"{label} partially available."
            ),
        }

    trust_items.append(_trust_item(
        "trust_score", "Backtest Trust Score",
        base_profile.get("trust_score"), comp_profile.get("trust_score"),
    ))
    trust_items.append(_trust_item(
        "backtest_reality_score", "Backtest Reality Score",
        base_profile.get("backtest_reality_score"), comp_profile.get("backtest_reality_score"),
    ))
    trust_items.append(_trust_item(
        "verification_score", "Evidence Verification Score",
        base_profile.get("verification_score"), comp_profile.get("verification_score"),
    ))
    trust_items.append(_trust_item(
        "reliability_score", "Strategy Reliability Score",
        base_profile.get("reliability_score"), comp_profile.get("reliability_score"),
    ))

    trust_statuses = [it["status"] for it in trust_items if it["status"] != "missing"]
    if all(s in ("improved", "unchanged") for s in trust_statuses) and "improved" in trust_statuses:
        section_g_status = "improved"
    elif any(s == "worsened" for s in trust_statuses):
        section_g_status = "worse"
    elif any(s == "improved" for s in trust_statuses):
        section_g_status = "mixed"
    else:
        section_g_status = "unchanged"
    sections.append(
        {
            "key": "trust_diff",
            "title": "Trust and Evidence Diff",
            "status": section_g_status,
            "items": trust_items,
        }
    )

    # ------------------------------------------------------------------
    # SECTION H: blocker_diff
    # ------------------------------------------------------------------
    blocker_items = []

    def _blocker_item(key: str, label: str, introduced: bool, resolved: bool) -> dict:
        if introduced:
            status = "introduced"
        elif resolved:
            status = "resolved"
        else:
            status = "unchanged"
        explanation = (
            f"{label} introduced in comparison version."
            if introduced
            else (f"{label} resolved in comparison version." if resolved else f"{label} unchanged.")
        )
        return {
            "key": key,
            "label": label,
            "base_value": None,
            "comparison_value": None,
            "delta": None,
            "status": status,
            "explanation": explanation,
        }

    # config_cost_missing
    base_has_cost = base_profile.get("transaction_cost_bps") is not None
    comp_has_cost = comp_profile.get("transaction_cost_bps") is not None
    blocker_items.append(_blocker_item(
        "config_cost_missing",
        "Transaction cost not declared",
        introduced=(base_has_cost and not comp_has_cost),
        resolved=(not base_has_cost and comp_has_cost),
    ))

    # short_enabled_removed
    base_short = base_profile.get("short_enabled")
    comp_short = comp_profile.get("short_enabled")
    base_had_short = base_short is True
    comp_lost_short = comp_short is not True
    blocker_items.append(_blocker_item(
        "short_enabled_removed",
        "Short selling enabled flag removed or disabled",
        introduced=(base_had_short and comp_lost_short),
        resolved=(not base_had_short and comp_short is True),
    ))

    # signal_missing
    base_has_signal = base_profile.get("signal_hash") is not None
    comp_has_signal = comp_profile.get("signal_hash") is not None
    blocker_items.append(_blocker_item(
        "signal_missing",
        "Signal snapshot missing",
        introduced=(base_has_signal and not comp_has_signal),
        resolved=(not base_has_signal and comp_has_signal),
    ))

    # universe_missing
    base_has_uni = base_profile.get("universe_hash") is not None
    comp_has_uni = comp_profile.get("universe_hash") is not None
    blocker_items.append(_blocker_item(
        "universe_missing",
        "Universe snapshot missing",
        introduced=(base_has_uni and not comp_has_uni),
        resolved=(not base_has_uni and comp_has_uni),
    ))

    # verification_degraded
    base_v_rank = _verification_rank(base_profile.get("verification_verdict"))
    comp_v_rank = _verification_rank(comp_profile.get("verification_verdict"))
    verif_degraded = (base_v_rank >= 0 and comp_v_rank >= 0 and comp_v_rank > base_v_rank)
    verif_improved = (base_v_rank >= 0 and comp_v_rank >= 0 and comp_v_rank < base_v_rank)
    blocker_items.append(_blocker_item(
        "verification_degraded",
        "Evidence verification verdict worsened",
        introduced=verif_degraded,
        resolved=verif_improved,
    ))

    # reality_degraded
    base_r_rank = _reality_rank(base_profile.get("reality_verdict"))
    comp_r_rank = _reality_rank(comp_profile.get("reality_verdict"))
    reality_degraded = (base_r_rank >= 0 and comp_r_rank >= 0 and comp_r_rank > base_r_rank)
    reality_improved = (base_r_rank >= 0 and comp_r_rank >= 0 and comp_r_rank < base_r_rank)
    blocker_items.append(_blocker_item(
        "reality_degraded",
        "Backtest reality verdict worsened",
        introduced=reality_degraded,
        resolved=reality_improved,
    ))

    introduced_count = sum(1 for it in blocker_items if it["status"] == "introduced")
    resolved_count = sum(1 for it in blocker_items if it["status"] == "resolved")
    if introduced_count > 0:
        section_h_status = "worse"
    elif resolved_count > 0:
        section_h_status = "improved"
    else:
        section_h_status = "unchanged"
    sections.append(
        {
            "key": "blocker_diff",
            "title": "Blocker Diff",
            "status": section_h_status,
            "items": blocker_items,
        }
    )

    # ------------------------------------------------------------------
    # VERDICT
    # ------------------------------------------------------------------
    improved_sections = sum(1 for s in sections if s["status"] in ("improved",))
    worsened_sections = sum(1 for s in sections if s["status"] in ("worse",))

    if introduced_count > 0 and worsened_sections > improved_sections:
        verdict = "worse"
    elif improved_sections > worsened_sections and introduced_count == 0:
        verdict = "improved"
    elif improved_sections > 0 or worsened_sections > 0:
        verdict = "mixed"
    else:
        verdict = "unchanged"

    # ------------------------------------------------------------------
    # TRUST DELTA
    # ------------------------------------------------------------------
    base_rel = _safe_float(base_profile.get("reliability_score"))
    comp_rel = _safe_float(comp_profile.get("reliability_score"))
    trust_delta = (comp_rel - base_rel) if (base_rel is not None and comp_rel is not None) else None

    # ------------------------------------------------------------------
    # PRIMARY CHANGE (biggest % delta in run metrics)
    # ------------------------------------------------------------------
    primary_change: str | None = None
    max_pct = 0.0
    for it in metric_items:
        if it.get("percent_delta") is not None and abs(it["percent_delta"]) > max_pct:
            max_pct = abs(it["percent_delta"])
            direction = "improved" if it["status"] == "improved" else "worsened"
            primary_change = (
                f"{it['label']} {direction} by {abs(it['percent_delta']):.1f}%."
            )

    # ------------------------------------------------------------------
    # PRIMARY RISK
    # ------------------------------------------------------------------
    primary_risk: str | None = None
    introduced_blockers = [it for it in blocker_items if it["status"] == "introduced"]
    if introduced_blockers:
        primary_risk = introduced_blockers[0]["label"]
    else:
        worsened_metric = next(
            (it for it in metric_items if it["status"] == "worsened" and it.get("significant")),
            None,
        )
        if worsened_metric:
            primary_risk = f"Significant worsening in {worsened_metric['label']}."
        elif worsened_sections > 0:
            worst_sec = next(s for s in sections if s["status"] == "worse")
            primary_risk = f"Section worsened: {worst_sec['title']}."

    # ------------------------------------------------------------------
    # SUMMARY
    # ------------------------------------------------------------------
    summary_parts: list[str] = []
    # Key metric movements
    for it in metric_items:
        if it.get("significant") and it["status"] in ("improved", "worsened"):
            direction = "improved" if it["status"] == "improved" else "worsened"
            summary_parts.append(
                f"{it['label']} {direction} by {abs(it['percent_delta']):.0f}%."
            )
    # Introduced blockers
    for blk in introduced_blockers:
        summary_parts.append(f"{blk['label']} in {comparison_version_label}.")
    # Resolved
    resolved_blockers = [it for it in blocker_items if it["status"] == "resolved"]
    for blk in resolved_blockers:
        summary_parts.append(f"{blk['label']} resolved in {comparison_version_label}.")
    if not summary_parts:
        if verdict == "unchanged":
            summary_parts.append("No significant evidence changes detected between versions.")
        else:
            summary_parts.append(f"Evidence comparison verdict: {verdict}.")
    summary = " ".join(summary_parts)

    # ------------------------------------------------------------------
    # SUGGESTED ACTIONS
    # ------------------------------------------------------------------
    suggested_actions: list[str] = []
    for blk in introduced_blockers:
        suggested_actions.append(f"Review and resolve: {blk['label']}.")
    for it in metric_items:
        if it["status"] == "worsened" and it.get("significant"):
            suggested_actions.append(
                f"Investigate {it['label']} worsening ({abs(it['percent_delta']):.1f}%)."
            )
    if not suggested_actions:
        if verdict == "improved":
            suggested_actions.append("Evidence improved. Consider logging a new reliability score.")
        else:
            suggested_actions.append("Review evidence diff and update config assumptions if needed.")

    # ------------------------------------------------------------------
    # Flat metric_deltas and blocker lists
    # ------------------------------------------------------------------
    metric_deltas = metric_items

    return {
        "strategy_id": str(strategy_id),
        "base_version": base_version_label,
        "comparison_version": comparison_version_label,
        "verdict": verdict,
        "trust_delta": trust_delta,
        "primary_change": primary_change,
        "primary_risk": primary_risk,
        "summary": summary,
        "sections": sections,
        "metric_deltas": metric_deltas,
        "blockers_introduced": introduced_blockers,
        "blockers_resolved": resolved_blockers,
        "suggested_actions": suggested_actions,
        "generated_at": now.isoformat(),
        "disclaimer": DISCLAIMER,
    }


# ---------------------------------------------------------------------------
# FUNCTION 4: render_lineage_diff_report
# ---------------------------------------------------------------------------


def render_lineage_diff_report(
    diff: dict,
    strategy_name: str,
    format: str = "json",
) -> str:
    """Render a lineage diff as markdown or JSON."""
    if format == "markdown":
        base = diff.get("base_version", "")
        comparison = diff.get("comparison_version", "")
        generated_at = diff.get("generated_at", "")
        verdict = diff.get("verdict", "")
        summary = diff.get("summary", "")
        sections = diff.get("sections", [])
        metric_deltas = diff.get("metric_deltas", [])
        blockers_introduced = diff.get("blockers_introduced", [])
        blockers_resolved = diff.get("blockers_resolved", [])
        suggested_actions = diff.get("suggested_actions", [])
        disclaimer = diff.get("disclaimer", DISCLAIMER)

        lines: list[str] = []
        lines.append(f"# Strategy Lineage Diff: {base} -> {comparison}")
        lines.append(f"Generated: {generated_at} | Strategy: {strategy_name} | Verdict: {verdict}")
        lines.append("")
        lines.append("## Summary")
        lines.append(summary)
        lines.append("")

        # Key changes
        worsened_metrics = [it for it in metric_deltas if it.get("status") == "worsened" and it.get("significant")]
        if worsened_metrics or blockers_introduced:
            lines.append("## Key Changes")
            for it in worsened_metrics:
                lines.append(f"- {it['label']} worsened by {abs(it.get('percent_delta', 0)):.1f}%")
            for blk in blockers_introduced:
                lines.append(f"- RISK: {blk['label']}")
            lines.append("")

        # Run metric diff table
        lines.append("## Run Metric Diff")
        lines.append("| Metric | Base | Comparison | Delta | Status |")
        lines.append("|--------|------|------------|-------|--------|")
        for it in metric_deltas:
            bv = it.get("base_value")
            cv = it.get("comparison_value")
            delta = it.get("delta")
            bv_str = f"{bv:.4f}" if isinstance(bv, float) else (str(bv) if bv is not None else "N/A")
            cv_str = f"{cv:.4f}" if isinstance(cv, float) else (str(cv) if cv is not None else "N/A")
            delta_str = f"{delta:+.4f}" if isinstance(delta, float) else (str(delta) if delta is not None else "N/A")
            lines.append(f"| {it['label']} | {bv_str} | {cv_str} | {delta_str} | {it.get('status', '')} |")
        lines.append("")

        # Config diff
        cfg_section = next((s for s in sections if s["key"] == "config_diff"), None)
        if cfg_section:
            lines.append("## Config Diff")
            for it in cfg_section.get("items", []):
                if it.get("status") != "unchanged":
                    lines.append(f"- [{it['status'].upper()}] {it['label']}: {it.get('explanation', '')}")
            lines.append("")

        # Universe diff
        uni_section = next((s for s in sections if s["key"] == "universe_diff"), None)
        if uni_section:
            lines.append("## Universe Diff")
            for it in uni_section.get("items", []):
                lines.append(f"- {it['label']}: {it.get('explanation', '')}")
            lines.append("")

        # Signal diff
        sig_section = next((s for s in sections if s["key"] == "signal_diff"), None)
        if sig_section:
            lines.append("## Signal Diff")
            for it in sig_section.get("items", []):
                if it.get("status") != "unchanged":
                    lines.append(f"- [{it['status'].upper()}] {it['label']}: {it.get('explanation', '')}")
            if not any(it.get("status") != "unchanged" for it in sig_section.get("items", [])):
                lines.append("- No signal changes detected.")
            lines.append("")

        # Trust diff
        trust_section = next((s for s in sections if s["key"] == "trust_diff"), None)
        if trust_section:
            lines.append("## Trust and Evidence Diff")
            for it in trust_section.get("items", []):
                lines.append(f"- {it['label']}: {it.get('explanation', '')} (status: {it.get('status', '')})")
            lines.append("")

        # New risks
        if blockers_introduced:
            lines.append("## New Risks")
            for blk in blockers_introduced:
                lines.append(f"- {blk['label']}")
            lines.append("")

        # Resolved items
        if blockers_resolved:
            lines.append("## Resolved Items")
            for blk in blockers_resolved:
                lines.append(f"- {blk['label']}")
            lines.append("")

        # Suggested actions
        if suggested_actions:
            lines.append("## Suggested Actions")
            for action in suggested_actions:
                lines.append(f"- {action}")
            lines.append("")

        lines.append("---")
        lines.append(f"*Disclaimer: {disclaimer}*")

        return "\n".join(lines)

    # Default: JSON
    return json.dumps(diff, default=str, indent=2)
