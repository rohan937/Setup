"""Evidence Graph service (M52).

Builds a deterministic graph of strategy evidence nodes and edges.
Read-only — no AuditTimelineEvent created, not trading advice.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

NODE_TYPE_LABELS = {
    "strategy": "Strategy",
    "strategy_version": "Version",
    "config_snapshot": "Config",
    "universe_snapshot": "Universe",
    "signal_snapshot": "Signal",
    "dataset": "Dataset",
    "dataset_snapshot": "Dataset Snap",
    "strategy_run": "Run",
    "backtest_audit": "Audit",
    "reliability_score": "Reliability",
    "readiness_scorecard": "Readiness",
    "shadow_monitor": "Shadow Monitor",
    "promotion_gates": "Promotion Gates",
    "report": "Report",
    "alert": "Alert",
    "timeline_event": "Timeline",
}

MAX_RUNS = 100
MAX_SNAPS = 100
MAX_TL = 50
MAX_ALERTS = 50
MAX_REPORTS = 20
MAX_SCORES = 20


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _score_to_status(
    score: Optional[float],
    t_healthy: float = 80,
    t_watch: float = 65,
    t_review: float = 50,
) -> str:
    if score is None:
        return "unknown"
    if score >= t_healthy:
        return "healthy"
    elif score >= t_watch:
        return "watch"
    elif score >= t_review:
        return "review"
    else:
        return "weak"


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class EvidenceGraphNodeData:
    node_id: str
    node_type: str
    label: str
    subtitle: Optional[str]
    status: str
    severity: str
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    score: Optional[float]
    metadata_json: dict
    route_hint: Optional[str] = None


@dataclass
class EvidenceGraphEdgeData:
    edge_id: str
    source_node_id: str
    target_node_id: str
    relationship: str
    label: str
    metadata_json: dict = field(default_factory=dict)


@dataclass
class EvidenceBlastRadiusData:
    focus_node_id: str
    focus_node_type: str
    upstream_count: int
    downstream_count: int
    affected_run_count: int
    affected_report_count: int
    affected_alert_count: int
    affected_audit_count: int
    affected_readiness: bool
    affected_shadow_monitor: bool
    affected_promotion_gates: bool
    affected_nodes: list
    blast_radius_severity: str


@dataclass
class EvidenceGraphSummaryData:
    strategy_id: uuid.UUID
    strategy_name: str
    generated_at: datetime
    node_count: int
    edge_count: int
    weak_node_count: int
    missing_node_count: int
    high_critical_alert_node_count: int
    connected_run_count: int
    orphan_evidence_count: int
    graph_status: str
    deterministic_summary: str
    suggested_checks: list = field(default_factory=list)


@dataclass
class StrategyEvidenceGraphData:
    summary: EvidenceGraphSummaryData
    nodes: list
    edges: list
    blast_radius: Optional[EvidenceBlastRadiusData]


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------

def build_strategy_evidence_graph(
    strategy_id: uuid.UUID,
    db: Session,
    *,
    focus_node_id: Optional[str] = None,
    focus_node_type: Optional[str] = None,
    include_timeline: bool = True,
    include_computed: bool = True,
) -> StrategyEvidenceGraphData:
    """Build the evidence graph for a strategy.

    Deterministic — no AI, no external calls, read-only.
    """
    from app.models.strategy import Strategy
    from app.models.strategy_version import StrategyVersion
    from app.models.strategy_run import StrategyRun
    from app.models.backtest_audit import BacktestAudit
    from app.models.strategy_config_snapshot import StrategyConfigSnapshot
    from app.models.universe_snapshot import UniverseSnapshot
    from app.models.signal_snapshot import SignalSnapshot
    from app.models.dataset_snapshot import DatasetSnapshot
    from app.models.dataset import Dataset
    from app.models.strategy_reliability_score import StrategyReliabilityScore
    from app.models.report import Report
    from app.models.alert import Alert
    from app.models.audit_timeline_event import AuditTimelineEvent

    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if strategy is None:
        raise ValueError(f"Strategy {strategy_id} not found")

    now = datetime.now(timezone.utc)

    nodes: dict[str, EvidenceGraphNodeData] = {}
    edges: list[EvidenceGraphEdgeData] = []

    def _add_node(
        nid, ntype, label, subtitle=None, status="unknown", severity="info",
        created_at=None, updated_at=None, score=None, metadata=None, route=None,
    ):
        nodes[nid] = EvidenceGraphNodeData(
            nid, ntype, label, subtitle, status, severity,
            created_at, updated_at, score, metadata or {}, route,
        )

    def _add_edge(sid, tid, rel, label=None):
        eid = f"edge:{sid}:{tid}:{rel}"
        edges.append(
            EvidenceGraphEdgeData(eid, sid, tid, rel, label or rel.replace("_", " "))
        )

    # -----------------------------------------------------------------------
    # STRATEGY NODE
    # -----------------------------------------------------------------------
    strat_id = f"strategy:{strategy_id}"
    _add_node(
        strat_id, "strategy", strategy.name, strategy.asset_class,
        "healthy" if strategy.status == "active" else "watch",
        "info", strategy.created_at, strategy.updated_at,
    )

    # -----------------------------------------------------------------------
    # VERSIONS
    # -----------------------------------------------------------------------
    versions = (
        db.query(StrategyVersion)
        .filter(StrategyVersion.strategy_id == strategy_id)
        .order_by(StrategyVersion.created_at.desc())
        .limit(50)
        .all()
    )
    version_id_map: dict = {}
    for v in versions:
        vid = f"version:{v.id}"
        version_id_map[v.id] = vid
        _add_node(
            vid, "strategy_version", v.version_label, v.signal_name,
            "healthy", "info", v.created_at, v.updated_at,
            route=f"/strategies/{strategy_id}",
        )
        _add_edge(strat_id, vid, "versioned_by")

    # -----------------------------------------------------------------------
    # CONFIG SNAPSHOTS
    # -----------------------------------------------------------------------
    cfgs = (
        db.query(StrategyConfigSnapshot)
        .filter(StrategyConfigSnapshot.strategy_id == strategy_id)
        .order_by(StrategyConfigSnapshot.created_at.desc())
        .limit(MAX_SNAPS)
        .all()
    )
    cfg_id_map: dict = {}
    for c in cfgs:
        cid = f"config:{c.id}"
        cfg_id_map[c.id] = cid
        _add_node(
            cid, "config_snapshot", c.label,
            f"hash {c.config_hash[:8] if c.config_hash else ''}",
            "healthy", "info", c.created_at, c.updated_at,
        )
        _add_edge(strat_id, cid, "configured_by", "config")
        if c.strategy_version_id and c.strategy_version_id in version_id_map:
            _add_edge(version_id_map[c.strategy_version_id], cid, "configured_by", "config for version")

    # -----------------------------------------------------------------------
    # UNIVERSE SNAPSHOTS
    # -----------------------------------------------------------------------
    unis = (
        db.query(UniverseSnapshot)
        .filter(UniverseSnapshot.strategy_id == strategy_id)
        .order_by(UniverseSnapshot.created_at.desc())
        .limit(MAX_SNAPS)
        .all()
    )
    uni_id_map: dict = {}
    for u in unis:
        uid = f"universe:{u.id}"
        uni_id_map[u.id] = uid
        _add_node(
            uid, "universe_snapshot", u.label, f"{u.symbol_count} symbols",
            "healthy", "info", u.created_at, u.updated_at,
            route=f"/strategies/{strategy_id}",
        )
        _add_edge(strat_id, uid, "uses_universe", "universe")
        if u.strategy_version_id and u.strategy_version_id in version_id_map:
            _add_edge(version_id_map[u.strategy_version_id], uid, "uses_universe")

    # -----------------------------------------------------------------------
    # SIGNAL SNAPSHOTS
    # -----------------------------------------------------------------------
    sigs = (
        db.query(SignalSnapshot)
        .filter(SignalSnapshot.strategy_id == strategy_id)
        .order_by(SignalSnapshot.created_at.desc())
        .limit(MAX_SNAPS)
        .all()
    )
    sig_id_map: dict = {}
    for s in sigs:
        sid2 = f"signal:{s.id}"
        sig_id_map[s.id] = sid2
        score = float(s.quality_score) if s.quality_score is not None else None
        status = _score_to_status(score, 80, 65, 50)
        sev = (
            "high" if (score is not None and score < 50)
            else ("medium" if (score is not None and score < 65) else "info")
        )
        _add_node(
            sid2, "signal_snapshot",
            s.label or f"Signal {str(s.id)[:8]}",
            s.signal_name, status, sev, s.created_at, s.updated_at, score,
        )
        _add_edge(strat_id, sid2, "uses_signal", "signal")
        if s.strategy_version_id and s.strategy_version_id in version_id_map:
            _add_edge(version_id_map[s.strategy_version_id], sid2, "uses_signal")

    # -----------------------------------------------------------------------
    # RUNS + LINKED EVIDENCE
    # -----------------------------------------------------------------------
    runs = (
        db.query(StrategyRun)
        .filter(StrategyRun.strategy_id == strategy_id)
        .order_by(StrategyRun.created_at.desc())
        .limit(MAX_RUNS)
        .all()
    )
    run_id_map: dict = {}
    ds_snap_cache: dict = {}

    for r in runs:
        rid = f"run:{r.id}"
        run_id_map[r.id] = rid
        _add_node(
            rid, "strategy_run", r.run_name, r.run_type,
            "healthy" if r.status == "completed" else "watch",
            "info", r.created_at, r.completed_at,
            route=f"/strategies/{strategy_id}",
        )
        _add_edge(strat_id, rid, "produced_run", f"{r.run_type} run")
        if r.strategy_version_id and r.strategy_version_id in version_id_map:
            _add_edge(version_id_map[r.strategy_version_id], rid, "produced_run")
        if r.universe_snapshot_id and r.universe_snapshot_id in uni_id_map:
            _add_edge(rid, uni_id_map[r.universe_snapshot_id], "uses_universe")
        if r.signal_snapshot_id and r.signal_snapshot_id in sig_id_map:
            _add_edge(rid, sig_id_map[r.signal_snapshot_id], "uses_signal")

        # Dataset snapshot via run
        if r.dataset_snapshot_id:
            dsid = str(r.dataset_snapshot_id)
            ds_node_id = f"dataset_snap:{dsid}"
            if dsid not in ds_snap_cache:
                ds_snap_cache[dsid] = ds_node_id
                try:
                    snap = db.query(DatasetSnapshot).filter(
                        DatasetSnapshot.id == r.dataset_snapshot_id
                    ).first()
                    if snap:
                        hs = float(snap.health_score) if snap.health_score is not None else None
                        ds_status = _score_to_status(hs, 80, 65, 50)
                        ds_sev = (
                            "high" if (hs is not None and hs < 50)
                            else ("medium" if (hs is not None and hs < 65) else "info")
                        )
                        _add_node(
                            ds_node_id, "dataset_snapshot",
                            snap.version_label or dsid[:8],
                            f"health {hs:.0f}" if hs is not None else None,
                            ds_status, ds_sev, snap.created_at, snap.updated_at, hs,
                        )
                        try:
                            ds = db.query(Dataset).filter(
                                Dataset.id == snap.dataset_id
                            ).first()
                            if ds:
                                dataset_node_id = f"dataset:{ds.id}"
                                if dataset_node_id not in nodes:
                                    _add_node(
                                        dataset_node_id, "dataset", ds.name, ds.dataset_type,
                                        "healthy", "info", ds.created_at, ds.updated_at,
                                    )
                                    _add_edge(strat_id, dataset_node_id, "uses_dataset", "dataset")
                                _add_edge(dataset_node_id, ds_node_id, "owns", "snapshot")
                        except Exception:
                            pass
                except Exception:
                    pass
            _add_edge(rid, ds_node_id, "uses_dataset", "dataset snapshot")

    # -----------------------------------------------------------------------
    # BACKTEST AUDITS
    # -----------------------------------------------------------------------
    try:
        audits = (
            db.query(BacktestAudit)
            .join(StrategyRun, BacktestAudit.strategy_run_id == StrategyRun.id)
            .filter(StrategyRun.strategy_id == strategy_id)
            .order_by(BacktestAudit.created_at.desc())
            .limit(MAX_RUNS)
            .all()
        )
        for a in audits:
            aid = f"audit:{a.id}"
            trust = float(a.trust_score)
            status = _score_to_status(trust, 80, 65, 50)
            sev = (
                "critical" if trust < 40
                else ("high" if trust < 55 else ("medium" if trust < 70 else "info"))
            )
            _add_node(
                aid, "backtest_audit", f"Audit {a.overall_status}",
                f"trust {trust:.0f}", status, sev, a.created_at, None, trust,
            )
            if a.strategy_run_id in run_id_map:
                _add_edge(run_id_map[a.strategy_run_id], aid, "audited_by", "audit")
    except Exception:
        pass

    # -----------------------------------------------------------------------
    # RELIABILITY SCORES
    # -----------------------------------------------------------------------
    try:
        scores = (
            db.query(StrategyReliabilityScore)
            .filter(StrategyReliabilityScore.strategy_id == strategy_id)
            .order_by(StrategyReliabilityScore.generated_at.desc())
            .limit(MAX_SCORES)
            .all()
        )
        for rs in scores:
            rsid = f"rel:{rs.id}"
            sc = rs.overall_score
            status = _score_to_status(float(sc) if sc else None)
            _add_node(
                rsid, "reliability_score",
                f"Reliability ({rs.status})",
                f"score {sc:.0f}" if sc else "no score",
                status, "info", rs.generated_at, None,
                float(sc) if sc else None,
            )
            _add_edge(strat_id, rsid, "scored_by", "reliability score")
    except Exception:
        pass

    # -----------------------------------------------------------------------
    # COMPUTED NODES
    # -----------------------------------------------------------------------
    if include_computed:
        try:
            from app.services.strategy_readiness import compute_strategy_readiness
            r = compute_strategy_readiness(strategy_id, db)
            ready_id = f"readiness:{strategy_id}"
            score = r.readiness_score
            verdict = r.readiness_verdict
            status = (
                "healthy" if verdict in (
                    "ready_for_paper_trading_consideration",
                    "ready_for_backtest_review",
                )
                else (
                    "review" if verdict == "requires_review_before_progression"
                    else ("weak" if verdict in ("blocked", "under_instrumented") else "unknown")
                )
            )
            _add_node(
                ready_id, "readiness_scorecard",
                f"Readiness: {r.verdict_label}",
                f"score {score:.0f}" if score else verdict,
                status, "info", r.generated_at, None, score,
            )
            _add_edge(strat_id, ready_id, "computed_from", "readiness")
        except Exception:
            pass

        try:
            from app.services.shadow_production import compute_shadow_production_monitor
            sm = compute_shadow_production_monitor(strategy_id, db)
            sm_id = f"shadow:{strategy_id}"
            sm_status = {
                "stable": "healthy",
                "watch": "watch",
                "review": "review",
                "severe": "weak",
                "no_shadow_runs": "missing",
                "insufficient_baseline": "missing",
            }.get(sm.monitor_status, "unknown")
            score_val = sm.shadow_stability_score
            _add_node(
                sm_id, "shadow_monitor",
                f"Shadow: {sm.monitor_status}",
                f"score {score_val:.0f}" if score_val else None,
                sm_status, "info", sm.generated_at, None, score_val,
            )
            _add_edge(strat_id, sm_id, "computed_from", "shadow monitor")
        except Exception:
            pass

        try:
            from app.services.promotion_gates import evaluate_promotion_gates
            pg = evaluate_promotion_gates(strategy_id, "paper_candidate", db)
            pg_id = f"promotion:{strategy_id}"
            pg_status = {
                "pass": "healthy",
                "conditional_pass": "watch",
                "requires_review": "review",
                "blocked": "weak",
                "insufficient_evidence": "missing",
            }.get(pg.promotion_verdict, "unknown")
            _add_node(
                pg_id, "promotion_gates",
                f"Gates: {pg.promotion_verdict}",
                f"score {pg.gate_score:.0f}" if pg.gate_score else None,
                pg_status, "info", pg.generated_at, None, pg.gate_score,
            )
            _add_edge(strat_id, pg_id, "computed_from", "promotion gates")
        except Exception:
            pass

    # -----------------------------------------------------------------------
    # REPORTS
    # -----------------------------------------------------------------------
    try:
        reports = (
            db.query(Report)
            .filter(Report.strategy_id == strategy_id)
            .order_by(Report.generated_at.desc())
            .limit(MAX_REPORTS)
            .all()
        )
        for rep in reports:
            rpid = f"report:{rep.id}"
            _add_node(
                rpid, "report",
                rep.title or rep.report_type, rep.report_type,
                "healthy", "info", rep.generated_at, None,
                float(rep.score) if rep.score else None,
            )
            _add_edge(strat_id, rpid, "reported_by", "report")
    except Exception:
        pass

    # -----------------------------------------------------------------------
    # ALERTS
    # -----------------------------------------------------------------------
    try:
        alerts = (
            db.query(Alert)
            .filter(Alert.strategy_id == str(strategy_id))
            .order_by(Alert.triggered_at.desc())
            .limit(MAX_ALERTS)
            .all()
        )
        for al in alerts:
            alid = f"alert:{al.id}"
            sev = al.severity if al.severity in ("info", "low", "medium", "high", "critical") else "medium"
            status = (
                "review" if al.severity in ("medium", "low")
                else ("weak" if al.severity in ("high", "critical") else "healthy")
            )
            _add_node(
                alid, "alert",
                al.title[:60] if al.title else "Alert",
                al.severity, status, sev, al.triggered_at, None,
            )
            _add_edge(strat_id, alid, "alerted_by", "alert")
    except Exception:
        pass

    # -----------------------------------------------------------------------
    # TIMELINE EVENTS
    # -----------------------------------------------------------------------
    if include_timeline:
        try:
            events = (
                db.query(AuditTimelineEvent)
                .filter(AuditTimelineEvent.strategy_id == strategy_id)
                .order_by(AuditTimelineEvent.event_time.desc())
                .limit(MAX_TL)
                .all()
            )
            for ev in events:
                evid = f"timeline:{ev.id}"
                _add_node(
                    evid, "timeline_event",
                    ev.title[:60] if ev.title else ev.event_type,
                    ev.source_type, "computed", "info", ev.event_time, None,
                )
                _add_edge(strat_id, evid, "timeline_event_for", "timeline")
        except Exception:
            pass

    # -----------------------------------------------------------------------
    # BLAST RADIUS
    # -----------------------------------------------------------------------
    blast: Optional[EvidenceBlastRadiusData] = None
    if focus_node_id:
        adj_out: dict[str, set] = {}
        adj_in: dict[str, set] = {}
        for e in edges:
            adj_out.setdefault(e.source_node_id, set()).add(e.target_node_id)
            adj_in.setdefault(e.target_node_id, set()).add(e.source_node_id)

        focus_full_id = (
            focus_node_id
            if focus_node_id in nodes
            else next(
                (n for n in nodes if n == focus_node_id or n.endswith(focus_node_id)),
                None,
            )
        )

        if focus_full_id:
            # BFS downstream
            downstream: set = set()
            q = list(adj_out.get(focus_full_id, []))
            visited: set = {focus_full_id}
            while q:
                n = q.pop()
                if n not in visited:
                    downstream.add(n)
                    visited.add(n)
                    q.extend(adj_out.get(n, []))

            # BFS upstream
            upstream: set = set()
            q = list(adj_in.get(focus_full_id, []))
            visited = {focus_full_id}
            while q:
                n = q.pop()
                if n not in visited:
                    upstream.add(n)
                    visited.add(n)
                    q.extend(adj_in.get(n, []))

            affected_all = downstream | upstream
            aff_runs = sum(1 for n in affected_all if n.startswith("run:"))
            aff_reports = sum(1 for n in affected_all if n.startswith("report:"))
            aff_alerts = sum(1 for n in affected_all if n.startswith("alert:"))
            aff_audits = sum(1 for n in affected_all if n.startswith("audit:"))
            aff_readiness = any(n.startswith("readiness:") for n in affected_all)
            aff_shadow = any(n.startswith("shadow:") for n in affected_all)
            aff_promo = any(n.startswith("promotion:") for n in affected_all)

            focus_node_obj = nodes.get(focus_full_id)
            focus_status = focus_node_obj.status if focus_node_obj else "unknown"

            sev = "none"
            if aff_runs >= 3 or (
                aff_readiness and focus_status in ("weak", "review")
            ):
                sev = "high"
            elif aff_runs >= 1 or aff_audits >= 1 or aff_reports >= 1:
                sev = "medium"
            elif len(affected_all) > 0:
                sev = "low"

            aff_nodes = [nodes[n] for n in list(affected_all)[:50] if n in nodes]
            blast = EvidenceBlastRadiusData(
                focus_full_id,
                focus_node_type or focus_full_id.split(":")[0],
                len(upstream),
                len(downstream),
                aff_runs,
                aff_reports,
                aff_alerts,
                aff_audits,
                aff_readiness,
                aff_shadow,
                aff_promo,
                aff_nodes,
                sev,
            )
        else:
            blast = EvidenceBlastRadiusData(
                focus_node_id,
                focus_node_type or "",
                0, 0, 0, 0, 0, 0,
                False, False, False,
                [], "none",
            )

    # -----------------------------------------------------------------------
    # SUMMARY
    # -----------------------------------------------------------------------
    node_list = list(nodes.values())
    weak_count = sum(1 for n in node_list if n.status == "weak")
    missing_count = sum(1 for n in node_list if n.status == "missing")
    hc_alerts = sum(
        1 for n in node_list
        if n.node_type == "alert" and n.severity in ("high", "critical")
    )
    conn_runs = sum(1 for n in node_list if n.node_type == "strategy_run")

    nodes_with_edges = (
        {e.source_node_id for e in edges} | {e.target_node_id for e in edges}
    )
    orphans = sum(
        1 for n in node_list
        if n.node_type not in (
            "strategy", "readiness_scorecard", "shadow_monitor", "promotion_gates"
        )
        and n.node_id not in nodes_with_edges
    )

    if conn_runs == 0 or len(node_list) < 5:
        graph_status = "sparse"
    elif weak_count > 0 or hc_alerts > 0:
        graph_status = "review"
    elif missing_count > 0:
        graph_status = "partial"
    else:
        graph_status = "complete"

    checks = []
    if conn_runs == 0:
        checks.append("Log at least one strategy run to populate the evidence graph.")
    if weak_count > 0:
        checks.append(f"Review {weak_count} weak evidence node(s) in the graph.")
    if hc_alerts > 0:
        checks.append(f"Resolve {hc_alerts} high/critical open alert(s).")

    summary_parts = [
        f"Evidence graph for {strategy.name}: {len(node_list)} node(s), {len(edges)} edge(s)."
    ]
    if weak_count:
        summary_parts.append(f"{weak_count} weak node(s).")
    if graph_status == "sparse":
        summary_parts.append("Graph is sparse; log more evidence.")
    summary_parts.append(
        "Deterministic graph of logged evidence. Not investment advice."
    )

    summary = EvidenceGraphSummaryData(
        strategy_id=strategy_id,
        strategy_name=strategy.name,
        generated_at=now,
        node_count=len(node_list),
        edge_count=len(edges),
        weak_node_count=weak_count,
        missing_node_count=missing_count,
        high_critical_alert_node_count=hc_alerts,
        connected_run_count=conn_runs,
        orphan_evidence_count=orphans,
        graph_status=graph_status,
        deterministic_summary=" ".join(summary_parts),
        suggested_checks=checks,
    )
    return StrategyEvidenceGraphData(
        summary=summary,
        nodes=node_list,
        edges=edges,
        blast_radius=blast,
    )
