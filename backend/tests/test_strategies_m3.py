"""M3 strategy creation and enriched list/detail tests.

Tests cover:
- POST /api/strategies: success, slug generation, duplicate 409, missing project 404,
  invalid asset_class 422
- GET /api/strategies: returns StrategyListItemOut shape (project_name, run_count,
  latest_run_at)
- GET /api/strategies/{id}: returns StrategyDetailOut shape (project_name, run_count,
  versions, runs)
- GET /api/strategies/{id}: 404 on unknown ID
"""

from __future__ import annotations

import uuid

import pytest


class TestCreateStrategy:
    def test_create_returns_201(self, client):
        projects = client.get("/api/projects").json()
        project_id = projects[0]["id"]

        resp = client.post(
            "/api/strategies",
            json={
                "project_id": project_id,
                "name": "M3 Test Strategy",
                "description": "Created by M3 tests",
                "asset_class": "equity",
                "status": "active",
            },
        )
        assert resp.status_code == 201

    def test_create_returns_expected_fields(self, client):
        projects = client.get("/api/projects").json()
        project_id = projects[0]["id"]

        resp = client.post(
            "/api/strategies",
            json={
                "project_id": project_id,
                "name": "Field Check Strategy",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Field Check Strategy"
        assert data["slug"] == "field-check-strategy"
        assert data["asset_class"] == "equity"
        assert data["status"] == "active"
        assert data["run_count"] == 0
        assert data["latest_run_at"] is None
        assert "project_name" in data
        assert "id" in data

    def test_slug_auto_generated_from_name(self, client):
        projects = client.get("/api/projects").json()
        project_id = projects[0]["id"]

        resp = client.post(
            "/api/strategies",
            json={"project_id": project_id, "name": "Auto Slug Generation Test!"},
        )
        assert resp.status_code == 201
        assert resp.json()["slug"] == "auto-slug-generation-test"

    def test_explicit_slug_used_when_provided(self, client):
        projects = client.get("/api/projects").json()
        project_id = projects[0]["id"]

        resp = client.post(
            "/api/strategies",
            json={
                "project_id": project_id,
                "name": "Explicit Slug Strategy",
                "slug": "my-custom-slug",
            },
        )
        assert resp.status_code == 201
        assert resp.json()["slug"] == "my-custom-slug"

    def test_duplicate_slug_returns_409(self, client):
        projects = client.get("/api/projects").json()
        project_id = projects[0]["id"]

        payload = {"project_id": project_id, "name": "Duplicate Slug Test", "slug": "dup-slug-409"}
        client.post("/api/strategies", json=payload)
        resp = client.post("/api/strategies", json=payload)
        assert resp.status_code == 409

    def test_missing_project_returns_404(self, client):
        resp = client.post(
            "/api/strategies",
            json={"project_id": str(uuid.uuid4()), "name": "Orphan Strategy"},
        )
        assert resp.status_code == 404

    def test_invalid_asset_class_returns_422(self, client):
        projects = client.get("/api/projects").json()
        project_id = projects[0]["id"]

        resp = client.post(
            "/api/strategies",
            json={
                "project_id": project_id,
                "name": "Bad Asset Class",
                "asset_class": "spaceship",
            },
        )
        assert resp.status_code == 422

    def test_invalid_status_returns_422(self, client):
        projects = client.get("/api/projects").json()
        project_id = projects[0]["id"]

        resp = client.post(
            "/api/strategies",
            json={
                "project_id": project_id,
                "name": "Bad Status Strategy",
                "status": "invented",
            },
        )
        assert resp.status_code == 422


class TestStrategyListEnriched:
    def test_list_has_project_name(self, client):
        data = client.get("/api/strategies").json()
        assert len(data) >= 1
        for item in data:
            assert "project_name" in item
            assert isinstance(item["project_name"], str)
            assert len(item["project_name"]) > 0

    def test_list_has_run_count(self, client):
        data = client.get("/api/strategies").json()
        for item in data:
            assert "run_count" in item
            assert isinstance(item["run_count"], int)
            assert item["run_count"] >= 0

    def test_seed_strategy_run_count_is_correct(self, client):
        data = client.get("/api/strategies").json()
        seed = next(s for s in data if s["slug"] == "aapl-mean-reversion-v1")
        assert seed["run_count"] == 1

    def test_list_has_latest_run_at(self, client):
        data = client.get("/api/strategies").json()
        seed = next(s for s in data if s["slug"] == "aapl-mean-reversion-v1")
        assert seed["latest_run_at"] is not None

    def test_newly_created_strategy_appears_in_list(self, client):
        projects = client.get("/api/projects").json()
        project_id = projects[0]["id"]

        resp = client.post(
            "/api/strategies",
            json={"project_id": project_id, "name": "List Visibility Check"},
        )
        assert resp.status_code == 201
        new_id = resp.json()["id"]

        strategies = client.get("/api/strategies").json()
        ids = [s["id"] for s in strategies]
        assert new_id in ids


class TestStrategyDetailEnriched:
    def test_detail_has_project_name(self, client):
        strategies = client.get("/api/strategies").json()
        sid = strategies[0]["id"]
        detail = client.get(f"/api/strategies/{sid}").json()
        assert "project_name" in detail
        assert isinstance(detail["project_name"], str)

    def test_detail_has_run_count(self, client):
        strategies = client.get("/api/strategies").json()
        seed = next(s for s in strategies if s["slug"] == "aapl-mean-reversion-v1")
        detail = client.get(f"/api/strategies/{seed['id']}").json()
        assert detail["run_count"] == 1

    def test_detail_has_latest_run_at(self, client):
        strategies = client.get("/api/strategies").json()
        seed = next(s for s in strategies if s["slug"] == "aapl-mean-reversion-v1")
        detail = client.get(f"/api/strategies/{seed['id']}").json()
        assert detail["latest_run_at"] is not None

    def test_detail_has_versions(self, client):
        strategies = client.get("/api/strategies").json()
        seed = next(s for s in strategies if s["slug"] == "aapl-mean-reversion-v1")
        detail = client.get(f"/api/strategies/{seed['id']}").json()
        assert "versions" in detail
        assert len(detail["versions"]) >= 1

    def test_detail_has_runs(self, client):
        strategies = client.get("/api/strategies").json()
        seed = next(s for s in strategies if s["slug"] == "aapl-mean-reversion-v1")
        detail = client.get(f"/api/strategies/{seed['id']}").json()
        assert "runs" in detail
        assert len(detail["runs"]) >= 1

    def test_detail_not_found(self, client):
        resp = client.get(f"/api/strategies/{uuid.uuid4()}")
        assert resp.status_code == 404
