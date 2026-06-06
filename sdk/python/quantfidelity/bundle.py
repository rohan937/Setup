"""EvidenceBundle — fluent builder for QuantFidelity evidence bundle payloads.

Mirrors the M22 backend ``EvidenceBundleRequest`` schema.  All sections are
optional; include only what you have logged evidence for.

Usage::

    from quantfidelity import EvidenceBundle

    bundle = (
        EvidenceBundle()
        .with_strategy_version("v1.0", git_commit="abc123")
        .with_config_snapshot(
            "config-baseline",
            config_json={
                "params": {"lookback": 20, "entry_z": 2.0},
                "assumptions": {"cost_bps": 5},
            },
        )
        .with_strategy_run("backtest-q1", run_type="backtest",
                           metrics_json={"sharpe": 1.4})
        .with_actions(run_backtest_audit=True, compute_reliability_score=True)
    )

    payload = bundle.to_dict()
    json_text = bundle.to_json(indent=2)
    bundle2 = EvidenceBundle.from_json(json_text)

Design notes:
- Internal state is a plain ``dict`` matching the API schema.
- ``with_*`` methods validate obvious type errors client-side (wrong types,
  empty required lists) but defer all business-logic validation to the server.
- Every ``with_*`` method returns ``self`` for optional chaining.
- ``None`` values in sections are omitted from the serialized output so the
  payload stays clean.
"""
from __future__ import annotations

import json
from typing import Any

from quantfidelity.exceptions import QuantFidelityValidationError


def _drop_none(d: dict) -> dict:
    """Return a shallow copy of *d* with all None values removed."""
    return {k: v for k, v in d.items() if v is not None}


