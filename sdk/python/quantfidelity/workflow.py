"""QuantResearchWorkflow — high-level research workflow builder.

Wraps :class:`~quantfidelity.bundle.EvidenceBundle` to provide a clean,
notebook-friendly API for building evidence bundles step-by-step.

Usage::

    from quantfidelity import QuantResearchWorkflow, QuantFidelityClient

    wf = (
        QuantResearchWorkflow(strategy_name="AAPL Mean Reversion", version_label="v1.0")
        .set_config(params={"lookback": 20}, assumptions={"cost_bps": 5})
        .set_universe(["AAPL", "MSFT", "NVDA"])
        .set_signals(signal_df, signal_name="z_score")
        .set_backtest_result(metrics={"sharpe": 1.6, "max_drawdown": -0.08})
        .enable_actions(run_backtest_audit=True, compute_reliability_score=True)
    )

    bundle = wf.to_bundle()
    client.ingest_bundle(strategy_id, bundle)
"""
from __future__ import annotations

from typing import Any


class QuantResearchWorkflow:
    """High-level, stepwise builder for QuantFidelity evidence bundles.

    Designed for use in Jupyter notebooks and research scripts.  Each
    ``set_*`` and ``enable_*`` method returns ``self`` for optional chaining.
    Call :meth:`to_bundle` to produce a fully assembled
    :class:`~quantfidelity.bundle.EvidenceBundle`.

    Parameters
    ----------
    strategy_name:
        Human-readable strategy name.  Used only for display / ``__repr__``.
    strategy_id:
        UUID of the strategy.  Required if you call
        :meth:`~quantfidelity.client.QuantFidelityClient.ingest_bundle` via
        the workflow.
    version_label:
        If provided, a strategy version section is automatically added to the
        bundle with this label.  You can override it later with
        :meth:`set_version`.
    """

    def __init__(
        self,
        strategy_name: str | None = None,
        strategy_id: str | None = None,
        version_label: str | None = None,
    ) -> None:
        self._strategy_name = strategy_name
        self._strategy_id = strategy_id
        self._version_label = version_label
        self._version_kwargs: dict[str, Any] | None = (
            {"version_label": version_label} if version_label else None
        )
        self._config: dict[str, Any] | None = None
        self._universe: dict[str, Any] | None = None
        self._dataset: dict[str, Any] | None = None
        self._signal: dict[str, Any] | None = None
        self._run: dict[str, Any] | None = None
        self._actions: dict[str, Any] | None = None

    # ------------------------------------------------------------------ #
    # Properties                                                           #
    # ------------------------------------------------------------------ #

    @property
    def strategy_id(self) -> str | None:
        """UUID of the target strategy."""
        return self._strategy_id

    @property
    def strategy_name(self) -> str | None:
        """Human-readable strategy name."""
        return self._strategy_name

    # ------------------------------------------------------------------ #
    # Builder methods                                                      #
    # ------------------------------------------------------------------ #

    def set_version(
        self,
        version_label: str,
        *,
        git_commit: str | None = None,
        branch_name: str | None = None,
        code_path: str | None = None,
        signal_name: str | None = None,
        signal_description: str | None = None,
    ) -> "QuantResearchWorkflow":
        """Set the strategy version for this workflow.

        Parameters
        ----------
        version_label:
            Version identifier, e.g. ``"v1.0.0"``.
        git_commit:
            Full or short SHA of the corresponding commit.
        branch_name:
            Git branch name.
        code_path:
            Path to the strategy entry-point file.
        signal_name:
            Name of the primary signal this version uses.
        signal_description:
            Human-readable description of the signal.
        """
        self._version_label = version_label
        self._version_kwargs = {
            k: v
            for k, v in {
                "version_label": version_label,
                "git_commit": git_commit,
                "branch_name": branch_name,
                "code_path": code_path,
                "signal_name": signal_name,
                "signal_description": signal_description,
            }.items()
            if v is not None
        }
        return self

    def set_config(
        self,
        params: dict[str, Any] | None = None,
        assumptions: dict[str, Any] | None = None,
        portfolio: dict[str, Any] | None = None,
        label: str = "config",
    ) -> "QuantResearchWorkflow":
        """Set strategy configuration.

        Parameters
        ----------
        params:
            Strategy parameter dict (lookback windows, thresholds, etc.).
        assumptions:
            Execution assumption dict (cost_bps, fill model, etc.).
        portfolio:
            Portfolio-level constraints or settings.
        label:
            Config snapshot label.  Defaults to ``"config"``.
        """
        cfg: dict[str, Any] = {}
        if params:
            cfg["params"] = params
        if assumptions:
            cfg["assumptions"] = assumptions
        if portfolio:
            cfg["portfolio"] = portfolio
        self._config = {"label": label, "config_json": cfg}
        return self

    def set_universe(
        self,
        symbols: Any,
        label: str = "universe",
        metadata: dict[str, Any] | None = None,
        source_type: str = "sdk_symbols",
    ) -> "QuantResearchWorkflow":
        """Set the investment universe.

        Parameters
        ----------
        symbols:
            Any iterable of ticker strings.
        label:
            Universe snapshot label.  Defaults to ``"universe"``.
        metadata:
            Arbitrary metadata dict (e.g. ``{"index": "SP500"}``).
        source_type:
            How the universe was sourced.
        """
        self._universe = {
            "label": label,
            "symbols": list(symbols),
            "metadata_json": metadata,
            "source_type": source_type,
        }
        return self

    def set_dataset(
        self,
        name: str,
        rows_or_df: Any = None,
        snapshot_label: str = "dataset-snapshot",
        asset_class: str = "equity",
        dataset_type: str = "equity_prices",
        source_type: str = "sdk_table",
    ) -> "QuantResearchWorkflow":
        """Set the price/feature dataset.

        Parameters
        ----------
        name:
            Dataset name (e.g. ``"SP500 OHLCV 2024"``).
        rows_or_df:
            Optional ``list[dict]`` or pandas DataFrame of dataset rows.
            When provided, a dataset snapshot will be included in the bundle.
        snapshot_label:
            Label for the dataset snapshot.  Defaults to ``"dataset-snapshot"``.
        asset_class:
            Asset class (e.g. ``"equity"``).
        dataset_type:
            Type of data (e.g. ``"equity_prices"``).
        source_type:
            Data source type.
        """
        self._dataset = {
            "name": name,
            "rows_or_df": rows_or_df,
            "snapshot_label": snapshot_label,
            "asset_class": asset_class,
            "dataset_type": dataset_type,
            "source_type": source_type,
        }
        return self

    def set_signals(
        self,
        rows_or_df: Any,
        label: str = "signal-snapshot",
        signal_name: str | None = None,
        signal_column: str = "signal",
    ) -> "QuantResearchWorkflow":
        """Set the signal data.

        Parameters
        ----------
        rows_or_df:
            ``list[dict]`` or pandas DataFrame of signal rows.
        label:
            Signal snapshot label.  Defaults to ``"signal-snapshot"``.
        signal_name:
            Name of the signal (e.g. ``"z_score"``).
        signal_column:
            Column name containing signal values.  Defaults to ``"signal"``.
        """
        self._signal = {
            "rows_or_df": rows_or_df,
            "label": label,
            "signal_name": signal_name,
            "signal_column": signal_column,
        }
        return self

    def set_backtest_result(
        self,
        params: dict[str, Any] | None = None,
        assumptions: dict[str, Any] | None = None,
        metrics: dict[str, Any] | None = None,
        run_name: str = "backtest",
    ) -> "QuantResearchWorkflow":
        """Set backtest run results.

        Parameters
        ----------
        params:
            Parameters used for this specific run.
        assumptions:
            Execution assumptions for this run.
        metrics:
            Performance metrics (sharpe, max_drawdown, etc.).
        run_name:
            Human-readable name for the run.
        """
        self._run = {
            "params": params,
            "assumptions": assumptions,
            "metrics": metrics,
            "run_name": run_name,
        }
        return self

    def enable_actions(
        self,
        run_backtest_audit: bool = True,
        compute_reliability_score: bool = True,
        generate_strategy_report: bool = False,
        generate_alerts: bool = False,
    ) -> "QuantResearchWorkflow":
        """Enable post-ingestion action flags.

        Parameters
        ----------
        run_backtest_audit:
            Compute a backtest reality-check audit.  Defaults to ``True``.
        compute_reliability_score:
            Compute and store a reliability score snapshot.  Defaults to ``True``.
        generate_strategy_report:
            Generate a strategy reliability report.
        generate_alerts:
            Run the alerts generation engine.
        """
        self._actions = {
            "run_backtest_audit": run_backtest_audit,
            "compute_reliability_score": compute_reliability_score,
            "generate_strategy_report": generate_strategy_report,
            "generate_alerts": generate_alerts,
        }
        return self

    # ------------------------------------------------------------------ #
    # Output / validation                                                  #
    # ------------------------------------------------------------------ #

    def to_bundle(self) -> "EvidenceBundle":  # noqa: F821
        """Assemble and return the :class:`~quantfidelity.bundle.EvidenceBundle`.

        Each configured section is applied in order:
        strategy version → config → universe → dataset → signals → run → actions.
        """
        from quantfidelity.bundle import EvidenceBundle  # noqa: PLC0415

        b = EvidenceBundle()

        if self._version_kwargs:
            b.with_strategy_version(**self._version_kwargs)

        if self._config:
            b.with_config_snapshot(
                self._config["label"],
                config_json=self._config["config_json"],
                strategy_version_label=self._version_label,
            )

        if self._universe:
            b.with_universe_from_symbols(
                self._universe["label"],
                self._universe["symbols"],
                strategy_version_label=self._version_label,
                source_type=self._universe.get("source_type", "sdk_symbols"),
                metadata_json=self._universe.get("metadata_json"),
            )

        if self._dataset:
            b.with_dataset(
                self._dataset["name"],
                asset_class=self._dataset["asset_class"],
                dataset_type=self._dataset["dataset_type"],
                source_type=self._dataset["source_type"],
            )
            if self._dataset.get("rows_or_df") is not None:
                b.with_dataset_snapshot_from_table(
                    self._dataset["snapshot_label"],
                    self._dataset["rows_or_df"],
                )

        if self._signal:
            b.with_signal_snapshot_from_table(
                self._signal["label"],
                self._signal["rows_or_df"],
                signal_name=self._signal.get("signal_name"),
                signal_column=self._signal.get("signal_column", "signal"),
                strategy_version_label=self._version_label,
                universe_snapshot_label=(
                    self._universe["label"] if self._universe else None
                ),
            )

        if self._run:
            b.with_backtest_run(
                self._run["run_name"],
                params=self._run.get("params"),
                assumptions=self._run.get("assumptions"),
                metrics=self._run.get("metrics"),
                strategy_version_label=self._version_label,
                dataset_snapshot_label=(
                    self._dataset["snapshot_label"] if self._dataset else None
                ),
                universe_snapshot_label=(
                    self._universe["label"] if self._universe else None
                ),
                signal_snapshot_label=(
                    self._signal["label"] if self._signal else None
                ),
            )

        if self._actions:
            b.with_actions(**self._actions)

        return b

    def to_dict(self) -> dict[str, Any]:
        """Return a plain dict representation of the assembled bundle."""
        return self.to_bundle().to_dict()

    def to_json(self, indent: int = 2) -> str:
        """Return a JSON string representation of the assembled bundle."""
        return self.to_bundle().to_json(indent=indent)

    def validate(self) -> list[str]:
        """Run SDK-side validation on the assembled bundle.

        Returns
        -------
        list[str]
            Human-readable validation issues.  Empty list = valid.
        """
        return self.to_bundle().validate()

    def raise_if_invalid(self) -> None:
        """Raise :class:`~quantfidelity.exceptions.QuantFidelityValidationError`
        if validation finds any issues.
        """
        self.to_bundle().raise_if_invalid()

    # ------------------------------------------------------------------ #
    # Dunder helpers                                                       #
    # ------------------------------------------------------------------ #

    def __repr__(self) -> str:
        parts: list[str] = []
        if self._strategy_name:
            parts.append(f"strategy={self._strategy_name!r}")
        if self._version_label:
            parts.append(f"version={self._version_label!r}")
        return f"QuantResearchWorkflow({', '.join(parts)})"
