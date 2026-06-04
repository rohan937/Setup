# CI Evidence Ingestion

Guide for integrating QuantFidelity evidence bundle ingestion into CI/CD pipelines,
shell scripts, and Python notebooks.

> **Deterministic.** Not investment advice.  No external APIs, no live market data.

---

## Prerequisites

- Python >= 3.11
- QuantFidelity SDK installed: `pip install -e sdk/python` (or `pip install -e "sdk/python[dev]"`)
- A running QuantFidelity backend (default: `http://localhost:8000`)
- An evidence bundle JSON file (see `sdk/python/examples/ci_bundle.json`)

---

## Quick start (5 steps)

1. **Install the SDK**
   ```bash
   pip install -e "sdk/python[dev]"
   ```

2. **Create an API key** (optional for local dev, required when `QF_REQUIRE_API_KEY_FOR_INGESTION=true`)
   ```bash
   curl -s -X POST http://localhost:8000/api/api-keys \
     -H "Content-Type: application/json" \
     -d '{"name": "ci-key"}' | python3 -m json.tool
   ```

3. **Export environment variables**
   ```bash
   export QUANTFIDELITY_BASE_URL=http://localhost:8000
   export QUANTFIDELITY_API_KEY=qf_local_<your-key>
   export QUANTFIDELITY_STRATEGY_ID=<your-strategy-uuid>
   ```

4. **Validate your bundle**
   ```bash
   qf validate --file sdk/python/examples/ci_bundle.json
   ```

5. **Ingest**
   ```bash
   qf ingest \
     --strategy-id "$QUANTFIDELITY_STRATEGY_ID" \
     --file sdk/python/examples/ci_bundle.json \
     --idempotency-key "ci-run-$(date +%Y%m%d)"
   ```

---

## Creating an API key

API keys are QuantFidelity-internal keys used to authenticate SDK requests.
They are not third-party market data keys.

```bash
# Create a key
curl -s -X POST http://localhost:8000/api/api-keys \
  -H "Content-Type: application/json" \
  -d '{"name": "my-ci-key"}' | python3 -m json.tool
# raw_key is returned once — store it immediately.

# List keys (does not return raw values)
curl -s http://localhost:8000/api/api-keys | python3 -m json.tool

# Revoke a key
curl -s -X DELETE http://localhost:8000/api/api-keys/<key-id>
```

Via the QuantFidelity Settings page: navigate to `/settings` and use the
"API Keys" section.

---

## Environment variables

| Variable                       | Required        | Default                   | Description                                      |
|-------------------------------|-----------------|---------------------------|--------------------------------------------------|
| `QUANTFIDELITY_BASE_URL`      | No              | `http://localhost:8000`   | QuantFidelity server URL                         |
| `QUANTFIDELITY_API_KEY`       | No*             | —                         | API key (`qf_local_...`). *Required if enforcement enabled |
| `QUANTFIDELITY_STRATEGY_ID`   | For live ingest | —                         | UUID of the target strategy                      |
| `QUANTFIDELITY_IDEMPOTENCY_KEY` | No            | auto-generated            | Idempotency key for deduplication                |
| `QF_REQUIRE_API_KEY_FOR_INGESTION` | Backend   | `false`                   | Backend: set `true` to require keys              |

The `qf` CLI also accepts `--base-url` and `--api-key` flags.
Flags take precedence over environment variables.

---

## Local validation

Validate a bundle without sending it to the server:

```bash
# Exit 0 = valid, exit 1 = issues found
qf validate --file sdk/python/examples/ci_bundle.json

# In Python
from quantfidelity.bundle import EvidenceBundle
bundle = EvidenceBundle.from_json(open("ci_bundle.json").read())
issues = bundle.validate()  # [] means valid
```

---

## Local ingestion commands

```bash
# Dry run — parse and print, no server call
qf ingest \
  --strategy-id "$QUANTFIDELITY_STRATEGY_ID" \
  --file sdk/python/examples/ci_bundle.json \
  --dry-run

# Validate then ingest (aborts on validation issues)
qf ingest \
  --strategy-id "$QUANTFIDELITY_STRATEGY_ID" \
  --file sdk/python/examples/ci_bundle.json \
  --validate-before-send

# Validate then ingest, force send even with warnings
qf ingest \
  --strategy-id "$QUANTFIDELITY_STRATEGY_ID" \
  --file sdk/python/examples/ci_bundle.json \
  --validate-before-send --force

# Full JSON response instead of concise summary
qf ingest \
  --strategy-id "$QUANTFIDELITY_STRATEGY_ID" \
  --file sdk/python/examples/ci_bundle.json \
  --json
```

---

## Using idempotency keys

Idempotency keys prevent duplicate ingestion if a CI job retries.

```bash
# Deterministic key based on date and run number
qf ingest \
  --strategy-id "$QUANTFIDELITY_STRATEGY_ID" \
  --file bundle.json \
  --idempotency-key "ci-$(date +%Y%m%d)-run-${CI_RUN_NUMBER:-0}"

# From environment variable
export QUANTFIDELITY_IDEMPOTENCY_KEY="ci-2024-01-15-run-42"
qf ingest --strategy-id "$QUANTFIDELITY_STRATEGY_ID" --file bundle.json
```

Same key + same payload replays the stored response (`idempotency_status: "replayed"`).
Same key + different payload returns a 409 Conflict.

---

## Buffer on failure and flush

If the server is unreachable, the bundle can be saved locally and retried later.

