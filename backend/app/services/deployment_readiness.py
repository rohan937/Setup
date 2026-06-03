"""M65 Deployment Readiness Checklist — read-only service.

Inspects the repository structure, configuration, and environment to produce
a structured checklist that helps operators confirm the project is ready for
local demo, staging, or production deployment.

No database writes occur. The ``db`` session argument is accepted for
interface consistency (and may be used for future live checks).
"""

from __future__ import annotations

import os
import glob
from datetime import datetime, timezone
from dataclasses import dataclass, field
from sqlalchemy.orm import Session

# ---------------------------------------------------------------------------
# Optional service availability probes
# ---------------------------------------------------------------------------

try:
    from app.services.system_health import get_system_health  # noqa: F401
    SYSTEM_HEALTH_AVAILABLE = True
except Exception:
    SYSTEM_HEALTH_AVAILABLE = False

try:
    from app.services.demo_seed import get_demo_status  # noqa: F401
    DEMO_SEED_AVAILABLE = True
except Exception:
    DEMO_SEED_AVAILABLE = False

# ---------------------------------------------------------------------------
# Path constants — resolve project root from this file's location
# ---------------------------------------------------------------------------

# This file lives at backend/app/services/deployment_readiness.py
# __file__ -> .../QuantFidelity/backend/app/services/deployment_readiness.py
# dirname x4 -> .../QuantFidelity/
BASE_DIR = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
BACKEND_DIR = os.path.join(BASE_DIR, "backend")
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
SDK_DIR = os.path.join(BASE_DIR, "sdk")
DOCS_DIR = os.path.join(BASE_DIR, "docs")
SCRIPTS_DIR = os.path.join(BASE_DIR, "scripts")
GITHUB_DIR = os.path.join(BASE_DIR, ".github")


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class ReadinessCheckData:
    check_key: str
    title: str
    category: str
    status: str  # pass/warning/fail/manual/not_applicable
    severity: str  # info/low/medium/high/critical
    observed_value: str | None = None
    expected_value: str | None = None
    explanation: str = ""
    suggested_action: str | None = None


@dataclass
class ReadinessCategoryData:
    category_key: str
    title: str
    status: str  # pass/warning/fail/manual
    pass_count: int = 0
    warning_count: int = 0
    fail_count: int = 0
    manual_count: int = 0
    checks: list = field(default_factory=list)


@dataclass
class DeploymentReadinessData:
    generated_at: datetime
    overall_status: str  # local_demo_ready/deployment_prep_ready/needs_review/blocked
    readiness_score: float
    pass_count: int
    warning_count: int
    fail_count: int
    manual_count: int
    blocker_count: int
    categories: list
    blockers: list  # str
    warnings: list  # str
    suggested_next_steps: list  # str
    deterministic_summary: str


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _file_exists(path: str) -> bool:
    return os.path.exists(path)


def _check(
    check_key: str,
    title: str,
    category: str,
    condition: bool,
    severity: str = "medium",
    pass_explanation: str = "",
    fail_explanation: str = "",
    observed: str | None = None,
    expected: str | None = None,
    suggested_action: str | None = None,
) -> ReadinessCheckData:
    if condition:
        return ReadinessCheckData(
            check_key=check_key,
            title=title,
            category=category,
            status="pass",
            severity=severity,
            observed_value=observed,
            expected_value=expected,
            explanation=pass_explanation,
            suggested_action=None,
        )
    return ReadinessCheckData(
        check_key=check_key,
        title=title,
        category=category,
        status="fail",
        severity=severity,
        observed_value=observed,
        expected_value=expected,
        explanation=fail_explanation,
        suggested_action=suggested_action,
    )


def _manual(
    check_key: str,
    title: str,
    category: str,
    explanation: str,
    severity: str = "medium",
) -> ReadinessCheckData:
    return ReadinessCheckData(
        check_key=check_key,
        title=title,
        category=category,
        status="manual",
        severity=severity,
        explanation=explanation,
    )


def _warn(
    check_key: str,
    title: str,
    category: str,
    explanation: str,
    severity: str = "low",
    observed: str | None = None,
    suggested_action: str | None = None,
) -> ReadinessCheckData:
    return ReadinessCheckData(
        check_key=check_key,
        title=title,
        category=category,
        status="warning",
        severity=severity,
        observed_value=observed,
        explanation=explanation,
        suggested_action=suggested_action,
    )


def _build_category(
    category_key: str,
    title: str,
    checks: list[ReadinessCheckData],
) -> ReadinessCategoryData:
    pass_count = sum(1 for c in checks if c.status == "pass")
    warning_count = sum(1 for c in checks if c.status == "warning")
    fail_count = sum(1 for c in checks if c.status == "fail")
    manual_count = sum(1 for c in checks if c.status == "manual")
    status = _compute_category_status_from_checks(checks)
    return ReadinessCategoryData(
        category_key=category_key,
        title=title,
        status=status,
        pass_count=pass_count,
        warning_count=warning_count,
        fail_count=fail_count,
        manual_count=manual_count,
        checks=checks,
    )


def _compute_category_status_from_checks(checks: list[ReadinessCheckData]) -> str:
    for c in checks:
        if c.status == "fail" and c.severity in ("critical", "high"):
            return "fail"
    for c in checks:
        if c.status == "fail":
            return "warning"
    for c in checks:
        if c.status == "warning":
            return "warning"
    for c in checks:
        if c.status == "manual":
            return "warning"
    return "pass"


# ---------------------------------------------------------------------------
# Category checkers
# ---------------------------------------------------------------------------


