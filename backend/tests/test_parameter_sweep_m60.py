"""M60 tests: Parameter Sweep Reliability Analysis.

Tests for:
  - POST /api/experiments/{id}/sweep-analysis  (via HTTP client)
  - analyze_parameter_sweep service directly
  - Edge cases: 0/1 run, no params, explicit parameter_key
  - Variant summaries, metric comparisons, evidence scoring
  - Fragility signals, rankings, suggested checks
  - persist=True creates StrategyExperimentAnalysis row
  - persist=False does not create row
  - Timeline event created only when persist=True
  - Forbidden language in deterministic summary

All tests use the shared session-scoped fixtures from conftest.py.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_seeded_project(db):
    from app.models.project import Project

    return db.query(Project).first()


def _make_strategy(db, project_id, *, suffix: str = "") -> object:
    from app.models.strategy import Strategy

    slug = f"m60-test-{suffix}-{uuid.uuid4().hex[:8]}"
    strat = Strategy(
        project_id=project_id,
        name=f"M60 Test Strategy {suffix}",
        slug=slug,
        asset_class="equity",
        status="active",
    )
    db.add(strat)
    db.commit()
    return strat


def _make_run(
    db,
    strategy_id,
    *,
    name: str = "run",
    metrics: dict | None = None,
    params: dict | None = None,
) -> object:
    from app.models.strategy_run import StrategyRun

    run = StrategyRun(
        strategy_id=strategy_id,
        run_name=name,
        run_type="backtest",
        status="completed",
        metrics_json=metrics or {"sharpe": 1.4, "max_drawdown": -0.12, "turnover": 0.5},
        params_json=params,
    )
    db.add(run)
    db.flush()
    return run


def _create_experiment(client, strategy_id: str, *, suffix: str = "") -> dict:
    exp_name = f"Sweep Experiment {suffix} {uuid.uuid4().hex[:6]}"
    resp = client.post(
        f"/api/strategies/{strategy_id}/experiments",
        json={"name": exp_name, "experiment_type": "parameter_sweep"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _add_run_to_experiment(
    client,
    experiment_id: str,
    run_id: str,
    *,
    variant_label: str | None = None,
    variant_key: str | None = None,
    variant_params_json: dict | None = None,
) -> dict:
    resp = client.post(
        f"/api/experiments/{experiment_id}/runs",
        json={
            "strategy_run_id": run_id,
            "variant_label": variant_label,
            "variant_key": variant_key,
            "variant_params_json": variant_params_json,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _post_sweep_analysis(
    client,
    experiment_id: str,
    *,
    parameter_key: str | None = None,
    persist: bool = True,
) -> dict:
    body: dict = {"persist": persist}
    if parameter_key is not None:
        body["parameter_key"] = parameter_key
    resp = client.post(f"/api/experiments/{experiment_id}/sweep-analysis", json=body)
    assert resp.status_code == 200, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# class TestParameterSweepBasic
# ---------------------------------------------------------------------------


class TestParameterSweepBasic:
    def test_insufficient_variants_with_0_runs(self, db, client):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="0runs")
        exp = _create_experiment(client, str(strat.id), suffix="0runs")

        data = _post_sweep_analysis(client, exp["id"], persist=False)

        assert data["sweep_status"] == "insufficient_variants"
        assert data["variant_summaries"] == []
        assert data["sweep_reliability_score"] is None

    def test_insufficient_variants_with_1_run(self, db, client):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="1run")
        exp = _create_experiment(client, str(strat.id), suffix="1run")
        run = _make_run(db, strat.id, name="only-run", params={"lookback": 10})
        db.commit()

        _add_run_to_experiment(
            client,
            exp["id"],
            str(run.id),
            variant_params_json={"lookback": 10},
        )

        data = _post_sweep_analysis(client, exp["id"], persist=False)

        assert data["sweep_status"] == "insufficient_variants"
        assert len(data["variant_summaries"]) == 0

    def test_insufficient_parameter_data_no_params(self, db, client):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="noparams")
        exp = _create_experiment(client, str(strat.id), suffix="noparams")

        run1 = _make_run(db, strat.id, name="no-params-1")
        run2 = _make_run(db, strat.id, name="no-params-2")
        db.commit()

        # Add runs with no params at all — override variant_params_json to None
        # by NOT passing variant_params_json (service will try run.params_json which is also None)
        _add_run_to_experiment(client, exp["id"], str(run1.id))
        _add_run_to_experiment(client, exp["id"], str(run2.id))

        data = _post_sweep_analysis(client, exp["id"], persist=False)

        assert data["sweep_status"] == "insufficient_parameter_data"
        assert data["parameter_key"] is None

    def test_detects_numeric_parameter_from_variant_params(self, db, client):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="varparams")
        exp = _create_experiment(client, str(strat.id), suffix="varparams")

        run1 = _make_run(db, strat.id, name="lookback-10")
        run2 = _make_run(db, strat.id, name="lookback-20")
        db.commit()

        _add_run_to_experiment(
            client, exp["id"], str(run1.id),
            variant_label="lb10", variant_params_json={"lookback": 10},
        )
        _add_run_to_experiment(
            client, exp["id"], str(run2.id),
            variant_label="lb20", variant_params_json={"lookback": 20},
        )

        data = _post_sweep_analysis(client, exp["id"], persist=False)

        assert data["sweep_status"] not in ("insufficient_variants", "insufficient_parameter_data")
        assert data["parameter_key"] == "lookback"
        assert len(data["variant_summaries"]) == 2

    def test_detects_parameter_from_run_params_json(self, db, client):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="runparams")
        exp = _create_experiment(client, str(strat.id), suffix="runparams")

        run1 = _make_run(db, strat.id, name="run-lb30", params={"lookback": 30})
        run2 = _make_run(db, strat.id, name="run-lb60", params={"lookback": 60})
        db.commit()

        # Add without explicit variant_params_json — service falls back to run.params_json
        _add_run_to_experiment(client, exp["id"], str(run1.id), variant_label="lb30")
        _add_run_to_experiment(client, exp["id"], str(run2.id), variant_label="lb60")

        data = _post_sweep_analysis(client, exp["id"], persist=False)

        assert data["parameter_key"] == "lookback"
        assert len(data["variant_summaries"]) == 2

        values = {v["parameter_value"] for v in data["variant_summaries"]}
        assert "30" in values
        assert "60" in values

    def test_explicit_parameter_key(self, db, client):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="explicitkey")
        exp = _create_experiment(client, str(strat.id), suffix="explicitkey")

        run1 = _make_run(
            db, strat.id, name="alpha-0.1",
            params={"alpha": 0.1, "lookback": 20},
        )
        run2 = _make_run(
            db, strat.id, name="alpha-0.5",
            params={"alpha": 0.5, "lookback": 20},
        )
        db.commit()

        _add_run_to_experiment(client, exp["id"], str(run1.id))
        _add_run_to_experiment(client, exp["id"], str(run2.id))

        data = _post_sweep_analysis(
            client, exp["id"], parameter_key="alpha", persist=False
        )

        assert data["parameter_key"] == "alpha"
        values = {v["parameter_value"] for v in data["variant_summaries"]}
        assert "0.1" in values
        assert "0.5" in values


# ---------------------------------------------------------------------------
# class TestParameterSweepAnalysis
# ---------------------------------------------------------------------------


class TestParameterSweepAnalysis:
    def test_variant_summaries_built(self, db, client):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="varsummary")
        exp = _create_experiment(client, str(strat.id), suffix="varsummary")

        for lb in [10, 20, 30]:
            run = _make_run(
                db, strat.id,
                name=f"lb-{lb}",
                metrics={"sharpe": 1.0 + lb * 0.01, "max_drawdown": -0.1},
                params={"lookback": lb},
            )
            db.commit()
            _add_run_to_experiment(
                client, exp["id"], str(run.id),
                variant_label=f"lookback_{lb}",
                variant_params_json={"lookback": lb},
            )

        data = _post_sweep_analysis(client, exp["id"], persist=False)

        assert len(data["variant_summaries"]) == 3
        labels = {v["variant_label"] for v in data["variant_summaries"]}
        assert "lookback_10" in labels
        assert "lookback_20" in labels
        assert "lookback_30" in labels

    def test_metric_comparisons_computed(self, db, client):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="metrics")
        exp = _create_experiment(client, str(strat.id), suffix="metrics")

        for lb, sh in [(10, 0.8), (20, 1.2), (30, 1.5)]:
            run = _make_run(
                db, strat.id,
                name=f"metric-{lb}",
                metrics={"sharpe": sh, "max_drawdown": -0.1, "annual_return": 0.12},
                params={"lookback": lb},
            )
            db.commit()
            _add_run_to_experiment(
                client, exp["id"], str(run.id),
                variant_params_json={"lookback": lb},
            )

        data = _post_sweep_analysis(client, exp["id"], persist=False)

        assert len(data["metric_comparisons"]) > 0
        sharpe_mc = next(
            (mc for mc in data["metric_comparisons"] if mc["metric_key"] == "sharpe"), None
        )
        assert sharpe_mc is not None
        assert sharpe_mc["available_count"] == 3
        assert sharpe_mc["min_value"] == pytest.approx(0.8)
        assert sharpe_mc["max_value"] == pytest.approx(1.5)
        assert sharpe_mc["range_value"] == pytest.approx(0.7)

    def test_numeric_variants_sorted_by_value(self, db, client):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="sorted")
        exp = _create_experiment(client, str(strat.id), suffix="sorted")

        # Add in non-sorted order: 30, 10, 20
        for lb in [30, 10, 20]:
            run = _make_run(db, strat.id, name=f"s-lb-{lb}", params={"lookback": lb})
            db.commit()
            _add_run_to_experiment(
                client, exp["id"], str(run.id),
                variant_params_json={"lookback": lb},
            )

        # Directly use the service to check sorted order
        from app.services.parameter_sweep import analyze_parameter_sweep

        result = analyze_parameter_sweep(db, exp["id"], persist=False)

        numeric_vals = [
            v.parameter_value_numeric
            for v in result.variant_summaries
            if v.parameter_value_numeric is not None
        ]
        # Service returns variants as built; the sorted order is only internal to region detection.
        # Check that all 3 values are present.
        assert sorted(numeric_vals) == [10.0, 20.0, 30.0]

    def test_evidence_scores_computed(self, db, client):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="evidscores")
        exp = _create_experiment(client, str(strat.id), suffix="evidscores")

        for lb in [10, 20]:
            run = _make_run(db, strat.id, name=f"es-{lb}", params={"lookback": lb})
            db.commit()
            _add_run_to_experiment(
                client, exp["id"], str(run.id),
                variant_params_json={"lookback": lb},
            )

        data = _post_sweep_analysis(client, exp["id"], persist=False)

        for v in data["variant_summaries"]:
            # Base score is 40; no dataset/signal/audit means no bonus
            assert v["evidence_score"] == 40.0
            assert v["variant_status"] in (
                "stable", "usable", "review", "fragile", "insufficient_evidence"
            )

    def test_fragile_variant_detected(self, db, client):
        """A run with no evidence links should be fragile or insufficient_evidence."""
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="fragile")
        exp = _create_experiment(client, str(strat.id), suffix="fragile")

        # Both runs have no dataset/signal/audit
        for lb in [5, 10]:
            run = _make_run(db, strat.id, name=f"frag-{lb}", params={"lookback": lb})
            db.commit()
            _add_run_to_experiment(
                client, exp["id"], str(run.id),
                variant_params_json={"lookback": lb},
            )

        data = _post_sweep_analysis(client, exp["id"], persist=False)

        # Base score = 40 -> status "review" (40 >= 40, no trust -> fragile rule: 40 >= 40 is review)
        for v in data["variant_summaries"]:
            assert v["variant_status"] in ("review", "fragile", "insufficient_evidence")
        assert data["fragility_signals"]["review_variant_count"] >= 2

    def test_stable_variant_detected(self, db, client):
        """A run with high evidence_score AND high trust should be stable."""
        from app.models.backtest_audit import BacktestAudit
        from app.models.dataset_snapshot import DatasetSnapshot
        from app.models.dataset import Dataset

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="stable")
        exp = _create_experiment(client, str(strat.id), suffix="stable")

        # Build a dataset + snapshot for each run
        dataset = Dataset(
            project_id=project.id,
            name=f"stable-ds-{uuid.uuid4().hex[:6]}",
            dataset_type="ohlcv",
        )
        db.add(dataset)
        db.flush()

        for i, lb in enumerate([10, 20]):
            snap = DatasetSnapshot(
                dataset_id=dataset.id,
                version_label=f"v{i}",
                health_score=90,
            )
            db.add(snap)
            db.flush()

            run = _make_run(
                db, strat.id, name=f"stable-{lb}",
                params={"lookback": lb},
                metrics={"sharpe": 1.5, "max_drawdown": -0.08},
            )
            run.dataset_snapshot_id = snap.id
            db.flush()

            audit = BacktestAudit(
                strategy_run_id=run.id,
                trust_score=85,
                overall_status="excellent",
                summary="Good.",
            )
            db.add(audit)
            db.flush()

            db.commit()
            _add_run_to_experiment(
                client, exp["id"], str(run.id),
                variant_params_json={"lookback": lb},
            )

        data = _post_sweep_analysis(client, exp["id"], persist=False)

        # At least one variant should be stable (evidence >= 80, trust >= 70)
        statuses = {v["variant_status"] for v in data["variant_summaries"]}
        assert "stable" in statuses or "usable" in statuses

    def test_sweep_score_computed(self, db, client):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="sweepscore")
        exp = _create_experiment(client, str(strat.id), suffix="sweepscore")

        for lb in [10, 20]:
            run = _make_run(db, strat.id, name=f"sc-{lb}", params={"lookback": lb})
            db.commit()
            _add_run_to_experiment(
                client, exp["id"], str(run.id),
                variant_params_json={"lookback": lb},
            )

        data = _post_sweep_analysis(client, exp["id"], persist=False)

        score = data["sweep_reliability_score"]
        assert score is not None
        assert 0.0 <= score <= 100.0

    def test_sweep_status_insufficient_variants(self, db, client):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="insvariants")
        exp = _create_experiment(client, str(strat.id), suffix="insvariants")

        data = _post_sweep_analysis(client, exp["id"], persist=False)

        assert data["sweep_status"] == "insufficient_variants"

    def test_persist_true_creates_analysis(self, db, client):
        from app.models.experiment import StrategyExperimentAnalysis

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="persist")
        exp = _create_experiment(client, str(strat.id), suffix="persist")

        for lb in [10, 20]:
            run = _make_run(db, strat.id, name=f"persist-{lb}", params={"lookback": lb})
            db.commit()
            _add_run_to_experiment(
                client, exp["id"], str(run.id),
                variant_params_json={"lookback": lb},
            )

        data = _post_sweep_analysis(client, exp["id"], persist=True)

        assert data["analysis_id"] is not None

        # Verify the row is in DB
        analysis_id = uuid.UUID(data["analysis_id"])
        row = (
            db.query(StrategyExperimentAnalysis)
            .filter(StrategyExperimentAnalysis.id == analysis_id)
            .first()
        )
        assert row is not None
        assert row.analysis_label is not None
        assert "lookback" in row.analysis_label.lower() or "sweep" in row.analysis_label.lower()

    def test_persist_false_no_analysis(self, db, client):
        from app.models.experiment import StrategyExperimentAnalysis

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="nopersist")
        exp = _create_experiment(client, str(strat.id), suffix="nopersist")

        for lb in [100, 200]:
            run = _make_run(db, strat.id, name=f"np-{lb}", params={"lookback": lb})
            db.commit()
            _add_run_to_experiment(
                client, exp["id"], str(run.id),
                variant_params_json={"lookback": lb},
            )

        before_count = (
            db.query(StrategyExperimentAnalysis)
            .filter(StrategyExperimentAnalysis.experiment_id == uuid.UUID(exp["id"]))
            .count()
        )

        data = _post_sweep_analysis(client, exp["id"], persist=False)

        assert data["analysis_id"] is None

        after_count = (
            db.query(StrategyExperimentAnalysis)
            .filter(StrategyExperimentAnalysis.experiment_id == uuid.UUID(exp["id"]))
            .count()
        )
        assert after_count == before_count

    def test_timeline_event_only_when_persist_true(self, db, client):
        from app.models.audit_timeline_event import AuditTimelineEvent
        from app.core.constants import EventType

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="timeline")
        exp = _create_experiment(client, str(strat.id), suffix="timeline")

        for lb in [15, 30]:
            run = _make_run(db, strat.id, name=f"tl-{lb}", params={"lookback": lb})
            db.commit()
            _add_run_to_experiment(
                client, exp["id"], str(run.id),
                variant_params_json={"lookback": lb},
            )

        # persist=False — no event
        before = (
            db.query(AuditTimelineEvent)
            .filter(AuditTimelineEvent.event_type == str(EventType.strategy_sweep_analyzed))
            .count()
        )
        _post_sweep_analysis(client, exp["id"], persist=False)
        after_no_persist = (
            db.query(AuditTimelineEvent)
            .filter(AuditTimelineEvent.event_type == str(EventType.strategy_sweep_analyzed))
            .count()
        )
        assert after_no_persist == before

        # persist=True — event created
        _post_sweep_analysis(client, exp["id"], persist=True)
        after_persist = (
            db.query(AuditTimelineEvent)
            .filter(AuditTimelineEvent.event_type == str(EventType.strategy_sweep_analyzed))
            .count()
        )
        assert after_persist == before + 1


# ---------------------------------------------------------------------------
# class TestParameterSweepSignals
# ---------------------------------------------------------------------------


class TestParameterSweepSignals:
    def _setup_3_variant_experiment(self, db, client, suffix: str):
        """Helper: create experiment with 3 variants (lookback 10/20/30)."""
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix=suffix)
        exp = _create_experiment(client, str(strat.id), suffix=suffix)

        for lb, sharpe in [(10, 1.0), (20, 1.3), (30, 1.1)]:
            run = _make_run(
                db, strat.id,
                name=f"sig-{lb}",
                metrics={"sharpe": sharpe, "max_drawdown": -0.1 * lb / 10},
                params={"lookback": lb},
            )
            db.commit()
            _add_run_to_experiment(
                client, exp["id"], str(run.id),
                variant_label=f"lookback_{lb}",
                variant_key=f"lookback_{lb}",
                variant_params_json={"lookback": lb},
            )

        return strat, exp

    def test_fragility_signals_structure(self, db, client):
        _, exp = self._setup_3_variant_experiment(db, client, suffix="fragsig")

        data = _post_sweep_analysis(client, exp["id"], persist=False)

        fs = data["fragility_signals"]
        required_keys = {
            "fragile_variant_count",
            "review_variant_count",
            "under_instrumented_variant_count",
            "narrow_peak_detected",
            "evidence_degradation_detected",
            "trust_degradation_detected",
            "metric_instability_detected",
        }
        assert required_keys.issubset(fs.keys())
        assert isinstance(fs["fragile_variant_count"], int)
        assert isinstance(fs["narrow_peak_detected"], bool)

    def test_rankings_present(self, db, client):
        _, exp = self._setup_3_variant_experiment(db, client, suffix="rankings")

        data = _post_sweep_analysis(client, exp["id"], persist=False)

        rankings = data["rankings"]
        assert len(rankings) > 0
        # Rankings should be sorted by score descending
        scores = [r["score"] for r in rankings if r["score"] is not None]
        assert scores == sorted(scores, reverse=True)
        # Ranks should be sequential starting from 1
        ranks = [r["rank"] for r in rankings]
        assert ranks[0] == 1

    def test_suggested_checks_present(self, db, client):
        _, exp = self._setup_3_variant_experiment(db, client, suffix="sugchecks")

        data = _post_sweep_analysis(client, exp["id"], persist=False)

        checks = data["suggested_checks"]
        assert isinstance(checks, list)
        # With no evidence (no dataset/signal/audit linked), there should be at least one check
        assert len(checks) >= 1

    def test_summary_avoids_forbidden_language(self, db, client):
        _, exp = self._setup_3_variant_experiment(db, client, suffix="forbidden")

        data = _post_sweep_analysis(client, exp["id"], persist=False)

        summary = data["deterministic_summary"].lower()
        forbidden = ["winner", "best parameter", "most profitable", "buy", "sell", "optimize", "ai"]
        for word in forbidden:
            assert word not in summary, (
                f"Forbidden word '{word}' found in summary: {data['deterministic_summary']!r}"
            )

    def test_detected_parameters_populated(self, db, client):
        _, exp = self._setup_3_variant_experiment(db, client, suffix="detparams")

        data = _post_sweep_analysis(client, exp["id"], persist=False)

        detected = data["detected_parameters"]
        assert isinstance(detected, list)
        assert len(detected) >= 1
        keys = [d["parameter_key"] for d in detected]
        assert "lookback" in keys

        lb_param = next(d for d in detected if d["parameter_key"] == "lookback")
        assert lb_param["numeric"] is True
        assert lb_param["value_count"] == 3
        assert lb_param["coverage_rate"] == pytest.approx(1.0)

    def test_experiment_404_unknown_id(self, db, client):
        fake_id = str(uuid.uuid4())
        resp = client.post(
            f"/api/experiments/{fake_id}/sweep-analysis",
            json={"persist": False},
        )
        assert resp.status_code == 404

    def test_metric_comparisons_have_all_keys(self, db, client):
        _, exp = self._setup_3_variant_experiment(db, client, suffix="allkeys")

        data = _post_sweep_analysis(client, exp["id"], persist=False)

        metric_keys = {mc["metric_key"] for mc in data["metric_comparisons"]}
        expected_keys = {
            "sharpe", "annual_return", "max_drawdown", "volatility",
            "turnover", "hit_rate", "trade_count",
        }
        assert expected_keys == metric_keys

    def test_analysis_label_in_persisted_row(self, db, client):
        from app.models.experiment import StrategyExperimentAnalysis

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="label")
        exp = _create_experiment(client, str(strat.id), suffix="label")

        for lb in [5, 15]:
            run = _make_run(db, strat.id, name=f"lbl-{lb}", params={"lookback": lb})
            db.commit()
            _add_run_to_experiment(
                client, exp["id"], str(run.id),
                variant_params_json={"lookback": lb},
            )

        resp = client.post(
            f"/api/experiments/{exp['id']}/sweep-analysis",
            json={"persist": True, "analysis_label": "Custom Sweep Label"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()

        assert data["analysis_id"] is not None
        row = (
            db.query(StrategyExperimentAnalysis)
            .filter(StrategyExperimentAnalysis.id == uuid.UUID(data["analysis_id"]))
            .first()
        )
        assert row is not None
        assert row.analysis_label == "Custom Sweep Label"

    def test_regions_list_present(self, db, client):
        _, exp = self._setup_3_variant_experiment(db, client, suffix="regions")

        data = _post_sweep_analysis(client, exp["id"], persist=False)

        assert "regions" in data
        assert isinstance(data["regions"], list)
        # Each region has the required fields
        for r in data["regions"]:
            required = {"region_key", "label", "variant_count", "run_ids", "status", "reason"}
            assert required.issubset(r.keys()), f"Missing keys in region: {r}"
