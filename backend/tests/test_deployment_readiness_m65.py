"""M65 tests: Deployment Readiness Checklist.

Tests for:
  - GET /api/admin/deployment-readiness
  - DeploymentReadinessResponse structure and fields
  - Category presence (7 categories)
  - Readiness score range (0-100)
  - Overall status values
  - Manual checks not counted as failures
  - Read-only behaviour (no timeline events created)
"""
from __future__ import annotations

import pytest

from app.models.audit_timeline_event import AuditTimelineEvent
from app.services.deployment_readiness import (
    get_deployment_readiness,
    _check_repo_hygiene,
    _check_backend_readiness,
    _check_frontend_readiness,
    _check_sdk_ci_readiness,
    _check_database_demo_readiness,
    _check_security_config_readiness,
    _check_deployment_blockers,
)

# ---------------------------------------------------------------------------
# Expected category keys
# ---------------------------------------------------------------------------

EXPECTED_CATEGORY_KEYS = {
    "repo_hygiene",
    "backend",
    "frontend",
    "sdk_ci",
    "database_demo",
    "security_config",
    "deployment_blockers",
}

VALID_OVERALL_STATUSES = {
    "local_demo_ready",
    "deployment_prep_ready",
    "needs_review",
    "blocked",
}

FORBIDDEN_SUMMARY_TERMS = ["AI", "certified", "guaranteed", "deployed"]


# ---------------------------------------------------------------------------
# Endpoint tests
# ---------------------------------------------------------------------------


class TestDeploymentReadinessEndpoint:
    def test_endpoint_returns_200(self, client):
        """GET /api/admin/deployment-readiness returns HTTP 200."""
        response = client.get("/api/admin/deployment-readiness")
        assert response.status_code == 200

    def test_response_has_all_categories(self, client):
        """Response body contains all 7 expected category keys."""
        response = client.get("/api/admin/deployment-readiness")
        assert response.status_code == 200
        data = response.json()
        category_keys = {cat["category_key"] for cat in data["categories"]}
        assert EXPECTED_CATEGORY_KEYS == category_keys

    def test_readiness_score_range(self, client):
        """readiness_score is in [0, 100]."""
        response = client.get("/api/admin/deployment-readiness")
        assert response.status_code == 200
        score = response.json()["readiness_score"]
        assert 0.0 <= score <= 100.0

    def test_overall_status_present(self, client):
        """overall_status is one of the four valid values."""
        response = client.get("/api/admin/deployment-readiness")
        assert response.status_code == 200
        status = response.json()["overall_status"]
        assert status in VALID_OVERALL_STATUSES


# ---------------------------------------------------------------------------
# Category-level tests
# ---------------------------------------------------------------------------


class TestDeploymentReadinessCategories:
    def _get_categories(self, client) -> dict:
        response = client.get("/api/admin/deployment-readiness")
        assert response.status_code == 200
        return {cat["category_key"]: cat for cat in response.json()["categories"]}

    def test_repo_hygiene_checks_present(self, client):
        """repo_hygiene category has at least one check."""
        categories = self._get_categories(client)
        assert "repo_hygiene" in categories
        assert len(categories["repo_hygiene"]["checks"]) > 0

    def test_backend_readiness_checks_present(self, client):
        """backend category has at least one check."""
        categories = self._get_categories(client)
        assert "backend" in categories
        assert len(categories["backend"]["checks"]) > 0

    def test_frontend_readiness_checks_present(self, client):
        """frontend category has at least one check."""
        categories = self._get_categories(client)
        assert "frontend" in categories
        assert len(categories["frontend"]["checks"]) > 0

    def test_sdk_ci_checks_present(self, client):
        """sdk_ci category has at least one check."""
        categories = self._get_categories(client)
        assert "sdk_ci" in categories
        assert len(categories["sdk_ci"]["checks"]) > 0

    def test_database_demo_checks_present(self, client):
        """database_demo category has at least one check."""
        categories = self._get_categories(client)
        assert "database_demo" in categories
        assert len(categories["database_demo"]["checks"]) > 0

    def test_security_config_checks_present(self, client):
        """security_config category has at least one check."""
        categories = self._get_categories(client)
        assert "security_config" in categories
        assert len(categories["security_config"]["checks"]) > 0

    def test_deployment_blockers_checks_present(self, client):
        """deployment_blockers category has at least one check."""
        categories = self._get_categories(client)
        assert "deployment_blockers" in categories
        assert len(categories["deployment_blockers"]["checks"]) > 0


