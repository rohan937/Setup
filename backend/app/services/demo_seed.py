"""Demo seed service — M46.

Populates (or resets) the demo dataset used to showcase QuantFidelity
capabilities.  All operations are idempotent: existing records are found by
slug/label and reused.

Entry points:
  seed_demo_data(db, ...)   — create / extend demo data
  get_demo_status(db)       — describe current demo state (read-only)
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from app.core.constants import (
    AssetClass,
    EventType,
    RunStatus,
    RunType,
    Severity,
    StrategyStatus,
)

if TYPE_CHECKING:
    pass


# ---------------------------------------------------------------------------
# Demo constants — stable identifiers
# ---------------------------------------------------------------------------

DEMO_ORG_NAME = "QuantFidelity Demo Org"
DEMO_PROJECT_NAME = "Quant Research Demo"
DEMO_PROJECT_SLUG = "quant-research-demo"

DEMO_STRATEGIES = [
    {
        "name": "AAPL Mean Reversion Demo",
        "slug": "aapl-mean-reversion-demo",
        "asset_class": "equity",
        "status": "active",
    },
    {
        "name": "FX Carry Strategy Demo",
        "slug": "fx-carry-demo",
        "asset_class": "fx",
        "status": "active",
    },
    {
        "name": "Crypto Momentum Demo",
        "slug": "crypto-momentum-demo",
        "asset_class": "crypto",
        "status": "active",
    },
]

# ---------------------------------------------------------------------------
# Small demo datasets
# ---------------------------------------------------------------------------

AAPL_OHLCV = [
    {"symbol": sym, "timestamp": ts, "open": o, "high": h, "low": l, "close": c, "volume": v}
    for sym, ts, o, h, l, c, v in [
        ("AAPL", "2024-01-02", 185.55, 188.91, 184.81, 185.64, 72043900),
        ("MSFT", "2024-01-02", 374.19, 375.66, 369.27, 374.02, 20481300),
        ("AAPL", "2024-01-03", 184.21, 185.88, 183.43, 184.25, 58862900),
        ("MSFT", "2024-01-03", 372.50, 374.10, 370.83, 373.24, 18329800),
        ("AAPL", "2024-01-04", 181.99, 183.09, 180.94, 182.68, 71878000),
        ("MSFT", "2024-01-04", 371.73, 373.57, 370.12, 372.89, 16543200),
        ("AAPL", "2024-01-05", 183.17, 184.67, 181.89, 184.40, 62549400),
        ("NVDA", "2024-01-02", 495.22, 505.48, 492.60, 495.72, 44872200),
        ("NVDA", "2024-01-03", 490.37, 495.60, 487.08, 493.55, 38124700),
        ("GOOGL", "2024-01-02", 140.93, 142.38, 139.59, 140.52, 24397600),
    ]
]

AAPL_SIGNALS = [
    {"symbol": "AAPL", "timestamp": "2024-01-02", "signal": 1.53},
    {"symbol": "MSFT", "timestamp": "2024-01-02", "signal": -0.42},
    {"symbol": "NVDA", "timestamp": "2024-01-02", "signal": 2.11},
    {"symbol": "GOOGL", "timestamp": "2024-01-02", "signal": -1.07},
    {"symbol": "AMZN", "timestamp": "2024-01-02", "signal": 0.35},
]

FX_OHLCV = [
    {"symbol": "EURUSD", "timestamp": "2024-01-02", "open": 1.0950, "high": 1.0980, "low": 1.0932, "close": 1.0961, "volume": 50000},
    {"symbol": "GBPUSD", "timestamp": "2024-01-02", "open": 1.2710, "high": 1.2748, "low": 1.2695, "close": 1.2738, "volume": 42000},
    {"symbol": "USDJPY", "timestamp": "2024-01-02", "open": 141.50, "high": 142.10, "low": 141.20, "close": 141.87, "volume": 38000},
    {"symbol": "AUDUSD", "timestamp": "2024-01-02", "open": 0.6823, "high": 0.6854, "low": 0.6808, "close": 0.6842, "volume": None},  # intentional null
    {"symbol": "EURUSD", "timestamp": "2024-01-03", "open": 1.0961, "high": 1.0991, "low": 1.0945, "close": 1.0975, "volume": 48000},
    {"symbol": "GBPUSD", "timestamp": "2024-01-03", "open": 1.2738, "high": 1.2755, "low": 1.2712, "close": 1.2742, "volume": 39000},
    {"symbol": "USDJPY", "timestamp": "2024-invalid-date", "open": 141.87, "high": 142.25, "low": 141.65, "close": 142.08, "volume": 36000},  # intentional bad timestamp
    {"symbol": "EURUSD", "timestamp": "2024-01-03", "open": 1.0975, "high": 1.1005, "low": 1.0958, "close": 1.0989, "volume": 51000},  # intentional duplicate
]

FX_SIGNALS = [
    {"symbol": "EURUSD", "timestamp": "2024-01-02", "signal": 0.85},
    {"symbol": "GBPUSD", "timestamp": "2024-01-02", "signal": None},  # missing signal
    {"symbol": "USDJPY", "timestamp": "2024-01-02", "signal": -1.20},
    {"symbol": "AUDUSD", "timestamp": "2024-01-02", "signal": 15.7},  # outlier
    {"symbol": "EURUSD", "timestamp": "2024-01-03", "signal": 0.92},
]

CRYPTO_ROWS = [
    {"symbol": "BTC", "timestamp": "2024-01-02", "close": 42800.0, "volume": 28000},
    {"symbol": "ETH", "timestamp": "2024-01-02", "close": 2250.0, "volume": 15000},
]


# ---------------------------------------------------------------------------
# Helper: _utcnow
# ---------------------------------------------------------------------------

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Helper: get-or-create strategy
# ---------------------------------------------------------------------------

def _get_or_create_strategy(
    db: Session,
    project_id,
    name: str,
    slug: str,
    asset_class: str,
    status: str,
):
    """Return (strategy, created_bool).

    Checks by project_id + slug. Creates + flushes if absent and emits a
    strategy_created timeline event.
    """
    from app.models.strategy import Strategy
    from app.models.audit_timeline_event import AuditTimelineEvent

    existing = (
        db.query(Strategy).filter_by(project_id=project_id, slug=slug).first()
    )
    if existing is not None:
        return existing, False

    strategy = Strategy(
        project_id=project_id,
        name=name,
        slug=slug,
        asset_class=asset_class,
        status=status,
    )
    db.add(strategy)
    db.flush()

    # We need org/project ids for the timeline event — look them up from project
    from app.models.project import Project as ProjectModel
    proj = db.get(ProjectModel, project_id)
    if proj is not None:
        event = AuditTimelineEvent(
            organization_id=proj.organization_id,
            project_id=proj.id,
            strategy_id=strategy.id,
            event_type=EventType.strategy_created,
            title=f"Strategy created: {name}",
            description=f"Demo strategy {name} created during demo seed.",
            source_type="strategy",
            source_id=str(strategy.id),
            severity=Severity.info,
            event_time=_utcnow(),
        )
        db.add(event)
        db.flush()

    return strategy, True


# ---------------------------------------------------------------------------
# AAPL strategy seeder (fully instrumented)
# ---------------------------------------------------------------------------

def _seed_aapl_strategy(
    db: Session,
    strategy,
    org,
    project,
    include_audits: bool,
    include_reports: bool,
) -> list[str]:
    """Create all evidence artifacts for the AAPL demo strategy.

    Returns a list of artifact labels created.
    """
    artifacts: list[str] = []

    # ---- 1. StrategyVersion v1.0 ----
    from app.models.strategy_version import StrategyVersion

    version1 = (
        db.query(StrategyVersion)
        .filter_by(strategy_id=strategy.id, version_label="v1.0")
        .first()
    )
    if version1 is None:
        version1 = StrategyVersion(
            strategy_id=strategy.id,
            version_label="v1.0",
            git_commit="abc123",
            branch_name="main",
            code_path="strategies/aapl_mean_reversion.py",
            signal_name="z_score_mean_reversion",
            signal_description="Mean reversion signal using z-score of recent returns.",
        )
        db.add(version1)
        db.flush()
        artifacts.append("strategy_version:v1.0")

    # ---- 2. StrategyVersion v2.0 ----
    version2 = (
        db.query(StrategyVersion)
        .filter_by(strategy_id=strategy.id, version_label="v2.0")
        .first()
    )
    if version2 is None:
        version2 = StrategyVersion(
            strategy_id=strategy.id,
            version_label="v2.0",
            git_commit="def456",
            branch_name="main",
            code_path="strategies/aapl_mean_reversion_v2.py",
            signal_name="z_score_mean_reversion_v2",
        )
        db.add(version2)
        db.flush()
        artifacts.append("strategy_version:v2.0")

    # ---- 3. Config snapshot v1 ----
    try:
        from app.models.strategy_config_snapshot import StrategyConfigSnapshot
        from app.services.config_snapshots import compute_config_hash, count_params, count_assumptions

        config1_json = {
            "params": {"lookback": 20, "entry_z": 2.0},
            "assumptions": {
                "transaction_cost_bps": 5,
                "slippage_bps": 5,
                "fill_model": "next_bar_open",
            },
        }
        cfg1_hash = compute_config_hash(config1_json)
        existing_cfg1 = (
            db.query(StrategyConfigSnapshot)
            .filter_by(strategy_id=strategy.id, config_hash=cfg1_hash)
            .first()
        )
        if existing_cfg1 is None:
            cfg1 = StrategyConfigSnapshot(
                strategy_id=strategy.id,
                strategy_version_id=version1.id,
                label="AAPL v1.0 config",
                source_type="manual_json",
                config_json=config1_json,
                config_hash=cfg1_hash,
                param_count=count_params(config1_json),
                assumption_count=count_assumptions(config1_json),
            )
            db.add(cfg1)
            db.flush()
            artifacts.append("config_snapshot:v1.0")
        else:
            cfg1 = existing_cfg1
    except Exception as exc:
        cfg1 = None
        print(f"[demo_seed] AAPL config v1 skipped: {exc}", file=sys.stderr)

    # ---- 4. Config snapshot v2 ----
    try:
        config2_json = {
            "params": {"lookback": 15, "entry_z": 1.8},
            "assumptions": {
                "transaction_cost_bps": 7,
                "slippage_bps": 7,
                "fill_model": "next_bar_open",
                "max_position_weight": 0.1,
            },
        }
        cfg2_hash = compute_config_hash(config2_json)
        existing_cfg2 = (
            db.query(StrategyConfigSnapshot)
            .filter_by(strategy_id=strategy.id, config_hash=cfg2_hash)
            .first()
        )
        if existing_cfg2 is None:
            cfg2 = StrategyConfigSnapshot(
                strategy_id=strategy.id,
                strategy_version_id=version2.id,
                label="AAPL v2.0 config",
                source_type="manual_json",
                config_json=config2_json,
                config_hash=cfg2_hash,
                param_count=count_params(config2_json),
                assumption_count=count_assumptions(config2_json),
            )
            db.add(cfg2)
            db.flush()
            artifacts.append("config_snapshot:v2.0")
    except Exception as exc:
        print(f"[demo_seed] AAPL config v2 skipped: {exc}", file=sys.stderr)

    # ---- 5. Universe snapshot v1 ----
    universe_snap = None
    try:
        from app.models.universe_snapshot import UniverseSnapshot
        from app.services.universe_snapshots import normalize_symbols, compute_universe_hash

        raw_symbols = ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN"]
        norm_symbols = normalize_symbols(raw_symbols)
        universe_meta = {
            "universe_type": "US_LARGE_CAP",
            "symbols": {
                "AAPL": {"sector": "Technology", "country": "US", "exchange": "NASDAQ"},
                "MSFT": {"sector": "Technology", "country": "US", "exchange": "NASDAQ"},
            },
        }
        u_hash = compute_universe_hash(norm_symbols, universe_meta)
        existing_u = (
            db.query(UniverseSnapshot)
            .filter_by(strategy_id=strategy.id, universe_hash=u_hash)
            .first()
        )
        if existing_u is None:
            universe_snap = UniverseSnapshot(
                strategy_id=strategy.id,
                strategy_version_id=version1.id,
                label="AAPL US Large Cap Universe v1",
                source_type="manual_json",
                symbols_json=norm_symbols,
                symbol_count=len(norm_symbols),
                metadata_json=universe_meta,
                universe_hash=u_hash,
            )
            db.add(universe_snap)
            db.flush()
            artifacts.append("universe_snapshot:v1.0")
        else:
            universe_snap = existing_u
    except Exception as exc:
        print(f"[demo_seed] AAPL universe snapshot skipped: {exc}", file=sys.stderr)

    # ---- 6. Signal snapshot ----
    signal_snap = None
    try:
        from app.models.signal_snapshot import SignalSnapshot
        from app.services.signal_snapshots import (
            summarize_signal_snapshot,
            compute_signal_hash,
        )

        sig_hash = compute_signal_hash(AAPL_SIGNALS)
        existing_sig = (
            db.query(SignalSnapshot)
            .filter_by(strategy_id=strategy.id, signal_hash=sig_hash)
            .first()
        )
        if existing_sig is None:
            summary = summarize_signal_snapshot(AAPL_SIGNALS)
            signal_snap = SignalSnapshot(
                strategy_id=strategy.id,
                strategy_version_id=version1.id,
                universe_snapshot_id=universe_snap.id if universe_snap else None,
                label="AAPL Signal 2024-01-02",
                signal_name="z_score_mean_reversion",
                source_type="manual_json",
                rows_json=AAPL_SIGNALS,
                row_count=summary.row_count,
                symbol_count=summary.symbol_count,
                symbols_json=summary.symbols,
                min_timestamp=summary.min_timestamp,
                max_timestamp=summary.max_timestamp,
                signal_value_count=summary.signal_value_count,
                missing_signal_count=summary.missing_signal_count,
                mean_value=summary.mean_value,
                min_value=summary.min_value,
                max_value=summary.max_value,
                stddev_value=summary.stddev_value,
                signal_hash=sig_hash,
                quality_score=summary.quality_score,
            )
            db.add(signal_snap)
            db.flush()
            artifacts.append("signal_snapshot:aapl_2024-01-02")
        else:
            signal_snap = existing_sig
    except Exception as exc:
        print(f"[demo_seed] AAPL signal snapshot skipped: {exc}", file=sys.stderr)

    # ---- 7. Dataset + DatasetSnapshot ----
    dataset_snap = None
    try:
        from app.models.dataset import Dataset
        from app.models.dataset_snapshot import DatasetSnapshot
        from app.services.data_quality import analyze_snapshot

        dataset = (
            db.query(Dataset)
            .filter_by(project_id=project.id, name="AAPL OHLCV 2024")
            .first()
        )
        if dataset is None:
            dataset = Dataset(
                project_id=project.id,
                name="AAPL OHLCV 2024",
                description="AAPL equity OHLCV demo dataset for 2024.",
                dataset_type="ohlcv",
                source_type="manual",
            )
            db.add(dataset)
            db.flush()
            artifacts.append("dataset:aapl_ohlcv_2024")

        existing_ds = (
            db.query(DatasetSnapshot)
            .filter_by(dataset_id=dataset.id, version_label="v1")
            .first()
        )
        if existing_ds is None:
            snap_summary = analyze_snapshot(AAPL_OHLCV)
            dataset_snap = DatasetSnapshot(
                dataset_id=dataset.id,
                version_label="v1",
                row_count=len(AAPL_OHLCV),
                health_score=snap_summary.health_score,
                rows_json=AAPL_OHLCV,
            )
            db.add(dataset_snap)
            db.flush()
            artifacts.append("dataset_snapshot:aapl_v1")
        else:
            dataset_snap = existing_ds
    except Exception as exc:
        print(f"[demo_seed] AAPL dataset snapshot skipped: {exc}", file=sys.stderr)

    # ---- 8. StrategyRun v1 ----
    run1 = None
    try:
        from app.models.strategy_run import StrategyRun

        run1 = (
            db.query(StrategyRun)
            .filter_by(strategy_id=strategy.id, run_name="AAPL Backtest v1")
            .first()
        )
        if run1 is None:
            run1 = StrategyRun(
                strategy_id=strategy.id,
                strategy_version_id=version1.id,
                dataset_snapshot_id=dataset_snap.id if dataset_snap else None,
                universe_snapshot_id=universe_snap.id if universe_snap else None,
                signal_snapshot_id=signal_snap.id if signal_snap else None,
                run_name="AAPL Backtest v1",
                run_type=RunType.backtest,
                status=RunStatus.completed,
                started_at=_utcnow(),
                completed_at=_utcnow(),
                params_json={"lookback_days": 20, "zscore_entry": 2.0},
                assumptions_json={
                    "transaction_cost_bps": 5,
                    "slippage_bps": 5,
                    "fill_model": "next_bar_open",
                },
                metrics_json={
                    "sharpe": 1.62,
                    "annual_return": 0.184,
                    "max_drawdown": -0.109,
                    "trade_count": 142,
                    "win_rate": 0.54,
                },
                universe_name="US_LARGE_CAP",
                notes="Demo baseline backtest run for AAPL mean reversion.",
            )
            db.add(run1)
            db.flush()
            artifacts.append("strategy_run:aapl_backtest_v1")
    except Exception as exc:
        print(f"[demo_seed] AAPL run v1 skipped: {exc}", file=sys.stderr)

    # ---- 9. StrategyRun v2 ----
    try:
        run2 = (
            db.query(StrategyRun)
            .filter_by(strategy_id=strategy.id, run_name="AAPL Backtest v2")
            .first()
        )
        if run2 is None:
            run2 = StrategyRun(
                strategy_id=strategy.id,
                strategy_version_id=version2.id,
                run_name="AAPL Backtest v2",
                run_type=RunType.backtest,
                status=RunStatus.completed,
                started_at=_utcnow(),
                completed_at=_utcnow(),
                params_json={"lookback_days": 15, "zscore_entry": 1.8},
                assumptions_json={
                    "transaction_cost_bps": 7,
                    "slippage_bps": 7,
                    "fill_model": "next_bar_open",
                },
                metrics_json={
                    "sharpe": 1.78,
                    "annual_return": 0.195,
                    "max_drawdown": -0.095,
                    "trade_count": 168,
                },
                universe_name="US_LARGE_CAP",
                notes="Demo improved backtest run for AAPL mean reversion v2.",
            )
            db.add(run2)
            db.flush()
            artifacts.append("strategy_run:aapl_backtest_v2")
    except Exception as exc:
        print(f"[demo_seed] AAPL run v2 skipped: {exc}", file=sys.stderr)

    # ---- 10. Backtest audit for run1 ----
    if include_audits and run1 is not None:
        try:
            from app.models.backtest_audit import BacktestAudit
            from app.models.backtest_issue import BacktestIssue
            from app.services.backtest_reality import run_backtest_audit

            existing_audit = (
                db.query(BacktestAudit)
                .filter_by(strategy_run_id=run1.id)
                .first()
            )
            if existing_audit is None:
                audit_result = run_backtest_audit(run1, data_evidence=None)
                audit = BacktestAudit(
                    strategy_run_id=run1.id,
                    trust_score=audit_result.trust_score,
                    lookahead_risk_score=audit_result.lookahead_risk_score,
                    cost_realism_score=audit_result.cost_realism_score,
                    fill_realism_score=audit_result.fill_realism_score,
                    liquidity_realism_score=audit_result.liquidity_realism_score,
                    borrow_realism_score=audit_result.borrow_realism_score,
                    data_quality_score=audit_result.data_quality_score,
                    overall_status=audit_result.overall_status,
                    summary=audit_result.summary,
                    cost_sensitivity_json=audit_result.cost_sensitivity_json,
                    fill_realism_json=audit_result.fill_realism_json,
                    fragility_summary_json=audit_result.fragility_summary_json,
                    cost_sensitivity_sweep_json=audit_result.cost_sensitivity_sweep_json,
                    fill_sensitivity_json=audit_result.fill_sensitivity_json,
                    penalty_attribution_json=audit_result.penalty_attribution_json,
                    improvement_checks_json=audit_result.improvement_checks_json,
                )
                db.add(audit)
                db.flush()
                for iss in audit_result.issues:
                    bi = BacktestIssue(
                        backtest_audit_id=audit.id,
                        issue_type=iss.issue_type,
                        severity=iss.severity,
                        title=iss.title,
                        description=iss.description,
                        evidence_json=iss.evidence_json,
                        suggested_check=iss.suggested_check,
                    )
                    db.add(bi)
                db.flush()
                artifacts.append("backtest_audit:aapl_run_v1")
        except Exception as exc:
            print(f"[demo_seed] AAPL backtest audit skipped: {exc}", file=sys.stderr)

    # ---- 11. Reliability score ----
    try:
        from app.models.strategy_reliability_score import StrategyReliabilityScore
        from app.services.strategy_reliability import compute_reliability_score

        score_dict = compute_reliability_score(str(strategy.id), db)
        _EXCLUDE_KEYS = {"strategy_id", "generated_at"}
        score = StrategyReliabilityScore(
            strategy_id=strategy.id,
            generated_at=score_dict.get("generated_at") or _utcnow(),
            **{k: v for k, v in score_dict.items() if k not in _EXCLUDE_KEYS},
        )
        db.add(score)
        db.flush()
        artifacts.append("reliability_score:aapl")
    except Exception as exc:
        print(f"[demo_seed] AAPL reliability score skipped: {exc}", file=sys.stderr)

    # ---- 12. Report ----
    if include_reports:
        try:
            from app.services.reports import generate_strategy_reliability_report, persist_report

            report_result = generate_strategy_reliability_report(strategy.id, db)
            persist_report(report_result, db)
            artifacts.append("report:strategy_reliability:aapl")
        except Exception as exc:
            print(f"[demo_seed] AAPL report skipped: {exc}", file=sys.stderr)

    return artifacts


# ---------------------------------------------------------------------------
# FX strategy seeder (review / partial)
# ---------------------------------------------------------------------------

def _seed_fx_strategy(
    db: Session,
    strategy,
    org,
    project,
    include_audits: bool,
    include_reports: bool,
) -> list[str]:
    """Create evidence artifacts for the FX carry demo strategy."""
    artifacts: list[str] = []

    # ---- 1. StrategyVersion v1.0 ----
    from app.models.strategy_version import StrategyVersion

    version1 = (
        db.query(StrategyVersion)
        .filter_by(strategy_id=strategy.id, version_label="v1.0")
        .first()
    )
    if version1 is None:
        version1 = StrategyVersion(
            strategy_id=strategy.id,
            version_label="v1.0",
            git_commit=None,
            branch_name="main",
            code_path="strategies/fx_carry.py",
            signal_name="fx_carry_signal",
        )
        db.add(version1)
        db.flush()
        artifacts.append("strategy_version:v1.0")

    # ---- 2. StrategyVersion v2.0 ----
    version2 = (
        db.query(StrategyVersion)
        .filter_by(strategy_id=strategy.id, version_label="v2.0")
        .first()
    )
    if version2 is None:
        version2 = StrategyVersion(
            strategy_id=strategy.id,
            version_label="v2.0",
            git_commit=None,
            branch_name="main",
            signal_name="fx_carry_signal_v2",
        )
        db.add(version2)
        db.flush()
        artifacts.append("strategy_version:v2.0")

    # ---- 3 & 4. Config snapshots ----
    try:
        from app.models.strategy_config_snapshot import StrategyConfigSnapshot
        from app.services.config_snapshots import compute_config_hash, count_params, count_assumptions

        config1_json = {
            "params": {"carry_lookback": 90},
            "assumptions": {
                "fill_model": "close",
                "slippage_bps": 2,
                "transaction_cost_bps": 3,
            },
        }
        cfg1_hash = compute_config_hash(config1_json)
        if not db.query(StrategyConfigSnapshot).filter_by(strategy_id=strategy.id, config_hash=cfg1_hash).first():
            db.add(StrategyConfigSnapshot(
                strategy_id=strategy.id,
                strategy_version_id=version1.id,
                label="FX v1.0 config",
                source_type="manual_json",
                config_json=config1_json,
                config_hash=cfg1_hash,
                param_count=count_params(config1_json),
                assumption_count=count_assumptions(config1_json),
            ))
            db.flush()
            artifacts.append("config_snapshot:v1.0")

        config2_json = {
            "params": {"carry_lookback": 60},
            "assumptions": {
                "fill_model": "same_close",
                "slippage_bps": 1,
                "transaction_cost_bps": 3,
            },
        }
        cfg2_hash = compute_config_hash(config2_json)
        if not db.query(StrategyConfigSnapshot).filter_by(strategy_id=strategy.id, config_hash=cfg2_hash).first():
            db.add(StrategyConfigSnapshot(
                strategy_id=strategy.id,
                strategy_version_id=version2.id,
                label="FX v2.0 config",
                source_type="manual_json",
                config_json=config2_json,
                config_hash=cfg2_hash,
                param_count=count_params(config2_json),
                assumption_count=count_assumptions(config2_json),
            ))
            db.flush()
            artifacts.append("config_snapshot:v2.0")
    except Exception as exc:
        print(f"[demo_seed] FX config snapshots skipped: {exc}", file=sys.stderr)

    # ---- 5. Universe snapshot ----
    try:
        from app.models.universe_snapshot import UniverseSnapshot
        from app.services.universe_snapshots import normalize_symbols, compute_universe_hash

        fx_symbols = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD"]
        norm_fx = normalize_symbols(fx_symbols)
        fx_u_meta = {"universe_type": "G10_FX"}
        fx_u_hash = compute_universe_hash(norm_fx, fx_u_meta)
        if not db.query(UniverseSnapshot).filter_by(strategy_id=strategy.id, universe_hash=fx_u_hash).first():
            db.add(UniverseSnapshot(
                strategy_id=strategy.id,
                strategy_version_id=version1.id,
                label="FX G10 Universe v1",
                source_type="manual_json",
                symbols_json=norm_fx,
                symbol_count=len(norm_fx),
                metadata_json=fx_u_meta,
                universe_hash=fx_u_hash,
            ))
            db.flush()
            artifacts.append("universe_snapshot:fx_v1")
    except Exception as exc:
        print(f"[demo_seed] FX universe snapshot skipped: {exc}", file=sys.stderr)

    # ---- 6. Signal snapshot (has missing / outliers) ----
    try:
        from app.models.signal_snapshot import SignalSnapshot
        from app.services.signal_snapshots import summarize_signal_snapshot, compute_signal_hash

        fx_sig_hash = compute_signal_hash(FX_SIGNALS)
        if not db.query(SignalSnapshot).filter_by(strategy_id=strategy.id, signal_hash=fx_sig_hash).first():
            summary = summarize_signal_snapshot(FX_SIGNALS)
            db.add(SignalSnapshot(
                strategy_id=strategy.id,
                strategy_version_id=version1.id,
                label="FX Carry Signal 2024-01-02",
                signal_name="fx_carry_signal",
                source_type="manual_json",
                rows_json=FX_SIGNALS,
                row_count=summary.row_count,
                symbol_count=summary.symbol_count,
                symbols_json=summary.symbols,
                min_timestamp=summary.min_timestamp,
                max_timestamp=summary.max_timestamp,
                signal_value_count=summary.signal_value_count,
                missing_signal_count=summary.missing_signal_count,
                mean_value=summary.mean_value,
                min_value=summary.min_value,
                max_value=summary.max_value,
                stddev_value=summary.stddev_value,
                signal_hash=fx_sig_hash,
                quality_score=summary.quality_score,
            ))
            db.flush()
            artifacts.append("signal_snapshot:fx_2024-01-02")
    except Exception as exc:
        print(f"[demo_seed] FX signal snapshot skipped: {exc}", file=sys.stderr)

    # ---- 7. Dataset + DatasetSnapshot ----
    run1 = None
    try:
        from app.models.dataset import Dataset
        from app.models.dataset_snapshot import DatasetSnapshot
        from app.services.data_quality import analyze_snapshot
        from app.models.strategy_run import StrategyRun

        dataset = (
            db.query(Dataset).filter_by(project_id=project.id, name="FX OHLCV 2024").first()
        )
        if dataset is None:
            dataset = Dataset(
                project_id=project.id,
                name="FX OHLCV 2024",
                description="FX OHLCV demo dataset with deliberate quality issues.",
                dataset_type="ohlcv",
                source_type="manual",
            )
            db.add(dataset)
            db.flush()
            artifacts.append("dataset:fx_ohlcv_2024")

        fx_ds = (
            db.query(DatasetSnapshot).filter_by(dataset_id=dataset.id, version_label="v1").first()
        )
        if fx_ds is None:
            snap_summary = analyze_snapshot(FX_OHLCV)
            fx_ds = DatasetSnapshot(
                dataset_id=dataset.id,
                version_label="v1",
                row_count=len(FX_OHLCV),
                health_score=snap_summary.health_score,
                rows_json=FX_OHLCV,
            )
            db.add(fx_ds)
            db.flush()
            artifacts.append("dataset_snapshot:fx_v1")

        # ---- 8. StrategyRun — no dataset link (missing evidence) ----
        run1 = (
            db.query(StrategyRun).filter_by(strategy_id=strategy.id, run_name="FX Carry Backtest v1").first()
        )
        if run1 is None:
            run1 = StrategyRun(
                strategy_id=strategy.id,
                strategy_version_id=version1.id,
                run_name="FX Carry Backtest v1",
                run_type=RunType.backtest,
                status=RunStatus.completed,
                started_at=_utcnow(),
                completed_at=_utcnow(),
                params_json={"carry_lookback": 90},
                assumptions_json={
                    "fill_model": "close",
                    "slippage_bps": 1,
                    "transaction_cost_bps": 3,
                },
                metrics_json={
                    "sharpe": 0.8,
                    "annual_return": 0.08,
                    "max_drawdown": -0.22,
                },
                universe_name="G10_FX",
                notes="FX carry demo run — missing dataset evidence link.",
            )
            db.add(run1)
            db.flush()
            artifacts.append("strategy_run:fx_backtest_v1")
    except Exception as exc:
        print(f"[demo_seed] FX dataset/run skipped: {exc}", file=sys.stderr)

    # ---- 9. Backtest audit ----
    if include_audits and run1 is not None:
        try:
            from app.models.backtest_audit import BacktestAudit
            from app.models.backtest_issue import BacktestIssue
            from app.services.backtest_reality import run_backtest_audit

            if not db.query(BacktestAudit).filter_by(strategy_run_id=run1.id).first():
                audit_result = run_backtest_audit(run1, data_evidence=None)
                audit = BacktestAudit(
                    strategy_run_id=run1.id,
                    trust_score=audit_result.trust_score,
                    lookahead_risk_score=audit_result.lookahead_risk_score,
                    cost_realism_score=audit_result.cost_realism_score,
                    fill_realism_score=audit_result.fill_realism_score,
                    liquidity_realism_score=audit_result.liquidity_realism_score,
                    borrow_realism_score=audit_result.borrow_realism_score,
                    data_quality_score=audit_result.data_quality_score,
                    overall_status=audit_result.overall_status,
                    summary=audit_result.summary,
                    cost_sensitivity_json=audit_result.cost_sensitivity_json,
                    fill_realism_json=audit_result.fill_realism_json,
                    fragility_summary_json=audit_result.fragility_summary_json,
                    cost_sensitivity_sweep_json=audit_result.cost_sensitivity_sweep_json,
                    fill_sensitivity_json=audit_result.fill_sensitivity_json,
                    penalty_attribution_json=audit_result.penalty_attribution_json,
                    improvement_checks_json=audit_result.improvement_checks_json,
                )
                db.add(audit)
                db.flush()
                for iss in audit_result.issues:
                    db.add(BacktestIssue(
                        backtest_audit_id=audit.id,
                        issue_type=iss.issue_type,
                        severity=iss.severity,
                        title=iss.title,
                        description=iss.description,
                        evidence_json=iss.evidence_json,
                        suggested_check=iss.suggested_check,
                    ))
                db.flush()
                artifacts.append("backtest_audit:fx_run_v1")
        except Exception as exc:
            print(f"[demo_seed] FX backtest audit skipped: {exc}", file=sys.stderr)

    # ---- 10. Reliability score ----
    try:
        from app.models.strategy_reliability_score import StrategyReliabilityScore
        from app.services.strategy_reliability import compute_reliability_score

        score_dict = compute_reliability_score(str(strategy.id), db)
        _EXCL = {"strategy_id", "generated_at"}
        db.add(StrategyReliabilityScore(
            strategy_id=strategy.id,
            generated_at=score_dict.get("generated_at") or _utcnow(),
            **{k: v for k, v in score_dict.items() if k not in _EXCL},
        ))
        db.flush()
        artifacts.append("reliability_score:fx")
    except Exception as exc:
        print(f"[demo_seed] FX reliability score skipped: {exc}", file=sys.stderr)

    return artifacts


# ---------------------------------------------------------------------------
# Crypto strategy seeder (under-instrumented)
# ---------------------------------------------------------------------------

def _seed_crypto_strategy(
    db: Session,
    strategy,
    org,
    project,
    include_audits: bool,
    include_reports: bool,
) -> list[str]:
    """Create minimal evidence artifacts for the crypto momentum demo strategy."""
    artifacts: list[str] = []

    # ---- 1. StrategyVersion v1.0 ----
    from app.models.strategy_version import StrategyVersion

    version1 = (
        db.query(StrategyVersion)
        .filter_by(strategy_id=strategy.id, version_label="v1.0")
        .first()
    )
    if version1 is None:
        version1 = StrategyVersion(
            strategy_id=strategy.id,
            version_label="v1.0",
            git_commit=None,
            branch_name="main",
            signal_name="crypto_momentum_signal",
        )
        db.add(version1)
        db.flush()
        artifacts.append("strategy_version:v1.0")

    # ---- 2. Config snapshot (minimal) ----
    try:
        from app.models.strategy_config_snapshot import StrategyConfigSnapshot
        from app.services.config_snapshots import compute_config_hash, count_params, count_assumptions

        crypto_config = {"params": {"momentum_window": 14}}
        cfg_hash = compute_config_hash(crypto_config)
        if not db.query(StrategyConfigSnapshot).filter_by(strategy_id=strategy.id, config_hash=cfg_hash).first():
            db.add(StrategyConfigSnapshot(
                strategy_id=strategy.id,
                strategy_version_id=version1.id,
                label="Crypto v1.0 config",
                source_type="manual_json",
                config_json=crypto_config,
                config_hash=cfg_hash,
                param_count=count_params(crypto_config),
                assumption_count=count_assumptions(crypto_config),
            ))
            db.flush()
            artifacts.append("config_snapshot:crypto_v1")
    except Exception as exc:
        print(f"[demo_seed] Crypto config snapshot skipped: {exc}", file=sys.stderr)

    # No universe snapshot, no signal snapshot (deliberate)

    # ---- 5. Dataset + DatasetSnapshot (sparse) ----
    try:
        from app.models.dataset import Dataset
        from app.models.dataset_snapshot import DatasetSnapshot
        from app.services.data_quality import analyze_snapshot

        dataset = (
            db.query(Dataset).filter_by(project_id=project.id, name="Crypto OHLCV").first()
        )
        if dataset is None:
            dataset = Dataset(
                project_id=project.id,
                name="Crypto OHLCV",
                description="Sparse crypto OHLCV demo dataset.",
                dataset_type="ohlcv",
                source_type="manual",
            )
            db.add(dataset)
            db.flush()
            artifacts.append("dataset:crypto_ohlcv")

        if not db.query(DatasetSnapshot).filter_by(dataset_id=dataset.id, version_label="v1").first():
            snap_summary = analyze_snapshot(CRYPTO_ROWS)
            db.add(DatasetSnapshot(
                dataset_id=dataset.id,
                version_label="v1",
                row_count=len(CRYPTO_ROWS),
                health_score=snap_summary.health_score,
                rows_json=CRYPTO_ROWS,
            ))
            db.flush()
            artifacts.append("dataset_snapshot:crypto_v1")
    except Exception as exc:
        print(f"[demo_seed] Crypto dataset snapshot skipped: {exc}", file=sys.stderr)

    # ---- 6. StrategyRun — sparse, no assumptions, no dataset link ----
    run1 = None
    try:
        from app.models.strategy_run import StrategyRun

        run1 = (
            db.query(StrategyRun).filter_by(strategy_id=strategy.id, run_name="Crypto Momentum Backtest v1").first()
        )
        if run1 is None:
            run1 = StrategyRun(
                strategy_id=strategy.id,
                strategy_version_id=version1.id,
                run_name="Crypto Momentum Backtest v1",
                run_type=RunType.backtest,
                status=RunStatus.completed,
                started_at=_utcnow(),
                completed_at=_utcnow(),
                params_json={"momentum_window": 14},
                assumptions_json=None,
                metrics_json={"sharpe": None, "annual_return": 0.15},
                notes="Sparse crypto demo run — minimal evidence.",
            )
            db.add(run1)
            db.flush()
            artifacts.append("strategy_run:crypto_backtest_v1")
    except Exception as exc:
        print(f"[demo_seed] Crypto run skipped: {exc}", file=sys.stderr)

    # No backtest audit (deliberate)

    # ---- 8. Reliability score (likely insufficient_evidence) ----
    try:
        from app.models.strategy_reliability_score import StrategyReliabilityScore
        from app.services.strategy_reliability import compute_reliability_score

        score_dict = compute_reliability_score(str(strategy.id), db)
        _EXCL2 = {"strategy_id", "generated_at"}
        db.add(StrategyReliabilityScore(
            strategy_id=strategy.id,
            generated_at=score_dict.get("generated_at") or _utcnow(),
            **{k: v for k, v in score_dict.items() if k not in _EXCL2},
        ))
        db.flush()
        artifacts.append("reliability_score:crypto")
    except Exception as exc:
        print(f"[demo_seed] Crypto reliability score skipped: {exc}", file=sys.stderr)

    return artifacts


# ---------------------------------------------------------------------------
# Public API: seed_demo_data
# ---------------------------------------------------------------------------

def seed_demo_data(
    db: Session,
    *,
    mode: str = "extend",
    confirm_reset: bool = False,
    include_reports: bool = True,
    include_alerts: bool = True,
    include_backtest_audits: bool = True,
) -> dict:
    """Create / extend the demo dataset.

    Parameters
    ----------
    mode:
        "extend"         — create missing records, leave existing alone.
        "reset_demo_only" — delete the demo org and re-seed from scratch
                            (requires confirm_reset=True).
    confirm_reset:
        Must be True when mode="reset_demo_only".
    include_reports:
        Generate strategy reliability reports (slow).
    include_alerts:
        Run alert generation after seeding.
    include_backtest_audits:
        Compute backtest reality checks.

    Returns
    -------
    dict suitable for DemoSeedResponse.
    """
    from app.models.organization import Organization
    from app.models.project import Project
    from app.models.audit_timeline_event import AuditTimelineEvent

    # ---- Step 1: handle reset ----
    if mode == "reset_demo_only":
        if not confirm_reset:
            raise ValueError("confirm_reset must be True to reset demo data.")
        # Use raw SQL DELETE to avoid SQLAlchemy ORM cascade nullifying non-null FKs.
        # The DB-level ondelete="CASCADE" handles child rows.
        from sqlalchemy import text as _text

        demo_org_row = db.query(Organization).filter(Organization.name == DEMO_ORG_NAME).first()
        found_org = demo_org_row is not None
        if found_org:
            org_name_for_delete = demo_org_row.name
            # Expire ORM identity map so it doesn't interfere with raw delete
            db.expunge_all()
            # Use name-based delete to avoid SQLite UUID format mismatch
            db.execute(
                _text("DELETE FROM organizations WHERE name = :name"),
                {"name": org_name_for_delete},
            )
            db.commit()
        return {
            "mode": mode,
            "summary": "Demo data reset.",
            "organization_id": None,
            "project_id": None,
            "strategy_ids": [],
            "created_counts": {},
            "reused_counts": {},
            "reset_counts": {"organizations": 1 if found_org else 0},
            "generated_artifacts": [],
            "warnings": [],
        }

    # ---- Step 2: get or create demo org ----
    demo_org = db.query(Organization).filter(Organization.name == DEMO_ORG_NAME).first()
    created_org = False
    if demo_org is None:
        # Need a unique slug — use a stable one derived from the name
        import re
        slug_candidate = re.sub(r"[^a-z0-9]+", "-", DEMO_ORG_NAME.lower()).strip("-")
        demo_org = Organization(name=DEMO_ORG_NAME, slug=slug_candidate)
        db.add(demo_org)
        db.flush()
        created_org = True

    # ---- Step 3: get or create demo project ----
    demo_project = (
        db.query(Project)
        .filter(Project.organization_id == demo_org.id, Project.slug == DEMO_PROJECT_SLUG)
        .first()
    )
    created_project = False
    if demo_project is None:
        demo_project = Project(
            organization_id=demo_org.id,
            name=DEMO_PROJECT_NAME,
            slug=DEMO_PROJECT_SLUG,
            description="Demo project for QuantFidelity showcase.",
        )
        db.add(demo_project)
        db.flush()
        created_project = True

    # ---- Step 4: create the 3 demo strategies ----
    strategy_ids: list[str] = []
    all_artifacts: list[str] = []
    created_strategies: list[str] = []
    reused_strategies: list[str] = []
    warnings: list[str] = []

    # AAPL — index 0
    try:
        aapl_def = DEMO_STRATEGIES[0]
        aapl_strategy, aapl_created = _get_or_create_strategy(
            db,
            demo_project.id,
            aapl_def["name"],
            aapl_def["slug"],
            aapl_def["asset_class"],
            aapl_def["status"],
        )
        strategy_ids.append(str(aapl_strategy.id))
        if aapl_created:
            created_strategies.append(aapl_def["name"])
        else:
            reused_strategies.append(aapl_def["name"])
        aapl_artifacts = _seed_aapl_strategy(
            db,
            aapl_strategy,
            demo_org,
            demo_project,
            include_backtest_audits,
            include_reports,
        )
        all_artifacts.extend(aapl_artifacts)
    except Exception as exc:
        warnings.append(f"AAPL strategy seed failed: {str(exc)[:200]}")
        print(f"[demo_seed] AAPL strategy seed failed: {exc}", file=sys.stderr)

    # FX — index 1
    try:
        fx_def = DEMO_STRATEGIES[1]
        fx_strategy, fx_created = _get_or_create_strategy(
            db,
            demo_project.id,
            fx_def["name"],
            fx_def["slug"],
            fx_def["asset_class"],
            fx_def["status"],
        )
        strategy_ids.append(str(fx_strategy.id))
        if fx_created:
            created_strategies.append(fx_def["name"])
        else:
            reused_strategies.append(fx_def["name"])
        fx_artifacts = _seed_fx_strategy(
            db,
            fx_strategy,
            demo_org,
            demo_project,
            include_backtest_audits,
            include_reports,
        )
        all_artifacts.extend(fx_artifacts)
    except Exception as exc:
        warnings.append(f"FX strategy seed failed: {str(exc)[:200]}")
        print(f"[demo_seed] FX strategy seed failed: {exc}", file=sys.stderr)

    # Crypto — index 2
    try:
        crypto_def = DEMO_STRATEGIES[2]
        crypto_strategy, crypto_created = _get_or_create_strategy(
            db,
            demo_project.id,
            crypto_def["name"],
            crypto_def["slug"],
            crypto_def["asset_class"],
            crypto_def["status"],
        )
        strategy_ids.append(str(crypto_strategy.id))
        if crypto_created:
            created_strategies.append(crypto_def["name"])
        else:
            reused_strategies.append(crypto_def["name"])
        crypto_artifacts = _seed_crypto_strategy(
            db,
            crypto_strategy,
            demo_org,
            demo_project,
            include_backtest_audits,
            include_reports,
        )
        all_artifacts.extend(crypto_artifacts)
    except Exception as exc:
        warnings.append(f"Crypto strategy seed failed: {str(exc)[:200]}")
        print(f"[demo_seed] Crypto strategy seed failed: {exc}", file=sys.stderr)

    # ---- Step 5: alerts ----
    if include_alerts:
        try:
            from app.services.alerts import generate_alerts
            org_id_str = str(demo_org.id)
            generate_alerts(db, org_id_str)
        except Exception as exc:
            warnings.append(f"Alert generation skipped: {str(exc)[:100]}")

    # ---- Step 6: demo_seeded timeline event ----
    event = AuditTimelineEvent(
        organization_id=demo_org.id,
        project_id=demo_project.id,
        strategy_id=None,
        event_type="demo_seeded",
        title="Demo data seeded",
        description=f"Demo data seeded in {mode} mode.",
        source_type="admin",
        source_id=str(demo_org.id),
        severity=Severity.info,
        metadata_json={
            "mode": mode,
            "created_org": created_org,
            "created_project": created_project,
        },
    )
    db.add(event)
    db.commit()

    return {
        "mode": mode,
        "summary": (
            f"Demo seed complete. "
            f"{'Created' if created_org else 'Reused'} org, "
            f"{'created' if created_project else 'reused'} project, "
            f"{len(strategy_ids)} strategy(ies) seeded."
        ),
        "organization_id": str(demo_org.id),
        "project_id": str(demo_project.id),
        "strategy_ids": strategy_ids,
        "created_counts": {
            "strategies": len(created_strategies),
            "artifacts": len(all_artifacts),
        },
        "reused_counts": {
            "strategies": len(reused_strategies),
        },
        "reset_counts": {},
        "generated_artifacts": all_artifacts,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# Public API: get_demo_status
# ---------------------------------------------------------------------------

def get_demo_status(db: Session) -> dict:
    """Return a summary of the current demo data state (read-only)."""
    from app.models.organization import Organization
    from app.models.project import Project
    from app.models.strategy import Strategy
    from app.models.audit_timeline_event import AuditTimelineEvent

    org = db.query(Organization).filter(Organization.name == DEMO_ORG_NAME).first()
    if not org:
        return {
            "demo_org_exists": False,
            "demo_project_exists": False,
            "strategy_count": 0,
            "demo_strategy_names": [],
            "last_seeded_at": None,
            "summary": "Demo data not yet seeded.",
        }

    proj = db.query(Project).filter(Project.organization_id == org.id).first()
    strats = (
        db.query(Strategy).filter(Strategy.project_id == proj.id).all()
        if proj else []
    )
    last_event = (
        db.query(AuditTimelineEvent)
        .filter(
            AuditTimelineEvent.organization_id == org.id,
            AuditTimelineEvent.event_type == "demo_seeded",
        )
        .order_by(AuditTimelineEvent.created_at.desc())
        .first()
    )
    return {
        "demo_org_exists": True,
        "demo_project_exists": proj is not None,
        "strategy_count": len(strats),
        "demo_strategy_names": [s.name for s in strats],
        "last_seeded_at": last_event.created_at if last_event else None,
        "summary": f"Demo org exists with {len(strats)} strategy(ies).",
    }
