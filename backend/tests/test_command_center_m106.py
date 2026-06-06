"""M106 tests: Research Command Center workspace-triage aggregation (read-only).

Covers:
  - TestBuildCommandCenter: build_command_center(db) payload shape + behavior
  - TestReadOnly: build_command_center must never create/mutate rows
  - TestCommandCenterEndpoint: GET /api/command-center integration

The aggregation is deterministic and READ-ONLY. It composes existing read-only
services (portfolio reliability, lifecycle pipeline) plus the active-review and
open-alert queries. Uses the shared session-scoped fixtures (client/db) from
conftest.py.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

# Registered endpoint path. dashboard.router has no internal prefix and is
# included under the "/api" prefix in app.api.router, so the "/command-center"
# route resolves at "/api/command-center".
COMMAND_CENTER_PATH = "/api/command-center"

_WORKSPACE_INT_KEYS = (
    "strategy_count",
    "healthy_count",
    "review_count",
    "blocked_count",
    "open_alert_count",
    "high_critical_alert_count",
    "pending_action_count",
    "pending_review_count",
    "production_ready_count",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_seeded_project(db):
    from app.models.project import Project

    return db.query(Project).first()


def _org_id_for_project(db, project) -> uuid.UUID:
    return project.organization_id


def _make_strategy(db, project_id, *, suffix: str = "") -> object:
    from app.models.strategy import Strategy

    slug = f"m106-{suffix}-{uuid.uuid4().hex[:8]}"
    strat = Strategy(
        project_id=project_id,
        name=f"M106 Test Strategy {suffix}",
        slug=slug,
        asset_class="equity",
        status="active",
    )
    db.add(strat)
    db.flush()
    return strat


def _make_alert(
    db,
    organization_id,
    strategy_id,
    *,
    severity: str = "high",
    status: str = "open",
) -> object:
    from app.models.alert import Alert

    alert = Alert(
        organization_id=organization_id,
        rule_type="m106_test_rule",
        status=status,
        severity=severity,
        title=f"M106 {severity} alert",
        strategy_id=str(strategy_id),
        triggered_at=datetime.now(timezone.utc),
    )
    db.add(alert)
    db.flush()
    return alert


def _make_review(db, strategy_id, *, status: str = "submitted") -> object:
    from app.models.strategy_review import StrategyReview

    review = StrategyReview(
        strategy_id=str(strategy_id),
        target_stage="paper_candidate",
        status=status,
        submitted_at=datetime.now(timezone.utc),
    )
    db.add(review)
    db.flush()
    return review


def _cleanup(db, *objs):
    for obj in reversed(objs):
        try:
            db.delete(obj)
        except Exception:
            pass
    db.flush()


def _count_rows(db) -> dict[str, int]:
    from app.models.alert import Alert
    from app.models.strategy import Strategy
    from app.models.strategy_review import StrategyReview
    from app.models.strategy_run import StrategyRun

    return {
        "Strategy": db.query(Strategy).count(),
        "Alert": db.query(Alert).count(),
        "StrategyReview": db.query(StrategyReview).count(),
        "StrategyRun": db.query(StrategyRun).count(),
    }


# ---------------------------------------------------------------------------
# TestBuildCommandCenter
# ---------------------------------------------------------------------------


class TestBuildCommandCenter:
    """Shape + behavior checks for build_command_center."""

    def test_returns_all_sections(self, db):
        from app.services.command_center import build_command_center

        data = build_command_center(db)
        expected_keys = {
            "workspace_summary",
            "lifecycle_summary",
            "top_actions",
            "strategies_needing_attention",
            "pending_reviews",
            "top_alerts",
            "generated_at",
            "disclaimer",
        }
        assert expected_keys <= set(data.keys()), (
            f"Missing keys: {expected_keys - set(data.keys())}"
        )

    def test_empty_workspace_graceful(self, db):
        """Aggregation never crashes; counts are ints>=0, sections are lists."""
        from app.services.command_center import build_command_center

        data = build_command_center(db)

        ws = data["workspace_summary"]
        assert isinstance(ws, dict)
        for k, v in ws.items():
            assert isinstance(v, int), f"workspace_summary[{k!r}] not int: {type(v)}"
            assert v >= 0, f"workspace_summary[{k!r}] negative: {v}"

        for list_key in (
            "lifecycle_summary",
            "top_actions",
            "strategies_needing_attention",
            "pending_reviews",
            "top_alerts",
        ):
            assert isinstance(data[list_key], list), f"{list_key} must be a list"

    def test_workspace_summary_counts_ints(self, db):
        from app.services.command_center import build_command_center

        ws = build_command_center(db)["workspace_summary"]
        for key in _WORKSPACE_INT_KEYS:
            assert key in ws, f"workspace_summary missing {key}"
            assert isinstance(ws[key], int), (
                f"workspace_summary[{key!r}] must be int, got {type(ws[key])}"
            )
            assert ws[key] >= 0, f"workspace_summary[{key!r}] must be >= 0"

    def test_strategy_with_alert_appears_in_attention(self, db):
        """A strategy with an open high-severity alert surfaces in attention +
        top_alerts."""
        from app.services.command_center import build_command_center

        project = _get_seeded_project(db)
        org_id = _org_id_for_project(db, project)
        strat = _make_strategy(db, project.id, suffix="alerted")
        alert = _make_alert(db, org_id, strat.id, severity="high", status="open")
        try:
            data = build_command_center(db)

            attention_ids = {
                str(r["strategy_id"]) for r in data["strategies_needing_attention"]
            }
            assert str(strat.id) in attention_ids, (
                "Strategy with open high-severity alert must appear in "
                f"strategies_needing_attention; got {attention_ids}"
            )

            assert len(data["top_alerts"]) >= 1, (
                "Open high-severity alert must produce a top_alerts entry"
            )
            alert_ids = {str(a["id"]) for a in data["top_alerts"]}
            assert str(alert.id) in alert_ids, (
                f"Created alert {alert.id} missing from top_alerts {alert_ids}"
            )
        finally:
            _cleanup(db, alert, strat)

    def test_pending_review_appears(self, db):
        """A submitted StrategyReview surfaces in pending_reviews + count."""
        from app.services.command_center import build_command_center

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="review")
        review = _make_review(db, strat.id, status="submitted")
        try:
            data = build_command_center(db)

            assert len(data["pending_reviews"]) >= 1, (
                "Submitted review must yield a non-empty pending_reviews list"
            )
            review_ids = {str(r["review_id"]) for r in data["pending_reviews"]}
            assert str(review.id) in review_ids, (
                f"Created review {review.id} missing from {review_ids}"
            )
            assert data["workspace_summary"]["pending_review_count"] >= 0
        finally:
            _cleanup(db, review, strat)

    def test_lifecycle_summary_has_stages(self, db):
        from app.services.command_center import build_command_center

        lifecycle = build_command_center(db)["lifecycle_summary"]
        assert isinstance(lifecycle, list)
        assert len(lifecycle) >= 1, "Expected at least one lifecycle stage entry"
        for stage in lifecycle:
            assert "key" in stage, f"stage missing 'key': {stage}"
            assert "label" in stage, f"stage missing 'label': {stage}"
            assert "count" in stage, f"stage missing 'count': {stage}"
            assert isinstance(stage["count"], int)

    def test_disclaimer(self, db):
        from app.services.command_center import build_command_center

        disclaimer = build_command_center(db)["disclaimer"]
        assert "not trading advice" in disclaimer.lower(), (
            f"Expected 'not trading advice' in disclaimer, got {disclaimer!r}"
        )


# ---------------------------------------------------------------------------
# TestReadOnly
# ---------------------------------------------------------------------------


class TestReadOnly:
    """build_command_center must never create or mutate rows."""

    def test_build_creates_no_rows(self, db):
        from app.services.command_center import build_command_center

        before = _count_rows(db)
        build_command_center(db)
        after = _count_rows(db)
        assert before == after, (
            f"build_command_center mutated row counts: {before} -> {after}"
        )


# ---------------------------------------------------------------------------
# TestCommandCenterEndpoint
# ---------------------------------------------------------------------------


class TestCommandCenterEndpoint:
    """Integration tests via TestClient for the M106 command-center endpoint."""

    def test_endpoint_200(self, client):
        resp = client.get(COMMAND_CENTER_PATH)
        assert resp.status_code == 200, (
            f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        )
        data = resp.json()
        for field in ("workspace_summary", "lifecycle_summary", "disclaimer"):
            assert field in data, f"Missing field: {field}"

    def test_endpoint_shape(self, client):
        resp = client.get(COMMAND_CENTER_PATH)
        assert resp.status_code == 200
        data = resp.json()
        for list_field in (
            "top_actions",
            "strategies_needing_attention",
            "pending_reviews",
            "top_alerts",
        ):
            assert isinstance(data[list_field], list), (
                f"{list_field} must be a list, got {type(data[list_field])}"
            )