# ---------------------------------------------------------------------------
# Content and behaviour tests
# ---------------------------------------------------------------------------


class TestDeploymentReadinessContent:
    def test_blockers_list_present(self, client):
        """blockers field is a list (may be empty if no critical/high fails)."""
        response = client.get("/api/admin/deployment-readiness")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["blockers"], list)

    def test_suggested_next_steps_present(self, client):
        """suggested_next_steps is a non-empty list."""
        response = client.get("/api/admin/deployment-readiness")
        assert response.status_code == 200
        data = response.json()
        # In a real project there will always be at least manual deployment items
        assert isinstance(data["suggested_next_steps"], list)
        assert len(data["suggested_next_steps"]) > 0

    def test_summary_avoids_forbidden_language(self, client):
        """deterministic_summary does not contain forbidden marketing/certainty terms."""
        response = client.get("/api/admin/deployment-readiness")
        assert response.status_code == 200
        summary = response.json()["deterministic_summary"]
        for term in FORBIDDEN_SUMMARY_TERMS:
            assert term not in summary, (
                f"deterministic_summary contains forbidden term '{term}': {summary!r}"
            )

    def test_manual_checks_are_not_fails(self, client):
        """Checks with status='manual' must not appear as fails or inflate fail_count."""
        response = client.get("/api/admin/deployment-readiness")
        assert response.status_code == 200
        data = response.json()

        # Recompute fail_count from raw checks and compare with reported value
        raw_fail_count = 0
        raw_manual_count = 0
        for cat in data["categories"]:
            for check in cat["checks"]:
                if check["status"] == "fail":
                    raw_fail_count += 1
                elif check["status"] == "manual":
                    raw_manual_count += 1

        assert data["fail_count"] == raw_fail_count, (
            f"Reported fail_count {data['fail_count']} != raw count {raw_fail_count}"
        )
        assert data["manual_count"] == raw_manual_count, (
            f"Reported manual_count {data['manual_count']} != raw count {raw_manual_count}"
        )
        # Manual checks must never be status=fail
        for cat in data["categories"]:
            for check in cat["checks"]:
                assert not (check["status"] == "fail" and check.get("suggested_action") == "__manual__"), (
                    f"Check {check['check_key']} should not be 'fail' for a manual item."
                )

    def test_no_timeline_event_created(self, db):
        """get_deployment_readiness is read-only — no AuditTimelineEvent rows are created."""
        before_count = db.query(AuditTimelineEvent).count()
        get_deployment_readiness(db)
        after_count = db.query(AuditTimelineEvent).count()
        assert after_count == before_count, (
            f"Expected no new timeline events, but count went from {before_count} to {after_count}."
        )


# ---------------------------------------------------------------------------
# Service-level unit tests
# ---------------------------------------------------------------------------


