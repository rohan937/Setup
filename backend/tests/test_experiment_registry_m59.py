"""M59 tests: Experiment Registry.

Tests for:
  - POST /api/strategies/{id}/experiments         — create experiment
  - GET  /api/strategies/{id}/experiments         — list experiments
  - GET  /api/experiments/{id}                    — get experiment detail
  - POST /api/experiments/{id}/runs               — add run to experiment
  - DELETE /api/experiments/{id}/runs/{run_id}    — remove run from experiment
  - POST /api/experiments/{id}/analyze            — run analysis
  - GET  /api/experiments/{id}/analyses           — list analyses
  - GET  /api/experiment-analyses/{id}            — get analysis detail
  - AuditTimelineEvent creation
  - Forbidden language check in deterministic summaries

All tests use shared session-scoped fixtures from conftest.py.
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

    slug = f"m59-test-{suffix}-{uuid.uuid4().hex[:8]}"
    strat = Strategy(
        project_id=project_id,
        name=f"M59 Test Strategy {suffix}",
        slug=slug,
        asset_class="equity",
        status="active",
    )
    db.add(strat)
    db.commit()
    return strat


def _make_run(db, strategy_id, *, name: str = "run", metrics: dict | None = None) -> object:
    from app.models.strategy_run import StrategyRun

    run = StrategyRun(
        strategy_id=strategy_id,
        run_name=name,
        run_type="backtest",
        status="completed",
        metrics_json=metrics or {"sharpe": 1.4, "max_drawdown": -0.12, "turnover": 0.5},
    )
    db.add(run)
    db.flush()
    return run


def _create_experiment_via_api(client, strategy_id: str, *, name: str | None = None, suffix: str = "") -> dict:
    exp_name = name or f"Experiment {suffix} {uuid.uuid4().hex[:6]}"
    resp = client.post(
        f"/api/strategies/{strategy_id}/experiments",
        json={"name": exp_name},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# class TestExperimentCreation
# ---------------------------------------------------------------------------

class TestExperimentCreation:
    def test_create_experiment_success(self, db, client):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="create")
        strat_id = str(strat.id)

        resp = client.post(
            f"/api/strategies/{strat_id}/experiments",
            json={
                "name": "My First Experiment",
                "description": "Testing experiment creation",
                "experiment_type": "parameter_sweep",
                "hypothesis": "Higher lookback improves Sharpe ratio",
            },
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["name"] == "My First Experiment"
        assert data["strategy_id"] == strat_id
        assert data["status"] == "active"
        assert data["slug"] == "my-first-experiment"
        assert data["experiment_type"] == "parameter_sweep"
        assert "id" in data
        assert "created_at" in data

    def test_create_duplicate_slug_returns_409(self, db, client):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="dupslug")
        strat_id = str(strat.id)

        resp1 = client.post(
            f"/api/strategies/{strat_id}/experiments",
            json={"name": "Duplicate Name"},
        )
        assert resp1.status_code == 201, resp1.text

        resp2 = client.post(
            f"/api/strategies/{strat_id}/experiments",
            json={"name": "Duplicate Name"},
        )
        assert resp2.status_code == 409, resp2.text

    def test_list_experiments(self, db, client):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="list")
        strat_id = str(strat.id)

        client.post(f"/api/strategies/{strat_id}/experiments", json={"name": "Exp Alpha"})
        client.post(f"/api/strategies/{strat_id}/experiments", json={"name": "Exp Beta"})

        resp = client.get(f"/api/strategies/{strat_id}/experiments")
        assert resp.status_code == 200, resp.text
        items = resp.json()
        assert isinstance(items, list)
        names = [e["name"] for e in items]
        assert "Exp Alpha" in names
        assert "Exp Beta" in names

    def test_get_experiment_detail_with_runs(self, db, client):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="detail")
        strat_id = str(strat.id)

        exp_data = _create_experiment_via_api(client, strat_id, suffix="detail")
        exp_id = exp_data["id"]

        run = _make_run(db, strat.id, name="detail-run")
        db.commit()

        client.post(
            f"/api/experiments/{exp_id}/runs",
            json={"strategy_run_id": str(run.id), "variant_label": "v1"},
        )

        resp = client.get(f"/api/experiments/{exp_id}")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["id"] == exp_id
        assert "experiment_runs" in data
        assert len(data["experiment_runs"]) >= 1
        labels = [r["variant_label"] for r in data["experiment_runs"]]
        assert "v1" in labels

    def test_create_experiment_404_unknown_strategy(self, db, client):
        fake_id = str(uuid.uuid4())
        resp = client.post(
            f"/api/strategies/{fake_id}/experiments",
            json={"name": "Orphan Experiment"},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# class TestExperimentRunManagement
# ---------------------------------------------------------------------------

class TestExperimentRunManagement:
    def test_add_run_success(self, db, client):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="addrun")
        strat_id = str(strat.id)

        exp_data = _create_experiment_via_api(client, strat_id, suffix="addrun")
        exp_id = exp_data["id"]

        run = _make_run(db, strat.id, name="variant-a", metrics={"sharpe": 1.4, "max_drawdown": -0.12, "turnover": 0.5})
        db.commit()

        resp = client.post(
            f"/api/experiments/{exp_id}/runs",
            json={
                "strategy_run_id": str(run.id),
                "variant_label": "variant-a",
                "variant_key": "lookback_30",
            },
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["strategy_run_id"] == str(run.id)
        assert data["variant_label"] == "variant-a"
        assert data["experiment_id"] == exp_id

    def test_add_run_from_different_strategy_rejected(self, db, client):
        project = _get_seeded_project(db)
        strat_a = _make_strategy(db, project.id, suffix="diffA")
        strat_b = _make_strategy(db, project.id, suffix="diffB")

        exp_data = _create_experiment_via_api(client, str(strat_a.id), suffix="diffA")
        exp_id = exp_data["id"]

        run_b = _make_run(db, strat_b.id, name="other-strat-run")
        db.commit()

        resp = client.post(
            f"/api/experiments/{exp_id}/runs",
            json={"strategy_run_id": str(run_b.id)},
        )
        assert resp.status_code == 400, resp.text

    def test_add_duplicate_run_returns_409(self, db, client):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="duprun")
        strat_id = str(strat.id)

        exp_data = _create_experiment_via_api(client, strat_id, suffix="duprun")
        exp_id = exp_data["id"]

        run = _make_run(db, strat.id, name="dup-run")
        db.commit()

        client.post(f"/api/experiments/{exp_id}/runs", json={"strategy_run_id": str(run.id)})
        resp2 = client.post(f"/api/experiments/{exp_id}/runs", json={"strategy_run_id": str(run.id)})
        assert resp2.status_code == 409, resp2.text

    def test_remove_run_success(self, db, client):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="removerun")
        strat_id = str(strat.id)

        exp_data = _create_experiment_via_api(client, strat_id, suffix="removerun")
        exp_id = exp_data["id"]

        run = _make_run(db, strat.id, name="to-remove")
        db.commit()

        client.post(f"/api/experiments/{exp_id}/runs", json={"strategy_run_id": str(run.id)})

        resp = client.delete(f"/api/experiments/{exp_id}/runs/{run.id}")
        assert resp.status_code == 204, resp.text

        # Verify removed
        detail = client.get(f"/api/experiments/{exp_id}")
        assert detail.status_code == 200
        run_ids = [r["strategy_run_id"] for r in detail.json()["experiment_runs"]]
        assert str(run.id) not in run_ids

    def test_remove_nonexistent_run_returns_404(self, db, client):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="removenotfound")
        strat_id = str(strat.id)

        exp_data = _create_experiment_via_api(client, strat_id, suffix="removenotfound")
        exp_id = exp_data["id"]

        fake_run_id = str(uuid.uuid4())
        resp = client.delete(f"/api/experiments/{exp_id}/runs/{fake_run_id}")
        assert resp.status_code == 404, resp.text


# ---------------------------------------------------------------------------
# class TestExperimentAnalysis
# ---------------------------------------------------------------------------

class TestExperimentAnalysis:
    def test_analyze_insufficient_evidence_fewer_than_2_runs(self, db, client):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="insuff")
        strat_id = str(strat.id)

        exp_data = _create_experiment_via_api(client, strat_id, suffix="insuff")
        exp_id = exp_data["id"]

        # No runs added
        resp = client.post(f"/api/experiments/{exp_id}/analyze")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["overall_status"] == "insufficient_evidence"

    def test_analyze_with_2_runs_returns_variant_summaries(self, db, client):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="2runs")
        strat_id = str(strat.id)

        exp_data = _create_experiment_via_api(client, strat_id, suffix="2runs")
        exp_id = exp_data["id"]

        run_a = _make_run(db, strat.id, name="variant-a", metrics={"sharpe": 1.4, "max_drawdown": -0.12, "turnover": 0.5})
        run_b = _make_run(db, strat.id, name="variant-b", metrics={"sharpe": 0.9, "max_drawdown": -0.18, "turnover": 0.7})
        db.commit()

        client.post(f"/api/experiments/{exp_id}/runs", json={"strategy_run_id": str(run_a.id), "variant_label": "variant-a"})
        client.post(f"/api/experiments/{exp_id}/runs", json={"strategy_run_id": str(run_b.id), "variant_label": "variant-b"})

        resp = client.post(f"/api/experiments/{exp_id}/analyze")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["overall_status"] != "insufficient_evidence"
        assert data["variant_count"] == 2
        assert data["result_json"] is not None
        summaries = data["result_json"]["variant_summaries"]
        assert len(summaries) == 2

    def test_analysis_computes_evidence_scores(self, db, client):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="evscores")
        strat_id = str(strat.id)

        exp_data = _create_experiment_via_api(client, strat_id, suffix="evscores")
        exp_id = exp_data["id"]

        run_a = _make_run(db, strat.id, name="ev-a", metrics={"sharpe": 1.2})
        run_b = _make_run(db, strat.id, name="ev-b", metrics={"sharpe": 0.8})
        db.commit()

        client.post(f"/api/experiments/{exp_id}/runs", json={"strategy_run_id": str(run_a.id)})
        client.post(f"/api/experiments/{exp_id}/runs", json={"strategy_run_id": str(run_b.id)})

        resp = client.post(f"/api/experiments/{exp_id}/analyze")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        summaries = data["result_json"]["variant_summaries"]
        for s in summaries:
            assert "evidence_score" in s
            assert isinstance(s["evidence_score"], int)
            assert 0 <= s["evidence_score"] <= 100

    def test_analysis_computes_metric_comparison(self, db, client):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="metrics")
        strat_id = str(strat.id)

        exp_data = _create_experiment_via_api(client, strat_id, suffix="metrics")
        exp_id = exp_data["id"]

        run_a = _make_run(db, strat.id, name="met-a", metrics={"sharpe": 1.5, "max_drawdown": -0.10, "turnover": 0.4})
        run_b = _make_run(db, strat.id, name="met-b", metrics={"sharpe": 0.8, "max_drawdown": -0.20, "turnover": 0.8})
        db.commit()

        client.post(f"/api/experiments/{exp_id}/runs", json={"strategy_run_id": str(run_a.id)})
        client.post(f"/api/experiments/{exp_id}/runs", json={"strategy_run_id": str(run_b.id)})

        resp = client.post(f"/api/experiments/{exp_id}/analyze")
        assert resp.status_code == 200, resp.text
        mc = resp.json()["result_json"]["metric_comparison"]
        assert isinstance(mc, list)
        sharpe_row = next((r for r in mc if r["metric_key"] == "sharpe"), None)
        assert sharpe_row is not None
        assert sharpe_row["available_count"] == 2
        assert sharpe_row["min_value"] == pytest.approx(0.8, abs=1e-6)
        assert sharpe_row["max_value"] == pytest.approx(1.5, abs=1e-6)

    def test_analysis_best_evidenced_run_id_set(self, db, client):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="bestev")
        strat_id = str(strat.id)

        exp_data = _create_experiment_via_api(client, strat_id, suffix="bestev")
        exp_id = exp_data["id"]

        run_a = _make_run(db, strat.id, name="best-a", metrics={"sharpe": 1.3})
        run_b = _make_run(db, strat.id, name="best-b", metrics={"sharpe": 0.6})
        db.commit()

        client.post(f"/api/experiments/{exp_id}/runs", json={"strategy_run_id": str(run_a.id)})
        client.post(f"/api/experiments/{exp_id}/runs", json={"strategy_run_id": str(run_b.id)})

        resp = client.post(f"/api/experiments/{exp_id}/analyze")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["best_evidenced_run_id"] is not None

    def test_analysis_weakest_evidence_run_id_set(self, db, client):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="weakev")
        strat_id = str(strat.id)

        exp_data = _create_experiment_via_api(client, strat_id, suffix="weakev")
        exp_id = exp_data["id"]

        run_a = _make_run(db, strat.id, name="weak-a")
        run_b = _make_run(db, strat.id, name="weak-b")
        db.commit()

        client.post(f"/api/experiments/{exp_id}/runs", json={"strategy_run_id": str(run_a.id)})
        client.post(f"/api/experiments/{exp_id}/runs", json={"strategy_run_id": str(run_b.id)})

        resp = client.post(f"/api/experiments/{exp_id}/analyze")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["weakest_evidence_run_id"] is not None

    def test_analysis_persisted(self, db, client):
        from app.models.experiment import StrategyExperimentAnalysis

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="persist")
        strat_id = str(strat.id)

        exp_data = _create_experiment_via_api(client, strat_id, suffix="persist")
        exp_id = exp_data["id"]

        run_a = _make_run(db, strat.id, name="persist-a")
        run_b = _make_run(db, strat.id, name="persist-b")
        db.commit()

        client.post(f"/api/experiments/{exp_id}/runs", json={"strategy_run_id": str(run_a.id)})
        client.post(f"/api/experiments/{exp_id}/runs", json={"strategy_run_id": str(run_b.id)})

        resp = client.post(f"/api/experiments/{exp_id}/analyze")
        assert resp.status_code == 200, resp.text
        analysis_id = resp.json()["id"]

        row = db.query(StrategyExperimentAnalysis).filter_by(id=uuid.UUID(analysis_id)).first()
        assert row is not None
        assert row.overall_status is not None

    def test_list_analyses(self, db, client):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="listanalyses")
        strat_id = str(strat.id)

        exp_data = _create_experiment_via_api(client, strat_id, suffix="listanalyses")
        exp_id = exp_data["id"]

        run_a = _make_run(db, strat.id, name="listana-a")
        run_b = _make_run(db, strat.id, name="listana-b")
        db.commit()

        client.post(f"/api/experiments/{exp_id}/runs", json={"strategy_run_id": str(run_a.id)})
        client.post(f"/api/experiments/{exp_id}/runs", json={"strategy_run_id": str(run_b.id)})

        client.post(f"/api/experiments/{exp_id}/analyze")
        client.post(f"/api/experiments/{exp_id}/analyze")

        resp = client.get(f"/api/experiments/{exp_id}/analyses")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "items" in data
        assert data["total"] >= 2

    def test_get_analysis_detail(self, db, client):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="getanalysis")
        strat_id = str(strat.id)

        exp_data = _create_experiment_via_api(client, strat_id, suffix="getanalysis")
        exp_id = exp_data["id"]

        run_a = _make_run(db, strat.id, name="getana-a")
        run_b = _make_run(db, strat.id, name="getana-b")
        db.commit()

        client.post(f"/api/experiments/{exp_id}/runs", json={"strategy_run_id": str(run_a.id)})
        client.post(f"/api/experiments/{exp_id}/runs", json={"strategy_run_id": str(run_b.id)})

        analysis_resp = client.post(f"/api/experiments/{exp_id}/analyze")
        analysis_id = analysis_resp.json()["id"]

        resp = client.get(f"/api/experiment-analyses/{analysis_id}")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["id"] == analysis_id
        assert data["experiment_id"] == exp_id
        assert "deterministic_summary" in data


# ---------------------------------------------------------------------------
# class TestExperimentSummary
# ---------------------------------------------------------------------------

class TestExperimentSummary:
    def _setup_experiment_with_2_runs(self, db, client, suffix: str) -> tuple[str, str, str]:
        """Returns (strategy_id, experiment_id, run_a_id)."""
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix=suffix)
        strat_id = str(strat.id)

        exp_data = _create_experiment_via_api(client, strat_id, suffix=suffix)
        exp_id = exp_data["id"]

        run_a = _make_run(db, strat.id, name=f"{suffix}-run-a")
        run_b = _make_run(db, strat.id, name=f"{suffix}-run-b")
        db.commit()

        client.post(f"/api/experiments/{exp_id}/runs", json={"strategy_run_id": str(run_a.id)})
        client.post(f"/api/experiments/{exp_id}/runs", json={"strategy_run_id": str(run_b.id)})

        return strat_id, exp_id, str(run_a.id)

    def test_timeline_events_created_on_create(self, db, client):
        from app.models.audit_timeline_event import AuditTimelineEvent

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="tl-create")
        strat_id = str(strat.id)

        before_count = (
            db.query(AuditTimelineEvent)
            .filter(
                AuditTimelineEvent.strategy_id == strat.id,
                AuditTimelineEvent.event_type == "strategy_experiment_created",
            )
            .count()
        )

        _create_experiment_via_api(client, strat_id, suffix="tl-create")

        after_count = (
            db.query(AuditTimelineEvent)
            .filter(
                AuditTimelineEvent.strategy_id == strat.id,
                AuditTimelineEvent.event_type == "strategy_experiment_created",
            )
            .count()
        )
        assert after_count == before_count + 1

    def test_timeline_events_created_on_add_run(self, db, client):
        from app.models.audit_timeline_event import AuditTimelineEvent

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="tl-addrun")
        strat_id = str(strat.id)

        exp_data = _create_experiment_via_api(client, strat_id, suffix="tl-addrun")
        exp_id = exp_data["id"]

        run = _make_run(db, strat.id, name="tl-addrun-v1")
        db.commit()

        before_count = (
            db.query(AuditTimelineEvent)
            .filter(
                AuditTimelineEvent.strategy_id == strat.id,
                AuditTimelineEvent.event_type == "strategy_experiment_run_added",
            )
            .count()
        )

        client.post(f"/api/experiments/{exp_id}/runs", json={"strategy_run_id": str(run.id)})

        after_count = (
            db.query(AuditTimelineEvent)
            .filter(
                AuditTimelineEvent.strategy_id == strat.id,
                AuditTimelineEvent.event_type == "strategy_experiment_run_added",
            )
            .count()
        )
        assert after_count == before_count + 1

    def test_timeline_events_created_on_analyze(self, db, client):
        from app.models.audit_timeline_event import AuditTimelineEvent

        _, exp_id, _ = self._setup_experiment_with_2_runs(db, client, suffix="tl-analyze")

        # Resolve strategy_id from the experiment
        from app.models.experiment import StrategyExperiment
        exp = db.query(StrategyExperiment).filter_by(id=uuid.UUID(exp_id)).first()
        assert exp is not None

        before_count = (
            db.query(AuditTimelineEvent)
            .filter(
                AuditTimelineEvent.strategy_id == exp.strategy_id,
                AuditTimelineEvent.event_type == "strategy_experiment_analyzed",
            )
            .count()
        )

        client.post(f"/api/experiments/{exp_id}/analyze")

        after_count = (
            db.query(AuditTimelineEvent)
            .filter(
                AuditTimelineEvent.strategy_id == exp.strategy_id,
                AuditTimelineEvent.event_type == "strategy_experiment_analyzed",
            )
            .count()
        )
        assert after_count == before_count + 1

    def test_summary_avoids_forbidden_language(self, db, client):
        """deterministic_summary must not contain investment-advisory or AI language."""
        _, exp_id, _ = self._setup_experiment_with_2_runs(db, client, suffix="forbidden")

        resp = client.post(f"/api/experiments/{exp_id}/analyze")
        assert resp.status_code == 200, resp.text
        summary = resp.json().get("deterministic_summary") or ""

        import re as _re
        forbidden_patterns = [
            (r'\bwinner\b', "winner"),
            (r'\bbest strategy\b', "best strategy"),
            (r'\bmost profitable\b', "most profitable"),
            (r'\bbuy\b', "buy"),
            (r'\bsell\b', "sell"),
            (r'\bAI\b', "AI"),
        ]
        for pattern, label in forbidden_patterns:
            assert not _re.search(pattern, summary, _re.IGNORECASE), (
                f"Forbidden term {label!r} found in summary: {summary!r}"
            )
