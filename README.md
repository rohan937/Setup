# QuantFidelity

Quant strategy reliability and observability infrastructure.

> QuantFidelity shows where alpha breaks between data, backtests, production, and execution.

QuantFidelity is a reliability layer for systematic trading teams. It tracks the full strategy
lifecycle — data, research, backtests, assumptions, intended orders, fills, and live P&L — and
deterministically explains where alpha leaks between research and live trading. It is **not** a
trading bot, **not** a stock tracker, and **not** an investment advisor. See the planning
documents in this folder (`Vision.txt`, `ProductSpec.txt`, `Architecture.txt`, etc.) for the
full thesis.

---

## Repository layout

```
QuantFidelity/
├── backend/                FastAPI service (Python)
│   ├── alembic.ini         Alembic migration configuration
│   ├── migrations/         Alembic migration scripts
│   │   └── versions/       Individual migration files
│   ├── app/
│   │   ├── main.py         App entrypoint + CORS + router wiring
│   │   ├── core/           Config (env-driven settings) + constants
│   │   ├── api/            Routers: health, meta, projects, strategies, timeline, datasets, reports
│   │   ├── models/         SQLAlchemy ORM models (17 tables)
│   │   ├── schemas/        Pydantic response models
│   │   ├── services/       Domain services (seed, run_comparison, data_quality, alerts, dataset_comparison, reports, universe_snapshots, strategy_reliability)
│   │   └── db/             SQLAlchemy engine, session, declarative base
│   └── tests/              Pytest tests (1292 tests, 1 skipped)
├── frontend/               React + TypeScript + Vite + Tailwind
│   └── src/
│       ├── components/     App shell, sidebar, topbar, cards
│       ├── pages/          Dashboard + placeholder pages
│       ├── lib/            API client, nav config
│       ├── types/          Shared TS types
│       └── styles/         Tailwind entry + base styles
├── docs/                   Engineering notes
└── *.txt                   Product planning documents
```

---

## Prerequisites

- Python 3.11+ (developed against 3.13)
- Node.js 20+ (developed against 24) and npm

No external database required for local development — defaults to SQLite.

---

## Backend — local setup & run

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env           # optional; defaults work for local dev
```

### Run database migrations

```bash
# From backend/
alembic upgrade head
```

This creates the database (SQLite by default at `backend/quantfidelity.db`).

To use PostgreSQL instead, set in `backend/.env`:

```env
QF_DATABASE_URL=postgresql+psycopg2://user:pass@localhost:5432/quantfidelity
```

Then run `alembic upgrade head` again.

### Seed demo data

```bash
# From backend/
python -m app.services.seed
```

Creates the QuantFidelity Demo org, project, AAPL Mean Reversion strategy, v1.0 version, and
baseline backtest run. Safe to run multiple times — idempotent.

### Run the API

```bash
uvicorn app.main:app --reload
# API available at http://localhost:8000
```

### Verify with curl

```bash
curl http://localhost:8000/health
curl http://localhost:8000/api
curl http://localhost:8000/api/projects
curl http://localhost:8000/api/strategies
curl http://localhost:8000/api/strategies/<strategy_id>
curl http://localhost:8000/api/strategies/<strategy_id>/runs
curl "http://localhost:8000/api/timeline?limit=10"

# M4: log a run
curl -s -X POST http://localhost:8000/api/strategies/<strategy_id>/runs \
  -H 'Content-Type: application/json' \
  -d '{
    "run_name": "Baseline Backtest 2024-Q1",
    "run_type": "backtest",
    "status": "completed",
    "universe_name": "SP500",
    "dataset_version": "v2024-01",
    "metrics_json": {"sharpe": 1.4, "max_drawdown": -0.12, "annual_return": 0.18},
    "params_json": {"lookback": 20, "threshold": 0.5},
    "assumptions_json": {"transaction_cost_bps": 5, "fill_model": "close"},
    "notes": "Baseline run before signal tuning"
  }'

# M5: compare two runs — deterministic diff, no AI
curl -s "http://localhost:8000/api/strategies/<strategy_id>/runs/compare?run_a_id=<run_a_id>&run_b_id=<run_b_id>" \
  | python3 -m json.tool
```

> **M5 note:** The comparison engine is purely deterministic — it diffs logged run data.
> No AI is used. Language in `deterministic_explanation` is explicitly hedged
> ("changed alongside", "noted as observed") and never makes causal claims.

Interactive OpenAPI docs: `http://localhost:8000/docs`

### Run tests

```bash
cd backend
./.venv/bin/pytest -v
# 64 tests: schema, seed, idempotency, all endpoints, M3 strategy creation, M4 run logging
```

---

## Frontend — local setup & run

```bash
cd frontend
npm install
cp .env.example .env           # optional; defaults to http://localhost:8000

npm run dev          # dev server → http://localhost:5173
npm run typecheck    # TypeScript check
npm run build        # production build
npm run preview      # preview production build
```

The top bar shows a live **Backend online / offline** indicator (calls `GET /api`), so run
the backend alongside the frontend to see it connected.

---

## Current milestone — M47: Research-to-Production Drift Engine v1

**Status: complete.**

### M47 deliverables

- **New service `backend/app/services/strategy_drift.py`** — `compute_strategy_drift(strategy_id, mode, baseline_run_id, comparison_run_id, db)` and 5 helper functions: `_run_to_summary`, `_compute_metric_drifts`, `_compute_evidence_drifts`, `_compute_assumption_drifts`, `_compute_trust_drifts`, `_compute_drift_score`. No AI, no external APIs. Fully deterministic. Not investment advice.

- **3 drift modes**:
  - `latest_stage_pair` (default) — compares latest backtest run against the latest paper or live run.
  - `selected_runs` — compares two caller-specified run IDs.
  - `full_stage_path` — walks all stage transitions (backtest → paper → live) in order.

- **4 drift dimensions**:
  - **Metric drift** — per-metric direction and severity across 6 metrics: sharpe, sortino, annual_return, max_drawdown, turnover, volatility.
  - **Evidence drift** — dataset health, signal quality, universe snapshot, and backtest trust score changes between runs.
  - **Assumption drift** — uses M40 `classify_assumption_change()` to surface weakening/positive/review config changes between runs.
  - **Trust drift** — backtest audit trust score delta and run health label comparison.

- **Drift score (0–100)**:
  - Starts at 100.
  - High metric drift: −20.
  - Medium metric drift: −10.
  - Evidence deterioration: −10.
  - Audit trust drop: −20.
  - Weakening assumptions: −10.

- **Drift status thresholds** (derived from drift score):
  - `stable`: score >= 85.
  - `watch`: score >= 70.
  - `review`: score >= 50.
  - `severe`: score < 50.
  - `insufficient_evidence`: not enough runs to compare.

- **New endpoint** `GET /api/strategies/{id}/drift`:
  - Read-only. No `AuditTimelineEvent` created.
  - Query params: `mode` (`latest_stage_pair` / `selected_runs` / `full_stage_path`), `baseline_run_id` (UUID, for selected_runs mode), `comparison_run_id` (UUID, for selected_runs mode).
  - Returns `StrategyDriftResponse`. 404 for unknown strategy.

- **New schemas `backend/app/schemas/strategy_drift.py`** — Pydantic request and response models for all drift dimensions and the top-level response.

- **Frontend — `DriftPanel`** in `StrategyDetail.tsx`:
  - Mode selector (latest_stage_pair / selected_runs / full_stage_path).
  - Run pair header showing baseline vs. comparison run labels and types.
  - Metric drift table (collapsible) — per-metric direction badges and severity indicators; drifted rows highlighted.
  - Evidence drift table (collapsible) — dataset health, signal quality, universe, and backtest trust delta rows.
  - Assumption drift section (collapsible) — weakening/positive/review config changes surfaced from M40.
  - Trust drift section (collapsible) — audit trust score and run health label comparison.
  - Drift score chip with drift status badge.
  - Suggested checks panel.
  - Auto-loads for each strategy on StrategyDetail page.

- **17 new backend M47 tests** (`tests/test_strategy_drift_m47.py`). All 17 passed on first run.
- **Backend total: 1292 passed, 1 skipped.**
- **Zero TypeScript errors**, clean production build (64 modules, built in ~800ms). One non-fatal chunk size warning — not an error.
- No external APIs. Deterministic. Not investment advice.

### What M47 does NOT build (by design)

- No live trading integration or broker API.
- No external market data ingestion.
- No automatic trading gates or circuit breakers based on drift.
- No production incident management.

---

## Previously completed — M46: Demo Mode + Data Seeder v2

**Status: complete.**

### M46 deliverables

- **New service `backend/app/services/demo_seed.py`** — `seed_demo_data(db, mode, confirm_reset)` and `get_demo_status(db)` functions. No AI, no external APIs. Fully deterministic. Not real market data.

- **Demo data — 3 deterministic strategies**:
  - **AAPL Mean Reversion Demo** — health status `healthy`, `well_instrumented` lineage.
  - **FX Carry Strategy Demo** — health status `review`, partial evidence.
  - **Crypto Momentum Demo** — health status `under_instrumented`, minimal evidence.

- **Evidence created per demo strategy** (deterministic, stable slugs):
  - Strategy versions, config snapshots, universe snapshots, signal snapshots.
  - Datasets and dataset snapshots.
  - Strategy runs.
  - Backtest audits (optional per strategy).
  - Reliability scores.
  - Alerts (optional per strategy).
  - Reports (optional per strategy).

- **Two new endpoints** registered in `backend/app/api/routes/admin.py`:
  - `POST /api/admin/seed-demo` — body: `{ "mode": "extend" | "reset_demo_only", "confirm_reset": true }`.
  - `GET /api/admin/demo-status` — returns demo org/project/strategy counts and last seeded timestamp.

- **Seeding modes**:
  - `extend` (default) — idempotent; reuses existing demo org/project/strategies by stable slugs. Safe to run multiple times.
  - `reset_demo_only` — deletes the demo org and all its data, then reseeds from scratch. Requires `confirm_reset=True`. Only the demo org/project is deleted — non-demo data is never touched.

- **Safety**: `reset_demo_only` requires `confirm_reset=True`; any non-demo organization is completely untouched.

- **`EventType.demo_seeded`** added to `backend/app/core/constants.py`.

- **New schemas `backend/app/schemas/demo_seed.py`** — `DemoSeedRequest`, `DemoSeedResponse`, `DemoStatusResponse`.

- **Frontend — Demo Mode section in `AdminSystemHealth.tsx`**:
  - Seed button (extend mode) and Reset + Reseed button (reset_demo_only).
  - Status chips showing demo strategy count and last seeded timestamp.
  - Result panel with links to seeded strategies after successful seed.

- **New docs `docs/demo-walkthrough.md`** — 10-step demo guide covering seed, navigation, and key feature exploration.

- **13 new backend M46 tests** (`tests/test_demo_seed_m46.py`). All 13 passed on first run.
- **Backend total: 1275 passed, 1 skipped.**
- **Zero TypeScript errors**, clean production build (64 modules, built in ~854ms).
- No external APIs. Fully deterministic. Not real market data. Not investment advice.

### Quick start

```bash
# Seed demo data
curl -s -X POST http://localhost:8000/api/admin/seed-demo \
  -H 'Content-Type: application/json' \
  -d '{"mode": "extend"}' | python3 -m json.tool

# Then open the frontend
open http://localhost:5173
```

### What M46 does NOT build (by design)

- No production deployment or cloud provisioning.
- No user onboarding flows or guided tours.
- No live or real market data.
- No AI-generated demo content.

---

## Previously completed — M45: System Health + Operations Dashboard v1

**Status: complete.**

### M45 deliverables

- **New service `backend/app/services/system_health.py`** — `get_system_health(db)` queries all major models for entity counts, ingestion health, API key health, and evidence activity. No AI, no external APIs, deterministic.

- **New endpoint** `GET /api/admin/system-health`:
  - Read-only. No `AuditTimelineEvent` created. No auth requirement beyond existing local behavior.
  - Returns `SystemHealthResponse`.

- **New router** `backend/app/api/routes/admin.py` registered in `app/api/router.py` under `/api` prefix.

- **Entity counts**:
  - Organizations, projects.
  - Strategies: active and archived counts.
  - Runs, datasets, snapshots (all types: dataset, signal, universe, config).
  - Backtest audits.
  - Alerts: open and high/critical counts.
  - Reports, timeline events.
  - API keys: active and revoked counts.
  - Ingestion batches: completed and failed counts.

- **Ingestion health status** (deterministic, rule-based):
  - `no_batches` — no ingestion batches exist.
  - `healthy` — failure_rate = 0.
  - `watch` — some failures exist.
  - `degraded` — failure_rate > 10% or 3+ recent failures.

- **API key health status** (deterministic, rule-based):
  - `healthy` — keys are in regular use.
  - `watch` — many never-used keys.
  - `review` — stale keys present.

- **Evidence activity status** (deterministic, rule-based):
  - `active` — last activity within 7 days.
  - `quiet` — last activity within 30 days.
  - `stale` — last activity more than 30 days ago.
  - `no_activity` — no timeline events exist.

- **System score (0–100)**: starts at 100, deducts for degraded ingestion, high/critical alerts, stale API keys, quiet/stale evidence activity, and under-instrumented strategies.

- **System status thresholds** (derived from system score):
  - `healthy` — score >= 80.
  - `watch` — score >= 60.
  - `review` — score >= 40.
  - `degraded` — score < 40.

- **Frontend — `AdminSystemHealth.tsx`** at route `/admin/system-health`:
  - Status banner showing system score and system status.
  - Entity count grid.
  - Three health panels: ingestion health, API key health, evidence activity.
  - Strategy and project rollup summaries.
  - Recent activity section.
  - Suggested checks panel.

- **Navigation**: "System Health" link added under a new Admin section in the sidebar.

- **Dashboard**: compact System Health card on `Dashboard.tsx` showing system score, system status, and a link to the full page.

- **New schemas `backend/app/schemas/system_health.py`** — Pydantic request and response models.

- **16 new backend M45 tests** (`tests/test_system_health_m45.py`). All 16 passed on first run.
- **Backend total: 1262 passed, 1 skipped.**
- **Zero TypeScript errors**, clean production build (64 modules, built in ~800ms). One non-fatal chunk size warning — not an error.
- No external APIs. Deterministic. Not for external reporting. Not investment advice.

### What M45 does NOT build (by design)

- No full RBAC admin auth, user management, or billing.
- No production monitoring integrations (Datadog, PagerDuty, etc.).
- No background workers or scheduled health checks.
- No AI-generated health summaries.
- No multi-tenant admin console.

---

## Previously completed — M44: Strategy Comparison Report v1

**Status: complete.**

### M44 deliverables

- **New service `backend/app/services/strategy_comparison_report.py`** — `generate_strategy_comparison_report(strategy_ids, format, include_raw_json, db)` aggregates health, reliability, coverage, assumption health, trends, and alerts per strategy into a structured comparison report. No AI, no external APIs, deterministic.

- **New endpoint** `POST /api/strategies/compare/report`:
  - **Request body**: `strategy_ids` (list of 2–4 UUIDs), `format` (`json` or `markdown`), `include_raw_json` (bool).
  - Registered BEFORE `GET /strategies/{strategy_id}` to avoid routing collision.
  - Returns `StrategyComparisonReportResponse`.
  - 404 for unknown strategies. 400 for invalid strategy count or format.

- **Report sections** — 7 sections per report:
  - `comparison_summary` — overall summary across all compared strategies.
  - `health_comparison` — health scores and statuses per strategy.
  - `reliability_comparison` — reliability scores per strategy.
  - `coverage_comparison` — evidence coverage scores per strategy.
  - `assumption_comparison` — assumption health scores and category statuses per strategy.
  - `trend_comparison` — trend directions (reliability, data health, backtest trust, signal quality) per strategy.
  - `alerts_comparison` — open alert counts and severities per strategy.

- **Rankings** — four ranked orderings, deterministic, nulls last:
  - By `evidence_coverage` — "higher evidence coverage".
  - By `reliability_score`.
  - By `health_score`.
  - By `assumption_health`.

- **Suggested review agenda** — deterministic checklist; critical health first, weakening config changes, deteriorating trends. Language uses "requires review" — never "best strategy", "most profitable", "buy/sell".

- **JSON format** — `StrategyComparisonReportResponse` with `metadata` + `sections` + `strategy_summaries` + `rankings`.

- **Markdown format** — same response envelope + `content` string with full Markdown report.

- **Filename** — `quantfidelity_strategy_comparison_report_{timestamp}.json` or `.md` (included in response metadata for client-side download).

- **Language**: "higher evidence coverage", "requires review" — never "best strategy", "most profitable", "buy/sell".

- **New schemas `backend/app/schemas/strategy_comparison_report.py`** — request and response Pydantic models.

- **Frontend — report generation panel in `StrategyComparison.tsx`**:
  - "Export JSON" and "Export Markdown" buttons — download via `Blob`.
  - "Copy Markdown" button for markdown format.
  - Rankings summary panel (evidence coverage, reliability, health, assumption health).
  - Suggested review agenda panel.

- **23 new backend M44 tests** (`tests/test_strategy_comparison_report_m44.py`). All 23 passed on first run.
- **Backend total: 1246 passed, 1 skipped.**
- **Zero TypeScript errors**, clean production build (63 modules, built in ~813ms).
- No external APIs. Deterministic. Not investment advice.

### What M44 does NOT build (by design)

- No AI-generated reports.
- No PDF export.
- No live performance comparison.
- No portfolio allocation or rebalancing recommendations.
- No scheduled delivery or email/Slack notifications.

---

## Previously completed — M43: Strategy Timeline Analytics v1

**Status: complete.**

### M43 deliverables

- **New service `backend/app/services/timeline_analytics.py`** — `compute_strategy_timeline_analytics(strategy_id, db, bucket, lookback_days)` assembles time-bucketed activity data and gap analysis from `AuditTimelineEvent` records. No AI, no external APIs, deterministic.

  - **`TimelineAnalyticsBucketData` dataclass** — one entry per time bucket:
    - `bucket_label` — human-readable period label (e.g. `"2026-W22"`, `"2026-05"`, `"2026-05-30"`).
    - `bucket_start` / `bucket_end` — ISO timestamp boundaries.
    - `total_events` — count of all events in the bucket.
    - `event_type_counts` — dict of event type → count.
    - `source_type_counts` — dict of source type → count.
    - `evidence_category_counts` — dict of evidence category → count (same 11 categories as M29: `run` / `data` / `backtest` / `config` / `universe` / `signal` / `reliability` / `report` / `alert` / `ingestion` / `other`).

  - **`TimelineInactivityGapData` dataclass** — one entry per gap >= 14 days:
    - `gap_start` / `gap_end` — ISO timestamps bounding the gap.
    - `gap_days` — length of the gap in days.
    - `preceding_event_type` / `following_event_type` — event types on either side of the gap (null if no preceding/following event).

  - **`StrategyTimelineAnalyticsData` dataclass** — top-level response:
    - `strategy_id`, `bucket`, `lookback_days`, `generated_at`.
    - `buckets` — list of `TimelineAnalyticsBucketData` in chronological order.
    - `total_events_in_window` — sum of all events across all buckets.
    - `active_buckets` — count of buckets with at least one event.
    - `empty_buckets` — count of buckets with zero events.
    - `peak_bucket_label` / `peak_bucket_count` — label and count of the busiest bucket.
    - `staleness_status` — `active` (event within 14 days), `watch` (15–45 days), `stale` (> 45 days), `no_activity` (no events in window).
    - `days_since_last_event` — float or null.
    - `inactivity_gaps` — list of `TimelineInactivityGapData` for gaps >= 14 days, sorted longest-first, capped at 10.
    - `evidence_category_mix` — dict of evidence category → total count across all buckets.
    - `deterministic_summary` — rule-based text summary; no AI, no investment advice.
    - `suggested_checks` — deterministic list of actionable checks based on staleness and gap analysis.

- **New endpoint** `GET /api/strategies/{id}/timeline/analytics`:
  - Query params: `bucket` (`day` / `week` / `month`, default `week`), `lookback_days` (int, default `180`, max `730`).
  - Returns `StrategyTimelineAnalyticsResponse`. Read-only — no `AuditTimelineEvent` created.
  - 404 for unknown strategy.

- **Activity buckets**: each contains `total_events`, `event_type_counts`, `source_type_counts`, `evidence_category_counts` per time period.

- **Evidence categories** reused from M29 `strategy_timeline` service: `run` / `data` / `backtest` / `config` / `universe` / `signal` / `reliability` / `report` / `alert` / `ingestion` / `other`.

- **Staleness status rules**:
  - `active`: last event within 14 days.
  - `watch`: last event 15–45 days ago.
  - `stale`: last event > 45 days ago.
  - `no_activity`: no events in the lookback window.

- **Gap analysis**: identifies inactivity gaps >= 14 days between consecutive events, sorted longest-first, capped at 10 gaps.

- **Deterministic summary and suggested checks**: no AI, no investment advice.

- **New schemas `backend/app/schemas/timeline_analytics.py`**:
  `TimelineAnalyticsBucket`, `TimelineInactivityGap`, `StrategyTimelineAnalyticsResponse`.

- **Frontend — `TimelineAnalyticsPanel`** in `StrategyDetail.tsx`:
  - Summary strip: total events, active buckets, empty buckets, peak bucket, staleness status badge, days since last event.
  - Bucket selector (day / week / month) and lookback selector (30 / 90 / 180 / 365 days).
  - Div-based activity bar chart — one bar per bucket, height proportional to `total_events`, no chart library required.
  - Evidence category mix panel showing category → count breakdown across the window.
  - Inactivity gaps table showing gap start, end, length in days, and surrounding event types.
  - Suggested checks panel.

- **24 new backend M43 tests** (`tests/test_timeline_analytics_m43.py`). All 24 passed on first run.
- **Backend total: 1223 passed, 1 skipped.**
- **Zero TypeScript errors**, clean production build (63 modules, built in 791ms).
- No external APIs. Read-only. Not investment advice.

### What M43 does NOT build (by design)

- No live polling or real-time activity streaming.
- No AI activity summaries or anomaly detection.
- No cross-strategy timeline comparison.
- No notification scheduling based on gap thresholds.

---

## Previously completed — M42: CI Evidence Ingestion Recipes v1

**Status: complete.**

### M42 deliverables

- **New `docs/ci-ingestion.md`** — end-to-end CI ingestion guide: environment variable setup,
  bundle validation, ingest command, idempotency, troubleshooting, and security notes.

- **New `.github/workflows/quantfidelity-ingest.example.yml`** — GitHub Actions workflow template
  (`workflow_dispatch` only). Uses `secrets.QUANTFIDELITY_API_KEY` — no hardcoded secrets.
  Idempotency key derived from `${{ github.run_id }}-${{ github.sha }}` so reruns are safe.

- **New `scripts/ingest_evidence_bundle.sh`** — shell script that validates a bundle file and
  ingests it via the CLI. Reads `QUANTFIDELITY_BASE_URL`, `QUANTFIDELITY_API_KEY`,
  `QUANTFIDELITY_STRATEGY_ID`, and optionally `QUANTFIDELITY_IDEMPOTENCY_KEY` from the environment.

- **New `scripts/flush_qf_buffer.sh`** — shell script for buffer operations (list and flush pending
  SDK buffer entries). Reads same environment variables.

- **New `sdk/python/examples/ci_bundle.json`** — example evidence bundle for CI validation.
  Validated with `Bundle is valid. No issues found.`

- **New `sdk/python/examples/ci_ingest.py`** — Python example demonstrating programmatic
  CI ingestion using the SDK.

- **New `Makefile`** with targets:
  - `sdk-test` — run the full SDK test suite.
  - `sdk-validate-example` — validate `ci_bundle.json` via the CLI.
  - `sdk-ingest-example-dry-run` — dry-run ingestion of the example bundle.
  - `qf-buffer-list` — list pending buffer entries.

- **CLI improvements in `sdk/python/quantfidelity/cli.py`**:
  - `_resolve_base_url()` — resolves `--base-url` flag or `QUANTFIDELITY_BASE_URL` env var
    (falls back to `http://localhost:8000`).
  - `_resolve_idempotency_key()` — resolves `--idempotency-key` flag or `QUANTFIDELITY_IDEMPOTENCY_KEY` env var.
  - Concise ingest success summary printed by default; `--json` flag outputs full JSON response.

- **Environment variables**:
  - `QUANTFIDELITY_BASE_URL` — API base URL (new in M42).
  - `QUANTFIDELITY_API_KEY` — API key (from M24).
  - `QUANTFIDELITY_STRATEGY_ID` — target strategy UUID.
  - `QUANTFIDELITY_IDEMPOTENCY_KEY` — optional idempotency key (new in M42).

- **SDK tests**: 32 passed in `test_cli.py` (includes new M42 env var tests) +
  9 passed in `test_ci_recipes_m42.py`. Total SDK: 189 passed, 3 skipped.

- **Backend**: unchanged. 1199 passed, 1 skipped.

- **Frontend**: unchanged. Zero TypeScript errors, clean build (built in ~741ms).
  One non-fatal chunk size warning (some chunks > 500 kB after minification) — non-blocking.

- **Shell script syntax**: both `ingest_evidence_bundle.sh` and `flush_qf_buffer.sh`
  pass `bash -n` syntax check (exit 0).

- **Security**: API keys passed via environment variables or GitHub Actions secrets.
  Keys are never printed in output, never hardcoded in examples or workflow files.

- **No external APIs. No real secrets used. Not investment advice.**

### What M42 does NOT build (by design)

- No server-side scheduling, cron parser, or scheduled ingestion runner.
- No Celery, task queue, or worker infrastructure.
- No notification delivery (Slack, email, PagerDuty) on ingestion events.
- No ingestion retry logic beyond what the SDK buffer already provides (M25).

---

## Previously completed — M41: Strategy Assumption Health Summary

**Status: complete.**

### M41 deliverables

- **New service `backend/app/services/assumption_health.py`** — `compute_assumption_health(strategy_id, db)`
  aggregates evidence from strategy runs, backtest audits, config snapshots, and M40 config diffs into a
  per-category assumption health summary. No AI, no external APIs, deterministic.

- **7 assumption categories** scored independently:
  - Transaction Costs
  - Slippage
  - Fill Realism
  - Borrow/Shorting
  - Liquidity/Capacity
  - Risk Controls
  - Data Evidence Linkage

- **Category scoring** (per category):
  - Base score: 70 if any evidence exists for that category; null if no evidence.
  - Positive evidence adds +10 per item, capped at 3 positive items (+30 max).
  - Weakening config changes (from M40 diff synthesis) subtract −20 each.
  - Backtest audit issues subtract −20 per high-severity issue, −10 per medium-severity issue.
  - Review items (suggested checks) subtract −5 each.
  - Final score clamped to 0–100.

- **Category status thresholds**:
  - `strong`: score >= 85
  - `acceptable`: score >= 70
  - `review`: score >= 50
  - `weak`: score < 50
  - `missing`: null (no evidence)

- **Overall weighted score** (null if fewer than 3 categories are scored):
  - Transaction Costs: 20%
  - Slippage: 15%
  - Fill Realism: 20%
  - Borrow/Shorting: 10%
  - Liquidity/Capacity: 15%
  - Risk Controls: 10%
  - Data Evidence Linkage: 10%

- **Config diff synthesis from M40**: compares the latest two config snapshots using
  `compare_config_snapshots_enriched()`. Surfaces positive/weakening/review changes and
  `key_assumption_changes` per category. No config snapshots → synthesis is skipped gracefully.

- **Backtest audit synthesis from M36**: pulls the latest backtest audit for the strategy and extracts
  `trust_score`, `cost_fragility_level`, `fill_realism_level`, `largest_penalty_category`, and
  top improvement checks. No audit → synthesis is skipped gracefully.

