"""Demo seed service — M46 + Clean Realistic Demo (v2).

Entry points:
  seed_demo_data(db, ...)   — create / extend demo data
  get_demo_status(db)       — describe current demo state (read-only)

Modes
-----
extend               — idempotent; creates missing records, leaves existing.
reset_demo_only      — deletes the demo org and re-seeds (legacy).
clean_realistic_demo — wipes ALL junk data from every table (strategies,
                       runs, snapshots, audits, alerts, timeline events, …)
                       then creates a small, high-quality demo workspace that
                       tells a clear product story.  workspace_members and
                       auth_users are preserved so logged-in sessions survive
                       the reset.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone

from sqlalchemy import text as _text
from sqlalchemy.orm import Session

from app.core.constants import (
    EventType,
    RunStatus,
    RunType,
    Severity,
)

# ---------------------------------------------------------------------------
# Demo constants — stable identifiers
# ---------------------------------------------------------------------------

DEMO_ORG_NAME = "Alpha Reliability Lab"
DEMO_ORG_SLUG = "alpha-reliability-lab"
DEMO_PROJECT_NAME = "Strategy Reliability Demo Portfolio"
DEMO_PROJECT_SLUG = "strategy-reliability-demo"

DEMO_STRATEGIES = [
    {
        "name": "AAPL Mean Reversion v1",
        "slug": "aapl-mean-reversion-v1",
        "asset_class": "equity",
        "status": "active",
        "story": "healthy",
    },
    {
        "name": "Global Futures Trend Model",
        "slug": "global-futures-trend-model",
        "asset_class": "future",
        "status": "active",
        "story": "review",
    },
    {
        "name": "Crypto Momentum Intraday",
        "slug": "crypto-momentum-intraday",
        "asset_class": "crypto",
        "status": "active",
        "story": "weak",
    },
]

# ---------------------------------------------------------------------------
# Fixed dates for deterministic output
# ---------------------------------------------------------------------------

_BASE_DATE = datetime(2026, 6, 1, 9, 0, 0, tzinfo=timezone.utc)

def _dt(offset_days: float = 0, offset_hours: float = 0) -> datetime:
    return _BASE_DATE + timedelta(days=offset_days, hours=offset_hours)

def _date_str(offset_days: int = 0) -> str:
    d = (_BASE_DATE + timedelta(days=offset_days)).date()
    return d.isoformat()

# ---------------------------------------------------------------------------
# Demo data tables: realistic OHLCV / signal rows
# ---------------------------------------------------------------------------

# AAPL: clean, realistic equity OHLCV across 5 symbols, 5 dates each
_AAPL_OHLCV = []
_aapl_prices = {
    "AAPL":  [(189.5, 191.8, 188.3, 190.2, 68_200_000), (190.2, 192.1, 189.4, 191.8, 61_400_000),
              (191.8, 193.5, 190.7, 192.4, 55_800_000), (192.4, 194.0, 191.2, 193.1, 58_100_000),
              (193.1, 194.8, 192.0, 194.3, 63_700_000)],
    "MSFT":  [(415.2, 417.6, 413.8, 416.4, 19_300_000), (416.4, 418.5, 415.1, 417.8, 17_800_000),
              (417.8, 420.0, 416.5, 419.2, 20_100_000), (419.2, 421.3, 418.0, 420.5, 18_600_000),
              (420.5, 422.8, 419.1, 421.7, 21_200_000)],
    "NVDA":  [(875.3, 885.0, 872.1, 881.4, 42_100_000), (881.4, 891.2, 878.5, 888.6, 38_700_000),
              (888.6, 895.4, 884.2, 893.1, 44_300_000), (893.1, 899.8, 889.7, 897.2, 40_500_000),
              (897.2, 905.0, 894.1, 902.8, 46_800_000)],
    "GOOGL": [(175.4, 177.2, 174.6, 176.3, 22_400_000), (176.3, 178.1, 175.4, 177.5, 20_800_000),
              (177.5, 179.3, 176.7, 178.8, 23_100_000), (178.8, 180.5, 177.9, 179.7, 21_600_000),
              (179.7, 181.4, 178.8, 180.9, 24_300_000)],
    "AMZN":  [(184.2, 186.5, 183.4, 185.6, 31_500_000), (185.6, 187.8, 184.7, 186.9, 29_200_000),
              (186.9, 189.1, 185.8, 188.2, 33_800_000), (188.2, 190.4, 187.1, 189.5, 30_700_000),
              (189.5, 191.7, 188.4, 190.8, 35_100_000)],
}
for sym, rows in _aapl_prices.items():
    for i, (o, h, l, c, v) in enumerate(rows):
        _AAPL_OHLCV.append({"symbol": sym, "timestamp": _date_str(i), "open": o, "high": h, "low": l, "close": c, "volume": v})

# AAPL signals: z-scores, realistic range, full coverage
_AAPL_SIGNALS = [
    {"symbol": "AAPL",  "timestamp": _date_str(4), "signal":  1.53},
    {"symbol": "MSFT",  "timestamp": _date_str(4), "signal": -0.42},
    {"symbol": "NVDA",  "timestamp": _date_str(4), "signal":  0.87},
    {"symbol": "GOOGL", "timestamp": _date_str(4), "signal": -1.15},
    {"symbol": "AMZN",  "timestamp": _date_str(4), "signal":  0.31},
    {"symbol": "AAPL",  "timestamp": _date_str(3), "signal":  1.28},
    {"symbol": "MSFT",  "timestamp": _date_str(3), "signal": -0.67},
    {"symbol": "NVDA",  "timestamp": _date_str(3), "signal":  1.04},
    {"symbol": "GOOGL", "timestamp": _date_str(3), "signal": -0.93},
    {"symbol": "AMZN",  "timestamp": _date_str(3), "signal":  0.55},
    {"symbol": "AAPL",  "timestamp": _date_str(2), "signal":  1.71},
    {"symbol": "MSFT",  "timestamp": _date_str(2), "signal": -0.18},
    {"symbol": "NVDA",  "timestamp": _date_str(2), "signal":  0.73},
    {"symbol": "GOOGL", "timestamp": _date_str(2), "signal": -1.34},
    {"symbol": "AMZN",  "timestamp": _date_str(2), "signal":  0.92},
]

# Global futures: liquid markets across equity index (ES, NQ), rates (ZN),
# FX (6E), and commodities (CL). 5 instruments, 2 dates; 6E volume is None on
# one row (intentional data-quality flag). (Var name kept for minimal churn.)
_FX_OHLCV = [
    {"symbol": "ES", "timestamp": _date_str(-30), "open": 5432.50, "high": 5458.75, "low": 5421.00, "close": 5450.25, "volume": 1_180_000},
    {"symbol": "NQ", "timestamp": _date_str(-30), "open": 19260.0, "high": 19345.0, "low": 19210.0, "close": 19318.0, "volume": 420_000},
    {"symbol": "ZN", "timestamp": _date_str(-30), "open": 110.45, "high": 110.72, "low": 110.31, "close": 110.59, "volume": 1_650_000},
    {"symbol": "6E", "timestamp": _date_str(-30), "open": 1.0824, "high": 1.0857, "low": 1.0805, "close": 1.0841, "volume": None},  # intentional null
    {"symbol": "CL", "timestamp": _date_str(-30), "open": 78.20, "high": 78.95, "low": 77.80, "close": 78.64, "volume": 540_000},
    {"symbol": "ES", "timestamp": _date_str(-29), "open": 5450.25, "high": 5479.00, "low": 5440.50, "close": 5468.75, "volume": 1_205_000},
    {"symbol": "NQ", "timestamp": _date_str(-29), "open": 19318.0, "high": 19402.0, "low": 19280.0, "close": 19377.0, "volume": 408_000},
    {"symbol": "ZN", "timestamp": _date_str(-29), "open": 110.59, "high": 110.81, "low": 110.42, "close": 110.68, "volume": 1_590_000},
    {"symbol": "6E", "timestamp": _date_str(-29), "open": 1.0841, "high": 1.0874, "low": 1.0823, "close": 1.0859, "volume": 138_000},
    {"symbol": "CL", "timestamp": _date_str(-29), "open": 78.64, "high": 79.30, "low": 78.10, "close": 79.05, "volume": 525_000},
]

# Global futures trend signal (time-series momentum); one missing value.
_FX_SIGNALS = [
    {"symbol": "ES", "timestamp": _date_str(-30), "signal":  0.62},
    {"symbol": "NQ", "timestamp": _date_str(-30), "signal":  None},   # missing
    {"symbol": "ZN", "timestamp": _date_str(-30), "signal": -0.48},
    {"symbol": "6E", "timestamp": _date_str(-30), "signal":  0.21},
    {"symbol": "CL", "timestamp": _date_str(-30), "signal":  0.77},
    {"symbol": "ES", "timestamp": _date_str(-29), "signal":  0.58},
    {"symbol": "NQ", "timestamp": _date_str(-29), "signal":  0.34},
    {"symbol": "ZN", "timestamp": _date_str(-29), "signal": -0.41},
]

# Crypto: sparse rows, suspicious price spike to trigger quality flag
_CRYPTO_OHLCV = [
    {"symbol": "BTCUSD", "timestamp": _date_str(-5), "open": 68_400.0, "high": 69_850.0, "low": 67_900.0, "close": 69_120.0, "volume": 28_400},
    {"symbol": "ETHUSD", "timestamp": _date_str(-5), "open":  3_580.0, "high":  3_645.0, "low":  3_520.0, "close":  3_612.0, "volume": 15_200},
    {"symbol": "SOLUSD", "timestamp": _date_str(-5), "open":   172.4,  "high":   178.1,  "low":   170.8,  "close":   176.2,  "volume":  8_600},
    {"symbol": "BTCUSD", "timestamp": _date_str(-4), "open": 69_120.0, "high": 85_000.0, "low": 68_800.0, "close": 84_500.0, "volume": 41_800},  # suspicious spike
    {"symbol": "ETHUSD", "timestamp": _date_str(-4), "open":  3_612.0, "high":  3_680.0, "low":  3_590.0, "close":  3_655.0, "volume": 14_900},
    {"symbol": "SOLUSD", "timestamp": _date_str(-4), "open":   176.2,  "high":   182.5,  "low":   174.1,  "close":   180.3,  "volume":  9_100},
]

# Crypto signals: very few, low quality
_CRYPTO_SIGNALS = [
    {"symbol": "BTCUSD", "timestamp": _date_str(-5), "signal": 0.0},
    {"symbol": "ETHUSD", "timestamp": _date_str(-5), "signal": 0.0},
    {"symbol": "SOLUSD", "timestamp": _date_str(-5), "signal": None},
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _get_or_create_strategy(db, project_id, name, slug, asset_class, status):
    from app.models.strategy import Strategy
    existing = db.query(Strategy).filter_by(project_id=project_id, slug=slug).first()
    if existing:
        return existing, False
    s = Strategy(project_id=project_id, name=name, slug=slug, asset_class=asset_class, status=status)
    db.add(s)
    db.flush()
    return s, True


def _make_version(db, strategy_id, version_label, git_commit, branch, code_path, signal_name):
    from app.models.strategy_version import StrategyVersion
    v = db.query(StrategyVersion).filter_by(strategy_id=strategy_id, version_label=version_label).first()
    if v:
        return v, False
    v = StrategyVersion(
        strategy_id=strategy_id, version_label=version_label,
        git_commit=git_commit, branch_name=branch, code_path=code_path, signal_name=signal_name,
    )
    db.add(v)
    db.flush()
    return v, True


def _make_config(db, strategy_id, version_id, label, config_json):
    try:
        from app.models.strategy_config_snapshot import StrategyConfigSnapshot
        from app.services.config_snapshots import compute_config_hash, count_params, count_assumptions
        h = compute_config_hash(config_json)
        c = db.query(StrategyConfigSnapshot).filter_by(strategy_id=strategy_id, config_hash=h).first()
        if c:
            return c
        c = StrategyConfigSnapshot(
            strategy_id=strategy_id, strategy_version_id=version_id, label=label,
            source_type="manual_json", config_json=config_json, config_hash=h,
            param_count=count_params(config_json), assumption_count=count_assumptions(config_json),
        )
        db.add(c)
        db.flush()
        return c
    except Exception as exc:
        print(f"[demo_seed] config snapshot {label} skipped: {exc}", file=sys.stderr)
        return None


def _make_universe(db, strategy_id, version_id, label, symbols, meta=None):
    try:
        from app.models.universe_snapshot import UniverseSnapshot
        from app.services.universe_snapshots import normalize_symbols, compute_universe_hash
        norm = normalize_symbols(symbols)
        h = compute_universe_hash(norm, meta or {})
        u = db.query(UniverseSnapshot).filter_by(strategy_id=strategy_id, universe_hash=h).first()
        if u:
            return u
        u = UniverseSnapshot(
            strategy_id=strategy_id, strategy_version_id=version_id, label=label,
            source_type="manual_json", symbols_json=norm, symbol_count=len(norm),
            metadata_json=meta or {}, universe_hash=h,
        )
        db.add(u)
        db.flush()
        return u
    except Exception as exc:
        print(f"[demo_seed] universe snapshot {label} skipped: {exc}", file=sys.stderr)
        return None


def _make_signal(db, strategy_id, version_id, universe_id, label, signal_name, rows):
    try:
        from app.models.signal_snapshot import SignalSnapshot
        from app.services.signal_snapshots import summarize_signal_snapshot, compute_signal_hash
        h = compute_signal_hash(rows)
        ss = db.query(SignalSnapshot).filter_by(strategy_id=strategy_id, signal_hash=h).first()
        if ss:
            return ss
        s = summarize_signal_snapshot(rows)
        ss = SignalSnapshot(
            strategy_id=strategy_id, strategy_version_id=version_id,
            universe_snapshot_id=universe_id,
            label=label, signal_name=signal_name, source_type="manual_json",
            rows_json=rows, row_count=s.row_count, symbol_count=s.symbol_count,
            symbols_json=s.symbols, min_timestamp=s.min_timestamp, max_timestamp=s.max_timestamp,
            signal_value_count=s.signal_value_count, missing_signal_count=s.missing_signal_count,
            mean_value=s.mean_value, min_value=s.min_value, max_value=s.max_value,
            stddev_value=s.stddev_value, signal_hash=h, quality_score=s.quality_score,
        )
        db.add(ss)
        db.flush()
        return ss
    except Exception as exc:
        print(f"[demo_seed] signal snapshot {label} skipped: {exc}", file=sys.stderr)
        return None


def _make_dataset_snapshot(db, project_id, dataset_name, dataset_desc, rows, version_label="v1"):
    try:
        from app.models.dataset import Dataset
        from app.models.dataset_snapshot import DatasetSnapshot
        from app.services.data_quality import analyze_snapshot
        ds = db.query(Dataset).filter_by(project_id=project_id, name=dataset_name).first()
        if not ds:
            ds = Dataset(project_id=project_id, name=dataset_name, description=dataset_desc,
                         dataset_type="ohlcv", source_type="manual")
            db.add(ds)
            db.flush()
        snap = db.query(DatasetSnapshot).filter_by(dataset_id=ds.id, version_label=version_label).first()
        if not snap:
            summary = analyze_snapshot(rows)
            snap = DatasetSnapshot(dataset_id=ds.id, version_label=version_label,
                                   row_count=len(rows), health_score=summary.health_score,
                                   rows_json=rows)
            db.add(snap)
            db.flush()
        return snap
    except Exception as exc:
        print(f"[demo_seed] dataset {dataset_name} skipped: {exc}", file=sys.stderr)
        return None


def _make_run(db, strategy_id, version_id, snap_id, univ_id, sig_id, name, run_type,
              params, assumptions, metrics, notes, run_at):
    from app.models.strategy_run import StrategyRun
    r = db.query(StrategyRun).filter_by(strategy_id=strategy_id, run_name=name).first()
    if r:
        return r
    r = StrategyRun(
        strategy_id=strategy_id, strategy_version_id=version_id,
        dataset_snapshot_id=snap_id, universe_snapshot_id=univ_id,
        signal_snapshot_id=sig_id, run_name=name, run_type=run_type,
        status=RunStatus.completed, started_at=run_at, completed_at=run_at,
        params_json=params, assumptions_json=assumptions, metrics_json=metrics, notes=notes,
    )
    db.add(r)
    db.flush()
    return r


def _make_audit(db, run, include_audits: bool):
    if not include_audits or run is None:
        return None
    try:
        from app.models.backtest_audit import BacktestAudit
        from app.models.backtest_issue import BacktestIssue
        from app.services.backtest_reality import run_backtest_audit
        if db.query(BacktestAudit).filter_by(strategy_run_id=run.id).first():
            return None
        res = run_backtest_audit(run, data_evidence=None)
        audit = BacktestAudit(
            strategy_run_id=run.id, trust_score=res.trust_score,
            lookahead_risk_score=res.lookahead_risk_score,
            cost_realism_score=res.cost_realism_score,
            fill_realism_score=res.fill_realism_score,
            liquidity_realism_score=res.liquidity_realism_score,
            borrow_realism_score=res.borrow_realism_score,
            data_quality_score=res.data_quality_score,
            overall_status=res.overall_status, summary=res.summary,
            cost_sensitivity_json=res.cost_sensitivity_json,
            fill_realism_json=res.fill_realism_json,
            fragility_summary_json=res.fragility_summary_json,
            cost_sensitivity_sweep_json=res.cost_sensitivity_sweep_json,
            fill_sensitivity_json=res.fill_sensitivity_json,
            penalty_attribution_json=res.penalty_attribution_json,
            improvement_checks_json=res.improvement_checks_json,
        )
        db.add(audit)
        db.flush()
        for iss in res.issues:
            db.add(BacktestIssue(
                backtest_audit_id=audit.id, issue_type=iss.issue_type,
                severity=iss.severity, title=iss.title, description=iss.description,
                evidence_json=iss.evidence_json, suggested_check=iss.suggested_check,
            ))
        db.flush()
        return audit
    except Exception as exc:
        print(f"[demo_seed] backtest audit skipped: {exc}", file=sys.stderr)
        return None


def _make_reliability_score(db, strategy_id):
    try:
        from app.models.strategy_reliability_score import StrategyReliabilityScore
        from app.services.strategy_reliability import compute_reliability_score
        d = compute_reliability_score(str(strategy_id), db)
        excl = {"strategy_id", "generated_at"}
        score = StrategyReliabilityScore(
            strategy_id=strategy_id,
            generated_at=d.get("generated_at") or _utcnow(),
            **{k: v for k, v in d.items() if k not in excl},
        )
        db.add(score)
        db.flush()
        return score
    except Exception as exc:
        print(f"[demo_seed] reliability score skipped: {exc}", file=sys.stderr)
        return None


def _make_report(db, strategy, include_reports: bool):
    if not include_reports:
        return
    try:
        from app.services.reports import generate_strategy_reliability_report, persist_report
        persist_report(generate_strategy_reliability_report(strategy.id, db), db)
    except Exception as exc:
        print(f"[demo_seed] report skipped: {exc}", file=sys.stderr)


def _make_review_case(db, strategy_id, title, case_key, severity, category, summary):
    """Create a review case. strategy_id must match the stored format of strategies.id.

    ResearchReviewCase.strategy_id is String(36); strategies.id is stored as 32-char hex
    by SQLAlchemy 2.0 on SQLite (same UUID format issue as workspace_members.organization_id).
    Use strategy_id.hex to pass the correct stored format.
    """
    try:
        import uuid as _uuid
        from app.models.review_case import ResearchReviewCase
        # Convert uuid.UUID → 32-char hex to match strategies.id stored format
        sid_str = strategy_id.hex if isinstance(strategy_id, _uuid.UUID) else str(strategy_id)
        existing = db.query(ResearchReviewCase).filter_by(
            strategy_id=sid_str, case_key=case_key
        ).first()
        if existing:
            return existing
        rc = ResearchReviewCase(
            strategy_id=sid_str, title=title, case_key=case_key,
            status="open", severity=severity, category=category,
            summary=summary, opened_at=_utcnow(),
        )
        db.add(rc)
        db.flush()
        return rc
    except Exception as exc:
        print(f"[demo_seed] review case {case_key} skipped: {exc}", file=sys.stderr)
        return None


# ---------------------------------------------------------------------------
# Strategy seeders
# ---------------------------------------------------------------------------

def _seed_aapl(db, strategy, org, project, include_audits, include_reports):
    arts = []

    v1, _ = _make_version(db, strategy.id, "v1.0", "a1b2c3d", "main",
                          "strategies/aapl_mean_reversion.py", "mean_reversion_zscore")
    v2, _ = _make_version(db, strategy.id, "v2.0", "e4f5g6h", "main",
                          "strategies/aapl_mean_reversion_v2.py", "mean_reversion_zscore_v2")
    arts.extend(["version:v1.0", "version:v2.0"])

    cfg1 = _make_config(db, strategy.id, v1.id, "AAPL Mean Reversion v1.0 Config", {
        "params": {"lookback": 20, "zscore_threshold": 1.5},
        "assumptions": {
            "transaction_cost_bps": 5,
            "slippage_bps": 2,
            "fill_model": "next_bar_open",
            "max_leverage": 1.0,
            "max_position_weight": 0.10,
            "liquidity_filter": "adv_1m_gt_10m",
        },
    })
    cfg2 = _make_config(db, strategy.id, v2.id, "AAPL Mean Reversion v2.0 Config", {
        "params": {"lookback": 15, "zscore_threshold": 1.8},
        "assumptions": {
            "transaction_cost_bps": 7,
            "slippage_bps": 3,
            "fill_model": "next_bar_open",
            "max_leverage": 1.0,
            "max_position_weight": 0.10,
            "liquidity_filter": "adv_1m_gt_10m",
        },
    })
    if cfg1: arts.append("config:v1.0")
    if cfg2: arts.append("config:v2.0")

    uni = _make_universe(db, strategy.id, v1.id,
                         "AAPL US Large-Cap Equity Universe",
                         ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN"],
                         {"universe_type": "US_LARGE_CAP",
                          "description": "Top-5 US large-cap tech equities."})
    if uni: arts.append("universe:v1")

    sig = _make_signal(db, strategy.id, v1.id, uni.id if uni else None,
                       f"AAPL Z-Score Signal {_date_str(4)}",
                       "mean_reversion_zscore", _AAPL_SIGNALS)
    if sig: arts.append("signal:aapl_zscore")

    dsnap = _make_dataset_snapshot(db, project.id, "AAPL Equity OHLCV Daily",
                                   "Clean daily OHLCV for AAPL universe (2026-06).",
                                   _AAPL_OHLCV)
    if dsnap: arts.append("dataset_snapshot:aapl_ohlcv")

    # Research run
    r_research = _make_run(
        db, strategy.id, v1.id,
        dsnap.id if dsnap else None, uni.id if uni else None, sig.id if sig else None,
        "AAPL Mean Reversion — Research",
        RunType.research,
        {"lookback": 20, "zscore_threshold": 1.5},
        {"transaction_cost_bps": 5, "slippage_bps": 2, "fill_model": "next_bar_open",
         "max_leverage": 1.0},
        {"sharpe": 1.38, "annual_return": 0.151, "volatility": 0.109,
         "max_drawdown": -0.112, "turnover": 1.72, "trade_count": 132, "win_rate": 0.54},
        "Initial research run to validate z-score signal quality.",
        _dt(-4),
    )
    arts.append("run:research_v1")

    # Backtest run (v1)
    r_bt1 = _make_run(
        db, strategy.id, v1.id,
        dsnap.id if dsnap else None, uni.id if uni else None, sig.id if sig else None,
        "AAPL Mean Reversion — Backtest v1",
        RunType.backtest,
        {"lookback": 20, "zscore_threshold": 1.5},
        {"transaction_cost_bps": 5, "slippage_bps": 2, "fill_model": "next_bar_open",
         "max_leverage": 1.0, "max_position_weight": 0.10},
        {"sharpe": 1.43, "annual_return": 0.162, "volatility": 0.113,
         "max_drawdown": -0.108, "turnover": 1.68, "trade_count": 147, "win_rate": 0.56},
        "Backtest v1 with realistic cost assumptions and full evidence chain.",
        _dt(-3),
    )
    arts.append("run:backtest_v1")
    _make_audit(db, r_bt1, include_audits)

    # Backtest run (v2 — improved)
    cfg2_snap = _make_config(db, strategy.id, v2.id, "AAPL Mean Reversion v2.0 Config", {
        "params": {"lookback": 15, "zscore_threshold": 1.8},
        "assumptions": {
            "transaction_cost_bps": 7, "slippage_bps": 3,
            "fill_model": "next_bar_open", "max_leverage": 1.0,
            "max_position_weight": 0.10, "liquidity_filter": "adv_1m_gt_10m",
        },
    })
    r_bt2 = _make_run(
        db, strategy.id, v2.id,
        dsnap.id if dsnap else None, uni.id if uni else None, sig.id if sig else None,
        "AAPL Mean Reversion — Backtest v2",
        RunType.backtest,
        {"lookback": 15, "zscore_threshold": 1.8},
        {"transaction_cost_bps": 7, "slippage_bps": 3, "fill_model": "next_bar_open",
         "max_leverage": 1.0, "max_position_weight": 0.10},
        {"sharpe": 1.52, "annual_return": 0.178, "volatility": 0.117,
         "max_drawdown": -0.101, "turnover": 1.85, "trade_count": 163, "win_rate": 0.57},
        "Tighter entry threshold improves Sharpe; cost model fully documented.",
        _dt(-1),
    )
    arts.append("run:backtest_v2")
    _make_audit(db, r_bt2, include_audits)

    _make_reliability_score(db, strategy.id)
    arts.append("reliability_score")
    _make_report(db, strategy, include_reports)

    return arts


def _seed_fx(db, strategy, org, project, include_audits, include_reports):
    # Seeds the "Global Futures Trend Model" strategy: a diversified futures
    # trend-following research strategy in a Backtest-Review state — solid
    # backtest evidence (v1-v3) but missing paper/shadow validation.
    # (Function/var names kept as `_fx` to minimize internal churn.)
    arts = []

    v1, _ = _make_version(db, strategy.id, "v1.0", None, "main",
                          "strategies/global_futures_trend.py", "time_series_momentum_signal")
    arts.append("version:v1.0")

    cfg = _make_config(db, strategy.id, v1.id, "Global Futures Trend Model Config", {
        "params": {
            "rebalance_frequency": "daily",
            "trend_lookback_days": 100,
            "vol_target": 0.15,
        },
        "assumptions": {
            "transaction_cost_bps": 6,
            "slippage_bps": 2,
            "fill_model": "next_bar_open",
            "max_leverage": 2.0,
            "max_position_weight": 0.20,
            "liquidity_filter": "liquid_futures_only",
        },
    })
    if cfg: arts.append("config:v1.0")

    uni = _make_universe(db, strategy.id, v1.id,
                         "Global Futures Trend Universe",
                         ["ES", "NQ", "ZN", "6E", "CL"],
                         {"universe_type": "GLOBAL_FUTURES",
                          "description": "Liquid global futures across equity index, rates, FX, and commodities."})
    if uni: arts.append("universe:global_futures")

    sig = _make_signal(db, strategy.id, v1.id, uni.id if uni else None,
                       f"Global Futures Trend Signal {_date_str(-29)}",
                       "time_series_momentum_signal", _FX_SIGNALS)
    if sig: arts.append("signal:global_futures_trend")

    dsnap = _make_dataset_snapshot(db, project.id, "Global Futures Daily OHLCV",
                                   "Daily futures OHLCV across equity index, rates, FX, and commodities; 6E missing one volume.",
                                   _FX_OHLCV)
    if dsnap: arts.append("dataset_snapshot:global_futures_ohlcv")

    # Backtest run (v1 — review band; fully evidenced)
    r_bt1 = _make_run(
        db, strategy.id, v1.id,
        dsnap.id if dsnap else None, uni.id if uni else None, sig.id if sig else None,
        "Global Futures Trend Backtest v1",
        RunType.backtest,
        {"rebalance_frequency": "daily", "trend_lookback_days": 100, "vol_target": 0.15},
        {"transaction_cost_bps": 6, "slippage_bps": 2, "fill_model": "next_bar_open",
         "max_leverage": 2.0, "max_position_weight": 0.20},
        {"sharpe": 0.84, "annual_return": 0.112, "volatility": 0.133,
         "max_drawdown": -0.187, "turnover": 3.40, "trade_count": 286, "win_rate": 0.47},
        "Trend-following backtest across liquid global futures. No paper/shadow run attached yet.",
        _dt(-28),
    )
    arts.append("run:backtest_v1")
    _make_audit(db, r_bt1, include_audits)

    # Second backtest — shorter lookback, mild deterioration (partial evidence)
    r_bt2 = _make_run(
        db, strategy.id, v1.id, None, uni.id if uni else None, None,
        "Global Futures Trend Backtest v2",
        RunType.backtest,
        {"rebalance_frequency": "daily", "trend_lookback_days": 60, "vol_target": 0.15},
        {"transaction_cost_bps": 6, "slippage_bps": 2, "fill_model": "next_bar_open",
         "max_leverage": 2.0},
        {"sharpe": 0.71, "annual_return": 0.094, "volatility": 0.131,
         "max_drawdown": -0.205, "turnover": 3.85, "trade_count": 312, "win_rate": 0.45},
        "Shorter lookback shows deterioration; signal evidence not linked on this run.",
        _dt(-10),
    )
    arts.append("run:backtest_v2")
    _make_audit(db, r_bt2, include_audits)

    # Third backtest — vol-targeted, re-evidenced (best of the three)
    r_bt3 = _make_run(
        db, strategy.id, v1.id,
        dsnap.id if dsnap else None, uni.id if uni else None, sig.id if sig else None,
        "Global Futures Trend Backtest v3",
        RunType.backtest,
        {"rebalance_frequency": "daily", "trend_lookback_days": 100, "vol_target": 0.12},
        {"transaction_cost_bps": 6, "slippage_bps": 2, "fill_model": "next_bar_open",
         "max_leverage": 2.0, "max_position_weight": 0.18},
        {"sharpe": 0.79, "annual_return": 0.103, "volatility": 0.129,
         "max_drawdown": -0.176, "turnover": 3.10, "trade_count": 268, "win_rate": 0.48},
        "Vol-targeted re-run with realistic costs. Still no paper/shadow validation.",
        _dt(-4),
    )
    arts.append("run:backtest_v3")
    _make_audit(db, r_bt3, include_audits)

    _make_reliability_score(db, strategy.id)
    arts.append("reliability_score")

    # Primary blocker: missing paper/shadow validation before promotion.
    _make_review_case(
        db, strategy.id,
        "Missing Paper/Shadow Validation",
        "missing_paper_shadow_validation",
        "high", "evidence_quality",
        "Backtest evidence (v1-v3) is in place, but no paper or shadow run is attached. "
        "Promotion to Paper Candidate requires paper/shadow validation evidence. "
        "Add a paper/shadow run and review high-severity data-health alerts before progression.",
    )
    arts.append("review_case:missing_paper_shadow")

    return arts


def _seed_crypto(db, strategy, org, project, include_audits, include_reports):
    arts = []

    v1, _ = _make_version(db, strategy.id, "v1.0", None, "feature/crypto-momentum",
                          None, "crypto_momentum_signal")
    arts.append("version:v1.0")

    cfg = _make_config(db, strategy.id, v1.id, "Crypto Momentum Intraday Config", {
        "params": {
            "lookback_hours": 24,
            "momentum_threshold": 0.03,
        },
        "assumptions": {
            "transaction_cost_bps": 0,   # missing — triggers audit issue
            "fill_model": "same_close",  # unrealistic — triggers audit issue
            "max_leverage": 3.0,
            "max_position_weight": 0.35,
        },
    })
    if cfg: arts.append("config:crypto_v1")

    uni = _make_universe(db, strategy.id, v1.id,
                         "Crypto Momentum Universe",
                         ["BTCUSD", "ETHUSD", "SOLUSD"],
                         {"universe_type": "CRYPTO_TOP3"})
    if uni: arts.append("universe:crypto_top3")

    # Very low-quality signal (few rows, missing values)
    sig = _make_signal(db, strategy.id, v1.id, uni.id if uni else None,
                       "Crypto Momentum Signal (Sparse)",
                       "crypto_momentum_signal", _CRYPTO_SIGNALS)
    if sig: arts.append("signal:crypto_sparse")

    dsnap = _make_dataset_snapshot(db, project.id, "Crypto Intraday OHLCV",
                                   "Sparse crypto OHLCV; suspicious BTC price spike on row 4.",
                                   _CRYPTO_OHLCV)
    if dsnap: arts.append("dataset_snapshot:crypto_ohlcv")

    # Single backtest run — inflated metrics from unrealistic assumptions
    r_bt1 = _make_run(
        db, strategy.id, v1.id,
        dsnap.id if dsnap else None, uni.id if uni else None, sig.id if sig else None,
        "Crypto Momentum — Backtest v1",
        RunType.backtest,
        {"lookback_hours": 24, "momentum_threshold": 0.03},
        {"transaction_cost_bps": 0, "fill_model": "same_close",
         "max_leverage": 3.0, "max_position_weight": 0.35},
        {"sharpe": 2.84, "annual_return": 0.523, "volatility": 0.423,
         "max_drawdown": -0.371, "turnover": 15.4, "trade_count": 1_247, "win_rate": 0.52},
        "Attractive headline numbers; same-close fill, zero costs, thin signal evidence.",
        _dt(-2),
    )
    arts.append("run:backtest_v1")
    _make_audit(db, r_bt1, include_audits)

    _make_reliability_score(db, strategy.id)
    arts.append("reliability_score")

    # Review case: backtest reliability degradation
    _make_review_case(
        db, strategy.id,
        "Crypto Momentum Backtest Reliability Degradation",
        "crypto_momentum_backtest_reliability_degradation",
        "high", "backtest_audit",
        "Backtest uses same-close fill model and zero transaction costs. "
        "High turnover (15×) with no borrow/slippage assumptions makes results unreliable. "
        "Signal evidence is sparse (3 rows, 1 missing). Dataset has suspicious price spike. "
        "Do not advance until assumptions are corrected and evidence is refreshed.",
    )
    arts.append("review_case:crypto_reliability")

    return arts


# ---------------------------------------------------------------------------
# Clean Realistic Demo: nuke all junk data, rebuild
# ---------------------------------------------------------------------------

_TABLES_TO_WIPE = [
    # Most-specific first (child tables), then parents.
    # workspace_members and auth_users are deliberately NOT wiped so that
    # logged-in sessions survive the reset.
    # organizations are NOT wiped — they are updated in-place — so that
    # workspace_members.organization_id FKs remain valid and RBAC keeps working.
    "backtest_issues",
    "backtest_audits",
    "data_quality_issues",
    "strategy_regression_test_results",
    "strategy_regression_test_runs",
    "strategy_regression_tests",
    "strategy_config_policy_results",
    "strategy_config_policy_evaluations",
    "strategy_config_policies",
    "evidence_sla_results",
    "evidence_sla_evaluations",
    "evidence_sla_policies",
    "strategy_experiment_analyses",
    "strategy_experiment_runs",
    "strategy_experiments",
    "strategy_reliability_snapshots",
    "strategy_reliability_scores",
    "strategy_config_snapshots",
    "universe_snapshots",
    "signal_snapshots",
    "dataset_snapshots",
    "strategy_runs",
    "strategy_versions",
    "research_review_case_events",
    "research_review_cases",
    "report_sections",
    "reports",
    "alert_rules",
    "alerts",
    "strategies",
    "datasets",
    "audit_timeline_events",
    "sdk_ingestion_batches",
    "api_keys",
    "projects",
]


def _wipe_all_demo_data(db: Session) -> dict:
    """Delete all demo content except workspace_members, auth_users, and organizations.

    Organizations are preserved in-place so that workspace_members.organization_id
    FKs remain valid — authenticated users can still use the session after the wipe.
    The caller is responsible for updating the org name/slug if needed.
    """
    counts: dict = {}
    for table in _TABLES_TO_WIPE:
        try:
            n = db.execute(_text(f"DELETE FROM {table}")).rowcount
            if n:
                counts[table] = n
        except Exception as exc:
            print(f"[demo_seed] wipe {table}: {exc}", file=sys.stderr)
    db.flush()
    return counts


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
    """Create / extend / reset the demo dataset.

    Modes
    -----
    extend               — idempotent; creates missing records.
    reset_demo_only      — deletes the demo org by name and re-seeds (legacy).
    clean_realistic_demo — wipes ALL strategy/evidence/alert junk from every
                           table, then re-creates a small clean demo workspace.
                           workspace_members and auth_users are preserved.
                           Requires confirm_reset=True.
    """
    from app.models.organization import Organization
    from app.models.project import Project
    from app.models.audit_timeline_event import AuditTimelineEvent

    # ── clean_realistic_demo ─────────────────────────────────────────────────
    if mode == "clean_realistic_demo":
        if not confirm_reset:
            raise ValueError("confirm_reset must be True for clean_realistic_demo mode.")

        wipe_counts = _wipe_all_demo_data(db)
        db.flush()

        # Find or create the demo org.  We keep the existing org row in-place
        # so that workspace_members.organization_id FKs remain valid (users can
        # still log in after the reset). We only update name/slug if they differ.
        demo_org = db.query(Organization).first()  # first org in DB
        if demo_org is None:
            demo_org = Organization(name=DEMO_ORG_NAME, slug=DEMO_ORG_SLUG)
            db.add(demo_org)
            db.flush()
        else:
            # Update to desired demo name/slug in-place
            demo_org.name = DEMO_ORG_NAME
            demo_org.slug = DEMO_ORG_SLUG
            db.flush()

        db.commit()

        demo_project = Project(
            organization_id=demo_org.id,
            name=DEMO_PROJECT_NAME,
            slug=DEMO_PROJECT_SLUG,
            description="Clean realistic demo portfolio for QuantFidelity product walkthroughs.",
        )
        db.add(demo_project)
        db.flush()

        # Seed all 3 strategies
        all_arts: list[str] = []
        strategy_ids: list[str] = []
        warnings: list[str] = []

        for s_def, seeder in [
            (DEMO_STRATEGIES[0], _seed_aapl),
            (DEMO_STRATEGIES[1], _seed_fx),
            (DEMO_STRATEGIES[2], _seed_crypto),
        ]:
            try:
                strat, _ = _get_or_create_strategy(
                    db, demo_project.id, s_def["name"], s_def["slug"],
                    s_def["asset_class"], s_def["status"],
                )
                strategy_ids.append(str(strat.id))
                arts = seeder(db, strat, demo_org, demo_project, include_backtest_audits, include_reports)
                all_arts.extend([f"{s_def['slug']}:{a}" for a in arts])
            except Exception as exc:
                warnings.append(f"{s_def['name']} seed failed: {str(exc)[:200]}")
                print(f"[demo_seed] {s_def['name']}: {exc}", file=sys.stderr)

        # Alerts
        if include_alerts:
            try:
                from app.services.alerts import generate_alerts
                generate_alerts(db, demo_org.id.hex)
            except Exception as exc:
                warnings.append(f"Alert generation skipped: {str(exc)[:100]}")

            # Reliability scores were first computed inside each seeder, before
            # alerts existed, so the stored score ignored the alert penalty.
            # Recompute now so the displayed "latest" reliability reflects the
            # open alerts (keeps review-state strategies honestly in-band).
            try:
                from app.models.strategy import Strategy as _Strategy
                for _strat in db.query(_Strategy).all():
                    _make_reliability_score(db, _strat.id)
                db.flush()
            except Exception as exc:
                warnings.append(f"Reliability refresh skipped: {str(exc)[:100]}")

        # Seed event
        db.add(AuditTimelineEvent(
            organization_id=demo_org.id,
            project_id=demo_project.id,
            event_type="demo_seeded",
            title="Clean realistic demo seeded",
            description="Junk data wiped; 3 realistic demo strategies created.",
            source_type="admin",
            source_id=str(demo_org.id),
            severity=Severity.info,
            event_time=_utcnow(),
            metadata_json={"mode": mode},
        ))
        db.commit()

        return {
            "mode": mode,
            "summary": (
                f"Clean realistic demo seeded: {DEMO_ORG_NAME} / {DEMO_PROJECT_NAME}. "
                f"{len(strategy_ids)} strategies, {len(all_arts)} artifacts. "
                f"Wiped: {sum(wipe_counts.values())} old rows."
            ),
            "organization_id": str(demo_org.id),
            "project_id": str(demo_project.id),
            "strategy_ids": strategy_ids,
            "created_counts": {"strategies": 3, "artifacts": len(all_arts)},
            "reused_counts": {},
            "reset_counts": wipe_counts,
            "generated_artifacts": all_arts,
            "warnings": warnings,
        }

    # ── reset_demo_only (legacy) ──────────────────────────────────────────────
    if mode == "reset_demo_only":
        if not confirm_reset:
            raise ValueError("confirm_reset must be True to reset demo data.")
        org = db.query(Organization).filter(Organization.name == DEMO_ORG_NAME).first()
        found = org is not None
        if found:
            name = org.name
            db.expunge_all()
            db.execute(_text("DELETE FROM organizations WHERE name = :n"), {"n": name})
            db.commit()
        return {
            "mode": mode,
            "summary": "Demo data reset (legacy mode).",
            "organization_id": None, "project_id": None, "strategy_ids": [],
            "created_counts": {}, "reused_counts": {},
            "reset_counts": {"organizations": 1 if found else 0},
            "generated_artifacts": [], "warnings": [],
        }

    # ── extend (default / idempotent) ─────────────────────────────────────────
    demo_org = db.query(Organization).filter(Organization.name == DEMO_ORG_NAME).first()
    created_org = False
    if demo_org is None:
        demo_org = Organization(name=DEMO_ORG_NAME, slug=DEMO_ORG_SLUG)
        db.add(demo_org)
        db.flush()
        created_org = True

    demo_project = (
        db.query(Project)
        .filter(Project.organization_id == demo_org.id, Project.slug == DEMO_PROJECT_SLUG)
        .first()
    )
    created_project = False
    if demo_project is None:
        demo_project = Project(
            organization_id=demo_org.id, name=DEMO_PROJECT_NAME,
            slug=DEMO_PROJECT_SLUG,
            description="Clean realistic demo portfolio for QuantFidelity product walkthroughs.",
        )
        db.add(demo_project)
        db.flush()
        created_project = True

    all_arts, strategy_ids, warnings = [], [], []
    created_s, reused_s = 0, 0

    for s_def, seeder in [
        (DEMO_STRATEGIES[0], _seed_aapl),
        (DEMO_STRATEGIES[1], _seed_fx),
        (DEMO_STRATEGIES[2], _seed_crypto),
    ]:
        try:
            strat, s_created = _get_or_create_strategy(
                db, demo_project.id, s_def["name"], s_def["slug"],
                s_def["asset_class"], s_def["status"],
            )
            strategy_ids.append(str(strat.id))
            if s_created: created_s += 1
            else: reused_s += 1
            arts = seeder(db, strat, demo_org, demo_project, include_backtest_audits, include_reports)
            all_arts.extend([f"{s_def['slug']}:{a}" for a in arts])
        except Exception as exc:
            warnings.append(f"{s_def['name']} seed failed: {str(exc)[:200]}")

    if include_alerts:
        try:
            from app.services.alerts import generate_alerts
            generate_alerts(db, demo_org.id.hex)
        except Exception as exc:
            warnings.append(f"Alert generation skipped: {str(exc)[:100]}")

    db.add(AuditTimelineEvent(
        organization_id=demo_org.id, project_id=demo_project.id,
        event_type="demo_seeded",
        title="Demo data seeded",
        description=f"Demo data seeded in {mode} mode.",
        source_type="admin", source_id=str(demo_org.id),
        severity=Severity.info, event_time=_utcnow(),
        metadata_json={"mode": mode, "created_org": created_org},
    ))
    db.commit()

    return {
        "mode": mode,
        "summary": (
            f"Demo seed complete. {'Created' if created_org else 'Reused'} org, "
            f"{'created' if created_project else 'reused'} project, "
            f"{len(strategy_ids)} strategy(ies)."
        ),
        "organization_id": str(demo_org.id),
        "project_id": str(demo_project.id),
        "strategy_ids": strategy_ids,
        "created_counts": {"strategies": created_s, "artifacts": len(all_arts)},
        "reused_counts": {"strategies": reused_s},
        "reset_counts": {},
        "generated_artifacts": all_arts,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# Public API: get_demo_status
# ---------------------------------------------------------------------------

def get_demo_status(db: Session) -> dict:
    from app.models.organization import Organization
    from app.models.project import Project
    from app.models.strategy import Strategy
    from app.models.audit_timeline_event import AuditTimelineEvent

    org = db.query(Organization).filter(Organization.name == DEMO_ORG_NAME).first()
    if not org:
        return {
            "demo_org_exists": False, "demo_project_exists": False,
            "strategy_count": 0, "demo_strategy_names": [],
            "last_seeded_at": None, "summary": "Demo data not yet seeded.",
        }
    proj = db.query(Project).filter(Project.organization_id == org.id).first()
    strats = db.query(Strategy).filter(Strategy.project_id == proj.id).all() if proj else []
    last = (
        db.query(AuditTimelineEvent)
        .filter(AuditTimelineEvent.organization_id == org.id,
                AuditTimelineEvent.event_type == "demo_seeded")
        .order_by(AuditTimelineEvent.created_at.desc())
        .first()
    )
    return {
        "demo_org_exists": True,
        "demo_project_exists": proj is not None,
        "strategy_count": len(strats),
        "demo_strategy_names": [s.name for s in strats],
        "last_seeded_at": last.created_at if last else None,
        "summary": f"{DEMO_ORG_NAME} / {DEMO_PROJECT_NAME}: {len(strats)} strategy(ies).",
    }
