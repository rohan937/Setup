"""M74 tests: Strategy Action Queue v1.

Tests for:
  - GET /api/strategies/{id}/action-queue endpoint
  - Deterministic action generation from DB-backbone checks
  - Setup actions on an empty strategy (report, regression, config, SLA, runs)
  - Governance / reporting actions disappear once configured (dedup of "done")
  - Link-evidence action when latest run is missing evidence FKs
  - Severity ordering + sequential priority ranks
  - Language policy: no investment-advice / no AI language

All tests use the shared session-scoped fixtures from conftest.py.
"""
from __future__ import annotations

import uuid

# ---------------------------------------------------------------------------
# Language policy constants
# ---------------------------------------------------------------------------

FORBIDDEN_INVESTMENT_WORDS = [
    "buy", "sell", "short the", "go long", "profit", "investment advice",
    "trading recommendation",
]
FORBIDDEN_AI_WORDS = ["ai-", "a.i.", "machine learning", "neural"]

_SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


def _has_forbidden(text: str, words: list[str]) -> list[str]:
    low = text.lower()
    return [w for w in words if w.lower() in low]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_seeded_project(db):
    from app.models.project import Project
    return db.query(Project).first()


def _get_seeded_org(db):
    from app.models.organization import Organization
    return db.query(Organization).first()


def _make_strategy(db, project_id, *, suffix: str = "") -> object:
    from app.models.strategy import Strategy

    slug = f"m74-{suffix}-{uuid.uuid4().hex[:8]}"
    strat = Strategy(
        project_id=project_id,
        name=f"M74 Test Strategy {suffix}",
        slug=slug,
        asset_class="equity",
        status="active",
    )
    db.add(strat)
    db.flush()
    return strat


def _make_run(db, strategy_id, *, run_type: str = "backtest", linked: bool = False) -> object:
    from app.models.strategy_run import StrategyRun

    run = StrategyRun(
        strategy_id=strategy_id,
        run_name=f"run-{uuid.uuid4().hex[:6]}",
        run_type=run_type,
        status="completed",
    )
    db.add(run)
    db.flush()
    return run


def _make_report(db, org_id, strategy_id) -> object:
    from app.models.report import Report

    rep = Report(
        organization_id=org_id,
        strategy_id=strategy_id,
        report_type="strategy_reliability",
        title="M74 reliability report",
        summary="test",
    )
    db.add(rep)
    db.flush()
    return rep


def _make_regression(db, strategy_id) -> object:
    from app.models.regression import StrategyRegressionTest

    t = StrategyRegressionTest(
        strategy_id=strategy_id,
        name="M74 regression",
        test_key=f"k-{uuid.uuid4().hex[:6]}",
        test_type="metric_threshold",
        operator="gte",
    )
    db.add(t)
    db.flush()
    return t


def _make_config_policy(db, strategy_id) -> object:
    from app.models.config_policy import StrategyConfigPolicy

    p = StrategyConfigPolicy(
        strategy_id=strategy_id,
        name="M74 guardrails",
        policy_json={"rules": []},
    )
    db.add(p)
    db.flush()
    return p


def _make_sla(db, strategy_id) -> object:
    from app.models.evidence_sla import EvidenceSLAPolicy

    s = EvidenceSLAPolicy(
        strategy_id=strategy_id,
        name="M74 SLA",
        policy_json={"rules": []},
    )
    db.add(s)
    db.flush()
    return s


def _fully_configure(db, org_id, strategy_id) -> None:
    _make_report(db, org_id, strategy_id)
    _make_regression(db, strategy_id)
    _make_config_policy(db, strategy_id)
    _make_sla(db, strategy_id)
    db.flush()


def _keys(data) -> set[str]:
    """Return the set of dedup keys (the part after the strategy hex prefix)."""
    return {it["id"].split(":", 1)[1] for it in data["items"]}


def _full_queue(client, strategy_id):
    """Fetch the queue with a high limit so generation (not the top-10 cap) is tested."""
    return client.get(f"/api/strategies/{strategy_id}/action-queue?limit=50").json()


# ---------------------------------------------------------------------------
# Endpoint shape
# ---------------------------------------------------------------------------