- **New endpoint** `GET /api/strategies/{id}/assumption-health`:
  - Read-only. No `AuditTimelineEvent` created.
  - 404 for unknown strategy.
  - Returns `AssumptionHealthResponse`.

- **New schemas** `backend/app/schemas/assumption_health.py`:
  `AssumptionCategoryScore`, `AssumptionHealthSummary`, `ConfigDiffSynthesis`,
  `BacktestAuditSynthesis`, `AssumptionHealthResponse`.

- **Frontend — `AssumptionHealthPanel`** in `StrategyDetail.tsx`:
  - Overall assumption health score chip with weighted score and overall status badge.
  - Category scorecard grid — one card per assumption category showing score, status badge,
    evidence count, and top issue.
  - Config changes section — lists key assumption changes with impact level badges (positive /
    weakening / review) sourced from M40 diff synthesis.
  - Backtest synthesis section — trust score, cost fragility level, fill realism level,
    largest penalty category, and top improvement checks from M36 audit synthesis.
  - Suggested checks panel — deduplicated list of actionable checks across all categories.

- **17 new backend M41 tests** (`tests/test_assumption_health_m41.py`).
- **Backend total: 1199 passed, 1 skipped.**
- **Zero TypeScript errors**, clean production build (63 modules, built in ~700ms).
- No external APIs. Deterministic. Not investment advice.

### What M41 does NOT build (by design)

- No AI-generated assumption assessments or automated assumption repair.
- No policy engine or compliance rule enforcement.
- No live execution validation or real-time fill monitoring.
- No cross-strategy assumption benchmarking or industry comparisons.

---

## Previously completed — M40: Config Snapshot Diff Engine v2

**Status: complete.**

### M40 deliverables

- **New function `compare_config_snapshots_enriched()`** added to
  `backend/app/services/config_snapshots.py`. Preserves the existing M15 `compare_config_snapshots()`
  function without modification.

- **Structured diff output** — returns a `ConfigSnapshotComparisonV2` object with four sections:
  `params_diff`, `assumptions_diff`, `portfolio_diff`, `risk_diff`. Each section is a
  `ConfigDiffSection` with a `changes` list and `added_count`, `removed_count`, `changed_count`.

- **`ConfigFieldChange`** — per-field diff record with:
  - `key_path` — dotted path of the changed field.
  - `old_value` / `new_value` — before and after values.
  - `change_type` — `added`, `removed`, or `changed`.
  - `category` — field category (e.g. `cost_assumptions`, `fill_model`, `slippage`, `borrow_cost`,
    `leverage`, `risk_limits`, `liquidity_filters`, or `general`).
  - `impact_level` — `positive`, `neutral`, `review`, `weakening`, or `unknown`.
  - `impact_reason` — deterministic explanation string.
  - `suggested_check` — actionable check hint.

- **Assumption classification rules** (deterministic, no AI):
  - **Cost assumptions**: adding → `positive`; removing → `weakening`; decreasing → `review`;
    increasing → `positive`.
  - **Fill model**: changing to same-close → `weakening`; changing to next-bar → `positive`.
  - **Slippage**: adding → `positive`; removing → `weakening`.
  - **Borrow cost**: adding → `positive`; removing → `weakening`.
  - **Leverage**: increasing → `review`.
  - **Risk limits**: removing → `weakening`; adding → `positive`.
  - **Liquidity filters**: removing → `weakening`; adding → `review`.

- **Impact language**: "may make backtest assumptions less conservative", "requires review".
  Deterministic — no causal claims, no investment advice.

- **New endpoint** `GET /api/strategies/{id}/config-snapshots/compare-v2?snapshot_a_id=...&snapshot_b_id=...`
  — returns a `ConfigSnapshotComparisonV2Response` with:
  - `weakening_changes` — list of changes with `impact_level=weakening`.
  - `positive_changes` — list of changes with `impact_level=positive`.
  - `review_changes` — list of changes with `impact_level=review`.
  - `highlighted_changes` — top changes across all impact levels.
  - `suggested_checks` — deduplicated list of suggested checks across all changes.
  - `deterministic_explanation` — rule-based summary string. Ends with "Not an investment recommendation."

- **New schemas** (`backend/app/schemas/config_snapshots.py`):
  `ConfigFieldChange`, `ConfigDiffSection`, `ConfigSnapshotComparisonV2Response`.

- **Frontend — `ConfigDiffPanel`** in `StrategyDetail.tsx`:
  - Snapshot A / Snapshot B selectors (dropdowns populated from existing config snapshots).
  - Collapsible sections for weakening changes, positive changes, review changes,
    params diff, and assumptions diff.
  - Suggested checks panel at the bottom.
  - Impact level badges (weakening / positive / review / neutral / unknown) per row.

- **22 new backend M40 tests** (`tests/test_config_diff_m40.py`). All 22 passed on first run.
- **Backend total: 1181 passed, 1 skipped.**
- **Zero TypeScript errors**, clean production build (63 modules, built in ~830ms).
- No external APIs. Deterministic. Not investment advice.

### What M40 does NOT build (by design)

- No GitHub integration or git-level config diff.
- No code parsing or AST-level diff.
- No AI explanations.
- No config policy engine or automatic repair.

---

## Previously completed — M39: Universe Snapshot Coverage Analysis v1

**Status: complete.**

### M39 deliverables

- **Migration** `0017_m39_universe_coverage_analysis.py` — adds 4 nullable JSON columns to `universe_snapshots`:
  `coverage_analysis_json`, `symbol_quality_json`, `universe_delta_json`, `universe_quality_summary_json`.
  All existing columns preserved. Safe to run on existing databases.

- **New service** `backend/app/services/universe_coverage.py` — deterministic universe coverage analysis
  service. Does not modify `universe_snapshots.py`. No AI, no external APIs. Six exported functions:
  - `compute_symbol_quality(symbols)` — per-symbol checks: duplicates, spaces, invalid characters,
    suspicious length; `quality_status` (`clean` / `review` / `weak`).
  - `compute_metadata_breakdown(snapshot)` — sector/country/exchange/liquidity_bucket distribution
    if symbol-level metadata is available under `metadata_json["symbols"]`; emits warning if absent.
  - `compute_universe_delta(snapshot, db)` — compares against previous snapshot: `added_count`,
    `removed_count`, `common_count`, `overlap_ratio`, `jaccard_similarity`, `churn_rate`,
    `delta_status` (`stable` / `review` / `high_churn` / `no_previous_snapshot`); added/removed
    symbol lists capped at 50.
  - `compute_run_linkage(snapshot, db)` — count of strategy runs using this universe snapshot;
    version label if version-linked.
  - `compute_universe_quality_summary(symbol_quality, metadata_breakdown, delta)` — aggregated summary
    with status counts, totals, suggested checks.
  - `compute_universe_coverage_analysis(snapshot, db)` — orchestrates all functions into a single response.

- **Snapshot creation updated** — `POST /api/strategies/{id}/universe-snapshots` now computes and stores
  all 4 coverage JSON fields on every new snapshot. Gracefully skips coverage computation if it fails
  (does not block ingestion).

- **New endpoint** `GET /api/universe-snapshots/{id}/coverage-analysis` — returns stored coverage fields
  if present; delta is always recomputed for freshness. 404 for unknown snapshot.

- **New schemas** `backend/app/schemas/universe_coverage.py` — Pydantic response models for all
  coverage analysis fields.

- **Frontend** — `UniverseCoveragePanel` in `StrategyDetail.tsx`:
  - Summary strip (status counts).
  - Delta section (collapsible): added/removed/common counts, overlap ratio, jaccard similarity,
    churn rate, delta status.
  - Metadata breakdown: sector/country/exchange/liquidity_bucket distribution.
  - Symbol quality table: per-symbol quality status.
  - Suggested checks panel.
  - "Inspect Coverage" button per snapshot row in the StrategyDetail universe snapshots section.

- **20 new backend M39 tests** (`tests/test_universe_coverage_m39.py`).
- **Backend total: 1160 passed, 1 skipped.**
- **Zero TypeScript errors**, clean production build (63 modules, built in 786ms).
- No external APIs. Deterministic. Not investment advice.

### What M39 does NOT build (by design)

- No external market data validation.
- No sector/market-cap enrichment from vendors.
- No corporate action engine.
- No automatic repair.
- No AI explanations.

---

## Previously completed — M38: Signal Quality Drill-Down v2

**Status: complete.**

### M38 deliverables

- **Migration** `0016_m38_signal_quality_drilldown.py` — adds 4 nullable JSON columns to `signal_snapshots`:
  `signal_distribution_json`, `symbol_quality_json`, `signal_row_quality_json`, `signal_quality_summary_json`.
  All existing columns preserved. Safe to run on existing databases.

- **New service** `backend/app/services/signal_quality_drilldown.py` — deterministic signal quality analysis
  service. Does not modify `signal_snapshots.py`. No AI, no external APIs. Six exported functions:
  - `compute_signal_distribution(rows)` — per-signal analysis: `value_count`, `missing_count`,
    `non_numeric_count`, `mean`, `median`, `min`, `max`, `stddev`, `zero_count`, `positive_count`,
    `negative_count`, `outlier_count` (IQR-based), extreme z-score counts, zero-variance detection,
    `distribution_status` (`clean` / `review` / `weak` / `unusable`).
  - `compute_symbol_quality(rows)` — per-symbol analysis: `missing_rate`, `mean`, `stddev`,
    `outlier_count`, `duplicate_timestamp_count`, `quality_status`; sorted by worst status; capped at 200.
  - `compute_timestamp_coverage(rows)` — totals: `total`, `duplicate_symbol_timestamp`, `invalid_timestamps`.
  - `compute_signal_row_quality_samples(rows)` — row evidence samples capped at 10 per type:
    missing signals, non-numeric signals, duplicate sym+ts, outliers, invalid timestamps.
  - `compute_signal_quality_summary(distribution, symbol_quality, timestamp_coverage)` — aggregated summary
    with status counts, totals, worst signals/symbols list, suggested checks.
  - `compute_signal_quality_drilldown(rows)` — orchestrates all functions into a single response.

- **Snapshot creation updated** — `POST /api/strategies/{id}/signal-snapshots` now computes and stores
  all 4 quality JSON fields on every new snapshot. Gracefully skips quality computation if it fails
  (does not block ingestion).

- **New endpoint** `GET /api/signal-snapshots/{id}/quality-drilldown` — returns stored quality fields
  if present; computes on-the-fly from snapshot rows if stored fields are null. 404 for unknown snapshot.

- **New schemas** `backend/app/schemas/signal_quality.py`:
  `SignalDistributionRead`, `SymbolQualityRead`, `TimestampCoverageRead`,
  `SignalRowQualitySamplesRead`, `SignalQualitySummaryRead`, `SignalQualityDrilldownResponse`.

- **Frontend** — `SignalQualityDrilldownPanel` in `StrategyDetail.tsx`:
  - Summary strip (status counts by signal distribution status).
  - Distribution card (collapsible, per-signal stats: value count, missing/non-numeric, mean/median/min/max/stddev,
    zero/positive/negative counts, outlier count, distribution status).
  - Symbol quality table (per-symbol missing rate, mean, stddev, outlier count, duplicate timestamp count,
    quality status).
  - Row evidence samples (grouped by sample type with row data).
  - Suggested checks panel.
  - "Inspect Quality" button per snapshot row in the StrategyDetail signal snapshots section opens the
    drill-down panel.

- **23 new backend M38 tests** (`tests/test_signal_quality_drilldown_m38.py`).
- **Backend total: 1140 passed, 1 skipped.**
- **Zero TypeScript errors**, clean production build (63 modules, built in 753ms).
- No external APIs. Deterministic. Not investment advice.

### What M38 does NOT build (by design)

- No factor IC/IR computation or alpha decay analysis.
- No external feature store integration.
- No automatic signal repair or correction.
- No AI explanations of signal quality.

---

## Previously completed — M37: Dataset Snapshot Quality Drill-Down v2

**Status: complete.**

### M37 deliverables

- **Migration** `0015_m37_dataset_quality_drilldown.py` — adds 3 nullable JSON columns to `dataset_snapshots`:
  `column_quality_json`, `row_quality_json`, `quality_summary_json`.
  All existing columns preserved. Safe to run on existing databases.

- **New service** `backend/app/services/dataset_quality_drilldown.py` — deterministic quality analysis service.
  No AI, no external APIs. Four exported functions:
  - `compute_column_quality(rows)` — per-column analysis: `inferred_type`, `null_rate`, `unique_count`,
    numeric stats (`min`, `max`, `mean`, `stddev`), `outlier_count` (IQR-based, requires >= 4 values),
    timestamp validity, `quality_status` (`clean` / `review` / `weak` / `unusable`), `issues` list.
  - `compute_row_quality_samples(rows)` — row evidence samples capped at 10 per type:
    duplicate rows, duplicate symbol+timestamp, invalid OHLC, suspicious returns (>50% move), missing values.
  - `compute_quality_summary(column_quality, row_samples)` — status counts, totals (missing, outliers,
    invalid timestamps), worst columns list, suggested checks.
  - `compute_dataset_quality_drilldown(rows)` — orchestrates all three functions into a single response.

- **Snapshot creation updated** — `POST /api/datasets/{id}/snapshots` now computes and stores all 3 quality
  JSON fields on every new snapshot. Gracefully skips quality computation if it fails (does not block ingestion).

- **New endpoint** `GET /api/dataset-snapshots/{id}/quality-drilldown` — returns stored quality fields
  if present; computes on-the-fly from `rows_json` if stored fields are null. 404 for unknown snapshot.

- **New schemas** `backend/app/schemas/dataset_quality.py`:
  `ColumnQualityRead`, `RowQualitySamplesRead`, `DatasetQualitySummaryRead`, `DatasetQualityDrilldownResponse`.

- **Frontend** — `QualityDrilldownPanel` in `DataHealth.tsx`:
  - Summary strip (status counts by column quality status).
  - Column quality table (per-column inferred type, null rate, unique count, numeric stats, outlier count, quality status, issues).
  - Row evidence samples (grouped by sample type with row data).
  - Suggested checks panel.
  - "Inspect Quality" button per snapshot row in the data health table opens the drill-down panel.

- **23 new backend M37 tests** (`tests/test_dataset_quality_drilldown_m37.py`).
- **Backend total: 1117 passed, 1 skipped.**
- **Zero TypeScript errors**, clean production build (63 modules, built in 733ms).
- No external APIs. Deterministic. Not investment advice.

### What M37 does NOT build (by design)

- No external data vendor integrations.
- No automatic data repair or correction.
- No AI data explanations.
- No streaming file upload.

---

## Previously completed — M36: Backtest Reality Check v3 — Sensitivity + Attribution

**Status: complete.**

### M36 deliverables

- **Migration** `0014_m36_backtest_audit_v3.py` — adds 4 nullable JSON columns to `backtest_audits`:
  `cost_sensitivity_sweep_json`, `fill_sensitivity_json`, `penalty_attribution_json`, `improvement_checks_json`.
  All existing columns preserved. Safe to run on existing databases.

- **Service** `backend/app/services/backtest_reality.py` — extended with 4 new analysis functions,
  all integrated into `run_backtest_reality_check()`. No AI, no external APIs, deterministic.

  - **Cost sensitivity sweep** — 6 scenarios (assumed, 2×, 3×, 5× cost, +10 bps, +25 bps).
    Adjusts `annual_return` and Sharpe by incremental cost drag per scenario.
    `trust_impact`: `low` if ratio >= 1.5, `medium` if >= 1.0, `high` if < 1.0.
    Approximation only — not a full re-backtest.

  - **Fill sensitivity** — 5 rule-based scenarios.
    `fill_realism_level`: `high_concern` for same-close or exact-fill models,
    `medium_concern` for mid without slippage, `low_concern` for next-bar.
    No market simulation.

  - **Penalty attribution** — maps existing `BacktestIssue` records to 9 categories.
    Applies severity weights: critical 25, high 15, medium 8, low 3.
    Computes `largest_penalty_category`.

  - **Improvement checks** — prioritized deterministic list generated from missing assumptions,
    high-concern fill models, missing dataset links, critical issues, missing borrow cost.

- **Schemas** — `BacktestAudit` and `BacktestAuditListItem` updated with 4 new optional fields.

- **Frontend** — `BacktestV3Panel` in `StrategyDetail.tsx` with 4 collapsible sections
  (cost sensitivity sweep, fill sensitivity, penalty attribution, improvement checks).
  `Backtests.tsx` shows compact v3 chips when v3 data is present.

- **25 new backend M36 tests** (`tests/test_backtest_reality_v3_m36.py`). Total: 1094 passed, 1 skipped.
- **Zero TypeScript errors**, clean production build (63 modules, built in 790ms).
- No external APIs. Deterministic. Not investment advice. Not a full re-backtest — approximations only.

### What M36 does NOT build (by design)

- No full backtest re-simulation or broker API fills.
- No live execution data or AI explanations.
- No market impact modeling or order-book simulation.

---

## Previously completed — M35: Strategy Version Lineage Tracker v1

**Status: complete.**

### M35 deliverables

- **New `backend/app/services/version_lineage.py`** — deterministic version lineage service.
  No AI, no external APIs, read-only.
  - `_compute_version_item(version, runs, ...)` — builds per-version evidence counts, latest evidence values, and evidence score.
  - `_compute_transitions(items)` — detects changes between adjacent versions: git/branch/signal_name changes plus config/universe/signal hash changes.
  - `get_strategy_version_lineage(strategy_id, db)` — assembles the full lineage response including all version items, transitions, and summary fields.

- **New endpoint** `GET /api/strategies/{id}/version-lineage`:
  - Read-only. No `AuditTimelineEvent` created.
  - 404 for unknown strategy.

- **Per-version evidence counts**:
  - `run_count` broken out by run type (backtest, paper, live, research, optimization).
  - `config_snapshot_count`, `universe_snapshot_count`, `signal_snapshot_count`.
  - `dataset_linked_run_count` — runs that have a linked dataset snapshot.
  - `backtest_audit_count`.

- **Per-version latest evidence**:
  - `run_at` — most recent run timestamp for that version.
  - `config_label`, `universe_label`, `signal_name` — latest labels from respective snapshots.
  - `backtest_trust_score`, `data_health_score`, `signal_quality_score` — latest scores from linked records.

- **Version evidence score (0–100)**:
  - Config snapshot present: 15 pts.
  - Universe snapshot present: 15 pts.
  - Signal snapshot present: 20 pts.
  - At least one run: 20 pts.
  - Dataset-linked run present: 15 pts.
  - Backtest audit present: 15 pts.

- **Lineage status per version**:
  - `well_instrumented`: score >= 80.
  - `usable`: score >= 60.
  - `partial`: score >= 30.
  - `under_instrumented`: score < 30.

- **Version transitions** (detected between adjacent versions):
  - Git commit hash change.
  - Branch change.
  - Signal name change.
  - Config hash change.
  - Universe hash change.
  - Signal hash change.

- **Summary fields**:
  - `most_instrumented_version` — version label with highest evidence score.
  - `least_instrumented_version` — version label with lowest evidence score.
  - `average_evidence_score` — mean score across all versions.
  - `versions_missing_runs`, `versions_missing_config`, `versions_missing_universe`, `versions_missing_signal`, `versions_missing_backtest_audit` — counts of versions lacking each evidence type.
  - `deterministic_summary` — rule-based text, no AI, not investment advice.

- **New schema file** `app/schemas/version_lineage.py` — `VersionLineageItem`, `VersionTransition`, `VersionLineageSummary`, `VersionLineageResponse`.

- **Frontend — `VersionLineagePanel`** in `StrategyDetail.tsx`:
  - Summary chips: total versions, average evidence score, under-instrumented count, missing evidence counts.
  - Per-version rows: evidence chips (config / universe / signal / runs / dataset / backtest), evidence score badge, lineage status badge (well_instrumented / usable / partial / under_instrumented).
  - Transitions section: per-transition row showing what changed between adjacent versions.

- **23 new backend M35 tests** (`tests/test_version_lineage_m35.py`).
- **Backend total: 1069 passed, 1 skipped.**
- **Zero TypeScript errors**, clean production build (63 modules, built in 591ms).
- No external APIs. Read-only. Not investment advice.

### What M35 does NOT build (by design)

- No GitHub integration or git commit ingestion.
- No AI lineage analysis or recommendations.
- No graph visualization of version lineage.

---

## Previously completed — M34: Multi-Strategy Run Comparison v1

**Status: complete.**

### M34 deliverables

- **New `backend/app/services/multi_run_comparison.py`** — deterministic multi-strategy run comparison service.
  No AI, no external APIs, read-only. Compares 2–4 strategies using their latest (or selected) runs.

- **New endpoint** `POST /api/strategies/runs/compare-multi`:
  - Registered BEFORE `GET /strategies/{strategy_id}` to avoid routing collision.
  - **Request**: `strategy_ids` (2–4 UUIDs), `mode` (`latest` or `selected`), optional `run_ids` map for selected mode.
  - **Per-run data collected**: metrics (`sharpe`, `annual_return`, `drawdown`, etc.), assumptions (`cost`, `fill_model`, etc.), evidence (dataset health, signal quality, universe, backtest trust, reliability).
  - **Comparison output**: `metric_matrix`, `assumption_matrix`, `evidence_matrix` (all as dicts keyed by strategy_id), 5 rankings (by trust / data / signal / reliability / coverage, nulls last), per-strategy gaps, shared gaps, `highlighted_differences`, `deterministic_explanation`.

- **Ranking language**: "Highest logged trust score", "Strongest linked data health", "Most complete evidence" — never "best strategy", never "most profitable".

- **Deterministic explanation**: no investment language, ends with "Not an investment recommendation."

- **New schema file** `app/schemas/multi_run_comparison.py` — request and response Pydantic models.

- **Frontend — `MultiRunComparison.tsx`** at route `/strategies/run-compare`:
  - Strategy selector panel, per-run cards, evidence matrix, metric matrix, assumption matrix, rankings panel, per-strategy gaps, shared gaps, disclaimer.

- **Nav integration**: not added to the sidebar nav. Accessed via links from the Strategies and Portfolio pages.

- **Strategies page**: "Compare Runs" button added to `Strategies.tsx`.

- **Portfolio page**: "Compare Runs →" link added to `Portfolio.tsx`.

- **22 new backend M34 tests** (`tests/test_multi_run_comparison_m34.py`).
- **Backend total: 1046 passed, 1 skipped.**
- **Zero TypeScript errors**, clean production build (63 modules, built in 782ms).
- No external APIs. Read-only. Not investment advice.

### What M34 does NOT build (by design)

- No P&L comparison or live performance comparison.
- No AI ranking or cross-strategy optimization.

---

## Previously completed — M33: Evidence Quality Alerts v1

**Status: complete.**

### M33 deliverables

- **11 new `AlertRuleType` values** added to `backend/app/core/constants.py`:
  `evidence_coverage_below_threshold`, `strategy_health_review_or_critical`,
  `reliability_score_deteriorating`, `data_health_deteriorating`,
  `signal_quality_deteriorating`, `backtest_trust_deteriorating`,
  `stale_strategy_run`, `missing_signal_evidence`, `missing_universe_evidence`,
  `missing_config_evidence`, `repeated_failed_ingestion`.

- **New function `run_evidence_quality_alerts(organization_id, db)`** in
  `backend/app/services/alerts.py`, integrated into the existing
  `run_alerts_generation` entry point so it runs alongside prior M11 alerts.

- **Alert checks implemented** (all deterministic, no AI, no external calls):
  - `evidence_coverage_below_threshold` — coverage < 50 → high; coverage < 70 → medium.
  - `strategy_health_review_or_critical` — critical health status → critical severity;
    review/watch health status → high severity.
  - `reliability_score_deteriorating` — 2-point delta ≤ −15 → high; delta ≤ −7 → medium.
  - `data_health_deteriorating` — latest data health < 50 → high; or 2-point trend
    delta < −2 → medium.
  - `signal_quality_deteriorating` — same 2-point delta pattern as data health.
  - `backtest_trust_deteriorating` — trust score < 40 → critical; trust score < 60 → high;
    2-point trend deteriorating → medium.
  - `stale_strategy_run` — no runs at all (and strategy has had runs) → medium;
    last run > 90 days → medium; last run > 30 days → low.
  - `missing_signal_evidence` / `missing_universe_evidence` / `missing_config_evidence` —
    triggered only when the strategy has at least one logged run.
  - `repeated_failed_ingestion` — 3+ failed ingestion batches in the last 7 days → medium;
    5+ → high.

- **Alert metadata**: each alert includes `metadata_json` with `evidence_json` (rule-specific
  context values) and `suggested_check` (deterministic action hint, no AI, not investment advice).

- **Alert language examples**: "Evidence coverage critically low", "Strategy health requires
  review", "Reliability score deteriorated", "Data health score low", "Signal quality
  deteriorating", "Backtest trust score critically low", "Strategy has no recent runs",
  "Strategy is missing signal evidence", "Repeated ingestion failures detected".

- **Deduplication**: same pattern as existing M11 alerts — no duplicate open/acknowledged/snoozed
  alert for the same `org + rule_type + source_type + source_id` combination.

- **Frontend — `AlertRuleType`** (`frontend/src/types/index.ts`) updated with all 11 new values.

- **Frontend — `Alerts.tsx`**: `suggested_check` field from `metadata_json` displayed per alert
  row; `RULE_LABEL_MAP` extended with human-readable labels for all 11 new rule types.

- **11 new backend M33 tests** (`tests/test_evidence_quality_alerts_m33.py`):
  each of the 11 alert rule types covered with at least one passing test.

- **Backend total: 1024 passed, 1 skipped.**
- **Zero TypeScript errors**, clean production build (62 modules, built in 762ms).
- No external APIs. No webhooks. Not investment advice.

### What M33 does NOT build (by design)

- No email or Slack notifications.
- No AI-detected or ML-detected alerts.
- No live market data alerts.
- No broker or execution alerts.

---

## Previously completed — M32: Multi-Strategy Portfolio View v1

**Status: complete.**

### M32 deliverables

- **New `backend/app/services/portfolio_overview.py`** — deterministic portfolio aggregation service.
  No AI, no external APIs, read-only.
  - `PortfolioStrategyItemData` dataclass — per-strategy row: `strategy_id`, `name`, `slug`,
    `asset_class`, `status`, `health_score`, `reliability_score`, `coverage_score`,
    `open_alert_count`, `critical_alert_count`, `high_alert_count`, `medium_alert_count`,
    `low_alert_count`, `trend_flags` (`PortfolioTrendFlagsData`), `missing_evidence_count`,
    `review_reason`.
  - `PortfolioTrendFlagsData` dataclass — lightweight 2-point trend check per evidence series
    (reliability, data health, backtest trust, signal quality). A series is flagged as
    `deteriorating` when the latest value minus the previous value falls below −2.0 (threshold 2.0).
    Fields: `reliability_deteriorating`, `data_health_deteriorating`,
    `backtest_trust_deteriorating`, `signal_quality_deteriorating`, `any_deteriorating`.
  - `PortfolioOverviewData` dataclass — top-level response: `strategy_count`,
    `active_strategy_count`, `average_health_score`, `average_reliability_score`,
    `average_coverage_score`, `total_open_alerts`, `critical_alert_count`, `high_alert_count`,
    `medium_alert_count`, `low_alert_count`, `status_distribution` (dict of status → count),
    `asset_class_counts` (dict of asset class → count), and four ranked sections:
    `top_review_strategies`, `most_under_instrumented`, `strongest_evidence`,
    `deteriorating_trend_strategies`. Also: `deterministic_summary`, `suggested_next_steps`,
    `generated_at`.
  - `get_portfolio_overview(db, *, project_id, organization_id, include_archived, limit_per_section)` —
    assembles a full `PortfolioOverviewData` for the given scope.

