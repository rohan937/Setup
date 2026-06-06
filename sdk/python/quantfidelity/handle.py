"""StrategyHandle — notebook-friendly per-strategy object for QuantFidelity.

M89: wraps a QuantFidelityClient and a strategy reference (UUID or slug) and
exposes concise ``log_*`` methods that each build and immediately ingest an
evidence bundle.

Usage::

    from quantfidelity import QuantFidelityClient
    from quantfidelity.handle import StrategyHandle

    client = QuantFidelityClient(base_url="http://localhost:8000")
    handle = StrategyHandle(client, "spy-trend")

    handle.log_run(
        "backtest-2024-q1",
        metrics={"sharpe": 1.4, "max_drawdown": -0.12},
        params={"lookback": 20},
    )
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from quantfidelity.client import QuantFidelityClient


class StrategyHandle:
    """Per-strategy helper for notebook and script workflows.

    Parameters
    ----------
    client:
        An authenticated :class:`~quantfidelity.client.QuantFidelityClient`.
    strategy_id_or_slug:
        Either a UUID string (e.g. ``"550e8400-e29b-41d4-a716-446655440000"``)
        or a human-readable slug (e.g. ``"spy-trend"``).  Slug resolution is
        lazy and cached after the first call.
    """

    def __init__(
        self,
        client: "QuantFidelityClient",
        strategy_id_or_slug: str,
    ) -> None:
        self._client = client
        self._ref = strategy_id_or_slug  # UUID or slug
        self._resolved_id: str | None = None  # cache

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    def _resolve(self) -> str:
        """Resolve slug to UUID if needed.

        Returns
        -------
        str
            The strategy UUID as a string.

        Raises
        ------
        QuantFidelityNotFoundError
            When the slug cannot be matched to any existing strategy.
        """
        if self._resolved_id:
            return self._resolved_id

        # If it looks like a UUID, use directly
        import uuid as _uuid

        try:
            _uuid.UUID(self._ref)
            self._resolved_id = self._ref
            return self._resolved_id
        except ValueError:
            pass

        # Otherwise look up by slug
        strats = self._client.list_strategies()
        match = next((s for s in strats if s.get("slug") == self._ref), None)
        if match is None:
            from quantfidelity.exceptions import QuantFidelityNotFoundError

            raise QuantFidelityNotFoundError(
                status_code=404,
                response_text=f"Strategy not found: {self._ref!r}",
            )
        self._resolved_id = str(match["id"])
        return self._resolved_id

    # ------------------------------------------------------------------ #
    # Properties                                                           #
    # ------------------------------------------------------------------ #

    @property
    def strategy_id(self) -> str:
        """Resolved strategy UUID string (lazy, cached after first access)."""
        return self._resolve()

    # ------------------------------------------------------------------ #
    # log_* methods                                                        #
    # ------------------------------------------------------------------ #

    def log_run(
        self,
        name: str,
        *,
        run_type: str = "backtest",
        metrics: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        assumptions: dict[str, Any] | None = None,
        version_label: str | None = None,
        notes: str | None = None,
        actions: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build and ingest a strategy run evidence bundle.

        Parameters
        ----------
        name:
            Human-readable name for this run (e.g. ``"backtest-2024-q1"``).
        run_type:
            Run type: ``"backtest"``, ``"paper"``, ``"research"``, ``"live"``.
            Defaults to ``"backtest"``.
        metrics:
            Performance metrics dict (e.g. ``{"sharpe": 1.4}``).
        params:
            Strategy parameter dict used for this run.
        assumptions:
            Execution assumption dict (cost, fill model, etc.).
        version_label:
            Strategy version label.  When provided, a ``strategy_version``
            section is added to the bundle before the run.
        notes:
            Freeform notes for this run.
        actions:
            Post-ingestion action flags.  Defaults to
            ``{"compute_reliability_score": True, "generate_alerts": True}``.

        Returns
        -------
        dict
            Parsed ingestion response.
        """
        from quantfidelity.bundle import EvidenceBundle

        b = EvidenceBundle()
        if version_label:
            b.with_strategy_version(version_label)
        b.with_strategy_run(
            name,
            run_type=run_type,
            params_json=params,
            assumptions_json=assumptions,
            metrics_json=metrics,
            strategy_version_label=version_label,
            notes=notes,
        )
        _actions = actions or {"compute_reliability_score": True, "generate_alerts": True}
        b.with_actions(**_actions)
        return self._client.ingest_bundle(self._resolve(), b)

    def log_paper_run(
        self,
        name: str,
        *,
        metrics: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        assumptions: dict[str, Any] | None = None,
        version_label: str | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        """Log a paper/live-like run.

        Convenience wrapper around :meth:`log_run` with ``run_type='paper'``.

        Parameters
        ----------
        name:
            Human-readable name for this run.
        metrics:
            Performance metrics dict.
        params:
            Strategy parameter dict.
        assumptions:
            Execution assumption dict.
        version_label:
            Strategy version label.
        notes:
            Freeform notes for this run.

        Returns
        -------
        dict
            Parsed ingestion response.
        """
        return self.log_run(
            name,
            run_type="paper",
            metrics=metrics,
            params=params,
            assumptions=assumptions,
            version_label=version_label,
            notes=notes,
        )

    def log_dataset(
        self,
        name: str,
        *,
        rows: list[dict[str, Any]] | None = None,
        symbols: list[str] | None = None,
        columns: list[str] | None = None,
        asset_class: str = "equity",
        dataset_type: str = "equity_prices",
        snapshot_label: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Log a dataset and optional snapshot rows.

        If ``rows`` is provided, a ``dataset_snapshot`` section is included.
        ``symbols`` and ``columns`` are stored in ``metadata_json`` if provided.

        Parameters
        ----------
        name:
            Dataset name (e.g. ``"SP500 OHLCV 2024"``).
        rows:
            When provided, a ``dataset_snapshot`` section is included in the
            bundle.  Must be a non-empty list of dicts.
        symbols:
            Ticker symbols present in the dataset.  Stored in ``metadata_json``.
        columns:
            Column names in the dataset.  Stored in ``metadata_json``.
        asset_class:
            Asset class (e.g. ``"equity"``, ``"fx"``).  Defaults to
            ``"equity"``.
        dataset_type:
            Type of data (e.g. ``"equity_prices"``).  Defaults to
            ``"equity_prices"``.
        snapshot_label:
            Label for the dataset snapshot.  Defaults to
            ``"dataset-snapshot"`` when ``rows`` is provided.
        metadata:
            Arbitrary metadata dict merged with ``symbols`` / ``columns``.

        Returns
        -------
        dict
            Parsed ingestion response.
        """
        from quantfidelity.bundle import EvidenceBundle

        b = EvidenceBundle()
        b.with_dataset(name, asset_class=asset_class, dataset_type=dataset_type)
        if rows is not None:
            snap_label = snapshot_label or "dataset-snapshot"
            b.with_dataset_snapshot(rows=rows, snapshot_label=snap_label)
        if symbols or columns or metadata:
            meta = dict(metadata or {})
            if symbols:
                meta["symbols"] = symbols
            if columns:
                meta["columns"] = columns
            # Attach metadata to dataset section
            b._data["dataset"]["metadata_json"] = meta  # type: ignore[attr-defined]
        return self._client.ingest_bundle(self._resolve(), b)

    def log_signal(
        self,
        name: str,
        *,
        rows: list[dict[str, Any]],
        signal_key: str | None = None,
        symbols: list[str] | None = None,
        signal_column: str = "signal",
        universe_snapshot_label: str | None = None,
        version_label: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Log a signal snapshot.

        Parameters
        ----------
        name:
            Signal name (e.g. ``"return_zscore"``).
        rows:
            Non-empty list of dicts.  Each dict should contain at minimum
            ``symbol``, ``timestamp``, and the signal column.
        signal_key:
            Bundle label for the snapshot.  Defaults to ``name``.
        symbols:
            Ticker symbols present in the snapshot (informational).
        signal_column:
            Name of the signal column in ``rows``.  Defaults to ``"signal"``.
        universe_snapshot_label:
            Link this snapshot to the named universe snapshot.
        version_label:
            Strategy version label.
        metadata:
            Arbitrary metadata dict forwarded as ``metadata_json``.

        Returns
        -------
        dict
            Parsed ingestion response.
        """
        from quantfidelity.bundle import EvidenceBundle

        label = signal_key or name
        b = EvidenceBundle()
        if version_label:
            b.with_strategy_version(version_label)
        b.with_signal_snapshot(
            label,
            rows=rows,
            signal_name=name,
            signal_column=signal_column,
            strategy_version_label=version_label,
            universe_snapshot_label=universe_snapshot_label,
            metadata_json=metadata,
        )
        return self._client.ingest_bundle(self._resolve(), b)

    def log_config(
        self,
        label: str = "config",
        *,
        params: dict[str, Any] | None = None,
        assumptions: dict[str, Any] | None = None,
        portfolio: dict[str, Any] | None = None,
        version_label: str | None = None,
    ) -> dict[str, Any]:
        """Log a config snapshot.

        Parameters
        ----------
        label:
            Human-readable label for this config snapshot.  Defaults to
            ``"config"``.
        params:
            Strategy parameter dict stored under the ``params`` key.
        assumptions:
            Execution assumption dict stored under the ``assumptions`` key.
        portfolio:
            Portfolio construction settings stored under the ``portfolio`` key.
        version_label:
            Strategy version label.

        Returns
        -------
        dict
            Parsed ingestion response.
        """
        from quantfidelity.bundle import EvidenceBundle

        cfg: dict[str, Any] = {}
        if params:
            cfg["params"] = params
        if assumptions:
            cfg["assumptions"] = assumptions
        if portfolio:
            cfg["portfolio"] = portfolio
        b = EvidenceBundle()
        if version_label:
            b.with_strategy_version(version_label)
        b.with_config_snapshot(label, config_json=cfg, strategy_version_label=version_label)
        return self._client.ingest_bundle(self._resolve(), b)

    def log_universe(
        self,
        name: str,
        *,
        symbols: list[str],
        metadata: dict[str, Any] | None = None,
        version_label: str | None = None,
    ) -> dict[str, Any]:
        """Log a universe snapshot.

        Parameters
        ----------
        name:
            Human-readable label for this universe snapshot
            (e.g. ``"sp500-2024-q1"``).
        symbols:
            Non-empty list of ticker symbols.
        metadata:
            Arbitrary metadata dict forwarded as ``metadata_json``.
        version_label:
            Strategy version label.

        Returns
        -------
        dict
            Parsed ingestion response.
        """
        from quantfidelity.bundle import EvidenceBundle

        b = EvidenceBundle()
        if version_label:
            b.with_strategy_version(version_label)
        b.with_universe_from_symbols(
            name,
            symbols,
            strategy_version_label=version_label,
            metadata_json=metadata,
        )
        return self._client.ingest_bundle(self._resolve(), b)

    # ------------------------------------------------------------------ #
    # Report / score / monitor                                             #
    # ------------------------------------------------------------------ #

    def generate_report(self) -> dict[str, Any]:
        """Generate a strategy reliability report.

        POST ``/api/reports/strategy/{id}``

        Returns
        -------
        dict
            Parsed report response.
        """
        return self._client.generate_report(self._resolve())

    def refresh_score(self) -> dict[str, Any]:
        """Recompute and store a reliability score.

        POST ``/api/strategies/{id}/reliability-score``

        Returns
        -------
        dict
            Parsed score response.
        """
        return self._client.refresh_score(self._resolve())

    def shadow_monitor(self) -> dict[str, Any]:
        """Return the M88 shadow drift monitor result.

        GET ``/api/strategies/{id}/shadow-monitor/refresh``

        Returns
        -------
        dict
            Parsed shadow monitor response.
        """
        return self._client.shadow_monitor(self._resolve())

    def get_detail(self) -> dict[str, Any]:
        """Return strategy detail dict.

        GET ``/api/strategies/{id}``

        Returns
        -------
        dict
            Full strategy detail payload.
        """
        return self._client.get_strategy(self._resolve())

    # ------------------------------------------------------------------ #
    # Dunder helpers                                                       #
    # ------------------------------------------------------------------ #

    def __repr__(self) -> str:
        return f"StrategyHandle(ref={self._ref!r})"
