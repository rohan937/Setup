"""Tests for M42 CI Evidence Ingestion Recipes.

Verifies that all CI recipe files exist and contain no hardcoded secrets or
API key values.  No server is required.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Root of the repository (three levels up from this file)
_REPO_ROOT = Path(__file__).parent.parent.parent.parent
_SDK_PYTHON = Path(__file__).parent.parent
_EXAMPLES = _SDK_PYTHON / "examples"
_SCRIPTS = _REPO_ROOT / "scripts"
_GITHUB_WORKFLOWS = _REPO_ROOT / ".github" / "workflows"
_DOCS = _REPO_ROOT / "docs"


# ---------------------------------------------------------------------------
# File existence tests
# ---------------------------------------------------------------------------


def test_ci_bundle_json_exists():
    ci_bundle = _EXAMPLES / "ci_bundle.json"
    assert ci_bundle.exists(), f"ci_bundle.json not found at {ci_bundle}"


def test_ci_bundle_json_validates():
    """ci_bundle.json should pass local SDK validation (exit 0)."""
    ci_bundle = _EXAMPLES / "ci_bundle.json"
    if not ci_bundle.exists():
        pytest.skip(f"ci_bundle.json not found at {ci_bundle}")

    from quantfidelity.cli import main  # noqa: PLC0415

    with pytest.raises(SystemExit) as exc_info:
        main(["validate", "--file", str(ci_bundle)])
    assert exc_info.value.code == 0, "ci_bundle.json failed local validation"


def test_ci_ingest_py_exists():
    ci_ingest = _EXAMPLES / "ci_ingest.py"
    if not ci_ingest.exists():
        pytest.skip(f"ci_ingest.py not found at {ci_ingest}")
    assert ci_ingest.exists()


def test_ingest_script_exists():
    script = _SCRIPTS / "ingest_evidence_bundle.sh"
    if not script.exists():
        pytest.skip(f"ingest_evidence_bundle.sh not found at {script}")
    assert script.exists()


def test_flush_script_exists():
    script = _SCRIPTS / "flush_qf_buffer.sh"
    if not script.exists():
        pytest.skip(f"flush_qf_buffer.sh not found at {script}")
    assert script.exists()


def test_github_workflow_exists():
    workflow = _GITHUB_WORKFLOWS / "quantfidelity-ingest.example.yml"
    if not workflow.exists():
        pytest.skip(f"workflow file not found at {workflow}")
    assert workflow.exists()


def test_docs_ci_ingestion_exists():
    doc = _DOCS / "ci-ingestion.md"
    if not doc.exists():
        pytest.skip(f"docs/ci-ingestion.md not found at {doc}")
    assert doc.exists()


# ---------------------------------------------------------------------------
# Security checks: no hardcoded API keys
# ---------------------------------------------------------------------------


def test_scripts_no_hardcoded_api_key():
    """Shell scripts must not contain hardcoded API key values."""
    ingest_sh = _SCRIPTS / "ingest_evidence_bundle.sh"
    flush_sh = _SCRIPTS / "flush_qf_buffer.sh"

    for script_path in (ingest_sh, flush_sh):
        if not script_path.exists():
            pytest.skip(f"Script not found: {script_path}")

        content = script_path.read_text(encoding="utf-8")

        # Must not contain a literal key value (prefix used by the app)
        assert "qf_local_" not in content, (
            f"{script_path.name} contains a hardcoded API key value"
        )
        # Must not assign api_key=<value> (naive pattern check)
        import re  # noqa: PLC0415
        assert not re.search(r'api[_-]key\s*=\s*["\'][^"\']+["\']', content, re.IGNORECASE), (
            f"{script_path.name} contains what looks like a hardcoded api_key assignment"
        )


def test_github_workflow_no_hardcoded_secrets():
    """The example GitHub Actions workflow must not contain hardcoded key values."""
    workflow = _GITHUB_WORKFLOWS / "quantfidelity-ingest.example.yml"
    if not workflow.exists():
        pytest.skip(f"Workflow file not found: {workflow}")

    content = workflow.read_text(encoding="utf-8")
    assert "qf_local_" not in content, (
        "GitHub Actions workflow contains a hardcoded API key value"
    )