def _check_repo_hygiene() -> ReadinessCategoryData:
    checks: list[ReadinessCheckData] = []

    checks.append(_check(
        "gitignore_exists", ".gitignore exists", "repo_hygiene",
        _file_exists(os.path.join(BASE_DIR, ".gitignore")),
        severity="high",
        pass_explanation=".gitignore is present.",
        fail_explanation=".gitignore is missing — secrets and build artefacts may be committed.",
        suggested_action="Add a .gitignore that excludes .env, *.db, node_modules, dist/, __pycache__/.",
    ))

    checks.append(_check(
        "readme_exists", "README.md exists", "repo_hygiene",
        _file_exists(os.path.join(BASE_DIR, "README.md")),
        severity="medium",
        pass_explanation="README.md is present.",
        fail_explanation="README.md is missing — operators have no onboarding guide.",
        suggested_action="Add a README.md with setup and run instructions.",
    ))

    checks.append(_check(
        "product_spec_exists", "ProductSpec.txt exists", "repo_hygiene",
        _file_exists(os.path.join(BASE_DIR, "ProductSpec.txt")),
        severity="low",
        pass_explanation="ProductSpec.txt is present.",
        fail_explanation="ProductSpec.txt is missing.",
    ))

    checks.append(_check(
        "architecture_txt_exists", "Architecture.txt exists", "repo_hygiene",
        _file_exists(os.path.join(BASE_DIR, "Architecture.txt")),
        severity="low",
        pass_explanation="Architecture.txt is present.",
        fail_explanation="Architecture.txt is missing.",
    ))

    checks.append(_check(
        "docs_demo_walkthrough_exists", "docs/demo-walkthrough.md exists", "repo_hygiene",
        _file_exists(os.path.join(DOCS_DIR, "demo-walkthrough.md")),
        severity="medium",
        pass_explanation="Demo walkthrough doc is present.",
        fail_explanation="docs/demo-walkthrough.md is missing.",
        suggested_action="Create docs/demo-walkthrough.md with step-by-step demo instructions.",
    ))

    checks.append(_check(
        "docs_ci_ingestion_exists", "docs/ci-ingestion.md exists", "repo_hygiene",
        _file_exists(os.path.join(DOCS_DIR, "ci-ingestion.md")),
        severity="medium",
        pass_explanation="CI ingestion guide is present.",
        fail_explanation="docs/ci-ingestion.md is missing.",
        suggested_action="Create docs/ci-ingestion.md documenting the CI evidence ingestion workflow.",
    ))

    # .env files must NOT be committed
    root_env = os.path.join(BASE_DIR, ".env")
    if _file_exists(root_env):
        checks.append(_warn(
            "root_env_not_committed", ".env not committed", "repo_hygiene",
            "A .env file was found at the project root. Verify it is excluded by .gitignore "
            "and not tracked by git.",
            severity="high",
            observed=".env file found",
            suggested_action="Run `git rm --cached .env` if it has been accidentally staged.",
        ))
    else:
        checks.append(_check(
            "root_env_not_committed", ".env not committed", "repo_hygiene",
            True,
            severity="high",
            pass_explanation="No .env at project root — not committed.",
        ))

    backend_env = os.path.join(BACKEND_DIR, ".env")
    if _file_exists(backend_env):
        checks.append(_warn(
            "backend_env_not_committed", "backend/.env not committed", "repo_hygiene",
            "A backend/.env file was found. Verify it is excluded by .gitignore.",
            severity="high",
            observed="backend/.env file found",
            suggested_action="Ensure backend/.env is in .gitignore and not git-tracked.",
        ))
    else:
        checks.append(_check(
            "backend_env_not_committed", "backend/.env not committed", "repo_hygiene",
            True,
            severity="high",
            pass_explanation="No backend/.env — not committed.",
        ))

    frontend_env = os.path.join(FRONTEND_DIR, ".env")
    if _file_exists(frontend_env):
        checks.append(_warn(
            "frontend_env_not_committed", "frontend/.env not committed", "repo_hygiene",
            "A frontend/.env file was found. Verify it is excluded by .gitignore.",
            severity="medium",
            observed="frontend/.env file found",
            suggested_action="Ensure frontend/.env is in .gitignore.",
        ))
    else:
        checks.append(_check(
            "frontend_env_not_committed", "frontend/.env not committed", "repo_hygiene",
            True,
            severity="medium",
            pass_explanation="No frontend/.env — not committed.",
        ))

    checks.append(_check(
        "backend_env_example_exists", "backend/.env.example exists", "repo_hygiene",
        _file_exists(os.path.join(BACKEND_DIR, ".env.example")),
        severity="medium",
        pass_explanation="backend/.env.example is present — operators can use it as a template.",
        fail_explanation="backend/.env.example is missing — operators have no env var reference.",
        suggested_action="Create backend/.env.example documenting all QF_ environment variables.",
    ))

    checks.append(_check(
        "makefile_exists", "Makefile exists", "repo_hygiene",
        _file_exists(os.path.join(BASE_DIR, "Makefile")),
        severity="low",
        pass_explanation="Makefile is present.",
        fail_explanation="Makefile is missing — common tasks are not scripted.",
    ))

    checks.append(_check(
        "scripts_dir_exists", "scripts/ directory exists", "repo_hygiene",
        _file_exists(SCRIPTS_DIR),
        severity="low",
        pass_explanation="scripts/ directory is present.",
        fail_explanation="scripts/ directory is missing.",
    ))

    checks.append(_check(
        "github_workflows_dir_exists", ".github/workflows/ directory exists", "repo_hygiene",
        _file_exists(os.path.join(GITHUB_DIR, "workflows")),
        severity="low",
        pass_explanation=".github/workflows/ directory is present.",
        fail_explanation=".github/workflows/ directory is missing — no GitHub Actions workflows.",
    ))

    return _build_category("repo_hygiene", "Repository Hygiene", checks)


