"""HTTP client for the QuantFidelity API.

Usage::

    from quantfidelity import QuantFidelityClient, EvidenceBundle

    client = QuantFidelityClient(base_url="http://localhost:8000")

    bundle = (
        EvidenceBundle()
        .with_strategy_run("backtest-q1", run_type="backtest",
                           metrics_json={"sharpe": 1.4})
        .with_actions(compute_reliability_score=True)
    )

    result = client.ingest_evidence_bundle(strategy_id, bundle)
    print(result["summary"])
"""
from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from quantfidelity.exceptions import (
    QuantFidelityAPIError,
    QuantFidelityConnectionError,
)

if TYPE_CHECKING:
    from quantfidelity.bundle import EvidenceBundle


class QuantFidelityClient:
    """Synchronous HTTP client for the QuantFidelity API.

    Parameters
    ----------
    base_url:
        Base URL of the QuantFidelity server (e.g. ``"http://localhost:8000"``).
        Trailing slashes are stripped automatically.
    api_key:
        Reserved for future API key authentication.  Pass ``None`` for local
        development (no authentication required).
    timeout:
        Request timeout in seconds.  Defaults to 30.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        *,
        api_key: str | None = None,
        timeout: int | float = 30,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key  # reserved: no auth implemented yet
        self._timeout = timeout

        try:
            import requests as _requests
            self._requests = _requests
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "The 'requests' package is required by QuantFidelityClient. "
                "Install it with: pip install requests"
            ) from exc

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._api_key:
            # Reserved: will be activated when API key auth is added (M24+)
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    def _url(self, path: str) -> str:
        return f"{self._base_url}{path}"

    def _handle_response(self, resp: Any) -> dict[str, Any]:
        """Raise :class:`QuantFidelityAPIError` on non-2xx; otherwise return JSON."""
        if not resp.ok:
            try:
                response_json = resp.json()
            except Exception:
                response_json = None
            raise QuantFidelityAPIError(
                status_code=resp.status_code,
                response_text=resp.text,
                response_json=response_json,
            )
        try:
            return resp.json()
        except Exception:
            return {"raw": resp.text}

    def _get(self, path: str) -> dict[str, Any]:
        url = self._url(path)
        try:
            resp = self._requests.get(
                url, headers=self._headers(), timeout=self._timeout
            )
        except self._requests.exceptions.ConnectionError as exc:
            raise QuantFidelityConnectionError(
                f"Cannot connect to QuantFidelity at {self._base_url}: {exc}"
            ) from exc
        except self._requests.exceptions.Timeout:
            raise QuantFidelityConnectionError(
                f"Request timed out after {self._timeout}s (GET {url})"
            )
        return self._handle_response(resp)

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = self._url(path)
        try:
            resp = self._requests.post(
                url,
                data=json.dumps(payload, default=str),
                headers=self._headers(),
                timeout=self._timeout,
            )
        except self._requests.exceptions.ConnectionError as exc:
            raise QuantFidelityConnectionError(
                f"Cannot connect to QuantFidelity at {self._base_url}: {exc}"
            ) from exc
        except self._requests.exceptions.Timeout:
            raise QuantFidelityConnectionError(
                f"Request timed out after {self._timeout}s (POST {url})"
            )
        return self._handle_response(resp)

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def ingest_evidence_bundle(
        self,
        strategy_id: str,
        bundle: "EvidenceBundle | dict[str, Any]",
    ) -> dict[str, Any]:
        """Submit an evidence bundle to QuantFidelity.

        POST ``/api/strategies/{strategy_id}/evidence-bundles``

        Parameters
        ----------
        strategy_id:
            UUID string of the target strategy.
        bundle:
            An :class:`~quantfidelity.bundle.EvidenceBundle` instance or a
            plain ``dict`` matching the ``EvidenceBundleRequest`` schema.

        Returns
        -------
        dict
            Parsed ``EvidenceBundleResponse`` JSON with keys:
            ``strategy_id``, ``created_count``, ``reused_count``,
            ``actions_run``, ``objects``, ``alerts_generated``,
            ``warnings``, ``summary``, ``timeline_events_created``,
            ``generated_at``.

        Raises
        ------
        QuantFidelityConnectionError
            If the server cannot be reached.
        QuantFidelityAPIError
            If the server returns a non-2xx response.
        """
        # Accept both EvidenceBundle instances and plain dicts
        try:
            payload = bundle.to_dict()  # type: ignore[union-attr]
        except AttributeError:
            payload = dict(bundle)  # type: ignore[arg-type]

        return self._post(
            f"/api/strategies/{strategy_id}/evidence-bundles",
            payload,
        )

    def get_evidence_bundle_example(self, strategy_id: str) -> dict[str, Any]:
        """Fetch an example evidence bundle payload for a strategy.

        GET ``/api/strategies/{strategy_id}/evidence-bundles/example``

        Useful for understanding the expected payload shape and for the
        frontend "Load Example" button.

        Parameters
        ----------
        strategy_id:
            UUID string of the strategy to fetch the example for.

        Returns
        -------
        dict
            A fully-populated example ``EvidenceBundleRequest`` payload.
        """
        return self._get(
            f"/api/strategies/{strategy_id}/evidence-bundles/example"
        )

    def health(self) -> dict[str, Any]:
        """Check the QuantFidelity server health.

        GET ``/health``

        Returns
        -------
        dict
            Server health status (``{"status": "ok", ...}``).
        """
        return self._get("/health")

    def api_root(self) -> dict[str, Any]:
        """Fetch the QuantFidelity API metadata.

        GET ``/api``

        Returns
        -------
        dict
            API metadata including version, environment, and docs URL.
        """
        return self._get("/api")

    def __repr__(self) -> str:
        auth = "api_key=***" if self._api_key else "api_key=None"
        return f"QuantFidelityClient(base_url={self._base_url!r}, {auth})"