- **Four ranked sections**:
  - `top_review_strategies` — strategies needing review (critical first, then review, then watch),
    sorted by health status urgency.
  - `most_under_instrumented` — strategies with lowest coverage scores (ascending), highlighting
    where evidence is missing.
  - `strongest_evidence` — strategies with highest coverage scores and no open alerts, sorted
    descending by coverage score.
  - `deteriorating_trend_strategies` — strategies where any trend series has `any_deteriorating=True`.

- **New endpoint** `GET /api/portfolio/overview`:
  - Query params: `project_id` (UUID, optional), `organization_id` (UUID, optional),
    `include_archived` (bool, default false), `limit_per_section` (int, default 10, max 50).
  - Returns `PortfolioOverviewResponse`. Read-only — no `AuditTimelineEvent` created.

- **New router** `backend/app/api/routes/portfolio.py` registered in `app/api/router.py`.

- **Aggregation fields**:
  - Average health/reliability/coverage scores across all scored strategies (null when no data).
  - Status distribution counts across all five health status values.
  - Per-asset-class strategy counts.
  - Total and per-severity open alert counts.

- **Deterministic summary and suggested next steps**: rule-based text, no AI, no causal claims,
  not investment advice. `note` field in response confirms this.

- **New schema file** `app/schemas/portfolio_overview.py` —
  `PortfolioTrendFlags`, `PortfolioStrategyItem`, `PortfolioOverviewResponse`.

- **New page** `frontend/src/pages/Portfolio.tsx` at route `/portfolio`:
  - Summary strip: active strategy count, average health score, average coverage score, total
    open alerts.
  - Health status distribution panel showing counts by status.
  - Four ranked sections displayed as card lists.
  - Full portfolio table with per-strategy health, reliability, coverage, alert counts, and
    trend flag indicators.
  - Suggested checks panel.

- **Navigation**: "Portfolio" item added under the Analysis section in `nav.ts`.

- **Dashboard**: compact Portfolio Overview panel added to `Dashboard.tsx` with key stats
  (strategy count, average health score, critical alert count, suggested next steps count).

- **Strategies page**: "Portfolio View" button added to `Strategies.tsx` linking to `/portfolio`.

- **19 new backend tests** (`tests/test_portfolio_m32.py`) across 3 test classes:
  - `TestPortfolioEndpoint` (12 tests): 200 response, response fields, seeded strategy present,
    archived exclusion, include_archived param, limit_per_section, project_id filter,
    health status counts, asset class counts, deterministic summary not investment advice,
    no timeline event created, read-only.
  - `TestPortfolioRankings` (4 tests): top_review includes critical strategies, under-instrumented
    sorted by coverage ascending, strongest evidence has high coverage, deteriorating trends
    requires two data points.
  - `TestPortfolioAggregation` (3 tests): averages null when no evidence, alert totals correct,
    suggested next steps deterministic.

- **Backend total: 1013 passed, 1 skipped.**
- **Zero TypeScript errors**, clean production build (62 modules, built in 625ms).
- No external APIs required. Read-only. Not investment advice.

### What M32 does NOT build (by design)

- No portfolio optimization, allocation suggestions, or rebalancing recommendations.
- No P&L attribution or return decomposition.
- No live drift detection or position-level monitoring.
- No AI-generated summaries or recommendations.
- No historical persistence of portfolio snapshots (computed on demand).

### Portfolio overview curl example

```bash
# Get full portfolio overview
curl "http://localhost:8000/api/portfolio/overview" | python3 -m json.tool
# Response: { strategy_count, active_strategy_count, average_health_score,
#   average_reliability_score, average_coverage_score, total_open_alerts,
#   critical_alert_count, high_alert_count, medium_alert_count, low_alert_count,
#   status_distribution, asset_class_counts,
#   top_review_strategies: [...], most_under_instrumented: [...],
#   strongest_evidence: [...], deteriorating_trend_strategies: [...],
#   deterministic_summary, suggested_next_steps: [...], note, generated_at }

# Filter by project
curl "http://localhost:8000/api/portfolio/overview?project_id=<project_id>" \
  | python3 -m json.tool

# Include archived strategies, limit sections to 5
curl "http://localhost:8000/api/portfolio/overview?include_archived=true&limit_per_section=5" \
  | python3 -m json.tool
```

> **M32 note:** Portfolio overview is deterministic — aggregated from existing per-strategy
> health, reliability, coverage, and trend records. No AI, no live market data, no external calls.
> Not investment advice.

---

## Previously completed — M31: Strategy Evidence Export v1

**Status: complete.**

### M31 deliverables

- **New `backend/app/services/strategy_export.py`** — `generate_strategy_export()` collects from all
  existing M27–M30 services (health, reliability, coverage, trends, run history, alerts, timeline,
  reports) and assembles a structured export. No AI, no external APIs, read-only.

- **New endpoint** `GET /api/strategies/{id}/export`:
  - Query params: `format` (`json` or `markdown`), `include_raw_json` (bool, default false),
    `limit_recent_runs` (int), `limit_timeline_events` (int).
  - 404 for unknown strategy. 400 for invalid format. Read-only — no `AuditTimelineEvent` created.

- **Export content — 9 sections**:
  identity, health, reliability, coverage, trends, run history, alerts, timeline, reports, and
  suggested checks.

- **JSON format** — `StrategyExportResponse` with `metadata` + `sections` array. Each section has:
  `section_key`, `title`, `summary`, `severity`, `evidence_json`.

- **Markdown format** — same response envelope but adds a `content` string with a complete formatted
  Markdown document.

- **Filename** — `quantfidelity_{slug}_evidence_export_{timestamp}.json` or `.md` (included in
  response metadata for client-side download).

- **Deterministic** — no AI, no causal claims, not investment advice. `metadata.note` confirms this.

- **New schema file** `app/schemas/strategy_export.py` —
  `StrategyExportSection`, `StrategyExportMetadata`, `StrategyExportResponse`.

- **Frontend — `ExportPanel`** in `StrategyDetail.tsx`:
  - "Export JSON" and "Export Markdown" buttons — download via `Blob`.
  - "Copy Markdown" button for markdown format.
  - Section severity summary displayed in panel.

- **24 new backend tests** (`tests/test_evidence_export_m31.py`).
- **Backend total: 994 passed, 1 skipped.**
- **Zero TypeScript errors**, clean production build (61 modules, built in 793 ms).
- No external APIs required. Read-only. Not investment advice.

### What M31 does NOT build (by design)

- No PDF export.
- No scheduled exports or email delivery.
- No cloud storage integration.
- No AI-written summaries.

### Evidence export curl example

```bash
# JSON export (default)
curl "http://localhost:8000/api/strategies/<strategy_id>/export" | python3 -m json.tool
# Response: { metadata: { export_id, strategy_slug, filename, note, generated_at, ... },
#   sections: [ { section_key, title, summary, severity, evidence_json }, ... ] }

# Markdown export with raw evidence
curl "http://localhost:8000/api/strategies/<strategy_id>/export?format=markdown&include_raw_json=true" \
  | python3 -m json.tool
```

> **M31 note:** Export is deterministic — assembled from existing logged evidence with no AI inference.
> Not investment advice.

---

## Previously completed — M30: Evidence Trend Panels v1

**Status: complete.**

### M30 deliverables

- **New `backend/app/services/evidence_trends.py`** — deterministic evidence trend computation service.
  No AI, no live market data, no external calls:
  - `TrendPointData` dataclass — individual data point: `value`, `label`, `recorded_at`.
  - `TrendSummaryData` dataclass — per-series summary: `latest_value`, `previous_value`, `delta`,
    `direction` (`improving` / `deteriorating` / `flat` / `insufficient_history`), `point_count`,
    `min`, `max`, `average`, `latest_label`, `latest_at`, `deterministic_summary`.
  - `StrategyEvidenceTrendsData` dataclass — top-level response: four trend series, `coverage_current`
    snapshot, `overall_summary`, `suggested_checks`.
  - **Trend direction rules**: delta > 2 → `improving`; delta < -2 → `deteriorating`; else `flat`;
    fewer than 2 data points → `insufficient_history`.
  - **Deterministic summaries** — example: `"Reliability score improved from 65 to 82 (+17) across
    4 data points."` No causal claims. Not investment advice.

- **Four trend series** computed from existing logged evidence:
  - **Reliability score** — from reliability score records.
  - **Data health** — from linked dataset snapshots (health scores over time).
  - **Backtest trust** — from backtest audit records.
  - **Signal quality** — from signal snapshot records.

- **New endpoint** `GET /api/strategies/{id}/evidence-trends`:
  - Query param: `limit_per_series` (default 20, max 100).
  - Returns `StrategyEvidenceTrendsData` — all four trend series, coverage snapshot,
    overall summary, and suggested checks for missing evidence.
  - 404 for unknown strategy. Read-only — no timeline event created.

- **New schema file** `app/schemas/evidence_trends.py`:
  `TrendPoint`, `TrendSummary`, `EvidenceTrendsResponse`.

- **Frontend — `EvidenceTrendsPanel`** in `StrategyDetail.tsx`:
  - Four `TrendPanel` sub-components, one per trend series.
  - **`MiniSparkline`** — div-based bar visualization (no chart library required).
  - Direction badge (improving / deteriorating / flat / insufficient_history).
  - Delta chip showing numeric change with sign.
  - Suggested checks panel for missing evidence series.

- **17 new backend tests** (`tests/test_evidence_trends_m30.py`).
- **Backend total: 970 passed, 1 skipped.**
- **Zero TypeScript errors**, clean production build (61 modules).
- No external APIs required. Read-only. Not investment advice.

### What M30 does NOT build (by design)

- No chart library — sparklines use plain CSS/div bars.
- No historical coverage trend series (evidence coverage score over time).
- No AI forecasts or predictive trend analysis.
- No multi-strategy trend comparison view.

### Evidence trends curl example

```bash
# Get evidence trend series for a strategy
curl "http://localhost:8000/api/strategies/<strategy_id>/evidence-trends" | python3 -m json.tool
# Response: { strategy_id, reliability_score: { points, summary }, data_health: { ... },
#   backtest_trust: { ... }, signal_quality: { ... }, coverage_current, overall_summary,
#   suggested_checks: [...], generated_at }

# Limit to 10 points per series
curl "http://localhost:8000/api/strategies/<strategy_id>/evidence-trends?limit_per_series=10" \
  | python3 -m json.tool
```

> **M30 note:** Trend computation is deterministic — built from existing logged evidence records.
> Delta and direction rules are rule-based. No AI, no live market data, no external calls.
> Not investment advice.

---

## Previously completed — M29: Strategy Run History + Timeline Drill-Down

**Status: complete.**

### M29 deliverables

- **New `backend/app/services/strategy_run_history.py`** — enriched per-run evidence service.
  No AI, no live market data, no external calls:
  - Returns each strategy run enriched with: dataset health score, signal quality score,
    universe symbol count, backtest trust score, version label, and `has_*` evidence flags
    (`has_dataset_snapshot`, `has_signal_snapshot`, `has_universe_snapshot`, `has_backtest_audit`).
  - **Run health label** (evaluated in order):
    - `strong`: all evidence present AND all scores >= 80.
    - `usable`: at least one evidence piece present AND no individual score is weak (< 75).
    - `review`: any score < 75 OR missing expected evidence.
    - `weak`: any individual score < 50.
    - `insufficient_evidence`: no evidence linked to the run.
  - **Evidence status filter**: `missing_dataset` / `missing_signal` / `missing_universe` /
    `missing_audit` / `complete` / `review` / `weak`.
  - **Run history summary fields**: `total_runs`, `strong_count`, `usable_count`,
    `review_count`, `weak_count`, `insufficient_count`, runs missing each evidence type
    (`runs_missing_dataset`, `runs_missing_signal`, `runs_missing_universe`,
    `runs_missing_audit`), `latest_run_at`.

- **New `backend/app/services/strategy_timeline.py`** — timeline enrichment service.
  No AI, no external calls:
  - Enriches each timeline event with `evidence_category` (one of: `run` / `data` /
    `backtest` / `config` / `universe` / `signal` / `reliability` / `report` / `alert` /
    `ingestion` / `other`), `source_label` (human-readable event source), and
    `linked_url_hint` (relative path hint for deep-linking).
  - **Timeline drilldown summary**: `total_events`, `event_type_counts` (dict),
    `source_type_counts` (dict), `latest_event_at`.

- **2 new API endpoints** registered in `app/api/routes/strategies.py`:
  - `GET /api/strategies/{id}/run-history` — returns enriched run list with health labels
    and summary. Supports `evidence_status` filter, `limit`, `offset` query params.
    Returns `RunHistoryResponse`.
  - `GET /api/strategies/{id}/timeline/drilldown` — returns enriched timeline events with
    evidence categories and drilldown summary. Supports `event_type` filter, `limit`,
    `offset` query params. Returns `TimelineDrilldownResponse`.

- **New schema file** `app/schemas/run_history.py`:
  `RunHistoryEntry`, `RunHistorySummary`, `RunHistoryResponse`,
  `TimelineDrilldownEntry`, `TimelineDrilldownSummary`, `TimelineDrilldownResponse`.

- **Frontend — `RunHistoryPanel`** in `StrategyDetail.tsx`:
  - Summary chips showing counts by run health label (strong / usable / review / weak /
    insufficient_evidence).
  - Enriched run table with health label badge, version label, dataset health score,
    signal quality score, universe symbol count, backtest trust score, and missing
    evidence chips per run.

- **Frontend — `EvidenceTimelinePanel`** in `StrategyDetail.tsx`:
  - Compact event list with colored category dots per evidence category.
  - Category legend and event type / source type summary chips.
  - Drilldown summary: total events, latest event timestamp.

- **20 new backend tests** (`tests/test_run_history_m29.py`).
- **Backend total: 953 passed, 1 skipped.**
- **Zero TypeScript errors**, clean production build (61 modules).
- No external APIs required. Read-only — no new events created. Not investment advice.

### What M29 does NOT build (by design)

- No live execution drift detection or order-level run replay.
- No AI-generated summaries of run history.
- No cross-strategy run history comparison.
- No historical snapshot persistence of run health labels (computed on demand).

### Run history + timeline drilldown curl examples

```bash
# Get enriched run history for a strategy
curl "http://localhost:8000/api/strategies/<strategy_id>/run-history" | python3 -m json.tool
# Response: { strategy_id, summary: { total_runs, strong_count, usable_count,
#   review_count, weak_count, insufficient_count, runs_missing_dataset,
#   runs_missing_signal, runs_missing_universe, runs_missing_audit, latest_run_at },
#   items: [{ run_id, run_name, run_type, status, health_label, version_label,
#     dataset_health_score, signal_quality_score, universe_symbol_count,
#     backtest_trust_score, has_dataset_snapshot, has_signal_snapshot,
#     has_universe_snapshot, has_backtest_audit, created_at }], total, limit, offset }

# Filter by evidence status
curl "http://localhost:8000/api/strategies/<strategy_id>/run-history?evidence_status=missing_dataset" \
  | python3 -m json.tool

# Get enriched timeline drilldown for a strategy
curl "http://localhost:8000/api/strategies/<strategy_id>/timeline/drilldown" | python3 -m json.tool
# Response: { strategy_id, summary: { total_events, event_type_counts,
#   source_type_counts, latest_event_at }, items: [{ event_id, event_type,
#   evidence_category, source_label, linked_url_hint, created_at, metadata_json }],
#   total, limit, offset }

# Filter by event type
curl "http://localhost:8000/api/strategies/<strategy_id>/timeline/drilldown?event_type=strategy_run_logged" \
  | python3 -m json.tool
```

> **M29 note:** Run history enrichment and timeline drilldown are deterministic — computed
> from logged evidence records. No AI, no live market data, no external calls.
> Not investment advice.

---

## Previously completed — M28: Project Health + Scoped API Keys v1

**Status: complete.**

### M28 deliverables

- **New `backend/app/services/project_health.py`** — deterministic project health snapshot service.
  No AI, no live market data, no external calls:
  - `ProjectHealthSnapshot` dataclass — `project_id`, `name`, `status` (health status),
    `health_score` (0–100 or null), `strategy_count` (int), `scored_strategy_count` (int),
    `average_strategy_health_score` (float or null), `critical_strategy_count` (int),
    `review_strategy_count` (int), `watch_strategy_count` (int), `healthy_strategy_count` (int),
    `insufficient_strategy_count` (int), `open_alert_count` (int), `critical_alert_count` (int),
    `high_alert_count` (int), `medium_alert_count` (int), `low_alert_count` (int),
    `recent_ingestion_failure_count` (int), `generated_at`.
  - `compute_project_health(project, db)` — computes a `ProjectHealthSnapshot` for one project.
  - `get_projects_health(db, *, status_filter, limit, offset)` — returns a paginated list of
    snapshots across all projects.

- **Project health status rules** (evaluated in order):
  - `critical`: any strategy in the project is `critical`, OR the project has any `critical`-severity open alerts.
  - `review`: any strategy is `review`, OR average strategy health score < 60.
  - `watch`: any strategy is `watch`, OR average strategy health score between 60 and 75.
  - `healthy`: majority of strategies are `healthy` AND average strategy health score >= 75.
  - `insufficient_evidence`: no strategies in the project, or most strategies are unscored.

- **Project health score (0–100 or null)**:
  Base = average strategy health scores across all scored strategies in the project.
  Deductions: critical alert −20, high alert −10, medium alert −4, low alert −2 (per open alert of that severity).
  Ingestion failure penalty applied when recent SDK ingestion batches have failed status.
  Floor: 0.

- **2 new API endpoints** registered in `app/api/routes/projects.py`:
  - `GET /api/projects/health` — paginated health list across all projects.
    Supports `status` filter, `limit`, `offset` query params. Returns `ProjectHealthListResponse`.
    Literal path registered BEFORE `{project_id}` to avoid routing collision.
  - `GET /api/projects/{id}/health` — health snapshot for one project.
    Returns `ProjectHealthRead`. 404 for unknown project.

- **Project-scoped API key enforcement**:
  When `QF_REQUIRE_API_KEY_FOR_INGESTION=true`:
  - Keys with a `project_id` set can only ingest evidence bundles into strategies that belong to
    that specific project. Ingesting into a strategy in a different project returns 403.
  - Org-level keys (`project_id=null`) are allowed to ingest into any strategy across all projects.
  - `evidence:write` scope is required on the key; keys without this scope are rejected with 403.
  - Keys with empty `scopes_json` are still accepted (backward-compatible with M24 `ingest` scope).

- **API key creation infers `organization_id` from project** when only `project_id` is provided
  in the create request body, so callers do not need to look up the org ID separately.

- **`ApiKeyRead` schema extended** with `project_name: str | None` — populated when the key is
  project-scoped, null for org-level keys.

- **New schemas** (`app/schemas/strategy.py` and `app/schemas/project.py`):
  `ProjectHealthRead`, `ProjectHealthListResponse`.

- **Frontend — Project Health panel in `Dashboard.tsx`**:
  - Summary panel showing project count by health status (critical / review / watch / healthy /
    insufficient_evidence).
  - Per-project health score, strategy count, and alert count summary.
  - Links to individual project pages.

- **Frontend — improved API key scope display in `Settings.tsx`**:
  - Project-scoped keys show a "Project: <name>" label alongside the key prefix and status.
  - Scope hint text explains what each scope allows (e.g. `evidence:write` vs `ingest`).
  - SDK usage snippet shown in the Settings panel demonstrating how to pass a scoped key.

- **17 new backend tests** (`tests/test_project_health_m28.py`) across 3 test classes:
  - `TestProjectHealthEndpoint` (6 tests): seeded project has health snapshot, required fields
    present, 404 for unknown project, list endpoint 200, list total >= 1, list status filter.
  - `TestProjectHealthAggregation` (5 tests): no strategies returns insufficient_evidence,
    critical strategy makes project critical, strategy counts correct, average health score
    computed, recent failed ingestion counted.
  - `TestProjectScopedApiKey` (6 tests): project-scoped key can ingest into matching project,
    project-scoped key blocked for different project, org-level key can ingest any project,
    key missing evidence:write scope rejected, empty scopes allowed (backward-compat),
    infer org_id from project on key create.

- **Backend total: 933 passed, 1 skipped.**
- **Zero TypeScript errors**, clean production build (61 modules).
- No external APIs required; no additional API keys needed beyond existing QF keys.

### What M28 does NOT build (by design)

- No full RBAC system, teams/members hierarchy, or per-user permissions.
- No OAuth 2.0 or JWT token issuance.
- No automatic scope enforcement on read endpoints (only ingestion is gated).
- No per-key rate limiting or quota enforcement.
- No real-time project health polling or push notifications.
- No historical persistence of project health snapshots (computed on demand).

### Project health + scoped key curl examples

```bash
# Get project health snapshot for all projects
curl "http://localhost:8000/api/projects/health" | python3 -m json.tool

# Get health for a specific project
curl "http://localhost:8000/api/projects/<project_id>/health" | python3 -m json.tool
# Response: { project_id, name, status, health_score, strategy_count, scored_strategy_count,
#   average_strategy_health_score, critical_strategy_count, review_strategy_count,
#   watch_strategy_count, healthy_strategy_count, insufficient_strategy_count,
#   open_alert_count, critical_alert_count, high_alert_count, medium_alert_count,
#   low_alert_count, recent_ingestion_failure_count, generated_at }

# Create a project-scoped API key (org_id inferred from project automatically)
curl -s -X POST http://localhost:8000/api/api-keys \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "CI Pipeline Key — Project Alpha",
    "project_id": "<project_id>",
    "scopes": ["evidence:write"]
  }' | python3 -m json.tool
# Response includes "key": "qf_local_...", "project_name": "Project Alpha"

# Ingest with project-scoped key (when QF_REQUIRE_API_KEY_FOR_INGESTION=true)
curl -s -X POST http://localhost:8000/api/strategies/<strategy_id>/evidence-bundles \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer qf_local_...' \
  -d '{"strategy_run": {"run_name": "bt", "run_type": "backtest"}}' \
  | python3 -m json.tool
# If strategy belongs to a different project than the key's project_id → 403 Forbidden
```

> **M28 note:** Project health computation is deterministic — aggregated from per-strategy health
> snapshots and open alert counts. No AI, no live market data, no external calls.
> Project-scoped key enforcement applies only to evidence ingestion; all other endpoints remain
> unauthenticated for local development. Not investment advice.

---

## Previously completed — M27: Strategy Health Dashboard v1

**Status: complete.**

### M27 deliverables

- **New `backend/app/services/strategy_health.py`** — deterministic health snapshot service.
  No AI, no live market data, no external calls:
  - `StrategyHealthSnapshot` dataclass — `strategy_id`, `name`, `slug`, `status` (health status),
    `health_score` (0–100 or null), `reliability_score` (float or null), `reliability_status`
    (string or null), `coverage_score` (float or null), `open_alert_count` (int),
    `critical_alert_count` (int), `high_alert_count` (int), `medium_alert_count` (int),
    `low_alert_count` (int), `primary_concern` (deterministic text, no AI), `last_run_age_days`
    (float or null), `missing_evidence` (list of strings), `suggested_checks` (list of strings),
    `generated_at`.
  - `compute_strategy_health(strategy, db)` — computes a `StrategyHealthSnapshot` for one strategy.
  - `get_strategies_health(db, *, status_filter, limit, offset)` — returns a paginated list of
    snapshots across all active strategies.

- **Health status values**: `healthy` / `watch` / `review` / `critical` / `insufficient_evidence`.
  Computation rules (evaluated in order):
  - `critical`: open critical alert, OR reliability score < 35 OR backtest trust < 40.
  - `review`: open high alert, OR reliability status is `weak` or `review`, OR evidence coverage < 60.
  - `watch`: open low/medium alert, OR evidence coverage 60–75, OR last run > 30 days stale.
  - `healthy`: reliability status `good` or `excellent` AND evidence coverage ≥ 75.
  - `insufficient_evidence`: no reliability score AND evidence coverage < 20.

- **Health score (0–100 or null)**:
  Base = reliability score if available, else evidence coverage score if available, else null.
  Deductions: critical alert −30, high alert −20, medium alert −8, low alert −3.
  Staleness deductions: no runs −20, last run > 90 days −20, last run > 30 days −10.
  Floor: 0.

- **Primary concern**: deterministic text string, no AI. Derived from the most severe issue.

- **Missing evidence and suggested checks**: sourced from latest reliability score record.

- **2 new API endpoints** (`app/api/routes/strategies.py`):
  - `GET /api/strategies/health` — paginated health list across all active strategies.
    Supports `status` filter, `limit`, `offset` query params. Returns `StrategyHealthListResponse`.
  - `GET /api/strategies/{id}/health` — health snapshot for one strategy.
    Returns `StrategyHealthRead`. 404 for unknown strategy.

- **New Pydantic schemas** (`app/schemas/strategy.py`):
  `StrategyHealthRead`, `StrategyHealthListResponse`.

- **Frontend — `StrategyHealthCard`** in `StrategyDetail.tsx`:
  - Status badge (critical/review/watch/healthy/insufficient_evidence), health score,
    reliability score, evidence coverage score.
  - Alert count chips (critical/high/medium/low).
  - Primary concern text.
  - Last run age in days.
  - Missing evidence chips.

- **Frontend — health status column** in `Strategies.tsx`:
  - Health status badge added to the strategies table alongside the reliability column.

- **Frontend — Strategy Health summary panel** in `Dashboard.tsx`:
  - Summary panel showing count of strategies by health status.
  - Links to individual strategy pages.

- **15 new backend tests** (`tests/test_health_m27.py`) across 2 test classes:
  - `TestStrategyHealthEndpoint` (7 tests): seeded strategy has health, required fields present,
    404 for unknown strategy, list endpoint 200, list total matches, list has all fields,
    health status filter.
  - `TestHealthStatusLogic` (8 tests): insufficient_evidence with no runs, healthy status with
    seeded strategy, review with open high alert, critical with open critical alert,
    health score decreases with critical alert, watch with open low alert,
    missing evidence list populated, primary concern text with no runs.

- **Backend total: 916 passed, 1 skipped.**
- **Zero TypeScript errors**, clean production build (61 modules).
- No external APIs required; no API keys needed beyond existing QF keys.

### What M27 does NOT build (by design)

- No realtime polling or push notifications on health status change.
- No AI health assessment or recommendations.
- No historical trend tracking of health snapshots over time.
- No database persistence of health snapshots (computed on demand).

---

## Previously completed — M26: SDK Pandas + Research Workflow Helpers v1

**Status: complete.**

### M26 deliverables

No backend or frontend changes — SDK only.

- **New `quantfidelity/dataframe.py`** — pandas-optional DataFrame helpers:
  - `rows_from_table(data)` — accepts `list[dict]` or a pandas `DataFrame`; returns `list[dict]`.
    When pandas is installed, converts NaN → `None`, `datetime`/`Timestamp` → ISO 8601 string,
    and numpy scalar types → native Python int/float.
  - `is_dataframe_like(obj)` — returns `True` when `obj` is a pandas `DataFrame`.
  - `normalize_records(records)` — converts NaN/numpy scalars/datetimes in a `list[dict]`.
  - `validate_required_columns(data, required)` — raises `ValueError` if any required column
    is absent from the first record.
  - **Pandas is OPTIONAL**: works with `list[dict]` by default.
    Install DataFrame support: `pip install "quantfidelity[pandas]"`.

- **`EvidenceBundle` new methods** (all chainable, added to `bundle.py`):
  - `with_dataset_snapshot_from_table(label, data, **kwargs)` — calls `rows_from_table(data)`
    then `with_dataset_snapshot()`.
  - `with_signal_snapshot_from_table(label, data, **kwargs)` — calls `rows_from_table(data)`
    then `with_signal_snapshot()`.
  - `with_universe_from_symbols(label, symbols, **kwargs)` — thin wrapper around
    `with_universe_snapshot()`.
  - `with_backtest_run(run_name, **kwargs)` — shortcut with `run_type="backtest"`.
  - `with_research_run(run_name, **kwargs)` — shortcut with `run_type="research"`.

