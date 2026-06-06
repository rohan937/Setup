"""M97 tests: Evidence Bundle Quality Grader.

Tests for:
  - TestGradeBundleService: grade_evidence_bundle direct calls
  - TestStageSufficiency: stage_sufficiency / sufficient_for projection
  - TestGradeReport: generate_bundle_quality_report (json + markdown)
  - TestGradeEndpoints: POST /api/evidence-bundles/grade[/report] integration

The grader is PURELY STRUCTURAL and READ-ONLY: it inspects a parsed bundle dict
and never touches the database. Endpoint tests use the shared conftest fixtures.
"""
from __future__ import annotations

import copy
import json


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _complete_bundle() -> dict:
    """A fully-populated, high-quality evidence bundle."""
    return {
        "strategy_version": {"version_label": "v1.0", "signal_name": "trend"},
        "config_snapshot": {
            "label": "cfg",
            "config_json": {
                "params": {"lookback": 20},
                "assumptions": {
                    "transaction_cost_bps": 5,
                    "slippage_bps": 2,
                    "fill_model": "next_open",
                },
            },
        },
        "universe_snapshot": {"label": "uni", "symbols": ["SPY", "QQQ"]},
        "signal_snapshot": {
            "label": "sig",
            "signal_name": "trend",
            "signal_column": "signal",
            "rows": [
                {"symbol": "SPY", "date": "2023-01-03", "signal": 1.0},
                {"symbol": "QQQ", "date": "2023-01-03", "signal": 0.0},
            ],
        },
        "dataset": {"name": "SPY OHLCV"},
        "dataset_snapshot": {
            "snapshot_label": "snap",
            "rows": [
                {"symbol": "SPY", "date": "2023-01-03", "close": 386.0},
                {"symbol": "QQQ", "date": "2023-01-03", "close": 270.0},
            ],
        },
        "strategy_run": {
            "run_name": "bt1",
            "run_type": "backtest",
            "metrics_json": {
                "sharpe": 1.2,
                "annual_return": 0.12,
                "volatility": 0.14,
                "max_drawdown": -0.1,
                "turnover": 0.4,
                "trade_count": 30,
            },
        },
    }


# ---------------------------------------------------------------------------
# TestGradeBundleService
# ---------------------------------------------------------------------------