class TestActionQueueEndpoint:
    def test_endpoint_returns_200(self, client, db):
        proj = _get_seeded_project(db)
        strat = _make_strategy(db, proj.id, suffix="200")
        db.flush()
        resp = client.get(f"/api/strategies/{strat.id}/action-queue")
        assert resp.status_code == 200

    def test_response_fields(self, client, db):
        proj = _get_seeded_project(db)
        strat = _make_strategy(db, proj.id, suffix="fields")
        db.flush()
        data = client.get(f"/api/strategies/{strat.id}/action-queue").json()
        for field in (
            "strategy_id", "strategy_name", "generated_at", "items",
            "total_action_count", "completed_count", "pending_count",
            "blocked_count", "optional_count", "deterministic_summary",
            "disclaimer",
        ):
            assert field in data, f"missing {field}"
        assert isinstance(data["items"], list)

    def test_unknown_strategy_404(self, client):
        resp = client.get(f"/api/strategies/{uuid.uuid4()}/action-queue")
        assert resp.status_code == 404

    def test_item_fields(self, client, db):
        proj = _get_seeded_project(db)
        strat = _make_strategy(db, proj.id, suffix="itemfields")
        db.flush()
        data = client.get(f"/api/strategies/{strat.id}/action-queue").json()
        assert data["items"], "empty strategy should still have setup actions"
        item = data["items"][0]
        for field in (
            "id", "strategy_id", "title", "description", "why_it_matters",
            "severity", "priority_rank", "status", "category", "source",
            "target_tab", "target_panel_label", "action_label", "action_type",
            "deterministic_reason", "created_from",
        ):
            assert field in item, f"item missing {field}"

    def test_limit_caps_items(self, client, db):
        proj = _get_seeded_project(db)
        strat = _make_strategy(db, proj.id, suffix="limit")
        db.flush()
        data = client.get(f"/api/strategies/{strat.id}/action-queue?limit=2").json()
        assert len(data["items"]) <= 2


# ---------------------------------------------------------------------------
# Generation rules — DB backbone (fully deterministic)
# ---------------------------------------------------------------------------

class TestGenerationRules:
    def test_empty_strategy_has_setup_actions(self, client, db):
        proj = _get_seeded_project(db)
        strat = _make_strategy(db, proj.id, suffix="empty")
        db.flush()
        data = _full_queue(client, strat.id)
        keys = _keys(data)
        # No runs, no report, no governance objects → all setup actions present.
        assert "no_runs" in keys
        assert "generate_report" in keys
        assert "create_regression_tests" in keys
        assert "create_config_policy" in keys
        assert "create_sla" in keys

    def test_missing_report_generates_report_action(self, client, db):
        proj = _get_seeded_project(db)
        strat = _make_strategy(db, proj.id, suffix="rep")
        db.flush()
        data = _full_queue(client, strat.id)
        gen = [i for i in data["items"] if i["action_type"] == "generate_report"]
        assert gen, "missing report should yield a generate_report action"
        assert gen[0]["category"] == "reporting"

    def test_missing_regression_tests_action(self, client, db):
        proj = _get_seeded_project(db)
        strat = _make_strategy(db, proj.id, suffix="reg")
        db.flush()
        data = client.get(f"/api/strategies/{strat.id}/action-queue").json()
        reg = [i for i in data["items"] if i["action_type"] == "create_regression_tests"]
        assert reg and reg[0]["category"] == "governance"

    def test_missing_config_policy_action(self, client, db):
        proj = _get_seeded_project(db)
        strat = _make_strategy(db, proj.id, suffix="cfg")
        db.flush()
        data = client.get(f"/api/strategies/{strat.id}/action-queue").json()
        cfg = [i for i in data["items"] if i["action_type"] == "create_policy"]
        assert cfg and cfg[0]["category"] == "governance"

    def test_missing_sla_action(self, client, db):
        proj = _get_seeded_project(db)
        strat = _make_strategy(db, proj.id, suffix="sla")
        db.flush()
        data = _full_queue(client, strat.id)
        sla = [i for i in data["items"] if i["action_type"] == "create_sla"]
        assert sla, "missing SLA should yield a create_sla action"

    def test_latest_run_missing_evidence_link_action(self, client, db):
        proj = _get_seeded_project(db)
        strat = _make_strategy(db, proj.id, suffix="link")
        _make_run(db, strat.id, run_type="backtest")  # all FKs null
        db.flush()
        data = _full_queue(client, strat.id)
        keys = _keys(data)
        assert "link_run_evidence" in keys
        link = next(i for i in data["items"] if i["id"].endswith("link_run_evidence"))
        assert link["related_object_type"] == "strategy_run"
        assert link["target_tab"] == "runs"

    def test_configured_strategy_drops_setup_actions(self, client, db):
        proj = _get_seeded_project(db)
        org = _get_seeded_org(db)
        strat = _make_strategy(db, proj.id, suffix="done")
        _fully_configure(db, org.id, strat.id)
        data = _full_queue(client, strat.id)
        keys = _keys(data)
        assert "generate_report" not in keys
        assert "create_regression_tests" not in keys
        assert "create_config_policy" not in keys
        assert "create_sla" not in keys


