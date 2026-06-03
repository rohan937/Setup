#!/usr/bin/env bash
# frontend_preview.sh — Serve the production build of the QuantFidelity frontend.
#
# Requires a prior successful `npm run build` (or frontend_build.sh run).
# Useful for local production-preview before deploying to Vercel.
#
# Usage:
#   bash scripts/frontend_preview.sh
#
# Environment variables:
#   VITE_PREVIEW_PORT  — Port to serve on. Default: 4173.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
FRONTEND_DIR="$REPO_ROOT/frontend"

PREVIEW_PORT="${VITE_PREVIEW_PORT:-4173}"

echo "[frontend-preview] Serving production build on port $PREVIEW_PORT"
echo "[frontend-preview] Directory: $FRONTEND_DIR"

cd "$FRONTEND_DIR"

if [ ! -d dist ]; then
  echo "[frontend-preview] ERROR: dist/ not found. Run frontend_build.sh first." >&2
  exit 1
fi

exec npx vite preview --port "$PREVIEW_PORT"
