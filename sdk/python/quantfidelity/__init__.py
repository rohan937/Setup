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

from quantfidelity.buffer import LocalBuffer
from quantfidelity.bundle import EvidenceBundle
from quantfidelity.client import QuantFidelityClient
from quantfidelity.exceptions import (
    QuantFidelityAPIError,
    QuantFidelityAuthError,
    QuantFidelityConnectionError,
    QuantFidelityError,
    QuantFidelityNotFoundError,
    QuantFidelityValidationError,
)
from quantfidelity.workflow import QuantResearchWorkflow
from quantfidelity.handle import StrategyHandle

__all__ = [
    "QuantFidelityClient",
    "EvidenceBundle",
    "LocalBuffer",
    "QuantFidelityError",
    "QuantFidelityConnectionError",
    "QuantFidelityAPIError",
    "QuantFidelityValidationError",
    "QuantFidelityAuthError",
    "QuantFidelityNotFoundError",
    "QuantResearchWorkflow",
    "StrategyHandle",
    "init",
    "strategy",
    "test_auth",
]

try:
    __version__ = version("quantfidelity")
except PackageNotFoundError:
    __version__ = "0.1.0-dev"

# ------------------------------------------------------------------ #
# Module-level global client state and convenience functions          #
# ------------------------------------------------------------------ #

_default_client: "QuantFidelityClient | None" = None


def init(
    base_url: str | None = None,
    api_key: str | None = None,
    *,
    timeout: int | float = 30,
) -> "QuantFidelityClient":
    """Initialize the default QuantFidelity client.

    Reads QF_BASE_URL / QUANTFIDELITY_BASE_URL and QF_API_KEY /
    QUANTFIDELITY_API_KEY from the environment when not provided explicitly.

    Usage::

        import quantfidelity as qf
        qf.init(base_url="https://quantfidelity-api.onrender.com", api_key="qf_...")
        strategy = qf.strategy("spy-trend")

    Parameters
    ----------
    base_url:
        Base URL of the QuantFidelity server.
        Defaults to env var or http://localhost:8000.
    api_key:
        API key. Defaults to env var QF_API_KEY / QUANTFIDELITY_API_KEY.
    timeout:
        Request timeout in seconds.
    """
    global _default_client
    _default_client = QuantFidelityClient(
        base_url=base_url,
        api_key=api_key,
        timeout=timeout,
    )
    return _default_client


def _get_default_client() -> "QuantFidelityClient":
    """Return the default client, creating one from env vars if needed."""
    global _default_client
    if _default_client is None:
        _default_client = QuantFidelityClient()
    return _default_client


def strategy(slug_or_id: str) -> "StrategyHandle":
    """Return a notebook-friendly StrategyHandle using the default client.

    Call qf.init() first to configure base_url and api_key, or set
    QUANTFIDELITY_BASE_URL / QF_BASE_URL and
    QUANTFIDELITY_API_KEY / QF_API_KEY env vars.

    Usage::

        import quantfidelity as qf
        qf.init(api_key="qf_...")
        s = qf.strategy("spy-trend")
        s.log_run("Backtest v1", metrics={"sharpe": 1.4})
    """
    return _get_default_client().strategy(slug_or_id)


def test_auth() -> dict:
    """Test authentication using the default client.

    Returns {"status": "ok", "authenticated": True} on success.
    Raises QuantFidelityAuthError on 401/403.
    """
    return _get_default_client().test_auth()
