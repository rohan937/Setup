"""M58 tests: Run Replay Pack endpoint.

Tests for:
  - GET /api/strategies/{id}/runs/{run_id}/replay-pack
  - JSON and markdown format support
  - Section presence and evidence linking
  - Completeness scoring
  - No AuditTimelineEvent side effects (read-only)
  - Forbidden language constraints
  - Input validation (404, 400)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from app.models.audit_timeline_event import AuditTimelineEvent
from app.models.backtest_audit import BacktestAudit
from app.models.dataset import Dataset
from app.models.dataset_snapshot import DatasetSnapshot
from app.models.organization import Organization
from app.models.project import Project
from app.models.signal_snapshot import SignalSnapshot
from app.models.strategy import Strategy
from app.models.strategy_config_snapshot import StrategyConfigSnapshot
from app.models.strategy_run import StrategyRun
from app.models.universe_snapshot import UniverseSnapshot


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_seeded_org(db) -> Organization:
    return db.query(Organization).first()


def _get_seeded_project(db) -> Project:
    return db.query(Project).first()


def _make_strategy(db, org, project, *, name=None, asset_class="equity", status="active"):
    slug = (name or f"test-{uuid.uuid4().hex[:6]}").lower().replace(" ", "-")
    s = Strategy(
        project_id=project.id,
        name=name or f"TestStrat-{uuid.uuid4().hex[:6]}",
        slug=slug,
        asset_class=asset_class,
        status=status,
    )
    db.add(s)
    db.flush()
    return s


def _make_run(db, strategy, *, run_type="backtest", status="completed", run_name=None):
    r = StrategyRun(
        strategy_id=strategy.id,
        run_name=run_name or f"run-{uuid.uuid4().hex[:6]}",
        run_type=run_type,
        status=status,
    )
    db.add(r)
    db.flush()
    return r


def _make_dataset(db, project):
    d = Dataset(
        project_id=project.id,
        name=f"test-dataset-{uuid.uuid4().hex[:6]}",
        dataset_type="ohlcv",
        source_type="manual",
    )
    db.add(d)
    db.flush()
    return d


def _make_dataset_snapshot(db, dataset, *, health_score=90):
    ds = DatasetSnapshot(
        dataset_id=dataset.id,
        version_label=f"v-{uuid.uuid4().hex[:6]}",
        row_count=100,
        health_score=health_score,
    )
    db.add(ds)
    db.flush()
    return ds


def _make_signal_snapshot(db, strategy, *, quality_score=85):
    ss = SignalSnapshot(
        strategy_id=strategy.id,
        label=f"signal-{uuid.uuid4().hex[:6]}",
        source_type="manual",
        rows_json=[],
        row_count=0,
        symbol_count=5,
        symbols_json=["AAPL", "GOOG", "MSFT", "AMZN", "META"],
        missing_signal_count=0,
        signal_hash=uuid.uuid4().hex,
        quality_score=quality_score,
    )
    db.add(ss)
    db.flush()
    return ss


def _make_universe_snapshot(db, strategy):
    us = UniverseSnapshot(
        strategy_id=strategy.id,
        label=f"universe-{uuid.uuid4().hex[:6]}",
        source_type="manual",
        symbols_json=["AAPL", "GOOG", "MSFT"],
        symbol_count=3,
        universe_hash=uuid.uuid4().hex,
    )
    db.add(us)
    db.flush()
    return us


def _make_backtest_audit(db, run, *, trust_score=80, overall_status="good"):
    audit = BacktestAudit(
        strategy_run_id=run.id,
        trust_score=trust_score,
        overall_status=overall_status,
    )
    db.add(audit)
    db.flush()
    return audit


def _make_config_snapshot(db, strategy, *, strategy_version_id=None):
    import hashlib, json as _json
    cfg = {"transaction_cost_bps": 5, "slippage_bps": 2, "fill_model": "vwap"}
    cfg_hash = hashlib.sha256(
        _json.dumps(cfg, sort_keys=True).encode()
    ).hexdigest()
    snap = StrategyConfigSnapshot(
        strategy_id=strategy.id,
        strategy_version_id=strategy_version_id,
        label=f"config-{uuid.uuid4().hex[:6]}",
        source_type="manual_json",
        config_json=cfg,
        config_hash=cfg_hash,
        param_count=3,
        assumption_count=0,
    )
    db.add(snap)
    db.flush()
    return snap


def _replay_url(strategy_id, run_id, **params) -> str:
    base = f"/api/strategies/{strategy_id}/runs/{run_id}/replay-pack"
    if params:
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{base}?{qs}"
    return base


# ---------------------------------------------------------------------------
# TestRunReplayEndpoint
# ---------------------------------------------------------------------------


class TestRunReplayEndpoint:
    """Integration tests for the replay-pack HTTP layer."""

    def test_json_replay_success(self, client, db):
        org = _get_seeded_org(db)
        project = _get_seeded_project(db)
        strategy = _make_strategy(db, org, project)
        run = _make_run(db, strategy)
        db.commit()
        try:
            resp = client.get(_replay_url(strategy.id, run.id))
            assert resp.status_code == 200
            data = resp.json()
            assert "metadata" in data
            assert "sections" in data
            assert "replay_status" in data
            assert "replay_completeness_score" in data
        finally:
            db.delete(run)
            db.delete(strategy)
            db.commit()

    def test_markdown_replay_success(self, client, db):
        org = _get_seeded_org(db)
        project = _get_seeded_project(db)
        strategy = _make_strategy(db, org, project)
        run = _make_run(db, strategy)
        db.commit()
        try:
            resp = client.get(_replay_url(strategy.id, run.id, format="markdown"))
            assert resp.status_code == 200
            data = resp.json()
            assert data.get("content") is not None
            assert isinstance(data["content"], str)
            assert len(data["content"]) > 0
        finally:
            db.delete(run)
            db.delete(strategy)
            db.commit()

    def test_missing_strategy_404(self, client):
        fake_strategy_id = uuid.uuid4()
        fake_run_id = uuid.uuid4()
        resp = client.get(_replay_url(fake_strategy_id, fake_run_id))
        assert resp.status_code == 404

    def test_missing_run_404(self, client, db):
        org = _get_seeded_org(db)
        project = _get_seeded_project(db)
        strategy = _make_strategy(db, org, project)
        db.commit()
        try:
            fake_run_id = uuid.uuid4()
            resp = client.get(_replay_url(strategy.id, fake_run_id))
            assert resp.status_code == 404
        finally:
            db.delete(strategy)
            db.commit()

    def test_run_wrong_strategy_400_or_404(self, client, db):
        org = _get_seeded_org(db)
        project = _get_seeded_project(db)
        strategy_a = _make_strategy(db, org, project)
        strategy_b = _make_strategy(db, org, project)
        run_b = _make_run(db, strategy_b)
        db.commit()
        try:
            # run_b belongs to strategy_b, accessing via strategy_a should fail
            resp = client.get(_replay_url(strategy_a.id, run_b.id))
            assert resp.status_code in (400, 404)
        finally:
            db.delete(run_b)
            db.delete(strategy_b)
            db.delete(strategy_a)
            db.commit()

    def test_metadata_fields_present(self, client, db):
        org = _get_seeded_org(db)
        project = _get_seeded_project(db)
        strategy = _make_strategy(db, org, project)
        run = _make_run(db, strategy)
        db.commit()
        try:
            resp = client.get(_replay_url(strategy.id, run.id))
            assert resp.status_code == 200
            meta = resp.json()["metadata"]
            assert meta["replay_id"] != ""
            assert meta["strategy_id"] == str(strategy.id)
            assert meta["run_id"] == str(run.id)
            assert meta["filename"] != ""
            assert meta["deterministic_note"] != ""
            assert meta["no_execution_replay_note"] != ""
        finally:
            db.delete(run)
            db.delete(strategy)
            db.commit()

    def test_filename_has_correct_extension_json(self, client, db):
        org = _get_seeded_org(db)
        project = _get_seeded_project(db)
        strategy = _make_strategy(db, org, project)
        run = _make_run(db, strategy)
        db.commit()
        try:
            resp = client.get(_replay_url(strategy.id, run.id, format="json"))
            assert resp.status_code == 200
            assert resp.json()["metadata"]["filename"].endswith(".json")
        finally:
            db.delete(run)
            db.delete(strategy)
            db.commit()

    def test_filename_has_correct_extension_markdown(self, client, db):
        org = _get_seeded_org(db)
        project = _get_seeded_project(db)
        strategy = _make_strategy(db, org, project)
        run = _make_run(db, strategy)
        db.commit()
        try:
            resp = client.get(_replay_url(strategy.id, run.id, format="markdown"))
            assert resp.status_code == 200
            assert resp.json()["metadata"]["filename"].endswith(".md")
        finally:
            db.delete(run)
            db.delete(strategy)
            db.commit()


# ---------------------------------------------------------------------------
# TestRunReplaySections
# ---------------------------------------------------------------------------


class TestRunReplaySections:
    """Tests verifying the expected sections are present in the replay pack."""

    def _get_section_keys(self, client, strategy_id, run_id) -> list[str]:
        resp = client.get(_replay_url(strategy_id, run_id))
        assert resp.status_code == 200
        return [s["section_key"] for s in resp.json()["sections"]]

    def test_run_identity_section_present(self, client, db):
        org = _get_seeded_org(db)
        project = _get_seeded_project(db)
        strategy = _make_strategy(db, org, project)
        run = _make_run(db, strategy)
        db.commit()
        try:
            keys = self._get_section_keys(client, strategy.id, run.id)
            assert "run_identity" in keys
        finally:
            db.delete(run)
            db.delete(strategy)
            db.commit()

    def test_backtest_audit_section_present(self, client, db):
        org = _get_seeded_org(db)
        project = _get_seeded_project(db)
        strategy = _make_strategy(db, org, project)
        run = _make_run(db, strategy)
        audit = _make_backtest_audit(db, run, trust_score=72, overall_status="review")
        db.commit()
        try:
            resp = client.get(_replay_url(strategy.id, run.id))
            assert resp.status_code == 200
            sections = resp.json()["sections"]
            audit_sec = next((s for s in sections if s["section_key"] == "backtest_audit"), None)
            assert audit_sec is not None
            assert audit_sec["evidence_json"]["trust_score"] == 72
            assert audit_sec["evidence_json"]["overall_status"] == "review"
        finally:
            db.delete(audit)
            db.delete(run)
            db.delete(strategy)
            db.commit()

    def test_backtest_audit_missing_creates_missing_evidence(self, client, db):
        org = _get_seeded_org(db)
        project = _get_seeded_project(db)
        strategy = _make_strategy(db, org, project)
        run = _make_run(db, strategy)
        db.commit()
        try:
            resp = client.get(_replay_url(strategy.id, run.id))
            assert resp.status_code == 200
            data = resp.json()
            # Section should exist with high severity
            audit_sec = next(
                (s for s in data["sections"] if s["section_key"] == "backtest_audit"),
                None,
            )
            assert audit_sec is not None
            assert audit_sec["severity"] == "high"
            # Missing evidence should include backtest_audit
            missing_types = [m["evidence_type"] for m in data["missing_evidence"]]
            assert "backtest_audit" in missing_types
            # The missing audit entry should have high severity
            audit_missing = next(
                m for m in data["missing_evidence"] if m["evidence_type"] == "backtest_audit"
            )
            assert audit_missing["severity"] == "high"
        finally:
            db.delete(run)
            db.delete(strategy)
            db.commit()

    def test_dataset_section_present_with_linked_run(self, client, db):
        org = _get_seeded_org(db)
        project = _get_seeded_project(db)
        strategy = _make_strategy(db, org, project)
        dataset = _make_dataset(db, project)
        ds = _make_dataset_snapshot(db, dataset, health_score=88)
        run = _make_run(db, strategy)
        run.dataset_snapshot_id = ds.id
        db.flush()
        db.commit()
        try:
            resp = client.get(_replay_url(strategy.id, run.id))
            assert resp.status_code == 200
            sections = resp.json()["sections"]
            ds_sec = next((s for s in sections if s["section_key"] == "dataset_evidence"), None)
            assert ds_sec is not None
            assert ds_sec["evidence_json"]["health_score"] == 88
            assert ds_sec["evidence_json"]["row_count"] == 100
        finally:
            db.delete(run)
            db.delete(ds)
            db.delete(dataset)
            db.delete(strategy)
            db.commit()

    def test_signal_section_present_with_linked_run(self, client, db):
        org = _get_seeded_org(db)
        project = _get_seeded_project(db)
        strategy = _make_strategy(db, org, project)
        ss = _make_signal_snapshot(db, strategy, quality_score=78)
        run = _make_run(db, strategy)
        run.signal_snapshot_id = ss.id
        db.flush()
        db.commit()
        try:
            resp = client.get(_replay_url(strategy.id, run.id))
            assert resp.status_code == 200
            sections = resp.json()["sections"]
            sig_sec = next((s for s in sections if s["section_key"] == "signal_evidence"), None)
            assert sig_sec is not None
            assert sig_sec["evidence_json"]["quality_score"] == 78
            assert sig_sec["evidence_json"]["symbol_count"] == 5
        finally:
            db.delete(run)
            db.delete(ss)
            db.delete(strategy)
            db.commit()

    def test_universe_section_present_with_linked_run(self, client, db):
        org = _get_seeded_org(db)
        project = _get_seeded_project(db)
        strategy = _make_strategy(db, org, project)
        us = _make_universe_snapshot(db, strategy)
        run = _make_run(db, strategy)
        run.universe_snapshot_id = us.id
        db.flush()
        db.commit()
        try:
            resp = client.get(_replay_url(strategy.id, run.id))
            assert resp.status_code == 200
            sections = resp.json()["sections"]
            univ_sec = next((s for s in sections if s["section_key"] == "universe_evidence"), None)
            assert univ_sec is not None
            assert univ_sec["evidence_json"]["symbol_count"] == 3
        finally:
            db.delete(run)
            db.delete(us)
            db.delete(strategy)
            db.commit()

    def test_config_snapshot_section_present(self, client, db):
        org = _get_seeded_org(db)
        project = _get_seeded_project(db)
        strategy = _make_strategy(db, org, project)
        config = _make_config_snapshot(db, strategy)
        run = _make_run(db, strategy)
        db.commit()
        try:
            resp = client.get(_replay_url(strategy.id, run.id))
            assert resp.status_code == 200
            sections = resp.json()["sections"]
            cfg_sec = next(
                (s for s in sections if s["section_key"] == "config_snapshot"), None
            )
            assert cfg_sec is not None
            # Should have found the snapshot (no missing evidence for config)
            data = resp.json()
            missing_types = [m["evidence_type"] for m in data["missing_evidence"]]
            assert "config_snapshot" not in missing_types
        finally:
            db.delete(run)
            db.delete(config)
            db.delete(strategy)
            db.commit()

    def test_computed_context_section_present(self, client, db):
        """computed_context section must always be present even if all calls fail."""
        org = _get_seeded_org(db)
        project = _get_seeded_project(db)
        strategy = _make_strategy(db, org, project)
        run = _make_run(db, strategy)
        db.commit()
        try:
            keys = self._get_section_keys(client, strategy.id, run.id)
            assert "computed_context" in keys
        finally:
            db.delete(run)
            db.delete(strategy)
            db.commit()

    def test_all_core_sections_present(self, client, db):
        """All 10 sections must be present for any run."""
        org = _get_seeded_org(db)
        project = _get_seeded_project(db)
        strategy = _make_strategy(db, org, project)
        run = _make_run(db, strategy)
        db.commit()
        try:
            keys = self._get_section_keys(client, strategy.id, run.id)
            expected = [
                "run_identity",
                "strategy_version",
                "config_snapshot",
                "dataset_evidence",
                "signal_evidence",
                "universe_evidence",
                "backtest_audit",
                "computed_context",
                "alerts_and_reports",
                "timeline_context",
            ]
            for key in expected:
                assert key in keys, f"Section '{key}' missing from replay pack"
        finally:
            db.delete(run)
            db.delete(strategy)
            db.commit()


# ---------------------------------------------------------------------------
# TestRunReplayCompleteness
# ---------------------------------------------------------------------------


class TestRunReplayCompleteness:
    """Tests for completeness scoring and status labels."""

    def test_completeness_score_sparse_empty_run(self, client, db):
        """A run with no linked evidence should score low (sparse/incomplete)."""
        org = _get_seeded_org(db)
        project = _get_seeded_project(db)
        strategy = _make_strategy(db, org, project)
        run = _make_run(db, strategy)
        db.commit()
        try:
            resp = client.get(_replay_url(strategy.id, run.id))
            assert resp.status_code == 200
            data = resp.json()
            score = data["replay_completeness_score"]
            status = data["replay_status"]
            assert score < 65, f"Expected score < 65 for empty run, got {score}"
            assert status in ("sparse", "incomplete", "review")
        finally:
            db.delete(run)
            db.delete(strategy)
            db.commit()

    def test_completeness_score_higher_with_evidence(self, client, db):
        """A run with dataset/signal/config evidence should score higher than an empty run."""
        org = _get_seeded_org(db)
        project = _get_seeded_project(db)
        strategy = _make_strategy(db, org, project)

        dataset = _make_dataset(db, project)
        ds = _make_dataset_snapshot(db, dataset, health_score=90)
        ss = _make_signal_snapshot(db, strategy, quality_score=88)
        us = _make_universe_snapshot(db, strategy)
        config = _make_config_snapshot(db, strategy)
        audit_run = _make_run(db, strategy)
        audit = _make_backtest_audit(db, audit_run, trust_score=85, overall_status="good")
        audit_run.dataset_snapshot_id = ds.id
        audit_run.signal_snapshot_id = ss.id
        audit_run.universe_snapshot_id = us.id
        db.flush()
        db.commit()

        # Empty run for comparison
        empty_run = _make_run(db, strategy)
        db.commit()

        try:
            resp_evidence = client.get(_replay_url(strategy.id, audit_run.id))
            resp_empty = client.get(_replay_url(strategy.id, empty_run.id))
            assert resp_evidence.status_code == 200
            assert resp_empty.status_code == 200
            score_with_evidence = resp_evidence.json()["replay_completeness_score"]
            score_empty = resp_empty.json()["replay_completeness_score"]
            assert score_with_evidence > score_empty, (
                f"Expected evidence run ({score_with_evidence}) > empty run ({score_empty})"
            )
        finally:
            db.delete(empty_run)
            db.delete(audit)
            db.delete(audit_run)
            db.delete(config)
            db.delete(us)
            db.delete(ss)
            db.delete(ds)
            db.delete(dataset)
            db.delete(strategy)
            db.commit()

    def test_replay_status_values_are_valid(self, client, db):
        org = _get_seeded_org(db)
        project = _get_seeded_project(db)
        strategy = _make_strategy(db, org, project)
        run = _make_run(db, strategy)
        db.commit()
        try:
            resp = client.get(_replay_url(strategy.id, run.id))
            assert resp.status_code == 200
            status = resp.json()["replay_status"]
            assert status in ("complete", "review", "incomplete", "sparse")
        finally:
            db.delete(run)
            db.delete(strategy)
            db.commit()

    def test_completeness_score_is_float_in_range(self, client, db):
        org = _get_seeded_org(db)
        project = _get_seeded_project(db)
        strategy = _make_strategy(db, org, project)
        run = _make_run(db, strategy)
        db.commit()
        try:
            resp = client.get(_replay_url(strategy.id, run.id))
            assert resp.status_code == 200
            score = resp.json()["replay_completeness_score"]
            assert isinstance(score, (int, float))
            assert 0.0 <= score <= 100.0
        finally:
            db.delete(run)
            db.delete(strategy)
            db.commit()


# ---------------------------------------------------------------------------
# TestRunReplayLanguage
# ---------------------------------------------------------------------------


class TestRunReplayLanguage:
    """Tests for forbidden language, disclaimer notes, and determinism constraints."""

    FORBIDDEN_WORDS = [
        "buy",
        "sell",
        "hold",
        "profitable",
        "strategy failed",
        "ai-generated",
    ]

    def test_markdown_no_forbidden_language(self, client, db):
        org = _get_seeded_org(db)
        project = _get_seeded_project(db)
        strategy = _make_strategy(db, org, project)
        run = _make_run(db, strategy)
        db.commit()
        try:
            resp = client.get(_replay_url(strategy.id, run.id, format="markdown"))
            assert resp.status_code == 200
            content = resp.json()["content"].lower()
            for word in self.FORBIDDEN_WORDS:
                assert word not in content, (
                    f"Forbidden word/phrase '{word}' found in markdown content"
                )
        finally:
            db.delete(run)
            db.delete(strategy)
            db.commit()

    def test_no_execution_replay_note_present(self, client, db):
        org = _get_seeded_org(db)
        project = _get_seeded_project(db)
        strategy = _make_strategy(db, org, project)
        run = _make_run(db, strategy)
        db.commit()
        try:
            resp = client.get(_replay_url(strategy.id, run.id))
            assert resp.status_code == 200
            note = resp.json()["metadata"]["no_execution_replay_note"]
            assert note is not None
            assert len(note) > 0
            # Must mention the non-execution nature
            note_lower = note.lower()
            assert "not" in note_lower or "no" in note_lower
        finally:
            db.delete(run)
            db.delete(strategy)
            db.commit()

    def test_deterministic_note_present(self, client, db):
        org = _get_seeded_org(db)
        project = _get_seeded_project(db)
        strategy = _make_strategy(db, org, project)
        run = _make_run(db, strategy)
        db.commit()
        try:
            resp = client.get(_replay_url(strategy.id, run.id))
            assert resp.status_code == 200
            note = resp.json()["metadata"]["deterministic_note"]
            assert note is not None
            assert "deterministic" in note.lower()
        finally:
            db.delete(run)
            db.delete(strategy)
            db.commit()

    def test_suggested_checks_deduplicated(self, client, db):
        org = _get_seeded_org(db)
        project = _get_seeded_project(db)
        strategy = _make_strategy(db, org, project)
        run = _make_run(db, strategy)
        db.commit()
        try:
            resp = client.get(_replay_url(strategy.id, run.id))
            assert resp.status_code == 200
            checks = resp.json()["suggested_review_checks"]
            assert len(checks) == len(set(checks)), "Duplicate suggested checks found"
        finally:
            db.delete(run)
            db.delete(strategy)
            db.commit()

    def test_no_timeline_event_created(self, client, db):
        """Replay pack is strictly read-only — must not write any AuditTimelineEvent."""
        org = _get_seeded_org(db)
        project = _get_seeded_project(db)
        strategy = _make_strategy(db, org, project)
        run = _make_run(db, strategy)
        db.commit()
        try:
            before_count = (
                db.query(AuditTimelineEvent)
                .filter(AuditTimelineEvent.strategy_id == strategy.id)
                .count()
            )
            resp = client.get(_replay_url(strategy.id, run.id))
            assert resp.status_code == 200
            db.expire_all()
            after_count = (
                db.query(AuditTimelineEvent)
                .filter(AuditTimelineEvent.strategy_id == strategy.id)
                .count()
            )
            assert before_count == after_count, (
                f"Expected no new timeline events, but count went from "
                f"{before_count} to {after_count}"
            )
        finally:
            db.delete(run)
            db.delete(strategy)
            db.commit()

    def test_raw_evidence_absent_by_default(self, client, db):
        org = _get_seeded_org(db)
        project = _get_seeded_project(db)
        strategy = _make_strategy(db, org, project)
        run = _make_run(db, strategy)
        db.commit()
        try:
            resp = client.get(_replay_url(strategy.id, run.id))
            assert resp.status_code == 200
            assert resp.json().get("raw_evidence") is None
        finally:
            db.delete(run)
            db.delete(strategy)
            db.commit()

    def test_raw_evidence_present_when_requested(self, client, db):
        org = _get_seeded_org(db)
        project = _get_seeded_project(db)
        strategy = _make_strategy(db, org, project)
        run = _make_run(db, strategy)
        db.commit()
        try:
            resp = client.get(
                _replay_url(strategy.id, run.id, include_raw_json="true")
            )
            assert resp.status_code == 200
            assert resp.json().get("raw_evidence") is not None
        finally:
            db.delete(run)
            db.delete(strategy)
            db.commit()

    def test_markdown_contains_strategy_and_run_name(self, client, db):
        org = _get_seeded_org(db)
        project = _get_seeded_project(db)
        strategy = _make_strategy(db, org, project, name="my-replay-strategy")
        run = _make_run(db, strategy, run_name="my-test-run-001")
        db.commit()
        try:
            resp = client.get(_replay_url(strategy.id, run.id, format="markdown"))
            assert resp.status_code == 200
            content = resp.json()["content"]
            assert "my-replay-strategy" in content
            assert "my-test-run-001" in content
        finally:
            db.delete(run)
            db.delete(strategy)
            db.commit()

    def test_markdown_not_investment_advice_disclaimer(self, client, db):
        org = _get_seeded_org(db)
        project = _get_seeded_project(db)
        strategy = _make_strategy(db, org, project)
        run = _make_run(db, strategy)
        db.commit()
        try:
            resp = client.get(_replay_url(strategy.id, run.id, format="markdown"))
            assert resp.status_code == 200
            content = resp.json()["content"].lower()
            assert "not investment advice" in content
        finally:
            db.delete(run)
            db.delete(strategy)
            db.commit()
