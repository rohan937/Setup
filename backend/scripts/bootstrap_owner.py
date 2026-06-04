#!/usr/bin/env python3
"""Bootstrap / repair a workspace owner for QuantFidelity.

Use this to fix a deployment where a user registered but ended up without a
workspace membership (e.g. "Current role: -", "No organization found"). It is
safe and idempotent: it reuses the existing organization (never creates a
duplicate) and creates-or-upgrades the member to role=owner / status=active,
linking the matching auth user when one exists.

Configuration (env vars or CLI flags; flags win):
    OWNER_EMAIL      (required)  the user's email
    OWNER_NAME       (optional)  display name (defaults to the auth user's name)
    WORKSPACE_NAME   (optional)  name for the workspace if one must be created
                                 (defaults to "Quant Research Workspace")

Examples:
    OWNER_EMAIL=rohan@configtrace.org OWNER_NAME="Rohan Shah" \\
        python3 scripts/bootstrap_owner.py

    python3 scripts/bootstrap_owner.py --email rohan@configtrace.org --name "Rohan Shah"

Runs against whatever DATABASE_URL points to (local SQLite or Render Postgres).
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Bootstrap / repair a workspace owner.")
    p.add_argument("--email", default=os.environ.get("OWNER_EMAIL"))
    p.add_argument("--name", default=os.environ.get("OWNER_NAME"))
    p.add_argument("--workspace-name", default=os.environ.get("WORKSPACE_NAME"))
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    if not args.email:
        print(
            "ERROR: OWNER_EMAIL is required (env var or --email).",
            file=sys.stderr,
        )
        return 2

    from app.db.session import SessionLocal
    from app.services.auth_users import bootstrap_owner, get_user_by_email

    db = SessionLocal()
    try:
        user = get_user_by_email(db, args.email)
        if user is None:
            print(
                f"WARNING: no registered auth user with email '{args.email.lower().strip()}'. "
                "The member will be created UNLINKED — the user should register with this "
                "email, then re-run this script (or it will auto-link on next login).",
                file=sys.stderr,
            )
        # Admin repair tool: do not block on an existing owner (idempotent).
        result = bootstrap_owner(
            db,
            email=args.email,
            display_name=args.name,
            workspace_name=args.workspace_name,
            require_no_owner=False,
        )
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        print(f"ERROR: bootstrap failed: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()

    print(json.dumps(result, indent=2))
    print(
        f"\nOK: '{result['email']}' is now {result['role']} "
        f"({result['status']}) of '{result['organization_name']}' "
        f"[linked={result['linked']}].",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
