"""M15 strategy versions and config snapshot tests.

Tests cover:
- POST /api/strategies/{id}/versions: 201, 404 strategy, 409 duplicate label
- GET  /api/strategies/{id}/versions: list newest-first, config_snapshot_count
- POST /api/strategies/{id}/config-snapshots: 201, hash/count computation, version link,
  version belongs to wrong strategy → 404, missing strategy → 404
- GET  /api/strategies/{id}/config-snapshots: list newest-first, filter by version_id
- GET  /api/strategies/{id}/config-snapshots/compare: diffs, is_same_config, 404 cases
- GET  /api/config-snapshots/{snapshot_id}: full detail with config_json, 404
- GET  /api/strategies/{id}: config_snapshots included, per-version config_snapshot_count
"""

from __future__ import annotations

import uuid


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _new_strategy(client, name: str | None = None) -> dict:
    """Create a fresh strategy and return its JSON response."""
    projects = client.get("/api/projects").json()
    project_id = projects[0]["id"]
    resp = client.post(
        "/api/strategies",
        json={"project_id": project_id, "name": name or f"M15 Strategy {uuid.uuid4().hex[:6]}"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _create_version(client, strategy_id: str, label: str = "v1.0", **extra) -> dict:
    """Create a strategy version and return its JSON response."""
    payload = {"version_label": label, **extra}
    resp = client.post(f"/api/strategies/{strategy_id}/versions", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _create_snapshot(client, strategy_id: str, label: str = "snap-1", config: dict | None = None, **extra) -> dict:
    """Create a config snapshot and return its JSON response."""
    payload = {
        "label": label,
        "config_json": config if config is not None else {"mode": "test"},
        **extra,
    }
    resp = client.post(f"/api/strategies/{strategy_id}/config-snapshots", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# POST /api/strategies/{id}/versions
# ---------------------------------------------------------------------------

class TestCreateStrategyVersion:
    def test_create_returns_201(self, client):
        sid = _new_strategy(client)["id"]
        resp = client.post(
            f"/api/strategies/{sid}/versions",
            json={"version_label": "v1.0.0"},
        )
        assert resp.status_code == 201

    def test_create_returns_expected_fields(self, client):
        sid = _new_strategy(client)["id"]
        resp = client.post(
            f"/api/strategies/{sid}/versions",
            json={
                "version_label": "v2.0-alpha",
                "git_commit": "abc123def456",
                "branch_name": "feature/ma-crossover",
                "code_path": "strategies/ma_crossover.py",
                "signal_name": "MA Crossover",
                "signal_description": "50/200 SMA crossover signal",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["version_label"] == "v2.0-alpha"
        assert data["git_commit"] == "abc123def456"
        assert data["branch_name"] == "feature/ma-crossover"
        assert data["code_path"] == "strategies/ma_crossover.py"
        assert data["signal_name"] == "MA Crossover"
        assert data["signal_description"] == "50/200 SMA crossover signal"
        assert data["strategy_id"] == sid
        assert "id" in data
        assert "created_at" in data
        assert "updated_at" in data
        assert data["config_snapshot_count"] == 0

    def test_create_optional_fields_null(self, client):
        sid = _new_strategy(client)["id"]
        data = _create_version(client, sid, "v-minimal")
        assert data["git_commit"] is None
        assert data["branch_name"] is None
        assert data["code_path"] is None
        assert data["signal_name"] is None
        assert data["signal_description"] is None

    def test_create_strategy_not_found_returns_404(self, client):
        fake_id = str(uuid.uuid4())
        resp = client.post(
            f"/api/strategies/{fake_id}/versions",
            json={"version_label": "v1.0"},
        )
        assert resp.status_code == 404

    def test_duplicate_label_within_same_strategy_returns_409(self, client):
        sid = _new_strategy(client)["id"]
        _create_version(client, sid, "v-duplicate")
        resp = client.post(
            f"/api/strategies/{sid}/versions",
            json={"version_label": "v-duplicate"},
        )
        assert resp.status_code == 409
        assert "v-duplicate" in resp.json()["detail"]

    def test_same_label_allowed_in_different_strategies(self, client):
        sid_a = _new_strategy(client)["id"]
        sid_b = _new_strategy(client)["id"]
        _create_version(client, sid_a, "v1.0")
        resp = client.post(
            f"/api/strategies/{sid_b}/versions",
            json={"version_label": "v1.0"},
        )
        assert resp.status_code == 201

    def test_version_label_required(self, client):
        sid = _new_strategy(client)["id"]
        resp = client.post(f"/api/strategies/{sid}/versions", json={})
        assert resp.status_code == 422

    def test_version_label_empty_string_rejected(self, client):
        sid = _new_strategy(client)["id"]
        resp = client.post(
            f"/api/strategies/{sid}/versions",
            json={"version_label": ""},
        )
        assert resp.status_code == 422

    def test_create_emits_timeline_event(self, client):
        sid = _new_strategy(client)["id"]
        _create_version(client, sid, "v-timeline-test")
        events = client.get(f"/api/strategies/{sid}/timeline").json()["items"]
        event_types = [e["event_type"] for e in events]
        assert "strategy_version_created" in event_types


# ---------------------------------------------------------------------------
# GET /api/strategies/{id}/versions
# ---------------------------------------------------------------------------

class TestListStrategyVersions:
    def test_list_empty_when_no_versions(self, client):
        sid = _new_strategy(client)["id"]
        resp = client.get(f"/api/strategies/{sid}/versions")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_returns_created_versions(self, client):
        sid = _new_strategy(client)["id"]
        _create_version(client, sid, "v1.0")
        _create_version(client, sid, "v2.0")
        data = client.get(f"/api/strategies/{sid}/versions").json()
        assert len(data) == 2
        labels = [v["version_label"] for v in data]
        assert "v1.0" in labels
        assert "v2.0" in labels

    def test_list_newest_first(self, client):
        sid = _new_strategy(client)["id"]
        _create_version(client, sid, "v-first")
        _create_version(client, sid, "v-second")
        _create_version(client, sid, "v-third")
        data = client.get(f"/api/strategies/{sid}/versions").json()
        # Newest first — "v-third" should appear before "v-first"
        assert data[0]["version_label"] == "v-third"
        assert data[-1]["version_label"] == "v-first"

    def test_list_includes_config_snapshot_count(self, client):
        sid = _new_strategy(client)["id"]
        ver = _create_version(client, sid, "v-counted")
        _create_snapshot(client, sid, "snap-A", strategy_version_id=ver["id"])
        _create_snapshot(client, sid, "snap-B", strategy_version_id=ver["id"])

        versions = client.get(f"/api/strategies/{sid}/versions").json()
        v = next(v for v in versions if v["version_label"] == "v-counted")
        assert v["config_snapshot_count"] == 2

    def test_list_strategy_not_found_returns_404(self, client):
        fake_id = str(uuid.uuid4())
        resp = client.get(f"/api/strategies/{fake_id}/versions")
        assert resp.status_code == 404

    def test_list_isolates_between_strategies(self, client):
        sid_a = _new_strategy(client)["id"]
        sid_b = _new_strategy(client)["id"]
        _create_version(client, sid_a, "v-only-in-a")
        data_b = client.get(f"/api/strategies/{sid_b}/versions").json()
        labels = [v["version_label"] for v in data_b]
        assert "v-only-in-a" not in labels


# ---------------------------------------------------------------------------
# POST /api/strategies/{id}/config-snapshots
# ---------------------------------------------------------------------------

class TestCreateConfigSnapshot:
    def test_create_returns_201(self, client):
        sid = _new_strategy(client)["id"]
        resp = client.post(
            f"/api/strategies/{sid}/config-snapshots",
            json={"label": "baseline-config", "config_json": {"mode": "live"}},
        )
        assert resp.status_code == 201

    def test_create_returns_expected_fields(self, client):
        sid = _new_strategy(client)["id"]
        resp = client.post(
            f"/api/strategies/{sid}/config-snapshots",
            json={
                "label": "full-config",
                "source_type": "file_upload",
                "source_filename": "config_v2.json",
                "config_json": {
                    "params": {"lookback": 20, "threshold": 0.5},
                    "assumptions": {"slippage": 0.001},
                    "universe": "SP500",
                },
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["strategy_id"] == sid
        assert data["label"] == "full-config"
        assert data["source_type"] == "file_upload"
        assert data["source_filename"] == "config_v2.json"
        assert data["param_count"] == 2
        assert data["assumption_count"] == 1
        assert len(data["config_hash"]) == 64  # SHA-256 hex
        assert "id" in data
        assert "created_at" in data
        # config_json should NOT appear in the summary response
        assert "config_json" not in data

    def test_config_hash_is_deterministic(self, client):
        """Same config in different key insertion order → same hash."""
        sid = _new_strategy(client)["id"]
        config_a = {"z_key": 1, "a_key": 2}
        config_b = {"a_key": 2, "z_key": 1}
        snap_a = _create_snapshot(client, sid, "hash-test-a", config_a)
        snap_b = _create_snapshot(client, sid, "hash-test-b", config_b)
        assert snap_a["config_hash"] == snap_b["config_hash"]

    def test_different_configs_produce_different_hash(self, client):
        sid = _new_strategy(client)["id"]
        snap_a = _create_snapshot(client, sid, "diff-a", {"lookback": 10})
        snap_b = _create_snapshot(client, sid, "diff-b", {"lookback": 20})
        assert snap_a["config_hash"] != snap_b["config_hash"]

    def test_param_count_zero_when_no_params_key(self, client):
        sid = _new_strategy(client)["id"]
        snap = _create_snapshot(client, sid, "no-params", {"mode": "test"})
        assert snap["param_count"] == 0
        assert snap["assumption_count"] == 0

    def test_param_count_zero_when_params_not_dict(self, client):
        sid = _new_strategy(client)["id"]
        snap = _create_snapshot(client, sid, "array-params", {"params": [1, 2, 3]})
        assert snap["param_count"] == 0

    def test_assumption_count_zero_when_assumptions_not_dict(self, client):
        sid = _new_strategy(client)["id"]
        snap = _create_snapshot(client, sid, "array-assumptions", {"assumptions": "string"})
        assert snap["assumption_count"] == 0

    def test_source_type_defaults_to_manual_json(self, client):
        sid = _new_strategy(client)["id"]
        snap = _create_snapshot(client, sid, "default-source")
        assert snap["source_type"] == "manual_json"

    def test_strategy_version_id_links_correctly(self, client):
        sid = _new_strategy(client)["id"]
        ver = _create_version(client, sid, "v-linked")
        snap = _create_snapshot(client, sid, "linked-snap", strategy_version_id=ver["id"])
        assert snap["strategy_version_id"] == ver["id"]

    def test_strategy_version_id_none_by_default(self, client):
        sid = _new_strategy(client)["id"]
        snap = _create_snapshot(client, sid, "no-version-link")
        assert snap["strategy_version_id"] is None

    def test_version_from_wrong_strategy_returns_404(self, client):
        sid_a = _new_strategy(client)["id"]
        sid_b = _new_strategy(client)["id"]
        ver_b = _create_version(client, sid_b, "v-b-version")
        resp = client.post(
            f"/api/strategies/{sid_a}/config-snapshots",
            json={
                "label": "bad-version-link",
                "config_json": {"x": 1},
                "strategy_version_id": ver_b["id"],
            },
        )
        assert resp.status_code == 404

    def test_strategy_not_found_returns_404(self, client):
        fake_id = str(uuid.uuid4())
        resp = client.post(
            f"/api/strategies/{fake_id}/config-snapshots",
            json={"label": "ghost-snap", "config_json": {"k": "v"}},
        )
        assert resp.status_code == 404

    def test_create_emits_timeline_event(self, client):
        sid = _new_strategy(client)["id"]
        _create_snapshot(client, sid, "timeline-snap")
        events = client.get(f"/api/strategies/{sid}/timeline").json()["items"]
        event_types = [e["event_type"] for e in events]
        assert "strategy_config_snapshot_logged" in event_types


# ---------------------------------------------------------------------------
# GET /api/strategies/{id}/config-snapshots
# ---------------------------------------------------------------------------

class TestListConfigSnapshots:
    def test_list_empty_when_no_snapshots(self, client):
        sid = _new_strategy(client)["id"]
        resp = client.get(f"/api/strategies/{sid}/config-snapshots")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_returns_created_snapshots(self, client):
        sid = _new_strategy(client)["id"]
        _create_snapshot(client, sid, "list-snap-1")
        _create_snapshot(client, sid, "list-snap-2")
        data = client.get(f"/api/strategies/{sid}/config-snapshots").json()
        assert len(data) == 2
        labels = {s["label"] for s in data}
        assert "list-snap-1" in labels
        assert "list-snap-2" in labels

    def test_list_newest_first(self, client):
        sid = _new_strategy(client)["id"]
        _create_snapshot(client, sid, "order-first")
        _create_snapshot(client, sid, "order-second")
        _create_snapshot(client, sid, "order-third")
        data = client.get(f"/api/strategies/{sid}/config-snapshots").json()
        assert data[0]["label"] == "order-third"
        assert data[-1]["label"] == "order-first"

    def test_list_no_config_json_in_response(self, client):
        sid = _new_strategy(client)["id"]
        _create_snapshot(client, sid, "no-blob-snap", {"secret": "hidden"})
        data = client.get(f"/api/strategies/{sid}/config-snapshots").json()
        for s in data:
            assert "config_json" not in s

    def test_list_filter_by_version_id(self, client):
        sid = _new_strategy(client)["id"]
        ver_a = _create_version(client, sid, "filter-v-a")
        ver_b = _create_version(client, sid, "filter-v-b")
        _create_snapshot(client, sid, "for-ver-a", strategy_version_id=ver_a["id"])
        _create_snapshot(client, sid, "for-ver-b", strategy_version_id=ver_b["id"])
        _create_snapshot(client, sid, "unlinked")

        data_a = client.get(
            f"/api/strategies/{sid}/config-snapshots",
            params={"version_id": ver_a["id"]},
        ).json()
        assert len(data_a) == 1
        assert data_a[0]["label"] == "for-ver-a"

        data_b = client.get(
            f"/api/strategies/{sid}/config-snapshots",
            params={"version_id": ver_b["id"]},
        ).json()
        assert len(data_b) == 1
        assert data_b[0]["label"] == "for-ver-b"

    def test_list_strategy_not_found_returns_404(self, client):
        resp = client.get(f"/api/strategies/{uuid.uuid4()}/config-snapshots")
        assert resp.status_code == 404

    def test_list_isolates_between_strategies(self, client):
        sid_a = _new_strategy(client)["id"]
        sid_b = _new_strategy(client)["id"]
        _create_snapshot(client, sid_a, "only-in-a")
        data_b = client.get(f"/api/strategies/{sid_b}/config-snapshots").json()
        assert all(s["label"] != "only-in-a" for s in data_b)


# ---------------------------------------------------------------------------
# GET /api/strategies/{id}/config-snapshots/compare
# ---------------------------------------------------------------------------

class TestCompareConfigSnapshots:
    def test_compare_identical_configs(self, client):
        sid = _new_strategy(client)["id"]
        config = {"params": {"lr": 0.01}, "assumptions": {"slippage": 0.001}}
        snap_a = _create_snapshot(client, sid, "cmp-same-a", config)
        snap_b = _create_snapshot(client, sid, "cmp-same-b", config)

        resp = client.get(
            f"/api/strategies/{sid}/config-snapshots/compare",
            params={"snapshot_a_id": snap_a["id"], "snapshot_b_id": snap_b["id"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_same_config"] is True
        assert data["total_changes"] == 0
        assert data["top_level"]["total_changes"] == 0
        assert data["params"]["total_changes"] == 0
        assert data["assumptions"]["total_changes"] == 0

    def test_compare_different_params(self, client):
        sid = _new_strategy(client)["id"]
        snap_a = _create_snapshot(client, sid, "diff-params-a", {
            "params": {"lookback": 10, "threshold": 0.5},
        })
        snap_b = _create_snapshot(client, sid, "diff-params-b", {
            "params": {"lookback": 20, "new_param": 99},
        })

        resp = client.get(
            f"/api/strategies/{sid}/config-snapshots/compare",
            params={"snapshot_a_id": snap_a["id"], "snapshot_b_id": snap_b["id"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_same_config"] is False
        # lookback changed, threshold removed, new_param added
        params_diff = data["params"]
        changed_keys = [c["key"] for c in params_diff["changed"]]
        removed_keys = [c["key"] for c in params_diff["removed"]]
        added_keys = [c["key"] for c in params_diff["added"]]
        assert "lookback" in changed_keys
        assert "threshold" in removed_keys
        assert "new_param" in added_keys

    def test_compare_returns_metadata(self, client):
        sid = _new_strategy(client)["id"]
        snap_a = _create_snapshot(client, sid, "meta-a", {"x": 1})
        snap_b = _create_snapshot(client, sid, "meta-b", {"x": 2})

        resp = client.get(
            f"/api/strategies/{sid}/config-snapshots/compare",
            params={"snapshot_a_id": snap_a["id"], "snapshot_b_id": snap_b["id"]},
        )
        data = resp.json()
        assert data["snapshot_a_id"] == snap_a["id"]
        assert data["snapshot_b_id"] == snap_b["id"]
        assert data["snapshot_a_label"] == "meta-a"
        assert data["snapshot_b_label"] == "meta-b"
        assert "highlighted_changes" in data

    def test_compare_snapshot_a_not_found(self, client):
        sid = _new_strategy(client)["id"]
        snap_b = _create_snapshot(client, sid, "real-snap")
        resp = client.get(
            f"/api/strategies/{sid}/config-snapshots/compare",
            params={"snapshot_a_id": str(uuid.uuid4()), "snapshot_b_id": snap_b["id"]},
        )
        assert resp.status_code == 404

    def test_compare_snapshot_b_not_found(self, client):
        sid = _new_strategy(client)["id"]
        snap_a = _create_snapshot(client, sid, "real-snap-a")
        resp = client.get(
            f"/api/strategies/{sid}/config-snapshots/compare",
            params={"snapshot_a_id": snap_a["id"], "snapshot_b_id": str(uuid.uuid4())},
        )
        assert resp.status_code == 404

    def test_compare_snapshot_from_wrong_strategy_returns_404(self, client):
        sid_a = _new_strategy(client)["id"]
        sid_b = _new_strategy(client)["id"]
        snap_a = _create_snapshot(client, sid_a, "cross-snap-a")
        snap_b = _create_snapshot(client, sid_b, "cross-snap-b")
        # Ask strategy A to compare a snapshot that belongs to strategy B
        resp = client.get(
            f"/api/strategies/{sid_a}/config-snapshots/compare",
            params={"snapshot_a_id": snap_a["id"], "snapshot_b_id": snap_b["id"]},
        )
        assert resp.status_code == 404

    def test_compare_strategy_not_found_returns_404(self, client):
        resp = client.get(
            f"/api/strategies/{uuid.uuid4()}/config-snapshots/compare",
            params={"snapshot_a_id": str(uuid.uuid4()), "snapshot_b_id": str(uuid.uuid4())},
        )
        assert resp.status_code == 404

    def test_compare_assumptions_diff(self, client):
        sid = _new_strategy(client)["id"]
        snap_a = _create_snapshot(client, sid, "assump-a", {
            "assumptions": {"slippage": 0.001, "commission": 5.0},
        })
        snap_b = _create_snapshot(client, sid, "assump-b", {
            "assumptions": {"slippage": 0.002},
        })
        resp = client.get(
            f"/api/strategies/{sid}/config-snapshots/compare",
            params={"snapshot_a_id": snap_a["id"], "snapshot_b_id": snap_b["id"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assump = data["assumptions"]
        changed_keys = [c["key"] for c in assump["changed"]]
        removed_keys = [c["key"] for c in assump["removed"]]
        assert "slippage" in changed_keys
        assert "commission" in removed_keys

    def test_compare_top_level_diff(self, client):
        sid = _new_strategy(client)["id"]
        snap_a = _create_snapshot(client, sid, "top-a", {"universe": "SP500", "mode": "live"})
        snap_b = _create_snapshot(client, sid, "top-b", {"universe": "NASDAQ", "extra_key": True})
        resp = client.get(
            f"/api/strategies/{sid}/config-snapshots/compare",
            params={"snapshot_a_id": snap_a["id"], "snapshot_b_id": snap_b["id"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        top = data["top_level"]
        changed_keys = [c["key"] for c in top["changed"]]
        removed_keys = [c["key"] for c in top["removed"]]
        added_keys = [c["key"] for c in top["added"]]
        assert "universe" in changed_keys
        assert "mode" in removed_keys
        assert "extra_key" in added_keys


# ---------------------------------------------------------------------------
# GET /api/config-snapshots/{snapshot_id}
# ---------------------------------------------------------------------------

class TestGetConfigSnapshotDetail:
    def test_get_returns_200(self, client):
        sid = _new_strategy(client)["id"]
        snap = _create_snapshot(client, sid, "detail-snap")
        resp = client.get(f"/api/config-snapshots/{snap['id']}")
        assert resp.status_code == 200

    def test_get_includes_config_json(self, client):
        sid = _new_strategy(client)["id"]
        config = {"params": {"alpha": 0.1}, "universe": "NASDAQ"}
        snap = _create_snapshot(client, sid, "detail-with-json", config)
        resp = client.get(f"/api/config-snapshots/{snap['id']}")
        assert resp.status_code == 200
        data = resp.json()
        assert "config_json" in data
        assert data["config_json"] == config

    def test_get_includes_all_fields(self, client):
        sid = _new_strategy(client)["id"]
        snap = _create_snapshot(
            client,
            sid,
            "all-fields-snap",
            {"k": "v"},
            source_type="file_upload",
            source_filename="params.json",
        )
        resp = client.get(f"/api/config-snapshots/{snap['id']}")
        data = resp.json()
        assert data["id"] == snap["id"]
        assert data["strategy_id"] == sid
        assert data["label"] == "all-fields-snap"
        assert data["source_type"] == "file_upload"
        assert data["source_filename"] == "params.json"
        assert data["config_hash"] == snap["config_hash"]
        assert data["param_count"] == snap["param_count"]
        assert data["assumption_count"] == snap["assumption_count"]

    def test_get_not_found_returns_404(self, client):
        resp = client.get(f"/api/config-snapshots/{uuid.uuid4()}")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/strategies/{id} — enriched with M15 data
# ---------------------------------------------------------------------------

class TestStrategyDetailM15:
    def test_detail_includes_config_snapshots_field(self, client):
        sid = _new_strategy(client)["id"]
        resp = client.get(f"/api/strategies/{sid}")
        assert resp.status_code == 200
        data = resp.json()
        assert "config_snapshots" in data
        assert isinstance(data["config_snapshots"], list)

    def test_detail_config_snapshots_populated(self, client):
        sid = _new_strategy(client)["id"]
        _create_snapshot(client, sid, "detail-snap-1")
        _create_snapshot(client, sid, "detail-snap-2")
        data = client.get(f"/api/strategies/{sid}").json()
        labels = {s["label"] for s in data["config_snapshots"]}
        assert "detail-snap-1" in labels
        assert "detail-snap-2" in labels

    def test_detail_config_snapshots_no_config_json_blob(self, client):
        sid = _new_strategy(client)["id"]
        _create_snapshot(client, sid, "no-blob-detail", {"secret": "hidden"})
        data = client.get(f"/api/strategies/{sid}").json()
        for s in data["config_snapshots"]:
            assert "config_json" not in s

    def test_detail_versions_include_config_snapshot_count(self, client):
        sid = _new_strategy(client)["id"]
        ver = _create_version(client, sid, "counted-version")
        _create_snapshot(client, sid, "count-snap-1", strategy_version_id=ver["id"])
        _create_snapshot(client, sid, "count-snap-2", strategy_version_id=ver["id"])

        data = client.get(f"/api/strategies/{sid}").json()
        versions = data["versions"]
        v = next(v for v in versions if v["version_label"] == "counted-version")
        assert v["config_snapshot_count"] == 2

    def test_detail_versions_newest_first(self, client):
        sid = _new_strategy(client)["id"]
        _create_version(client, sid, "v-first-detail")
        _create_version(client, sid, "v-last-detail")
        data = client.get(f"/api/strategies/{sid}").json()
        version_labels = [v["version_label"] for v in data["versions"]]
        assert version_labels.index("v-last-detail") < version_labels.index("v-first-detail")