- **Bundle validation** — `EvidenceBundle` gains two new methods:
  - `validate()` → `list[str]` — returns a list of human-readable issue strings (empty = valid).
  - `raise_if_invalid()` → `None` — raises `QuantFidelityValidationError` if any issues exist.

- **`QuantResearchWorkflow`** — new high-level research workflow builder
  (`quantfidelity/workflow.py`, exported from `quantfidelity/__init__.py`):
  - `QuantResearchWorkflow(strategy_name, version_label)` — initialises with strategy name and
    version label.
  - `set_version(label, **kwargs)` — chainable version config.
  - `set_config(params, **kwargs)` — chainable config snapshot.
  - `set_universe(symbols, label=None, **kwargs)` — chainable universe.
  - `set_dataset(name, **kwargs)` — chainable dataset.
  - `set_signals(rows_or_df, label=None, **kwargs)` — chainable signal snapshot (accepts
    `list[dict]` or DataFrame via `rows_from_table`).
  - `set_backtest_result(metrics, **kwargs)` — chainable backtest run.
  - `set_research_result(metrics, **kwargs)` — chainable research run.
  - `enable_actions(**kwargs)` — chainable actions (default: `compute_reliability_score=True`).
  - `to_bundle()` → `EvidenceBundle` — assembles and returns the final bundle.
  - `__repr__` shows strategy name, version, and configured sections.

- **`QuantFidelityClient` additions**:
  - `ingest_bundle(strategy_id, bundle, **kwargs)` — alias for `ingest_evidence_bundle()`.
  - `validate_bundle(bundle)` → `list[str]` — SDK-side validation only; never calls the server.

- **CLI additions** (`qf` command):
  - `qf validate --file bundle.json` — validates a bundle JSON file; prints "Bundle is valid.
    No issues found." or lists issues; exits 0 / 1.
  - `qf ingest --validate-before-send` — runs `bundle.validate()` before sending; aborts on
    issues unless `--force` is also passed.

- **New examples** (`sdk/python/examples/`):
  - `research_workflow_aapl.py` — demonstrates `QuantResearchWorkflow` end-to-end; outputs a
    valid JSON bundle (strategy_version `v3.0.0`).
  - `pandas_usage.py` — demonstrates `rows_from_table`, `with_dataset_snapshot_from_table`,
    and `with_signal_snapshot_from_table` with plain `list[dict]`.

- **43 new SDK tests** (`sdk/python/tests/test_pandas_m26.py`), 3 skipped (pandas-optional
  DataFrame tests require `pandas` which is not installed in CI — expected behavior).
- **SDK total: 174 passed, 3 skipped.**
- No external APIs required; no API keys needed for local use.

### What M26 does NOT build (by design)

- No live data fetching, no market data integration.
- No automated Git commit/push from workflow.
- No Jupyter `.ipynb` execution or notebook integration.
- No PyPI publishing of the SDK.

---

## Previously completed — M25: SDK Ingestion Reliability v1

**Status: complete.**

### M25 deliverables

- **New DB table** `sdk_ingestion_batches` (migration `0014_m25_sdk_ingestion_batches.py`):

  | Column | Type | Notes |
  |---|---|---|
  | `id` | UUID PK | |
  | `strategy_id` | UUID FK strategies CASCADE | |
  | `idempotency_key` | String 255, unique | caller-supplied or auto-generated |
  | `request_hash` | String 64 | SHA-256 of bundle payload, excluding `idempotency_key` field |
  | `status` | String 20 | `pending` \| `completed` \| `failed` |
  | `response_json` | JSON, nullable | stored response on success |
  | `error_json` | JSON, nullable | stored error info on failure |
  | `created_at` | DateTime | |
  | `updated_at` | DateTime | |

- **Idempotency behavior**:
  - Same key + same payload → replay stored response (`idempotency_status="replayed"`).
  - Same key + different payload → 409 Conflict.
  - Failed batch → allow retry (status reset to `pending`, fresh attempt made).

- **Idempotency key sources** (header takes precedence):
  - `Idempotency-Key` HTTP header.
  - `idempotency_key` field in JSON body.

- **`request_hash`**: SHA-256 of bundle payload with the `idempotency_key` field excluded before hashing.

- **Response fields added** to `EvidenceBundleResponse`:
  - `idempotency_key` — key used for this request.
  - `idempotency_status` — `new` | `replayed` | `retried_after_failure`.
  - `ingestion_batch_id` — UUID of the `sdk_ingestion_batches` row.

- **SDK retry** (`sdk/python/quantfidelity/client.py`):
  - `ingest_evidence_bundle(strategy_id, bundle, *, retry=True, max_retries=3, backoff_seconds=0.5, idempotency_key=None, buffer_on_failure=False)`.
  - Retry on: connection errors, timeouts, 502/503/504. Exponential backoff (`backoff_seconds × 2^attempt`).
  - No retry on: 400, 401, 403, 404, 409, 422.
  - When `retry=True`, an idempotency key is auto-generated (UUID4) if not supplied, ensuring safe retries.

- **`buffer_on_failure=True`**: when all retries are exhausted, writes the bundle to `~/.quantfidelity/buffer.jsonl` instead of raising. No API key is stored in the buffer file.

- **New `buffer.py`** (`sdk/python/quantfidelity/buffer.py`): `LocalBuffer` class with:
  - `add(strategy_id, bundle_dict, idempotency_key)` — appends a JSONL record.
  - `list_records()` — returns all buffered records.
  - `clear()` — removes all records.
  - `flush(client)` — sends each record via the client, removes successes, keeps failures.

- **New client convenience methods**:
  - `client.buffer_evidence_bundle(strategy_id, bundle)` — force-buffer without attempting server.
  - `client.flush_buffer()` — flush all buffered records; returns `{"flushed": N, "failed": N, "remaining": N}`.
  - `client.list_buffered()` — returns list of buffered records.
  - `client.clear_buffer()` — removes all buffered records.

- **CLI additions** (`qf` command):
  - `qf ingest --idempotency-key <key>` — pass an explicit idempotency key.
  - `qf ingest --buffer-on-failure` — buffer locally if server is unreachable.
  - `qf buffer list` — show buffered records.
  - `qf buffer flush [--base-url URL]` — flush buffered records to server.
  - `qf buffer clear [--yes]` — clear buffer (requires `--yes` confirmation flag).

- **Frontend**: optional idempotency key field added to the Evidence Bundle Ingestion panel in `StrategyDetail.tsx`. When filled, the value is sent as the `Idempotency-Key` header. Response panel shows `idempotency_status` and `ingestion_batch_id`.

- **13 new backend tests** (`tests/test_ingestion_reliability_m25.py`):
  ingestion without key still works, batch created on ingestion with key, replay returns stored
  response, replay sets `idempotency_status=replayed`, replay does not duplicate run, different
  payload same key → 409, key from body works, header takes precedence over body,
  request_hash excludes idempotency_key field, failed batch allows retry,
  `idempotency_status=new` on first request, batch stores no raw API key, batch stores response_json.

- **21 new SDK tests** (`sdk/python/tests/test_reliability_m25.py`):
  idempotency key sent as header, retry=True generates key, no key when retry=False,
  retries on 503 then succeeds, no retry on 400/401/409, retries on connection error then
  buffers, buffer add creates record, buffer does not store API key, list_records empty,
  list_records returns added, clear removes all, flush sends and removes successful,
  flush preserves failed records, client buffer_on_failure writes to buffer,
  client list_buffered, client clear_buffer, CLI ingest passes idempotency key,
  CLI buffer list empty, CLI buffer clear with yes flag.

- **Backend total: 901 passed, 1 skipped.**
- **SDK total: 131 passed.**
- **Zero TypeScript errors**, clean build (61 modules).

### What M25 does NOT build (by design)

- No async server workers, Redis/Celery, or distributed job queues.
- No pandas/numpy helpers or DataFrames-to-dict conversion utilities.
- No PyPI publishing of the SDK.

---

## Previously completed — M24: API Key Foundation + SDK Auth

**Status: complete.**

### M24 deliverables

- **New table** `api_keys` (migration `0013_m24_api_keys.py`):

  | Column | Type | Notes |
  |---|---|---|
  | `id` | UUID PK | |
  | `organization_id` | UUID FK organizations CASCADE | |
  | `project_id` | UUID FK projects SET NULL, nullable | scope to project or org-wide |
  | `name` | String 255 | human-readable label |
  | `key_prefix` | String 16 | first 8 chars of raw key, stored plain for display |
  | `key_hash` | String 64 | SHA-256 of full raw key — raw key never stored |
  | `scopes_json` | JSON | list of scope strings, e.g. `["ingest"]` |
  | `status` | String 20 | `active` \| `revoked` |
  | `last_used_at` | DateTime, nullable | updated on each authenticated request |
  | `revoked_at` | DateTime, nullable | set when revoked |
  | `created_at` | DateTime | |
  | `updated_at` | DateTime | |

- **Key format**: `qf_local_<random>` for local development; `qf_live_<random>` for production environments. 40-character random suffix (URL-safe base64).
- **Storage**: SHA-256 hash only. Raw key is returned **once** at creation and never stored. If lost, revoke and create a new key.
- **3 new API endpoints** (`app/api/routes/api_keys.py`):
  - `POST /api/api-keys` — create a new API key. Returns `ApiKeyCreateResponse` including the raw `key` field (shown once only). Emits `api_key_created` timeline event.
  - `GET  /api/api-keys` — list all API keys for the default organization (never returns raw key or hash). Supports `status`, `project_id`, `limit`, `offset` query params.
  - `PATCH /api/api-keys/{id}/revoke` — revoke an active key. Sets `status=revoked`, `revoked_at=now`. Emits `api_key_revoked` timeline event. Returns 404 if key not found, 409 if already revoked.
- **Config** (`app/core/config.py`): `QF_REQUIRE_API_KEY_FOR_INGESTION=false` (default). When `true`, `POST /api/strategies/{id}/evidence-bundles` requires a valid active API key sent in `Authorization: Bearer <key>` or `X-QF-Api-Key: <key>` headers. All other endpoints remain unauthenticated.
- **Auth dependency** (`app/api/deps.py`): `require_api_key(request, db)` — extracts key from header, computes SHA-256, looks up matching active `api_key` record, updates `last_used_at`. Returns the `ApiKey` ORM object. Raises 401 for missing/invalid key, 403 for revoked key.
- **Timeline events**: `EventType.api_key_created`, `EventType.api_key_revoked` added to `constants.py`.
- **SDK activated** (`sdk/python/quantfidelity/client.py`): `api_key` parameter now sends `Authorization: Bearer <key>` header on every request. `QUANTFIDELITY_API_KEY` environment variable supported as fallback — set it and omit `api_key=` in the constructor.
- **Frontend**: new `Settings` page (`frontend/src/pages/Settings.tsx`) at route `/settings`:
  - API key management panel: create key form (name, optional project scope), key list table (name, prefix, status, last used, created), revoke button per active key.
  - Raw key shown once in a dismissible copy-to-clipboard panel immediately after creation. Warning: "This key will not be shown again."
  - "Settings" nav item added under Configuration section in `nav.ts`.
- **22 new backend tests** (`tests/test_api_keys_m24.py`):
  - Key creation, key listing, key revocation, duplicate revocation returns 409.
  - Auth enforcement when `QF_REQUIRE_API_KEY_FOR_INGESTION=true`: missing key → 401, invalid key → 401, revoked key → 403, valid key → 200.
  - Auth bypass when `QF_REQUIRE_API_KEY_FOR_INGESTION=false` (default): no key needed.
  - Timeline events emitted for create and revoke.
  - Key hash stored, raw key NOT stored in DB.
  - `last_used_at` updated on authenticated request.
- **Backend total at M24: 888 passed, 1 skipped.**
- **Zero TypeScript errors**, clean build (61 modules).
- **SDK tests at M24: 110 passed.**

### What M24 does NOT build (by design)

- No full auth system, OAuth 2.0, or JWT token issuance.
- No roles/permissions system or per-endpoint access control beyond the single ingestion gate.
- No production secrets manager (Vault, AWS Secrets Manager, etc.).
- No PyPI publishing of the SDK.
- No per-key rate limiting or quota enforcement.
- No key rotation with zero-downtime overlap window.

### API key curl examples

```bash
# Create an API key
curl -s -X POST http://localhost:8000/api/api-keys \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "CI Pipeline Key",
    "scopes": ["ingest"]
  }' | python3 -m json.tool
# Response includes "key": "qf_local_..." — copy this now, it will not be shown again.

# List all API keys (raw key never returned)
curl "http://localhost:8000/api/api-keys" | python3 -m json.tool

# Revoke a key
curl -s -X PATCH "http://localhost:8000/api/api-keys/<key_id>/revoke" \
  | python3 -m json.tool

# Ingest with auth (when QF_REQUIRE_API_KEY_FOR_INGESTION=true):
curl -s -X POST http://localhost:8000/api/strategies/<strategy_id>/evidence-bundles \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer qf_local_...' \
  -d '{"strategy_run": {"run_name": "bt", "run_type": "backtest"}}' \
  | python3 -m json.tool

# Alternative auth header:
curl -s -X POST http://localhost:8000/api/strategies/<strategy_id>/evidence-bundles \
  -H 'Content-Type: application/json' \
  -H 'X-QF-Api-Key: qf_local_...' \
  -d '{"strategy_run": {"run_name": "bt", "run_type": "backtest"}}' \
  | python3 -m json.tool
```

### SDK example with api_key parameter

```python
from quantfidelity import QuantFidelityClient, EvidenceBundle
import os

# Option 1: pass key directly
client = QuantFidelityClient(
    base_url="http://localhost:8000",
    api_key="qf_local_..."
)

# Option 2: use environment variable (recommended for CI)
# export QUANTFIDELITY_API_KEY=qf_local_...
client = QuantFidelityClient(base_url="http://localhost:8000")

bundle = (
    EvidenceBundle()
    .with_strategy_run("bt-2024-q1", run_type="backtest",
                       metrics_json={"sharpe": 1.4, "max_drawdown": -0.12})
    .with_actions(compute_reliability_score=True)
)
result = client.ingest_evidence_bundle("<strategy-uuid>", bundle)
print(result["summary"])
```

> **Security note:** Do not commit API keys to git. Use environment variables or a secrets manager.

> **M24 note:** API key authentication is opt-in via `QF_REQUIRE_API_KEY_FOR_INGESTION`. All
> other endpoints remain unauthenticated for local development. Key storage uses SHA-256 hash
> only — the raw key is never persisted. No AI, no live data, not investment advice.

---

## Previously completed — M23: Evidence Bundle Python SDK v1

**Status: complete.**

### M23 deliverables

- **New package** `sdk/python/` — a local pip-installable Python package named `quantfidelity`.
  Install with `cd sdk/python && pip install -e .` (editable) or `pip install -e ".[dev]"` for tests.
- **`EvidenceBundle` builder** (`sdk/python/quantfidelity/bundle.py`) — fluent chainable API
  for all 7 evidence sections plus `with_actions()`:
  `with_strategy_version()`, `with_config_snapshot()`, `with_universe_snapshot()`,
  `with_signal_snapshot()`, `with_dataset()`, `with_dataset_snapshot()`,
  `with_strategy_run()`, `with_actions()`.
  Serialise with `to_dict()` / `to_json(indent=2)`; load with `from_dict()` / `from_json()`.
  Lightweight client-side validation catches wrong types and empty required lists.
- **`QuantFidelityClient`** (`sdk/python/quantfidelity/client.py`):
  - `__init__(base_url, *, api_key=None, timeout=30)` — `api_key` reserved for M24+
  - `ingest_evidence_bundle(strategy_id, bundle)` — accepts `EvidenceBundle` or plain `dict`
  - `get_evidence_bundle_example(strategy_id)` — fetches sample payload from API
  - `health()` — GET `/health`
  - `api_root()` — GET `/api`
  - Uses `requests` library (sync HTTP)
- **Exception classes** (`sdk/python/quantfidelity/exceptions.py`):
  `QuantFidelityError` (base), `QuantFidelityConnectionError`, `QuantFidelityAPIError`
  (stores `status_code`, `response_text`, `response_json`), `QuantFidelityValidationError`
- **TypedDict annotations** (`sdk/python/quantfidelity/types.py`) — optional IDE type hints
  mirroring all M22 bundle schemas
- **CLI entry point** `qf` (`sdk/python/quantfidelity/cli.py`):
  - `qf ingest --strategy-id <uuid> --file bundle.json [--dry-run]`
  - `qf example --strategy-id <uuid> [--output out.json]`
  - `qf health`
  - `--base-url URL`, `--api-key KEY` global flags; exit 0 success, exit 1 error
- **Examples** (`sdk/python/examples/`):
  - `aapl_mean_reversion_bundle.py` — full 7-section bundle; prints payload by default;
    sends to server only when `RUN_QF_EXAMPLE=1` env var is set
  - `bundle.json` — static JSON copy of the full AAPL bundle payload
- **99 SDK tests** (`sdk/python/tests/`) with no server required:
  - `test_bundle.py` (53 tests): all section setters, validation errors, chaining,
    serialisation round-trips, section management, repr, equality
  - `test_client.py` (28 tests): construction, URL building, ingest + error paths,
    example + health endpoints (uses `responses` mock)
  - `test_cli.py` (18 tests): argparse, dry-run, file errors, success path, connection
    errors, example/health commands (uses `unittest.mock`)
- **`sdk/python/README.md`** — full SDK documentation
- **866 backend tests** still pass (no backend changes in M23), 1 skipped.
- **Zero TypeScript errors**, clean frontend build (no frontend changes in M23).

### SDK install & quick start

```bash
# Install locally (from repo root):
cd sdk/python
pip install -e .           # runtime only
pip install -e ".[dev]"   # + pytest + responses + pytest-mock

# Run SDK tests:
pytest -v          # 99 passed, 0 failed

# Quick start:
from quantfidelity import QuantFidelityClient, EvidenceBundle
client = QuantFidelityClient(base_url="http://localhost:8000")
bundle = (
    EvidenceBundle()
    .with_strategy_run("bt-2024-q1", run_type="backtest",
                       metrics_json={"sharpe": 1.4, "max_drawdown": -0.12})
    .with_actions(compute_reliability_score=True)
)
result = client.ingest_evidence_bundle("<strategy-uuid>", bundle)
print(result["summary"])
```

### CLI usage

```bash
# Ingest a bundle from a JSON file:
qf ingest --strategy-id <uuid> --file sdk/python/examples/bundle.json

# Dry-run: parse and print without sending:
qf ingest --strategy-id <uuid> --file bundle.json --dry-run

# Fetch and save an example payload:
qf example --strategy-id <uuid> --output my_bundle.json

# Check server health:
qf health

# Custom server:
qf --base-url http://qf.myteam.internal ingest --strategy-id <uuid> --file bundle.json
```

### What M23 does NOT build (by design)

- No PyPI publish — local editable install only.
- No API key authentication — `api_key` parameter reserved for M24+.
- No async support — synchronous `requests` only.
- No automatic Git detection — git info supplied manually.
- No pandas/numpy helpers — DataFrames converted to `list[dict]` by the user.
- No retry or offline buffering — connection errors raise immediately.

> **M23 note:** This SDK is the foundation for future milestones (auth, async, pandas helpers,
> PyPI release, CI integration).  Wraps the M22 evidence bundle endpoint directly —
> deterministic, no AI, no live data, not investment advice.

---

## Previously completed — M22: Evidence Ingestion Bundle v1

**Status: complete.**

### M22 deliverables

- **2 new API endpoints** registered in `app/api/routes/evidence.py` (alongside the existing M21
  coverage endpoint):
  - `POST /api/strategies/{strategy_id}/evidence-bundles` — ingest a structured evidence bundle
    in a single all-or-nothing DB transaction. Accepts up to 7 evidence sections plus an optional
    `actions` block. Returns `EvidenceBundleResponse` with created/reused counts, objects map,
    alerts generated, warnings, and `generated_at`.
  - `GET  /api/strategies/{strategy_id}/evidence-bundles/example` — returns a pre-filled
    example `EvidenceBundleRequest` payload seeded from the strategy's own existing evidence
    (versions, config snapshots, universe snapshots, signal snapshots, datasets). Useful for
    SDK scaffolding and interactive exploration. Registered BEFORE the POST route. Read-only —
    no audit event.
- **`app/services/evidence_ingestion.py`** — new deterministic ingestion service.
  No AI, no live market data, no external calls:
  - `ingest_evidence_bundle(strategy_id, bundle, db)` — processes sections in dependency order
    and returns an `EvidenceBundleResult` dataclass. The route handler commits; the service does
    not call `db.commit()`.
  - **Section processing order** (dependency-respecting):
    1. `strategy_version` — reused if `version_label` already exists on this strategy; created
       otherwise.
    2. `config_snapshot` — always created fresh when present; linked to reused or new version.
    3. `universe_snapshot` — always created; normalizes symbols (uppercase + sort); computes
       SHA-256 `universe_hash`.
    4. `signal_snapshot` — always created; normalizes rows; computes SHA-256 `signal_hash` and
       quality score.
    5. `dataset` — reused if a dataset with the same `name` already exists in the strategy's
       project; created otherwise.
    6. `dataset_snapshot` — always created; runs all 10 data-quality checks; computes health
       score.
    7. `strategy_run` — always created; linked to all snapshots and dataset snapshot created
       above.
  - **Reuse logic**: `strategy_version` reused if `version_label` already exists for this
    strategy. `dataset` reused if `name` already exists in the same project.
    Reused objects increment `reused_count`; new objects increment `created_count`.
  - **Transaction behaviour**: all sections are added to one DB session. If any section raises
    an unexpected exception, the entire transaction rolls back and the endpoint returns 500.
    Individual per-section errors (e.g., bad FK reference) raise 422 before any writes occur.
    Optional `actions` failures add warnings but do not roll back the rest of the transaction.
  - **Actions** (all optional, run after all sections are persisted):
    - `run_backtest_audit` — runs the M8/M13 backtest reality check on the newly created run
      (only applies to backtest/research/paper run types).
    - `compute_reliability_score` — computes and stores a fresh reliability score for the strategy.
    - `generate_strategy_report` — generates a strategy reliability report.
    - `generate_alerts` — runs the M11 alert generation engine for the default org.
  - **New `EventType.evidence_bundle_ingested`** added to `app/core/constants.py`. Exactly one
    audit timeline event is created per bundle call (after all sections and actions succeed).
    Event metadata includes section counts, actions run, and warnings summary.
  - `EvidenceBundleResult` dataclass fields: `strategy_id`, `created_count`, `reused_count`,
    `actions_run`, `objects` (per-section `{id, name, type, status}` or `None`),
    `alerts_generated`, `warnings`, `summary`, `timeline_events_created`, `generated_at`.
- **New Pydantic schemas** (`app/schemas/evidence_ingestion.py`):
  `StrategyVersionBundleSection`, `ConfigSnapshotBundleSection`,
  `UniverseSnapshotBundleSection`, `SignalSnapshotBundleSection`, `DatasetBundleSection`,
  `DatasetSnapshotBundleSection`, `StrategyRunBundleSection`, `EvidenceBundleActions`,
  `EvidenceBundleRequest`, `EvidenceBundleObjectRef`, `EvidenceBundleObjects`,
  `EvidenceBundleResponse`.
- **23 new backend tests** (`tests/test_evidence_ingestion_m22.py`) across multiple test classes:
  - Bundle with all sections creates objects and returns correct counts.
  - Reuse logic: strategy_version reused when label exists; dataset reused when name matches.
  - All-or-nothing transaction: partial bundles (only version, only run, etc.) succeed.
  - Actions: `run_backtest_audit` appended to `actions_run`; `compute_reliability_score`,
    `generate_strategy_report`, `generate_alerts` each tested.
  - Timeline event created with `evidence_bundle_ingested` event type.
  - Example endpoint returns valid `EvidenceBundleRequest` shape.
  - 404 for unknown strategy on both POST and GET example endpoints.
  - `created_count` and `reused_count` correctly track object lifecycle.
  - Warnings list populated when optional action fails gracefully.
- **866 total backend tests** (843 prior M2–M21 + 23 new), 1 skipped.
- **Frontend types** (`frontend/src/types/index.ts`):
  `EvidenceBundleObjectRef`, `EvidenceBundleObjects`, `EvidenceBundleActions`,
  `StrategyVersionBundleSection`, `ConfigSnapshotBundleSection`,
  `UniverseSnapshotBundleSection`, `SignalSnapshotBundleSection`, `DatasetBundleSection`,
  `DatasetSnapshotBundleSection`, `StrategyRunBundleSection`, `EvidenceBundleRequest`,
  `EvidenceBundleResponse` interfaces added.
- **Frontend API** (`frontend/src/lib/api.ts`): `ingestEvidenceBundle(strategyId, payload)` and
  `getEvidenceBundleExample(strategyId)` added.
- **`StrategyDetail.tsx` updated** — "Ingest Evidence" panel added:
  - "Load Example" button populates a JSON textarea with the strategy-specific example payload
    from `GET .../evidence-bundles/example`.
  - JSON textarea — editable, validated client-side before submit.
  - "Ingest Bundle" submit button — calls `POST .../evidence-bundles`; shows spinner.
  - Result panel: summary text, created/reused counts, actions run list, alerts generated,
    warnings list (if any), and a per-section objects table (section name, status, id prefix).
  - On success, calls `setRefreshKey((k) => k + 1)` to reload strategy detail.
- **Zero TypeScript errors**, clean production build (61 modules, 384.81 kB JS bundle).

### Evidence Bundle sections

| Section | Reuse policy | Key fields |
|---|---|---|
| `strategy_version` | Reused if `version_label` already exists on this strategy | `version_label`, `git_commit`, `branch_name`, `signal_name` |
| `config_snapshot` | Always created | `label`, `config_json`, `strategy_version_id` (auto-linked) |
| `universe_snapshot` | Always created | `label`, `symbols` (normalized), `source_type` |
| `signal_snapshot` | Always created | `label`, `rows`, `signal_column`, `signal_name` |
| `dataset` | Reused if `name` already exists in this project | `name`, `dataset_type`, `source_type` |
| `dataset_snapshot` | Always created | `version_label`, `rows` (data quality checked) |
| `strategy_run` | Always created | `run_name`, `run_type`, `metrics_json`, `params_json`, `assumptions_json` |

### What M22 does NOT build (by design)

- No Python SDK package, no published `pip install quantfidelity` distribution.
- No API key authentication or per-client rate limiting.
- No async ingestion queue or background workers.
- No streaming responses or real-time progress notifications.
- No AI-generated summaries or smart field suggestions.
- No duplicate-bundle detection (same evidence can be ingested multiple times — callers control idempotency).

### Note: foundation for future Python SDK

`POST /api/strategies/{strategy_id}/evidence-bundles` is the intended call target for a future
`quantfidelity` Python SDK. The bundle schema maps directly to what a `StrategyEvidenceBundle`
class would submit from a research notebook or CI pipeline. M22 builds only the server-side
receiver; the SDK package is a separate future milestone.

### Sample curl