class EvidenceBundle:
    """Fluent builder for a QuantFidelity evidence bundle payload.

    All sections are optional.  Build only the sections that contain evidence
    you want to submit to ``POST /api/strategies/{id}/evidence-bundles``.
    """

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    # ------------------------------------------------------------------ #
    # Section setters                                                      #
    # ------------------------------------------------------------------ #

    def with_strategy_version(
        self,
        version_label: str,
        *,
        git_commit: str | None = None,
        branch_name: str | None = None,
        code_path: str | None = None,
        signal_name: str | None = None,
        signal_description: str | None = None,
    ) -> "EvidenceBundle":
        """Attach a strategy version to this bundle.

        The backend will create the version if ``version_label`` does not
        already exist for the strategy, or silently reuse it if it does.

        Parameters
        ----------
        version_label:
            Version identifier, e.g. ``"v1.0.0"``.  Required.
        git_commit:
            Full or short SHA of the commit that this version corresponds to.
        branch_name:
            Git branch name (e.g. ``"main"``).
        code_path:
            Path to the strategy entry-point file (e.g. ``"strategies/aapl.py"``).
        signal_name:
            Name of the primary signal this version uses.
        signal_description:
            Human-readable description of the signal.
        """
        if not version_label or not version_label.strip():
            raise QuantFidelityValidationError("version_label must be a non-empty string")
        self._data["strategy_version"] = _drop_none(
            {
                "version_label": version_label,
                "git_commit": git_commit,
                "branch_name": branch_name,
                "code_path": code_path,
                "signal_name": signal_name,
                "signal_description": signal_description,
            }
        )
        return self

    def with_config_snapshot(
        self,
        label: str,
        *,
        config_json: dict[str, Any],
        strategy_version_label: str | None = None,
        source_type: str = "manual_json",
        source_filename: str | None = None,
    ) -> "EvidenceBundle":
        """Attach a config snapshot.

        Parameters
        ----------
        label:
            Human-readable label for this snapshot (e.g. ``"baseline-config"``).
        config_json:
            Must be a ``dict``.  Typically contains ``params`` and
            ``assumptions`` sub-dicts.
        strategy_version_label:
            If set, link this snapshot to the named version.
        source_type:
            How the config was sourced.  Defaults to ``"manual_json"``.
        source_filename:
            Optional path to the source file.
        """
        if not label or not label.strip():
            raise QuantFidelityValidationError("config snapshot label must be a non-empty string")
        if not isinstance(config_json, dict):
            raise QuantFidelityValidationError(
                f"config_json must be a dict (not {type(config_json).__name__})"
            )
        self._data["config_snapshot"] = _drop_none(
            {
                "label": label,
                "config_json": config_json,
                "strategy_version_label": strategy_version_label,
                "source_type": source_type,
                "source_filename": source_filename,
            }
        )
        return self

    def with_universe_snapshot(
        self,
        label: str,
        *,
        symbols: list[str],
        strategy_version_label: str | None = None,
        source_type: str = "manual_json",
        source_filename: str | None = None,
        metadata_json: dict[str, Any] | None = None,
    ) -> "EvidenceBundle":
        """Attach a universe snapshot.

        Parameters
        ----------
        label:
            Human-readable label (e.g. ``"sp500-2024-q1"``).
        symbols:
            Non-empty list of ticker symbols.  Normalised server-side
            (trimmed, uppercased, deduplicated, sorted).
        strategy_version_label:
            Link this snapshot to the named version.
        source_type:
            How the universe was sourced.
        source_filename:
            Optional path to the source file.
        metadata_json:
            Arbitrary metadata dict (e.g. ``{"rebalance_freq": "monthly"}``).
        """
        if not label or not label.strip():
            raise QuantFidelityValidationError("universe snapshot label must be a non-empty string")
        if not isinstance(symbols, list):
            raise QuantFidelityValidationError(
                f"symbols must be a list (not {type(symbols).__name__})"
            )
        if len(symbols) == 0:
            raise QuantFidelityValidationError("symbols must be a non-empty list")
        self._data["universe_snapshot"] = _drop_none(
            {
                "label": label,
                "symbols": symbols,
                "strategy_version_label": strategy_version_label,
                "source_type": source_type,
                "source_filename": source_filename,
                "metadata_json": metadata_json,
            }
        )
        return self

    def with_signal_snapshot(
        self,
        label: str,
        *,
        rows: list[dict[str, Any]],
        strategy_version_label: str | None = None,
        universe_snapshot_label: str | None = None,
        signal_name: str | None = None,
        source_type: str = "manual_json",
        source_filename: str | None = None,
        signal_column: str = "signal",
        metadata_json: dict[str, Any] | None = None,
    ) -> "EvidenceBundle":
        """Attach a signal snapshot.

        Parameters
        ----------
        label:
            Human-readable label (e.g. ``"z-score-signals-2024-q1"``).
        rows:
            Non-empty list of dicts.  Each dict should contain at minimum
            ``symbol``, ``timestamp``, and the signal column.
        strategy_version_label:
            Link this snapshot to the named version.
        universe_snapshot_label:
            Link this snapshot to the named universe snapshot.
        signal_name:
            Name of the signal (e.g. ``"return_zscore"``).
        source_type:
            How the signal was sourced.
        source_filename:
            Optional path to the source file.
        signal_column:
            Name of the signal column in ``rows``.  Defaults to ``"signal"``.
        metadata_json:
            Arbitrary metadata.
        """
        if not label or not label.strip():
            raise QuantFidelityValidationError("signal snapshot label must be a non-empty string")
        if not isinstance(rows, list):
            raise QuantFidelityValidationError(
                f"rows must be a list (not {type(rows).__name__})"
            )
        if len(rows) == 0:
            raise QuantFidelityValidationError("signal snapshot rows must be a non-empty list")
        self._data["signal_snapshot"] = _drop_none(
            {
                "label": label,
                "rows": rows,
                "strategy_version_label": strategy_version_label,
                "universe_snapshot_label": universe_snapshot_label,
                "signal_name": signal_name,
                "source_type": source_type,
                "source_filename": source_filename,
                "signal_column": signal_column,
                "metadata_json": metadata_json,
            }
        )
        return self

    def with_dataset(
        self,
        name: str,
        *,
        slug: str | None = None,
        description: str | None = None,
        asset_class: str = "equity",
        dataset_type: str = "equity_prices",
        source_type: str = "csv_upload",
    ) -> "EvidenceBundle":
        """Attach a dataset.

        The backend will create the dataset if one with the same ``name`` does
        not already exist in the project, or silently reuse it if it does.

        Parameters
        ----------
        name:
            Dataset name (e.g. ``"SP500 OHLCV 2024"``).
        slug:
            URL-friendly slug.  Auto-generated server-side if omitted.
        description:
            Human-readable description.
        asset_class:
            Asset class (e.g. ``"equity"``, ``"fx"``).
        dataset_type:
            Type of data (e.g. ``"equity_prices"``, ``"ohlcv"``).
        source_type:
            Data source (e.g. ``"csv_upload"``, ``"api"``).
        """
        if not name or not name.strip():
            raise QuantFidelityValidationError("dataset name must be a non-empty string")
        self._data["dataset"] = _drop_none(
            {
                "name": name,
                "slug": slug,
                "description": description,
                "asset_class": asset_class,
                "dataset_type": dataset_type,
                "source_type": source_type,
            }
        )
        return self

    def with_dataset_snapshot(
        self,
        *,
        rows: list[dict[str, Any]],
        snapshot_label: str | None = None,
        source_filename: str | None = None,
    ) -> "EvidenceBundle":
        """Attach a dataset snapshot.

        Requires a ``dataset`` section to be present in the same bundle (or
        an existing dataset to be reused).

        Parameters
        ----------
        rows:
            Non-empty list of record dicts.
        snapshot_label:
            Human-readable label for this snapshot version (e.g. ``"2024-q1"``).
        source_filename:
            Optional path to the source file.
        """
        if not isinstance(rows, list):
            raise QuantFidelityValidationError(
                f"dataset snapshot rows must be a list (not {type(rows).__name__})"
            )
        if len(rows) == 0:
            raise QuantFidelityValidationError("dataset snapshot rows must be a non-empty list")
        self._data["dataset_snapshot"] = _drop_none(
            {
                "rows": rows,
                "snapshot_label": snapshot_label,
                "source_filename": source_filename,
            }
        )
        return self

    def with_strategy_run(
        self,
        run_name: str,
        *,
        run_type: str = "backtest",
        status: str = "completed",
        strategy_version_label: str | None = None,
        dataset_snapshot_label: str | None = None,
        universe_snapshot_label: str | None = None,
        signal_snapshot_label: str | None = None,
        started_at: str | None = None,
        completed_at: str | None = None,
        params_json: dict[str, Any] | None = None,
        assumptions_json: dict[str, Any] | None = None,
        metrics_json: dict[str, Any] | None = None,
        universe_name: str | None = None,
        dataset_version: str | None = None,
        notes: str | None = None,
    ) -> "EvidenceBundle":
        """Attach a strategy run record.

        The run will be linked to the created version, dataset snapshot,
        universe snapshot, and/or signal snapshot by their labels.

        Parameters
        ----------
        run_name:
            Human-readable name for the run (e.g. ``"backtest-2024-q1"``).
        run_type:
            Type of run: ``"backtest"``, ``"paper"``, ``"research"``, ``"live"``.
        status:
            Run status.  Defaults to ``"completed"``.
        strategy_version_label:
            Link this run to the named strategy version.
        dataset_snapshot_label:
            Link this run to the named dataset snapshot.
        universe_snapshot_label:
            Link this run to the named universe snapshot.
        signal_snapshot_label:
            Link this run to the named signal snapshot.
        started_at:
            ISO-8601 datetime string when the run started.
        completed_at:
            ISO-8601 datetime string when the run completed.
        params_json:
            Strategy parameter dict used for this run.
        assumptions_json:
            Execution assumption dict (cost, fill model, etc.).
        metrics_json:
            Performance metrics dict (sharpe, max_drawdown, etc.).
        universe_name:
            Human-readable name for the universe traded.
        dataset_version:
            Free-text dataset version label.
        notes:
            Freeform notes for this run.
        """
        if not run_name or not run_name.strip():
            raise QuantFidelityValidationError("run_name must be a non-empty string")
        if not run_type or not run_type.strip():
            raise QuantFidelityValidationError("run_type must be a non-empty string")
        self._data["strategy_run"] = _drop_none(
            {
                "run_name": run_name,
                "run_type": run_type,
                "status": status,
                "strategy_version_label": strategy_version_label,
                "dataset_snapshot_label": dataset_snapshot_label,
                "universe_snapshot_label": universe_snapshot_label,
                "signal_snapshot_label": signal_snapshot_label,
                "started_at": started_at,
                "completed_at": completed_at,
                "params_json": params_json,
                "assumptions_json": assumptions_json,
                "metrics_json": metrics_json,
                "universe_name": universe_name,
                "dataset_version": dataset_version,
                "notes": notes,
            }
        )
        return self

    def with_dataset_snapshot_from_table(
        self,
        snapshot_label: str | None,
        rows_or_df: Any,
        *,
        source_filename: str | None = None,
    ) -> "EvidenceBundle":
        """Attach a dataset snapshot from a ``list[dict]`` or pandas DataFrame.

        Parameters
        ----------
        snapshot_label:
            Human-readable label for this snapshot version.
        rows_or_df:
            Either a ``list[dict]`` or a pandas ``DataFrame``.
        source_filename:
            Optional path to the source file.
        """
        from quantfidelity.dataframe import rows_from_table  # noqa: PLC0415

        rows = rows_from_table(rows_or_df)
        return self.with_dataset_snapshot(
            rows=rows,
            snapshot_label=snapshot_label,
            source_filename=source_filename,
        )

    def with_signal_snapshot_from_table(
        self,
        label: str,
        rows_or_df: Any,
        *,
        signal_name: str | None = None,
        signal_column: str = "signal",
        strategy_version_label: str | None = None,
        universe_snapshot_label: str | None = None,
        source_type: str = "sdk_table",
        source_filename: str | None = None,
        metadata_json: dict[str, Any] | None = None,
    ) -> "EvidenceBundle":
        """Attach a signal snapshot from a ``list[dict]`` or pandas DataFrame.

        Parameters
        ----------
        label:
            Human-readable label for this snapshot.
        rows_or_df:
            Either a ``list[dict]`` or a pandas ``DataFrame``.
        signal_name:
            Name of the signal.
        signal_column:
            Name of the signal column.  Defaults to ``"signal"``.
        strategy_version_label:
            Link this snapshot to the named version.
        universe_snapshot_label:
            Link this snapshot to the named universe snapshot.
        source_type:
            How the signal was sourced.  Defaults to ``"sdk_table"``.
        source_filename:
            Optional path to the source file.
        metadata_json:
            Arbitrary metadata.
        """
        from quantfidelity.dataframe import rows_from_table  # noqa: PLC0415

        rows = rows_from_table(rows_or_df)
        return self.with_signal_snapshot(
            label,
            rows=rows,
            signal_name=signal_name,
            signal_column=signal_column,
            strategy_version_label=strategy_version_label,
            universe_snapshot_label=universe_snapshot_label,
            source_type=source_type,
            source_filename=source_filename,
            metadata_json=metadata_json,
        )

    def with_universe_from_symbols(
        self,
        label: str,
        symbols: Any,
        *,
        strategy_version_label: str | None = None,
        source_type: str = "sdk_symbols",
        source_filename: str | None = None,
        metadata_json: dict[str, Any] | None = None,
    ) -> "EvidenceBundle":
        """Attach a universe snapshot from a list of symbol strings.

        Parameters
        ----------
        label:
            Human-readable label (e.g. ``"sp500-2024-q1"``).
        symbols:
            Any iterable of ticker strings (list, tuple, set, generator, …).
        strategy_version_label:
            Link this snapshot to the named version.
        source_type:
            How the universe was sourced.  Defaults to ``"sdk_symbols"``.
        source_filename:
            Optional path to the source file.
        metadata_json:
            Arbitrary metadata dict.
        """
        return self.with_universe_snapshot(
            label,
            symbols=list(symbols),
            strategy_version_label=strategy_version_label,
            source_type=source_type,
            source_filename=source_filename,
            metadata_json=metadata_json,
        )

    def with_backtest_run(
        self,
        run_name: str,
        *,
        params: dict[str, Any] | None = None,
        assumptions: dict[str, Any] | None = None,
        metrics: dict[str, Any] | None = None,
        strategy_version_label: str | None = None,
        dataset_snapshot_label: str | None = None,
        universe_snapshot_label: str | None = None,
        signal_snapshot_label: str | None = None,
        universe_name: str | None = None,
        dataset_version: str | None = None,
        notes: str | None = None,
    ) -> "EvidenceBundle":
        """Clean alias for ``with_strategy_run(run_type='backtest')``.

        Parameters
        ----------
        run_name:
            Human-readable name for the run.
        params:
            Strategy parameter dict used for this run (``params_json``).
        assumptions:
            Execution assumption dict (``assumptions_json``).
        metrics:
            Performance metrics dict (``metrics_json``).
        """
        return self.with_strategy_run(
            run_name,
            run_type="backtest",
            params_json=params,
            assumptions_json=assumptions,
            metrics_json=metrics,
            strategy_version_label=strategy_version_label,
            dataset_snapshot_label=dataset_snapshot_label,
            universe_snapshot_label=universe_snapshot_label,
            signal_snapshot_label=signal_snapshot_label,
            universe_name=universe_name,
            dataset_version=dataset_version,
            notes=notes,
        )

    def with_research_run(
        self,
        run_name: str,
        *,
        params: dict[str, Any] | None = None,
        assumptions: dict[str, Any] | None = None,
        metrics: dict[str, Any] | None = None,
        strategy_version_label: str | None = None,
        notes: str | None = None,
    ) -> "EvidenceBundle":
        """Clean alias for ``with_strategy_run(run_type='research')``.

        Parameters
        ----------
        run_name:
            Human-readable name for the run.
        params:
            Strategy parameter dict (``params_json``).
        assumptions:
            Execution assumption dict (``assumptions_json``).
        metrics:
            Performance metrics dict (``metrics_json``).
        """
        return self.with_strategy_run(
            run_name,
            run_type="research",
            params_json=params,
            assumptions_json=assumptions,
            metrics_json=metrics,
            strategy_version_label=strategy_version_label,
            notes=notes,
        )

    def with_paper_run(
        self,
        run_name: str,
        *,
        params: dict[str, Any] | None = None,
        assumptions: dict[str, Any] | None = None,
        metrics: dict[str, Any] | None = None,
        strategy_version_label: str | None = None,
        dataset_snapshot_label: str | None = None,
        universe_snapshot_label: str | None = None,
        signal_snapshot_label: str | None = None,
        notes: str | None = None,
    ) -> "EvidenceBundle":
        """Clean alias for with_strategy_run(run_type='paper').

        Use this to log a paper (simulated live-like) trading run for
        shadow monitoring comparison against a backtest baseline.
        """
        return self.with_strategy_run(
            run_name,
            run_type="paper",
            params_json=params,
            assumptions_json=assumptions,
            metrics_json=metrics,
            strategy_version_label=strategy_version_label,
            dataset_snapshot_label=dataset_snapshot_label,
            universe_snapshot_label=universe_snapshot_label,
            signal_snapshot_label=signal_snapshot_label,
            notes=notes,
        )

    def validate(self) -> list[str]:
        """Return a list of human-readable validation issues. Empty list = valid.

        Performs lightweight SDK-side checks only; the backend remains the
        authoritative source of truth for full business-logic validation.

        Returns
        -------
        list[str]
            Each entry is a human-readable description of a validation issue.
            An empty list means the bundle looks valid from the client side.
        """
        issues: list[str] = []

        if "config_snapshot" in self._data:
            cj = self._data["config_snapshot"].get("config_json")
            if cj is not None and not isinstance(cj, dict):
                issues.append(
                    "config_snapshot.config_json must be a dict object, not a list or scalar"
                )

        if "dataset_snapshot" in self._data:
            rows = self._data["dataset_snapshot"].get("rows", [])
            if not isinstance(rows, list):
                issues.append("dataset_snapshot.rows must be a list")
            elif len(rows) == 0:
                issues.append("dataset_snapshot.rows is empty — no data to ingest")
            elif not all(isinstance(r, dict) for r in rows):
                issues.append(
                    "dataset_snapshot.rows must contain dicts (not scalars or lists)"
                )

        if "signal_snapshot" in self._data:
            ss = self._data["signal_snapshot"]
            rows = ss.get("rows", [])
            signal_col = ss.get("signal_column", "signal")
            if not isinstance(rows, list):
                issues.append("signal_snapshot.rows must be a list")
            elif len(rows) == 0:
                issues.append("signal_snapshot.rows is empty")
            else:
                missing = [i for i, r in enumerate(rows) if signal_col not in r]
                if missing:
                    issues.append(
                        f"signal_snapshot.rows: {len(missing)} row(s) missing"
                        f" '{signal_col}' column"
                    )

        if "universe_snapshot" in self._data:
            syms = self._data["universe_snapshot"].get("symbols", [])
            if not isinstance(syms, list) or len(syms) == 0:
                issues.append("universe_snapshot.symbols must be a non-empty list")

        if "strategy_run" in self._data:
            sr = self._data["strategy_run"]
            for field in ("params_json", "assumptions_json", "metrics_json"):
                val = sr.get(field)
                if val is not None and not isinstance(val, dict):
                    issues.append(
                        f"strategy_run.{field} must be a dict or null,"
                        f" got {type(val).__name__}"
                    )

        if "actions" in self._data:
            for k, v in self._data["actions"].items():
                if not isinstance(v, bool):
                    issues.append(
                        f"actions.{k} must be a boolean, got {type(v).__name__}"
                    )

        return issues

    def raise_if_invalid(self) -> None:
        """Raise :class:`~quantfidelity.exceptions.QuantFidelityValidationError`
        if :meth:`validate` finds any issues.

        Raises
        ------
        QuantFidelityValidationError
            When one or more validation issues are detected.
        """
        issues = self.validate()
        if issues:
            raise QuantFidelityValidationError(
                "Evidence bundle validation failed:\n"
                + "\n".join(f"  - {i}" for i in issues)
            )

    def with_actions(
        self,
        *,
        run_backtest_audit: bool = False,
        compute_reliability_score: bool = False,
        generate_strategy_report: bool = False,
        generate_alerts: bool = False,
    ) -> "EvidenceBundle":
        """Set post-ingestion action flags.

        Actions are executed deterministically after all evidence sections
        have been created.  They reuse existing services — no AI, no live data.

        Parameters
        ----------
        run_backtest_audit:
            Compute a backtest reality-check audit for the submitted run.
            Requires a ``strategy_run`` section with ``run_type="backtest"``.
        compute_reliability_score:
            Compute and store a reliability score snapshot for the strategy.
        generate_strategy_report:
            Generate a strategy reliability report.
        generate_alerts:
            Run the alerts generation engine for the strategy's organisation.
        """
        self._data["actions"] = {
            "run_backtest_audit": run_backtest_audit,
            "compute_reliability_score": compute_reliability_score,
            "generate_strategy_report": generate_strategy_report,
            "generate_alerts": generate_alerts,
        }
        return self

    # ------------------------------------------------------------------ #
    # Section removal helpers                                              #
    # ------------------------------------------------------------------ #

    def without_strategy_version(self) -> "EvidenceBundle":
        """Remove the strategy_version section from this bundle."""
        self._data.pop("strategy_version", None)
        return self

    def without_actions(self) -> "EvidenceBundle":
        """Remove the actions section from this bundle."""
        self._data.pop("actions", None)
        return self

    # ------------------------------------------------------------------ #
    # Inspection helpers                                                   #
    # ------------------------------------------------------------------ #

    def sections(self) -> list[str]:
        """Return the names of all sections currently set in this bundle."""
        return list(self._data.keys())

    def is_empty(self) -> bool:
        """Return True if no sections have been set."""
        return len(self._data) == 0

    # ------------------------------------------------------------------ #
    # Serialisation / deserialisation                                      #
    # ------------------------------------------------------------------ #

    def to_dict(self) -> dict[str, Any]:
        """Return a plain dict representation of the bundle, ready to POST.

        Sections that have not been set are omitted.  Within each section,
        ``None`` fields are omitted (they are already stripped by ``_drop_none``
        in each setter).
        """
        return dict(self._data)

    def to_json(self, indent: int | None = 2, **kwargs: Any) -> str:
        """Return a JSON string representation of the bundle.

        Parameters
        ----------
        indent:
            Indentation level for pretty-printing.  Defaults to 2.
        **kwargs:
            Additional keyword arguments forwarded to ``json.dumps``.
        """
        return json.dumps(self.to_dict(), indent=indent, default=str, **kwargs)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EvidenceBundle":
        """Create an :class:`EvidenceBundle` from a plain dict.

        This is the inverse of :meth:`to_dict`.  The dict is stored as-is —
        no client-side validation is run on load.

        Parameters
        ----------
        data:
            A dict matching the evidence bundle schema.
        """
        if not isinstance(data, dict):
            raise QuantFidelityValidationError(
                f"EvidenceBundle.from_dict expects a dict, got {type(data).__name__}"
            )
        bundle = cls()
        bundle._data = dict(data)
        return bundle

    @classmethod
    def from_json(cls, json_text: str) -> "EvidenceBundle":
        """Create an :class:`EvidenceBundle` from a JSON string.

        Parameters
        ----------
        json_text:
            A JSON string returned by :meth:`to_json` or read from a file.
        """
        try:
            data = json.loads(json_text)
        except json.JSONDecodeError as exc:
            raise QuantFidelityValidationError(
                f"Cannot parse evidence bundle JSON: {exc}"
            ) from exc
        return cls.from_dict(data)

    # ------------------------------------------------------------------ #
    # Dunder helpers                                                       #
    # ------------------------------------------------------------------ #

    def __repr__(self) -> str:
        sections = ", ".join(self._data.keys()) or "(empty)"
        return f"EvidenceBundle(sections=[{sections}])"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, EvidenceBundle):
            return NotImplemented
        return self._data == other._data