def _check_backend_readiness() -> ReadinessCategoryData:
    checks: list[ReadinessCheckData] = []

    checks.append(_check(
        "backend_main_exists", "backend/app/main.py exists", "backend",
        _file_exists(os.path.join(BACKEND_DIR, "app", "main.py")),
        severity="high",
        pass_explanation="FastAPI application entrypoint is present.",
        fail_explanation="backend/app/main.py is missing.",
    ))

    checks.append(_check(
        "backend_config_exists", "backend/app/core/config.py exists", "backend",
        _file_exists(os.path.join(BACKEND_DIR, "app", "core", "config.py")),
        severity="high",
        pass_explanation="Settings/config module is present.",
        fail_explanation="backend/app/core/config.py is missing.",
    ))

    checks.append(_check(
        "backend_router_exists", "backend/app/api/router.py exists", "backend",
        _file_exists(os.path.join(BACKEND_DIR, "app", "api", "router.py")),
        severity="high",
        pass_explanation="API router is present.",
        fail_explanation="backend/app/api/router.py is missing.",
    ))

    has_requirements = _file_exists(
        os.path.join(BACKEND_DIR, "requirements.txt")
    ) or _file_exists(os.path.join(BACKEND_DIR, "pyproject.toml"))
    checks.append(_check(
        "backend_deps_file_exists",
        "backend/requirements.txt or pyproject.toml exists",
        "backend",
        has_requirements,
        severity="high",
        pass_explanation="Python dependency manifest is present.",
        fail_explanation="Neither requirements.txt nor pyproject.toml found in backend/.",
        suggested_action="Add requirements.txt or pyproject.toml to backend/.",
    ))

    checks.append(_check(
        "migrations_dir_exists", "backend/migrations/ exists", "backend",
        _file_exists(os.path.join(BACKEND_DIR, "migrations")),
        severity="high",
        pass_explanation="Alembic migrations directory is present.",
        fail_explanation="backend/migrations/ is missing.",
    ))

    migrations_versions_dir = os.path.join(BACKEND_DIR, "migrations", "versions")
    checks.append(_check(
        "migrations_versions_dir_exists", "backend/migrations/versions/ exists", "backend",
        _file_exists(migrations_versions_dir),
        severity="high",
        pass_explanation="migrations/versions/ directory exists.",
        fail_explanation="backend/migrations/versions/ is missing.",
    ))

    migration_files = glob.glob(os.path.join(migrations_versions_dir, "*.py")) if _file_exists(migrations_versions_dir) else []
    checks.append(_check(
        "migration_files_exist", "Migration version files exist", "backend",
        len(migration_files) > 0,
        severity="high",
        observed=f"{len(migration_files)} migration file(s) found",
        pass_explanation=f"{len(migration_files)} migration file(s) found in migrations/versions/.",
        fail_explanation="No migration files found in migrations/versions/.",
        suggested_action="Run `alembic revision --autogenerate` to create initial migration.",
    ))

    checks.append(_check(
        "admin_routes_exist", "backend/app/api/routes/admin.py exists", "backend",
        _file_exists(os.path.join(BACKEND_DIR, "app", "api", "routes", "admin.py")),
        severity="medium",
        pass_explanation="Admin routes file is present.",
        fail_explanation="backend/app/api/routes/admin.py is missing.",
    ))

    checks.append(_check(
        "demo_seed_service_exists", "backend/app/services/demo_seed.py exists", "backend",
        _file_exists(os.path.join(BACKEND_DIR, "app", "services", "demo_seed.py")),
        severity="medium",
        pass_explanation="Demo seed service is present.",
        fail_explanation="backend/app/services/demo_seed.py is missing.",
    ))

    checks.append(_check(
        "system_health_service_exists", "backend/app/services/system_health.py exists", "backend",
        _file_exists(os.path.join(BACKEND_DIR, "app", "services", "system_health.py")),
        severity="medium",
        pass_explanation="System health service is present.",
        fail_explanation="backend/app/services/system_health.py is missing.",
    ))

    checks.append(_check(
        "reliability_snapshot_service_exists",
        "backend/app/services/reliability_snapshots.py exists",
        "backend",
        _file_exists(os.path.join(BACKEND_DIR, "app", "services", "reliability_snapshots.py")),
        severity="low",
        pass_explanation="Reliability snapshot service is present.",
        fail_explanation="backend/app/services/reliability_snapshots.py is missing.",
    ))

    # This file itself — trivially passes after M65 is written
    checks.append(_check(
        "deployment_readiness_service_exists",
        "backend/app/services/deployment_readiness.py exists",
        "backend",
        _file_exists(os.path.join(BACKEND_DIR, "app", "services", "deployment_readiness.py")),
        severity="low",
        pass_explanation="Deployment readiness service (M65) is present.",
        fail_explanation="backend/app/services/deployment_readiness.py is missing.",
    ))

    checks.append(_check(
        "api_key_service_exists", "backend/app/services/api_keys.py exists", "backend",
        _file_exists(os.path.join(BACKEND_DIR, "app", "services", "api_keys.py")),
        severity="medium",
        pass_explanation="API key service is present.",
        fail_explanation="backend/app/services/api_keys.py is missing.",
    ))

    checks.append(_check(
        "backend_tests_dir_exists", "backend/tests/ directory exists", "backend",
        _file_exists(os.path.join(BACKEND_DIR, "tests")),
        severity="medium",
        pass_explanation="Backend tests directory is present.",
        fail_explanation="backend/tests/ is missing — no automated test coverage.",
        suggested_action="Add backend/tests/ with pytest test files.",
    ))

    checks.append(_check(
        "health_route_exists", "backend/app/api/routes/health.py exists", "backend",
        _file_exists(os.path.join(BACKEND_DIR, "app", "api", "routes", "health.py")),
        severity="medium",
        pass_explanation="Health check route is present.",
        fail_explanation="backend/app/api/routes/health.py is missing.",
    ))

    return _build_category("backend", "Backend Readiness", checks)


def _check_frontend_readiness() -> ReadinessCategoryData:
    checks: list[ReadinessCheckData] = []

    checks.append(_check(
        "frontend_package_json_exists", "frontend/package.json exists", "frontend",
        _file_exists(os.path.join(FRONTEND_DIR, "package.json")),
        severity="high",
        pass_explanation="Frontend package.json is present.",
        fail_explanation="frontend/package.json is missing.",
    ))

    checks.append(_check(
        "frontend_vite_config_exists", "frontend/vite.config.ts exists", "frontend",
        _file_exists(os.path.join(FRONTEND_DIR, "vite.config.ts")),
        severity="high",
        pass_explanation="Vite config is present.",
        fail_explanation="frontend/vite.config.ts is missing.",
    ))

    checks.append(_check(
        "frontend_api_lib_exists", "frontend/src/lib/api.ts exists", "frontend",
        _file_exists(os.path.join(FRONTEND_DIR, "src", "lib", "api.ts")),
        severity="high",
        pass_explanation="Frontend API client is present.",
        fail_explanation="frontend/src/lib/api.ts is missing.",
    ))

    checks.append(_check(
        "frontend_app_tsx_exists", "frontend/src/App.tsx exists", "frontend",
        _file_exists(os.path.join(FRONTEND_DIR, "src", "App.tsx")),
        severity="high",
        pass_explanation="Root App component is present.",
        fail_explanation="frontend/src/App.tsx is missing.",
    ))

    checks.append(_check(
        "frontend_dashboard_page_exists", "frontend/src/pages/Dashboard.tsx exists", "frontend",
        _file_exists(os.path.join(FRONTEND_DIR, "src", "pages", "Dashboard.tsx")),
        severity="medium",
        pass_explanation="Dashboard page component is present.",
        fail_explanation="frontend/src/pages/Dashboard.tsx is missing.",
    ))

    checks.append(_check(
        "frontend_admin_system_health_page_exists",
        "frontend/src/pages/AdminSystemHealth.tsx exists",
        "frontend",
        _file_exists(os.path.join(FRONTEND_DIR, "src", "pages", "AdminSystemHealth.tsx")),
        severity="medium",
        pass_explanation="Admin system health page is present.",
        fail_explanation="frontend/src/pages/AdminSystemHealth.tsx is missing.",
    ))

    checks.append(_check(
        "frontend_deployment_readiness_page_exists",
        "frontend/src/pages/DeploymentReadiness.tsx exists",
        "frontend",
        _file_exists(os.path.join(FRONTEND_DIR, "src", "pages", "DeploymentReadiness.tsx")),
        severity="low",
        pass_explanation="Deployment readiness page (M65 frontend) is present.",
        fail_explanation="frontend/src/pages/DeploymentReadiness.tsx not yet created (expected after M65 frontend).",
        suggested_action="Create the DeploymentReadiness.tsx frontend page as part of M65 frontend work.",
    ))

    frontend_dist = os.path.join(FRONTEND_DIR, "dist")
    if _file_exists(frontend_dist):
        checks.append(_warn(
            "frontend_dist_not_committed",
            "frontend/dist should not be committed",
            "frontend",
            "frontend/dist/ exists on disk. Verify it is excluded by .gitignore and not tracked by git.",
            severity="medium",
            observed="frontend/dist found",
            suggested_action="Add frontend/dist to .gitignore if not already present, and run `git rm -r --cached frontend/dist`.",
        ))
    else:
        checks.append(_check(
            "frontend_dist_not_committed",
            "frontend/dist not present (not committed)",
            "frontend",
            True,
            severity="medium",
            pass_explanation="frontend/dist is not present — build artefacts are not committed.",
        ))

    checks.append(_check(
        "frontend_nav_lib_exists", "frontend/src/lib/nav.ts exists", "frontend",
        _file_exists(os.path.join(FRONTEND_DIR, "src", "lib", "nav.ts")),
        severity="low",
        pass_explanation="Navigation utility is present.",
        fail_explanation="frontend/src/lib/nav.ts is missing.",
    ))

    return _build_category("frontend", "Frontend Readiness", checks)


