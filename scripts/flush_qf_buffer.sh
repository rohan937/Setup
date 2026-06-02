#!/usr/bin/env bash
# flush_qf_buffer.sh
#
# List and flush any locally buffered QuantFidelity evidence bundle records.
#
# The offline buffer stores bundles that failed to ingest (e.g., server
# unreachable).  This script lists them and attempts to resend them.
#
# Not investment advice.  Deterministic — no external APIs.
#
# Usage:
#   bash scripts/flush_qf_buffer.sh
#
# Environment variables:
#   QUANTFIDELITY_BASE_URL  (optional) Server URL (default: http://localhost:8000)

set -euo pipefail

QF_BASE_URL="${QUANTFIDELITY_BASE_URL:-http://localhost:8000}"

echo "QuantFidelity Buffer Flush"
echo "  Server: $QF_BASE_URL"
echo ""

# ---------------------------------------------------------------------------
# List buffered records
# ---------------------------------------------------------------------------

echo "Buffered records:"
qf buffer list

echo ""

# ---------------------------------------------------------------------------
# Flush buffered records to the server
# ---------------------------------------------------------------------------

echo "Flushing buffered records to $QF_BASE_URL ..."
qf buffer flush --base-url "$QF_BASE_URL"

echo ""
echo "Done."