```bash
# Ingest an evidence bundle for a strategy
curl -s -X POST http://localhost:8000/api/strategies/<strategy_id>/evidence-bundles \
  -H 'Content-Type: application/json' \
  -d '{
    "strategy_version": {
      "version_label": "v1.2.0",
      "branch_name": "main",
      "signal_name": "momentum_12m"
    },
    "config_snapshot": {
      "label": "prod-config-2024-Q1",
      "config_json": {
        "params": {"lookback": 252, "threshold": 0.05},
        "assumptions": {"transaction_cost_bps": 10}
      }
    },
    "universe_snapshot": {
      "label": "SP500-2024-Q1",
      "symbols": ["AAPL", "MSFT", "GOOG", "AMZN"]
    },
    "signal_snapshot": {
      "label": "momentum-12m-2024-Q1",
      "signal_name": "momentum_12m",
      "rows": [
        {"symbol": "AAPL", "timestamp": "2024-01-01", "signal": 0.52},
        {"symbol": "MSFT", "timestamp": "2024-01-01", "signal": 0.78}
      ]
    },
    "dataset": {
      "name": "SP500 Daily OHLCV",
      "dataset_type": "ohlcv",
      "source_type": "manual"
    },
    "dataset_snapshot": {
      "version_label": "v2024-Q1",
      "rows": [
        {"symbol": "AAPL", "timestamp": "2024-01-02", "close": 187.1, "volume": 52000000},
        {"symbol": "MSFT", "timestamp": "2024-01-02", "close": 374.0, "volume": 28000000}
      ]
    },
    "strategy_run": {
      "run_name": "Momentum Backtest 2024-Q1",
      "run_type": "backtest",
      "status": "completed",
      "metrics_json": {"sharpe": 1.4, "annual_return": 0.18, "max_drawdown": -0.12},
      "assumptions_json": {"transaction_cost_bps": 10, "fill_model": "close"}
    },
    "actions": {
      "run_backtest_audit": true,
      "compute_reliability_score": true
    }
  }' | python3 -m json.tool
# Response:
# {
#   "strategy_id": "...",
#   "created_count": 7,
#   "reused_count": 0,
#   "actions_run": ["run_backtest_audit", "compute_reliability_score"],
#   "objects": {
#     "strategy_version": {"id": "...", "name": "v1.2.0", "type": "strategy_version", "status": "created"},
#     "strategy_run": {"id": "...", "name": "Momentum Backtest 2024-Q1", "type": "strategy_run", "status": "created"},
#     ...
#   },
#   "alerts_generated": 0,
#   "warnings": [],
#   "summary": "Ingested 7 objects (7 created, 0 reused). Actions run: run_backtest_audit, compute_reliability_score.",
#   "generated_at": "2026-06-01T..."
# }

# Get an example bundle payload pre-filled from existing strategy evidence
curl "http://localhost:8000/api/strategies/<strategy_id>/evidence-bundles/example" \
  | python3 -m json.tool
```

> **M22 note:** The ingestion service is deterministic — no AI, no live market data, no external
> calls. All evidence is logged from the caller-supplied payload. Not investment advice.

---

## Previously completed — M21: Evidence Coverage Matrix v1

**Status: complete.**

### M21 deliverables

- **1 new API endpoint** — `GET /api/evidence/coverage` in new `app/api/routes/evidence.py`.
  Returns a paginated evidence coverage matrix for all non-archived strategies by default.
  Query params: `include_archived`, `asset_class`, `status`, `limit` (1–500, default 100),
  `offset`. Read-only — no audit timeline event created.
- **`app/services/evidence_coverage.py`** — new deterministic coverage service.
  No AI, no live market data, no external calls:
  - `get_evidence_coverage_matrix(db, *, include_archived, asset_class, status, limit, offset)` —
    for every matched strategy, computes coverage across 11 evidence layers and returns a
    paginated `EvidenceCoverageMatrixData` with per-row rows and aggregate summary.
  - **11 evidence columns** with deterministic status per column:
    `strategy_runs`, `backtest_runs`, `dataset_evidence`, `backtest_audits`,
    `config_snapshots`, `universe_snapshots`, `signal_snapshots`, `alerts`,
    `reports`, `reliability_scores`, `timeline_events`.
  - **Cell statuses**: `complete` | `partial` | `review` | `missing`.
  - **Coverage score** (0–100): average of per-cell status weights × 100.
    `complete=1.0`, `partial=0.6`, `review=0.4`, `missing=0.0`.
  - **Per-column status rules** (key examples):
    - `strategy_runs`: complete if ≥2 runs, partial if 1, missing if 0.
    - `backtest_runs`: complete if ≥1 backtest run, missing otherwise.
    - `dataset_evidence`: complete if ≥1 run linked to a snapshot with min health ≥75;
      review if linked but min health < 75; missing if no linked snapshot.
    - `backtest_audits`: complete if any audit has trust_score ≥75; review if audits
      exist but avg trust < 75; missing if none.
    - `config_snapshots`, `universe_snapshots`: complete if ≥1 exists, missing otherwise.
    - `signal_snapshots`: complete if ≥1 and avg quality ≥75; review if exists but avg < 75.
    - `alerts`: complete if no open high/critical; review if high/critical open; partial if
      only low/medium open.
    - `reports`: complete if a `strategy_reliability` report exists; partial if any other
      report type exists; missing if no reports.
    - `reliability_scores`: complete if latest score is excellent/good; review if weak/review
      status; partial if `insufficient_evidence`; missing if no score.
    - `timeline_events`: complete if ≥3 events; partial if 1–2; missing if 0.
  - **Suggested next steps**: ordered list of `suggested_check` strings (missing first,
    then review, then partial) for each coverage row.
  - **Aggregate summary** over all matched strategies: `strategy_count`,
    `average_coverage_score`, cell counts by status, and `most_common_missing_evidence`
    (up to 5 labels, most common first).
  - `Alert.strategy_id` is `String(36)` — queries use `str(uuid_val)`.
- **New Pydantic schemas** (`app/schemas/evidence_coverage.py`):
  `EvidenceCoverageCell`, `StrategyEvidenceCoverageRow`, `EvidenceCoverageSummary`,
  `EvidenceCoverageMatrixResponse`.
- **58 new backend tests** (`tests/test_evidence_m21.py`) across 4 test classes:
  - `TestEvidenceCoverageEndpoint` (16 tests): 200 response, envelope fields, column presence,
    cell fields, cell status validity, score in range, seeded strategy present,
    include_archived filter, asset_class filter, status filter, pagination limit/offset,
    suggested_next_steps is list, most_common_missing is list.
  - `TestEvidenceCoverageService` (33 tests): per-column status rules for all 11 columns —
    strategy_runs (missing/partial/complete), backtest_runs (missing/complete),
    dataset_evidence (missing), backtest_audits (missing/complete/review),
    config_snapshots (missing/complete), universe_snapshots (missing/complete),
    signal_snapshots (missing/complete/review), alerts (complete/review-high/review-critical/
    partial-medium/partial-low), reports (missing/complete/partial), reliability_scores
    (missing/partial-insufficient/review-weak/review-review/complete-good/complete-excellent),
    timeline events (missing/complete).
  - `TestCoverageScoreFormula` (6 tests): all-complete=100, all-missing=0, all-partial=60,
    all-review=40, empty=0, mixed calculation.
  - `TestEvidenceCoverageSummary` (4 tests): strategy_count matches total, average in range,
    cell counts sum to strategy_count×11, service average correct.
- **843 total backend tests** (785 prior M2–M20 + 58 new), 1 skipped.
- **Frontend types** (`frontend/src/types/index.ts`): `EvidenceCoverageCell`,
  `StrategyEvidenceCoverageRow`, `EvidenceCoverageSummary`, `EvidenceCoverageMatrixResponse`,
  `EvidenceCoverageParams` interfaces added.
- **Frontend API** (`frontend/src/lib/api.ts`): `getEvidenceCoverage(params?)` added.
- **New page** `frontend/src/pages/EvidenceCoverage.tsx` at route `/evidence/coverage`:
  - Summary cards: Strategies, Avg Coverage, Missing Cells, Review Cells.
  - Filter bar: asset_class and strategy status dropdowns; both trigger live reload.
  - Matrix table: Strategy (name + asset + status badges), Coverage (score + progress bar),
    11 evidence column cells (coloured dot + count). Each cell coloured by status.
  - **Click-to-expand row** — reveals per-cell summary text, latest_at timestamps, and
    suggested next steps ordered by priority (missing → review → partial).
  - Under-instrumented panel: bottom-5 strategies by coverage score (scores < 80).
  - Most Common Missing Evidence panel: top 5 most-missing evidence labels from summary.
  - Legend: complete (teal) / partial (amber) / review (orange) / missing (muted).
  - Score thresholds: ≥80 teal, ≥50 amber, ≥25 orange, <25 red.
  - "Compare Strategies" link in page header.
  - No chart libraries used.
- **`App.tsx`** — `EvidenceCoverage` route at `evidence/coverage`.
- **`nav.ts`** — "Evidence Matrix" item added under Analysis section.
- **`Strategies.tsx`** — "Evidence Matrix" secondary button added to PageHeader.
- **`Dashboard.tsx`** — "Instrumentation Coverage" quick card inserted between the
  reliability pillars strip and evidence counters. Shows avg coverage score, complete/
  missing/review cell counts, and most-common-missing chips. Links to `/evidence/coverage`.
- **Zero TypeScript errors**, clean production build (61 modules, ≈379 kB JS bundle).

### Evidence coverage scoring formula

```
status_weights = { complete: 1.0, partial: 0.6, review: 0.4, missing: 0.0 }
evidence_coverage_score = mean(status_weights[cell.status] for cell in 11_columns) × 100
```

All scores are deterministic — computed from existing logged evidence, not estimated or
AI-generated.

### What M21 does NOT build (by design)

- No AI recommendations or auto-fix suggestions.
- No automatic instrumentation ingestion or SDK-based data capture.
- No live drift attribution or execution-side evidence columns.
- No email/Slack/webhook notifications when coverage score changes.
- No historical trend tracking of per-strategy coverage scores over time.
- No reliability score formula changes.
- No alert generation changes.

### Verify with curl

```bash
# Evidence coverage matrix for all active strategies:
curl "http://localhost:8000/api/evidence/coverage" | python3 -m json.tool
# Response: { total, limit, offset, generated_at, items: [...], summary: {...} }

# Each item has:
# { strategy_id, name, slug, asset_class, status, evidence_coverage_score,
#   missing_count, review_count, partial_count, complete_count,
#   strategy_runs: {status, count, latest_at, summary, suggested_check},
#   backtest_runs: {...}, dataset_evidence: {...}, ... (11 columns),
#   suggested_next_steps: ["..."] }

# Summary field has:
# { strategy_count, average_coverage_score, complete_cell_count,
#   partial_cell_count, review_cell_count, missing_cell_count,
#   most_common_missing_evidence: ["Strategy Runs", ...] }

# Filter by asset_class:
curl "http://localhost:8000/api/evidence/coverage?asset_class=equity" | python3 -m json.tool

# Include archived strategies:
curl "http://localhost:8000/api/evidence/coverage?include_archived=true" | python3 -m json.tool

# Pagination:
curl "http://localhost:8000/api/evidence/coverage?limit=10&offset=0" | python3 -m json.tool
```

> **M21 note:** Coverage computation is deterministic — based on logged evidence counts and
> statuses from existing data. No AI, no live data, no external calls. Not investment advice.

---

## Previously completed — M20: Strategy Comparison Dashboard v1

**Status: complete.**

### M20 deliverables

- **1 new API endpoint** — `POST /api/strategies/compare` registered in `app/api/routes/strategies.py`
  BEFORE the parameterised `GET /api/strategies/{strategy_id}` route to prevent literal path
  collision. Accepts 2–8 strategy IDs. Returns `StrategyComparisonResponse`. No timeline event
  (read-only analysis, not a mutation).
- **`app/services/strategy_comparison.py`** — new deterministic comparison service.
  No AI, no live market data, no external calls:
  - `compare_strategies(strategy_ids, db, *, include_archived)` — accepts 2–8 UUIDs.
    Raises `ValueError` for: fewer than 2, more than 8, unknown IDs, archived strategies (unless
    `include_archived=True`).
  - **Evidence coverage score** (0–100) from 8 binary evidence checks:
    `run_count > 0` (+10), `backtest_run > 0` (+10), `dataset_linked > 0` (+20),
    `backtest_audit > 0` (+20), `signal_snapshots > 0` (+15), `universe_snapshots > 0` (+10),
    `config_snapshots > 0` (+10), `reports > 0` (+5).
  - **Gap labels** derived deterministically: `no_runs`, `no_dataset_evidence`,
    `no_backtest_audit`, `no_signal_evidence`, `no_universe_evidence`, `no_config_snapshot`,
    `open_high_alerts`, `insufficient_reliability_score`, `stale_reliability_score`.
  - **Reliability ranking** — two-tier sort: scored strategies sorted by score descending,
    null or `insufficient_evidence` strategies always rank last. Ties broken alphabetically.
  - **Evidence-coverage ranking** — sorted by evidence coverage score descending.
  - **Shared gaps** — gap labels present in every strategy being compared.
  - **Differentiators** — strategies whose evidence coverage score differs from the maximum
    by more than 15 points, calling out which specific gaps they have that others do not.
  - **`deterministic_explanation`** — hedged prose using only approved language.
    Ends with "This comparison is based on logged evidence. It is not investment advice."
    Approved vocabulary: "better evidenced", "higher current reliability score", "more complete
    instrumentation", "requires review". Forbidden: "better strategy", "more profitable",
    "should trade", "alpha is stronger", "buy/sell".
  - Four dataclasses: `StrategyEvidenceCoverageData`, `StrategyComparisonItemData`,
    `StrategyComparisonRankingItemData`, `StrategyComparisonResult` (list fields use
    `field(default_factory=list)`).
  - `Alert.strategy_id` is a `String(36)` column → queries use `str(uuid_val)`.
  - SQLite stores naive datetimes → stale-score check normalises with
    `gen_at.replace(tzinfo=timezone.utc)` before computing the 30-day timedelta.
- **New Pydantic schemas** (`app/schemas/strategy.py`):
  `StrategyEvidenceCoverage`, `StrategyComparisonItem`, `StrategyComparisonRankingItem`,
  `StrategyComparisonRequest`, `StrategyComparisonResponse`.
- **45 new backend tests** — `tests/test_comparison_m20.py` across 5 test classes:
  - `TestStrategyComparisonService` (16 tests): at-least-two, at-most-eight, unknown-id,
    archived-rejected/allowed, correct count, identities present, coverage counts, gaps list,
    reliability ranking, coverage ranking, explanation present, forbidden-language check,
    disclaimer present, shared-gaps subset, generated-at recent.
  - `TestStrategyComparisonScoredRanking` (2 tests): scored-ranks-above-unscored,
    null-scores-rank-last.
  - `TestStrategyComparisonEndpoint` (16 tests): two-strategies success, required fields,
    coverage fields, <2 rejected, >8 rejected, missing strategy 404, archived rejection/allowed,
    ranking counts match, explanation not investment advice, strongest/weakest null when no scores,
    open-alert count included, expected gap keys, high-alert gap triggered, no timeline event,
    invalid UUID 422.
  - `TestEvidenceCoverageScore` (3 tests): empty=0, full=100, partial=20.
  - `TestGapGeneration` (8 tests): no-runs, no-dataset, open-high, open-critical, medium-not-
    triggered, insufficient-reliability, stale-reliability, fresh-no-stale.
- **785 total backend tests** (740 prior M2–M19 + 45 new), 1 skipped.
- **Frontend types** (`frontend/src/types/index.ts`): `StrategyEvidenceCoverage`,
  `StrategyComparisonItem`, `StrategyComparisonRankingItem`, `StrategyComparisonRequest`,
  `StrategyComparisonResponse` interfaces added.
- **Frontend API** (`frontend/src/lib/api.ts`): `compareStrategies(payload)` added.
- **New page** `frontend/src/pages/StrategyComparison.tsx` at route `/strategies/compare`:
  - Strategy selector — checkbox list of all registered strategies; select 2–8 to enable Compare.
  - `ReliabilityStatusChip` — colour-coded status pill (excellent/good/review/weak/insufficient).
  - `GapChip` — gap label chip with severity colouring.
  - `CoverageBar` — div-bar visualization of evidence coverage score (no chart library).
  - `StrategyCard` — compact per-strategy panel showing all evidence sub-scores, coverage counts,
    gaps, missing evidence list, and suggested checks.
  - `RankingTable` — ranked table for reliability or coverage rankings.
  - Side-by-side comparison score grid and full explanation + disclaimer.
  - Score colour thresholds: ≥75 green, ≥55 amber, <55 red, null muted.
  - Coverage colour: ≥80 green, ≥40 amber, <40 red.
- **`Strategies.tsx`** — "Compare Strategies" secondary button added to PageHeader, navigating
  to `/strategies/compare`.
- **`App.tsx`** — `StrategyComparison` route registered BEFORE `strategies/:id`.
- **`nav.ts`** — "Compare Strategies" nav item added under Research section.
- **Zero TypeScript errors**, clean production build (60 modules, ≈365 kB JS bundle).

### Language constraints (M20)

M20 uses language that describes logged evidence and deterministic scores only:

| Allowed | Forbidden |
|---|---|
| "better evidenced" | "better strategy" |
| "higher current reliability score" | "more profitable" |
| "more complete instrumentation" | "should trade" |
| "requires review" | "alpha is stronger" |
| "lower evidence coverage score" | "buy signal" / "sell signal" |

All output from `POST /api/strategies/compare` ends with:
> "This comparison is based on logged evidence. It is not investment advice."

### What M20 does NOT build (by design)

- No AI-driven comparison, no predictive scores, no market data.
- No broker connectivity, no live trading actions.
- No email/Slack/webhook notifications when comparison results change.
- No real-time streaming or polling of comparison results.
- No live drift attribution or execution-side comparisons.
- No portfolio-level cross-strategy weighting or allocation suggestions.
- No historical comparison trend tracking (comparing two comparison snapshots over time).

### Verify with curl

```bash
# First, register at least two strategies (or use the seed data):
curl http://localhost:8000/api/strategies | python3 -m json.tool
# Note the "id" fields from the response.

# Compare two strategies by ID:
curl -s -X POST http://localhost:8000/api/strategies/compare \
  -H 'Content-Type: application/json' \
  -d '{"strategy_ids": ["<strategy_id_1>", "<strategy_id_2>"]}' \
  | python3 -m json.tool
# Response envelope:
# {
#   "strategies": [{ strategy_id, name, overall_reliability_score, coverage: {...},
#                    gaps: [...], missing_evidence: [...], suggested_checks: [...] }],
#   "ranked_by_reliability": [{ rank, strategy_id, name, score, score_label, status }],
#   "ranked_by_evidence_coverage": [{ rank, strategy_id, name, score, score_label, status }],
#   "strongest_strategy_id": "<id or null>",
#   "weakest_strategy_id": "<id or null>",
#   "shared_gaps": [...],
#   "differentiators": [...],
#   "deterministic_explanation": "...",
#   "generated_at": "..."
# }

# Compare up to 8 strategies with archived included:
curl -s -X POST http://localhost:8000/api/strategies/compare \
  -H 'Content-Type: application/json' \
  -d '{"strategy_ids": ["<id1>", "<id2>", "<id3>"], "include_archived": true}' \
  | python3 -m json.tool

# Too few strategies (returns 422):
curl -s -X POST http://localhost:8000/api/strategies/compare \
  -H 'Content-Type: application/json' \
  -d '{"strategy_ids": ["<id1>"]}' | python3 -m json.tool
```

> **M20 note:** Comparisons are deterministic — based on logged evidence snapshots and stored
> reliability scores, not live recalculation or market data. No AI, no predictions,
> no investment advice.

---

## Previously completed — M19: Reliability Score History + Evidence Trend Panel

**Status: complete.**

### M19 deliverables

- **3 new API endpoints** (`app/api/routes/strategies.py`) — all registered in safe order
  (literal paths before parameterised sub-paths) to avoid Starlette routing conflicts:
  - `GET /api/strategies/{id}/reliability-scores/compare?score_a_id=…&score_b_id=…` —
    deterministic comparison of any two stored reliability scores belonging to the same strategy.
    Validates both scores exist (404) and belong to the strategy (400). Returns full
    `ReliabilityScoreComparisonResponse`. No timeline event (read-only). Registered BEFORE the
    history list endpoint.
  - `GET /api/strategies/{id}/reliability-scores` — paginated history list, newest-first.
    Returns `StrategyReliabilityScoreHistoryResponse` envelope (`total`, `limit`, `offset`,
    `items`). Supports `limit` and `offset` query params.
  - `GET /api/strategies/{id}/reliability-score/trend` — latest vs. previous score comparison.
    Returns `ReliabilityScoreTrendResponse` with `has_trend`, `message`, `latest`, `previous`,
    and a full `comparison` object. Returns `has_trend: false` (with informative message) when
    fewer than 2 scores exist. Registered BEFORE the existing single-score GET endpoint.
