"""M19 Reliability Score History + Trend Panel tests.

Tests cover:
- compare_reliability_scores service: overall delta, component deltas,
  evidence count deltas, resolved / still-missing evidence, status change,
  same-score self-comparison, deterministic explanation language
- GET /api/strategies/{id}/reliability-scores  (history list)
  - newest-first ordering, limit/offset, 404 for unknown strategy
- GET /api/strategies/{id}/reliability-scores/compare
  - success, 404 for unknown score, wrong-strategy score rejected
  - same score compared to itself returns zero deltas
- GET /api/strategies/{id}/reliability-score/trend
  - not_enough_history when < 2 scores
  - has_trend=True when 2+ scores
  - latest vs previous comparison populated
  - no timeline event created (read-only)
- All existing M2–M18 tests still pass (run full suite via conftest)
"""

from __future__ import annotations

import uuid

import pytest

from app.services.strategy_reliability import (
    ReliabilityComparisonResult,
    compare_reliability_scores,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _new_strategy(client, name: str | None = None) -> dict:
    projects = client.get("/api/projects").json()
    project_id = projects[0]["id"]
    resp = client.post(
        "/api/strategies",
        json={"project_id": project_id, "name": name or f"M19-{uuid.uuid4().hex[:6]}"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _compute_score(client, strategy_id: str) -> dict:
    resp = client.post(f"/api/strategies/{strategy_id}/reliability-score")
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# Unit tests: compare_reliability_scores service
# ---------------------------------------------------------------------------

class TestCompareReliabilityScoresService:
    """Tests for the compare_reliability_scores() service function.

    We build lightweight mock objects (SimpleNamespace) so we don't need a DB.
    """

    def _make_score(self, **kwargs):
        from types import SimpleNamespace
        import datetime as dt
        defaults = dict(
            id=uuid.uuid4(),
            strategy_id=uuid.uuid4(),
            generated_at=dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc),
            overall_score=70.0,
            status="good",
            strategy_activity_score=75.0,
            data_evidence_score=80.0,
            backtest_trust_score=65.0,
            config_evidence_score=85.0,
            universe_evidence_score=75.0,
            signal_evidence_score=None,
            alert_penalty_score=100.0,
            report_coverage_score=None,
            evidence_counts_json={"run_count": 2, "version_count": 1},
            missing_evidence_json=["No signal snapshots found."],
        )
        defaults.update(kwargs)
        return SimpleNamespace(**defaults)

    def test_overall_delta_computed(self):
        a = self._make_score(overall_score=60.0)
        b = self._make_score(overall_score=75.0)
        result = compare_reliability_scores(a, b)
        assert result.overall_delta == pytest.approx(15.0, abs=0.1)

    def test_overall_delta_none_when_a_none(self):
        a = self._make_score(overall_score=None, status="insufficient_evidence")
        b = self._make_score(overall_score=72.0, status="good")
        result = compare_reliability_scores(a, b)
        assert result.overall_delta is None

    def test_overall_delta_none_when_both_none(self):
        a = self._make_score(overall_score=None, status="insufficient_evidence")
        b = self._make_score(overall_score=None, status="insufficient_evidence")
        result = compare_reliability_scores(a, b)
        assert result.overall_delta is None

    def test_status_changed_detected(self):
        a = self._make_score(status="review")
        b = self._make_score(status="good")
        result = compare_reliability_scores(a, b)
        assert result.status_changed is True

    def test_status_unchanged_when_same(self):
        a = self._make_score(status="good")
        b = self._make_score(status="good")
        result = compare_reliability_scores(a, b)
        assert result.status_changed is False

    def test_component_deltas_present(self):
        a = self._make_score(data_evidence_score=60.0)
        b = self._make_score(data_evidence_score=80.0)
        result = compare_reliability_scores(a, b)
        data_delta = next(
            d for d in result.component_deltas if d.component == "data_evidence_score"
        )
        assert data_delta.delta == pytest.approx(20.0, abs=0.1)
        assert data_delta.score_a == pytest.approx(60.0)
        assert data_delta.score_b == pytest.approx(80.0)

    def test_became_available_detected(self):
        a = self._make_score(signal_evidence_score=None)
        b = self._make_score(signal_evidence_score=85.0)
        result = compare_reliability_scores(a, b)
        sig_delta = next(
            d for d in result.component_deltas if d.component == "signal_evidence_score"
        )
        assert sig_delta.became_available is True
        assert sig_delta.delta is None

    def test_became_null_detected(self):
        a = self._make_score(signal_evidence_score=85.0)
        b = self._make_score(signal_evidence_score=None)
        result = compare_reliability_scores(a, b)
        sig_delta = next(
            d for d in result.component_deltas if d.component == "signal_evidence_score"
        )
        assert sig_delta.became_null is True

    def test_evidence_count_deltas_computed(self):
        a = self._make_score(evidence_counts_json={"run_count": 1})
        b = self._make_score(evidence_counts_json={"run_count": 3})
        result = compare_reliability_scores(a, b)
        run_delta = next(e for e in result.evidence_count_deltas if e.key == "run_count")
        assert run_delta.delta == 2
        assert run_delta.count_a == 1
        assert run_delta.count_b == 3

    def test_resolved_missing_evidence_detected(self):
        a = self._make_score(missing_evidence_json=["No signal snapshots.", "No audits."])
        b = self._make_score(missing_evidence_json=["No signal snapshots."])
        result = compare_reliability_scores(a, b)
        assert "No audits." in result.resolved_missing_evidence

    def test_still_missing_evidence_detected(self):
        a = self._make_score(missing_evidence_json=["No signal snapshots."])
        b = self._make_score(missing_evidence_json=["No signal snapshots."])
        result = compare_reliability_scores(a, b)
        assert "No signal snapshots." in result.still_missing_evidence

    def test_newly_available_evidence_detected(self):
        a = self._make_score(missing_evidence_json=[])
        b = self._make_score(missing_evidence_json=["No backtest audits."])
        result = compare_reliability_scores(a, b)
        assert "No backtest audits." in result.newly_available_evidence

    def test_self_comparison_zero_deltas(self):
        score = self._make_score(overall_score=72.5)
        result = compare_reliability_scores(score, score)
        assert result.overall_delta == pytest.approx(0.0, abs=0.1)
        assert result.status_changed is False
        for d in result.component_deltas:
            if d.delta is not None:
                assert d.delta == pytest.approx(0.0, abs=0.05)

    def test_explanation_is_deterministic_string(self):
        a = self._make_score(overall_score=60.0, status="review")
        b = self._make_score(overall_score=78.0, status="good")
        result = compare_reliability_scores(a, b)
        exp = result.deterministic_explanation
        assert isinstance(exp, str)
        assert len(exp) > 20

    def test_explanation_avoids_causal_overclaiming(self):
        """Explanation must not contain causal language."""
        a = self._make_score(overall_score=60.0)
        b = self._make_score(overall_score=78.0)
        result = compare_reliability_scores(a, b)
        exp = result.explanation if hasattr(result, "explanation") else result.deterministic_explanation
        # Check hedged language is present
        assert "deterministic" in exp.lower() or "not a causal" in exp.lower()
        # Check prohibited causal language absent
        for phrase in ["because of", "caused by", "due to", "proves that"]:
            assert phrase not in exp.lower(), f"Prohibited phrase found: {phrase!r}"

    def test_highlighted_changes_populated_on_large_delta(self):
        a = self._make_score(data_evidence_score=40.0, backtest_trust_score=50.0)
        b = self._make_score(data_evidence_score=80.0, backtest_trust_score=85.0)
        result = compare_reliability_scores(a, b)
        assert len(result.highlighted_changes) > 0
        # Should mention data evidence or backtest trust
        combined = " ".join(result.highlighted_changes).lower()
        assert "data evidence" in combined or "backtest" in combined

    def test_highlighted_empty_on_no_significant_change(self):
        a = self._make_score(data_evidence_score=80.0)
        b = self._make_score(data_evidence_score=80.5)  # < 3-point threshold
        result = compare_reliability_scores(a, b)
        # Highlighted only for status change or large deltas
        data_hl = [h for h in result.highlighted_changes if "data" in h.lower()]
        assert len(data_hl) == 0


# ---------------------------------------------------------------------------
# API: GET /api/strategies/{id}/reliability-scores  (history)
# ---------------------------------------------------------------------------

class TestReliabilityScoreHistory:
    def test_empty_history_returns_404_for_unknown_strategy(self, client):
        resp = client.get(f"/api/strategies/{uuid.uuid4()}/reliability-scores")
        assert resp.status_code == 404

    def test_empty_history_before_any_compute(self, client):
        s = _new_strategy(client)
        resp = client.get(f"/api/strategies/{s['id']}/reliability-scores")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["items"] == []

    def test_history_returns_scores_after_compute(self, client):
        s = _new_strategy(client)
        _compute_score(client, s["id"])
        resp = client.get(f"/api/strategies/{s['id']}/reliability-scores")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1

    def test_history_newest_first(self, client):
        s = _new_strategy(client)
        _compute_score(client, s["id"])
        _compute_score(client, s["id"])
        _compute_score(client, s["id"])
        resp = client.get(f"/api/strategies/{s['id']}/reliability-scores")
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 3
        # generated_at should be descending (newest first)
        dates = [item["generated_at"] for item in items]
        assert dates == sorted(dates, reverse=True)

    def test_history_limit_respected(self, client):
        s = _new_strategy(client)
        for _ in range(5):
            _compute_score(client, s["id"])
        resp = client.get(f"/api/strategies/{s['id']}/reliability-scores?limit=3")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 5
        assert len(data["items"]) == 3

    def test_history_offset_respected(self, client):
        s = _new_strategy(client)
        for _ in range(4):
            _compute_score(client, s["id"])
        resp = client.get(
            f"/api/strategies/{s['id']}/reliability-scores?limit=10&offset=2"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 4
        assert len(data["items"]) == 2

    def test_history_response_has_pagination_fields(self, client):
        s = _new_strategy(client)
        resp = client.get(
            f"/api/strategies/{s['id']}/reliability-scores?limit=10&offset=0"
        )
        data = resp.json()
        assert "total" in data
        assert "limit" in data
        assert "offset" in data
        assert "items" in data

    def test_history_items_have_all_component_fields(self, client):
        s = _new_strategy(client)
        _compute_score(client, s["id"])
        items = client.get(
            f"/api/strategies/{s['id']}/reliability-scores"
        ).json()["items"]
        item = items[0]
        for field in [
            "id", "strategy_id", "overall_score", "status",
            "strategy_activity_score", "data_evidence_score", "backtest_trust_score",
            "config_evidence_score", "universe_evidence_score", "signal_evidence_score",
            "alert_penalty_score", "report_coverage_score",
            "evidence_counts_json", "missing_evidence_json", "suggested_checks_json",
            "generated_at",
        ]:
            assert field in item, f"Missing field: {field}"


# ---------------------------------------------------------------------------
# API: GET /api/strategies/{id}/reliability-scores/compare
# ---------------------------------------------------------------------------

class TestReliabilityScoreCompareEndpoint:
    def test_compare_two_scores_success(self, client):
        s = _new_strategy(client)
        score_a = _compute_score(client, s["id"])
        score_b = _compute_score(client, s["id"])
        resp = client.get(
            f"/api/strategies/{s['id']}/reliability-scores/compare"
            f"?score_a_id={score_a['id']}&score_b_id={score_b['id']}"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["score_a_id"] == score_a["id"]
        assert data["score_b_id"] == score_b["id"]

    def test_compare_unknown_strategy_404(self, client):
        resp = client.get(
            f"/api/strategies/{uuid.uuid4()}/reliability-scores/compare"
            f"?score_a_id={uuid.uuid4()}&score_b_id={uuid.uuid4()}"
        )
        assert resp.status_code == 404

    def test_compare_unknown_score_a_404(self, client):
        s = _new_strategy(client)
        score_b = _compute_score(client, s["id"])
        resp = client.get(
            f"/api/strategies/{s['id']}/reliability-scores/compare"
            f"?score_a_id={uuid.uuid4()}&score_b_id={score_b['id']}"
        )
        assert resp.status_code == 404

    def test_compare_unknown_score_b_404(self, client):
        s = _new_strategy(client)
        score_a = _compute_score(client, s["id"])
        resp = client.get(
            f"/api/strategies/{s['id']}/reliability-scores/compare"
            f"?score_a_id={score_a['id']}&score_b_id={uuid.uuid4()}"
        )
        assert resp.status_code == 404

    def test_compare_rejects_score_from_another_strategy(self, client):
        s1 = _new_strategy(client)
        s2 = _new_strategy(client)
        score_a = _compute_score(client, s1["id"])
        score_b = _compute_score(client, s2["id"])
        # score_b belongs to s2, but we're querying s1 → 404
        resp = client.get(
            f"/api/strategies/{s1['id']}/reliability-scores/compare"
            f"?score_a_id={score_a['id']}&score_b_id={score_b['id']}"
        )
        assert resp.status_code == 404

    def test_compare_same_score_to_itself(self, client):
        s = _new_strategy(client)
        score = _compute_score(client, s["id"])
        resp = client.get(
            f"/api/strategies/{s['id']}/reliability-scores/compare"
            f"?score_a_id={score['id']}&score_b_id={score['id']}"
        )
        assert resp.status_code == 200
        data = resp.json()
        # Self-comparison: overall_delta should be 0 or None
        if data["overall_delta"] is not None:
            assert abs(data["overall_delta"]) < 0.1

    def test_compare_response_has_required_fields(self, client):
        s = _new_strategy(client)
        score_a = _compute_score(client, s["id"])
        score_b = _compute_score(client, s["id"])
        data = client.get(
            f"/api/strategies/{s['id']}/reliability-scores/compare"
            f"?score_a_id={score_a['id']}&score_b_id={score_b['id']}"
        ).json()
        for field in [
            "score_a_id", "score_b_id", "score_a_generated_at", "score_b_generated_at",
            "overall_score_a", "overall_score_b", "overall_delta",
            "status_a", "status_b", "status_changed",
            "component_deltas", "evidence_count_deltas",
            "newly_available_evidence", "resolved_missing_evidence", "still_missing_evidence",
            "highlighted_changes", "deterministic_explanation",
        ]:
            assert field in data, f"Missing field: {field}"

    def test_compare_component_deltas_present(self, client):
        s = _new_strategy(client)
        score_a = _compute_score(client, s["id"])
        score_b = _compute_score(client, s["id"])
        data = client.get(
            f"/api/strategies/{s['id']}/reliability-scores/compare"
            f"?score_a_id={score_a['id']}&score_b_id={score_b['id']}"
        ).json()
        assert isinstance(data["component_deltas"], list)
        assert len(data["component_deltas"]) == 8  # all 8 components
        first = data["component_deltas"][0]
        assert "component" in first
        assert "label" in first
        assert "score_a" in first
        assert "score_b" in first
        assert "became_available" in first

    def test_compare_no_timeline_event_created(self, client):
        s = _new_strategy(client)
        score_a = _compute_score(client, s["id"])
        score_b = _compute_score(client, s["id"])
        # Count timeline events before
        tl_before = client.get(
            f"/api/strategies/{s['id']}/timeline"
        ).json()["total"]
        # Compare (read-only)
        client.get(
            f"/api/strategies/{s['id']}/reliability-scores/compare"
            f"?score_a_id={score_a['id']}&score_b_id={score_b['id']}"
        )
        # Count timeline events after
        tl_after = client.get(
            f"/api/strategies/{s['id']}/timeline"
        ).json()["total"]
        assert tl_after == tl_before  # no new event for a read-only comparison

    def test_compare_explanation_avoids_causal_phrases(self, client):
        s = _new_strategy(client)
        score_a = _compute_score(client, s["id"])
        score_b = _compute_score(client, s["id"])
        data = client.get(
            f"/api/strategies/{s['id']}/reliability-scores/compare"
            f"?score_a_id={score_a['id']}&score_b_id={score_b['id']}"
        ).json()
        exp = data["deterministic_explanation"].lower()
        for phrase in ["because of", "caused by", "due to", "proves that"]:
            assert phrase not in exp, f"Causal phrase found: {phrase!r}"
        assert "deterministic" in exp or "not a causal" in exp


# ---------------------------------------------------------------------------
# API: GET /api/strategies/{id}/reliability-score/trend
# ---------------------------------------------------------------------------

class TestReliabilityScoreTrend:
    def test_trend_404_for_unknown_strategy(self, client):
        resp = client.get(f"/api/strategies/{uuid.uuid4()}/reliability-score/trend")
        assert resp.status_code == 404

    def test_not_enough_history_when_zero_scores(self, client):
        s = _new_strategy(client)
        resp = client.get(f"/api/strategies/{s['id']}/reliability-score/trend")
        assert resp.status_code == 200
        data = resp.json()
        assert data["has_trend"] is False
        assert "not enough" in data["message"].lower() or "compute" in data["message"].lower()
        assert data["latest"] is None
        assert data["previous"] is None
        assert data["comparison"] is None

    def test_not_enough_history_when_one_score(self, client):
        s = _new_strategy(client)
        _compute_score(client, s["id"])
        resp = client.get(f"/api/strategies/{s['id']}/reliability-score/trend")
        assert resp.status_code == 200
        data = resp.json()
        assert data["has_trend"] is False
        assert data["latest"] is not None  # shows the one score
        assert data["previous"] is None

    def test_trend_has_trend_when_two_scores(self, client):
        s = _new_strategy(client)
        _compute_score(client, s["id"])
        _compute_score(client, s["id"])
        resp = client.get(f"/api/strategies/{s['id']}/reliability-score/trend")
        assert resp.status_code == 200
        data = resp.json()
        assert data["has_trend"] is True

    def test_trend_latest_and_previous_populated(self, client):
        s = _new_strategy(client)
        score_a = _compute_score(client, s["id"])
        score_b = _compute_score(client, s["id"])
        resp = client.get(f"/api/strategies/{s['id']}/reliability-score/trend")
        data = resp.json()
        assert data["latest"]["id"] == score_b["id"]
        assert data["previous"]["id"] == score_a["id"]

    def test_trend_comparison_populated(self, client):
        s = _new_strategy(client)
        _compute_score(client, s["id"])
        _compute_score(client, s["id"])
        resp = client.get(f"/api/strategies/{s['id']}/reliability-score/trend")
        data = resp.json()
        assert data["comparison"] is not None
        cmp = data["comparison"]
        assert "component_deltas" in cmp
        assert "deterministic_explanation" in cmp
        assert "overall_delta" in cmp

    def test_trend_no_timeline_event_created(self, client):
        s = _new_strategy(client)
        _compute_score(client, s["id"])
        _compute_score(client, s["id"])
        tl_before = client.get(
            f"/api/strategies/{s['id']}/timeline"
        ).json()["total"]
        client.get(f"/api/strategies/{s['id']}/reliability-score/trend")
        tl_after = client.get(
            f"/api/strategies/{s['id']}/timeline"
        ).json()["total"]
        assert tl_after == tl_before

    def test_trend_comparison_previous_is_score_a(self, client):
        """Trend uses previous (older) as A and latest (newer) as B."""
        s = _new_strategy(client)
        score_a = _compute_score(client, s["id"])
        score_b = _compute_score(client, s["id"])
        data = client.get(
            f"/api/strategies/{s['id']}/reliability-score/trend"
        ).json()
        cmp = data["comparison"]
        assert cmp["score_a_id"] == score_a["id"]
        assert cmp["score_b_id"] == score_b["id"]

    def test_trend_uses_latest_two_of_three(self, client):
        """With 3 scores, trend compares 2nd-newest and newest (not 1st and 2nd)."""
        s = _new_strategy(client)
        score_1 = _compute_score(client, s["id"])  # oldest
        score_2 = _compute_score(client, s["id"])  # middle
        score_3 = _compute_score(client, s["id"])  # newest
        data = client.get(
            f"/api/strategies/{s['id']}/reliability-score/trend"
        ).json()
        assert data["latest"]["id"] == score_3["id"]
        assert data["previous"]["id"] == score_2["id"]
        # score_1 (oldest) should NOT appear
        assert data["comparison"]["score_a_id"] == score_2["id"]