class TestDeploymentReadinessService:
    def test_service_returns_all_categories(self, db):
        """get_deployment_readiness returns 7 categories."""
        result = get_deployment_readiness(db)
        keys = {cat.category_key for cat in result.categories}
        assert keys == EXPECTED_CATEGORY_KEYS

    def test_score_is_float_in_range(self, db):
        """readiness_score is a float between 0 and 100."""
        result = get_deployment_readiness(db)
        assert isinstance(result.readiness_score, float)
        assert 0.0 <= result.readiness_score <= 100.0

    def test_counts_sum_correctly(self, db):
        """Pass + warning + fail + manual counts add up to total check count."""
        result = get_deployment_readiness(db)
        total_checks = sum(
            len(cat.checks) for cat in result.categories
        )
        count_sum = (
            result.pass_count
            + result.warning_count
            + result.fail_count
            + result.manual_count
        )
        assert count_sum == total_checks, (
            f"Count sum {count_sum} != total checks {total_checks}"
        )

    def test_category_counts_consistent(self, db):
        """Each category's pass/warning/fail/manual counts match its checks list."""
        result = get_deployment_readiness(db)
        for cat in result.categories:
            expected_pass = sum(1 for c in cat.checks if c.status == "pass")
            expected_warn = sum(1 for c in cat.checks if c.status == "warning")
            expected_fail = sum(1 for c in cat.checks if c.status == "fail")
            expected_manual = sum(1 for c in cat.checks if c.status == "manual")
            assert cat.pass_count == expected_pass, f"{cat.category_key} pass_count mismatch"
            assert cat.warning_count == expected_warn, f"{cat.category_key} warning_count mismatch"
            assert cat.fail_count == expected_fail, f"{cat.category_key} fail_count mismatch"
            assert cat.manual_count == expected_manual, f"{cat.category_key} manual_count mismatch"

    def test_deployment_blockers_all_manual(self, db):
        """All checks in deployment_blockers category are status='manual'."""
        result = get_deployment_readiness(db)
        blockers_cat = next(
            (cat for cat in result.categories if cat.category_key == "deployment_blockers"),
            None,
        )
        assert blockers_cat is not None
        for check in blockers_cat.checks:
            assert check.status == "manual", (
                f"deployment_blockers check '{check.check_key}' has status '{check.status}', expected 'manual'."
            )

    def test_category_repo_hygiene_has_gitignore_check(self, db):
        """repo_hygiene category contains a check for .gitignore."""
        cat = _check_repo_hygiene()
        check_keys = {c.check_key for c in cat.checks}
        assert "gitignore_exists" in check_keys

    def test_category_backend_has_main_check(self, db):
        """backend category includes check for backend/app/main.py."""
        cat = _check_backend_readiness()
        check_keys = {c.check_key for c in cat.checks}
        assert "backend_main_exists" in check_keys

    def test_security_config_has_critical_backend_env_check(self, db):
        """security_config includes a critical-severity check for backend/.env not committed."""
        cat = _check_security_config_readiness()
        critical_checks = [
            c for c in cat.checks
            if c.check_key == "sec_backend_env_not_committed"
        ]
        assert len(critical_checks) == 1
        assert critical_checks[0].severity == "critical"

    def test_generated_at_is_utc(self, db):
        """generated_at has timezone info (UTC)."""
        result = get_deployment_readiness(db)
        assert result.generated_at.tzinfo is not None

    def test_deterministic_summary_contains_score(self, db):
        """deterministic_summary mentions the numeric score."""
        result = get_deployment_readiness(db)
        assert str(int(result.readiness_score)) in result.deterministic_summary

    def test_check_severities_are_valid(self, db):
        """All check severities are one of the known valid values."""
        valid_severities = {"info", "low", "medium", "high", "critical"}
        result = get_deployment_readiness(db)
        for cat in result.categories:
            for check in cat.checks:
                assert check.severity in valid_severities, (
                    f"Check '{check.check_key}' has unknown severity '{check.severity}'."
                )

    def test_check_statuses_are_valid(self, db):
        """All check statuses are one of the known valid values."""
        valid_statuses = {"pass", "warning", "fail", "manual", "not_applicable"}
        result = get_deployment_readiness(db)
        for cat in result.categories:
            for check in cat.checks:
                assert check.status in valid_statuses, (
                    f"Check '{check.check_key}' has unknown status '{check.status}'."
                )
