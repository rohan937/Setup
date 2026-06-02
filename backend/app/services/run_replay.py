"""Run Replay Pack service (M58).

Deterministic packaging of all logged evidence for a single strategy run into
a replay bundle (JSON or Markdown). No AI, no random content, no side effects.
No new DB tables. Read-only.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any

from sqlalchemy.orm import Session


# ---------------------------------------------------------------------------
# Optional service imports — wrapped at call-site with try/except
# ---------------------------------------------------------------------------

try:
    from app.services.strategy_readiness import compute_strategy_readiness
    _HAS_READINESS = True
except ImportError:
    _HAS_READINESS = False

try:
    from app.services.evidence_freshness import compute_evidence_freshness
    _HAS_FRESHNESS = True
except ImportError:
    _HAS_FRESHNESS = False

try:
    from app.services.strategy_drift import compute_strategy_drift
    _HAS_DRIFT = True
except ImportError:
    _HAS_DRIFT = False

try:
    from app.services.shadow_production import compute_shadow_production_monitor
    _HAS_SHADOW = True
except ImportError:
    _HAS_SHADOW = False

try:
    from app.services.assumption_health import compute_assumption_health
    _HAS_ASSUMPTION = True
except ImportError:
    _HAS_ASSUMPTION = False

try:
    from app.services.change_impact import analyze_strategy_change_impact
    _HAS_CHANGE_IMPACT = True
except ImportError:
    _HAS_CHANGE_IMPACT = False


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class RunReplaySectionData:
    section_key: str
    title: str
    summary: str
    severity: str | None = None  # None / low / medium / high / critical
    evidence_json: dict = field(default_factory=dict)


@dataclass
class RunReplayMissingEvidenceData:
    evidence_type: str
    severity: str  # low / medium / high
    suggested_action: str


@dataclass
class RunReplayData:
    replay_id: str
    generated_at: datetime
    format: str
    strategy_id: str
    run_id: str
    filename: str
    deterministic_note: str
    no_execution_replay_note: str
    replay_status: str  # complete / review / incomplete / sparse
    replay_completeness_score: float
    sections: list  # list[RunReplaySectionData]
    missing_evidence: list  # list[RunReplayMissingEvidenceData]
    suggested_review_checks: list  # list[str]
    content: str | None = None  # markdown if format=markdown
    raw_evidence: dict | None = None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _safe_filename(strategy_slug: str, run_name: str, fmt: str) -> str:
    """Build a deterministic safe filename for the replay pack."""
    now_ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    def _sanitize(s: str, max_len: int = 40) -> str:
        safe = "".join(
            c.lower() if c.isalnum() or c in "-_" else "_"
            for c in (s or "unknown")
        )
        return safe[:max_len]

    safe_slug = _sanitize(strategy_slug)
    safe_run = _sanitize(run_name)
    return f"quantfidelity_run_replay_{safe_slug}_{safe_run}_{now_ts}.{fmt}"


def _section(
    key: str,
    title: str,
    summary: str,
    severity: str | None = None,
    evidence_json: dict | None = None,
) -> RunReplaySectionData:
    return RunReplaySectionData(
        section_key=key,
        title=title,
        summary=summary,
        severity=severity,
        evidence_json=evidence_json or {},
    )


# ---------------------------------------------------------------------------
# Section collectors
# ---------------------------------------------------------------------------


def _collect_run_sections(
    db: Session,
    strategy: Any,
    run: Any,
    include_raw_json: bool,
) -> tuple[list[RunReplaySectionData], list[RunReplayMissingEvidenceData], list[str]]:
    """Collect all replay sections for a single run.

    Returns (sections, missing_evidence, suggested_checks).
    Each section is wrapped in try/except so one failure does not abort the pack.
    """
    from app.models.backtest_audit import BacktestAudit
    from app.models.backtest_issue import BacktestIssue
    from app.models.dataset_snapshot import DatasetSnapshot
    from app.models.signal_snapshot import SignalSnapshot
    from app.models.strategy_config_snapshot import StrategyConfigSnapshot
    from app.models.strategy_reliability_score import StrategyReliabilityScore
    from app.models.strategy_version import StrategyVersion
    from app.models.universe_snapshot import UniverseSnapshot
    from app.models.alert import Alert
    from app.models.report import Report
    from app.models.audit_timeline_event import AuditTimelineEvent

    sections: list[RunReplaySectionData] = []
    missing: list[RunReplayMissingEvidenceData] = []
    checks: list[str] = []

    # Mutable state shared across section blocks
    _state: dict[str, Any] = {
        "dataset_health": None,
        "signal_quality": None,
        "has_audit": False,
        "config_found": False,
        "readiness_not_ready": False,
    }

    # --- 1. run_identity ---
    try:
        created_str = (
            run.created_at.date().isoformat()
            if run.created_at
            else "unknown"
        )
        ev: dict[str, Any] = {
            "run_id": str(run.id),
            "run_name": run.run_name,
            "run_type": run.run_type,
            "status": run.status,
            "started_at": str(run.started_at) if run.started_at else None,
            "completed_at": str(run.completed_at) if run.completed_at else None,
            "created_at": str(run.created_at) if run.created_at else None,
            "notes": run.notes,
            "universe_name": getattr(run, "universe_name", None),
            "dataset_version": getattr(run, "dataset_version", None),
            "has_dataset_snapshot": run.dataset_snapshot_id is not None,
            "has_universe_snapshot": run.universe_snapshot_id is not None,
            "has_signal_snapshot": run.signal_snapshot_id is not None,
            "has_strategy_version": run.strategy_version_id is not None,
        }
        if include_raw_json:
            ev["metrics_json"] = run.metrics_json
            ev["assumptions_json"] = run.assumptions_json
            ev["params_json"] = run.params_json
        else:
            # Include summary counts only
            ev["metrics_count"] = len(run.metrics_json) if isinstance(run.metrics_json, dict) else 0
            ev["assumptions_count"] = len(run.assumptions_json) if isinstance(run.assumptions_json, dict) else 0
            ev["params_count"] = len(run.params_json) if isinstance(run.params_json, dict) else 0
        sections.append(_section(
            "run_identity",
            "Run Identity",
            f"Run {run.run_name} ({run.run_type}) logged {created_str}. Status: {run.status}.",
            evidence_json=ev,
        ))
    except Exception as exc:
        sections.append(_section(
            "run_identity",
            "Run Identity",
            f"Run identity data unavailable: {exc}",
        ))

    # --- 2. strategy_version ---
    try:
        if run.strategy_version_id is not None:
            sv = db.query(StrategyVersion).filter(
                StrategyVersion.id == run.strategy_version_id
            ).first()
            if sv is not None:
                sections.append(_section(
                    "strategy_version",
                    "Strategy Version",
                    f"Version: {sv.version_label or 'unlabeled'}. Branch: {sv.branch_name or 'N/A'}.",
                    evidence_json={
                        "version_id": str(sv.id),
                        "version_label": sv.version_label,
                        "git_commit": sv.git_commit,
                        "branch_name": sv.branch_name,
                        "code_path": sv.code_path,
                        "signal_name": sv.signal_name,
                        "signal_description": sv.signal_description,
                    },
                ))
            else:
                sections.append(_section(
                    "strategy_version",
                    "Strategy Version",
                    "Strategy version ID is set but record not found.",
                    severity="medium",
                ))
                missing.append(RunReplayMissingEvidenceData(
                    evidence_type="strategy_version",
                    severity="high",
                    suggested_action="Strategy version not linked to run. Link a strategy version before promoting.",
                ))
        else:
            sections.append(_section(
                "strategy_version",
                "Strategy Version",
                "No strategy version linked to this run.",
                severity="medium",
            ))
            missing.append(RunReplayMissingEvidenceData(
                evidence_type="strategy_version",
                severity="high",
                suggested_action="Strategy version not linked to run. Link a strategy version before promoting.",
            ))
    except Exception as exc:
        sections.append(_section(
            "strategy_version",
            "Strategy Version",
            f"Strategy version data unavailable: {exc}",
        ))

    # --- 3. config_snapshot ---
    try:
        config_snap = None

        # First try: match by strategy_version_id
        if run.strategy_version_id is not None:
            config_snap = (
                db.query(StrategyConfigSnapshot)
                .filter(StrategyConfigSnapshot.strategy_version_id == run.strategy_version_id)
                .order_by(StrategyConfigSnapshot.created_at.desc())
                .first()
            )

        # Fallback: most recent config snapshot for the strategy at or before run creation
        if config_snap is None:
            q = (
                db.query(StrategyConfigSnapshot)
                .filter(StrategyConfigSnapshot.strategy_id == strategy.id)
                .order_by(StrategyConfigSnapshot.created_at.desc())
            )
            if run.created_at is not None:
                run_created = run.created_at
                if run_created.tzinfo is None:
                    run_created = run_created.replace(tzinfo=timezone.utc)
                q = q.filter(StrategyConfigSnapshot.created_at <= run_created)
            config_snap = q.first()

        if config_snap is not None:
            _state["config_found"] = True
            cfg = config_snap.config_json or {}
            # Extract key assumption fields from config_json or nested keys
            assumptions_src = cfg.get("assumptions") or cfg.get("params") or cfg
            key_assumptions = {
                k: assumptions_src.get(k)
                for k in (
                    "transaction_cost_bps",
                    "slippage_bps",
                    "fill_model",
                    "execution_timing",
                    "borrow_cost_bps",
                    "short_enabled",
                    "max_leverage",
                    "max_position_weight",
                    "liquidity_filter",
                )
                if assumptions_src.get(k) is not None
            }
            ev = {
                "config_snapshot_id": str(config_snap.id),
                "label": config_snap.label,
                "config_hash": config_snap.config_hash,
                "param_count": config_snap.param_count,
                "assumption_count": config_snap.assumption_count,
                "source_type": config_snap.source_type,
                "key_assumptions": key_assumptions,
            }
            if include_raw_json:
                ev["config_json"] = cfg
            sections.append(_section(
                "config_snapshot",
                "Config Snapshot",
                f"Config snapshot '{config_snap.label}' found (hash: {config_snap.config_hash[:8]}...).",
                evidence_json=ev,
            ))
        else:
            sections.append(_section(
                "config_snapshot",
                "Config Snapshot",
                "No config snapshot found for this run or strategy version.",
                severity="medium",
            ))
            missing.append(RunReplayMissingEvidenceData(
                evidence_type="config_snapshot",
                severity="medium",
                suggested_action="Upload a config snapshot linked to this strategy or strategy version.",
            ))
    except Exception as exc:
        sections.append(_section(
            "config_snapshot",
            "Config Snapshot",
            f"Config snapshot data unavailable: {exc}",
        ))

    # --- 4. dataset_evidence ---
    try:
        if run.dataset_snapshot_id is not None:
            ds = db.query(DatasetSnapshot).filter(
                DatasetSnapshot.id == run.dataset_snapshot_id
            ).first()
            if ds is not None:
                _state["dataset_health"] = ds.health_score
                sev = (
                    "high" if ds.health_score < 60
                    else "medium" if ds.health_score < 75
                    else None
                )
                col_count: int | None = None
                if isinstance(ds.column_quality_json, list):
                    col_count = len(ds.column_quality_json)
                ev = {
                    "dataset_snapshot_id": str(ds.id),
                    "version_label": ds.version_label,
                    "health_score": ds.health_score,
                    "row_count": ds.row_count,
                    "column_count": col_count,
                    "quality_summary": ds.quality_summary_json,
                }
                if include_raw_json:
                    rows = ds.rows_json
                    if isinstance(rows, list) and len(rows) > 100:
                        ev["rows_json_sample"] = rows[:100]
                        ev["rows_json_truncated"] = True
                        ev["rows_json_total"] = len(rows)
                    else:
                        ev["rows_json"] = rows
                sections.append(_section(
                    "dataset_evidence",
                    "Dataset Evidence",
                    (
                        f"Dataset snapshot '{ds.version_label}' linked. "
                        f"Health score: {ds.health_score}/100. "
                        f"Rows: {ds.row_count}."
                    ),
                    severity=sev,
                    evidence_json=ev,
                ))
            else:
                sections.append(_section(
                    "dataset_evidence",
                    "Dataset Evidence",
                    "Dataset snapshot ID set but record not found.",
                    severity="medium",
                ))
                missing.append(RunReplayMissingEvidenceData(
                    evidence_type="dataset_snapshot",
                    severity="medium",
                    suggested_action="Re-link the dataset snapshot — the referenced record is missing.",
                ))
        else:
            sections.append(_section(
                "dataset_evidence",
                "Dataset Evidence",
                "No dataset snapshot linked to this run.",
                severity="medium",
            ))
            missing.append(RunReplayMissingEvidenceData(
                evidence_type="dataset_snapshot",
                severity="medium",
                suggested_action="Link a dataset snapshot to this run to capture input data evidence.",
            ))
    except Exception as exc:
        sections.append(_section(
            "dataset_evidence",
            "Dataset Evidence",
            f"Dataset evidence unavailable: {exc}",
        ))

    # --- 5. signal_evidence ---
    try:
        if run.signal_snapshot_id is not None:
            ss = db.query(SignalSnapshot).filter(
                SignalSnapshot.id == run.signal_snapshot_id
            ).first()
            if ss is not None:
                _state["signal_quality"] = ss.quality_score
                sev = (
                    "high" if ss.quality_score < 60
                    else "medium" if ss.quality_score < 75
                    else None
                )
                ev = {
                    "signal_snapshot_id": str(ss.id),
                    "label": ss.label,
                    "signal_name": ss.signal_name,
                    "quality_score": ss.quality_score,
                    "signal_hash": ss.signal_hash,
                    "row_count": ss.row_count,
                    "symbol_count": ss.symbol_count,
                    "missing_signal_count": ss.missing_signal_count,
                    "mean_value": ss.mean_value,
                    "min_value": ss.min_value,
                    "max_value": ss.max_value,
                    "stddev_value": ss.stddev_value,
                    "min_timestamp": ss.min_timestamp,
                    "max_timestamp": ss.max_timestamp,
                    "signal_quality_summary": ss.signal_quality_summary_json,
                }
                if include_raw_json:
                    rows = ss.rows_json
                    if isinstance(rows, list) and len(rows) > 100:
                        ev["rows_json_sample"] = rows[:100]
                        ev["rows_json_truncated"] = True
                        ev["rows_json_total"] = len(rows)
                    else:
                        ev["rows_json"] = rows
                sections.append(_section(
                    "signal_evidence",
                    "Signal Evidence",
                    (
                        f"Signal snapshot '{ss.label}' linked. "
                        f"Quality score: {ss.quality_score}/100. "
                        f"Symbols: {ss.symbol_count}."
                    ),
                    severity=sev,
                    evidence_json=ev,
                ))
            else:
                sections.append(_section(
                    "signal_evidence",
                    "Signal Evidence",
                    "Signal snapshot ID set but record not found.",
                    severity="medium",
                ))
                missing.append(RunReplayMissingEvidenceData(
                    evidence_type="signal_snapshot",
                    severity="medium",
                    suggested_action="Re-link the signal snapshot — the referenced record is missing.",
                ))
        else:
            sections.append(_section(
                "signal_evidence",
                "Signal Evidence",
                "No signal snapshot linked to this run.",
                severity="medium",
            ))
            missing.append(RunReplayMissingEvidenceData(
                evidence_type="signal_snapshot",
                severity="medium",
                suggested_action="Link a signal snapshot to this run to capture signal input evidence.",
            ))
    except Exception as exc:
        sections.append(_section(
            "signal_evidence",
            "Signal Evidence",
            f"Signal evidence unavailable: {exc}",
        ))

    # --- 6. universe_evidence ---
    try:
        if run.universe_snapshot_id is not None:
            us = db.query(UniverseSnapshot).filter(
                UniverseSnapshot.id == run.universe_snapshot_id
            ).first()
            if us is not None:
                ev = {
                    "universe_snapshot_id": str(us.id),
                    "label": us.label,
                    "symbol_count": us.symbol_count,
                    "universe_hash": us.universe_hash,
                    "source_type": us.source_type,
                    "universe_quality_summary": us.universe_quality_summary_json,
                }
                if include_raw_json:
                    syms = us.symbols_json
                    if isinstance(syms, list) and len(syms) > 200:
                        ev["symbols_json_sample"] = syms[:200]
                        ev["symbols_json_truncated"] = True
                        ev["symbols_json_total"] = len(syms)
                    else:
                        ev["symbols_json"] = syms
                sections.append(_section(
                    "universe_evidence",
                    "Universe Evidence",
                    f"Universe snapshot '{us.label}' linked. Symbols: {us.symbol_count}.",
                    evidence_json=ev,
                ))
            else:
                sections.append(_section(
                    "universe_evidence",
                    "Universe Evidence",
                    "Universe snapshot ID set but record not found.",
                    severity="low",
                ))
                missing.append(RunReplayMissingEvidenceData(
                    evidence_type="universe_snapshot",
                    severity="low",
                    suggested_action="Re-link the universe snapshot — the referenced record is missing.",
                ))
        else:
            sections.append(_section(
                "universe_evidence",
                "Universe Evidence",
                "No universe snapshot linked to this run.",
                severity="low",
            ))
            missing.append(RunReplayMissingEvidenceData(
                evidence_type="universe_snapshot",
                severity="low",
                suggested_action="Link a universe snapshot to improve run reproducibility.",
            ))
    except Exception as exc:
        sections.append(_section(
            "universe_evidence",
            "Universe Evidence",
            f"Universe evidence unavailable: {exc}",
        ))

    # --- 7. backtest_audit ---
    try:
        audits = (
            db.query(BacktestAudit)
            .filter(BacktestAudit.strategy_run_id == run.id)
            .order_by(BacktestAudit.created_at.desc())
            .all()
        )
        if audits:
            _state["has_audit"] = True
            latest = audits[0]

            # Derive fragility levels from JSON blobs
            cost_fragility_level: str | None = None
            fill_realism_level: str | None = None
            if isinstance(latest.fragility_summary_json, dict):
                cost_fragility_level = latest.fragility_summary_json.get("fragility_level")
            if isinstance(latest.fill_realism_json, dict):
                fill_realism_level = latest.fill_realism_json.get("fragility_level")

            # Largest penalty category
            largest_penalty_cat: str | None = None
            if isinstance(latest.penalty_attribution_json, dict):
                largest_penalty_cat = latest.penalty_attribution_json.get("largest_penalty_category")

            # First 5 improvement checks
            improvement_checks: list[str] = []
            if isinstance(latest.improvement_checks_json, list):
                improvement_checks = [
                    str(c) for c in latest.improvement_checks_json[:5]
                ]
            elif isinstance(latest.improvement_checks_json, dict):
                items = latest.improvement_checks_json.get("checks", [])
                improvement_checks = [str(c) for c in items[:5]]

            # Issue summary
            all_issues = (
                db.query(BacktestIssue)
                .filter(BacktestIssue.backtest_audit_id == latest.id)
                .all()
            )
            issue_count = len(all_issues)
            issue_severity_counts: dict[str, int] = {}
            for iss in all_issues:
                issue_severity_counts[iss.severity] = issue_severity_counts.get(iss.severity, 0) + 1
            top_issue_titles = [iss.title for iss in all_issues[:10]]

            trust_sev = (
                "high" if latest.trust_score < 50
                else "medium" if latest.trust_score < 70
                else None
            )
            ev = {
                "audit_id": str(latest.id),
                "trust_score": latest.trust_score,
                "overall_status": latest.overall_status,
                "lookahead_risk_score": latest.lookahead_risk_score,
                "cost_realism_score": latest.cost_realism_score,
                "fill_realism_score": latest.fill_realism_score,
                "liquidity_realism_score": latest.liquidity_realism_score,
                "borrow_realism_score": latest.borrow_realism_score,
                "data_quality_score": latest.data_quality_score,
                "cost_fragility_level": cost_fragility_level,
                "fill_realism_level": fill_realism_level,
                "largest_penalty_category": largest_penalty_cat,
                "improvement_checks_preview": improvement_checks,
                "issue_count": issue_count,
                "issue_severity_counts": issue_severity_counts,
                "top_issue_titles": top_issue_titles,
                "total_audits_for_run": len(audits),
            }
            sections.append(_section(
                "backtest_audit",
                "Backtest Audit",
                (
                    f"Trust score: {latest.trust_score}/100 ({latest.overall_status}). "
                    f"Issues: {issue_count}."
                ),
                severity=trust_sev,
                evidence_json=ev,
            ))
        else:
            sections.append(_section(
                "backtest_audit",
                "Backtest Audit",
                "No backtest audit found for this run.",
                severity="high",
            ))
            missing.append(RunReplayMissingEvidenceData(
                evidence_type="backtest_audit",
                severity="high",
                suggested_action="No backtest audit for this run. Run Backtest Reality Check to generate an audit.",
            ))
    except Exception as exc:
        sections.append(_section(
            "backtest_audit",
            "Backtest Audit",
            f"Backtest audit data unavailable: {exc}",
        ))

    # --- 8. computed_context ---
    try:
        ctx_ev: dict[str, Any] = {}
        ctx_summaries: list[str] = []
        ctx_worst_sev: str | None = None

        # Reliability score
        try:
            from app.models.strategy_reliability_score import StrategyReliabilityScore
            score = (
                db.query(StrategyReliabilityScore)
                .filter(StrategyReliabilityScore.strategy_id == strategy.id)
                .order_by(StrategyReliabilityScore.generated_at.desc())
                .first()
            )
            if score:
                ctx_ev["reliability"] = {
                    "overall_score": score.overall_score,
                    "status": score.status,
                    "generated_at": str(score.generated_at) if score.generated_at else None,
                }
                ctx_summaries.append(
                    f"Reliability: {score.overall_score:.1f}/100 ({score.status})."
                )
                if score.status in ("weak",) and score.overall_score is not None and score.overall_score < 35:
                    ctx_worst_sev = "high"
                elif score.status in ("weak", "review") and ctx_worst_sev is None:
                    ctx_worst_sev = "medium"
        except Exception:
            pass

        # Readiness
        if _HAS_READINESS:
            try:
                readiness = compute_strategy_readiness(strategy.id, db)
                verdict = getattr(readiness, "readiness_verdict", None)
                ctx_ev["readiness"] = {
                    "readiness_verdict": verdict,
                    "readiness_score": getattr(readiness, "readiness_score", None),
                }
                ctx_summaries.append(f"Readiness: {verdict or 'N/A'}.")
                if verdict and verdict not in ("ready", "promoted"):
                    _state["readiness_not_ready"] = True
            except Exception:
                pass

        # Evidence freshness
        if _HAS_FRESHNESS:
            try:
                freshness = compute_evidence_freshness(strategy.id, db)
                freshness_status = getattr(freshness, "freshness_status", None)
                stale_count = getattr(freshness, "stale_count", None)
                ctx_ev["freshness"] = {
                    "freshness_status": freshness_status,
                    "stale_count": stale_count,
                }
                ctx_summaries.append(
                    f"Evidence freshness: {freshness_status or 'N/A'} "
                    f"(stale items: {stale_count or 0})."
                )
            except Exception:
                pass

        # Drift
        if _HAS_DRIFT:
            try:
                drift = compute_strategy_drift(strategy.id, db)
                drift_status = getattr(drift, "drift_status", None)
                drift_score = getattr(drift, "drift_score", None)
                ctx_ev["drift"] = {
                    "drift_status": drift_status,
                    "drift_score": drift_score,
                }
                ctx_summaries.append(f"Drift: {drift_status or 'N/A'}.")
            except Exception:
                pass

        # Shadow production monitor
        if _HAS_SHADOW:
            try:
                shadow = compute_shadow_production_monitor(strategy.id, db)
                monitor_status = getattr(shadow, "monitor_status", None)
                ctx_ev["shadow_monitor"] = {"monitor_status": monitor_status}
                ctx_summaries.append(f"Shadow monitor: {monitor_status or 'N/A'}.")
            except Exception:
                pass

        # Assumption health
        if _HAS_ASSUMPTION:
            try:
                ah = compute_assumption_health(strategy.id, db)
                ah_status = ah.get("status")
                ah_score = ah.get("overall_assumption_score")
                ctx_ev["assumption_health"] = {
                    "status": ah_status,
                    "overall_assumption_score": ah_score,
                }
                ctx_summaries.append(
                    f"Assumption health: {ah_status or 'N/A'} "
                    f"(score: {ah_score or 'N/A'})."
                )
            except Exception:
                pass

        summary_str = (
            " ".join(ctx_summaries)
            if ctx_summaries
            else "Computed context unavailable — all context services failed or are not configured."
        )

        sections.append(_section(
            "computed_context",
            "Computed Context",
            summary_str,
            severity=ctx_worst_sev,
            evidence_json=ctx_ev,
        ))
    except Exception as exc:
        sections.append(_section(
            "computed_context",
            "Computed Context",
            f"Computed context unavailable: {exc}",
        ))

    # --- 9. alerts_and_reports ---
    try:
        open_alerts = (
            db.query(Alert)
            .filter(
                Alert.strategy_id == str(strategy.id),
                Alert.status == "open",
            )
            .order_by(Alert.triggered_at.desc())
            .limit(20)
            .all()
        )
        reports = (
            db.query(Report)
            .filter(Report.strategy_id == strategy.id)
            .order_by(Report.generated_at.desc())
            .limit(10)
            .all()
        )
        hc_alert_count = sum(
            1 for a in open_alerts if a.severity in ("high", "critical")
        )
        ar_sev = (
            "high" if hc_alert_count > 0
            else "medium" if len(open_alerts) > 0
            else None
        )
        ev = {
            "open_alert_count": len(open_alerts),
            "high_critical_alert_count": hc_alert_count,
            "alerts": [
                {
                    "title": a.title,
                    "severity": a.severity,
                    "triggered_at": str(a.triggered_at) if a.triggered_at else None,
                }
                for a in open_alerts
            ],
            "report_count": len(reports),
            "reports": [
                {
                    "title": r.title,
                    "report_type": r.report_type,
                    "score": r.score,
                    "generated_at": str(r.generated_at) if r.generated_at else None,
                }
                for r in reports
            ],
        }
        sections.append(_section(
            "alerts_and_reports",
            "Alerts and Reports",
            (
                f"Open alerts: {len(open_alerts)} "
                f"({hc_alert_count} high/critical). "
                f"Reports on file: {len(reports)}."
            ),
            severity=ar_sev,
            evidence_json=ev,
        ))
        if hc_alert_count > 0:
            missing.append(RunReplayMissingEvidenceData(
                evidence_type="open_high_critical_alerts",
                severity="high",
                suggested_action=(
                    f"Resolve {hc_alert_count} open high/critical alert(s) before considering this run complete."
                ),
            ))
    except Exception as exc:
        sections.append(_section(
            "alerts_and_reports",
            "Alerts and Reports",
            f"Alerts and reports data unavailable: {exc}",
        ))

    # --- 10. timeline_context ---
    try:
        run_created = run.created_at
        if run_created is not None and run_created.tzinfo is None:
            run_created = run_created.replace(tzinfo=timezone.utc)

        # Events linked directly to this run by source_id
        run_events = (
            db.query(AuditTimelineEvent)
            .filter(
                AuditTimelineEvent.strategy_id == str(strategy.id),
                AuditTimelineEvent.source_id == str(run.id),
            )
            .order_by(AuditTimelineEvent.event_time.desc())
            .limit(50)
            .all()
        )

        # Supplement with events within 7 days of run creation if needed
        nearby_events: list[Any] = []
        if len(run_events) < 50 and run_created is not None:
            window_start = run_created - timedelta(days=7)
            window_end = run_created + timedelta(days=7)
            nearby_events = (
                db.query(AuditTimelineEvent)
                .filter(
                    AuditTimelineEvent.strategy_id == str(strategy.id),
                    AuditTimelineEvent.event_time >= window_start,
                    AuditTimelineEvent.event_time <= window_end,
                )
                .order_by(AuditTimelineEvent.event_time.desc())
                .limit(50)
                .all()
            )

        # Merge and deduplicate, preserving order
        seen_ids: set[str] = set()
        all_events: list[Any] = []
        for ev_obj in run_events + nearby_events:
            eid = str(ev_obj.id)
            if eid not in seen_ids:
                seen_ids.add(eid)
                all_events.append(ev_obj)
        all_events = all_events[:50]

        tl_sev = None if all_events else "low"
        ev = {
            "event_count": len(all_events),
            "events": [
                {
                    "event_type": e.event_type,
                    "title": e.title,
                    "severity": e.severity,
                    "event_time": str(e.event_time) if e.event_time else None,
                    "source_type": e.source_type,
                    "source_id": e.source_id,
                }
                for e in all_events
            ],
        }
        sections.append(_section(
            "timeline_context",
            "Timeline Context",
            (
                f"{len(all_events)} timeline event(s) found near this run."
                if all_events
                else "No timeline events found for this run."
            ),
            severity=tl_sev,
            evidence_json=ev,
        ))
        if not all_events:
            missing.append(RunReplayMissingEvidenceData(
                evidence_type="timeline_events",
                severity="low",
                suggested_action="No timeline events near this run. Log key events to improve audit trail.",
            ))
    except Exception as exc:
        sections.append(_section(
            "timeline_context",
            "Timeline Context",
            f"Timeline context unavailable: {exc}",
        ))

    # --- Build suggested_review_checks ---
    seen_checks: set[str] = set()

    def _add_check(c: str) -> None:
        if c not in seen_checks:
            seen_checks.add(c)
            checks.append(c)

    if _state["config_found"]:
        _add_check("Confirm run assumptions match the linked config snapshot.")

    dataset_health = _state["dataset_health"]
    if dataset_health is not None and dataset_health < 75:
        _add_check("Review dataset health score before relying on this backtest.")

    signal_quality = _state["signal_quality"]
    if signal_quality is not None and signal_quality < 75:
        _add_check("Inspect signal quality drill-down — signal quality is below 75.")

    if not _state["has_audit"]:
        _add_check("Run Backtest Reality Check — no audit exists for this run.")

    _add_check("Run Regression Test Suite against the previous accepted run.")

    if _state["readiness_not_ready"]:
        _add_check("Evaluate Promotion Gates before advancing this strategy.")

    high_missing_count = sum(1 for m in missing if m.severity == "high")
    if high_missing_count > 1:
        _add_check("Generate Review Cases if multiple high-severity findings are present.")

    return sections, missing, checks


# ---------------------------------------------------------------------------
# Completeness scoring
# ---------------------------------------------------------------------------


def _compute_replay_score(
    sections: list[RunReplaySectionData],
    missing_evidence: list[RunReplayMissingEvidenceData],
) -> tuple[float, str]:
    """Compute a deterministic replay completeness score (0–100) and status label."""
    score = 0.0

    section_map = {s.section_key: s for s in sections}

    # Run + strategy version evidence: 20 pts
    run_sec = section_map.get("run_identity")
    sv_sec = section_map.get("strategy_version")
    run_ok = run_sec is not None and run_sec.severity not in ("high", "critical")
    sv_ok = sv_sec is not None and sv_sec.severity not in ("high", "critical")
    if run_ok:
        score += 10.0
    if sv_ok:
        score += 10.0

    # Config evidence: 10 pts
    missing_types = {m.evidence_type for m in missing_evidence}
    if "config_snapshot" not in missing_types:
        score += 10.0

    # Dataset/signal/universe evidence: 30 pts (10 each)
    for ev_type, section_key in (
        ("dataset_snapshot", "dataset_evidence"),
        ("signal_snapshot", "signal_evidence"),
        ("universe_snapshot", "universe_evidence"),
    ):
        sec = section_map.get(section_key)
        if ev_type not in missing_types and sec is not None and sec.severity not in ("high", "critical"):
            score += 10.0
        elif ev_type not in missing_types and sec is not None:
            score += 5.0  # partial credit even if severity is medium

    # Audit/reliability/readiness: 25 pts
    audit_sec = section_map.get("backtest_audit")
    if "backtest_audit" not in missing_types and audit_sec is not None and audit_sec.severity not in ("high",):
        score += 10.0
    elif "backtest_audit" not in missing_types and audit_sec is not None:
        score += 5.0

    ctx_sec = section_map.get("computed_context")
    if ctx_sec is not None and ctx_sec.evidence_json:
        # Partial credit based on how many context fields are populated
        ctx_fields = len(ctx_sec.evidence_json)
        score += min(15.0, ctx_fields * 3.0)

    # Timeline/alerts/reports: 15 pts
    tl_sec = section_map.get("timeline_context")
    if tl_sec is not None and tl_sec.evidence_json.get("event_count", 0) > 0:
        score += 10.0

    ar_sec = section_map.get("alerts_and_reports")
    if ar_sec is not None and ar_sec.evidence_json:
        score += 5.0

    score = max(0.0, min(100.0, score))

    if score >= 85:
        status = "complete"
    elif score >= 65:
        status = "review"
    elif score >= 40:
        status = "incomplete"
    else:
        status = "sparse"

    return score, status


# ---------------------------------------------------------------------------
# Markdown generator
# ---------------------------------------------------------------------------


def _generate_markdown(
    strategy: Any,
    run: Any,
    sections: list[RunReplaySectionData],
    missing_evidence: list[RunReplayMissingEvidenceData],
    suggested_checks: list[str],
    replay_status: str,
    replay_score: float,
) -> str:
    import json as _json

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    lines: list[str] = []

    lines.append("# QuantFidelity Run Replay Pack")
    lines.append("")
    lines.append(
        f"**Strategy:** {strategy.name} | "
        f"**Run:** {run.run_name} | "
        f"**Type:** {run.run_type}"
    )
    lines.append(
        f"**Generated:** {generated_at} | "
        f"**Completeness:** {replay_score:.0f}/100 ({replay_status})"
    )
    lines.append("")
    lines.append(
        "> This replay pack reconstructs logged QuantFidelity evidence only. "
        "It is not broker or order execution replay, trade reconstruction, or investment advice."
    )
    lines.append(
        "> Deterministic — based solely on evidence logged in QuantFidelity. "
        "No AI was used in generating this document."
    )
    lines.append("")
    lines.append("---")
    lines.append("")

    # Sections
    sev_labels = {
        "critical": "CRITICAL",
        "high": "HIGH SEVERITY",
        "medium": "REVIEW REQUIRED",
        "low": "ATTENTION",
    }
    for i, sec in enumerate(sections, 1):
        lines.append(f"## {i}. {sec.title}")
        lines.append("")
        if sec.severity and sec.severity in sev_labels:
            lines.append(f"**[{sev_labels[sec.severity]}]** {sec.summary}")
        else:
            lines.append(sec.summary)
        lines.append("")
        if sec.evidence_json:
            lines.append("```json")
            lines.append(_json.dumps(sec.evidence_json, indent=2, default=str))
            lines.append("```")
            lines.append("")

    # Missing evidence
    if missing_evidence:
        lines.append("---")
        lines.append("")
        lines.append("## Missing Evidence")
        lines.append("")
        for me in missing_evidence:
            sev_label = me.severity.upper()
            lines.append(f"- **[{sev_label}]** `{me.evidence_type}`: {me.suggested_action}")
        lines.append("")

    # Suggested review checks
    if suggested_checks:
        lines.append("---")
        lines.append("")
        lines.append("## Suggested Review Checks")
        lines.append("")
        for chk in suggested_checks:
            lines.append(f"- {chk}")
        lines.append("")

    # Notes and limitations
    lines.append("---")
    lines.append("")
    lines.append("## Notes and Limitations")
    lines.append("")
    lines.append(
        f"- This replay pack reflects evidence logged in QuantFidelity as of {generated_at}."
    )
    lines.append("- It does not reflect live market conditions or future performance.")
    lines.append("- Completeness scores are deterministic and based on logged evidence only.")
    lines.append("- Not investment advice.")
    lines.append("- Generated by QuantFidelity M58 Run Replay Pack.")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_run_replay_pack(
    db: Session,
    strategy_id: uuid.UUID,
    run_id: uuid.UUID,
    *,
    format: str = "json",
    include_raw_json: bool = False,
) -> RunReplayData:
    """Generate a run replay pack for a single strategy run.

    Read-only — no DB writes, no AuditTimelineEvent created.

    :param db: SQLAlchemy session.
    :param strategy_id: UUID of the parent strategy.
    :param run_id: UUID of the specific run to replay.
    :param format: "json" (default) or "markdown".
    :param include_raw_json: If True, populate raw evidence blobs in sections.
    :raises ValueError: If strategy or run not found, or run belongs to wrong strategy.
    """
    from app.models.strategy import Strategy
    from app.models.strategy_run import StrategyRun

    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if strategy is None:
        raise ValueError(f"Strategy {strategy_id} not found")

    run = db.query(StrategyRun).filter(StrategyRun.id == run_id).first()
    if run is None:
        raise ValueError(f"Run {run_id} not found")

    if str(run.strategy_id) != str(strategy_id):
        raise ValueError(f"Run {run_id} does not belong to strategy {strategy_id}")

    if format not in ("json", "markdown"):
        raise ValueError(f"Invalid format: {format!r}. Must be 'json' or 'markdown'.")

    replay_id = uuid.uuid4().hex[:12]
    generated_at = datetime.now(timezone.utc)

    sections, missing_evidence, suggested_checks = _collect_run_sections(
        db, strategy, run, include_raw_json
    )

    replay_score, replay_status = _compute_replay_score(sections, missing_evidence)

    slug_or_name = strategy.slug or strategy.name
    run_name_safe = run.run_name or str(run_id)[:8]
    fmt_ext = "md" if format == "markdown" else "json"
    filename = _safe_filename(slug_or_name, run_name_safe, fmt_ext)

    content: str | None = None
    if format == "markdown":
        content = _generate_markdown(
            strategy,
            run,
            sections,
            missing_evidence,
            suggested_checks,
            replay_status,
            replay_score,
        )

    raw_evidence: dict | None = None
    if include_raw_json:
        raw_evidence = {
            sec.section_key: sec.evidence_json
            for sec in sections
            if sec.evidence_json
        }

    return RunReplayData(
        replay_id=replay_id,
        generated_at=generated_at,
        format=format,
        strategy_id=str(strategy_id),
        run_id=str(run_id),
        filename=filename,
        deterministic_note=(
            "Deterministic replay based solely on evidence logged in QuantFidelity. "
            "No AI was used."
        ),
        no_execution_replay_note=(
            "This is not broker or order execution replay. "
            "It does not reconstruct trades, orders, or fills. "
            "Not investment advice."
        ),
        replay_status=replay_status,
        replay_completeness_score=replay_score,
        sections=sections,
        missing_evidence=missing_evidence,
        suggested_review_checks=suggested_checks,
        content=content,
        raw_evidence=raw_evidence,
    )