class TestGradeBundleService:
    """Direct calls to grade_evidence_bundle."""

    def test_complete_bundle_high_grade(self):
        from app.services.evidence_bundle_grader import grade_evidence_bundle

        data = grade_evidence_bundle(_complete_bundle())
        assert data.quality_score >= 80, (
            f"Expected complete bundle score >= 80, got {data.quality_score}"
        )
        assert data.letter_grade in ("A", "A-", "B+", "B"), (
            f"Expected high letter grade, got {data.letter_grade!r}"
        )

    def test_empty_bundle_invalid(self):
        from app.services.evidence_bundle_grader import grade_evidence_bundle

        data = grade_evidence_bundle({})
        assert data.verdict == "invalid", (
            f"Expected empty bundle verdict 'invalid', got {data.verdict!r}"
        )

    def test_missing_config_lowers_score(self):
        from app.services.evidence_bundle_grader import grade_evidence_bundle

        full = grade_evidence_bundle(_complete_bundle()).quality_score
        bundle = _complete_bundle()
        del bundle["config_snapshot"]
        reduced = grade_evidence_bundle(bundle).quality_score
        assert reduced < full, (
            f"Removing config_snapshot should lower score: {reduced} < {full}"
        )

    def test_missing_dataset_lowers_score(self):
        from app.services.evidence_bundle_grader import grade_evidence_bundle

        full = grade_evidence_bundle(_complete_bundle()).quality_score
        bundle = _complete_bundle()
        del bundle["dataset"]
        del bundle["dataset_snapshot"]
        reduced = grade_evidence_bundle(bundle).quality_score
        assert reduced < full, (
            f"Removing dataset evidence should lower score: {reduced} < {full}"
        )

    def test_missing_signal_lowers_score(self):
        from app.services.evidence_bundle_grader import grade_evidence_bundle

        full = grade_evidence_bundle(_complete_bundle()).quality_score
        bundle = _complete_bundle()
        del bundle["signal_snapshot"]
        reduced = grade_evidence_bundle(bundle).quality_score
        assert reduced < full, (
            f"Removing signal_snapshot should lower score: {reduced} < {full}"
        )

    def test_missing_run_lowers_score(self):
        from app.services.evidence_bundle_grader import grade_evidence_bundle

        full = grade_evidence_bundle(_complete_bundle()).quality_score
        bundle = _complete_bundle()
        del bundle["strategy_run"]
        data = grade_evidence_bundle(bundle)
        assert data.quality_score < full, (
            f"Removing strategy_run should lower score: {data.quality_score} < {full}"
        )
        missing_keys = {m.key for m in data.missing}
        assert "strategy_run" in missing_keys, (
            f"Expected strategy_run in missing keys, got {missing_keys}"
        )

    def test_missing_costs_warning(self):
        from app.services.evidence_bundle_grader import grade_evidence_bundle

        bundle = _complete_bundle()
        # Assumptions present but without transaction_cost_bps/cost_bps.
        bundle["config_snapshot"]["config_json"]["assumptions"] = {
            "fill_model": "next_open"
        }
        data = grade_evidence_bundle(bundle)
        assert any("cost" in w.lower() for w in data.warnings), (
            f"Expected a cost warning, got warnings: {data.warnings}"
        )

    def test_symbol_mismatch_warning(self):
        from app.services.evidence_bundle_grader import grade_evidence_bundle

        bundle = _complete_bundle()
        bundle["signal_snapshot"]["rows"] = [
            {"symbol": "AAA", "date": "2023-01-03", "signal": 1.0}
        ]
        bundle["universe_snapshot"]["symbols"] = ["SPY"]
        data = grade_evidence_bundle(bundle)
        assert any(
            "overlap" in w.lower() or "symbol" in w.lower() for w in data.warnings
        ), (
            f"Expected a symbol/overlap warning, got warnings: {data.warnings}"
        )

    def test_paper_run_detected(self):
        from app.services.evidence_bundle_grader import grade_evidence_bundle

        bundle = _complete_bundle()
        bundle["strategy_run"]["run_type"] = "paper"
        data = grade_evidence_bundle(bundle)
        assert data.stage_sufficiency["shadow"] in ("pass", "warning"), (
            "Paper run should make shadow stage better than fail, got "
            f"{data.stage_sufficiency['shadow']!r}"
        )

    def test_letter_grade_boundaries(self):
        from app.services.evidence_bundle_grader import grade_evidence_bundle

        near_perfect = grade_evidence_bundle(_complete_bundle())
        assert near_perfect.letter_grade in ("A", "A-"), (
            f"Expected near-perfect bundle to grade A/A-, got {near_perfect.letter_grade!r}"
        )
        sparse = grade_evidence_bundle({"strategy_version": {"version_label": "v0"}})
        assert sparse.letter_grade in ("C", "D", "F"), (
            f"Expected sparse bundle to grade C/D/F, got {sparse.letter_grade!r}"
        )

    def test_disclaimer_present(self):
        from app.services.evidence_bundle_grader import grade_evidence_bundle

        data = grade_evidence_bundle(_complete_bundle())
        assert "not trading advice" in data.disclaimer.lower(), (
            f"Expected 'not trading advice' in disclaimer, got: {data.disclaimer!r}"
        )

    def test_included_lists_all_sections(self):
        from app.services.evidence_bundle_grader import grade_evidence_bundle

        data = grade_evidence_bundle(_complete_bundle())
        included_keys = {i.key for i in data.included}
        for key in (
            "strategy_version",
            "config_snapshot",
            "universe_snapshot",
            "signal_snapshot",
            "dataset_snapshot",
            "strategy_run",
        ):
            assert key in included_keys, (
                f"Expected {key} in included keys, got {included_keys}"
            )


# ---------------------------------------------------------------------------
# TestStageSufficiency
# ---------------------------------------------------------------------------


