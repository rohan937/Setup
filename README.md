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
```

Interactive OpenAPI docs: `http://localhost:8000/docs`

### Run tests

```bash
cd backend
./.venv/bin/pytest -v
# 30 tests: schema, seed, idempotency, all endpoints, JSON round-trip
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

## Current milestone — M3: Strategy Creation + Strategy List

**Status: complete.**

### M3 deliverables

- **POST /api/strategies** — create a strategy with name, description, asset class, status,
  and auto-generated slug; validates against `AssetClass`/`StrategyStatus` constants; 409 on
  duplicate slug within a project; logs an `AuditTimelineEvent` on create.
- **Enriched GET /api/strategies** — returns `StrategyListItemOut` with `project_name`,
  `run_count`, and `latest_run_at` aggregated via bulk SQL queries (no N+1).
- **Enriched GET /api/strategies/{id}** — returns `StrategyDetailOut` with all the above
  plus `versions` and `runs` lists (eager-loaded via `selectinload`).
- **`app/core/utils.py`** — `slugify()` utility: lowercase, strip special chars, collapse
  whitespace/hyphens, truncate to 100 chars.
- **Frontend Strategies page** — full rewrite with real API data; loading, error, and empty
  states; sortable table with name, project, asset class badge, status badge, run count,
  last run date; "New Strategy" button.
- **StrategyCreateDrawer** — slide-over form with project selector, name, optional slug,
  description, asset class, and status; submits to POST /api/strategies; refreshes list on
  success.
- **StrategyDetail page** — `/strategies/:id` route; shows header with badges, stat row,
  versions card, runs card with metric pills.
- **Dashboard update** — Strategies section shows real data (mini-table, "View all" link).
- **Badge component** — colored chip for status, asset_class, run_type, run_status variants.
- **19 new tests** — `tests/test_strategies_m3.py`: create success, slug generation,
  duplicate 409, missing project 404, invalid asset_class/status 422, enriched list fields,
  detail fields, 404 on unknown ID.
- **49 total passing tests**, clean TypeScript typecheck, clean production build.

### Previously completed

- **M2: Core Database Schema** — SQLAlchemy 2.x, Alembic, 7 ORM models, seed data, 5
  read-only endpoints, 30 tests.
- **M1: Project Foundation** — FastAPI backend, React+TS+Vite+Tailwind dark shell, 8
  placeholder pages, design tokens from UIDesignSystem.txt.

---

## Intentionally NOT built yet

The following are deferred to later milestones:

- Authentication / API keys (M-later)
- Strategy Lineage (run comparison, version diffing) — M4
- Data Integrity Engine — M5
- Backtest Reality Check — M6
- Live Drift / Execution Attribution — M7
- Python SDK and ingestion endpoints — M8
- Live market data providers (no external/paid data) — M9
- AI diagnostic layer — M10
- Alerts, reports, and audit trail logic — M11

No paid services, no live market data, and no broker/trading actions are part of this project.