# ---------------------------------------------------------------------------
# Dedup + ordering + counts
# ---------------------------------------------------------------------------

class TestOrderingAndDedup:
    def test_priority_ranks_sequential(self, client, db):
        proj = _get_seeded_project(db)
        strat = _make_strategy(db, proj.id, suffix="rank")
        db.flush()
        data = client.get(f"/api/strategies/{strat.id}/action-queue").json()
        ranks = [i["priority_rank"] for i in data["items"]]
        assert ranks == list(range(1, len(ranks) + 1))

    def test_no_duplicate_ids(self, client, db):
        proj = _get_seeded_project(db)
        strat = _make_strategy(db, proj.id, suffix="dedup")
        _make_run(db, strat.id, run_type="backtest")
        db.flush()
        data = client.get(f"/api/strategies/{strat.id}/action-queue").json()
        ids = [i["id"] for i in data["items"]]
        assert len(ids) == len(set(ids)), "action ids must be unique (dedup)"

    def test_severity_ordering_non_decreasing(self, client, db):
        proj = _get_seeded_project(db)
        strat = _make_strategy(db, proj.id, suffix="sev")
        _make_run(db, strat.id, run_type="backtest")
        db.flush()
        data = client.get(f"/api/strategies/{strat.id}/action-queue").json()
        sev_ranks = [_SEVERITY_RANK[i["severity"]] for i in data["items"]]
        assert sev_ranks == sorted(sev_ranks), "items must be ordered by severity"

    def test_counts_consistent(self, client, db):
        proj = _get_seeded_project(db)
        strat = _make_strategy(db, proj.id, suffix="counts")
        db.flush()
        data = client.get(f"/api/strategies/{strat.id}/action-queue").json()
        total = data["total_action_count"]
        assert total == (
            data["completed_count"] + data["pending_count"]
            + data["blocked_count"] + data["optional_count"]
        )
        assert total >= len(data["items"])


# ---------------------------------------------------------------------------
# Language policy
# ---------------------------------------------------------------------------

class TestLanguagePolicy:
    def _all_text(self, data) -> str:
        # The disclaimer intentionally contains the phrase "trading
        # recommendations" (a negation), so it is excluded from the scan.
        chunks = [data["deterministic_summary"]]
        for it in data["items"]:
            chunks += [
                it["title"], it["description"], it["why_it_matters"],
                it["action_label"], it["deterministic_reason"],
            ]
        return " ".join(chunks)

    def test_no_investment_language(self, client, db):
        proj = _get_seeded_project(db)
        strat = _make_strategy(db, proj.id, suffix="lang1")
        _make_run(db, strat.id, run_type="backtest")
        db.flush()
        data = client.get(f"/api/strategies/{strat.id}/action-queue").json()
        found = _has_forbidden(self._all_text(data), FORBIDDEN_INVESTMENT_WORDS)
        assert not found, f"investment language found: {found}"

    def test_no_ai_language(self, client, db):
        proj = _get_seeded_project(db)
        strat = _make_strategy(db, proj.id, suffix="lang2")
        db.flush()
        data = client.get(f"/api/strategies/{strat.id}/action-queue").json()
        found = _has_forbidden(self._all_text(data), FORBIDDEN_AI_WORDS)
        assert not found, f"AI language found: {found}"

    def test_disclaimer_present(self, client, db):
        proj = _get_seeded_project(db)
        strat = _make_strategy(db, proj.id, suffix="disc")
        db.flush()
        data = client.get(f"/api/strategies/{strat.id}/action-queue").json()
        assert "does not provide trading recommendations" in data["disclaimer"]