- **`compare_reliability_scores(score_a, score_b)` service function** added to
  `app/services/strategy_reliability.py`. Deterministic — no AI, no live data, no external calls:
  - Computes `overall_delta` (score_b − score_a) and `status_changed` flag.
  - `ReliabilityComponentDelta` per component: `score_a`, `score_b`, `delta` (None when either
    is null), `became_available` (None → value), `became_null` (value → None).
  - `EvidenceCountDelta` per evidence count key present in either score.
  - Evidence change sets: `resolved_missing_evidence` (was missing, now addressed),
    `still_missing_evidence` (missing in both), `newly_available_evidence` (newly missing in B).
  - `highlighted_changes`: bullets for components where `|delta| ≥ 3.0` points.
  - `deterministic_explanation`: hedged prose ("changed from", "improved alongside", "may
    reflect") — no causal language. Ends with "This is a deterministic score comparison based
    on stored evidence snapshots, not a causal claim."
- **Three new dataclasses** in the service: `ReliabilityComponentDelta`, `EvidenceCountDelta`,
  `ReliabilityComparisonResult` (list fields use `field(default_factory=list)`).
  `TYPE_CHECKING` guard prevents circular import of the ORM model at runtime.
- **New schemas** (`app/schemas/strategy.py`):
  `StrategyReliabilityScoreHistoryResponse`, `ReliabilityComponentDelta`, `EvidenceCountDelta`,
  `ReliabilityScoreComparisonResponse`, `ReliabilityScoreTrendResponse`.
- **44 new backend tests** — `tests/test_reliability_m19.py` across 5 test classes:
  - `TestCompareReliabilityScoresService` (15 tests): `SimpleNamespace` mock objects — no DB
    needed. overall_delta, became_available/became_null flags, evidence count deltas,
    resolved/still/newly missing evidence, self-comparison zero deltas, explanation language
    (no causal phrases: "caused", "because", "due to"), highlighted changes threshold (≥ 3.0).
  - `TestReliabilityScoreHistory` (8 tests): history newest-first, limit/offset pagination,
    404 unknown strategy, all envelope fields present.
  - `TestReliabilityScoreCompareEndpoint` (9 tests): success, 404 unknown strategy/score,
    cross-strategy score rejection (400), self-comparison, no timeline event created,
    explanation avoids causal phrases.
  - `TestReliabilityScoreTrend` (8 tests): 404 unknown, not-enough-history (0 and 1 scores),
    has_trend with 2+ scores, latest/previous populated correctly, no timeline event,
    comparison uses prev=A/latest=B, 3 scores uses newest two.
  - 4 additional edge-case tests.
- **740 total backend tests** (696 prior M2–M18 + 44 new), 1 skipped.
- **Frontend types** (`frontend/src/types/index.ts`):
  `StrategyReliabilityScoreHistoryResponse`, `ReliabilityComponentDelta`, `EvidenceCountDelta`,
  `ReliabilityScoreComparisonResponse`, `ReliabilityScoreTrendResponse` interfaces added.
- **Frontend API** (`frontend/src/lib/api.ts`):
  `getStrategyReliabilityScoreHistory()`, `compareStrategyReliabilityScores()`,
  `getStrategyReliabilityScoreTrend()` added.
- **Extended `ReliabilityPanel`** (`frontend/src/pages/StrategyDetail.tsx`):
  - `ScoreSparkline` — div-bar visualization (no chart library) of the last N scores,
    colour-coded by range (≥75 green, ≥55 amber, <55 red, null gray). Shown when ≥ 2 scores.
  - `ScoreHistoryStrip` — table of up to 5 most-recent scores: When / Score / Status /
    Activity / Data / Backtest / Signal columns.
  - `TrendSection` — overall delta with ▲/▼/≈ indicator, status-change arrow if changed,
    component movers grid (`|delta| ≥ 1.0`), resolved evidence list (green), still-missing
    list (amber), `deterministic_explanation` in italic.
  - `deltaColor()` and `deltaSign()` helpers (e.g. ▲ +3.2 / ▼ −1.8 / ≈).
  - `scoreHistory` and `scoreTrend` state. `loadReliabilityHistory()` loads last 10 scores
    on page load and derives a synthetic `ReliabilityScoreTrendResponse` from the two most-recent
    items — no extra API call on load.
- **Zero TypeScript errors**, clean production build (59 modules, ≈349 kB JS bundle).

### What M19 does NOT build (by design)

- Full comparison UI panel (compare endpoint available via API; the `comparison` field in the
  synthetic trend built from history is `null` — no extra round-trip on page load).
- AI-driven trend explanations, predictions, or anomaly detection.
- Live score refresh, streaming, or polling.
- Email, Slack, or webhook notifications when reliability score changes.
- Live drift attribution or execution-side score contributions.
- Per-component score history charts or time-series visualizations beyond the sparkline.

### Verify with curl

```bash
# First, compute at least two reliability scores for a strategy:
curl -s -X POST http://localhost:8000/api/strategies/<strategy_id>/reliability-score \
  | python3 -m json.tool

# List reliability score history (paginated, newest first)
curl "http://localhost:8000/api/strategies/<strategy_id>/reliability-scores?limit=10" \
  | python3 -m json.tool
# Response: { "total": N, "limit": 10, "offset": 0, "items": [...] }

# Compare two stored scores
curl "http://localhost:8000/api/strategies/<strategy_id>/reliability-scores/compare?\
score_a_id=<older_score_id>&score_b_id=<newer_score_id>" | python3 -m json.tool
# Response: overall_score_a, overall_score_b, overall_delta, status_a, status_b, status_changed,
#   component_deltas[{component, label, score_a, score_b, delta, became_available, became_null}],
#   evidence_count_deltas, newly_available_evidence, resolved_missing_evidence,
#   still_missing_evidence, highlighted_changes, deterministic_explanation

# Trend: latest vs previous score
curl "http://localhost:8000/api/strategies/<strategy_id>/reliability-score/trend" \
  | python3 -m json.tool
# Response: { "has_trend": true, "message": "...", "latest": {...}, "previous": {...},
#   "comparison": { "overall_delta": ..., "component_deltas": [...], ... } }

# Trend when only one score exists:
# Response: { "has_trend": false, "message": "Not enough history. Compute at least two
#   reliability scores to see trend.", "latest": {...}, "previous": null, "comparison": null }
```

> **M19 note:** Score comparisons are deterministic — based on stored evidence snapshots, not
> live recalculation. Language in `deterministic_explanation` is explicitly hedged ("changed
> from", "improved alongside", "may reflect") and ends with "not a causal claim." No AI,
> no live data, no external calls.

---

## Previously completed — M18: Strategy Reliability Score Engine v1

**Status: complete.**

### M18 deliverables

- **Migration `0011_m18_reliability_scores.py`** — adds `strategy_reliability_scores` table.
  Columns: `id` (UUID PK), `strategy_id` (FK strategies CASCADE), `overall_score` (Float nullable),
  `status` (String 50), 8 component score columns (Float nullable each), 4 JSON blob columns
  (`evidence_counts_json`, `component_summaries_json`, `missing_evidence_json`, `suggested_checks_json`),
  `generated_at` (DateTime), `created_at`, `updated_at`.
  Indexes on: strategy_id, status, generated_at.
- **`EventType.strategy_reliability_scored`** and new **`ReliabilityScoreStatus`** StrEnum added to `constants.py`.
- **`app/models/strategy_reliability_score.py`** — new `StrategyReliabilityScore` ORM model with all columns + relationship to `Strategy`.
- **Strategy model** updated with `reliability_scores` relationship (CASCADE delete-orphan).
- **`app/services/strategy_reliability.py`** — deterministic scoring engine. No AI, no live data:
  - `_score_activity(runs)` — 30/55/75 based on run count + +10 bonus for mixed run types (backtest + paper/live/research).
  - `_score_data_evidence(runs, db)` — averages linked dataset snapshot health; caps at 60 if any health <50, caps at 70 if any critical quality issue. Returns None if no linked snapshots.
  - `_score_backtest_trust(runs, db)` — averages backtest audit trust scores; caps at 65 if any weak/unreliable status. Returns None if no audits.
  - `_score_config_evidence(strategy_id, versions, db)` — 40/60/85/90 based on version+config snapshot counts.
  - `_score_universe_evidence(runs, snapshots, db)` — 75 (1 snapshot) or 85 (2+); +10 if any run links a universe snapshot. Returns None if no snapshots.
  - `_score_signal_evidence(runs, snapshots, db)` — averages quality scores; caps at 75 if any <70; +5 boost if any run links a signal snapshot. Returns None if no snapshots.
  - `_score_alert_penalty(strategy_id, db)` — 100 - (5×low + 10×medium + 20×high + 30×critical open alerts); floor 0.
  - `_score_report_coverage(strategy_id, db)` — 80 (existing report) or 90 (generated within 30 days). Returns None if no strategy_reliability reports.
  - Weighted overall score: backtest_trust=25%, data_evidence=20%, signal_evidence=15%, universe/config/activity/alert_penalty=10% each. Null + `insufficient_evidence` when fewer than 3 non-null components.
  - Status thresholds: ≥90=excellent, ≥75=good, ≥55=review, else=weak.
  - Deterministic suggested checks list based on missing/low-score components.
- **Schemas** (`app/schemas/strategy.py`): `StrategyReliabilityScoreRead`, `StrategyReliabilityScoreListResponse` added. `StrategyListItemOut` and `StrategyDetailOut` both gain `latest_reliability_score` field.
- **API endpoints** (`app/api/routes/strategies.py`):
  - `POST /api/strategies/{id}/reliability-score` — computes and stores score, creates timeline event.
  - `GET  /api/strategies/{id}/reliability-score` — returns latest score (404 if none).
  - Updated `GET /api/strategies` list to include `latest_reliability_score` per strategy.
  - Updated `GET /api/strategies/{id}` detail to include `latest_reliability_score`.
- **New router** (`app/api/routes/reliability.py`): `GET /api/reliability-scores` with `status`, `strategy_id`, `limit`, `offset` filters; newest-first.
- **Dashboard** (`app/services/dashboard_summary.py` + `app/schemas/dashboard.py`): `DashboardScores` gains `average_strategy_reliability_score` (avg of latest per-strategy scores) and `strategies_by_reliability_status` (status → count breakdown).
- **Tests** (`backend/tests/test_reliability_m18.py`) — 71 tests covering all component scoring functions (unit), overall formula, status thresholds, suggested checks, API endpoints (POST/GET/list), dashboard fields, and strategy detail/list integration. 696 total tests (625 prior + 71 new), 1 skipped.
- **Frontend types** (`frontend/src/types/index.ts`): `StrategyReliabilityScore`, `StrategyReliabilityScoreListResponse` added. `Strategy`, `StrategyDetail`, `DashboardScores` updated.
- **Frontend API** (`frontend/src/lib/api.ts`): `computeStrategyReliabilityScore`, `getStrategyReliabilityScore`, `getReliabilityScores` added.
- **Frontend StrategyDetail** (`frontend/src/pages/StrategyDetail.tsx`): Reliability panel with overall score, status badge, 8-component grid, missing evidence list, suggested checks, and Compute/Refresh button.
- **Frontend Strategies** (`frontend/src/pages/Strategies.tsx`): Reliability column added to table showing score + status badge.
- **Frontend Dashboard** (`frontend/src/pages/Dashboard.tsx`): "Avg Reliability" pillar added; reliability status breakdown chips displayed.

### What M18 does NOT build (by design)

- No AI-driven scoring, no live market data, no external API calls.
- No broker connectivity, no live trading actions.
- No email/Slack/webhook notifications.
- No real-time streaming score updates.
- Scoring is deterministic and snapshot-based: run POST to refresh.

---

## Previously completed — M17: Signal Snapshotting + Signal Coverage Evidence

**Status: complete.**

### M17 deliverables

- **Migration `0010_m17_signal_snapshots.py`** — adds `signal_snapshots` table and
  `signal_snapshot_id` FK column on `strategy_runs`.
  `signal_snapshots` columns: `id` (UUID PK), `strategy_id` (FK strategies CASCADE),
  `strategy_version_id` (FK strategy_versions SET NULL, nullable),
  `universe_snapshot_id` (FK universe_snapshots SET NULL, nullable),
  `label` (String 255), `signal_name` (String 255, nullable),
  `source_type` (String 100, default `manual_json`), `source_filename` (String 512, nullable),
  `rows_json` (JSON — full verbatim row payload), `row_count` (Integer),
  `symbol_count` (Integer), `symbols_json` (JSON — sorted distinct symbols, NOT full rows_json),
  `min_timestamp`, `max_timestamp` (String 100, nullable), `signal_value_count` (Integer),
  `missing_signal_count` (Integer), `mean_value`, `min_value`, `max_value`, `stddev_value`
  (Float nullable), `signal_hash` (String 64, SHA-256, indexed), `quality_score` (Integer),
  `metadata_json` (JSON nullable), `created_at`, `updated_at`.
  Indexes: strategy_id, version_id, universe_snapshot_id, signal_hash, created_at.
  `strategy_runs.signal_snapshot_id` — nullable UUID FK to `signal_snapshots` (SET NULL), indexed.
  18 total ORM tables.
- **`EventType.signal_snapshot_logged`** added to `constants.py`.
- **`app/models/signal_snapshot.py`** — new `SignalSnapshot` ORM model. Linked to `Strategy`
  (CASCADE delete), `StrategyVersion` (SET NULL), `UniverseSnapshot` (SET NULL). `strategy_runs`
  back-populated. Strategy, StrategyVersion, UniverseSnapshot, and StrategyRun models all updated
  with `signal_snapshots` / `signal_snapshot` relationships.
- **`app/services/signal_snapshots.py`** — deterministic service. No AI, no live data:
  - `_is_numeric(v)` — finite int/float only; bools and NaN/Inf excluded.
  - `_parse_timestamp(ts)` — tries ISO 8601 date and datetime formats, returns canonical string.
  - `normalize_signal_rows(rows, signal_column)` — validates list-of-dicts input.
  - `compute_signal_hash(rows, metadata, signal_column)` — SHA-256. Rows sorted by
    `(symbol, timestamp, signal_column_value)` before hashing. Same rows in any insertion order
    always produce the same 64-char hex hash.
  - `SignalSummary` dataclass + `summarize_signal_snapshot(rows, signal_column)` — computes
    `row_count`, `symbol_count`, `symbols_json` (sorted distinct), `min/max_timestamp`,
    `signal_value_count`, `missing_signal_count`, `mean/min/max/stddev_value`, and
    `quality_score` (starts at 100, deductions: −8 to −40 for missing/non-numeric signals,
    −15 for >5% duplicate symbol+timestamp keys, −10 for invalid timestamps, −5 for zero
    variance with ≥10 rows; clamped 0–100).
  - `SignalComparisonResult` dataclass + `compare_signal_snapshots(...)` — full comparison:
    set-based symbol overlap (overlap_ratio, jaccard_similarity), `row_count_delta` always
    computed (unconditionally), quality_score_delta, keyed row-level changes when both
    symbol+timestamp fields are present. Hedged language throughout.
- **Schemas** (`app/schemas/strategy.py`) extended:
  - `SignalSnapshotCreate` — input schema (strategy_version_id and universe_snapshot_id both
    optional; label, source_type, signal_name, source_filename, signal_column, rows list,
    metadata_json optional dict).
  - `SignalSnapshotSummary` — lightweight evidence embedded in run responses (id, label,
    signal_name, row_count, symbol_count, signal_value_count, missing_signal_count,
    quality_score, mean_value, stddev_value, created_at).
  - `SignalSnapshotRead` — summary output without rows_json blob (used in list responses).
  - `SignalSnapshotDetail` — extends Read with `rows_json` payload.
  - `SignalRowChangeOut` — single changed row in comparison response.
  - `SignalComparisonResponse` — full comparison response (all counts, ratios,
    highlighted_changes, deterministic_explanation).
  - `StrategyVersionOut` — extended with `signal_snapshot_count: int = 0`.
  - `StrategyRunCreate` — extended with `signal_snapshot_id: uuid.UUID | None = None`.
  - `StrategyRunOut` — extended with `signal_snapshot_id` and
    `signal_snapshot: SignalSnapshotSummary | None`.
  - `StrategyDetailOut` — extended with `signal_snapshots: list[SignalSnapshotRead]`.
- **4 new API endpoints** + 3 updated:
  - `POST /api/strategies/{strategy_id}/signal-snapshots` — validates strategy and optional
    FK links (version and universe snapshot ownership), normalizes rows, rejects empty list
    (422), computes hash + stats + quality score, stores verbatim rows_json, emits
    `signal_snapshot_logged` audit timeline event → 201 `SignalSnapshotRead`. No rows_json blob
    in response.
  - `GET  /api/strategies/{strategy_id}/signal-snapshots` — list newest-first; optional
    `version_id` filter. No rows_json in list response.
  - `GET  /api/strategies/{strategy_id}/signal-snapshots/compare?snapshot_a_id=…&snapshot_b_id=…`
    — registered BEFORE the list route (literal `/compare` matched first). Read-only
    comparison → 200 `SignalComparisonResponse`. No timeline event.
  - `GET  /api/signal-snapshots/{snapshot_id}` — full detail with rows_json payload → 200.
  - `POST /api/strategies/{strategy_id}/runs` updated — accepts `signal_snapshot_id`; validates
    snapshot exists (404) and belongs to same strategy (400); validates version consistency if
    both are specified; attaches `signal_snapshot` summary to response.
  - `GET  /api/strategies/{strategy_id}/runs` updated — eagerly loads `signal_snapshot` via
    `selectinload`.
  - `GET  /api/strategies/{strategy_id}` updated — eagerly loads `signal_snapshots`,
    computes per-version `signal_snapshot_count`, includes `signal_snapshots` in
    `StrategyDetailOut`.
- **80 new backend tests** — `tests/test_signal_m17.py` across 12 test classes:
  - `TestNormalizeSignalRows` — valid input, non-list rejected, non-dict rows rejected, empty
    list allowed.
  - `TestComputeSignalHash` — 64-char hex, determinism across row orderings, different rows
    produce different hash, custom signal column, metadata changes hash.
  - `TestSummarizeSignalSnapshot` — row_count, symbol_count, signal_value_count,
    missing_signal_count, mean/min/max/stddev, quality_score deductions (missing signals,
    duplicates, invalid timestamps, zero variance), symbols_json sorted distinct.
  - `TestCompareSignalSnapshots` — identical, different, B superset, empty, overlap_ratio,
    jaccard_similarity, row_count_delta always set (not conditional on is_same),
    quality_score_delta, keyed row changes.
  - `TestCreateSignalSnapshot` — 201, hash determinism, stats correct, timeline event, version
    link, universe link, wrong version → 404, wrong universe → 404, empty rows → 422.
  - `TestListSignalSnapshots` — empty, returns created, newest-first, version_id filter,
    404, no rows_json blob.
  - `TestGetSignalSnapshot` — rows_json present, all fields, 404.
  - `TestCompareSignalSnapshotsRoute` — response fields, A not found → 404, B not found → 404,
    wrong strategy → 404, missing params → 422.
  - `TestRunSignalSnapshotLinkage` — run with snapshot, run without, wrong strategy → 400,
    nonexistent → 404, summary fields in response.
  - `TestListRunsSignalEvidence` — embedded in list, null for unlinked.
  - `TestStrategyDetailSignalSnapshots` — included in detail, version count, no blob.
  - `TestVersionsSignalSnapshotCount` — in version list, zero for new version.
- **Frontend types** (`frontend/src/types/index.ts`):
  - `StrategyVersion` extended with `signal_snapshot_count: number`.
  - `SignalSnapshotSummary`, `SignalSnapshotRead`, `SignalSnapshotDetail` interfaces.
  - `SignalSnapshotCreateRequest`, `SignalRowChange`, `SignalComparisonResponse` interfaces.
  - `StrategyRun` extended with `signal_snapshot_id: string | null` and
    `signal_snapshot: SignalSnapshotSummary | null`.
  - `StrategyDetail.signal_snapshots: SignalSnapshotRead[]` field added.
  - `StrategyRunCreateRequest.signal_snapshot_id?: string` field added.
- **API client** (`frontend/src/lib/api.ts`):
  - `createSignalSnapshot()`, `getSignalSnapshots()`, `getSignalSnapshot()`,
    `compareSignalSnapshots()`.
- **`SignalSnapshotDrawer.tsx`** — right-panel drawer for logging a signal snapshot.
  Fields: label (required), signal_name (optional), strategy_version_id (optional dropdown),
  universe_snapshot_id (optional dropdown), source_type (select), source_filename,
  signal_column (defaults to `"signal"`), rows JSON textarea (validated as non-empty array of
  objects), metadata_json (optional JSON textarea). Follows same quant-terminal pattern as
  `UniverseSnapshotDrawer.tsx`.
- **`RunLogDrawer.tsx` updated** — accepts optional `signalSnapshots?: SignalSnapshotRead[]`
  prop. When signal snapshots are available, shows a "Signal Evidence (optional)" selector
  block with quality_score and symbol_count displayed per option. Preview shows quality score
  (colored by threshold), symbol count, and row count. Selected `signal_snapshot_id` included
  in run payload.
- **`StrategyDetail.tsx` updated**:
  - Imports `SignalSnapshotDrawer`, `SignalSnapshotRead`, `SignalSnapshotSummary`.
  - `SignalEvidenceChip` — inline chip on run rows showing quality_score (colored by
    threshold), signal_name, label, symbol count, mean, and stddev when a signal snapshot is
    linked.
  - `SignalEvidencePanel` — section card showing all signal snapshots (up to 5, with "+ N more"
    overflow), each with quality score (colored), symbol count, row count, signal name, source
    type, hash prefix, date. "+ Log Signal" header button. Empty state with guidance text.
  - `+ Log Signal` button added to header actions bar.
  - `SignalSnapshotDrawer` wired up; calls `setRefreshKey((k) => k + 1)` on creation.
  - `RunLogDrawer` receives `signalSnapshots={strategy.signal_snapshots}`.
  - Signal snapshot evidence chip shown per run row when `r.signal_snapshot` is non-null.
  - Panel inserted between Universe Evidence and Version & Config Evidence sections.
- **625 total passing tests** (1 skipped), zero TypeScript errors, clean production build.

### What M17 does NOT build (by design)

- Signal analytics, factor attribution, or alpha decomposition.
- Live market data ingestion or real-time signal feeds.
- Automated signal generation or AI-driven signal quality checks.
- SDK ingestion hooks or external data connectors.
- Signal comparison UI (compare endpoint available via API; frontend panel is future work).
- Deployment evidence or live drift attribution.

### Verify with curl

```bash
# Log a signal snapshot
curl -s -X POST http://localhost:8000/api/strategies/<strategy_id>/signal-snapshots \
  -H "Content-Type: application/json" \
  -d '{
    "label": "momentum-12m-2024-Q1",
    "signal_name": "momentum_12m",
    "source_type": "manual_json",
    "rows": [
      {"symbol": "AAPL", "timestamp": "2024-01-01", "signal": 0.52},
      {"symbol": "MSFT", "timestamp": "2024-01-01", "signal": 0.78},
      {"symbol": "GOOG", "timestamp": "2024-01-01", "signal": 0.34}
    ]
  }' | python3 -m json.tool
# Response: id, label, row_count=3, symbol_count=3, signal_hash (64-char SHA-256),
#   quality_score, mean_value, min_value, max_value, stddev_value, created_at, ...

# List signal snapshots (newest first)
curl "http://localhost:8000/api/strategies/<strategy_id>/signal-snapshots" \
  | python3 -m json.tool

# Filter by version
curl "http://localhost:8000/api/strategies/<strategy_id>/signal-snapshots?version_id=<version_id>" \
  | python3 -m json.tool

# Get full detail (includes rows_json payload)
curl "http://localhost:8000/api/signal-snapshots/<snapshot_id>" | python3 -m json.tool

# Compare two signal snapshots (read-only, no audit event)
curl "http://localhost:8000/api/strategies/<strategy_id>/signal-snapshots/compare?\
snapshot_a_id=<snap_a>&snapshot_b_id=<snap_b>" | python3 -m json.tool
# Response: is_same_signals, added_symbols, removed_symbols, overlap_ratio, jaccard_similarity,
#   row_count_delta, quality_score_delta, changed_rows, highlighted_changes,
#   deterministic_explanation

# Log a run linked to a signal snapshot
curl -s -X POST http://localhost:8000/api/strategies/<strategy_id>/runs \
  -H "Content-Type: application/json" \
  -d '{
    "run_name": "Momentum Backtest Q1 2024",
    "run_type": "backtest",
    "signal_snapshot_id": "<snapshot_id>",
    "metrics_json": {"sharpe": 1.4}
  }' | python3 -m json.tool
# Response includes "signal_snapshot": { "id": ..., "label": ..., "quality_score": ..., ... }
```

> **M17 note:** Signal hash is SHA-256 of rows sorted by `(symbol, timestamp, signal_value)` +
> optional metadata. Two snapshots with identical signal values in any insertion order always
> produce the same hash. Quality score starts at 100 and deducts for missing/non-numeric
> signals, duplicate keys, invalid timestamps, and zero variance. Language is hedged
> ("observed", "noted", "may suggest") and never makes causal claims.

---

## Previously completed — M16: Universe Snapshotting + Coverage Evidence

**Status: complete.**

### M16 deliverables

- **Migration `0009_m16_universe_snapshots.py`** — adds `universe_snapshots` table and
  `universe_snapshot_id` FK column on `strategy_runs`.
  `universe_snapshots` columns: `id` (UUID PK), `strategy_id` (FK strategies CASCADE),
  `strategy_version_id` (FK strategy_versions SET NULL, nullable), `label` (String 255),
  `source_type` (String 100, default `manual_json`), `source_filename` (String 512, nullable),
  `symbols_json` (JSON — normalized symbol list), `symbol_count` (Integer),
  `metadata_json` (JSON nullable), `universe_hash` (String 64, SHA-256, indexed), `created_at`,
  `updated_at`. Indexes: strategy_id, version_id, universe_hash, created_at.
  `strategy_runs.universe_snapshot_id` — nullable UUID FK to `universe_snapshots` (SET NULL),
  with index. 17 total ORM tables.
- **`EventType.universe_snapshot_logged`** added to `constants.py`.
- **`app/models/universe_snapshot.py`** — new `UniverseSnapshot` ORM model. Linked to
  `Strategy` (CASCADE delete) and `StrategyVersion` (SET NULL). `strategy_runs` back-populated.
  Strategy and StrategyVersion models updated with `universe_snapshots` relationship.
  `StrategyRun` model updated with `universe_snapshot_id` FK column and `universe_snapshot`
  relationship.
- **`app/services/universe_snapshots.py`** — deterministic service. No AI, no live data:
  - `normalize_symbols(symbols)` — trim, uppercase, deduplicate, sort. Drops empty entries.
  - `compute_universe_hash(symbols, metadata)` — SHA-256 of
    `{"symbols": sorted, "metadata": ...}` with `sort_keys=True`. Two universes with identical
    symbols in any order always produce the same 64-char hex hash.
  - `UniverseComparisonResult` dataclass — full comparison output with exact counts and capped
    display lists.
  - `compare_universe_snapshots(...)` — set-based deterministic comparison.
    `overlap_ratio = |A ∩ B| / max(|A|, |B|)`, `jaccard_similarity = |A ∩ B| / |A ∪ B|`.
    Added/removed symbol lists capped at 50 in the response; counts are exact.
    Language is hedged throughout ("observed", "noted", "may affect") — no causal claims.
- **Schemas** (`app/schemas/strategy.py`) extended:
  - `UniverseSnapshotCreate` — new input schema (strategy_version_id nullable, label,
    source_type, source_filename, symbols list, metadata_json optional dict).
  - `UniverseSnapshotSummary` — lightweight evidence embedded in run responses (id, label,
    symbol_count, universe_hash, strategy_version_id, created_at).
  - `UniverseSnapshotRead` — summary output without symbols_json blob (used in list responses).
  - `UniverseSnapshotDetail` — extends Read with `symbols_json: list[str]`.
  - `UniverseComparisonResponse` — full comparison response (all counts, ratios, capped lists,
    highlighted_changes, deterministic_explanation).
  - `StrategyVersionOut` — extended with `universe_snapshot_count: int = 0`.
  - `StrategyRunCreate` — extended with `universe_snapshot_id: uuid.UUID | None = None`.
  - `StrategyRunOut` — extended with `universe_snapshot_id` and
    `universe_snapshot: UniverseSnapshotSummary | None`.
  - `StrategyDetailOut` — extended with `universe_snapshots: list[UniverseSnapshotRead]`.
- **4 new API endpoints** + 3 updated:
  - `POST /api/strategies/{strategy_id}/universe-snapshots` — validates strategy, validates
    `strategy_version_id` belongs to this strategy if provided, validates symbols list non-empty,
    normalizes symbols, rejects all-empty list after normalization (422), computes
    `universe_hash`, emits `universe_snapshot_logged` audit timeline event → 201
    `UniverseSnapshotRead`. Response does NOT include `symbols_json` blob.
  - `GET  /api/strategies/{strategy_id}/universe-snapshots` — list newest-first; optional
    `version_id` query param to filter by linked version. No `symbols_json` blob.
  - `GET  /api/strategies/{strategy_id}/universe-snapshots/compare?snapshot_a_id=…&snapshot_b_id=…`
    — registered BEFORE the list route (literal `/compare` matched first). Read-only
    comparison of two snapshots belonging to this strategy → 200 `UniverseComparisonResponse`.
    No timeline event.
  - `GET  /api/universe-snapshots/{snapshot_id}` — full detail with `symbols_json` payload → 200.
  - `POST /api/strategies/{strategy_id}/runs` updated — accepts `universe_snapshot_id`; validates
    snapshot exists (404) and belongs to same strategy (400); attaches `universe_snapshot` summary
    to response; logs snapshot label and symbol count in the timeline event metadata.
  - `GET  /api/strategies/{strategy_id}/runs` updated — eagerly loads `universe_snapshot` via
    `selectinload`.
  - `GET  /api/strategies/{strategy_id}/versions` updated — includes `universe_snapshot_count`
    per version via a single grouped query.
  - `GET  /api/strategies/{strategy_id}` updated — eagerly loads `universe_snapshots`,
    computes per-version `universe_snapshot_count`, includes `universe_snapshots` in
    `StrategyDetailOut`.
- **62 new backend tests** — `tests/test_universe_m16.py` across 13 test classes:
  - `TestNormalizeSymbols` — sorted/uppercase, deduplication, whitespace, empty, single,
    order independence.
  - `TestComputeUniverseHash` — 64-char hex, determinism, different symbols, metadata effect,
    metadata sort-key determinism.
  - `TestCompareUniverseSnapshots` — identical, different, B superset, empty, overlap ratio
    formula, Jaccard, highlighted changes, hedged explanation.
  - `TestCreateUniverseSnapshot` — 201, normalization, hash determinism, version link, version
    wrong strategy → 404, missing strategy → 404, empty symbols → 422, all-whitespace → 422,
    metadata_json, source_filename, no symbols_json blob in response, timeline event created.
  - `TestListUniverseSnapshots` — empty, returns created, newest-first, filter by version_id,
    404, no symbols_json in list response.
  - `TestGetUniverseSnapshot` — symbols present, symbols are normalized, 404, all fields.
  - `TestCompareUniverseSnapshotsRoute` — identical, different, response fields, A not found → 404,
    B not found → 404, snapshot from wrong strategy → 404, missing strategy → 404,
    symbol_count_delta, missing query params → 422.
  - `TestRunUniverseSnapshotLinkage` — run with snapshot, run without, wrong strategy → 400,
    nonexistent → 404, summary fields.
  - `TestListRunsUniverseEvidence` — embedded in list, null for unlinked.
  - `TestStrategyDetailUniverseSnapshots` — included in detail, version count, no blob.
  - `TestVersionsUniverseSnapshotCount` — in version list, zero for new version.
- **Frontend types** (`frontend/src/types/index.ts`):
  - `StrategyVersion` extended with `universe_snapshot_count: number`.
  - `UniverseSnapshotSummary`, `UniverseSnapshotRead`, `UniverseSnapshotDetail` interfaces.
  - `UniverseSnapshotCreateRequest`, `UniverseComparisonResponse` interfaces.
  - `StrategyRun` extended with `universe_snapshot_id: string | null` and
    `universe_snapshot: UniverseSnapshotSummary | null`.
  - `StrategyDetail.universe_snapshots: UniverseSnapshotRead[]` field added.
  - `StrategyRunCreateRequest.universe_snapshot_id?: string` field added.
- **API client** (`frontend/src/lib/api.ts`):
  - `createUniverseSnapshot()`, `getUniverseSnapshots()`, `getUniverseSnapshot()`,
    `compareUniverseSnapshots()`.
- **`UniverseSnapshotDrawer.tsx`** — right-panel drawer for logging a universe snapshot.
  Fields: label (required), strategy_version_id (optional dropdown, only when versions exist),
  source_type (select), source_filename, symbols textarea (one per line or comma-separated,
  hint about normalization), metadata_json (optional JSON textarea). Client-side parses symbols
  and validates metadata JSON before submit. Calls `onCreated(snapshot)`.
- **`RunLogDrawer.tsx` updated** — accepts optional `universeSnapshots: UniverseSnapshotRead[]`
  prop. When universe snapshots are available, shows a "Universe Evidence (optional)" selector
  block. Selected snapshot shows symbol count + hash prefix preview. Selected
  `universe_snapshot_id` included in run payload.
- **`StrategyDetail.tsx` updated**:
  - Imports `UniverseSnapshotDrawer`, `UniverseSnapshotRead`, `UniverseSnapshotSummary`.
  - `UniverseEvidenceChip` — inline chip on run rows showing symbol count + label + hash
    prefix when a universe snapshot is linked.
  - `UniverseEvidencePanel` — section card showing all universe snapshots (up to 5, with
    "+ N more" overflow), each with symbol count, source type, hash prefix, date. "+ Log
    Universe" header button. Empty state with guidance text.
  - `+ Log Universe` button added to header actions bar.
  - `UniverseSnapshotDrawer` wired up; calls `setRefreshKey((k) => k + 1)` on creation.
  - `RunLogDrawer` receives `universeSnapshots={strategy.universe_snapshots}`.
  - Universe snapshot evidence chip shown per run row when `r.universe_snapshot` is non-null.
  - Panel inserted between Data Evidence and Version & Config Evidence sections.
- **545 total passing tests** (1 skipped), zero TypeScript errors, clean production build.

### What M16 does NOT build (by design)

- Sector/factor exposure analytics or universe composition analysis.
- Live market data, corporate actions, or index membership tracking.
- Signal snapshots (separate milestone).
- AI explanations of universe changes.
- SDK ingestion hooks or automated snapshot creation.
- Universe comparison UI (compare endpoint available via API; frontend panel is future work).
- Deployment evidence or live drift attribution.

### Verify with curl

```bash
# Log a universe snapshot
curl -s -X POST http://localhost:8000/api/strategies/<strategy_id>/universe-snapshots \
  -H "Content-Type: application/json" \
  -d '{
    "label": "SP500-2024-Q1",
    "symbols": ["AAPL", "MSFT", "goog", "amzn", "tsla"],
    "source_type": "manual_json"
  }' | python3 -m json.tool
# Response: id, label, symbol_count=5, universe_hash (64-char SHA-256), created_at, ...
# Symbols normalized: ["AAPL", "AMZN", "GOOG", "MSFT", "TSLA"] (uppercased + sorted)

# List universe snapshots (newest first)
curl "http://localhost:8000/api/strategies/<strategy_id>/universe-snapshots" \
  | python3 -m json.tool

# Filter by version
curl "http://localhost:8000/api/strategies/<strategy_id>/universe-snapshots?version_id=<version_id>" \
  | python3 -m json.tool

# Get full detail (includes symbols_json payload)
curl "http://localhost:8000/api/universe-snapshots/<snapshot_id>" | python3 -m json.tool

# Compare two universe snapshots (read-only, no audit event)
curl "http://localhost:8000/api/strategies/<strategy_id>/universe-snapshots/compare?\
snapshot_a_id=<snap_a>&snapshot_b_id=<snap_b>" | python3 -m json.tool
# Response: is_same_universe, added_count, removed_count, overlap_ratio, jaccard_similarity,
#   added_symbols (≤50), removed_symbols (≤50), highlighted_changes, deterministic_explanation

# Log a run linked to a universe snapshot
curl -s -X POST http://localhost:8000/api/strategies/<strategy_id>/runs \
  -H "Content-Type: application/json" \
  -d '{
    "run_name": "SP500 Q1 Backtest",
    "run_type": "backtest",
    "universe_snapshot_id": "<snapshot_id>",
    "metrics_json": {"sharpe": 1.4}
  }' | python3 -m json.tool
# Response includes "universe_snapshot": { "id": ..., "label": ..., "symbol_count": 5, ... }
```

> **M16 note:** Universe hash is SHA-256 of sorted symbols + optional metadata. Two snapshots
> with the same symbols in any order always produce the same hash. Comparison is set-based —
> no order sensitivity. Language is hedged ("observed", "noted", "may affect") and never makes
> causal claims.

---

## Previously completed — M15: Strategy Versions + Config Snapshotting

**Status: complete.**

### M15 deliverables

- **Migration `0008_m15_config_snapshots.py`** — adds `strategy_config_snapshots` table.
  Columns: `id` (UUID PK), `strategy_id` (FK strategies CASCADE), `strategy_version_id`
  (FK strategy_versions SET NULL, nullable), `label` (String 255), `source_type` (String 100,
  default `manual_json`), `source_filename` (String 512, nullable), `config_json` (JSON),
  `config_hash` (String 64, SHA-256 of normalized JSON), `param_count` (Integer),
  `assumption_count` (Integer), `created_at`, `updated_at`. Indexes: strategy_id, version_id,
  config_hash, created_at. 17 total ORM tables.
- **`EventType.strategy_config_snapshot_logged`** added to `constants.py`.
- **`app/models/strategy_config_snapshot.py`** — new ORM model. `StrategyConfigSnapshot` linked
  back to `Strategy` (cascade delete) and `StrategyVersion` (SET NULL). Both parent models
  updated with `config_snapshots` relationship.
- **`app/services/config_snapshots.py`** — deterministic hash + comparison service:
  - `compute_config_hash(config_json)` — SHA-256 hex of `sort_keys=True` JSON (64-char string).
    Two configs with identical keys/values in any order produce the same hash.
  - `count_params(config_json)` / `count_assumptions(config_json)` — count keys under `params`
    / `assumptions` if the value is a dict; else 0.
  - `compare_config_snapshots(snap_a_id, snap_b_id, snap_a_label, snap_b_label, config_a, config_b)`
    — flat structural diff at three levels: top-level keys (excluding `params`/`assumptions`),
    params sub-keys, assumptions sub-keys. Returns `ConfigComparisonResult` dataclass with
    `is_same_config`, per-section `added/removed/changed`, `highlighted_changes` (≤10 bullets),
    and `total_changes`. No recursive diffing. Language is hedged.
- **Schemas** (`app/schemas/strategy.py`) extended:
  - `StrategyVersionCreate` — new input schema (version_label, git_commit, branch_name,
    code_path, signal_name, signal_description).
  - `StrategyConfigSnapshotCreate` — new input schema (strategy_version_id nullable,
    label, source_type, source_filename, config_json dict).
  - `StrategyVersionOut` — extended with `config_snapshot_count: int = 0`.
  - `StrategyConfigSnapshotRead` — summary output (no config_json blob).
  - `StrategyConfigSnapshotDetail` — extends Read with `config_json`.
  - `ConfigKeyChangeOut`, `ConfigComparisonSectionOut`, `ConfigComparisonResponse` — comparison output.
  - `StrategyDetailOut` — extended with `config_snapshots: list[StrategyConfigSnapshotRead]`.
- **6 new API endpoints** (`app/api/routes/strategies.py`):
  - `POST /api/strategies/{strategy_id}/versions` — validates strategy exists, prevents duplicate
    `version_label` within same strategy (409), creates version, emits `strategy_version_created`
    timeline event → 201 `StrategyVersionOut`.
  - `GET  /api/strategies/{strategy_id}/versions` — list newest-first with `config_snapshot_count`
    per version (aggregated in one grouped query).
  - `POST /api/strategies/{strategy_id}/config-snapshots` — validates strategy, validates
    `strategy_version_id` belongs to this strategy if provided, validates `config_json` is dict,
    computes `config_hash` / `param_count` / `assumption_count`, emits
    `strategy_config_snapshot_logged` timeline event → 201 `StrategyConfigSnapshotRead`.
  - `GET  /api/strategies/{strategy_id}/config-snapshots` — list newest-first; optional
    `version_id` query param to filter by linked version.
  - `GET  /api/strategies/{strategy_id}/config-snapshots/compare?snapshot_a_id=…&snapshot_b_id=…`
    — read-only structural comparison of two snapshots belonging to this strategy → 200
    `ConfigComparisonResponse`. No timeline event.
  - `GET  /api/config-snapshots/{snapshot_id}` — full detail with `config_json` payload.
  - `GET /api/strategies/{strategy_id}` updated — eagerly loads `config_snapshots`, includes
    them in `StrategyDetailOut`, computes per-version `config_snapshot_count` from loaded
    snapshots without an extra query.
  - Route registration order: `compare` registered before list endpoint; literal "versions"
    before config-snapshot sub-paths. No routing conflicts.
- **53 new backend tests** — `tests/test_versions_m15.py` across 6 test classes:
  - `TestCreateStrategyVersion` — 201, field values, optional fields null, 404 unknown strategy,
    409 duplicate label within strategy, same label allowed in different strategies, empty label
    422, timeline event created.
  - `TestListStrategyVersions` — empty list, returns created, newest-first, config_snapshot_count,
    404 unknown strategy, isolation between strategies.
  - `TestCreateConfigSnapshot` — 201, field values, hash determinism (key order invariant),
    different configs produce different hashes, param/assumption counting (zero when missing or
    non-dict), default source_type, version link, version from wrong strategy → 404, 404 strategy,
    timeline event.
  - `TestListConfigSnapshots` — empty, returns created, newest-first, no config_json blob in list,
    filter by version_id, 404, isolation.
  - `TestCompareConfigSnapshots` — identical → is_same_config true, diff params, metadata fields,
    snapshot A/B not found → 404, cross-strategy snapshot → 404, strategy not found → 404,
    assumptions diff, top-level diff.
  - `TestGetConfigSnapshotDetail` — 200, config_json present, all fields, 404.
  - `TestStrategyDetailM15` — config_snapshots field present, populated, no blob, per-version
    count, newest-first versions.
- **Frontend types** (`frontend/src/types/index.ts`):
  - `StrategyVersion` extended with `config_snapshot_count: number`.
  - `StrategyConfigSnapshotRead`, `StrategyConfigSnapshotDetail` interfaces.
  - `StrategyVersionCreateRequest`, `StrategyConfigSnapshotCreateRequest` request types.
  - `ConfigKeyChange`, `ConfigComparisonSection`, `ConfigComparisonResponse` interfaces.
  - `StrategyDetail.config_snapshots` field added.
- **API client** (`frontend/src/lib/api.ts`):
  - `createStrategyVersion()`, `getStrategyVersions()`.
  - `createConfigSnapshot()`, `getConfigSnapshots()`, `compareConfigSnapshots()`,
    `getConfigSnapshot()`.
- **`VersionCreateDrawer.tsx`** — right-panel drawer for creating a strategy version.
  Fields: version_label (required), git_commit, branch_name, code_path, signal_name,
  signal_description. 409 duplicate label surfaced as error. Calls `onCreated(version)`.
- **`ConfigSnapshotDrawer.tsx`** — right-panel drawer for logging a config snapshot.
  Fields: label (required), strategy_version_id (optional dropdown), source_type (select),
  source_filename, config_json (textarea). Validates JSON client-side before submit. Calls
  `onCreated(snapshot)`.
- **`RunLogDrawer.tsx` updated** — accepts optional `versions: StrategyVersion[]` prop.
  When versions are provided, shows a "Strategy Version (optional)" selector above Run Type.
  Selected version_id is included in the run payload.
- **`StrategyDetail.tsx` updated** — "Version & Config Evidence" section replaces the old
  "Code Versions" card:
  - Per-version rows show label, signal name, branch/path, git commit (7-char), created date.
  - Each version row has a collapsible chip showing linked config snapshot count; click expands
    an inline list of those snapshots (label, source_type, param/assumption counts, hash prefix).
  - Unlinked config snapshots (no version link) shown in a separate subsection.
  - Section header has "+ Create Version" and "+ Log Config" inline buttons.
  - Header action bar adds "+ Create Version" and "+ Log Config" buttons beside "Generate Report"
    and "+ Log Run".
  - `VersionCreateDrawer` and `ConfigSnapshotDrawer` wired up; both call
    `setRefreshKey((k) => k + 1)` on creation to refresh strategy detail.
  - `RunLogDrawer` receives `versions={strategy.versions}` for the version selector.
- **483 total passing tests** (1 skipped), zero TypeScript errors, clean production build.
  (545 total after M16.)

### What M15 does NOT build (by design)

- Recursive config diffing beyond one level of nesting.
- GitHub integration, automatic version detection from commits.
- SDK ingestion hooks or automated config snapshot creation.
- Deployment evidence or live drift attribution.
- AI explanations of config differences.
- Full strategy timeline beyond the existing audit trail.

### Verify with curl

```bash
# Create a strategy version
curl -s -X POST http://localhost:8000/api/strategies/<strategy_id>/versions \
  -H "Content-Type: application/json" \
  -d '{"version_label": "v1.0.0", "branch_name": "main", "signal_name": "50/200 SMA"}' \
  | python3 -m json.tool
# Response: id, strategy_id, version_label, config_snapshot_count=0, created_at, ...

# List versions with snapshot counts
curl "http://localhost:8000/api/strategies/<strategy_id>/versions" | python3 -m json.tool

# Log a config snapshot linked to the version
curl -s -X POST http://localhost:8000/api/strategies/<strategy_id>/config-snapshots \
  -H "Content-Type: application/json" \
  -d '{
    "label": "prod-config-2024-Q1",
    "strategy_version_id": "<version_id>",
    "config_json": {
      "params": {"lookback": 20, "threshold": 0.5},
      "assumptions": {"slippage": 0.001}
    }
  }' | python3 -m json.tool
# Response: id, config_hash (64-char SHA-256), param_count=2, assumption_count=1, ...

# List config snapshots (newest first)
curl "http://localhost:8000/api/strategies/<strategy_id>/config-snapshots" | python3 -m json.tool

# Filter by version
curl "http://localhost:8000/api/strategies/<strategy_id>/config-snapshots?version_id=<version_id>" \
  | python3 -m json.tool

# Compare two snapshots
curl "http://localhost:8000/api/strategies/<strategy_id>/config-snapshots/compare?snapshot_a_id=<a>&snapshot_b_id=<b>" \
  | python3 -m json.tool
# Response: is_same_config, top_level/params/assumptions diffs, highlighted_changes, total_changes

# Full snapshot detail (with config_json)
curl "http://localhost:8000/api/config-snapshots/<snapshot_id>" | python3 -m json.tool
```

> **M15 note:** Config hash is SHA-256 of `sort_keys=True` JSON — insertion order is irrelevant.
> Two configs with the same keys/values always produce the same hash. Comparison is flat (one
> level) and structural only — values compared with `==`, no recursive diff. Language is hedged.

---

## Previously completed — M14: Reliability Reports v1

**Status: complete.**

### M14 deliverables

- **Migration `0007_m14_reports_tables.py`** — adds 2 new tables: `reports` and `report_sections`.
  `reports` stores the top-level report record (type, score, summary, source FK, JSON blob).
  `report_sections` stores ordered evidence sections with optional severity and `evidence_json`.
  FKs: organization CASCADE, project/strategy SET NULL, report_id CASCADE (sections).
  14 indexes total. 16 total ORM tables.
- **`ReportType`, `ReportStatus`** StrEnum constants added to `constants.py`.
  `EventType.report_generated` added.
- **`app/models/report.py`** and **`app/models/report_section.py`** — two new ORM models.
  `Report` added to organization, project, and strategy relationships. `Report.sections` uses
  `cascade="all, delete-orphan"`.
- **`app/services/reports.py`** — deterministic report generation service. No AI, no live data,
  no external calls. Three generators:
  - **`generate_strategy_reliability_report(strategy_id, db)`** — 10 sections:
    `overview`, `strategy_activity`, `latest_runs`, `data_evidence`, `backtest_trust`,
    `cost_sensitivity` (conditional on `fragility_summary_json`), `fill_realism` (conditional on
    `fill_realism_json`), `open_alerts`, `recent_timeline`, `suggested_checks`.
    Score = avg(evidence_scores) − min(alert_penalty, 30), where evidence_scores includes latest
    backtest trust score and/or average snapshot health score. Score is `null` when neither
    source is available — never fabricated.
  - **`generate_backtest_audit_report(audit_id, db)`** — 6 sections:
    `audit_summary`, `trust_score_breakdown`, `cost_sensitivity` (conditional),
    `fill_realism` (conditional), `data_evidence`, `issues_and_checks`.
    Score = audit trust score directly.
  - **`generate_dataset_health_report(snapshot_id, db)`** — 6 sections:
    `snapshot_summary`, `data_health_score`, `quality_issues`, `schema_and_coverage`,
    `linked_strategy_runs`, `suggested_checks`.
    Score = snapshot health score directly.
  - **`persist_report(result, db)`** — writes a `ReportResult` to the DB; caller commits.
  - Section severity mapping: score < 50 → high; < 75 → medium; < 90 → low; else None.
  - All summaries use hedged, evidence-based language ("noted", "observed", "may require review").
    No causal claims, no AI language, no trading advice.
- **`app/schemas/reports.py`** — 4 Pydantic schemas: `ReportSectionRead`, `ReportRead`,
  `ReportDetail` (extends `ReportRead` with `sections`), `ReportListResponse`.
- **5 new API endpoints** (`app/api/routes/reports.py`):
  - `POST /api/reports/strategy/{strategy_id}` — generate strategy reliability report → 201.
  - `POST /api/reports/backtest-audit/{audit_id}` — generate backtest audit report → 201.
  - `POST /api/reports/dataset-snapshot/{snapshot_id}` — generate dataset health report → 201.
  - `GET  /api/reports` — paginated list (filters: `report_type`, `strategy_id`, `source_type`,
    `limit`, `offset`). Newest first.
  - `GET  /api/reports/{report_id}` — report detail with all sections. 404 if not found.
  - All three POST endpoints emit a `report_generated` `AuditTimelineEvent`.
- **80 new backend tests** — `tests/test_reports_m14.py` across 8 test classes:
  - All three POST endpoints → 201, required sections present, correct `report_type`/`source_type`
  - Score null when no evidence, score computed when audit or snapshot exists
  - Score is integer 0–100, equals trust_score (backtest) or health_score (dataset)
  - Section fields, order_index sequential, evidence_json populated
  - Conditional sections (cost_sensitivity, fill_realism) only present when data available
  - List endpoint pagination, filters, envelope shape, items do not include sections
  - GET detail returns sections; sections match POST response
  - 404 for all three unknown IDs
  - Timeline event created on generation; report_id in metadata
  - No causal overclaiming language in summaries
  - `report_json` populated with correct IDs
- **Frontend types** — `ReportType`, `ReportStatus`, `ReportSection`, `ReportRead`,
  `ReportDetail`, `ReportListResponse`, `ReportFilters` added to `frontend/src/types/index.ts`.
- **API client** — `generateStrategyReport()`, `generateBacktestAuditReport()`,
  `generateDatasetSnapshotReport()`, `getReports()`, `getReport()` added to `frontend/src/lib/api.ts`.
- **`Reports.tsx` page** — list + detail view:
  - Filter bar (All / Strategy / Backtest / Dataset type chips).
  - Report list rows: score chip, type badge, title, summary excerpt, date, source type.
  - Pagination (25 per page, prev/next).
  - Report detail: score pill with bar, title, summary, section count, generated timestamp.
  - Section rows: expandable with evidence_json raw JSON view. Severity chips colour-coded.
  - Empty state with guidance to generate reports from Strategy/Backtest pages.
  - URL: `/reports` (list) and `/reports/:id` (detail with back button).
- **`StrategyDetail.tsx` update** — "Generate Report" button in strategy header.
  On click, calls `POST /api/reports/strategy/{id}`. On success, shows a mini report summary
  panel below the stat strip (score, title, summary, section count, date) with a "view full
  report →" link to `/reports/{id}`.
- **Nav** — "Reports" item added to Analysis section in `frontend/src/lib/nav.ts`.
- **430 total passing tests** (1 skipped), zero TypeScript errors, clean production build.

### What M14 does NOT build (by design)

- PDF export, AI-generated reports, email/Slack delivery, scheduled reports.
- Live drift reports, execution attribution reports.
- Report versioning, diff-between-reports, archiving workflows.
- SDK or external trigger endpoints.

### Verify with curl

```bash
# Generate a strategy reliability report
curl -s -X POST http://localhost:8000/api/reports/strategy/<strategy_id> \
  | python3 -m json.tool
# Response: id, report_type="strategy_reliability", score, summary, sections[{section_key, title, ...}]

# Generate a backtest audit report
curl -s -X POST http://localhost:8000/api/reports/backtest-audit/<audit_id> \
  | python3 -m json.tool

# Generate a dataset health report
curl -s -X POST http://localhost:8000/api/reports/dataset-snapshot/<snapshot_id> \
  | python3 -m json.tool

# List all reports (paginated, newest first)
curl "http://localhost:8000/api/reports?limit=10" | python3 -m json.tool

# Filter by type
curl "http://localhost:8000/api/reports?report_type=strategy_reliability" | python3 -m json.tool

# Filter by strategy
curl "http://localhost:8000/api/reports?strategy_id=<strategy_id>" | python3 -m json.tool

# Get report detail with all sections
curl "http://localhost:8000/api/reports/<report_id>" | python3 -m json.tool
```

> **M14 note:** All reports are deterministic — computed from existing DB evidence, never
> fabricated. Scores are `null` when insufficient evidence exists. Language is hedged
> ("noted", "observed", "may require review") and never makes causal claims or investment
> recommendations.

---

## Previously completed — M13: Backtest Reality Check v2

**Status: complete.**

### M13 deliverables

- **Migration `0006_m13_backtest_sensitivity.py`** — adds 3 nullable JSON columns to
  `backtest_audits`: `cost_sensitivity_json`, `fill_realism_json`, `fragility_summary_json`.
- **`app/core/constants.py`** — 9 new `BacktestIssueType` values:
  `high_cost_fragility`, `medium_cost_fragility`, `same_bar_fill`, `mid_fill_no_slippage`,
  `high_participation_rate`, `elevated_participation_rate`, `missing_liquidity_filter`,
  `missing_execution_timing`, `high_trade_count_simple_fill`.
- **`app/services/backtest_reality.py`** — full rewrite with M13 analyses (all M8 checks preserved):
  - **I. Cost sensitivity** (`_analyze_cost_sensitivity`): estimates adjusted return and Sharpe
    under 5/10/15/25/50 bps cost scenarios. Incremental drag = `turnover × (cost_bps − assumed_cost_bps) / 10 000`.
    Fragility level: "high" if estimated Sharpe < 1.0 at 10 bps; "medium" if < 1.0 at 25 bps;
    "low" otherwise. Returns "unknown" when turnover or both return/sharpe are absent.
  - **J. Fill realism** (`_analyze_fill_realism`): examines fill_model, slippage_bps,
    execution_timing, participation_rate, liquidity_filter, trade_count. Produces structured
    `findings` list and an overall `fill_realism_level`:
    `weak` → high-severity finding present; `review` → medium finding; `strong` → slippage +
    timing both present; `acceptable` → fill model present with no medium+ findings; `unknown` → no fill_model.
  - **K. Fragility summary** (`_build_fragility_summary`): rolls cost + fill into `overall_fragility`
    and `key_concerns`.
  - New BacktestIssues created for M13 findings; M8 duplicates (`missing_fill_model`,
    `close_fill_model`, `same_close_fill`) skipped to avoid double-counting.
  - `missing_liquidity_filter` now maps to `liquidity_realism_score` (was always 100 in M8).
  - All outputs are labelled as estimates: "approximate", "not a full re-backtest",
    "may require review". No causal language.
- **`app/schemas/backtest.py`** — 5 new typed nested schemas:
  `CostSensitivityScenario`, `CostSensitivityResult`, `FillRealismFinding`, `FillRealismResult`,
  `FragilitySummary`. `BacktestAuditRead` and `BacktestAuditListItem` updated.
  `BacktestAuditListItem` adds `cost_fragility_level: str | None` and `fill_realism_level: str | None`
  (null = unknown/unavailable — not the string "unknown").
- **`app/api/routes/backtests.py`** — POST audit persists JSON blobs; GET and list endpoints
  return them; list items extract fragility levels for quick display.
- **38 new tests** — `tests/test_backtest_m13.py`:
  - M13 JSON fields present in POST and GET responses
  - Scenarios at 5/10/15/25/50 bps present
  - Adjusted return and Sharpe decrease monotonically as cost increases
  - High fragility (Sharpe < 1.0 at 10 bps), medium fragility (< 1.0 at 25 bps)
  - Unknown fragility when turnover missing; no divide-by-zero on edge cases
  - `incremental_cost_drag == 0` at assumed cost level
  - Assumed cost bps included in scenarios
  - Fill realism: unknown level when fill_model missing
  - `same_bar_fill` issue + weak level for same_bar/intrabar fills
  - `mid_fill_no_slippage` issue for mid/midpoint fills without slippage_bps
  - `high_participation_rate` and `elevated_participation_rate` issues
  - `missing_liquidity_filter` issue and `liquidity_realism_score < 100`
  - Strong fill_realism_level with full assumptions
  - Fragility summary keys present; overall_fragility = high for weak fill
  - Trust score reduced by M13 issues; `fill_realism_score < 100` for same_bar
  - List endpoint returns `cost_fragility_level` and `fill_realism_level`; null for unknown
  - M8 backward-compatibility: `close_fill_model` and `missing_fill_model` still raised exactly once
- **Frontend types** — 5 new interfaces: `CostSensitivityScenario`, `CostSensitivityResult`,
  `FillRealismFinding`, `FillRealismResult`, `FragilitySummary`. `BacktestAudit` and
  `BacktestAuditListItem` updated with M13 fields.
- **`Backtests.tsx`** — `AuditCard` updated:
  - Cost/fill fragility level chips.
  - Compact cost sensitivity scenario strip showing Sharpe at 5/10/25/50 bps.
  - Top fill realism findings (medium+ severity, excluding informational).
  - Liquidity subscore added (now 5 subscores: Cost / Fill / Liquidity / Borrow / Data).
- **`StrategyDetail.tsx`** — `BacktestAuditPanel` updated:
  - Fragility key_concerns banner (when present).
  - Collapsible **Cost Sensitivity** section: compact scenario table with baseline + 5 cost tiers,
    adjusted return %, adjusted Sharpe (colour-coded below 1.0), Sharpe delta.
  - Collapsible **Fill Realism** section: fill_model, findings list, slippage/timing/participation metadata.
  - Liquidity subscore added (5 subscores).
- **350 total passing tests** (1 skipped), zero TypeScript errors, clean production build.

### What M13 does NOT build (by design)

- Live execution drift or real broker fills.
- AI-generated explanations or scoring.
- Full overfit / parameter sensitivity engine (parameter sweeps, walk-forward, etc.).
- Regime analysis or market condition attribution.
- SDK ingestion or external data providers.
- Email, Slack, or webhook delivery of fragility reports.

### Verify with curl

```bash
# Post an audit for a run with detailed assumptions:
curl -s -X POST http://localhost:8000/api/strategy-runs/<run_id>/backtest-audit | python3 -m json.tool

# The response includes cost_sensitivity_json, fill_realism_json, fragility_summary_json.
# Example cost_sensitivity_json snippet:
# {
#   "assumed_cost_bps": 5.0,
#   "base_sharpe": 1.8,
#   "cost_fragility_level": "low",
#   "scenarios": [
#     { "cost_bps": 5.0,  "adjusted_sharpe": 1.80, "sharpe_delta": 0.0 },
#     { "cost_bps": 10.0, "adjusted_sharpe": 1.62, "sharpe_delta": -0.18 },
#     { "cost_bps": 25.0, "adjusted_sharpe": 1.26, "sharpe_delta": -0.54 },
#     { "cost_bps": 50.0, "adjusted_sharpe": 0.72, "sharpe_delta": -1.08 }
#   ],
#   "warnings": ["These are estimates only — not a full re-backtest. Treat as indicative."]
# }
```

> **M13 note:** All numeric outputs are estimates derived from logged metrics. They are not a
> substitute for a full re-backtest with explicit cost scenarios. Language throughout uses
> "estimated", "approximate", "may require review" and never makes definitive causal claims.

---

## Previously completed — M12: Dataset Snapshot Comparison

**Status: complete.**

### M12 deliverables

- **`app/schemas/dataset_comparison.py`** — 9 new Pydantic schemas covering every comparison
  section: `MetadataComparison`, `SchemaComparison`, `TypeChange`, `SymbolCoverageComparison`,
  `TimestampCoverageComparison`, `DataHealthComparison`, `ValueRevisionExample`,
  `ValueRevisionsComparison`, `DatasetSnapshotComparisonResponse`.
- **`app/services/dataset_comparison.py`** — pure-Python deterministic comparison service
  (`compare_snapshots()`). No DB access, no AI, no causal language. Covers:
  - **Metadata** — row count delta.
  - **Schema** — added/removed columns, type changes (inferred via `_infer_type()`).
  - **Symbol coverage** — added/removed symbols, common count, keyed_by_symbol flag.
  - **Timestamp range** — min/max date change detection, date-range-days delta.
  - **Data health** — health score delta, issue count delta, worst severity, issue type changes.
  - **Value revisions** — row-level diff keyed by `(symbol, timestamp)` composite key;
    SHA-256 hash-based fallback when keys unavailable; `MAX_EXAMPLES = 20` cap.
  - **Highlighted changes** — top-N human-readable bullet points.
  - **Deterministic explanation** — hedged prose ("observed", "may affect", never causal).
  - **Warnings** — different column sets, hash-fallback active, examples capped.
- **New API endpoint** — `GET /api/datasets/{dataset_id}/snapshots/compare`:
  - Query params: `snapshot_a_id`, `snapshot_b_id`.
  - Validates dataset exists (404), both snapshots exist (404 each), both belong to dataset (400).
  - Comparing a snapshot to itself returns `is_same_snapshot: true` with empty diffs.
- **46 new backend tests** — `tests/test_dataset_comparison_m12.py` across 10 test classes:
  basic shape, error cases (404/400), same-snapshot, metadata, schema, symbol coverage,
  timestamp coverage, data health, value revisions (keyed + hash fallback + cap), explanation
  language (no causal keywords), warnings.
- **Frontend types** — `MetadataComparison`, `TypeChange`, `SchemaComparison`,
  `SymbolCoverageComparison`, `TimestampCoverageComparison`, `DataHealthComparison`,
  `ValueRevisionExample`, `ValueRevisionsComparison`, `DatasetSnapshotComparisonResponse`
  added to `frontend/src/types/index.ts`.
- **`compareDatasetSnapshots()`** added to `frontend/src/lib/api.ts`.
- **Data Health page rewrite** (`DataHealth.tsx`):
  - **Compare Snapshots panel** — visible when selected dataset has ≥2 snapshots.
  - Snapshot A / Snapshot B selectors; defaults to previous vs latest.
  - "Compare →" button triggers deterministic diff.
  - **Result display** — summary card, warnings, notable changes bullet list, deterministic
    explanation, column-header row, then six section cards:
    - **Metadata** — row count A/B/delta.
    - **Schema** — column counts, added/removed column pills, type change table.
    - **Symbol Coverage** — symbol counts, added/removed symbol pills.
    - **Timestamp Coverage** — min/max dates, range-days delta.
    - **Data Health** — health score delta, issue count delta, worst severity, issue type pills.
    - **Value Revisions** — added/removed/changed counts; examples table (symbol, timestamp,
      type, changed fields, field deltas); capped-examples note.
  - Empty state when <2 snapshots: "Upload at least two snapshots to compare dataset drift."
  - `DatasetSections` component loads dataset detail once and renders both history and compare.
- **312 total passing tests** (1 skipped) at M12 completion, zero TypeScript errors, clean production build.

### Verify with curl

```bash
# Upload two snapshots for the same dataset, then compare:
curl -s "http://localhost:8000/api/datasets/<dataset_id>/snapshots/compare?\
snapshot_a_id=<snap_a_id>&snapshot_b_id=<snap_b_id>" | python3 -m json.tool
```

Example response (abridged):
```json
{
  "is_same_snapshot": false,
  "summary": "3 notable change(s) detected across schema, coverage, health, and row data.",
  "highlighted_changes": [
    "Row count changed: 4 → 5 (+1)",
    "Timestamp range extended: max date changed to 2024-01-04",
    "1 row(s) with revised values (e.g. AAPL / 2024-01-02)"
  ],
  "deterministic_explanation": "1 difference(s) were observed in row counts...",
  "warnings": [],
  "metadata": { "row_count_a": 4, "row_count_b": 5, "row_count_delta": 1 },
  "value_revisions": {
    "keyed_comparison_available": true,
    "added_rows_count": 1,
    "removed_rows_count": 0,
    "changed_rows_count": 1,
    "examples": [...]
  }
}
```

> **M12 note:** The comparison engine is purely deterministic — it diffs stored snapshot data.
> No AI is used. Language in `deterministic_explanation` is explicitly hedged
> ("observed", "noted", "may affect") and never makes causal claims.

---

## Previously completed — M11: Alerts Engine v1

**Status: complete.**

### M11 deliverables

- **2 new ORM models** — `AlertRule`, `Alert` (14 total tables). Alembic migration
  `0005_m11_alert_tables.py` chained from `0004`. `Alert` has cascade-delete from
  `Organization` and nullable SET NULL from `Strategy`.
- **`AlertRuleType`, `AlertStatus`** StrEnum constants added to `constants.py`.
  `EventType.alert_generated` and `EventType.alert_status_changed` added.
- **`app/services/alerts.py`** — pure-Python deterministic alert generation (no AI, no
  external calls). Five check types:
  1. **`data_health_below_threshold`** — `DatasetSnapshot.health_score < 70`:
     critical <25, high <50, medium <70.
  2. **`backtest_trust_below_threshold`** — `BacktestAudit.trust_score < 70`:
     same severity thresholds.
  3. **`data_quality_issue_high_or_critical`** — any `DataQualityIssue` with severity
     high/critical: critical issue → high alert, high issue → medium alert.
  4. **`backtest_issue_high_or_critical`** — any `BacktestIssue` with severity
     high/critical: same escalation.
  5. **`strategy_run_missing_dataset_evidence`** — backtest/research/paper runs with no
     linked `dataset_snapshot_id` → low severity alert.
  **Deduplication:** if an open/acknowledged/snoozed alert already exists for the same
  `rule_type + source_type + source_id`, the new alert is skipped. Resolved alerts allow
  re-triggering.
- **4 new API endpoints:**
  - `POST /api/alerts/generate` — trigger the generation service for the default org;
    returns `{ alerts_created, alerts_skipped_duplicate, total_alerts_open }`.
  - `GET  /api/alerts` — paginated + filterable list (`status`, `severity`, `rule_type`,
    `strategy_id`, `limit`, `offset`). Returns `{ items, total, limit, offset }`.
  - `GET  /api/alerts/{id}` — fetch a single alert. 404 if not found.
  - `PATCH /api/alerts/{id}` — update alert status. Transitions open→acknowledged set
    `acknowledged_at`; any transition to resolved sets `resolved_at`. 422 on invalid status.
- **Dashboard integration** — `GET /api/dashboard/summary` now includes:
  - `counts.open_alert_count`, `counts.high_critical_alert_count`
  - `recent_alerts: list[DashboardAlertItem]` (up to 5, most-recent-first)
- **`Alerts.tsx` page rewrite** — full evidence-driven alert page:
  - **Filter bar** — status, severity, rule type dropdowns.
  - **Alert rows** — severity dot, status badge, rule type chip, title, expandable
    description, acknowledge/resolve action buttons.
  - **"Run alert check" button** — calls `POST /api/alerts/generate`; shows
    `+N created · M skipped` feedback; reloads list.
  - **Load more** pagination.
- **Dashboard Reliability Signals panel** — new panel showing open alert count,
  high/critical count badge, and up to 5 recent alerts. Links to `/alerts`.
- **`Alert`, `AlertListResponse`, `AlertGenerateResponse`, `AlertFilters`,
  `AlertUpdateRequest`, `DashboardAlertItem`** added to `frontend/src/types/index.ts`.
- **`generateAlerts()`, `getAlerts()`, `getAlert()`, `updateAlert()`** added to
  `frontend/src/lib/api.ts`.
- **32 new tests** — `tests/test_alerts_m11.py`: generate shape, deduplication,
  resolved re-trigger, low trust/health/missing-evidence alerts, list pagination + filters,
  GET / PATCH routes (404, 422, timestamp side-effects), dashboard integration.
- **266 total passing tests** (1 skipped), clean TypeScript typecheck, clean production build.
- **Alembic migration applied** to `backend/quantfidelity.db`.

### Verify with curl

```bash
# Generate alerts (idempotent — safe to run multiple times)
curl -s -X POST http://localhost:8000/api/alerts/generate | python3 -m json.tool
# Response: { "alerts_created": N, "alerts_skipped_duplicate": M, "total_alerts_open": K }

# List all open alerts (newest-triggered first)
curl "http://localhost:8000/api/alerts?status=open" | python3 -m json.tool

# Filter by severity
curl "http://localhost:8000/api/alerts?severity=high" | python3 -m json.tool

# Filter by rule type
curl "http://localhost:8000/api/alerts?rule_type=data_health_below_threshold" | python3 -m json.tool

# Acknowledge an alert
curl -s -X PATCH http://localhost:8000/api/alerts/<alert_id> \
  -H 'Content-Type: application/json' \
  -d '{"status": "acknowledged"}' | python3 -m json.tool

# Resolve an alert
curl -s -X PATCH http://localhost:8000/api/alerts/<alert_id> \
  -H 'Content-Type: application/json' \
  -d '{"status": "resolved"}' | python3 -m json.tool

# Dashboard includes alert counts + recent alerts
curl "http://localhost:8000/api/dashboard/summary" | python3 -m json.tool
```

> **M11 note:** The alerts engine is purely deterministic — it evaluates existing DB
> evidence against hardcoded thresholds. No AI, no live data, no email/Slack, no broker
> actions. Alerts are informational reliability signals, not incident tickets.

### Previously completed

- **M10: Audit Timeline v1** — improved `/api/timeline` with pagination + 5 filters,
  `/api/strategies/{id}/timeline`, richer event data, Timeline page rewrite, AuditTrailPanel,
  40 tests, 234 total tests.

---

## Previously completed — M10: Audit Timeline v1

**Status: complete.**

### M10 deliverables

- **Improved `GET /api/timeline`** — now returns a paginated envelope (`items`, `total`,
  `limit`, `offset`) instead of a bare list. Supports five optional AND-combined filters:
  `project_id`, `strategy_id`, `event_type`, `severity`, `source_type`. Max limit 200.
  Newest-first ordering on `event_time`.
- **New `GET /api/strategies/{strategy_id}/timeline`** — scoped event stream for one strategy.
  Supports `limit` and `offset`. Returns 404 for unknown strategies.
- **Richer event data for all four source types:**
  - `strategy_created` — adds `description` (asset class, project, status) + `metadata_json`
    (strategy_name, asset_class, status, project_name).
  - `strategy_run_logged` — adds `description` (run type, strategy name, status, universe) +
    `metadata_json` (run_type, status, universe_name, strategy_name).
  - `dataset_snapshot_uploaded` — already had description + metadata; unchanged.
  - `backtest_audited` — adds `description` (trust score, status, issue count) + enriched
    `metadata_json` (run_name, trust_score, overall_status, issue_count, strategy_name).
    Severity now escalates: trust <25 → high, <50 → medium, <75 → low, ≥75 → info.
- **Timeline page rewrite** — real evidence stream with:
  - **Filter bar** — source type, severity, event type dropdowns (reset to page 1 on change).
  - **Event rows** — severity dot, event-type badge (colour-coded by type), title, expandable
    description, metadata score if available (trust/health/Sharpe), source type label, timestamp.
  - **Load more** button — appends next page without scroll-to-top, shows remaining count.
  - **Total counter** — shows matching event count in filter bar.
  - Evidence language throughout: "Evidence Stream", "Audit Trail", "Run Evidence", etc.
- **Strategy Detail audit trail panel** — compact 5-event preview at the bottom of each
  strategy page, loaded from `GET /api/strategies/{id}/timeline`. Shows event-type badge,
  title, date. Overflow footer if total > 5. Links to `/timeline`.
- **`TimelineEvent`, `TimelineListResponse`, `TimelineFilters`** added to
  `frontend/src/types/index.ts`.
- **`getTimeline()`, `getStrategyTimeline()`** added to `frontend/src/lib/api.ts`.
- **40 new tests** — `tests/test_timeline_m10.py`: shape, pagination, all filters, AND-combining,
  strategy-scoped endpoint, event quality (descriptions + metadata), severity escalation,
  count increments for all four event sources.
- **3 existing tests patched** — `test_db.py` (list → paginated envelope), `test_comparison_m5.py`
  (limit 500→200, total count via `.json()["total"]`), `test_data_health_m6.py` (items[0] index).
- **234 total passing tests**, clean TypeScript typecheck, clean production build.

> **Note:** The timeline is an evidence/audit trail, not an alert system. It records facts
> (what happened and when) without raising notifications, scoring urgency, or creating tasks.
> No AI summaries, no alert engine, no incident queue.

### Verify with curl

```bash
# Paginated event stream — default 50, newest first
curl "http://localhost:8000/api/timeline" | python3 -m json.tool
# Response: { "items": [...], "total": N, "limit": 50, "offset": 0 }

# Filter by source type (strategy / strategy_run / dataset_snapshot / backtest_audit)
curl "http://localhost:8000/api/timeline?source_type=backtest_audit" | python3 -m json.tool

# Filter by severity escalation
curl "http://localhost:8000/api/timeline?severity=high" | python3 -m json.tool

# AND-combine filters
curl "http://localhost:8000/api/timeline?event_type=strategy_run_logged&severity=info" \
  | python3 -m json.tool

# Paginate
curl "http://localhost:8000/api/timeline?limit=10&offset=10" | python3 -m json.tool

# Strategy-scoped timeline (newest first for that strategy only)
curl "http://localhost:8000/api/strategies/<strategy_id>/timeline" | python3 -m json.tool
```

### Previously completed

- **M9: Unified Reliability Dashboard v1** — aggregated endpoint, score strip, evidence counters,
  data health + backtest trust panels, recent activity panels, 27 tests, 194 total tests.

---

## Previously completed — M9: Unified Reliability Dashboard v1

**Status: complete.**

### M9 deliverables

- **`GET /api/dashboard/summary`** — single aggregated endpoint returning all M3–M8 evidence
  in one response. Scores are `null` when no evidence exists; never faked.
- **`app/services/dashboard_summary.py`** — pure SQLAlchemy aggregation service (no AI, no
  external calls). Queries all M3–M8 tables for counts, averages, minimums, and most-recent
  evidence items.
- **Score design:** All four dimension scores are `null` until real evidence is ingested.
  - `data_health_score` — average `DatasetSnapshot.health_score` across all snapshots.
  - `backtest_trust_score` — average `BacktestAudit.trust_score` across all audits.
  - `strategy_activity_score` — deterministic formula: 0 strategies → null; 1+ strategies + 0 runs → 20;
    1–2 runs → 40; 3–5 → 60; 6–9 → 80; 10+ → 100.
  - `overall_reliability_score` — simple average of available (non-null) dimension scores.
- **`DashboardSummary` schema** — `generated_at`, `counts` (all evidence counts), `scores`
  (four reliability dimensions + lowest scores), `recent_runs`, `recent_snapshots`,
  `recent_audits`, `recent_timeline_events` (most-recent 5 each).
- **Dashboard page rewrite** — evidence-driven reliability cockpit:
  - **Score strip** — four pillars (Overall, Data Health, Backtest Trust, Strategy Activity).
    Each shows the real score (green/yellow/orange/red) or "—" + "No evidence yet" when null.
  - **Evidence counters** — strategies, total runs, dataset snapshots, backtest audits.
  - **Active strategies table** — top-6, links to detail pages.
  - **Data Health panel** — snapshot count, with-issues count, lowest score, issues-by-severity
    chips. Empty state links to /datasets.
  - **Backtest Trust panel** — audit count, issue count, lowest trust, status breakdown,
    issues-by-severity chips. Empty state links to /backtests.
  - **Recent Activity** — four side-by-side panels (recent runs, snapshots, audits, timeline
    events). Each item shows title, strategy name, score (colour-coded), date.
- **`DashboardSummary`, `DashboardCounts`, `DashboardScores`, `RecentEvidenceItem`** added to
  `frontend/src/types/index.ts`.
- **`getDashboardSummary()`** added to `frontend/src/lib/api.ts`.
- **27 new tests** — `tests/test_dashboard_m9.py`: shape, counts, scores, score null/non-null
  contracts, run/snapshot/audit increments, recent items, 5-item caps.
- **194 total passing tests**, clean TypeScript typecheck, clean production build.

### Verify with curl

```bash
curl http://localhost:8000/api/dashboard/summary | python3 -m json.tool
# Response: generated_at, counts{…}, scores{data_health_score, backtest_trust_score,
#   strategy_activity_score, overall_reliability_score, …},
#   recent_runs[…], recent_snapshots[…], recent_audits[…], recent_timeline_events[…]
```

> **M9 note:** All scores are computed deterministically from existing DB records. No AI,
> no live market data, no external calls. Scores return `null` when no evidence exists —
> "No evidence yet" is the correct state, not a fake 100.

### Previously completed

- **M8: Backtest Reality Check v1** — 2 new tables, 8-category audit engine, 3 endpoints,
  Backtests page rewrite, StrategyDetail audit panel, 34 tests, 167 total tests.

---

## Previously completed — M8: Backtest Reality Check v1

**Status: complete.**

### M8 deliverables

- **2 new ORM models** — `BacktestAudit`, `BacktestIssue` (12 total tables). Alembic migration
  `0004_m8_backtest_audit_tables.py` chained from `0003`. Cascade-delete: removing an audit also
  removes its issues. POST is idempotent — re-auditing a run replaces the existing audit.
- **`backtest_reality.py` service** — pure Python deterministic engine (no AI, no database
  access). 8 check categories:
  - **A. Transaction cost realism** — missing, zero, or unusually low `transaction_cost_bps`
  - **B. Fill model realism** — missing `fill_model`; close/EOD fills; open fills without slippage
  - **C. Borrow / short realism** — `short_enabled=true` with missing or zero `borrow_rate`
  - **D. Sample size / trade count** — high Sharpe with very few trades
  - **E. Turnover realism** — `turnover > 1.5×` (medium) or `> 3.0×` (high)
  - **F. Data evidence** — low health score (<70), critical data issue, or no linked snapshot
  - **G. Max drawdown sanity** — `abs(max_drawdown) > 0.5`
  - **H. Metric plausibility** — Sharpe >4, annual return >100%, zero volatility with non-zero return
- **Trust score formula**: start 100, subtract per-issue (critical=−25, high=−15, medium=−8,
  low=−3), floor 0. Six subscores (cost, fill, borrow, data_quality, lookahead, liquidity) use
  the same formula scoped by category. `overall_status`: excellent ≥90, good 75–89, review
  50–74, weak 25–49, unreliable <25. Summary language is explicitly hedged ("may indicate",
  "could make results optimistic") — never causal.
- **3 new API endpoints:**
  - `POST /api/strategy-runs/{run_id}/backtest-audit` — run + store audit (idempotent), 201.
    Returns 404 if run not found. Returns 400 for live runs.
  - `GET  /api/strategy-runs/{run_id}/backtest-audit` — fetch latest audit, 404 if none.
  - `GET  /api/backtests/audits` — newest-first list with strategy/run context.
- **`BacktestStatus`, `BacktestIssueType`, `backtest_audited` EventType** added to `constants.py`.
- **`BacktestAuditListItem`, `BacktestAuditDetail`, `BacktestAuditRead`, `BacktestIssueRead`**
  Pydantic schemas.
- **`Backtests` page** — full rewrite: audit list with trust score bar, status chip, subscore
  grid (cost/fill/borrow/data), top issues with severity dots, summary text. Empty state links
  to Strategy Lab.
- **`StrategyDetail` audit panel** — "Run Backtest Audit" button per eligible run
  (backtest/research/paper). After auditing: shows trust score + status + subscore grid +
  expandable issue list with suggested checks. "Re-audit" link. Live runs show a disabled note.
- **34 new tests** — `tests/test_backtest_reality_m8.py`: all 8 check categories, trust score
  formula, status thresholds, idempotency/deduplication, 404/400 error cases, list context.
- **167 total passing tests**, clean TypeScript typecheck, clean production build.
- **Alembic migration applied** to `backend/quantfidelity.db`.

### Verify with curl

```bash
# Audit a backtest run (idempotent — re-POST replaces existing audit)
curl -s -X POST http://localhost:8000/api/strategy-runs/<run_id>/backtest-audit \
  | python3 -m json.tool
# Response: trust_score, overall_status, issues[], subscores

# Fetch the latest audit for a run
curl http://localhost:8000/api/strategy-runs/<run_id>/backtest-audit | python3 -m json.tool

# List all audits with strategy/run context
curl http://localhost:8000/api/backtests/audits | python3 -m json.tool
```

> **M8 note:** The backtest reality engine is purely deterministic — it evaluates logged
> `params_json`, `assumptions_json`, and `metrics_json` against rule thresholds. No AI is
> used. Issue language ("may indicate", "could make results optimistic") is explicitly hedged
> and never makes causal claims.

### Previously completed

- **M7: Strategy Run Dataset Linkage + Data Evidence** — dataset_snapshot_id FK, DataEvidenceSummary,
  RunLogDrawer dataset selector, StrategyDetail evidence panel, 14 tests, 133 total tests.

---

## Previously completed — M7: Strategy Run Dataset Linkage + Data Evidence

**Status: complete.**

### M7 deliverables

- **`dataset_snapshot_id` on `strategy_runs`** — nullable FK column linking any run to a
  QuantFidelity dataset snapshot from the same project. Alembic migration `0003` (batch-mode
  for SQLite) adds the column with a `SET NULL` cascade. The existing `dataset_version` free-text
  label is kept unchanged.
- **Validation** — `POST /api/strategies/{id}/runs` accepts optional `dataset_snapshot_id`.
  If provided: snapshot must exist (404), and its dataset must belong to the same project as
  the strategy (400). Cross-project links are rejected.
- **`DataEvidenceSummary` schema** — lightweight evidence object embedded in `StrategyRunOut`:
  `dataset_name`, `snapshot_label`, `health_score`, `row_count`, `column_count`, `symbol_count`,
  `min_timestamp`, `max_timestamp`, `issue_count`, `worst_severity`. Column/symbol/timestamp
  stats are computed from `rows_json` at response time (no extra DB columns).
- **Enriched run responses** — `GET /api/strategies/{id}`, `GET /api/strategies/{id}/runs`,
  and `POST /api/strategies/{id}/runs` all include `dataset_snapshot` evidence when linked.
  No-linked runs return `"dataset_snapshot": null`.
- **`Data Evidence` panel** on Strategy Detail page — shows health score bar, row count,
  symbol count, column count, issue count, worst severity, and timestamp range from the
  most recent run with a linked snapshot.
- **Per-run data evidence chip** in Run Evidence list — inline health score + dataset
  name + snapshot label + issue summary per run. Unlinked runs show subtle "No dataset
  snapshot linked" text.
- **`RunLogDrawer` dataset selector** — two-stage selector: first choose a dataset (loaded
  from `/api/datasets`), then choose a snapshot (loaded from `/api/datasets/{id}/snapshots`).
  Selected snapshot shows health score preview. Blank = no link.
- **14 new tests** — `tests/test_run_dataset_link_m7.py`: linked run 201, evidence fields,
  column/symbol/timestamp stats, issue_count + worst_severity, nonexistent snapshot 404,
  run list includes evidence, strategy detail includes evidence, unlinked runs return null.
- **133 total passing tests**, clean TypeScript typecheck, clean production build.
- **Alembic migration applied** to `backend/quantfidelity.db`.

### Verify with curl

```bash
# Log a run linked to a dataset snapshot
curl -s -X POST http://localhost:8000/api/strategies/<strategy_id>/runs \
  -H 'Content-Type: application/json' \
  -d '{
    "run_name": "Q1 Backtest with OHLCV v2",
    "run_type": "backtest",
    "status": "completed",
    "dataset_snapshot_id": "<snapshot_id>",
    "metrics_json": {"sharpe": 1.4, "max_drawdown": -0.12}
  }' | python3 -m json.tool
# Response includes "dataset_snapshot": { "health_score": ..., "issue_count": ... }

# Fetch strategy detail — runs include data evidence
curl http://localhost:8000/api/strategies/<strategy_id> | python3 -m json.tool
```

### Previously completed

- **M6: Dataset Snapshot Upload + Basic Data Health** — 3 tables, 6 endpoints, data quality
  engine (10 check types), DataHealth page, 27 tests, 119 total tests.

---

### M6 deliverables

- **3 new ORM models** — `Dataset`, `DatasetSnapshot`, `DataQualityIssue` (10 total
  tables). Alembic migration `0002_m6_dataset_tables.py` chained from `0001`.
- **6 new API endpoints:**
  - `POST /api/datasets` — register a named dataset (type: ohlcv/factors/fundamentals/
    returns/custom; source: manual/vendor/computed/sdk). Validates project exists. 201.
  - `GET /api/datasets` — list all datasets with snapshot count. 200.
  - `GET /api/datasets/{id}` — dataset detail with snapshot metadata list. 404 if missing.
  - `POST /api/datasets/{id}/snapshots` — ingest a JSON array of row objects; runs all
    10 data quality checks; persists issues; computes health score; creates
    `dataset_snapshot_uploaded` audit timeline event. Returns `DatasetSnapshotDetail`. 201.
  - `GET /api/datasets/{id}/snapshots` — list snapshots for a dataset (newest first). 200.
  - `GET /api/dataset-snapshots/{snapshot_id}` — snapshot detail with all quality issues.
- **`app/services/data_quality.py`** — pure Python quality engine (no AI, no database
  access). 10 check types: `missing_values`, `duplicate_rows`,
  `duplicate_symbol_timestamp`, `invalid_timestamp`, `negative_zero_price`,
  `high_lt_low`, `close_outside_range`, `open_outside_range`, `negative_volume`,
  `suspicious_return_jump` (>25% medium, >50% high). Health score formula: start 100,
  subtract per-issue penalty (critical=25, high=15, medium=8, low=3), floor at 0.
- **`app/schemas/dataset.py`** — `DatasetCreate`, `DatasetRead`, `DatasetDetail`,
  `DatasetSnapshotCreate`, `DatasetSnapshotRead`, `DatasetSnapshotDetail`,
  `DataQualityIssueRead` Pydantic schemas.
- **`DataHealth` page** — full rewrite: dataset list with create form (left panel), selected
  dataset detail, "Upload & Analyse" snapshot form with JSON textarea, health score bar
  (green/amber/red), severity-tagged issue list, snapshot history table.
- **27 new tests** — `tests/test_data_health_m6.py`: CRUD 201/404/422, snapshot ingestion,
  all 10 issue type detections, critical/high severity assertions, health score floor at 0,
  score decrement for critical issues, audit event created on upload.
- **119 total passing tests**, clean TypeScript typecheck, clean production build.

### Verify with curl

```bash
# Create a dataset
curl -s -X POST http://localhost:8000/api/datasets \
  -H 'Content-Type: application/json' \
  -d '{
    "project_id": "<project_id>",
    "name": "AAPL Daily OHLCV",
    "dataset_type": "ohlcv",
    "source_type": "manual"
  }' | python3 -m json.tool

# Upload a snapshot with a bad row to trigger quality checks
curl -s -X POST http://localhost:8000/api/datasets/<dataset_id>/snapshots \
  -H 'Content-Type: application/json' \
  -d '{
    "version_label": "v2024-01",
    "rows": [
      {"symbol":"AAPL","timestamp":"2024-01-02","open":185.3,"high":188.5,"low":184.9,"close":187.1,"volume":52000000},
      {"symbol":"AAPL","timestamp":"2024-01-03","open":180.0,"high":175.0,"low":170.0,"close":173.0,"volume":48000000}
    ]
  }' | python3 -m json.tool

# List all datasets
curl http://localhost:8000/api/datasets
```

### Previously completed

- **M5: Strategy Run Comparison** — GET /api/strategies/{id}/runs/compare, pure-Python
  diff engine, RunComparisonPanel, 28 tests, 92 total tests.
- **M4: Strategy Run Logging** — POST /api/strategies/{id}/runs, RunLogDrawer, 64 tests.
- **M3: Strategy Creation + Strategy Lab** — POST /api/strategies, enriched list/detail,
  slugify util, quant terminal visual identity, 49 tests.
- **M2: Core Database Schema** — SQLAlchemy 2.x, Alembic, 7 ORM models, seed data, 5
  read-only endpoints, 30 tests.
- **M1: Project Foundation** — FastAPI backend, React+TS+Vite+Tailwind dark shell, 8
  placeholder pages, design tokens from UIDesignSystem.txt.

---

## Intentionally NOT built yet

The following are deferred to later milestones:

- Authentication / API keys (M-later)
- Extended alert rules with custom thresholds
- Live Drift / Execution Attribution
- Python SDK and ingestion endpoints
- Live market data providers (no external/paid data)
- AI diagnostic layer (bounded to deterministic evidence) — M16+
- Full overfit / parameter sensitivity engine (walk-forward, parameter sweeps)
- Regime analysis and market condition attribution
- PDF export, scheduled report delivery, AI-generated report text

No paid services, no live market data, and no broker/trading actions are part of this project.
