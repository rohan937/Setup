"""QuantFidelity Python SDK.

Local Python SDK for submitting evidence bundles to QuantFidelity.
Wraps the M22 ``POST /api/strategies/{id}/evidence-bundles`` endpoint.

Not investment advice.  Deterministic — no AI, no live market data.

Quick start::

    from quantfidelity import QuantFidelityClient, EvidenceBundle

    client = QuantFidelityClient(base_url="http://localhost:8000")

    bundle = (
        EvidenceBundle()
        .with_strategy_version("v1.0", git_commit="abc123")
        .with_strategy_run(
            "backtest-2024-q1",
            run_type="backtest",
            metrics_json={"sharpe": 1.4, "max_drawdown": -0.12},
        )
        .with_actions(
            run_backtest_audit=True,
            compute_reliability_score=True,
        )
    )

    result = client.ingest_evidence_bundle("<strategy-uuid>", bundle)
    print(result["summary"])
"""

from importlib.metadata import PackageNotFoundError, version

from quantfidelity.bundle import EvidenceBundle
from quantfidelity.client import QuantFidelityClient
from quantfidelity.exceptions import (
    QuantFidelityAPIError,
    QuantFidelityConnectionError,
    QuantFidelityError,
    QuantFidelityValidationError,
)

__all__ = [
    "QuantFidelityClient",
    "EvidenceBundle",
    "QuantFidelityError",
    "QuantFidelityConnectionError",
    "QuantFidelityAPIError",
    "QuantFidelityValidationError",
]

try:
    __version__ = version("quantfidelity")
except PackageNotFoundError:
    __version__ = "0.1.0-dev"
