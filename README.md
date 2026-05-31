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
│   │   ├── api/            Routers: health, meta, projects, strategies, timeline, datasets
│   │   ├── models/         SQLAlchemy ORM models (10 tables)
│   │   ├── schemas/        Pydantic response models
│   │   ├── services/       Domain services (seed, run_comparison, data_quality)
│   │   └── db/             SQLAlchemy engine, session, declarative base
│   └── tests/              Pytest tests (133 tests)
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

## Current milestone — M8: Backtest Reality Check v1

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
- Backtest Reality Check (Trust Score) — M8
- Live Drift / Execution Attribution — M8
- Python SDK and ingestion endpoints — M9
- Live market data providers (no external/paid data) — M10
- AI diagnostic layer (bounded to deterministic evidence) — M11
- Alerts, reports, and audit trail logic — M12

No paid services, no live market data, and no broker/trading actions are part of this project.
