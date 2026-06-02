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
from app.models.strategy_config_snapshot import StrategyConfigSnapshot
from app.models.universe_snapshot import UniverseSnapshot
from app.models.signal_snapshot import SignalSnapshot
from app.models.audit_timeline_event import AuditTimelineEvent
from app.models.dataset import Dataset
from app.models.dataset_snapshot import DatasetSnapshot
from app.models.data_quality_issue import DataQualityIssue
from app.models.backtest_audit import BacktestAudit
from app.models.backtest_issue import BacktestIssue
from app.models.alert_rule import AlertRule
from app.models.alert import Alert
from app.models.report import Report
from app.models.report_section import ReportSection
from app.models.strategy_reliability_score import StrategyReliabilityScore
from app.models.api_key import ApiKey
from app.models.sdk_ingestion_batch import SdkIngestionBatch
from app.models.regression import (
    StrategyRegressionTest,
    StrategyRegressionTestRun,
    StrategyRegressionTestResult,
)
from app.models.config_policy import (
    StrategyConfigPolicy,
    StrategyConfigPolicyEvaluation,
    StrategyConfigPolicyResult,
)

__all__ = [
    "Organization",
    "User",
    "Project",
    "Strategy",
    "StrategyVersion",
    "StrategyRun",
    "StrategyConfigSnapshot",
    "UniverseSnapshot",
    "SignalSnapshot",
    "AuditTimelineEvent",
    "Dataset",
    "DatasetSnapshot",
    "DataQualityIssue",
    "BacktestAudit",
    "BacktestIssue",
    "AlertRule",
    "Alert",
    "Report",
    "ReportSection",
    "StrategyReliabilityScore",
    "ApiKey",
    "SdkIngestionBatch",
    "StrategyRegressionTest",
    "StrategyRegressionTestRun",
    "StrategyRegressionTestResult",
    "StrategyConfigPolicy",
    "StrategyConfigPolicyEvaluation",
    "StrategyConfigPolicyResult",
]
