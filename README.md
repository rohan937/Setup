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
│   │   ├── api/            Routers: health, meta, projects, strategies, timeline
│   │   ├── models/         SQLAlchemy ORM models (7 tables)
│   │   ├── schemas/        Pydantic response models
│   │   ├── services/       Domain services (seed, more in later milestones)
│   │   └── db/             SQLAlchemy engine, session, declarative base
│   └── tests/              Pytest tests (30 tests)
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
```

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

## Current milestone — M4: Strategy Run Logging

**Status: complete.**

### M4 deliverables

- **POST /api/strategies/{strategy_id}/runs** — log a strategy run with `run_name`,
  `run_type` (validated: research/backtest/paper/live), `status` (validated, default:
  completed), optional `started_at`/`completed_at`, `params_json`, `assumptions_json`,
  `metrics_json` (all must be JSON objects if provided), `universe_name`, `dataset_version`,
  `notes`; validates strategy exists; validates `strategy_version_id` belongs to same
  strategy when provided; auto-sets `completed_at = utcnow()` when status is completed and
  no value supplied; logs an `AuditTimelineEvent` with `event_type=strategy_run_logged`.
- **GET /api/strategies/{id}/runs** — updated to newest-first ordering.
- **GET /api/strategies/{id}** — runs list now newest-first.
- **`StrategyRunCreate` Pydantic schema** — validated input for run creation.
- **`RunLogDrawer` component** — slide-over form with run_name, run_type, status,
  universe/dataset fields, and JSON text areas (metrics, params, assumptions) with
  placeholder examples and client-side JSON object validation.
- **StrategyDetail page** — "Log Run" button in header; drawer opens, submits, refreshes
  detail page on success.
- **15 new tests** — `tests/test_strategies_m4.py`: create success, field values,
  completed_at auto-set, pending status no completed_at, invalid run_type/status 422,
  dict-only JSON fields, strategy not found 404, version not found 404, required field 422,
  run appears in list endpoint, newest-first ordering, run appears in detail.
- **64 total passing tests**, clean TypeScript typecheck, clean production build.

### Previously completed

- **M3: Strategy Creation + Strategy Lab** — POST /api/strategies, enriched list/detail,
  slugify util, Badge/StrategyCreateDrawer/Strategies/StrategyDetail pages, quant terminal
  visual identity, 49 tests.
- **M2: Core Database Schema** — SQLAlchemy 2.x, Alembic, 7 ORM models, seed data, 5
  read-only endpoints, 30 tests.
- **M1: Project Foundation** — FastAPI backend, React+TS+Vite+Tailwind dark shell, 8
  placeholder pages, design tokens from UIDesignSystem.txt.

---

## Intentionally NOT built yet

The following are deferred to later milestones:

- Authentication / API keys (M-later)
- Strategy Lineage (run comparison, version diffing) — M5
- Data Integrity Engine — M6
- Backtest Reality Check — M7
- Live Drift / Execution Attribution — M8
- Python SDK and ingestion endpoints — M9
- Live market data providers (no external/paid data) — M10
- AI diagnostic layer — M11
- Alerts, reports, and audit trail logic — M12

No paid services, no live market data, and no broker/trading actions are part of this project.
