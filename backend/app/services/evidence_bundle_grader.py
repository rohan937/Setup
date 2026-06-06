"""Evidence Bundle Quality Grader service (M97).

PURELY STRUCTURAL and READ-ONLY. Takes a parsed evidence bundle dict (the shape
produced by ``EvidenceBundleRequest.model_dump()``) and grades the completeness
and structure of the evidence it contains. It performs NO database access — it
only inspects the bundle structure.

Language policy:
  Use: "present", "absent", "logged", "noted", "not declared"
  Never: "fraud", "falsified", "better strategy", "should trade"
  Always include disclaimer.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

# ---------------------------------------------------------------------------
# Disclaimer
# ---------------------------------------------------------------------------

DISCLAIMER = (
    "Bundle grading checks evidence completeness and structure. "
    "It is not trading advice."
)

# Metrics that count as "useful" for run quality.
USEFUL_METRICS = (
    "sharpe",
    "annual_return",
    "volatility",
    "max_drawdown",
    "turnover",
    "trade_count",
    "win_rate",
)

# Column-name hints used for structural detection in row dicts.
_DATE_HINTS = ("date", "timestamp", "datetime", "time", "ts", "dt")
_SYMBOL_HINTS = ("symbol", "ticker", "asset", "instrument", "sym")

# The core sections we report on in the included checklist.
_SECTION_LABELS = {
    "strategy_version": "Strategy version",
    "config_snapshot": "Config snapshot",
    "universe_snapshot": "Universe snapshot",
    "signal_snapshot": "Signal snapshot",
    "dataset": "Dataset",
    "dataset_snapshot": "Dataset snapshot",
    "strategy_run": "Strategy run",
}

_STAGES = (
    "research",
    "backtest_review",
    "paper_candidate",
    "shadow",
    "production_candidate",
)


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class IncludedItem:
    key: str
    label: str
    status: str  # present | partial | absent
    quality: str  # good | fair | weak | missing
    details: str


@dataclass
class MissingItem:
    key: str
    label: str
    severity: str  # low | medium | high
    why_it_matters: str


@dataclass
class BundleGradeData:
    quality_score: float  # 0-100
    letter_grade: str
    verdict: str
    stage_sufficiency: dict[str, str]
    sufficient_for: list[str]
    not_sufficient_for: list[str]
    included: list[IncludedItem]
    missing: list[MissingItem]
    warnings: list[str]
    recommended_fixes: list[str]
    generated_at: datetime
    disclaimer: str = DISCLAIMER


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _section(bundle: dict, key: str) -> dict | None:
    """Return a section as a dict, or None if absent/empty/non-dict."""
    value = (bundle or {}).get(key)
    if isinstance(value, dict) and value:
        return value
    return None


def _as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _row_keys_lower(rows: list) -> set[str]:
    """Collect all lowercased keys present across row dicts."""
    keys: set[str] = set()
    for row in rows:
        if isinstance(row, dict):
            keys.update(str(k).lower() for k in row.keys())
    return keys


def _has_hint(keys: set[str], hints: tuple[str, ...]) -> bool:
    return any(any(h in k for h in hints) for k in keys)


def _detect_symbol_column(rows: list) -> str | None:
    """Return the actual key (original casing) that looks like a symbol column."""
    for row in rows:
        if isinstance(row, dict):
            for k in row.keys():
                if any(h in str(k).lower() for h in _SYMBOL_HINTS):
                    return k
    return None


def _assumptions(config: dict | None) -> dict:
    config_json = _as_dict((config or {}).get("config_json"))
    return _as_dict(config_json.get("assumptions"))


def _has_cost(assumptions: dict) -> bool:
    return (
        assumptions.get("transaction_cost_bps") is not None
        or assumptions.get("cost_bps") is not None
    )


def _useful_metric_count(run: dict | None) -> int:
    metrics = _as_dict((run or {}).get("metrics_json"))
    return sum(
        1
        for m in USEFUL_METRICS
        if metrics.get(m) is not None
    )


def _run_type(run: dict | None) -> str:
    return str((run or {}).get("run_type") or "").strip().lower()


def _is_paper_or_shadow(run: dict | None) -> bool:
    return _run_type(run) in ("paper", "shadow", "live")


# ---------------------------------------------------------------------------
# summarize_bundle_contents
# ---------------------------------------------------------------------------


def summarize_bundle_contents(bundle: dict) -> list[IncludedItem]:
    """Return an IncludedItem for each core section (present or absent)."""
    bundle = _as_dict(bundle)
    items: list[IncludedItem] = []

    # --- strategy_version ---
    sv = _section(bundle, "strategy_version")
    if sv is None:
        items.append(
            IncludedItem(
                "strategy_version",
                _SECTION_LABELS["strategy_version"],
                "absent",
                "missing",
                "No strategy version declared.",
            )
        )
    else:
        version_label = sv.get("version_label")
        signal_name = sv.get("signal_name")
        if version_label and signal_name:
            items.append(
                IncludedItem(
                    "strategy_version",
                    _SECTION_LABELS["strategy_version"],
                    "present",
                    "good",
                    f"Version '{version_label}' with signal '{signal_name}'.",
                )
            )
        elif version_label:
            items.append(
                IncludedItem(
                    "strategy_version",
                    _SECTION_LABELS["strategy_version"],
                    "partial",
                    "fair",
                    f"Version '{version_label}' present but no signal_name declared.",
                )
            )
        else:
            items.append(
                IncludedItem(
                    "strategy_version",
                    _SECTION_LABELS["strategy_version"],
                    "partial",
                    "fair",
                    "Version section present but no version_label.",
                )
            )

    # --- config_snapshot ---
    cfg = _section(bundle, "config_snapshot")
    if cfg is None:
        items.append(
            IncludedItem(
                "config_snapshot",
                _SECTION_LABELS["config_snapshot"],
                "absent",
                "missing",
                "No config snapshot declared.",
            )
        )
    else:
        assumptions = _assumptions(cfg)
        has_cost = _has_cost(assumptions)
        has_fill = assumptions.get("fill_model") is not None
        if not assumptions:
            items.append(
                IncludedItem(
                    "config_snapshot",
                    _SECTION_LABELS["config_snapshot"],
                    "partial",
                    "weak",
                    "Config present but assumptions block is empty.",
                )
            )
        elif has_cost and has_fill:
            items.append(
                IncludedItem(
                    "config_snapshot",
                    _SECTION_LABELS["config_snapshot"],
                    "present",
                    "good",
                    "Config present with cost and fill_model assumptions.",
                )
            )
        else:
            items.append(
                IncludedItem(
                    "config_snapshot",
                    _SECTION_LABELS["config_snapshot"],
                    "partial",
                    "fair",
                    "Config present but some cost/fill assumptions missing.",
                )
            )

    # --- universe_snapshot ---
    uni = _section(bundle, "universe_snapshot")
    if uni is None:
        items.append(
            IncludedItem(
                "universe_snapshot",
                _SECTION_LABELS["universe_snapshot"],
                "absent",
                "missing",
                "No universe snapshot declared.",
            )
        )
    else:
        symbols = _as_list(uni.get("symbols"))
        if len(symbols) >= 1:
            items.append(
                IncludedItem(
                    "universe_snapshot",
                    _SECTION_LABELS["universe_snapshot"],
                    "present",
                    "good",
                    f"Universe present with {len(symbols)} symbol(s).",
                )
            )
        else:
            items.append(
                IncludedItem(
                    "universe_snapshot",
                    _SECTION_LABELS["universe_snapshot"],
                    "partial",
                    "weak",
                    "Universe present but symbol list is empty.",
                )
            )

    # --- signal_snapshot ---
    sig = _section(bundle, "signal_snapshot")
    if sig is None:
        items.append(
            IncludedItem(
                "signal_snapshot",
                _SECTION_LABELS["signal_snapshot"],
                "absent",
                "missing",
                "No signal snapshot declared.",
            )
        )
    else:
        rows = _as_list(sig.get("rows"))
        signal_column = sig.get("signal_column") or "signal"
        if rows:
            row_keys = _row_keys_lower(rows)
            if str(signal_column).lower() in row_keys:
                items.append(
                    IncludedItem(
                        "signal_snapshot",
                        _SECTION_LABELS["signal_snapshot"],
                        "present",
                        "good",
                        f"Signal present with {len(rows)} row(s) and "
                        f"column '{signal_column}'.",
                    )
                )
            else:
                items.append(
                    IncludedItem(
                        "signal_snapshot",
                        _SECTION_LABELS["signal_snapshot"],
                        "partial",
                        "fair",
                        f"Signal present with {len(rows)} row(s) but column "
                        f"'{signal_column}' not found in rows.",
                    )
                )
        else:
            items.append(
                IncludedItem(
                    "signal_snapshot",
                    _SECTION_LABELS["signal_snapshot"],
                    "partial",
                    "weak",
                    "Signal section present but rows are empty.",
                )
            )

    # --- dataset ---
    ds = _section(bundle, "dataset")
    if ds is None:
        items.append(
            IncludedItem(
                "dataset",
                _SECTION_LABELS["dataset"],
                "absent",
                "missing",
                "No dataset declared.",
            )
        )
    else:
        name = ds.get("name")
        items.append(
            IncludedItem(
                "dataset",
                _SECTION_LABELS["dataset"],
                "present",
                "good" if name else "fair",
                f"Dataset '{name}' declared." if name else "Dataset present but unnamed.",
            )
        )

    # --- dataset_snapshot ---
    dss = _section(bundle, "dataset_snapshot")
    if dss is None:
        items.append(
            IncludedItem(
                "dataset_snapshot",
                _SECTION_LABELS["dataset_snapshot"],
                "absent",
                "missing",
                "No dataset snapshot declared.",
            )
        )
    else:
        rows = _as_list(dss.get("rows"))
        if rows:
            row_keys = _row_keys_lower(rows)
            has_date = _has_hint(row_keys, _DATE_HINTS)
            has_symbol = _has_hint(row_keys, _SYMBOL_HINTS)
            if has_date and has_symbol:
                items.append(
                    IncludedItem(
                        "dataset_snapshot",
                        _SECTION_LABELS["dataset_snapshot"],
                        "present",
                        "good",
                        f"Dataset snapshot present with {len(rows)} row(s), "
                        "date and symbol columns detected.",
                    )
                )
            else:
                missing_cols = []
                if not has_date:
                    missing_cols.append("date/timestamp")
                if not has_symbol:
                    missing_cols.append("symbol")
                items.append(
                    IncludedItem(
                        "dataset_snapshot",
                        _SECTION_LABELS["dataset_snapshot"],
                        "partial",
                        "fair",
                        f"Dataset snapshot present with {len(rows)} row(s) but "
                        f"missing column(s): {', '.join(missing_cols)}.",
                    )
                )
        else:
            items.append(
                IncludedItem(
                    "dataset_snapshot",
                    _SECTION_LABELS["dataset_snapshot"],
                    "partial",
                    "weak",
                    "Dataset snapshot present but rows are empty.",
                )
            )

    # --- strategy_run ---
    run = _section(bundle, "strategy_run")
    if run is None:
        items.append(
            IncludedItem(
                "strategy_run",
                _SECTION_LABELS["strategy_run"],
                "absent",
                "missing",
                "No strategy run declared.",
            )
        )
    else:
        metric_count = _useful_metric_count(run)
        run_type = run.get("run_type") or "backtest"
        if metric_count >= 3:
            items.append(
                IncludedItem(
                    "strategy_run",
                    _SECTION_LABELS["strategy_run"],
                    "present",
                    "good",
                    f"Run ({run_type}) present with {metric_count} useful metric(s).",
                )
            )
        elif metric_count >= 1:
            items.append(
                IncludedItem(
                    "strategy_run",
                    _SECTION_LABELS["strategy_run"],
                    "partial",
                    "fair",
                    f"Run ({run_type}) present with {metric_count} useful metric(s).",
                )
            )
        else:
            items.append(
                IncludedItem(
                    "strategy_run",
                    _SECTION_LABELS["strategy_run"],
                    "partial",
                    "weak",
                    f"Run ({run_type}) present but no useful metrics logged.",
                )
            )

    return items


# ---------------------------------------------------------------------------
# evaluate_bundle_stage_sufficiency
# ---------------------------------------------------------------------------


def evaluate_bundle_stage_sufficiency(
    bundle: dict, target_stage: str | None = None
) -> dict[str, str]:
    """Map each lifecycle stage -> pass | warning | fail for this bundle."""
    bundle = _as_dict(bundle)

    sv = _section(bundle, "strategy_version")
    cfg = _section(bundle, "config_snapshot")
    uni = _section(bundle, "universe_snapshot")
    sig = _section(bundle, "signal_snapshot")
    dss = _section(bundle, "dataset_snapshot")
    run = _section(bundle, "strategy_run")

    actions = _as_dict(bundle.get("actions"))
    has_report_action = bool(actions.get("generate_strategy_report"))

    metric_count = _useful_metric_count(run)
    run_is_backtest = run is not None and _run_type(run) in ("", "backtest")
    run_is_paper = _is_paper_or_shadow(run)

    result: dict[str, str] = {}

    # --- research ---
    result["research"] = "pass" if (sv or cfg) else "fail"

    # --- backtest_review ---
    core_present = all([sv, cfg, uni, sig, dss, run])
    if core_present and run_is_backtest and metric_count >= 1:
        result["backtest_review"] = "pass"
    elif sum(bool(x) for x in (sv, cfg, uni, sig, dss, run)) >= 4 and run is not None:
        # Most present but minor gaps.
        result["backtest_review"] = "warning"
    else:
        result["backtest_review"] = "fail"

    # --- paper_candidate ---
    if result["backtest_review"] == "pass" and metric_count >= 3:
        result["paper_candidate"] = "pass" if has_report_action else "warning"
    elif result["backtest_review"] in ("pass", "warning"):
        result["paper_candidate"] = "warning"
    else:
        result["paper_candidate"] = "fail"

    # --- shadow ---
    if run_is_paper and metric_count >= 1:
        result["shadow"] = "pass"
    elif run is not None and metric_count >= 1:
        # Backtest only — usable run but not yet paper/shadow.
        result["shadow"] = "warning"
    else:
        result["shadow"] = "fail"

    # --- production_candidate ---
    high_completeness = core_present and metric_count >= 3
    if run_is_paper and high_completeness:
        result["production_candidate"] = "pass"
    elif run is not None and (run_is_paper or high_completeness):
        result["production_candidate"] = "warning"
    else:
        result["production_candidate"] = "fail"

    return result


# ---------------------------------------------------------------------------
# grade_evidence_bundle
# ---------------------------------------------------------------------------


def grade_evidence_bundle(bundle: dict) -> BundleGradeData:
    """Deterministically grade an evidence bundle's structure and completeness."""
    bundle = _as_dict(bundle)

    sv = _section(bundle, "strategy_version")
    cfg = _section(bundle, "config_snapshot")
    uni = _section(bundle, "universe_snapshot")
    sig = _section(bundle, "signal_snapshot")
    ds = _section(bundle, "dataset")
    dss = _section(bundle, "dataset_snapshot")
    run = _section(bundle, "strategy_run")
    actions = _as_dict(bundle.get("actions"))

    score = 100.0
    warnings: list[str] = []
    missing: list[MissingItem] = []

    # --- core-section penalties ---
    if sv is None:
        score -= 8
        missing.append(
            MissingItem(
                "strategy_version",
                _SECTION_LABELS["strategy_version"],
                "medium",
                "Version identity ties evidence to a specific code revision.",
            )
        )
    if cfg is None:
        score -= 15
        missing.append(
            MissingItem(
                "config_snapshot",
                _SECTION_LABELS["config_snapshot"],
                "high",
                "Config declares the parameters and cost assumptions behind results.",
            )
        )
    if uni is None:
        score -= 12
        missing.append(
            MissingItem(
                "universe_snapshot",
                _SECTION_LABELS["universe_snapshot"],
                "medium",
                "Universe defines which symbols the strategy was evaluated on.",
            )
        )
    if ds is None or dss is None:
        score -= 15
        missing.append(
            MissingItem(
                "dataset_snapshot",
                _SECTION_LABELS["dataset_snapshot"],
                "medium",
                "Dataset evidence anchors results to reproducible input data.",
            )
        )
    if sig is None:
        score -= 12
        missing.append(
            MissingItem(
                "signal_snapshot",
                _SECTION_LABELS["signal_snapshot"],
                "medium",
                "Signal rows show the actual positions/scores driving the run.",
            )
        )
    if run is None:
        score -= 20
        missing.append(
            MissingItem(
                "strategy_run",
                _SECTION_LABELS["strategy_run"],
                "high",
                "A run with metrics is the core result being evidenced.",
            )
        )
    else:
        metrics = _as_dict(run.get("metrics_json"))
        if not metrics:
            score -= 10

    # --- quality warnings + small penalties ---
    if cfg is not None:
        assumptions = _assumptions(cfg)
        if not _has_cost(assumptions):
            warnings.append(
                "Config assumptions do not declare transaction_cost_bps/cost_bps."
            )
            score -= 5
        if assumptions.get("slippage_bps") is None:
            warnings.append("Config assumptions do not declare slippage_bps.")
            score -= 3
        if assumptions.get("fill_model") is None:
            warnings.append("Config assumptions do not declare fill_model.")
            score -= 3

    if uni is not None and not _as_list(uni.get("symbols")):
        warnings.append("Universe snapshot is present but contains no symbols.")
        score -= 5

    if dss is not None:
        ds_rows = _as_list(dss.get("rows"))
        if not ds_rows:
            warnings.append("Dataset snapshot is present but has no rows.")
            score -= 5
        else:
            ds_keys = _row_keys_lower(ds_rows)
            if not _has_hint(ds_keys, _DATE_HINTS):
                warnings.append(
                    "Dataset snapshot rows have no date/timestamp column detected."
                )
                score -= 3
            if not _has_hint(ds_keys, _SYMBOL_HINTS):
                warnings.append(
                    "Dataset snapshot rows have no symbol column detected."
                )
                score -= 2

    if sig is not None:
        sig_rows = _as_list(sig.get("rows"))
        if not sig_rows:
            warnings.append("Signal snapshot is present but has no rows.")
            score -= 4

    # signal + universe symbol overlap
    if sig is not None and uni is not None:
        sig_rows = _as_list(sig.get("rows"))
        uni_symbols = {str(s).lower() for s in _as_list(uni.get("symbols")) if s}
        symbol_key = _detect_symbol_column(sig_rows)
        if sig_rows and uni_symbols and symbol_key is not None:
            sig_symbols = {
                str(r.get(symbol_key)).lower()
                for r in sig_rows
                if isinstance(r, dict) and r.get(symbol_key) is not None
            }
            if sig_symbols and not (sig_symbols & uni_symbols):
                warnings.append(
                    "Signal symbols do not overlap with universe symbols."
                )
                score -= 5

    if run is not None:
        if not run.get("run_type"):
            warnings.append("Strategy run does not declare a run_type.")
            score -= 2
        metrics = _as_dict(run.get("metrics_json"))
        if metrics and metrics.get("sharpe") is None:
            warnings.append("Run metrics do not include sharpe (minor).")

    # --- non-section missing items ---
    if run is None or not _is_paper_or_shadow(run):
        missing.append(
            MissingItem(
                "paper_run",
                "Paper / shadow run",
                "medium",
                "Paper runs enable shadow monitoring and research-to-reality "
                "drift checks.",
            )
        )
    if not actions.get("generate_strategy_report"):
        missing.append(
            MissingItem(
                "reliability_report",
                "Reliability report",
                "low",
                "A reliability report is an external/optional artifact generated "
                "after ingestion.",
            )
        )

    # --- final score / grade / verdict ---
    quality_score = max(0.0, min(100.0, round(score, 1)))

    if quality_score >= 95:
        letter_grade = "A"
    elif quality_score >= 90:
        letter_grade = "A-"
    elif quality_score >= 85:
        letter_grade = "B+"
    elif quality_score >= 80:
        letter_grade = "B"
    elif quality_score >= 70:
        letter_grade = "C"
    elif quality_score >= 60:
        letter_grade = "D"
    else:
        letter_grade = "F"

    if run is None and cfg is None and ds is None:
        verdict = "invalid"
    elif quality_score >= 85:
        verdict = "excellent"
    elif quality_score >= 75:
        verdict = "good"
    elif quality_score >= 60:
        verdict = "usable"
    elif quality_score >= 40:
        verdict = "weak"
    else:
        verdict = "invalid"

    stage_sufficiency = evaluate_bundle_stage_sufficiency(bundle)
    sufficient_for = [s for s in _STAGES if stage_sufficiency.get(s) == "pass"]
    not_sufficient_for = [
        s for s in _STAGES if stage_sufficiency.get(s) == "fail"
    ]

    included = summarize_bundle_contents(bundle)

    # --- recommended fixes (deterministic, deduplicated, up to 8) ---
    recommended_fixes: list[str] = []

    def _add_fix(text: str) -> None:
        if text not in recommended_fixes:
            recommended_fixes.append(text)

    fix_by_key = {
        "strategy_version": "Add a strategy_version with a version_label and signal_name.",
        "config_snapshot": "Add a config_snapshot including cost and fill_model assumptions.",
        "universe_snapshot": "Add a universe_snapshot listing the evaluated symbols.",
        "dataset_snapshot": "Add a dataset and dataset_snapshot with dated, symbol-keyed rows.",
        "signal_snapshot": "Add a signal_snapshot with rows and the signal column.",
        "strategy_run": "Add a strategy_run with metrics_json (sharpe, returns, drawdown).",
        "paper_run": "Add a paper or shadow run to enable drift monitoring.",
        "reliability_report": "Enable generate_strategy_report to produce a reliability report.",
    }
    for item in missing:
        if item.key in fix_by_key:
            _add_fix(fix_by_key[item.key])

    for w in warnings:
        if "transaction_cost" in w or "cost_bps" in w:
            _add_fix("Declare transaction_cost_bps/cost_bps in config assumptions.")
        elif "slippage_bps" in w:
            _add_fix("Declare slippage_bps in config assumptions.")
        elif "fill_model" in w:
            _add_fix("Declare fill_model in config assumptions.")
        elif "no symbols" in w:
            _add_fix("Populate the universe_snapshot symbols list.")
        elif "no rows" in w and "Dataset" in w:
            _add_fix("Populate dataset_snapshot rows with input data.")
        elif "date/timestamp" in w:
            _add_fix("Include a date/timestamp column in dataset_snapshot rows.")
        elif "symbol column" in w:
            _add_fix("Include a symbol column in dataset_snapshot rows.")
        elif "no rows" in w and "Signal" in w:
            _add_fix("Populate signal_snapshot rows.")
        elif "do not overlap" in w:
            _add_fix("Align signal symbols with the declared universe symbols.")
        elif "run_type" in w:
            _add_fix("Declare a run_type on the strategy_run.")

    # External requirements that cannot live inside a bundle.
    _add_fix(
        "External requirement: create regression tests after ingestion."
    )
    _add_fix(
        "External requirement: external governance approvals are required for "
        "production promotion."
    )

    recommended_fixes = recommended_fixes[:8]

    return BundleGradeData(
        quality_score=quality_score,
        letter_grade=letter_grade,
        verdict=verdict,
        stage_sufficiency=stage_sufficiency,
        sufficient_for=sufficient_for,
        not_sufficient_for=not_sufficient_for,
        included=included,
        missing=missing,
        warnings=warnings,
        recommended_fixes=recommended_fixes,
        generated_at=datetime.now(timezone.utc),
        disclaimer=DISCLAIMER,
    )


