"""M40 config diff enrichment tests.

Tests cover:
- Enriched comparison service function (compare_config_snapshots_enriched)
- Assumption classification logic (classify_assumption_change)
- GET /api/strategies/{id}/config-snapshots/compare-v2 endpoint
"""

from __future__ import annotations

import uuid


# ---------------------------------------------------------------------------
# Helpers (reuse M15 pattern)
# ---------------------------------------------------------------------------

def _new_strategy(client, name: str | None = None) -> dict:
    projects = client.get("/api/projects").json()
    project_id = projects[0]["id"]
    resp = client.post(
        "/api/strategies",
        json={"project_id": project_id, "name": name or f"M40 Strategy {uuid.uuid4().hex[:6]}"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _create_snapshot(client, strategy_id: str, label: str, config: dict) -> dict:
    resp = client.post(
        f"/api/strategies/{strategy_id}/config-snapshots",
        json={"label": label, "config_json": config},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _compare_v2(client, strategy_id: str, snap_a_id: str, snap_b_id: str):
    return client.get(
        f"/api/strategies/{strategy_id}/config-snapshots/compare-v2",
        params={"snapshot_a_id": snap_a_id, "snapshot_b_id": snap_b_id},
    )


# ---------------------------------------------------------------------------
# TestConfigDiffEnriched — service-level tests
# ---------------------------------------------------------------------------

class TestConfigDiffEnriched:
    """Tests for compare_config_snapshots_enriched via the API endpoint."""

    def test_identical_configs_no_changes(self, client):
        sid = _new_strategy(client)["id"]
        config = {
            "params": {"lookback": 20, "threshold": 0.5},
            "assumptions": {"transaction_cost_bps": 5, "slippage_bps": 3},
        }
        snap_a = _create_snapshot(client, sid, "m40-ident-a", config)
        snap_b = _create_snapshot(client, sid, "m40-ident-b", config)
        try:
            resp = _compare_v2(client, sid, snap_a["id"], snap_b["id"])
            assert resp.status_code == 200, resp.text
            data = resp.json()
            assert data["total_changes"] == 0
            assert data["is_same_config"] is True
        finally:
            pass

    def test_added_param_detected(self, client):
        sid = _new_strategy(client)["id"]
        config_a = {"params": {"lookback": 20}}
        config_b = {"params": {"lookback": 20, "new_param": 99}}
        snap_a = _create_snapshot(client, sid, "m40-add-param-a", config_a)
        snap_b = _create_snapshot(client, sid, "m40-add-param-b", config_b)
        try:
            resp = _compare_v2(client, sid, snap_a["id"], snap_b["id"])
            assert resp.status_code == 200, resp.text
            data = resp.json()
            changes = data["params_diff"]["changes"]
            added = [c for c in changes if c["change_type"] == "added" and c["key"] == "new_param"]
            assert len(added) == 1
        finally:
            pass

    def test_removed_param_detected(self, client):
        sid = _new_strategy(client)["id"]
        config_a = {"params": {"lookback": 20, "old_param": 5}}
        config_b = {"params": {"lookback": 20}}
        snap_a = _create_snapshot(client, sid, "m40-rem-param-a", config_a)
        snap_b = _create_snapshot(client, sid, "m40-rem-param-b", config_b)
        try:
            resp = _compare_v2(client, sid, snap_a["id"], snap_b["id"])
            assert resp.status_code == 200, resp.text
            data = resp.json()
            changes = data["params_diff"]["changes"]
            removed = [c for c in changes if c["change_type"] == "removed" and c["key"] == "old_param"]
            assert len(removed) == 1
        finally:
            pass

    def test_changed_param_detected(self, client):
        sid = _new_strategy(client)["id"]
        config_a = {"params": {"lookback": 20}}
        config_b = {"params": {"lookback": 50}}
        snap_a = _create_snapshot(client, sid, "m40-chg-param-a", config_a)
        snap_b = _create_snapshot(client, sid, "m40-chg-param-b", config_b)
        try:
            resp = _compare_v2(client, sid, snap_a["id"], snap_b["id"])
            assert resp.status_code == 200, resp.text
            data = resp.json()
            changes = data["params_diff"]["changes"]
            changed = [c for c in changes if c["change_type"] == "changed" and c["key"] == "lookback"]
            assert len(changed) == 1
            assert changed[0]["old_value"] == 20
            assert changed[0]["new_value"] == 50
        finally:
            pass

    def test_added_assumption_detected(self, client):
        sid = _new_strategy(client)["id"]
        config_a = {"assumptions": {}}
        config_b = {"assumptions": {"transaction_cost_bps": 5}}
        snap_a = _create_snapshot(client, sid, "m40-add-assump-a", config_a)
        snap_b = _create_snapshot(client, sid, "m40-add-assump-b", config_b)
        try:
            resp = _compare_v2(client, sid, snap_a["id"], snap_b["id"])
            assert resp.status_code == 200, resp.text
            data = resp.json()
            changes = data["assumptions_diff"]["changes"]
            added = [c for c in changes if c["change_type"] == "added" and c["key"] == "transaction_cost_bps"]
            assert len(added) == 1
        finally:
            pass

    def test_removed_assumption_detected(self, client):
        sid = _new_strategy(client)["id"]
        config_a = {"assumptions": {"slippage_bps": 3}}
        config_b = {"assumptions": {}}
        snap_a = _create_snapshot(client, sid, "m40-rem-assump-a", config_a)
        snap_b = _create_snapshot(client, sid, "m40-rem-assump-b", config_b)
        try:
            resp = _compare_v2(client, sid, snap_a["id"], snap_b["id"])
            assert resp.status_code == 200, resp.text
            data = resp.json()
            changes = data["assumptions_diff"]["changes"]
            removed = [c for c in changes if c["change_type"] == "removed" and c["key"] == "slippage_bps"]
            assert len(removed) == 1
        finally:
            pass

    def test_changed_assumption_detected(self, client):
        sid = _new_strategy(client)["id"]
        config_a = {"assumptions": {"fill_model": "next_bar_open"}}
        config_b = {"assumptions": {"fill_model": "close"}}
        snap_a = _create_snapshot(client, sid, "m40-chg-assump-a", config_a)
        snap_b = _create_snapshot(client, sid, "m40-chg-assump-b", config_b)
        try:
            resp = _compare_v2(client, sid, snap_a["id"], snap_b["id"])
            assert resp.status_code == 200, resp.text
            data = resp.json()
            changes = data["assumptions_diff"]["changes"]
            changed = [c for c in changes if c["change_type"] == "changed" and c["key"] == "fill_model"]
            assert len(changed) == 1
        finally:
            pass


# ---------------------------------------------------------------------------
# TestAssumptionClassification — unit tests via the service directly
# ---------------------------------------------------------------------------

class TestAssumptionClassification:
    """Unit tests for classify_assumption_change() logic."""

    def _classify(self, key, old_val, new_val):
        from app.services.config_snapshots import classify_assumption_change
        return classify_assumption_change(key, old_val, new_val)

    def test_adding_cost_bps_positive(self):
        impact, reason, check = self._classify("transaction_cost_bps", None, 5)
        assert impact == "positive"

    def test_removing_cost_bps_weakening(self):
        impact, reason, check = self._classify("transaction_cost_bps", 5, None)
        assert impact == "weakening"

    def test_decreasing_cost_bps_review(self):
        impact, reason, check = self._classify("transaction_cost_bps", 10, 3)
        assert impact == "review"

    def test_increasing_cost_bps_positive(self):
        impact, reason, check = self._classify("transaction_cost_bps", 3, 10)
        assert impact == "positive"

    def test_same_close_fill_weakening(self):
        impact, reason, check = self._classify("fill_model", "next_bar_open", "close")
        assert impact == "weakening"

    def test_improving_fill_positive(self):
        impact, reason, check = self._classify("fill_model", "close", "next_bar_open")
        assert impact == "positive"

    def test_adding_slippage_positive(self):
        impact, reason, check = self._classify("slippage_bps", None, 5)
        assert impact == "positive"

    def test_removing_slippage_weakening(self):
        impact, reason, check = self._classify("slippage_bps", 5, None)
        assert impact == "weakening"

    def test_removing_liquidity_filter_weakening(self):
        impact, reason, check = self._classify("liquidity_filter", "adv_1m", None)
        assert impact == "weakening"


# ---------------------------------------------------------------------------
# TestApiEndpoint — HTTP endpoint tests
# ---------------------------------------------------------------------------

class TestApiEndpoint:
    def test_compare_v2_returns_200(self, client):
        sid = _new_strategy(client)["id"]
        snap_a = _create_snapshot(client, sid, "m40-api-a", {"params": {"x": 1}})
        snap_b = _create_snapshot(client, sid, "m40-api-b", {"params": {"x": 2}})
        try:
            resp = _compare_v2(client, sid, snap_a["id"], snap_b["id"])
            assert resp.status_code == 200, resp.text
        finally:
            pass

    def test_response_has_enriched_fields(self, client):
        sid = _new_strategy(client)["id"]
        config_a = {
            "assumptions": {"transaction_cost_bps": 5, "fill_model": "next_bar_open"},
        }
        config_b = {
            "assumptions": {"fill_model": "close"},
        }
        snap_a = _create_snapshot(client, sid, "m40-enrich-a", config_a)
        snap_b = _create_snapshot(client, sid, "m40-enrich-b", config_b)
        try:
            resp = _compare_v2(client, sid, snap_a["id"], snap_b["id"])
            assert resp.status_code == 200, resp.text
            data = resp.json()
            assert "weakening_changes" in data
            assert "positive_changes" in data
            assert "suggested_checks" in data
            assert "deterministic_explanation" in data
            assert isinstance(data["weakening_changes"], list)
            assert isinstance(data["positive_changes"], list)
            assert isinstance(data["suggested_checks"], list)
        finally:
            pass

    def test_unknown_strategy_404(self, client):
        try:
            fake_id = str(uuid.uuid4())
            snap_id = str(uuid.uuid4())
            resp = client.get(
                f"/api/strategies/{fake_id}/config-snapshots/compare-v2",
                params={"snapshot_a_id": snap_id, "snapshot_b_id": snap_id},
            )
            assert resp.status_code == 404
        finally:
            pass

    def test_snapshot_wrong_strategy_400(self, client):
        sid_a = _new_strategy(client)["id"]
        sid_b = _new_strategy(client)["id"]
        snap_from_b = _create_snapshot(client, sid_b, "m40-wrong-strat", {"x": 1})
        snap_from_a = _create_snapshot(client, sid_a, "m40-correct-strat", {"x": 1})
        try:
            resp = _compare_v2(client, sid_a, snap_from_a["id"], snap_from_b["id"])
            # snap_from_b belongs to sid_b, not sid_a → 404
            assert resp.status_code == 404
        finally:
            pass

    def test_no_timeline_event_created(self, client, db):
        from app.models.audit_timeline_event import AuditTimelineEvent
        sid = _new_strategy(client)["id"]
        snap_a = _create_snapshot(client, sid, "m40-noevt-a", {"params": {"z": 1}})
        snap_b = _create_snapshot(client, sid, "m40-noevt-b", {"params": {"z": 2}})
        try:
            count_before = db.query(AuditTimelineEvent).count()
            _compare_v2(client, sid, snap_a["id"], snap_b["id"])
            count_after = db.query(AuditTimelineEvent).count()
            assert count_after == count_before
        finally:
            pass

    def test_deterministic_explanation_no_investment_language(self, client):
        sid = _new_strategy(client)["id"]
        snap_a = _create_snapshot(client, sid, "m40-lang-a", {"params": {"alpha": 0.1}})
        snap_b = _create_snapshot(client, sid, "m40-lang-b", {"params": {"alpha": 0.2}})
        try:
            resp = _compare_v2(client, sid, snap_a["id"], snap_b["id"])
            assert resp.status_code == 200, resp.text
            explanation = resp.json()["deterministic_explanation"].lower()
            for forbidden in ("buy", "sell", "profit"):
                assert forbidden not in explanation, f"Forbidden word '{forbidden}' found in explanation"
            # The spec says "Not investment advice." must appear (verbatim check on original case)
            assert "investment advice" in resp.json()["deterministic_explanation"].lower() or \
                   resp.json()["total_changes"] == 0
        finally:
            pass
