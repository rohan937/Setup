"""ORM models package.

Importing this package ensures all model classes are registered with the
SQLAlchemy mapper and with ``Base.metadata``, which is required for Alembic
autogenerate and for ``Base.metadata.create_all()`` in tests.
"""

from app.models.organization import Organization
from app.models.user import User
from app.models.project import Project
from app.models.strategy import Strategy
from app.models.strategy_version import StrategyVersion
from app.models.strategy_run import StrategyRun
from app.models.audit_timeline_event import AuditTimelineEvent
from app.models.dataset import Dataset
from app.models.dataset_snapshot import DatasetSnapshot
from app.models.data_quality_issue import DataQualityIssue
from app.models.backtest_audit import BacktestAudit
from app.models.backtest_issue import BacktestIssue
from app.models.alert_rule import AlertRule
from app.models.alert import Alert

__all__ = [
    "Organization",
    "User",
    "Project",
    "Strategy",
    "StrategyVersion",
    "StrategyRun",
    "AuditTimelineEvent",
    "Dataset",
    "DatasetSnapshot",
    "DataQualityIssue",
    "BacktestAudit",
    "BacktestIssue",
    "AlertRule",
    "Alert",
]
