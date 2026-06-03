#!/usr/bin/env bash
# backend_start.sh — Start the QuantFidelity FastAPI application server.
#
# Intended for use as a Render start command or local production-like startup.
#
# Usage:
#   bash scripts/backend_start.sh
#
# Environment variables:
#   PORT            — Port to listen on (set automatically by Render). Default: 8000.
#   QF_HOST         — Host to bind. Default: 0.0.0.0
#   QF_LOG_LEVEL    — Uvicorn log level (debug|info|warning|error). Default: info.
#   QF_WORKERS      — Number of uvicorn worker processes. Default: 1.
#                     Increase for production if your Render plan supports it.
#
# Notes:
#   - Run backend_migrate.sh BEFORE this script on first deploy and after schema changes.
#   - On Render the start command should be:
#       bash scripts/backend_start.sh
#   - The pre-deploy command should be:
#       bash scripts/backend_migrate.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKEND_DIR="$REPO_ROOT/backend"

# Honour Render's PORT env var; fall back to QF_PORT or 8000.
LISTEN_PORT="${PORT:-${QF_PORT:-8000}}"
BIND_HOST="${QF_HOST:-0.0.0.0}"
LOG_LEVEL="${QF_LOG_LEVEL:-info}"
WORKERS="${QF_WORKERS:-1}"

echo "[start] QuantFidelity backend"
echo "[start] Binding: $BIND_HOST:$LISTEN_PORT  workers: $WORKERS  log-level: $LOG_LEVEL"

cd "$BACKEND_DIR"

exec uvicorn app.main:app \
  --host "$BIND_HOST" \
  --port "$LISTEN_PORT" \
  --workers "$WORKERS" \
  --log-level "$LOG_LEVEL"