```bash
# Save to buffer on failure
qf ingest \
  --strategy-id "$QUANTFIDELITY_STRATEGY_ID" \
  --file bundle.json \
  --buffer-on-failure

# List buffered records
qf buffer list

# Flush buffered records to the server
qf buffer flush --base-url "$QUANTFIDELITY_BASE_URL"

# Clear buffer without flushing
qf buffer clear --yes
```

The buffer never stores API keys.  Keys are resolved from the environment at flush time.

Shell script shortcut: `scripts/flush_qf_buffer.sh`

---

## GitHub Actions integration

See `.github/workflows/quantfidelity-ingest.example.yml` for a full example workflow.

Key points from the example:
- `QUANTFIDELITY_API_KEY` is stored as a GitHub Actions secret and passed via the `env:` block — it is never echoed or logged.
- The idempotency key is constructed from `github.run_id` and `github.sha` so each unique run gets a unique key, but retries of the same run are deduplicated.
- The workflow first validates, then ingests, so CI fails fast on malformed bundles.
- `workflow_dispatch` inputs let you override `strategy_id` and `bundle_file` without editing the YAML.

To adapt the workflow for your project:
1. Copy `.github/workflows/quantfidelity-ingest.example.yml` to your repo.
2. Add `QUANTFIDELITY_API_KEY` to your repository's Actions secrets.
3. Update the default value for `strategy_id` in the `workflow_dispatch` inputs.
4. Trigger via the GitHub Actions UI or from another workflow using `workflow_call`.

---

## Cron / shell script usage

Use `scripts/ingest_evidence_bundle.sh` for cron-based or ad-hoc shell ingestion:

```bash
# Set environment variables
export QUANTFIDELITY_BASE_URL=http://localhost:8000
export QUANTFIDELITY_STRATEGY_ID=<uuid>
export QUANTFIDELITY_API_KEY=<key>    # optional

# Run
bash scripts/ingest_evidence_bundle.sh

# Or make it executable and run directly
chmod +x scripts/ingest_evidence_bundle.sh
./scripts/ingest_evidence_bundle.sh
```

To override the bundle file:
```bash
QUANTFIDELITY_BUNDLE_FILE=/path/to/my_bundle.json bash scripts/ingest_evidence_bundle.sh
```

---

## Python / notebook usage

```python
import os
from quantfidelity import QuantFidelityClient, EvidenceBundle
import hashlib
from datetime import date

base_url = os.environ.get("QUANTFIDELITY_BASE_URL", "http://localhost:8000")
api_key  = os.environ.get("QUANTFIDELITY_API_KEY")
strategy_id = os.environ["QUANTFIDELITY_STRATEGY_ID"]

client = QuantFidelityClient(base_url=base_url, api_key=api_key)

bundle = (
    EvidenceBundle()
    .with_strategy_run("ci-backtest", run_type="backtest",
                       metrics_json={"sharpe": 1.4})
    .with_actions(compute_reliability_score=True)
)

# Deterministic idempotency key
today = date.today().isoformat()
key = hashlib.sha256(f"{today}:{strategy_id}".encode()).hexdigest()[:16]
idem_key = f"nb-{today}-{key}"

result = client.ingest_evidence_bundle(
    strategy_id, bundle,
    idempotency_key=idem_key,
    buffer_on_failure=True,
)
print(f"Created: {result['created_count']}, Reused: {result['reused_count']}")
```

See `sdk/python/examples/ci_ingest.py` for a standalone runnable script.

---

## Common errors and solutions

| Error | Likely cause | Fix |
|-------|-------------|-----|
| `connection refused` | Server not running | Start the backend: `uvicorn backend.main:app --reload` |
| `401 Unauthorized` | API key missing or wrong | Check `QUANTFIDELITY_API_KEY` is set correctly |
| `403 Forbidden` | Key lacks permission | Create a key with `ingest` scope or use a full-access key |
| `404 Not Found` | Wrong strategy UUID | Verify `QUANTFIDELITY_STRATEGY_ID` against `/api/strategies` |
| `409 Conflict` | Idempotency key reused with different payload | Use a new idempotency key or match the original payload |
| `422 Unprocessable Entity` | Invalid bundle structure | Run `qf validate` first |
| `Bundle has N validation issue(s)` | SDK-side validation failed | Check the issue list and fix the bundle |

---

## Security notes

- **Never commit API keys** to source control.  Always use environment variables or a secret manager.
- Use `--api-key` flag only in trusted local environments where the process list is not visible to other users.
- The offline buffer (`~/.quantfidelity/buffer.jsonl`) stores bundle payloads but never API keys.  Protect this file appropriately.
- GitHub Actions: store `QUANTFIDELITY_API_KEY` as an encrypted repository secret, not as a plain environment variable in the workflow YAML.
- Rotate keys regularly from the QuantFidelity Settings page.

---

## Web upload alternative

This guide covers the terminal/SDK ingestion path, which is the right choice for
CI, cron, and automated pipelines. For **manual ingestion, research, and demos**,
the web app now offers an evidence-bundle uploader — drag/drop or paste JSON,
validate, preview, then ingest — without the SDK or CLI.

Both paths hit the same backend endpoint and produce identical results. See
[`web-evidence-upload.md`](./web-evidence-upload.md) for the web flow.

---

## Notes

All computations are deterministic.  No AI, no live market data, no external API calls.
This guide is for system integration only and is not investment advice.
