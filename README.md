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

## Current milestone — M5: Strategy Run Comparison + Deterministic Diffing

**Status: complete.**

### M5 deliverables

- **`GET /api/strategies/{strategy_id}/runs/compare?run_a_id=…&run_b_id=…`** — pure
  read-only deterministic diff of two runs from the same strategy. Validates strategy
  exists, both runs exist, both belong to the same strategy. Returns a structured JSON
  response with per-section diffs (params, assumptions, metrics, metadata), numeric deltas
  and percent deltas for recognised numeric fields, highlighted natural-language change
  sentences, and a hedged plain-language explanation. Does NOT create an audit timeline
  event. Returns 404/400/422 for all error cases.
- **`app/services/run_comparison.py`** — pure Python comparison engine; no database
  access, no AI. Compares `params_json`, `assumptions_json`, `metrics_json` key-by-key;
  compares scalar metadata fields (run_type, status, universe_name, dataset_version,
  strategy_version_id). Recognises 14 important metrics and 10 important params for
  highlighted changes. Language is strictly hedged: "changed alongside", "noted as
  observed" — never "caused".
- **`app/schemas/comparison.py`** — `FieldChange`, `ComparisonSection`,
  `RunComparisonResponse` Pydantic schemas.
- **`RunComparisonPanel` component** — quant terminal UI on StrategyDetail; selects Run A
  (baseline) and Run B (compare), defaults to the two most recent runs; one-click compare;
  shows explanation box, key-changes list, and per-section diff tables with directional
  delta coloring (green/red). Empty state when fewer than two runs exist.
- **28 new tests** — `tests/test_comparison_m5.py`: endpoint 200, response structure,
  404/400/422 error cases, same-run returns no changes, params/assumptions/metrics diffs,
  numeric delta values, non-numeric fields handled safely, highlighted changes for
  important fields, causal language check, no audit event created, total_changes
  reconciliation, unchanged_count correctness, type-mismatch warning.
- **92 total passing tests**, clean TypeScript typecheck, clean production build.

### Previously completed

- **M4: Strategy Run Logging** — POST /api/strategies/{id}/runs, RunLogDrawer, 64 tests.
- **M3: Strategy Creation + Strategy Lab** — POST /api/strategies, enriched list/detail,
  slugify util, quant terminal visual identity, 49 tests.
- **M2: Core Database Schema** — SQLAlchemy 2.x, Alembic, 7 ORM models, seed data, 5
  read-only endpoints, 30 tests.
- **M1: Project Foundation** — FastAPI backend, React+TS+Vite+Tailwind dark shell, 8
  placeholder pages, design tokens from UIDesignSystem.txt.

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
- Data Integrity Engine — M6
- Backtest Reality Check (Trust Score) — M7
- Live Drift / Execution Attribution — M8
- Python SDK and ingestion endpoints — M9
- Live market data providers (no external/paid data) — M10
- AI diagnostic layer (bounded to deterministic evidence) — M11
- Alerts, reports, and audit trail logic — M12

No paid services, no live market data, and no broker/trading actions are part of this project.
