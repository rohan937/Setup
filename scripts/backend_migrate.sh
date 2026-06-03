#!/usr/bin/env bash
# backend_migrate.sh — Run Alembic migrations for QuantFidelity.
#
# Intended for use as a Render pre-deploy command or as a local one-shot migration step.
#
# Usage:
#   bash scripts/backend_migrate.sh
#
# Required environment:
#   QF_DATABASE_URL  — SQLAlchemy database URL (SQLite or PostgreSQL).
#                      Defaults to the SQLite dev database if not set.
#
# Notes:
#   - This script never prints secrets or database credentials.
#   - It must succeed (exit 0) before the application server starts.
#   - On Render, set this as the pre-deploy command:
#       bash scripts/backend_migrate.sh
#   - Alembic reads QF_DATABASE_URL via backend/migrations/env.py.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKEND_DIR="$REPO_ROOT/backend"

echo "[migrate] QuantFidelity — running Alembic migrations"
echo "[migrate] Backend directory: $BACKEND_DIR"

cd "$BACKEND_DIR"

# Verify alembic is available.
if ! command -v alembic &>/dev/null; then
  echo "[migrate] ERROR: alembic not found. Install dependencies first:" >&2
  echo "[migrate]   pip install -r requirements.txt" >&2
  exit 1
fi

echo "[migrate] Running: alembic upgrade head"
alembic upgrade head

echo "[migrate] Migrations complete."
