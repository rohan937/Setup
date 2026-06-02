"""M44 tests: Strategy Comparison Report endpoint.

Tests for:
  - POST /api/strategies/compare/report
  - JSON and markdown format support
  - Section presence and metadata correctness
  - No AuditTimelineEvent side effects
  - raw_evidence gating
  - Input validation (400, 422)
  - Language safety (no forbidden words)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from app.models.audit_timeline_event import AuditTimelineEvent
from app.models.organization import Organization
from app.models.project import Project
from app.models.strategy import Strategy
from app.models.strategy_run import StrategyRun


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


def _make_run(db, strategy, *, run_type="backtest", status="completed"):
    r = StrategyRun(
        strategy_id=strategy.id,
        run_name=f"run-{uuid.uuid4().hex[:6]}",
        run_type=run_type,
        status=status,
    )
    db.add(r)
    db.flush()
    return r


def _get_seeded_org(db):
    return db.query(Organization).first()


def _get_seeded_project(db):
    return db.query(Project).first()


def _post_report(client, strategy_ids, *, format="json", include_raw_json=False):
    return client.post(
        "/api/strategies/compare/report",
        json={
            "strategy_ids": [str(sid) for sid in strategy_ids],
            "format": format,
            "include_raw_json": include_raw_json,
        },
    )


# ---------------------------------------------------------------------------
# TestComparisonReportEndpoint
# ---------------------------------------------------------------------------


class TestComparisonReportEndpoint:
    """HTTP-layer integration tests for the comparison report endpoint."""

    def test_json_report_two_strategies(self, client, db):
        org = _get_seeded_org(db)
        project = _get_seeded_project(db)
        s1 = _make_strategy(db, org, project)
        s2 = _make_strategy(db, org, project)
        db.commit()
        try:
            resp = _post_report(client, [s1.id, s2.id])
            assert resp.status_code == 200
            data = resp.json()
            assert data["format"] == "json"
        finally:
            db.delete(s1)
            db.delete(s2)
            db.commit()

    def test_markdown_report(self, client, db):
        org = _get_seeded_org(db)
        project = _get_seeded_project(db)
        s1 = _make_strategy(db, org, project)
        s2 = _make_strategy(db, org, project)
        db.commit()
        try:
            resp = _post_report(client, [s1.id, s2.id], format="markdown")
            assert resp.status_code == 200
            data = resp.json()
            assert data["content"] is not None
            assert len(data["content"]) > 0
        finally:
            db.delete(s1)
            db.delete(s2)
            db.commit()

    def test_rejects_fewer_than_two(self, client, db):
        org = _get_seeded_org(db)
        project = _get_seeded_project(db)
        s1 = _make_strategy(db, org, project)
        db.commit()
        try:
            resp = _post_report(client, [s1.id])
            assert resp.status_code == 422
        finally:
            db.delete(s1)
            db.commit()

    def test_rejects_more_than_four(self, client, db):
        org = _get_seeded_org(db)
        project = _get_seeded_project(db)
        strategies = [_make_strategy(db, org, project) for _ in range(5)]
        db.commit()
        try:
            resp = _post_report(client, [s.id for s in strategies])
            assert resp.status_code == 422
        finally:
            for s in strategies:
                db.delete(s)
            db.commit()

    def test_missing_strategy_400(self, client):
        fake1 = uuid.uuid4()
        fake2 = uuid.uuid4()
        resp = _post_report(client, [fake1, fake2])
        assert resp.status_code == 400

    def test_response_has_sections(self, client, db):
        org = _get_seeded_org(db)
        project = _get_seeded_project(db)
        s1 = _make_strategy(db, org, project)
        s2 = _make_strategy(db, org, project)
        db.commit()
        try:
            resp = _post_report(client, [s1.id, s2.id])
            assert resp.status_code == 200
            data = resp.json()
            assert "sections" in data
            assert isinstance(data["sections"], list)
            assert len(data["sections"]) > 0
        finally:
            db.delete(s1)
            db.delete(s2)
            db.commit()

    def test_response_has_summaries(self, client, db):
        org = _get_seeded_org(db)
        project = _get_seeded_project(db)
        s1 = _make_strategy(db, org, project)
        s2 = _make_strategy(db, org, project)
        db.commit()
        try:
            resp = _post_report(client, [s1.id, s2.id])
            assert resp.status_code == 200
            data = resp.json()
            assert "strategy_summaries" in data
            assert isinstance(data["strategy_summaries"], list)
            assert len(data["strategy_summaries"]) == 2
        finally:
            db.delete(s1)
            db.delete(s2)
            db.commit()

    def test_response_has_rankings(self, client, db):
        org = _get_seeded_org(db)
        project = _get_seeded_project(db)
        s1 = _make_strategy(db, org, project)
        s2 = _make_strategy(db, org, project)
        db.commit()
        try:
            resp = _post_report(client, [s1.id, s2.id])
            assert resp.status_code == 200
            data = resp.json()
            assert "rankings" in data
            assert isinstance(data["rankings"], dict)
            assert len(data["rankings"]) > 0
        finally:
            db.delete(s1)
            db.delete(s2)
            db.commit()

    def test_response_has_agenda(self, client, db):
        org = _get_seeded_org(db)
        project = _get_seeded_project(db)
        s1 = _make_strategy(db, org, project)
        s2 = _make_strategy(db, org, project)
        db.commit()
        try:
            resp = _post_report(client, [s1.id, s2.id])
            assert resp.status_code == 200
            data = resp.json()
            assert "suggested_review_agenda" in data
            assert isinstance(data["suggested_review_agenda"], list)
            assert len(data["suggested_review_agenda"]) > 0
        finally:
            db.delete(s1)
            db.delete(s2)
            db.commit()

    def test_filename_has_correct_extension_json(self, client, db):
        org = _get_seeded_org(db)
        project = _get_seeded_project(db)
        s1 = _make_strategy(db, org, project)
        s2 = _make_strategy(db, org, project)
        db.commit()
        try:
            resp = _post_report(client, [s1.id, s2.id], format="json")
            assert resp.status_code == 200
            data = resp.json()
            assert data["filename"].endswith(".json")
        finally:
            db.delete(s1)
            db.delete(s2)
            db.commit()

    def test_filename_has_correct_extension_markdown(self, client, db):
        org = _get_seeded_org(db)
        project = _get_seeded_project(db)
        s1 = _make_strategy(db, org, project)
        s2 = _make_strategy(db, org, project)
        db.commit()
        try:
            resp = _post_report(client, [s1.id, s2.id], format="markdown")
            assert resp.status_code == 200
            data = resp.json()
            assert data["filename"].endswith(".md")
        finally:
            db.delete(s1)
            db.delete(s2)
            db.commit()


# ---------------------------------------------------------------------------
# TestReportContent
# ---------------------------------------------------------------------------


class TestReportContent:
    """Tests for specific section presence and content correctness."""

    def _make_two_strategies(self, db):
        org = _get_seeded_org(db)
        project = _get_seeded_project(db)
        s1 = _make_strategy(db, org, project)
        s2 = _make_strategy(db, org, project)
        db.commit()
        return s1, s2

    def _cleanup(self, db, *strategies):
        for s in strategies:
            db.delete(s)
        db.commit()

    def _get_sections(self, client, db):
        s1, s2 = self._make_two_strategies(db)
        try:
            resp = _post_report(client, [s1.id, s2.id])
            assert resp.status_code == 200
            return resp.json()["sections"], s1, s2
        except Exception:
            self._cleanup(db, s1, s2)
            raise

    def test_health_section_present(self, client, db):
        s1, s2 = self._make_two_strategies(db)
        try:
            resp = _post_report(client, [s1.id, s2.id])
            assert resp.status_code == 200
            keys = [sec["section_key"] for sec in resp.json()["sections"]]
            assert "health_comparison" in keys
        finally:
            self._cleanup(db, s1, s2)

    def test_reliability_section_present(self, client, db):
        s1, s2 = self._make_two_strategies(db)
        try:
            resp = _post_report(client, [s1.id, s2.id])
            assert resp.status_code == 200
            keys = [sec["section_key"] for sec in resp.json()["sections"]]
            assert "reliability_comparison" in keys
        finally:
            self._cleanup(db, s1, s2)

    def test_coverage_section_present(self, client, db):
        s1, s2 = self._make_two_strategies(db)
        try:
            resp = _post_report(client, [s1.id, s2.id])
            assert resp.status_code == 200
            keys = [sec["section_key"] for sec in resp.json()["sections"]]
            assert "coverage_comparison" in keys
        finally:
            self._cleanup(db, s1, s2)

    def test_assumption_section_present(self, client, db):
        s1, s2 = self._make_two_strategies(db)
        try:
            resp = _post_report(client, [s1.id, s2.id])
            assert resp.status_code == 200
            keys = [sec["section_key"] for sec in resp.json()["sections"]]
            assert "assumption_comparison" in keys
        finally:
            self._cleanup(db, s1, s2)

    def test_trends_section_present(self, client, db):
        s1, s2 = self._make_two_strategies(db)
        try:
            resp = _post_report(client, [s1.id, s2.id])
            assert resp.status_code == 200
            keys = [sec["section_key"] for sec in resp.json()["sections"]]
            assert "trend_comparison" in keys
        finally:
            self._cleanup(db, s1, s2)

    def test_alerts_section_present(self, client, db):
        s1, s2 = self._make_two_strategies(db)
        try:
            resp = _post_report(client, [s1.id, s2.id])
            assert resp.status_code == 200
            keys = [sec["section_key"] for sec in resp.json()["sections"]]
            assert "alerts_comparison" in keys
        finally:
            self._cleanup(db, s1, s2)

    def test_raw_evidence_absent_default(self, client, db):
        s1, s2 = self._make_two_strategies(db)
        try:
            resp = _post_report(client, [s1.id, s2.id], include_raw_json=False)
            assert resp.status_code == 200
            assert resp.json()["raw_evidence"] is None
        finally:
            self._cleanup(db, s1, s2)

    def test_raw_evidence_present(self, client, db):
        s1, s2 = self._make_two_strategies(db)
        try:
            resp = _post_report(client, [s1.id, s2.id], include_raw_json=True)
            assert resp.status_code == 200
            assert resp.json()["raw_evidence"] is not None
        finally:
            self._cleanup(db, s1, s2)

    def test_no_timeline_event_created(self, client, db):
        s1, s2 = self._make_two_strategies(db)
        before_count = db.query(AuditTimelineEvent).count()
        try:
            resp = _post_report(client, [s1.id, s2.id])
            assert resp.status_code == 200
            after_count = db.query(AuditTimelineEvent).count()
            assert after_count == before_count
        finally:
            self._cleanup(db, s1, s2)


# ---------------------------------------------------------------------------
# TestReportLanguage
# ---------------------------------------------------------------------------


_FORBIDDEN_WORDS = ["buy", "sell", "most profitable", "best strategy", "worst strategy", "AI-generated"]


class TestReportLanguage:
    """Tests that report content uses safe, evidence-only language."""

    def _make_two_strategies(self, db):
        org = _get_seeded_org(db)
        project = _get_seeded_project(db)
        s1 = _make_strategy(db, org, project)
        s2 = _make_strategy(db, org, project)
        db.commit()
        return s1, s2

    def _cleanup(self, db, *strategies):
        for s in strategies:
            db.delete(s)
        db.commit()

    def test_markdown_no_forbidden_words(self, client, db):
        s1, s2 = self._make_two_strategies(db)
        try:
            resp = _post_report(client, [s1.id, s2.id], format="markdown")
            assert resp.status_code == 200
            content = resp.json()["content"] or ""
            content_lower = content.lower()
            for word in _FORBIDDEN_WORDS:
                assert word.lower() not in content_lower, (
                    f"Forbidden word '{word}' found in markdown content"
                )
        finally:
            self._cleanup(db, s1, s2)

    def test_agenda_no_investment_advice_words(self, client, db):
        s1, s2 = self._make_two_strategies(db)
        try:
            resp = _post_report(client, [s1.id, s2.id])
            assert resp.status_code == 200
            agenda_text = " ".join(resp.json()["suggested_review_agenda"]).lower()
            for word in ["buy", "sell"]:
                assert word not in agenda_text, (
                    f"Forbidden word '{word}' found in suggested_review_agenda"
                )
        finally:
            self._cleanup(db, s1, s2)

    def test_note_present(self, client, db):
        s1, s2 = self._make_two_strategies(db)
        try:
            resp = _post_report(client, [s1.id, s2.id])
            assert resp.status_code == 200
            note = resp.json()["metadata"]["note"].lower()
            assert "deterministic" in note
        finally:
            self._cleanup(db, s1, s2)
