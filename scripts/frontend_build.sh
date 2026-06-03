#!/usr/bin/env bash
# frontend_build.sh — Typecheck and production-build the QuantFidelity frontend.
#
# Intended for local pre-deploy validation and CI.
# On Vercel this is NOT needed — Vercel runs `npm run build` directly.
#
# Usage:
#   bash scripts/frontend_build.sh
#
# Environment variables (optional, all VITE_* prefixed):
#   VITE_API_BASE_URL  — Backend API URL. Defaults to http://localhost:8000.
#                        Production: https://your-render-backend.onrender.com
#   VITE_APP_ENV       — Application environment (local|staging|production).
#   VITE_DEMO_MODE     — Demo mode flag (true|false).
#
# Notes:
#   - This script never prints API URLs, tokens, or any secret values.
#   - `npm run typecheck` runs tsc --noEmit before the build to catch type errors.
#   - The build output is written to frontend/dist/.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
FRONTEND_DIR="$REPO_ROOT/frontend"

echo "[frontend-build] QuantFidelity frontend"
echo "[frontend-build] Directory: $FRONTEND_DIR"

cd "$FRONTEND_DIR"

# Ensure node_modules are present.
if [ ! -d node_modules ]; then
  echo "[frontend-build] node_modules not found — running npm ci"
  npm ci
fi

echo "[frontend-build] Running: npm run typecheck"
npm run typecheck

echo "[frontend-build] Running: npm run build"
npm run build

echo "[frontend-build] Build complete. Output: $FRONTEND_DIR/dist/"
