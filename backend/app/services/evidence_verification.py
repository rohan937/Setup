"""Evidence Verification Service (M92).

Verifies evidence consistency for a strategy by checking linked snapshots,
content hashes, time ordering, and link completeness.

Language policy: use "time-consistency issue" and "verification warning" —
never "fraud" or "falsified".
"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.backtest_audit import BacktestAudit
from app.models.strategy import Strategy
from app.models.strategy_config_snapshot import StrategyConfigSnapshot
from app.models.strategy_run import StrategyRun

# ---------------------------------------------------------------------------
# Disclaimer
# ---------------------------------------------------------------------------

DISCLAIMER = (
    "Evidence verification checks research evidence consistency. "
    "It is not trading advice."
)


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class EvidenceVerificationCheck:
    key: str
    title: str
    status: str  # pass | warning | fail | missing
    severity: str  # low | medium | high | critical
    evidence_type: str
    evidence_id: str | None
    explanation: str
    recommended_fix: str | None


@dataclass
class EvidenceChainNode:
    evidence_type: str
    evidence_id: str
    label: str | None
    content_hash: str
    created_at: datetime | None


@dataclass
class EvidenceVerificationData:
    strategy_id: uuid.UUID
    strategy_name: str
    generated_at: datetime
    verification_score: float  # 0–100
    verdict: str  # verified | review | warning | failed | insufficient_data
    chain_status: str  # intact | warning | broken | insufficient_data
    root_hash: str | None
    checks: list[EvidenceVerificationCheck]
    tamper_warnings: list[str]
    time_consistency_warnings: list[str]
    link_consistency_warnings: list[str]
    suggested_actions: list[str]
    disclaimer: str


# ---------------------------------------------------------------------------
# Fingerprint helper
# ---------------------------------------------------------------------------


def _canonical_json(obj) -> str:
    """Return a deterministic JSON string for the given object."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def compute_evidence_fingerprint(evidence_type: str, obj) -> str:
    """Return a deterministic SHA-256 hex fingerprint for an evidence object.

    Reuses existing hash fields where available to ensure consistency with
    hashes stored in the database.
    """
    if evidence_type == "config_snapshot":
        if getattr(obj, "config_hash", None):
            return obj.config_hash
        raw = (getattr(obj, "label", "") or "") + _canonical_json(
            getattr(obj, "config_json", {}) or {}
        )
        return hashlib.sha256(raw.encode()).hexdigest()

    if evidence_type == "universe_snapshot":
        if getattr(obj, "universe_hash", None):
            return obj.universe_hash
        raw = _canonical_json(getattr(obj, "symbols_json", []) or [])
        return hashlib.sha256(raw.encode()).hexdigest()

    if evidence_type == "signal_snapshot":
        if getattr(obj, "signal_hash", None):
            return obj.signal_hash
        raw = _canonical_json(getattr(obj, "rows_json", []) or [])
        return hashlib.sha256(raw.encode()).hexdigest()

    if evidence_type == "dataset_snapshot":
        raw = (
            "dataset_snapshot:"
            + str(getattr(obj, "id", ""))
            + ":"
            + str(getattr(obj, "row_count", 0))
        )
        return hashlib.sha256(raw.encode()).hexdigest()

    if evidence_type == "strategy_run":
        metrics = getattr(obj, "metrics_json", None) or {}
        raw_parts = [
            str(getattr(obj, "run_name", "")),
            str(getattr(obj, "run_type", "")),
            str(getattr(obj, "created_at", "")),
            str(getattr(obj, "dataset_snapshot_id", "")),
            str(getattr(obj, "universe_snapshot_id", "")),
            str(getattr(obj, "signal_snapshot_id", "")),
            str(getattr(obj, "strategy_version_id", "")),
            _canonical_json(metrics),
        ]
        return hashlib.sha256("|".join(raw_parts).encode()).hexdigest()

    if evidence_type == "strategy_version":
        version_label = getattr(obj, "version_label", "") or ""
        git_commit = getattr(obj, "git_commit", None) or "none"
        raw = "version:" + version_label + ":" + git_commit
        return hashlib.sha256(raw.encode()).hexdigest()

    # Fallback: hash the repr
    return hashlib.sha256(repr(obj).encode()).hexdigest()


# ---------------------------------------------------------------------------
# Core verification function
# ---------------------------------------------------------------------------


