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
import time
import uuid
from typing import TYPE_CHECKING, Any

from quantfidelity.exceptions import (
    QuantFidelityAPIError,
    QuantFidelityConnectionError,
)

if TYPE_CHECKING:
    from quantfidelity.bundle import EvidenceBundle

# Status codes that are non-retryable (client errors)
_NO_RETRY_STATUSES = {400, 401, 403, 404, 409, 422}
# Status codes that are retryable (server/rate-limit errors)
_RETRY_STATUSES = {429, 500, 502, 503, 504}


class QuantFidelityClient:
    """Synchronous HTTP client for the QuantFidelity API.

    Parameters
    ----------
    base_url:
        Base URL of the QuantFidelity server (e.g. ``"http://localhost:8000"``).
        Trailing slashes are stripped automatically.
    api_key:
        API key for authentication.  When provided, it is sent as an
        ``Authorization: Bearer <key>`` header on every request.  Pass
        ``None`` for local development (no authentication required).
    timeout:
        Request timeout in seconds.  Defaults to 30.
    buffer_path:
        Path for the offline buffer file.  Defaults to
        ``~/.quantfidelity/buffer.jsonl``.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        *,
        api_key: str | None = None,
        timeout: int | float = 30,
        buffer_path: str | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout
        self._buffer_path = buffer_path
        self._buffer = None

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

    @property
    def _get_buffer(self):
        """Lazy-initialise and return the local buffer."""
        if self._buffer is None:
            from quantfidelity.buffer import LocalBuffer
            self._buffer = LocalBuffer(path=self._buffer_path)
        return self._buffer

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._api_key:
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
        *,
        idempotency_key: str | None = None,
        retry: bool = True,
        max_retries: int = 3,
        backoff_seconds: float = 0.5,
        buffer_on_failure: bool = False,
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
        idempotency_key:
            Optional idempotency key for the request.  When ``retry=True``
            and no key is supplied, one is auto-generated.
        retry:
            Whether to retry on transient errors.  Defaults to ``True``.
        max_retries:
            Maximum number of attempts (including the first).  Only used
            when ``retry=True``.
        backoff_seconds:
            Base backoff time in seconds.  Actual sleep is
            ``backoff_seconds * 2 ** attempt``.
        buffer_on_failure:
            If ``True``, save the bundle to the local offline buffer when
            all attempts fail, instead of raising.

        Returns
        -------
        dict
            Parsed ``EvidenceBundleResponse`` JSON, or
            ``{"buffered": True, "buffer_id": ..., "error": ...}`` if
            ``buffer_on_failure=True`` and all attempts failed.

        Raises
        ------
        QuantFidelityConnectionError
            If the server cannot be reached and ``buffer_on_failure=False``.
        QuantFidelityAPIError
            If the server returns a non-2xx response and
            ``buffer_on_failure=False``.
        """
        # Auto-generate idempotency key when retrying
        if retry and idempotency_key is None:
            idempotency_key = str(uuid.uuid4())

        # Accept both EvidenceBundle instances and plain dicts
        try:
            payload = bundle.to_dict()  # type: ignore[union-attr]
        except AttributeError:
            payload = dict(bundle)  # type: ignore[arg-type]

        url = self._url(f"/api/strategies/{strategy_id}/evidence-bundles")
        attempts = max_retries if retry else 1
        last_exc: Exception | None = None

        for attempt in range(attempts):
            # Sleep between retries with exponential backoff
            if attempt > 0:
                time.sleep(backoff_seconds * (2 ** (attempt - 1)))

            # Build per-request headers (with optional idempotency key)
            headers: dict[str, str] = {"Content-Type": "application/json"}
            if self._api_key:
                headers["Authorization"] = f"Bearer {self._api_key}"
            if idempotency_key:
                headers["Idempotency-Key"] = idempotency_key

            try:
                resp = self._requests.post(
                    url,
                    data=json.dumps(payload, default=str),
                    headers=headers,
                    timeout=self._timeout,
                )
            except self._requests.exceptions.ConnectionError as exc:
                last_exc = QuantFidelityConnectionError(
                    f"Cannot connect to QuantFidelity at {self._base_url}: {exc}"
                )
                # Retry on connection error
                continue
            except self._requests.exceptions.Timeout as exc:
                last_exc = QuantFidelityConnectionError(
                    f"Request timed out after {self._timeout}s (POST {url})"
                )
                continue

            if resp.ok:
                try:
                    return resp.json()
                except Exception:
                    return {"raw": resp.text}

            # Determine whether to retry based on status code
            try:
                response_json = resp.json()
            except Exception:
                response_json = None

            api_exc = QuantFidelityAPIError(
                status_code=resp.status_code,
                response_text=resp.text,
                response_json=response_json,
            )

            if resp.status_code in _NO_RETRY_STATUSES:
                # Non-retryable: raise immediately
                raise api_exc

            # Retryable status: save and continue
            last_exc = api_exc

        # All attempts exhausted
        if buffer_on_failure and last_exc is not None:
            from quantfidelity.buffer import LocalBuffer
            buf = LocalBuffer(path=self._buffer_path)
            record = buf.add(
                base_url=self._base_url,
                strategy_id=strategy_id,
                payload=payload,
                idempotency_key=idempotency_key,
                error=str(last_exc),
            )
            return {
                "buffered": True,
                "buffer_id": record["buffer_id"],
                "error": str(last_exc),
            }

        if last_exc is not None:
            raise last_exc

        # Should not reach here
        raise QuantFidelityConnectionError(  # pragma: no cover
            f"Unexpected error during ingest to {url}"
        )

    def buffer_evidence_bundle(
        self,
        strategy_id: str,
        bundle: "EvidenceBundle | dict[str, Any]",
        *,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """Buffer a bundle locally without attempting to send it first.

        Parameters
        ----------
        strategy_id:
            UUID string of the target strategy.
        bundle:
            An :class:`~quantfidelity.bundle.EvidenceBundle` instance or a
            plain ``dict``.
        idempotency_key:
            Optional idempotency key.  Auto-generated if not provided.

        Returns
        -------
        dict
            The buffered record including ``buffer_id``.
        """
        try:
            payload = bundle.to_dict()  # type: ignore[union-attr]
        except AttributeError:
            payload = dict(bundle)  # type: ignore[arg-type]

        idem = idempotency_key or str(uuid.uuid4())
        from quantfidelity.buffer import LocalBuffer
        buf = LocalBuffer(path=self._buffer_path)
        return buf.add(
            base_url=self._base_url,
            strategy_id=strategy_id,
            payload=payload,
            idempotency_key=idem,
        )

    def flush_buffer(self, *, max_items: int | None = None) -> dict[str, Any]:
        """Attempt to resend all buffered records.

        Returns
        -------
        dict
            ``{"flushed": N, "failed": M, "remaining": K}``
        """
        from quantfidelity.buffer import LocalBuffer
        buf = LocalBuffer(path=self._buffer_path)
        return buf.flush(self, max_items=max_items)

    def list_buffered(self) -> list[dict[str, Any]]:
        """Return all records currently in the local offline buffer."""
        from quantfidelity.buffer import LocalBuffer
        return LocalBuffer(path=self._buffer_path).list_records()

    def clear_buffer(self) -> int:
        """Remove all records from the local offline buffer.

        Returns
        -------
        int
            Number of records removed.
        """
        from quantfidelity.buffer import LocalBuffer
        return LocalBuffer(path=self._buffer_path).clear()

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

    def ingest_bundle(
        self,
        strategy_id: str,
        bundle: "EvidenceBundle | dict[str, Any]",
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Ergonomic alias for :meth:`ingest_evidence_bundle`.

        Provided for clean notebook/script usage where the longer name feels
        verbose.  All keyword arguments are forwarded unchanged.

        Parameters
        ----------
        strategy_id:
            UUID string of the target strategy.
        bundle:
            An :class:`~quantfidelity.bundle.EvidenceBundle` instance or a
            plain ``dict``.
        **kwargs:
            Forwarded to :meth:`ingest_evidence_bundle`.
        """
        return self.ingest_evidence_bundle(strategy_id, bundle, **kwargs)

    def validate_bundle(
        self,
        bundle: "EvidenceBundle | dict[str, Any]",
    ) -> list[str]:
        """Run SDK-side validation on a bundle without contacting the server.

        Parameters
        ----------
        bundle:
            An :class:`~quantfidelity.bundle.EvidenceBundle` instance or a
            plain ``dict``.

        Returns
        -------
        list[str]
            Human-readable validation issues.  Empty list = valid.
        """
        try:
            return bundle.validate()  # type: ignore[union-attr]
        except AttributeError:
            from quantfidelity.bundle import EvidenceBundle  # noqa: PLC0415

            return EvidenceBundle.from_dict(bundle).validate()  # type: ignore[arg-type]

    def __repr__(self) -> str:
        auth = "api_key=***" if self._api_key else "api_key=None"
        return f"QuantFidelityClient(base_url={self._base_url!r}, {auth})"