class TestStageSufficiency:
    """stage_sufficiency / sufficient_for projection."""

    def test_research_pass_with_version(self):
        from app.services.evidence_bundle_grader import grade_evidence_bundle

        data = grade_evidence_bundle(
            {"strategy_version": {"version_label": "v1.0", "signal_name": "trend"}}
        )
        assert data.stage_sufficiency["research"] == "pass", (
            f"Expected research=pass with a version, got {data.stage_sufficiency['research']!r}"
        )

    def test_backtest_review_pass_with_complete(self):
        from app.services.evidence_bundle_grader import grade_evidence_bundle

        data = grade_evidence_bundle(_complete_bundle())
        assert data.stage_sufficiency["backtest_review"] == "pass", (
            "Expected backtest_review=pass for complete bundle, got "
            f"{data.stage_sufficiency['backtest_review']!r}"
        )

    def test_shadow_fail_without_paper(self):
        from app.services.evidence_bundle_grader import grade_evidence_bundle

        data = grade_evidence_bundle(_complete_bundle())
        assert data.stage_sufficiency["shadow"] in ("fail", "warning"), (
            "Expected shadow in (fail, warning) for backtest-only bundle, got "
            f"{data.stage_sufficiency['shadow']!r}"
        )

    def test_sufficient_for_includes_backtest_review(self):
        from app.services.evidence_bundle_grader import grade_evidence_bundle

        data = grade_evidence_bundle(_complete_bundle())
        assert "backtest_review" in data.sufficient_for, (
            f"Expected backtest_review in sufficient_for, got {data.sufficient_for}"
        )


# ---------------------------------------------------------------------------
# TestGradeReport
# ---------------------------------------------------------------------------


class TestGradeReport:
    """generate_bundle_quality_report."""

    def test_json_report_parseable(self):
        from app.services.evidence_bundle_grader import generate_bundle_quality_report

        content = generate_bundle_quality_report(_complete_bundle(), format="json")
        parsed = json.loads(content)
        assert "quality_score" in parsed and "letter_grade" in parsed, (
            f"Expected parseable JSON with grade fields, got keys: {list(parsed.keys())}"
        )

    def test_markdown_report_has_header(self):
        from app.services.evidence_bundle_grader import generate_bundle_quality_report

        content = generate_bundle_quality_report(_complete_bundle(), format="markdown")
        assert "# Evidence Bundle Quality Report" in content, (
            "Expected markdown header in report"
        )


# ---------------------------------------------------------------------------
# TestGradeEndpoints
# ---------------------------------------------------------------------------


class TestGradeEndpoints:
    """Integration tests via TestClient for the M97 grade endpoints."""

    def test_grade_endpoint_200(self, client):
        resp = client.post(
            "/api/evidence-bundles/grade", json=_complete_bundle()
        )
        assert resp.status_code == 200, (
            f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        )
        data = resp.json()
        assert "letter_grade" in data, (
            f"Expected letter_grade in response, got keys: {list(data.keys())}"
        )

    def test_grade_empty_bundle_200(self, client):
        resp = client.post("/api/evidence-bundles/grade", json={})
        assert resp.status_code == 200, (
            f"Expected 200 for empty bundle, got {resp.status_code}: {resp.text[:200]}"
        )
        data = resp.json()
        assert data["verdict"] == "invalid", (
            f"Expected verdict 'invalid' for empty bundle, got {data['verdict']!r}"
        )

    def test_grade_report_json_200(self, client):
        resp = client.post(
            "/api/evidence-bundles/grade/report?format=json",
            json=_complete_bundle(),
        )
        assert resp.status_code == 200, (
            f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        )

    def test_grade_report_markdown_200(self, client):
        resp = client.post(
            "/api/evidence-bundles/grade/report?format=markdown",
            json=_complete_bundle(),
        )
        assert resp.status_code == 200, (
            f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        )
        assert "Evidence Bundle Quality Report" in resp.text, (
            "Expected markdown body in response"
        )

    def test_grade_report_invalid_format_400(self, client):
        resp = client.post(
            "/api/evidence-bundles/grade/report?format=xml",
            json=_complete_bundle(),
        )
        assert resp.status_code == 400, (
            f"Expected 400 for invalid format, got {resp.status_code}: {resp.text[:200]}"
        )

    def test_grade_does_not_mutate_db(self, client, db):
        from app.models.strategy import Strategy
        from app.models.strategy_run import StrategyRun
        from app.models.dataset_snapshot import DatasetSnapshot

        before_strategies = db.query(Strategy).count()
        before_runs = db.query(StrategyRun).count()
        before_snaps = db.query(DatasetSnapshot).count()

        resp = client.post(
            "/api/evidence-bundles/grade", json=_complete_bundle()
        )
        assert resp.status_code == 200

        after_strategies = db.query(Strategy).count()
        after_runs = db.query(StrategyRun).count()
        after_snaps = db.query(DatasetSnapshot).count()

        assert before_strategies == after_strategies, "grade must not create Strategy rows"
        assert before_runs == after_runs, "grade must not create StrategyRun rows"
        assert before_snaps == after_snaps, "grade must not create DatasetSnapshot rows"