def verify_strategy_evidence(
    strategy_id: uuid.UUID, db: Session
) -> EvidenceVerificationData:
    """Run all evidence consistency checks for the given strategy.

    Returns an EvidenceVerificationData dataclass with checks, score, verdict,
    chain status, and structured warning lists.
    """
    now = datetime.now(timezone.utc)
    checks: list[EvidenceVerificationCheck] = []
    chain_nodes: list[EvidenceChainNode] = []
    time_consistency_warnings: list[str] = []
    link_consistency_warnings: list[str] = []
    tamper_warnings: list[str] = []
    suggested_actions: list[str] = []

    # ------------------------------------------------------------------
    # Load strategy
    # ------------------------------------------------------------------
    strategy = db.get(Strategy, strategy_id)
    strategy_name = strategy.name if strategy else str(strategy_id)

    # ------------------------------------------------------------------
    # Load runs (latest 20, ordered newest first)
    # ------------------------------------------------------------------
    runs: list[StrategyRun] = (
        db.query(StrategyRun)
        .filter(StrategyRun.strategy_id == strategy_id)
        .order_by(StrategyRun.created_at.desc())
        .limit(20)
        .all()
    )

    if not runs:
        return EvidenceVerificationData(
            strategy_id=strategy_id,
            strategy_name=strategy_name,
            generated_at=now,
            verification_score=0.0,
            verdict="insufficient_data",
            chain_status="insufficient_data",
            root_hash=None,
            checks=[
                EvidenceVerificationCheck(
                    key="no_runs",
                    title="No Strategy Runs Found",
                    status="missing",
                    severity="critical",
                    evidence_type="strategy_run",
                    evidence_id=None,
                    explanation="No strategy runs are recorded for this strategy.",
                    recommended_fix="Log at least one backtest run to enable evidence verification.",
                )
            ],
            tamper_warnings=[],
            time_consistency_warnings=[],
            link_consistency_warnings=["No strategy runs found — cannot verify evidence chain."],
            suggested_actions=["Log a backtest run with linked dataset, universe, and signal snapshots."],
            disclaimer=DISCLAIMER,
        )

    # ------------------------------------------------------------------
    # Pick primary run: prefer latest backtest, fallback to any latest
    # ------------------------------------------------------------------
    primary_run: StrategyRun | None = None
    for run in runs:
        if run.run_type == "backtest":
            primary_run = run
            break
    if primary_run is None:
        primary_run = runs[0]

    run_created_at = primary_run.created_at

    # ------------------------------------------------------------------
    # Add the primary run itself as a chain node
    # ------------------------------------------------------------------
    run_fingerprint = compute_evidence_fingerprint("strategy_run", primary_run)
    chain_nodes.append(
        EvidenceChainNode(
            evidence_type="strategy_run",
            evidence_id=str(primary_run.id),
            label=primary_run.run_name,
            content_hash=run_fingerprint,
            created_at=run_created_at,
        )
    )

    # ------------------------------------------------------------------
    # Helper: time-ordering check
    # ------------------------------------------------------------------
    def _check_time_order(
        snap_created_at: datetime | None,
        snap_type: str,
        snap_id: str,
        snap_label: str,
    ) -> None:
        if snap_created_at is None or run_created_at is None:
            return
        # Ensure both are timezone-aware for comparison
        snap_ts = snap_created_at
        run_ts = run_created_at
        if snap_ts.tzinfo is None:
            snap_ts = snap_ts.replace(tzinfo=timezone.utc)
        if run_ts.tzinfo is None:
            run_ts = run_ts.replace(tzinfo=timezone.utc)
        if snap_ts > run_ts:
            delta_hours = (snap_ts - run_ts).total_seconds() / 3600
            msg = (
                f"{snap_type} '{snap_label}' (id={snap_id}) was created "
                f"{delta_hours:.1f} hours after the run timestamp — time-consistency issue."
            )
            time_consistency_warnings.append(msg)
            checks.append(
                EvidenceVerificationCheck(
                    key=f"time_order_{snap_type}_{snap_id[:8]}",
                    title=f"Time-Consistency Issue: {snap_type}",
                    status="warning",
                    severity="high",
                    evidence_type=snap_type,
                    evidence_id=snap_id,
                    explanation=msg,
                    recommended_fix=(
                        f"Confirm that the {snap_type} was recorded before or during the run. "
                        "Re-link with a correctly dated snapshot if needed."
                    ),
                )
            )

    # ------------------------------------------------------------------
    # Check strategy_version link
    # ------------------------------------------------------------------
    if primary_run.strategy_version_id and primary_run.strategy_version:
        sv = primary_run.strategy_version
        sv_fp = compute_evidence_fingerprint("strategy_version", sv)
        chain_nodes.append(
            EvidenceChainNode(
                evidence_type="strategy_version",
                evidence_id=str(sv.id),
                label=sv.version_label,
                content_hash=sv_fp,
                created_at=getattr(sv, "created_at", None),
            )
        )
        _check_time_order(
            getattr(sv, "created_at", None),
            "strategy_version",
            str(sv.id),
            sv.version_label,
        )
        checks.append(
            EvidenceVerificationCheck(
                key="strategy_version_linked",
                title="Strategy Version Linked",
                status="pass",
                severity="low",
                evidence_type="strategy_version",
                evidence_id=str(sv.id),
                explanation=f"Run is linked to strategy version '{sv.version_label}'.",
                recommended_fix=None,
            )
        )
    else:
        link_consistency_warnings.append(
            "Primary run has no linked strategy version — version provenance is unverifiable."
        )
        checks.append(
            EvidenceVerificationCheck(
                key="strategy_version_missing",
                title="Strategy Version Not Linked",
                status="warning",
                severity="medium",
                evidence_type="strategy_version",
                evidence_id=None,
                explanation="The primary run does not reference a strategy version.",
                recommended_fix="Link the run to a strategy version for full provenance tracking.",
            )
        )
        suggested_actions.append("Link the primary run to a strategy version.")

    # ------------------------------------------------------------------
    # Check dataset_snapshot link
    # ------------------------------------------------------------------
    if primary_run.dataset_snapshot_id and primary_run.snapshot:
        ds = primary_run.snapshot
        ds_fp = compute_evidence_fingerprint("dataset_snapshot", ds)
        chain_nodes.append(
            EvidenceChainNode(
                evidence_type="dataset_snapshot",
                evidence_id=str(ds.id),
                label=getattr(ds, "version_label", None),
                content_hash=ds_fp,
                created_at=getattr(ds, "created_at", None),
            )
        )
        _check_time_order(
            getattr(ds, "created_at", None),
            "dataset_snapshot",
            str(ds.id),
            getattr(ds, "version_label", str(ds.id)),
        )
        checks.append(
            EvidenceVerificationCheck(
                key="dataset_snapshot_linked",
                title="Dataset Snapshot Linked",
                status="pass",
                severity="low",
                evidence_type="dataset_snapshot",
                evidence_id=str(ds.id),
                explanation=(
                    f"Run is linked to dataset snapshot '{getattr(ds, 'version_label', ds.id)}' "
                    f"with {getattr(ds, 'row_count', 0)} rows."
                ),
                recommended_fix=None,
            )
        )
    else:
        link_consistency_warnings.append(
            "Primary run has no linked dataset snapshot — data provenance cannot be verified."
        )
        checks.append(
            EvidenceVerificationCheck(
                key="dataset_snapshot_missing",
                title="Dataset Snapshot Not Linked",
                status="fail",
                severity="high",
                evidence_type="dataset_snapshot",
                evidence_id=None,
                explanation="The primary run does not reference a dataset snapshot.",
                recommended_fix="Upload and link a dataset snapshot to establish data provenance.",
            )
        )
        suggested_actions.append("Link the primary run to a dataset snapshot.")

    # ------------------------------------------------------------------
    # Check universe_snapshot link
    # ------------------------------------------------------------------
    if primary_run.universe_snapshot_id and primary_run.universe_snapshot:
        us = primary_run.universe_snapshot
        us_fp = compute_evidence_fingerprint("universe_snapshot", us)
        chain_nodes.append(
            EvidenceChainNode(
                evidence_type="universe_snapshot",
                evidence_id=str(us.id),
                label=getattr(us, "label", None),
                content_hash=us_fp,
                created_at=getattr(us, "created_at", None),
            )
        )
        _check_time_order(
            getattr(us, "created_at", None),
            "universe_snapshot",
            str(us.id),
            getattr(us, "label", str(us.id)),
        )
        checks.append(
            EvidenceVerificationCheck(
                key="universe_snapshot_linked",
                title="Universe Snapshot Linked",
                status="pass",
                severity="low",
                evidence_type="universe_snapshot",
                evidence_id=str(us.id),
                explanation=(
                    f"Run is linked to universe snapshot '{getattr(us, 'label', us.id)}' "
                    f"with {getattr(us, 'symbol_count', 0)} symbols."
                ),
                recommended_fix=None,
            )
        )
    else:
        link_consistency_warnings.append(
            "Primary run has no linked universe snapshot — universe provenance cannot be verified."
        )
        checks.append(
            EvidenceVerificationCheck(
                key="universe_snapshot_missing",
                title="Universe Snapshot Not Linked",
                status="fail",
                severity="high",
                evidence_type="universe_snapshot",
                evidence_id=None,
                explanation="The primary run does not reference a universe snapshot.",
                recommended_fix="Upload and link a universe snapshot to establish universe provenance.",
            )
        )
        suggested_actions.append("Link the primary run to a universe snapshot.")

    # ------------------------------------------------------------------
    # Check signal_snapshot link
    # ------------------------------------------------------------------
    if primary_run.signal_snapshot_id and primary_run.signal_snapshot:
        ss = primary_run.signal_snapshot
        ss_fp = compute_evidence_fingerprint("signal_snapshot", ss)
        chain_nodes.append(
            EvidenceChainNode(
                evidence_type="signal_snapshot",
                evidence_id=str(ss.id),
                label=getattr(ss, "label", None),
                content_hash=ss_fp,
                created_at=getattr(ss, "created_at", None),
            )
        )
        _check_time_order(
            getattr(ss, "created_at", None),
            "signal_snapshot",
            str(ss.id),
            getattr(ss, "label", str(ss.id)),
        )
        checks.append(
            EvidenceVerificationCheck(
                key="signal_snapshot_linked",
                title="Signal Snapshot Linked",
                status="pass",
                severity="low",
                evidence_type="signal_snapshot",
                evidence_id=str(ss.id),
                explanation=(
                    f"Run is linked to signal snapshot '{getattr(ss, 'label', ss.id)}' "
                    f"with {getattr(ss, 'row_count', 0)} rows."
                ),
                recommended_fix=None,
            )
        )
    else:
        link_consistency_warnings.append(
            "Primary run has no linked signal snapshot — signal provenance is unverifiable."
        )
        checks.append(
            EvidenceVerificationCheck(
                key="signal_snapshot_missing",
                title="Signal Snapshot Not Linked",
                status="warning",
                severity="medium",
                evidence_type="signal_snapshot",
                evidence_id=None,
                explanation="The primary run does not reference a signal snapshot.",
                recommended_fix="Upload and link a signal snapshot for complete evidence coverage.",
            )
        )
        suggested_actions.append("Link the primary run to a signal snapshot.")

    # ------------------------------------------------------------------
    # Config snapshot via strategy_version
    # ------------------------------------------------------------------
    config_snapshot: StrategyConfigSnapshot | None = None
    if primary_run.strategy_version_id:
        config_snapshot = (
            db.query(StrategyConfigSnapshot)
            .filter(
                StrategyConfigSnapshot.strategy_version_id
                == primary_run.strategy_version_id
            )
            .order_by(StrategyConfigSnapshot.created_at.desc())
            .first()
        )
    if config_snapshot is None:
        # Fall back to any config snapshot for this strategy
        config_snapshot = (
            db.query(StrategyConfigSnapshot)
            .filter(StrategyConfigSnapshot.strategy_id == strategy_id)
            .order_by(StrategyConfigSnapshot.created_at.desc())
            .first()
        )

    if config_snapshot:
        cs_fp = compute_evidence_fingerprint("config_snapshot", config_snapshot)
        chain_nodes.append(
            EvidenceChainNode(
                evidence_type="config_snapshot",
                evidence_id=str(config_snapshot.id),
                label=config_snapshot.label,
                content_hash=cs_fp,
                created_at=config_snapshot.created_at,
            )
        )
        if config_snapshot.config_hash:
            checks.append(
                EvidenceVerificationCheck(
                    key="config_hash_present",
                    title="Config Hash Present",
                    status="pass",
                    severity="low",
                    evidence_type="config_snapshot",
                    evidence_id=str(config_snapshot.id),
                    explanation=(
                        f"Config snapshot '{config_snapshot.label}' has a stored "
                        f"content hash ({config_snapshot.config_hash[:12]}…)."
                    ),
                    recommended_fix=None,
                )
            )
        else:
            tamper_warnings.append(
                f"Config snapshot '{config_snapshot.label}' is missing a config_hash — "
                "content integrity cannot be confirmed."
            )
            checks.append(
                EvidenceVerificationCheck(
                    key="config_hash_missing",
                    title="Config Hash Missing",
                    status="warning",
                    severity="medium",
                    evidence_type="config_snapshot",
                    evidence_id=str(config_snapshot.id),
                    explanation="The config snapshot has no stored content hash.",
                    recommended_fix="Regenerate the config snapshot so that a config_hash is stored.",
                )
            )
    else:
        link_consistency_warnings.append(
            "No config snapshot found for this strategy — configuration provenance is incomplete."
        )
        checks.append(
            EvidenceVerificationCheck(
                key="config_snapshot_missing",
                title="Config Snapshot Not Found",
                status="warning",
                severity="medium",
                evidence_type="config_snapshot",
                evidence_id=None,
                explanation="No configuration snapshot is associated with this strategy.",
                recommended_fix="Log a config snapshot to record the strategy's parameter state.",
            )
        )
        suggested_actions.append("Log a config snapshot for this strategy.")

    # ------------------------------------------------------------------
    # Backtest audit check
    # ------------------------------------------------------------------
    if primary_run.run_type == "backtest":
        has_audit = bool(primary_run.backtest_audits)
        if has_audit:
            checks.append(
                EvidenceVerificationCheck(
                    key="backtest_audit_present",
                    title="Backtest Audit Present",
                    status="pass",
                    severity="low",
                    evidence_type="backtest_audit",
                    evidence_id=str(primary_run.backtest_audits[0].id),
                    explanation="The primary backtest run has an associated backtest audit record.",
                    recommended_fix=None,
                )
            )
        else:
            checks.append(
                EvidenceVerificationCheck(
                    key="backtest_audit_missing",
                    title="Backtest Audit Missing",
                    status="warning",
                    severity="medium",
                    evidence_type="backtest_audit",
                    evidence_id=None,
                    explanation="The primary backtest run has no backtest audit record.",
                    recommended_fix="Submit a backtest audit for the primary run.",
                )
            )
            suggested_actions.append("Submit a backtest audit for the primary backtest run.")
    elif primary_run.run_type in ("paper", "shadow", "live"):
        # For non-backtest runs: check that a baseline backtest run exists for the strategy
        baseline_exists = any(r.run_type == "backtest" for r in runs)
        if baseline_exists:
            checks.append(
                EvidenceVerificationCheck(
                    key="baseline_backtest_present",
                    title="Baseline Backtest Present",
                    status="pass",
                    severity="low",
                    evidence_type="strategy_run",
                    evidence_id=None,
                    explanation=f"A baseline backtest run exists for this strategy (primary run type: {primary_run.run_type}).",
                    recommended_fix=None,
                )
            )
        else:
            checks.append(
                EvidenceVerificationCheck(
                    key="baseline_backtest_missing",
                    title="Baseline Backtest Missing",
                    status="warning",
                    severity="high",
                    evidence_type="strategy_run",
                    evidence_id=None,
                    explanation=(
                        f"Primary run type is '{primary_run.run_type}' but no baseline backtest "
                        "run exists for this strategy."
                    ),
                    recommended_fix="Log a backtest run before moving to paper or live trading.",
                )
            )
            suggested_actions.append(
                "Log a baseline backtest run before conducting paper or live trading."
            )

    # ------------------------------------------------------------------
    # Symbol overlap check (signal vs universe)
    # ------------------------------------------------------------------
    if (
        primary_run.signal_snapshot_id
        and primary_run.signal_snapshot
        and primary_run.universe_snapshot_id
        and primary_run.universe_snapshot
    ):
        ss = primary_run.signal_snapshot
        us = primary_run.universe_snapshot
        signal_symbols = set(getattr(ss, "symbols_json", None) or [])
        universe_symbols = set(getattr(us, "symbols_json", None) or [])
        if signal_symbols and universe_symbols:
            overlap = signal_symbols & universe_symbols
            if not overlap:
                msg = (
                    "Signal snapshot and universe snapshot share zero symbol overlap — "
                    "the signal may not apply to the trading universe."
                )
                link_consistency_warnings.append(msg)
                checks.append(
                    EvidenceVerificationCheck(
                        key="symbol_overlap_zero",
                        title="Zero Symbol Overlap: Signal vs Universe",
                        status="warning",
                        severity="high",
                        evidence_type="signal_snapshot",
                        evidence_id=str(ss.id),
                        explanation=msg,
                        recommended_fix=(
                            "Verify that the signal snapshot targets symbols present in the "
                            "universe snapshot."
                        ),
                    )
                )
                suggested_actions.append(
                    "Check that signal symbols and universe symbols are aligned."
                )
            else:
                checks.append(
                    EvidenceVerificationCheck(
                        key="symbol_overlap_ok",
                        title="Signal/Universe Symbol Overlap",
                        status="pass",
                        severity="low",
                        evidence_type="signal_snapshot",
                        evidence_id=str(ss.id),
                        explanation=(
                            f"{len(overlap)} symbol(s) overlap between signal and universe snapshots."
                        ),
                        recommended_fix=None,
                    )
                )

    # ------------------------------------------------------------------
    # Config/run consistency: turnover/trade_count without transaction_cost_bps
    # ------------------------------------------------------------------
    metrics = primary_run.metrics_json or {}
    assumptions = primary_run.assumptions_json or {}
    config_params = {}
    if config_snapshot and config_snapshot.config_json:
        config_params = config_snapshot.config_json or {}
    has_turnover_metric = "turnover" in metrics or "trade_count" in metrics
    has_cost_model = (
        "transaction_cost_bps" in assumptions
        or "transaction_cost_bps" in config_params
        or "cost_bps" in assumptions
        or "cost_bps" in config_params
    )
    if has_turnover_metric and not has_cost_model:
        checks.append(
            EvidenceVerificationCheck(
                key="transaction_cost_missing",
                title="Transaction Cost Not Modelled",
                status="warning",
                severity="medium",
                evidence_type="strategy_run",
                evidence_id=str(primary_run.id),
                explanation=(
                    "Run records turnover/trade_count metrics but no transaction_cost_bps "
                    "assumption is present — cost impact on performance is unverifiable."
                ),
                recommended_fix=(
                    "Add a transaction_cost_bps entry to the run's assumptions_json or "
                    "config snapshot."
                ),
            )
        )
        suggested_actions.append(
            "Add transaction_cost_bps to run assumptions or config snapshot."
        )

    # ------------------------------------------------------------------
    # Compute root_hash from sorted chain node content hashes
    # ------------------------------------------------------------------
    root_hash: str | None = None
    if chain_nodes:
        sorted_hashes = sorted(n.content_hash for n in chain_nodes)
        root_hash = hashlib.sha256("|".join(sorted_hashes).encode()).hexdigest()

    # ------------------------------------------------------------------
    # Chain status
    # ------------------------------------------------------------------
    high_fails = sum(
        1
        for c in checks
        if c.status in ("fail", "warning") and c.severity in ("high", "critical")
    )
    missing_core = sum(
        1
        for c in checks
        if c.status in ("fail", "missing")
        and c.evidence_type in ("dataset_snapshot", "universe_snapshot")
    )
    time_issue_count = len(time_consistency_warnings)

    if high_fails >= 3:
        chain_status = "broken"
    elif high_fails > 0 or time_issue_count > 0:
        chain_status = "warning"
    else:
        chain_status = "intact"

    # ------------------------------------------------------------------
    # Verification score
    # ------------------------------------------------------------------
    score = 100.0
    for c in checks:
        if c.status in ("fail", "missing"):
            if c.severity == "critical":
                score -= 25
            elif c.severity == "high":
                score -= 15
            elif c.severity == "medium":
                score -= 8
            else:
                score -= 3
        elif c.status == "warning":
            if c.severity == "critical":
                score -= 25
            elif c.severity == "high":
                score -= 15
            elif c.severity == "medium":
                score -= 8
            else:
                score -= 3

    if missing_core >= 2:
        score = min(score, 60.0)
    if chain_status == "broken":
        score = min(score, 40.0)
    score = max(score, 0.0)

    # ------------------------------------------------------------------
    # Verdict
    # ------------------------------------------------------------------
    if score >= 85 and chain_status == "intact":
        verdict = "verified"
    elif score >= 70:
        verdict = "review"
    elif score >= 50:
        verdict = "warning"
    else:
        verdict = "failed"

    return EvidenceVerificationData(
        strategy_id=strategy_id,
        strategy_name=strategy_name,
        generated_at=now,
        verification_score=round(score, 2),
        verdict=verdict,
        chain_status=chain_status,
        root_hash=root_hash,
        checks=checks,
        tamper_warnings=tamper_warnings,
        time_consistency_warnings=time_consistency_warnings,
        link_consistency_warnings=link_consistency_warnings,
        suggested_actions=list(dict.fromkeys(suggested_actions)),  # deduplicate, preserve order
        disclaimer=DISCLAIMER,
    )


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def generate_evidence_verification_report(
    strategy_id: uuid.UUID,
    db: Session,
    *,
    format: str = "json",
) -> str:
    """Generate a formatted evidence verification report.

    Args:
        strategy_id: UUID of the strategy to verify.
        db: SQLAlchemy session.
        format: "json" (default) or "markdown".

    Returns:
        A string containing the report in the requested format.
    """
    data = verify_strategy_evidence(strategy_id, db)

    if format == "markdown":
        lines: list[str] = [
            f"# Evidence Verification Report",
            f"",
            f"**Strategy:** {data.strategy_name}  ",
            f"**Strategy ID:** {data.strategy_id}  ",
            f"**Generated:** {data.generated_at.isoformat()}  ",
            f"**Score:** {data.verification_score:.1f} / 100  ",
            f"**Verdict:** {data.verdict.upper()}  ",
            f"**Chain Status:** {data.chain_status}  ",
            f"**Root Hash:** {data.root_hash or 'N/A'}  ",
            f"",
            f"---",
            f"",
            f"## Checks",
            f"",
            f"| # | Key | Title | Status | Severity | Evidence Type | Explanation |",
            f"|---|-----|-------|--------|----------|---------------|-------------|",
        ]
        for i, c in enumerate(data.checks, 1):
            lines.append(
                f"| {i} | `{c.key}` | {c.title} | **{c.status}** | {c.severity} | "
                f"{c.evidence_type} | {c.explanation} |"
            )

        if data.time_consistency_warnings:
            lines += [
                "",
                "## Time-Consistency Warnings",
                "",
            ]
            for w in data.time_consistency_warnings:
                lines.append(f"- {w}")

        if data.tamper_warnings:
            lines += [
                "",
                "## Verification Warnings",
                "",
            ]
            for w in data.tamper_warnings:
                lines.append(f"- {w}")

        if data.link_consistency_warnings:
            lines += [
                "",
                "## Link Consistency Warnings",
                "",
            ]
            for w in data.link_consistency_warnings:
                lines.append(f"- {w}")

        if data.suggested_actions:
            lines += [
                "",
                "## Suggested Actions",
                "",
            ]
            for a in data.suggested_actions:
                lines.append(f"1. {a}")

        lines += [
            "",
            "---",
            "",
            f"*{data.disclaimer}*",
        ]
        return "\n".join(lines)

    # Default: JSON
    payload = {
        "strategy_id": str(data.strategy_id),
        "strategy_name": data.strategy_name,
        "generated_at": data.generated_at.isoformat(),
        "verification_score": data.verification_score,
        "verdict": data.verdict,
        "chain_status": data.chain_status,
        "root_hash": data.root_hash,
        "checks": [
            {
                "key": c.key,
                "title": c.title,
                "status": c.status,
                "severity": c.severity,
                "evidence_type": c.evidence_type,
                "evidence_id": c.evidence_id,
                "explanation": c.explanation,
                "recommended_fix": c.recommended_fix,
            }
            for c in data.checks
        ],
        "tamper_warnings": data.tamper_warnings,
        "time_consistency_warnings": data.time_consistency_warnings,
        "link_consistency_warnings": data.link_consistency_warnings,
        "suggested_actions": data.suggested_actions,
        "disclaimer": data.disclaimer,
    }
    return json.dumps(payload, indent=2, default=str)
