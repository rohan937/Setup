"""CI ingestion script for QuantFidelity evidence bundles.

Reads bundle configuration from the environment and submits the CI bundle to
a QuantFidelity server.  Safe to run in CI pipelines — secrets are read from
environment variables and never printed.

Not investment advice.  Deterministic — no external APIs, no live market data.

Usage (validation mode, no server required):
    python ci_ingest.py

Usage (live ingestion):
    RUN_QF_EXAMPLE=1 \\
    QUANTFIDELITY_STRATEGY_ID=<uuid> \\
    QUANTFIDELITY_API_KEY=<key> \\
    python ci_ingest.py

Environment variables:
    QUANTFIDELITY_BASE_URL        Server URL (default: http://localhost:8000)
    QUANTFIDELITY_API_KEY         API key (optional for local dev)
    QUANTFIDELITY_STRATEGY_ID     UUID of the target strategy (required for live run)
    QUANTFIDELITY_IDEMPOTENCY_KEY Idempotency key (auto-generated from date+id if unset)
    RUN_QF_EXAMPLE                Set to "1" to perform live ingestion
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import date
from pathlib import Path

# ---------------------------------------------------------------------------
# Locate the bundle file relative to this script
# ---------------------------------------------------------------------------

_SCRIPT_DIR = Path(__file__).parent
_BUNDLE_PATH = _SCRIPT_DIR / "ci_bundle.json"


def _load_bundle() -> dict:
    """Load and return the CI bundle as a dict."""
    if not _BUNDLE_PATH.exists():
        print(f"Error: bundle file not found: {_BUNDLE_PATH}", file=sys.stderr)
        sys.exit(1)
    try:
        with open(_BUNDLE_PATH, encoding="utf-8") as fh:
            return json.load(fh)
    except json.JSONDecodeError as exc:
        print(f"Error: invalid JSON in {_BUNDLE_PATH}: {exc}", file=sys.stderr)
        sys.exit(1)


def _validate_bundle(bundle: dict) -> None:
    """Run SDK-side validation on the bundle.  Exits 1 if issues are found."""
    # Import here so the script can be read without the SDK installed for
    # documentation purposes.
    from quantfidelity.bundle import EvidenceBundle  # noqa: PLC0415

    eb = EvidenceBundle.from_dict(bundle)
    issues = eb.validate()
    if issues:
        print(f"Validation failed — {len(issues)} issue(s):", file=sys.stderr)
        for issue in issues:
            print(f"  - {issue}", file=sys.stderr)
        sys.exit(1)
    print("Validation passed.")


def _build_idempotency_key(strategy_id: str) -> str:
    """Return a deterministic idempotency key based on today's date and strategy id."""
    today = date.today().isoformat()
    raw = f"{today}:{strategy_id}"
    digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
    return f"ci-{today}-{digest}"


def _print_summary(result: dict) -> None:
    """Print a safe summary of the ingestion result without exposing secrets."""
    print("Bundle ingested successfully.")
    print(f"  strategy_id: {result.get('strategy_id', '—')}")
    print(f"  created:     {result.get('created_count', '—')}")
    print(f"  reused:      {result.get('reused_count', '—')}")
    if result.get("idempotency_status"):
        print(f"  idempotency: {result['idempotency_status']}")
    if result.get("ingestion_batch_id"):
        print(f"  batch_id:    {result['ingestion_batch_id']}")
    if result.get("summary"):
        print(f"  summary:     {result['summary']}")


def main() -> None:
    base_url = os.environ.get("QUANTFIDELITY_BASE_URL", "http://localhost:8000")
    api_key = os.environ.get("QUANTFIDELITY_API_KEY") or None
    strategy_id = os.environ.get("QUANTFIDELITY_STRATEGY_ID", "").strip()
    idempotency_key_env = os.environ.get("QUANTFIDELITY_IDEMPOTENCY_KEY", "").strip()
    run_example = os.environ.get("RUN_QF_EXAMPLE", "").strip() == "1"

    bundle = _load_bundle()

    if not run_example:
        # Validation-only mode: useful in PR checks and local development.
        print("RUN_QF_EXAMPLE not set — running validation only (no server call).")
        print(f"Bundle path: {_BUNDLE_PATH}")
        _validate_bundle(bundle)
        print()
        print("To perform live ingestion, set the following env vars and re-run:")
        print("  RUN_QF_EXAMPLE=1")
        print("  QUANTFIDELITY_STRATEGY_ID=<your-strategy-uuid>")
        print("  QUANTFIDELITY_BASE_URL=http://localhost:8000  # or your server")
        print("  QUANTFIDELITY_API_KEY=<optional>")
        print()
        print("Bundle payload:")
        print(json.dumps(bundle, indent=2))
        sys.exit(0)

    # Live ingestion mode
    if not strategy_id:
        print(
            "Error: QUANTFIDELITY_STRATEGY_ID is required when RUN_QF_EXAMPLE=1.",
            file=sys.stderr,
        )
        sys.exit(1)

    _validate_bundle(bundle)

    idempotency_key = idempotency_key_env or _build_idempotency_key(strategy_id)
    print(f"Idempotency key: {idempotency_key}")
    print(f"Target strategy: {strategy_id}")
    print(f"Server:          {base_url}")
    # Never print api_key

    from quantfidelity.client import QuantFidelityClient  # noqa: PLC0415
    from quantfidelity.exceptions import QuantFidelityError  # noqa: PLC0415

    client = QuantFidelityClient(base_url=base_url, api_key=api_key)
    try:
        result = client.ingest_evidence_bundle(
            strategy_id,
            bundle,
            idempotency_key=idempotency_key,
            buffer_on_failure=True,
            retry=True,
        )
    except QuantFidelityError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    _print_summary(result)
    sys.exit(0)


if __name__ == "__main__":
    main()
