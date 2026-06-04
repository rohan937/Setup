#!/usr/bin/env python3
"""M78 — CLI: seed the advanced demo strategy.

Usage (from the backend/ directory, with the venv active):

    python3 scripts/seed_advanced_demo_strategy.py

Creates (or idempotently refreshes) the "US Equity Quality-Momentum Rotation"
demo strategy with its full historical evidence trail. Safe to run repeatedly —
it never duplicates the strategy. Deterministic synthetic data only; not real
trading performance.

Works against whatever database DATABASE_URL points to (local SQLite or the
deployed Render Postgres).
"""
from __future__ import annotations

import json
import os
import sys

# Ensure the backend package root is importable when run as a script.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main() -> int:
    from app.db.session import SessionLocal
    from app.services.advanced_demo_seed import seed_advanced_demo_strategy

    db = SessionLocal()
    try:
        result = seed_advanced_demo_strategy(db)
    finally:
        db.close()

    print(json.dumps(result, indent=2))
    print(
        f"\n{result['status'].upper()}: {result['strategy_name']} "
        f"({result['strategy_id']}) — {result['total_artifacts']} artifacts.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