def _check_sdk_ci_readiness() -> ReadinessCategoryData:
    checks: list[ReadinessCheckData] = []

    checks.append(_check(
        "sdk_python_dir_exists", "sdk/python/ exists", "sdk_ci",
        _file_exists(os.path.join(SDK_DIR, "python")),
        severity="medium",
        pass_explanation="sdk/python directory is present.",
        fail_explanation="sdk/python/ is missing.",
    ))

    checks.append(_check(
        "sdk_python_pyproject_exists", "sdk/python/pyproject.toml exists", "sdk_ci",
        _file_exists(os.path.join(SDK_DIR, "python", "pyproject.toml")),
        severity="medium",
        pass_explanation="SDK pyproject.toml is present.",
        fail_explanation="sdk/python/pyproject.toml is missing.",
    ))

    checks.append(_check(
        "sdk_cli_exists", "sdk/python/quantfidelity/cli.py exists", "sdk_ci",
        _file_exists(os.path.join(SDK_DIR, "python", "quantfidelity", "cli.py")),
        severity="medium",
        pass_explanation="SDK CLI entry point is present.",
        fail_explanation="sdk/python/quantfidelity/cli.py is missing.",
    ))

    checks.append(_check(
        "sdk_readme_exists", "sdk/python/README.md exists", "sdk_ci",
        _file_exists(os.path.join(SDK_DIR, "python", "README.md")),
        severity="low",
        pass_explanation="SDK README is present.",
        fail_explanation="sdk/python/README.md is missing.",
    ))

    checks.append(_check(
        "sdk_tests_dir_exists", "sdk/python/tests/ exists", "sdk_ci",
        _file_exists(os.path.join(SDK_DIR, "python", "tests")),
        severity="medium",
        pass_explanation="SDK tests directory is present.",
        fail_explanation="sdk/python/tests/ is missing.",
    ))

    checks.append(_check(
        "docs_ci_ingestion_exists_sdk", "docs/ci-ingestion.md exists", "sdk_ci",
        _file_exists(os.path.join(DOCS_DIR, "ci-ingestion.md")),
        severity="medium",
        pass_explanation="CI ingestion guide is present.",
        fail_explanation="docs/ci-ingestion.md is missing.",
    ))

    checks.append(_check(
        "github_ingest_example_exists",
        ".github/workflows/quantfidelity-ingest.example.yml exists",
        "sdk_ci",
        _file_exists(os.path.join(GITHUB_DIR, "workflows", "quantfidelity-ingest.example.yml")),
        severity="low",
        pass_explanation="Example ingestion workflow is present.",
        fail_explanation=".github/workflows/quantfidelity-ingest.example.yml is missing.",
    ))

    checks.append(_check(
        "script_ingest_bundle_exists", "scripts/ingest_evidence_bundle.sh exists", "sdk_ci",
        _file_exists(os.path.join(SCRIPTS_DIR, "ingest_evidence_bundle.sh")),
        severity="low",
        pass_explanation="Evidence bundle ingestion script is present.",
        fail_explanation="scripts/ingest_evidence_bundle.sh is missing.",
    ))

    checks.append(_check(
        "script_flush_buffer_exists", "scripts/flush_qf_buffer.sh exists", "sdk_ci",
        _file_exists(os.path.join(SCRIPTS_DIR, "flush_qf_buffer.sh")),
        severity="low",
        pass_explanation="Flush buffer script is present.",
        fail_explanation="scripts/flush_qf_buffer.sh is missing.",
    ))

    checks.append(_check(
        "sdk_example_bundle_exists", "sdk/python/examples/bundle.json exists", "sdk_ci",
        _file_exists(os.path.join(SDK_DIR, "python", "examples", "bundle.json")),
        severity="low",
        pass_explanation="SDK example bundle.json is present.",
        fail_explanation="sdk/python/examples/bundle.json is missing.",
    ))

    checks.append(_check(
        "sdk_ci_bundle_exists", "sdk/python/examples/ci_bundle.json exists", "sdk_ci",
        _file_exists(os.path.join(SDK_DIR, "python", "examples", "ci_bundle.json")),
        severity="low",
        pass_explanation="SDK example ci_bundle.json is present.",
        fail_explanation="sdk/python/examples/ci_bundle.json is missing.",
    ))

    return _build_category("sdk_ci", "SDK & CI Readiness", checks)


def _check_database_demo_readiness() -> ReadinessCategoryData:
    checks: list[ReadinessCheckData] = []

    migrations_versions_dir = os.path.join(BACKEND_DIR, "migrations", "versions")
    migration_files = glob.glob(os.path.join(migrations_versions_dir, "*.py")) if _file_exists(migrations_versions_dir) else []
    checks.append(_check(
        "db_migrations_present", "migrations/versions/ has migration files", "database_demo",
        len(migration_files) > 0,
        severity="high",
        observed=f"{len(migration_files)} file(s)",
        pass_explanation=f"{len(migration_files)} migration file(s) found.",
        fail_explanation="No migration files found in migrations/versions/.",
        suggested_action="Run `alembic revision --autogenerate -m 'initial'` to create migration.",
    ))

    m0001_files = [f for f in migration_files if os.path.basename(f).startswith("0001")]
    checks.append(_check(
        "db_migration_0001_exists", "Initial migration (0001) exists", "database_demo",
        len(m0001_files) > 0,
        severity="high",
        observed=os.path.basename(m0001_files[0]) if m0001_files else "not found",
        pass_explanation="Initial migration 0001 is present.",
        fail_explanation="Initial migration file starting with '0001' not found.",
    ))

    checks.append(_check(
        "demo_seed_available", "Demo seed service importable", "database_demo",
        DEMO_SEED_AVAILABLE,
        severity="medium",
        pass_explanation="Demo seed service imported successfully.",
        fail_explanation="Demo seed service failed to import.",
    ))

    checks.append(_check(
        "system_health_available", "System health service importable", "database_demo",
        SYSTEM_HEALTH_AVAILABLE,
        severity="medium",
        pass_explanation="System health service imported successfully.",
        fail_explanation="System health service failed to import.",
    ))

    # Reliability snapshot migration (0023 or m65a)
    reliability_snap_migration = [
        f for f in migration_files
        if "0023" in os.path.basename(f) or "m65a" in os.path.basename(f).lower()
    ]
    checks.append(_check(
        "reliability_snapshot_migration_exists",
        "Reliability snapshot migration (0023/m65a) exists",
        "database_demo",
        len(reliability_snap_migration) > 0,
        severity="low",
        observed=os.path.basename(reliability_snap_migration[0]) if reliability_snap_migration else "not found",
        pass_explanation="Reliability snapshot migration is present.",
        fail_explanation="Reliability snapshot migration (0023/m65a) not found.",
    ))

    checks.append(_manual(
        "manual_alembic_upgrade_head",
        "Confirm alembic upgrade head works in target DB",
        "database_demo",
        "Manually run `alembic upgrade head` against the target database and confirm it succeeds "
        "with no errors before deploying.",
        severity="high",
    ))

    checks.append(_manual(
        "manual_demo_seed_runs",
        "Confirm demo seed runs successfully",
        "database_demo",
        "Manually run POST /api/admin/seed-demo and verify the response shows expected record counts.",
        severity="medium",
    ))

    return _build_category("database_demo", "Database & Demo Readiness", checks)