# ---------------------------------------------------------------------------
# generate_bundle_quality_report
# ---------------------------------------------------------------------------


def generate_bundle_quality_report(bundle: dict, format: str = "json") -> str:
    """Render the bundle grade as JSON (default) or a Markdown report."""
    data = grade_evidence_bundle(bundle)

    if format == "markdown":
        lines: list[str] = []
        lines.append("# Evidence Bundle Quality Report")
        lines.append("")
        lines.append(
            f"**Grade:** {data.letter_grade}  "
            f"**Score:** {data.quality_score}/100  "
            f"**Verdict:** {data.verdict}"
        )
        lines.append("")

        lines.append("## Included evidence")
        lines.append("")
        for item in data.included:
            mark = "✅" if item.status == "present" else (
                "⚠️" if item.status == "partial" else "❌"
            )
            lines.append(
                f"- {mark} **{item.label}** ({item.quality}) — {item.details}"
            )
        lines.append("")

        lines.append("## Missing / external")
        lines.append("")
        if data.missing:
            for m in data.missing:
                lines.append(
                    f"- ❌ **{m.label}** [{m.severity}] — {m.why_it_matters}"
                )
        else:
            lines.append("- None")
        lines.append("")

        lines.append("## Warnings")
        lines.append("")
        if data.warnings:
            for w in data.warnings:
                lines.append(f"- {w}")
        else:
            lines.append("- None")
        lines.append("")

        lines.append("## Stage sufficiency")
        lines.append("")
        lines.append("| Stage | Status |")
        lines.append("| --- | --- |")
        for stage in _STAGES:
            lines.append(f"| {stage} | {data.stage_sufficiency.get(stage, 'fail')} |")
        lines.append("")

        lines.append("## Recommended fixes")
        lines.append("")
        if data.recommended_fixes:
            for fix in data.recommended_fixes:
                lines.append(f"- {fix}")
        else:
            lines.append("- None")
        lines.append("")

        lines.append("---")
        lines.append("")
        lines.append(f"_{data.disclaimer}_")
        return "\n".join(lines)

    # JSON output
    payload = {
        "quality_score": data.quality_score,
        "letter_grade": data.letter_grade,
        "verdict": data.verdict,
        "stage_sufficiency": data.stage_sufficiency,
        "sufficient_for": data.sufficient_for,
        "not_sufficient_for": data.not_sufficient_for,
        "included": [asdict(i) for i in data.included],
        "missing": [asdict(m) for m in data.missing],
        "warnings": data.warnings,
        "recommended_fixes": data.recommended_fixes,
        "generated_at": data.generated_at.isoformat(),
        "disclaimer": data.disclaimer,
    }
    return json.dumps(payload, indent=2)
