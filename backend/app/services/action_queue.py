"""M74 Strategy Action Queue — deterministic, evidence-derived next-actions.

Consolidates "what should I do next?" for a strategy across the evidence
lifecycle (evidence linkage, readiness, governance setup, freshness,
assumptions, reporting). Computed live from existing data and services — no
new persistence, no AI, no trading recommendations.

Robustness: every enrichment source is wrapped in try/except so a single
broken subsystem cannot break the queue. The reliable DB-existence checks form
the backbone; the heavier compute services add detail when available.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

# ---------------------------------------------------------------------------
# Ranking tables
# ---------------------------------------------------------------------------

_SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
_STATUS_RANK = {"blocked": 0, "pending": 1, "optional": 2, "done": 3}
# Lower = surfaced earlier when severity/status tie.
_CATEGORY_RANK = {
    "readiness": 0,
    "governance": 1,
    "freshness": 2,
    "assumptions": 2,
    "run_quality": 3,
    "evidence": 3,
    "shadow": 4,
    "developer": 5,
    "reporting": 6,
}

_DEFAULT_LIMIT = 10


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class _Item:
    """Mutable internal action item with a dedup key + accumulating reasons."""

    def __init__(
        self,
        *,
        dedup_key: str,
        title: str,
        description: str,
        why_it_matters: str,
        severity: str,
        status: str,
        category: str,
        source: str,
        action_label: str,
        action_type: str,
        target_tab: str | None = None,
        target_panel_label: str | None = None,
        related_object_id: str | None = None,
        related_object_type: str | None = None,
        deterministic_reason: str,
    ) -> None:
        self.dedup_key = dedup_key
        self.title = title
        self.description = description
        self.why_it_matters = why_it_matters
        self.severity = severity
        self.status = status
        self.category = category
        self.source = source
        self.action_label = action_label
        self.action_type = action_type
        self.target_tab = target_tab
        self.target_panel_label = target_panel_label
        self.related_object_id = related_object_id
        self.related_object_type = related_object_type
        self.deterministic_reason = deterministic_reason
        self.created_from: list[str] = [source]

    def merge(self, other: "_Item") -> None:
        """Merge another item that points at the same underlying issue."""
        # Keep the more severe one's severity.
        if _SEVERITY_RANK[other.severity] < _SEVERITY_RANK[self.severity]:
            self.severity = other.severity
        if _STATUS_RANK.get(other.status, 9) < _STATUS_RANK.get(self.status, 9):
            self.status = other.status
        for src in other.created_from:
            if src not in self.created_from:
                self.created_from.append(src)
        # Append the other source's reason if distinct.
        if other.deterministic_reason and other.deterministic_reason not in self.deterministic_reason:
            self.deterministic_reason = (
                f"{self.deterministic_reason} {other.deterministic_reason}"
            )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def get_action_queue(
    db: Session, strategy_id: uuid.UUID, *, limit: int = _DEFAULT_LIMIT
) -> dict:
    """Build the prioritized action queue for *strategy_id*.

    Raises ValueError if the strategy does not exist.
    """
    from app.models.strategy import Strategy

    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if strategy is None:
        raise ValueError("Strategy not found")

    sid_hex = strategy_id.hex
    items: dict[str, _Item] = {}

    def add(item: _Item) -> None:
        existing = items.get(item.dedup_key)
        if existing is None:
            items[item.dedup_key] = item
        else:
            existing.merge(item)

    # ---- Backbone: reliable DB-existence checks --------------------------
    _check_runs_and_evidence(db, strategy, add)
    _check_reporting(db, strategy_id, add)
    _check_governance_setup(db, strategy_id, sid_hex, add)

    # ---- Enrichment: guarded service calls -------------------------------
    _enrich_health(db, strategy_id, add)
    _enrich_readiness(db, strategy_id, add)
    _enrich_freshness(db, strategy_id, add)
    _enrich_promotion(db, strategy_id, add)
    _enrich_assumptions(db, strategy_id, add)

    # ---- Sort + rank -----------------------------------------------------
    ordered = sorted(
        items.values(),
        key=lambda it: (
            _SEVERITY_RANK.get(it.severity, 9),
            _STATUS_RANK.get(it.status, 9),
            _CATEGORY_RANK.get(it.category, 9),
            it.title.lower(),
        ),
    )

    total = len(ordered)
    completed = sum(1 for it in ordered if it.status == "done")
    pending = sum(1 for it in ordered if it.status == "pending")
    blocked = sum(1 for it in ordered if it.status == "blocked")
    optional = sum(1 for it in ordered if it.status == "optional")

    limited = ordered[: max(0, limit)]
    out_items = []
    for rank, it in enumerate(limited, start=1):
        out_items.append(
            {
                "id": f"{sid_hex}:{it.dedup_key}",
                "strategy_id": str(strategy_id),
                "title": it.title,
                "description": it.description,
                "why_it_matters": it.why_it_matters,
                "severity": it.severity,
                "priority_rank": rank,
                "status": it.status,
                "category": it.category,
                "source": it.source,
                "target_tab": it.target_tab,
                "target_panel_label": it.target_panel_label,
                "action_label": it.action_label,
                "action_type": it.action_type,
                "related_object_id": it.related_object_id,
                "related_object_type": it.related_object_type,
                "deterministic_reason": it.deterministic_reason,
                "created_from": it.created_from,
            }
        )

    summary = _build_summary(strategy.name, ordered, blocked, pending)

    return {
        "strategy_id": str(strategy_id),
        "strategy_name": strategy.name,
        "generated_at": _utcnow(),
        "items": out_items,
        "total_action_count": total,
        "completed_count": completed,
        "pending_count": pending,
        "blocked_count": blocked,
        "optional_count": optional,
        "deterministic_summary": summary,
        "disclaimer": (
            "Action Queue prioritizes research evidence tasks. "
            "It does not provide trading recommendations."
        ),
    }


# ---------------------------------------------------------------------------
# Backbone checks (DB existence — always safe)
# ---------------------------------------------------------------------------

def _check_runs_and_evidence(db: Session, strategy, add) -> None:
    from app.models.strategy_run import StrategyRun

    runs = (
        db.query(StrategyRun)
        .filter(StrategyRun.strategy_id == strategy.id)
        .order_by(StrategyRun.created_at.desc())
        .all()
    )

    if not runs:
        add(_Item(
            dedup_key="no_runs",
            title="Log your first strategy run",
            description="No runs are logged for this strategy yet.",
            why_it_matters="Runs anchor every downstream check — backtest audits, reliability, drift, and readiness all build on logged run evidence.",
            severity="high",
            status="pending",
            category="run_quality",
            source="run_history",
            action_label="Log a run or upload a bundle",
            action_type="upload_bundle",
            target_tab="developer",
            target_panel_label="Evidence Bundle Ingestion",
            deterministic_reason="No strategy_run records exist for this strategy.",
        ))
        return

    latest = runs[0]
    # Missing linked evidence on the latest run → one merged "link evidence" item.
    missing_layers = []
    if latest.dataset_snapshot_id is None:
        missing_layers.append("dataset")
    if latest.signal_snapshot_id is None:
        missing_layers.append("signal")
    if latest.universe_snapshot_id is None:
        missing_layers.append("universe")
    if latest.strategy_version_id is None:
        missing_layers.append("version")

    if missing_layers:
        layer_text = ", ".join(missing_layers)
        is_latest_backtest = latest.run_type in ("backtest", "paper", "live")
        add(_Item(
            dedup_key="link_run_evidence",
            title="Link evidence to the latest run",
            description=f"The latest run “{latest.run_name}” is missing linked {layer_text} evidence.",
            why_it_matters="Without linked evidence, run-level trust scoring and drift comparisons are incomplete.",
            severity="high" if is_latest_backtest else "medium",
            status="pending",
            category="run_quality",
            source="run_history",
            action_label="Link or upload evidence",
            action_type="upload_bundle",
            target_tab="runs",
            target_panel_label="Run Evidence",
            related_object_id=str(latest.id),
            related_object_type="strategy_run",
            deterministic_reason=f"Latest run is missing FK links: {layer_text}.",
        ))

    # No paper/live run → shadow-monitoring prerequisite.
    has_progression_run = any(r.run_type in ("paper", "live") for r in runs)
    if not has_progression_run:
        add(_Item(
            dedup_key="no_progression_run",
            title="Log a paper run before shadow monitoring",
            description="Only research/backtest runs exist for this strategy.",
            why_it_matters="Shadow monitoring needs a paper or live-like run to compare against backtest behavior.",
            severity="low",
            status="optional",
            category="shadow",
            source="run_history",
            action_label="Upload a paper run bundle",
            action_type="upload_bundle",
            target_tab="developer",
            target_panel_label="Evidence Bundle Ingestion",
            deterministic_reason="No run with run_type in (paper, live) exists.",
        ))


def _check_reporting(db: Session, strategy_id: uuid.UUID, add) -> None:
    from app.models.report import Report

    has_report = (
        db.query(Report)
        .filter(
            Report.strategy_id == strategy_id,
            Report.report_type == "strategy_reliability",
        )
        .first()
        is not None
    )
    if not has_report:
        add(_Item(
            dedup_key="generate_report",
            title="Generate a reliability report",
            description="No strategy reliability report has been generated yet.",
            why_it_matters="Reports package the current evidence state into a shareable summary for review and export.",
            severity="low",
            status="pending",
            category="reporting",
            source="report",
            action_label="Generate report",
            action_type="generate_report",
            target_tab="exports",
            target_panel_label="Strategy Evidence Export",
            deterministic_reason="No strategy_reliability Report row exists.",
        ))


def _check_governance_setup(db: Session, strategy_id: uuid.UUID, sid_hex: str, add) -> None:
    from app.models.regression import StrategyRegressionTest
    from app.models.config_policy import StrategyConfigPolicy
    from app.models.evidence_sla import EvidenceSLAPolicy

    if db.query(StrategyRegressionTest).filter(
        StrategyRegressionTest.strategy_id == strategy_id
    ).first() is None:
        add(_Item(
            dedup_key="create_regression_tests",
            title="Create default regression tests",
            description="No regression tests are configured for this strategy.",
            why_it_matters="Regression tests catch metric and trust deterioration between runs before it reaches review.",
            severity="medium",
            status="pending",
            category="governance",
            source="regression_tests",
            action_label="Create default tests",
            action_type="create_regression_tests",
            target_tab="governance",
            target_panel_label="Regression Test Suite",
            deterministic_reason="No strategy_regression_tests rows exist.",
        ))

    if db.query(StrategyConfigPolicy).filter(
        StrategyConfigPolicy.strategy_id == strategy_id
    ).first() is None:
        add(_Item(
            dedup_key="create_config_policy",
            title="Create config guardrails",
            description="No config policy guardrails are configured.",
            why_it_matters="Guardrails prevent unrealistic assumptions such as missing transaction costs or same-close fills.",
            severity="medium",
            status="pending",
            category="governance",
            source="config_policy",
            action_label="Create default guardrails",
            action_type="create_policy",
            target_tab="governance",
            target_panel_label="Config Policy Guardrails",
            deterministic_reason="No strategy_config_policies rows exist.",
        ))

    if db.query(EvidenceSLAPolicy).filter(
        EvidenceSLAPolicy.strategy_id == strategy_id
    ).first() is None:
        add(_Item(
            dedup_key="create_sla",
            title="Create an evidence SLA policy",
            description="No evidence SLA policy is configured.",
            why_it_matters="SLA rules track stale or missing evidence so obligations are visible before reviews.",
            severity="low",
            status="pending",
            category="governance",
            source="sla",
            action_label="Create default SLA",
            action_type="create_sla",
            target_tab="governance",
            target_panel_label="Evidence SLA Monitor",
            deterministic_reason="No evidence_sla_policies rows exist.",
        ))


# ---------------------------------------------------------------------------
# Enrichment (guarded service calls)
# ---------------------------------------------------------------------------

def _enrich_health(db: Session, strategy_id: uuid.UUID, add) -> None:
    try:
        from app.services.strategy_health import compute_strategy_health

        snap = compute_strategy_health(strategy_id, db)
        if getattr(snap, "open_alert_count", 0) and snap.open_alert_count > 0:
            sev = "high" if getattr(snap, "high_critical_alert_count", 0) else "medium"
            add(_Item(
                dedup_key="triage_alerts",
                title="Triage open alerts",
                description=f"{snap.open_alert_count} open alert(s) on this strategy.",
                why_it_matters="Open alerts flag evidence-quality or reliability issues that need acknowledgement or resolution.",
                severity=sev,
                status="pending",
                category="evidence",
                source="alerts",
                action_label="Open Alerts",
                action_type="navigate",
                target_tab="overview",
                target_panel_label="Alerts",
                deterministic_reason=f"Strategy health reports open_alert_count={snap.open_alert_count}.",
            ))
        for layer in (getattr(snap, "missing_evidence", None) or [])[:6]:
            routed = _route_missing_evidence(layer)
            if routed is not None:
                # Merge into the matching backbone item (e.g. the report or
                # run-evidence action) so one issue is not listed twice.
                rkey, rcat, rtab, rpanel, raction = routed
                add(_Item(
                    dedup_key=rkey,
                    title=_missing_layer_title(layer),
                    description=str(layer),
                    why_it_matters="This evidence layer is absent, which weakens the reliability assessment.",
                    severity="medium",
                    status="pending",
                    category=rcat,
                    source="reliability",
                    action_label="Add evidence",
                    action_type=raction,
                    target_tab=rtab,
                    target_panel_label=rpanel,
                    deterministic_reason=f"Strategy health missing_evidence includes: {layer}.",
                ))
                continue
            key = _missing_layer_key(layer)
            add(_Item(
                dedup_key=f"missing_evidence:{key}",
                title=_missing_layer_title(layer),
                description=str(layer),
                why_it_matters="This evidence layer is absent, which weakens the reliability assessment.",
                severity="medium",
                status="pending",
                category="evidence",
                source="reliability",
                action_label="Add evidence",
                action_type="upload_bundle",
                target_tab="evidence",
                target_panel_label="Evidence",
                deterministic_reason=f"Strategy health missing_evidence includes: {layer}.",
            ))
    except Exception:
        pass


def _enrich_readiness(db: Session, strategy_id: uuid.UUID, add) -> None:
    try:
        from app.services.strategy_readiness import compute_strategy_readiness

        r = compute_strategy_readiness(strategy_id, db)
        verdict = (getattr(r, "readiness_verdict", "") or "").lower()
        blockers = getattr(r, "blockers", None) or []
        is_blocked = verdict in ("blocked", "requires_review", "under_instrumented")
        for i, b in enumerate(blockers[:5]):
            add(_Item(
                dedup_key=f"readiness_blocker:{i}",
                title=str(b),
                description="Readiness blocker for the next research stage.",
                why_it_matters="The strategy cannot progress to the next stage until this is resolved.",
                severity="high",
                status="blocked" if is_blocked else "pending",
                category="readiness",
                source="readiness",
                action_label="Review readiness",
                action_type="navigate",
                target_tab="governance",
                target_panel_label="Promotion Gates",
                deterministic_reason=f"Readiness verdict={verdict or 'n/a'}; blocker: {b}.",
            ))
    except Exception:
        pass


def _enrich_freshness(db: Session, strategy_id: uuid.UUID, add) -> None:
    try:
        from app.services.evidence_freshness import compute_evidence_freshness

        f = compute_evidence_freshness(strategy_id, db)
        stale = getattr(f, "stale_count", 0) or 0
        missing = getattr(f, "missing_count", 0) or 0
        aging = getattr(f, "aging_count", 0) or 0
        order = getattr(f, "suggested_refresh_order", None) or []
        first = order[0] if order else None
        if stale > 0 or missing > 0:
            add(_Item(
                dedup_key="refresh_stale_evidence",
                title="Refresh stale evidence",
                description=(
                    f"{stale} stale and {missing} missing evidence item(s)"
                    + (f"; refresh {first} first." if first else ".")
                ),
                why_it_matters="Decisions should use current evidence; stale snapshots understate real-world risk.",
                severity="high" if stale > 0 else "medium",
                status="pending",
                category="freshness",
                source="freshness",
                action_label="Upload fresh evidence",
                action_type="upload_bundle",
                target_tab="evidence",
                target_panel_label="Evidence Freshness",
                deterministic_reason=f"Freshness reports stale={stale}, missing={missing}.",
            ))
        elif aging > 0:
            add(_Item(
                dedup_key="refresh_aging_evidence",
                title="Refresh aging evidence soon",
                description=f"{aging} evidence item(s) approaching the freshness limit.",
                why_it_matters="Refreshing aging evidence early avoids a stale-evidence block at review time.",
                severity="low",
                status="optional",
                category="freshness",
                source="freshness",
                action_label="Review freshness",
                action_type="navigate",
                target_tab="evidence",
                target_panel_label="Evidence Freshness",
                deterministic_reason=f"Freshness reports aging={aging}.",
            ))
    except Exception:
        pass


def _enrich_promotion(db: Session, strategy_id: uuid.UUID, add) -> None:
    try:
        from app.services.promotion_gates import evaluate_promotion_gates

        g = evaluate_promotion_gates(strategy_id, "paper_candidate", db)
        blocker_count = getattr(g, "blocker_count", 0) or 0
        if blocker_count > 0:
            target = getattr(g, "target_stage", "the next stage")
            add(_Item(
                dedup_key="promotion_blocked",
                title="Resolve promotion blockers",
                description=f"{blocker_count} gate(s) block promotion to {target}.",
                why_it_matters="The strategy cannot advance until required promotion gates pass.",
                severity="high",
                status="blocked",
                category="governance",
                source="promotion_gates",
                action_label="Review promotion gates",
                action_type="navigate",
                target_tab="governance",
                target_panel_label="Promotion Gates",
                deterministic_reason=f"Promotion gate evaluation reports blocker_count={blocker_count}.",
            ))
    except Exception:
        pass


def _enrich_assumptions(db: Session, strategy_id: uuid.UUID, add) -> None:
    try:
        from app.services.assumption_health import compute_assumption_health

        a = compute_assumption_health(strategy_id, db)
        status = (a.get("overall_status") or "").lower() if isinstance(a, dict) else ""
        if status in ("review", "weak"):
            add(_Item(
                dedup_key="review_assumptions",
                title="Review strategy assumptions",
                description=f"Assumption health is “{status}”.",
                why_it_matters="Weak cost, fill, borrow, leverage, or liquidity assumptions can make backtests unreliable.",
                severity="high" if status == "weak" else "medium",
                status="pending",
                category="assumptions",
                source="assumption_health",
                action_label="Review assumptions",
                action_type="navigate",
                target_tab="governance",
                target_panel_label="Config Policy Guardrails",
                deterministic_reason=f"Assumption health overall_status={status}.",
            ))
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _route_missing_evidence(layer: str):
    """Map a free-form missing_evidence string onto a backbone dedup key.

    Returns (dedup_key, category, target_tab, panel_label, action_type) when the
    string clearly refers to an issue already tracked by a backbone check, so the
    two sources merge into one item. Returns None when it should stand alone.
    """
    s = str(layer).lower()
    if "report" in s:
        return ("generate_report", "reporting", "exports",
                "Strategy Evidence Export", "generate_report")
    if any(t in s for t in ("dataset", "signal", "universe", "version")):
        return ("link_run_evidence", "run_quality", "runs",
                "Run Evidence", "upload_bundle")
    if "config" in s or "policy" in s or "guardrail" in s:
        return ("create_config_policy", "governance", "governance",
                "Config Policy Guardrails", "create_policy")
    return None


def _missing_layer_key(layer: str) -> str:
    return layer.strip().lower().replace(" ", "_")[:48]


def _missing_layer_title(layer: str) -> str:
    s = str(layer)
    looks_token = (" " not in s) or all(c.isalnum() or c == "_" for c in s)
    if looks_token:
        return f"Add {s.replace('_', ' ')} evidence"
    return s[0].upper() + s[1:] if s else "Add evidence"


def _build_summary(name: str, items: list[_Item], blocked: int, pending: int) -> str:
    if not items:
        return f"{name}: no outstanding actions — the core evidence looks complete."
    top = items[0]
    parts = [f"{name}: {len(items)} action(s)"]
    if blocked:
        parts.append(f"{blocked} blocking progression")
    parts.append(f"top priority — {top.title.lower()}")
    return ". ".join(parts) + "."