def _check_security_config_readiness() -> ReadinessCategoryData:
    checks: list[ReadinessCheckData] = []

    env_example_path = os.path.join(BACKEND_DIR, ".env.example")

    checks.append(_check(
        "sec_env_example_exists", "backend/.env.example exists", "security_config",
        _file_exists(env_example_path),
        severity="high",
        pass_explanation="backend/.env.example documents all required env vars.",
        fail_explanation="backend/.env.example is missing — no env var documentation for operators.",
        suggested_action="Create backend/.env.example with all QF_ variables and safe defaults.",
    ))

    checks.append(_check(
        "sec_api_key_service_exists", "API key service exists", "security_config",
        _file_exists(os.path.join(BACKEND_DIR, "app", "services", "api_keys.py")),
        severity="medium",
        pass_explanation="API key service is present.",
        fail_explanation="backend/app/services/api_keys.py is missing.",
    ))

    # Check .env.example for required variable documentation
    env_example_content = ""
    if _file_exists(env_example_path):
        try:
            with open(env_example_path, "r") as fh:
                env_example_content = fh.read()
        except Exception:
            env_example_content = ""

    api_key_var_documented = "QF_REQUIRE_API_KEY_FOR_INGESTION" in env_example_content
    checks.append(_check(
        "api_key_ingestion_documented",
        "QF_REQUIRE_API_KEY_FOR_INGESTION documented in .env.example",
        "security_config",
        api_key_var_documented,
        severity="medium",
        pass_explanation="QF_REQUIRE_API_KEY_FOR_INGESTION is documented in .env.example.",
        fail_explanation="QF_REQUIRE_API_KEY_FOR_INGESTION not found in backend/.env.example.",
        suggested_action="Add QF_REQUIRE_API_KEY_FOR_INGESTION=false to backend/.env.example with a comment.",
    ))

    # backend/.env must not exist (critical — secrets check)
    backend_env_path = os.path.join(BACKEND_DIR, ".env")
    backend_env_absent = not _file_exists(backend_env_path)
    checks.append(_check(
        "sec_backend_env_not_committed",
        "backend/.env not committed (secrets check)",
        "security_config",
        backend_env_absent,
        severity="critical",
        pass_explanation="backend/.env is not present — secrets are not at risk of being committed.",
        fail_explanation="backend/.env exists. Verify it is gitignored and not tracked by git.",
        suggested_action="Run `git rm --cached backend/.env` if accidentally tracked.",
    ))

    database_url_documented = "DATABASE_URL" in env_example_content
    checks.append(_check(
        "database_url_documented",
        "DATABASE_URL documented in backend/.env.example",
        "security_config",
        database_url_documented,
        severity="medium",
        pass_explanation="DATABASE_URL is referenced in .env.example.",
        fail_explanation="DATABASE_URL not found in backend/.env.example.",
        suggested_action="Add QF_DATABASE_URL to backend/.env.example with the SQLite default.",
    ))

    checks.append(_manual(
        "manual_prod_database_url",
        "Set production DATABASE_URL in Render/Railway environment",
        "security_config",
        "Configure QF_DATABASE_URL in the production platform environment (Render, Railway, etc.) "
        "pointing to a production-grade database. Never commit this value.",
        severity="critical",
    ))

    checks.append(_manual(
        "manual_cors_origins_prod",
        "Configure CORS_ORIGINS for production domain",
        "security_config",
        "Set QF_CORS_ORIGINS to your actual production frontend URL (e.g. https://app.yourco.com) "
        "before going live. The current default allows localhost only.",
        severity="high",
    ))

    checks.append(_manual(
        "manual_api_key_enforcement",
        "Enable QF_REQUIRE_API_KEY_FOR_INGESTION=true in production",
        "security_config",
        "Set QF_REQUIRE_API_KEY_FOR_INGESTION=true in production to gate all evidence ingestion "
        "behind valid API keys.",
        severity="high",
    ))

    checks.append(_manual(
        "manual_rotate_demo_api_keys",
        "Rotate any local/demo API keys before production",
        "security_config",
        "Any API keys created during local development or demo seeding should be revoked and "
        "replaced with fresh production keys before public launch.",
        severity="medium",
    ))

    checks.append(_manual(
        "manual_no_secrets_in_history",
        "Verify no real secrets are committed to git history",
        "security_config",
        "Run `git log --all --full-history -- '*.env'` and a secrets scanner (e.g. trufflehog) "
        "to confirm no credentials are present in git history.",
        severity="critical",
    ))

    return _build_category("security_config", "Security & Configuration", checks)


