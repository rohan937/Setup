"""Idempotent seed script that populates the demo dataset.

Run once after migrating:

    cd backend
    python -m app.services.seed

Safe to run multiple times — existing records are found by slug/email and
reused rather than duplicated.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.constants import (
    AssetClass,
    EventType,
    RunStatus,
    RunType,
    Severity,
    StrategyStatus,
    UserRole,
)
from app.models.audit_timeline_event import AuditTimelineEvent
from app.models.organization import Organization
from app.models.project import Project
from app.models.strategy import Strategy
from app.models.strategy_run import StrategyRun
from app.models.strategy_version import StrategyVersion
from app.models.user import User


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_seed(db: Session) -> dict[str, str]:
    """Create demo seed data. Returns a dict of created/found object IDs.

    All operations are idempotent: if a record already exists (matched by
    slug or email) it is returned as-is.
    """

    # 1. Organization
    org = db.query(Organization).filter_by(slug="quantfidelity-demo").first()
    if org is None:
        org = Organization(name="QuantFidelity Demo", slug="quantfidelity-demo")
        db.add(org)
        db.flush()

    # 2. User
    user = db.query(User).filter_by(
        organization_id=org.id, email="demo@quantfidelity.local"
    ).first()
    if user is None:
        user = User(
            organization_id=org.id,
            email="demo@quantfidelity.local",
            name="Demo User",
            role=UserRole.owner,
        )
        db.add(user)
        db.flush()

    # 3. Project
    project = db.query(Project).filter_by(
        organization_id=org.id, slug="alpha-reliability-lab"
    ).first()
    if project is None:
        project = Project(
            organization_id=org.id,
            name="Alpha Reliability Lab",
            slug="alpha-reliability-lab",
            description="Demo project for QuantFidelity reliability research.",
        )
        db.add(project)
        db.flush()

    # 4. Strategy
    strategy = (
        db.query(Strategy)
        .filter_by(project_id=project.id, slug="aapl-mean-reversion-v1")
        .first()
    )
    if strategy is None:
        strategy = Strategy(
            project_id=project.id,
            name="AAPL Mean Reversion v1",
            slug="aapl-mean-reversion-v1",
            description=(
                "Simple mean reversion strategy on AAPL using z-score of recent returns. "
                "Research / demo use only."
            ),
            asset_class=AssetClass.equity,
            status=StrategyStatus.active,
        )
        db.add(strategy)
        db.flush()
        _add_timeline_event(
            db,
            org_id=org.id,
            project_id=project.id,
            strategy_id=strategy.id,
            event_type=EventType.strategy_created,
            title="Strategy created: AAPL Mean Reversion v1",
            description="Initial version of the AAPL mean reversion strategy.",
            source_type="strategy",
            source_id=str(strategy.id),
        )

    # 5. Strategy version
    version = (
        db.query(StrategyVersion)
        .filter_by(strategy_id=strategy.id, version_label="v1.0")
        .first()
    )
    if version is None:
        version = StrategyVersion(
            strategy_id=strategy.id,
            version_label="v1.0",
            git_commit=None,
            branch_name="main",
            code_path="strategies/aapl_mean_reversion.py",
            signal_name="return_zscore_mean_reversion",
            signal_description=(
                "Mean reversion signal using recent return z-score. "
                "Entry when z-score < -2.0, exit when z-score > 0."
            ),
        )
        db.add(version)
        db.flush()

    # 6. Strategy run (baseline backtest)
    run = (
        db.query(StrategyRun)
        .filter_by(strategy_id=strategy.id, run_name="Baseline Backtest Run")
        .first()
    )
    if run is None:
        run = StrategyRun(
            strategy_id=strategy.id,
            strategy_version_id=version.id,
            run_name="Baseline Backtest Run",
            run_type=RunType.backtest,
            status=RunStatus.completed,
            started_at=_utcnow(),
            completed_at=_utcnow(),
            params_json={
                "lookback_days": 20,
                "zscore_entry": 2.0,
            },
            assumptions_json={
                "transaction_cost_bps": 5,
                "fill_model": "mid_plus_5bps",
            },
            metrics_json={
                "sharpe": 1.6,
                "turnover": 0.42,
                "max_drawdown": 0.11,
            },
            universe_name="US_LARGE_CAP",
            dataset_version="demo_prices_v1",
            notes="Baseline run with 20-day lookback and 5 bps cost assumption.",
        )
        db.add(run)
        db.flush()
        _add_timeline_event(
            db,
            org_id=org.id,
            project_id=project.id,
            strategy_id=strategy.id,
            event_type=EventType.strategy_run_logged,
            title="Baseline run logged: Backtest (Sharpe 1.6)",
            description=(
                "Baseline backtest completed. "
                "Sharpe 1.6, turnover 0.42, max drawdown 11%."
            ),
            source_type="strategy_run",
            source_id=str(run.id),
            metadata_json={"sharpe": 1.6, "run_type": "backtest"},
        )

    db.commit()

    return {
        "organization_id": str(org.id),
        "user_id": str(user.id),
        "project_id": str(project.id),
        "strategy_id": str(strategy.id),
        "strategy_version_id": str(version.id),
        "strategy_run_id": str(run.id),
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _add_timeline_event(
    db: Session,
    *,
    org_id,
    project_id,
    strategy_id,
    event_type: str,
    title: str,
    description: str | None = None,
    source_type: str | None = None,
    source_id: str | None = None,
    severity: str = Severity.info,
    metadata_json: dict | None = None,
) -> AuditTimelineEvent:
    event = AuditTimelineEvent(
        organization_id=org_id,
        project_id=project_id,
        strategy_id=strategy_id,
        event_type=event_type,
        title=title,
        description=description,
        source_type=source_type,
        source_id=source_id,
        severity=severity,
        event_time=_utcnow(),
        metadata_json=metadata_json,
    )
    db.add(event)
    db.flush()
    return event


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    from app.db.session import SessionLocal

    print("QuantFidelity seed — running…")
    db = SessionLocal()
    try:
        ids = run_seed(db)
        print("Seed complete.")
        for key, value in ids.items():
            print(f"  {key}: {value}")
    except Exception as exc:
        db.rollback()
        print(f"Seed failed: {exc}", file=sys.stderr)
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
