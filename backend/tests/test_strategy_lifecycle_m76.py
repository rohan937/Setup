"""M76 tests: Strategy Lifecycle inference.

Covers GET /api/strategies/{id}/lifecycle:
  - response shape + 404
  - stage inference from run types (no runs / backtest / paper / live)
  - stage ordering + states (completed/current/blocked/upcoming)
  - blockers derived from the action queue + action metadata
  - language policy (no trading-recommendation language)

Uses the shared session fixtures (client/db) from conftest.py.
"""
from __future__ import annotations

import uuid

FORBIDDEN = ["buy", "sell", "trading recommendation", "investment advice"]
STAGE_ORDER = [
    "research", "backtest", "backtest_review",
    "paper_candidate", "shadow", "production_candidate",
]


def _project(db):
    from app.models.project import Project
    return db.query(Project).first()


def _mk_strategy(db, project_id, suffix=""):
    from app.models.strategy import Strategy
    s = Strategy(
        project_id=project_id,
        name=f"M76 {suffix}",
        slug=f"m76-{suffix}-{uuid.uuid4().hex[:8]}",
        asset_class="equity",
        status="active",
    )
    db.add(s)
    db.flush()
    return s


def _mk_run(db, strategy_id, run_type):
    from app.models.strategy_run import StrategyRun
    r = StrategyRun(
        strategy_id=strategy_id,
        run_name=f"run-{uuid.uuid4().hex[:6]}",
        run_type=run_type,
        status="completed",
    )
    db.add(r)
    db.flush()
    return r


def _get(client, sid):
    return client.get(f"/api/strategies/{sid}/lifecycle").json()


class TestLifecycleEndpoint:
    def test_returns_200(self, client, db):
        s = _mk_strategy(db, _project(db).id, "200")
        db.flush()
        assert client.get(f"/api/strategies/{s.id}/lifecycle").status_code == 200

    def test_unknown_404(self, client):
        assert client.get(f"/api/strategies/{uuid.uuid4()}/lifecycle").status_code == 404

    def test_response_fields(self, client, db):
        s = _mk_strategy(db, _project(db).id, "fields")
        db.flush()
        d = _get(client, s.id)
        for f in (
            "strategy_id", "strategy_name", "generated_at", "stages",
            "current_stage", "current_stage_label", "next_stage", "next_stage_label",
            "blocked", "blocked_stage", "blockers", "suggested_actions",
            "deterministic_summary", "disclaimer",
        ):
            assert f in d, f"missing {f}"

    def test_six_stages_in_order(self, client, db):
        s = _mk_strategy(db, _project(db).id, "stages")
        db.flush()
        d = _get(client, s.id)
        assert [st["key"] for st in d["stages"]] == STAGE_ORDER


class TestStageInference:
    def test_no_runs_is_research(self, client, db):
        s = _mk_strategy(db, _project(db).id, "noruns")
        db.flush()
        d = _get(client, s.id)
        assert d["current_stage"] == "research"
        assert d["next_stage"] == "backtest"

    def test_backtest_run_is_backtest(self, client, db):
        s = _mk_strategy(db, _project(db).id, "bt")
        _mk_run(db, s.id, "backtest")
        db.flush()
        d = _get(client, s.id)
        # A bare backtest run (no review-ready evidence) sits at Backtest.
        assert d["current_stage"] == "backtest"
        assert d["next_stage"] == "backtest_review"

    def test_paper_run_is_paper_candidate(self, client, db):
        s = _mk_strategy(db, _project(db).id, "paper")
        _mk_run(db, s.id, "backtest")
        _mk_run(db, s.id, "paper")
        db.flush()
        d = _get(client, s.id)
        assert d["current_stage"] == "paper_candidate"
        assert d["next_stage"] == "shadow"

    def test_live_run_is_shadow_or_beyond(self, client, db):
        s = _mk_strategy(db, _project(db).id, "live")
        _mk_run(db, s.id, "backtest")
        _mk_run(db, s.id, "live")
        db.flush()
        d = _get(client, s.id)
        idx = STAGE_ORDER.index(d["current_stage"])
        assert idx >= STAGE_ORDER.index("shadow")


class TestStageStates:
    def test_states_consistent(self, client, db):
        s = _mk_strategy(db, _project(db).id, "states")
        _mk_run(db, s.id, "backtest")
        db.flush()
        d = _get(client, s.id)
        cur = d["current_stage"]
        cur_idx = STAGE_ORDER.index(cur)
        for st in d["stages"]:
            if st["index"] < cur_idx:
                assert st["state"] == "completed"
            elif st["index"] == cur_idx:
                assert st["state"] == "current"
            else:
                assert st["state"] in ("upcoming", "blocked")
        # exactly one current
        assert sum(1 for st in d["stages"] if st["state"] == "current") == 1

    def test_blocked_stage_is_next_when_blocked(self, client, db):
        s = _mk_strategy(db, _project(db).id, "blocked")
        _mk_run(db, s.id, "backtest")
        db.flush()
        d = _get(client, s.id)
        if d["blocked"]:
            assert d["blocked_stage"] == d["next_stage"]
            blocked_states = [st for st in d["stages"] if st["state"] == "blocked"]
            assert len(blocked_states) == 1
            assert blocked_states[0]["key"] == d["next_stage"]


class TestBlockers:
    def test_empty_strategy_has_blockers(self, client, db):
        # A bare strategy has missing evidence/governance → blockers.
        s = _mk_strategy(db, _project(db).id, "bl")
        _mk_run(db, s.id, "backtest")
        db.flush()
        d = _get(client, s.id)
        assert d["blocked"] is True
        assert len(d["blockers"]) > 0
        b = d["blockers"][0]
        for f in ("reason", "detail", "severity", "action_type", "action_label"):
            assert f in b
        assert len(d["suggested_actions"]) > 0

    def test_link_evidence_blocker_carries_run_id(self, client, db):
        s = _mk_strategy(db, _project(db).id, "link")
        run = _mk_run(db, s.id, "backtest")  # all evidence FKs null
        db.flush()
        d = _get(client, s.id)
        link_blockers = [b for b in d["blockers"] if b["action_type"] == "link_evidence"]
        if link_blockers:
            assert link_blockers[0]["related_run_id"] == str(run.id)


class TestLanguagePolicy:
    def test_no_trading_language(self, client, db):
        s = _mk_strategy(db, _project(db).id, "lang")
        _mk_run(db, s.id, "backtest")
        db.flush()
        d = _get(client, s.id)
        text = " ".join([
            d["deterministic_summary"],
            *[b["reason"] + " " + b["detail"] for b in d["blockers"]],
        ]).lower()
        found = [w for w in FORBIDDEN if w in text]
        assert not found, f"forbidden language: {found}"

    def test_disclaimer_not_trading(self, client, db):
        s = _mk_strategy(db, _project(db).id, "disc")
        db.flush()
        d = _get(client, s.id)
        assert "not a trading recommendation" in d["disclaimer"].lower()