def _check_render_deployment_prep() -> ReadinessCategoryData:
    """M70: checks for Render + PostgreSQL deployment readiness artifacts."""
    checks: list[ReadinessCheckData] = []

    # Migrate script
    migrate_sh = os.path.join(SCRIPTS_DIR, "backend_migrate.sh")
    migrate_exists = _file_exists(migrate_sh)
    checks.append(_check(
        "backend_migrate_sh_exists",
        "scripts/backend_migrate.sh exists",
        "render_deployment",
        migrate_exists,
        severity="high",
        pass_explanation="Migration script present — use as Render pre-deploy command.",
        fail_explanation="scripts/backend_migrate.sh is missing.",
        suggested_action="Create scripts/backend_migrate.sh that runs `alembic upgrade head`.",
    ))
    if migrate_exists:
        executable = os.access(migrate_sh, os.X_OK)
        checks.append(_check(
            "backend_migrate_sh_executable",
            "scripts/backend_migrate.sh is executable",
            "render_deployment",
            executable,
            severity="medium",
            pass_explanation="Migration script is executable.",
            fail_explanation="scripts/backend_migrate.sh is not executable.",
            suggested_action="Run: chmod +x scripts/backend_migrate.sh",
        ))

    # Start script
    start_sh = os.path.join(SCRIPTS_DIR, "backend_start.sh")
    start_exists = _file_exists(start_sh)
    checks.append(_check(
        "backend_start_sh_exists",
        "scripts/backend_start.sh exists",
        "render_deployment",
        start_exists,
        severity="high",
        pass_explanation="Start script present — use as Render start command.",
        fail_explanation="scripts/backend_start.sh is missing.",
        suggested_action="Create scripts/backend_start.sh that runs uvicorn.",
    ))
    if start_exists:
        executable = os.access(start_sh, os.X_OK)
        checks.append(_check(
            "backend_start_sh_executable",
            "scripts/backend_start.sh is executable",
            "render_deployment",
            executable,
            severity="medium",
            pass_explanation="Start script is executable.",
            fail_explanation="scripts/backend_start.sh is not executable.",
            suggested_action="Run: chmod +x scripts/backend_start.sh",
        ))

    # Render docs
    render_docs = os.path.join(DOCS_DIR, "render-backend.md")
    checks.append(_check(
        "render_backend_docs_exist",
        "docs/render-backend.md exists",
        "render_deployment",
        _file_exists(render_docs),
        severity="medium",
        pass_explanation="Render deployment guide is present.",
        fail_explanation="docs/render-backend.md is missing.",
        suggested_action="Create docs/render-backend.md with Render deployment instructions.",
    ))

    # render.yaml.example
    render_yaml = os.path.join(BASE_DIR, "render.yaml.example")
    checks.append(_check(
        "render_yaml_example_exists",
        "render.yaml.example exists",
        "render_deployment",
        _file_exists(render_yaml),
        severity="low",
        pass_explanation="render.yaml.example is present.",
        fail_explanation="render.yaml.example is missing (optional but helpful).",
        suggested_action="Create render.yaml.example with placeholder Render blueprint config.",
    ))

    # PostgreSQL driver documented / present in requirements
    requirements_path = os.path.join(BACKEND_DIR, "requirements.txt")
    req_content = ""
    if _file_exists(requirements_path):
        try:
            with open(requirements_path) as fh:
                req_content = fh.read()
        except Exception:
            req_content = ""
    psycopg_present = "psycopg2" in req_content or "psycopg" in req_content
    checks.append(_check(
        "psycopg2_in_requirements",
        "psycopg2 (PostgreSQL driver) in requirements.txt",
        "render_deployment",
        psycopg_present,
        severity="high",
        pass_explanation="PostgreSQL driver (psycopg2) is listed in requirements.txt.",
        fail_explanation="psycopg2-binary is not in requirements.txt — PostgreSQL connections will fail.",
        suggested_action="Add psycopg2-binary>=2.9.0 to backend/requirements.txt.",
    ))

    # Deployment health endpoint (GET /api/health/deployment)
    health_route = os.path.join(BACKEND_DIR, "app", "api", "routes", "health.py")
    health_content = ""
    if _file_exists(health_route):
        try:
            with open(health_route) as fh:
                health_content = fh.read()
        except Exception:
            health_content = ""
    deployment_health_endpoint = "health/deployment" in health_content
    checks.append(_check(
        "deployment_health_endpoint_exists",
        "GET /api/health/deployment endpoint exists",
        "render_deployment",
        deployment_health_endpoint,
        severity="medium",
        pass_explanation="Deployment health endpoint is present.",
        fail_explanation="Deployment health endpoint (GET /api/health/deployment) not found in health routes.",
        suggested_action="Add the /api/health/deployment endpoint to backend/app/api/routes/health.py.",
    ))

    # postgres:// URL normalization documented in config or env example
    env_example_path = os.path.join(BACKEND_DIR, ".env.example")
    env_example_content = ""
    if _file_exists(env_example_path):
        try:
            with open(env_example_path) as fh:
                env_example_content = fh.read()
        except Exception:
            env_example_content = ""
    postgres_url_documented = "postgres://" in env_example_content or "postgresql" in env_example_content
    checks.append(_check(
        "postgres_url_documented",
        "PostgreSQL URL format documented in .env.example",
        "render_deployment",
        postgres_url_documented,
        severity="medium",
        pass_explanation="PostgreSQL URL format is documented in .env.example.",
        fail_explanation="PostgreSQL URL format not found in backend/.env.example.",
        suggested_action="Add a PostgreSQL URL example to backend/.env.example.",
    ))

    # JWT secret safety note documented
    jwt_documented = "QF_JWT_SECRET_KEY" in env_example_content
    checks.append(_check(
        "jwt_secret_documented",
        "QF_JWT_SECRET_KEY documented in .env.example",
        "render_deployment",
        jwt_documented,
        severity="medium",
        pass_explanation="QF_JWT_SECRET_KEY is documented in .env.example.",
        fail_explanation="QF_JWT_SECRET_KEY not found in backend/.env.example.",
        suggested_action="Document QF_JWT_SECRET_KEY in backend/.env.example with a security note.",
    ))

    return _build_category("render_deployment", "Render / PostgreSQL Deployment Prep (M70)", checks)


def _check_deployment_blockers() -> ReadinessCategoryData:
    checks: list[ReadinessCheckData] = []

    checks.append(_manual(
        "blocker_prod_db_not_configured",
        "Production DATABASE_URL not configured yet",
        "deployment_blockers",
        "A production database has not been provisioned or connected. This must be done before "
        "any production deployment.",
        severity="high",
    ))

    checks.append(_manual(
        "blocker_render_service_not_created",
        "Render service not created yet",
        "deployment_blockers",
        "The backend Render (or equivalent PaaS) service has not been created. Create the service "
        "and configure environment variables before deploying.",
        severity="high",
    ))

    checks.append(_manual(
        "blocker_vercel_project_not_created",
        "Vercel project not created yet",
        "deployment_blockers",
        "The frontend Vercel (or equivalent) project has not been created. Set up the project and "
        "link it to the repository before deploying.",
        severity="medium",
    ))

    checks.append(_manual(
        "blocker_prod_cors_not_set",
        "Production CORS allowlist not set yet",
        "deployment_blockers",
        "QF_CORS_ORIGINS has not been configured for the production frontend URL.",
        severity="high",
    ))

    checks.append(_manual(
        "blocker_api_key_enforcement_not_tested",
        "Production API key enforcement not tested in production env",
        "deployment_blockers",
        "QF_REQUIRE_API_KEY_FOR_INGESTION enforcement has only been tested locally. Verify it "
        "works correctly in the production environment.",
        severity="medium",
    ))

    checks.append(_manual(
        "blocker_prod_demo_seed_not_validated",
        "Production demo seed not validated",
        "deployment_blockers",
        "POST /api/admin/seed-demo has not been run and validated against the production database.",
        severity="medium",
    ))

    checks.append(_manual(
        "blocker_prod_migrations_not_run",
        "Production migrations not run",
        "deployment_blockers",
        "`alembic upgrade head` has not been run against the production database. Run it as part "
        "of the deployment pipeline before starting the server.",
        severity="high",
    ))

    checks.append(_manual(
        "blocker_domain_not_configured",
        "Domain not configured",
        "deployment_blockers",
        "A custom domain has not been pointed at the production deployment.",
        severity="medium",
    ))

    checks.append(_manual(
        "blocker_https_not_validated",
        "HTTPS not validated",
        "deployment_blockers",
        "TLS/HTTPS for the production deployment has not been validated end-to-end.",
        severity="medium",
    ))

    checks.append(_manual(
        "blocker_public_demo_qa_not_completed",
        "Public demo QA not completed",
        "deployment_blockers",
        "The full public demo walkthrough has not been completed against the production environment.",
        severity="medium",
    ))

    checks.append(_manual(
        "blocker_m71_frontend_deployment_prep",
        "M71 Frontend deployment prep: Vercel project not created yet",
        "deployment_blockers",
        "M71 (Frontend Deployment Prep) covers Vercel project setup, environment variables, "
        "and connecting the frontend to the production backend URL.",
        severity="medium",
    ))

    checks.append(_manual(
        "blocker_prod_jwt_secret_not_set",
        "Production QF_JWT_SECRET_KEY not set to a strong secret",
        "deployment_blockers",
        "Set QF_JWT_SECRET_KEY to a long random secret on Render before serving real users. "
        "Generate with: python3 -c \"import secrets; print(secrets.token_hex(32))\"",
        severity="critical",
    ))

    return _build_category("deployment_blockers", "Deployment Blockers", checks)


def _check_frontend_vercel_deployment() -> ReadinessCategoryData:
    """M71: checks for Vercel frontend deployment readiness artifacts."""
    checks: list[ReadinessCheckData] = []

    # frontend/.env.example
    fe_env_example = os.path.join(FRONTEND_DIR, ".env.example")
    fe_env_content = ""
    fe_env_exists = _file_exists(fe_env_example)
    checks.append(_check(
        "frontend_env_example_exists",
        "frontend/.env.example exists",
        "frontend_vercel_deployment",
        fe_env_exists,
        severity="high",
        pass_explanation="frontend/.env.example documents required VITE_ env vars.",
        fail_explanation="frontend/.env.example is missing.",
        suggested_action="Create frontend/.env.example documenting VITE_API_BASE_URL.",
    ))
    if fe_env_exists:
        try:
            with open(fe_env_example) as fh:
                fe_env_content = fh.read()
        except Exception:
            fe_env_content = ""

    vite_api_url_documented = "VITE_API_BASE_URL" in fe_env_content
    checks.append(_check(
        "vite_api_base_url_documented",
        "VITE_API_BASE_URL documented in frontend/.env.example",
        "frontend_vercel_deployment",
        vite_api_url_documented,
        severity="high",
        pass_explanation="VITE_API_BASE_URL is documented in frontend/.env.example.",
        fail_explanation="VITE_API_BASE_URL not found in frontend/.env.example.",
        suggested_action="Add VITE_API_BASE_URL=http://localhost:8000 to frontend/.env.example.",
    ))

    # frontend/vercel.json
    vercel_json = os.path.join(FRONTEND_DIR, "vercel.json")
    vercel_json_exists = _file_exists(vercel_json)
    checks.append(_check(
        "frontend_vercel_json_exists",
        "frontend/vercel.json exists",
        "frontend_vercel_deployment",
        vercel_json_exists,
        severity="high",
        pass_explanation="frontend/vercel.json present — SPA routing configured.",
        fail_explanation="frontend/vercel.json is missing — deep-link refreshes will 404 on Vercel.",
        suggested_action="Create frontend/vercel.json with SPA rewrite to /index.html.",
    ))
    if vercel_json_exists:
        try:
            with open(vercel_json) as fh:
                vercel_json_content = fh.read()
        except Exception:
            vercel_json_content = ""
        has_rewrite = "index.html" in vercel_json_content
        checks.append(_check(
            "frontend_vercel_json_has_rewrite",
            "frontend/vercel.json contains SPA rewrite to /index.html",
            "frontend_vercel_deployment",
            has_rewrite,
            severity="high",
            pass_explanation="vercel.json rewrites all paths to /index.html.",
            fail_explanation="vercel.json does not contain a rewrite to /index.html.",
            suggested_action='Add {"rewrites": [{"source": "/(.*)", "destination": "/index.html"}]} to vercel.json.',
        ))

    # docs/vercel-frontend.md
    vercel_docs = os.path.join(DOCS_DIR, "vercel-frontend.md")
    checks.append(_check(
        "vercel_frontend_docs_exist",
        "docs/vercel-frontend.md exists",
        "frontend_vercel_deployment",
        _file_exists(vercel_docs),
        severity="medium",
        pass_explanation="Vercel deployment guide is present.",
        fail_explanation="docs/vercel-frontend.md is missing.",
        suggested_action="Create docs/vercel-frontend.md with Vercel deployment instructions.",
    ))

    # scripts/frontend_build.sh
    build_sh = os.path.join(SCRIPTS_DIR, "frontend_build.sh")
    build_exists = _file_exists(build_sh)
    checks.append(_check(
        "frontend_build_sh_exists",
        "scripts/frontend_build.sh exists",
        "frontend_vercel_deployment",
        build_exists,
        severity="medium",
        pass_explanation="Frontend build script is present.",
        fail_explanation="scripts/frontend_build.sh is missing.",
        suggested_action="Create scripts/frontend_build.sh that runs npm run typecheck && npm run build.",
    ))
    if build_exists:
        executable = os.access(build_sh, os.X_OK)
        checks.append(_check(
            "frontend_build_sh_executable",
            "scripts/frontend_build.sh is executable",
            "frontend_vercel_deployment",
            executable,
            severity="low",
            pass_explanation="Frontend build script is executable.",
            fail_explanation="scripts/frontend_build.sh is not executable.",
            suggested_action="Run: chmod +x scripts/frontend_build.sh",
        ))

    # api.ts uses VITE_API_BASE_URL
    api_ts_path = os.path.join(FRONTEND_DIR, "src", "lib", "api.ts")
    api_ts_content = ""
    if _file_exists(api_ts_path):
        try:
            with open(api_ts_path) as fh:
                api_ts_content = fh.read()
        except Exception:
            api_ts_content = ""
    api_uses_vite_env = "VITE_API_BASE_URL" in api_ts_content
    checks.append(_check(
        "api_ts_uses_vite_api_base_url",
        "frontend/src/lib/api.ts uses VITE_API_BASE_URL",
        "frontend_vercel_deployment",
        api_uses_vite_env,
        severity="high",
        pass_explanation="API client reads backend URL from VITE_API_BASE_URL.",
        fail_explanation="api.ts does not reference VITE_API_BASE_URL — hardcoded localhost will break production.",
        suggested_action="Update api.ts to use import.meta.env.VITE_API_BASE_URL.",
    ))

    # No hardcoded non-fallback localhost in api.ts
    # We allow the fallback default but not a standalone hardcoded URL
    has_getApiBaseUrl = "getApiBaseUrl" in api_ts_content
    checks.append(_check(
        "api_ts_has_get_api_base_url_helper",
        "frontend/src/lib/api.ts exports getApiBaseUrl helper",
        "frontend_vercel_deployment",
        has_getApiBaseUrl,
        severity="low",
        pass_explanation="getApiBaseUrl() helper is exported from api.ts.",
        fail_explanation="getApiBaseUrl() helper not found in api.ts.",
        suggested_action="Export getApiBaseUrl() from api.ts for environment URL introspection.",
    ))

    # frontend/.env.local must not exist (secrets check)
    fe_env_local = os.path.join(FRONTEND_DIR, ".env.local")
    fe_env_local_absent = not _file_exists(fe_env_local)
    checks.append(_check(
        "frontend_env_local_not_committed",
        "frontend/.env.local not present (not committed)",
        "frontend_vercel_deployment",
        fe_env_local_absent,
        severity="high",
        pass_explanation="frontend/.env.local is not present — local secrets not at risk of being committed.",
        fail_explanation="frontend/.env.local exists. Verify it is gitignored and not git-tracked.",
        suggested_action="Ensure frontend/.env.local is in .gitignore and not tracked by git.",
    ))

    # Vercel deployment manual checklist
    checks.append(_manual(
        "manual_vercel_project_not_created",
        "Vercel project not created yet",
        "frontend_vercel_deployment",
        "Create a Vercel project connected to the repository and set VITE_API_BASE_URL "
        "to the Render backend URL. See docs/vercel-frontend.md.",
        severity="high",
    ))

    checks.append(_manual(
        "manual_vite_api_base_url_not_set_in_vercel",
        "VITE_API_BASE_URL not yet set in Vercel dashboard",
        "frontend_vercel_deployment",
        "After Render backend is deployed, set VITE_API_BASE_URL in Vercel project "
        "Settings → Environment Variables.",
        severity="high",
    ))

    checks.append(_manual(
        "manual_backend_cors_not_set_for_vercel",
        "Backend QF_CORS_ORIGINS not yet updated for Vercel frontend origin",
        "frontend_vercel_deployment",
        "After the Vercel URL is known (e.g. https://quantfidelity.vercel.app), update "
        "QF_CORS_ORIGINS on the Render backend to include that exact origin.",
        severity="high",
    ))

    return _build_category(
        "frontend_vercel_deployment", "Vercel / Frontend Deployment Prep (M71)", checks
    )


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def _compute_readiness_score(categories: list[ReadinessCategoryData]) -> float:
    score = 100.0
    critical_fail_deduction = 0.0
    high_fail_deduction = 0.0
    medium_fail_deduction = 0.0
    low_fail_deduction = 0.0
    warning_deduction = 0.0
    manual_deduction = 0.0

    for cat in categories:
        for check in cat.checks:
            if check.status == "fail":
                if check.severity == "critical":
                    critical_fail_deduction += 30.0
                elif check.severity == "high":
                    high_fail_deduction += 20.0
                elif check.severity == "medium":
                    medium_fail_deduction += 10.0
                else:
                    low_fail_deduction += 5.0
            elif check.status == "warning":
                warning_deduction += 3.0
            elif check.status == "manual":
                manual_deduction += 1.0

    # Apply caps
    critical_fail_deduction = min(critical_fail_deduction, 60.0)
    high_fail_deduction = min(high_fail_deduction, 60.0)
    medium_fail_deduction = min(medium_fail_deduction, 40.0)
    warning_deduction = min(warning_deduction, 20.0)
    manual_deduction = min(manual_deduction, 10.0)

    total_deduction = (
        critical_fail_deduction
        + high_fail_deduction
        + medium_fail_deduction
        + low_fail_deduction
        + warning_deduction
        + manual_deduction
    )
    return max(0.0, score - total_deduction)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def get_deployment_readiness(db: Session) -> DeploymentReadinessData:
    """Run all deployment readiness checks and return a structured report.

    Read-only — no database writes occur.
    """
    categories = [
        _check_repo_hygiene(),
        _check_backend_readiness(),
        _check_frontend_readiness(),
        _check_sdk_ci_readiness(),
        _check_database_demo_readiness(),
        _check_security_config_readiness(),
        _check_render_deployment_prep(),
        _check_frontend_vercel_deployment(),
        _check_deployment_blockers(),
    ]

    score = _compute_readiness_score(categories)

    # Aggregate counts
    pass_count = sum(cat.pass_count for cat in categories)
    warning_count = sum(cat.warning_count for cat in categories)
    fail_count = sum(cat.fail_count for cat in categories)
    manual_count = sum(cat.manual_count for cat in categories)

    # Blockers: fail checks with severity critical or high
    blockers: list[str] = []
    for cat in categories:
        for check in cat.checks:
            if check.status == "fail" and check.severity in ("critical", "high"):
                blockers.append(f"[{check.severity.upper()}] {check.title}: {check.explanation}")

    blocker_count = len(blockers)

    # Warnings: warning/manual checks with severity high or medium
    warnings_list: list[str] = []
    for cat in categories:
        for check in cat.checks:
            if check.status in ("warning", "manual") and check.severity in ("high", "medium"):
                warnings_list.append(f"[{check.severity.upper()}] {check.title}: {check.explanation}")

    # Overall status
    has_critical_fail = any(
        check.status == "fail" and check.severity == "critical"
        for cat in categories
        for check in cat.checks
    )
    has_high_fail = any(
        check.status == "fail" and check.severity == "high"
        for cat in categories
        for check in cat.checks
    )

    if has_critical_fail:
        overall_status = "blocked"
    elif score < 75 or has_high_fail:
        overall_status = "needs_review"
    elif score >= 85 and not has_high_fail and not has_critical_fail:
        overall_status = "deployment_prep_ready"
    else:
        overall_status = "local_demo_ready"

    # Suggested next steps (deterministic, up to 5)
    next_steps: list[str] = []
    # Highest-priority fails first
    for cat in categories:
        for check in cat.checks:
            if check.status == "fail" and check.suggested_action and len(next_steps) < 5:
                next_steps.append(check.suggested_action)
    # Fill with manual checks if space remains
    for cat in categories:
        for check in cat.checks:
            if check.status == "manual" and check.explanation and len(next_steps) < 5:
                next_steps.append(check.title)
    next_steps = list(dict.fromkeys(next_steps))[:5]  # deduplicate, preserve order

    # Deterministic summary
    deterministic_summary = (
        f"Deployment readiness score: {score:.0f}/100. "
        f"Status: {overall_status}. "
        f"{pass_count} checks passing, {fail_count} failing, "
        f"{warning_count} warnings, {manual_count} manual items. "
        f"{blocker_count} blocker(s) require resolution before production deployment."
    )

    return DeploymentReadinessData(
        generated_at=datetime.now(timezone.utc),
        overall_status=overall_status,
        readiness_score=score,
        pass_count=pass_count,
        warning_count=warning_count,
        fail_count=fail_count,
        manual_count=manual_count,
        blocker_count=blocker_count,
        categories=categories,
        blockers=blockers,
        warnings=warnings_list,
        suggested_next_steps=next_steps,
        deterministic_summary=deterministic_summary,
    )
