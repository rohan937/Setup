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
├── backend/            FastAPI service (Python)
│   ├── app/
│   │   ├── main.py     App entrypoint + CORS + router wiring
│   │   ├── core/       Config (env-driven settings)
│   │   ├── api/        Routers (health, meta)
│   │   ├── models/     SQLAlchemy models (later milestones)
│   │   ├── schemas/    Pydantic response models
│   │   ├── services/   Domain services (later milestones)
│   │   └── db/         Database layer (later milestones)
│   └── tests/          Pytest smoke tests
├── frontend/           React + TypeScript + Vite + Tailwind
│   └── src/
│       ├── components/ App shell, sidebar, topbar, cards
│       ├── pages/      Dashboard + placeholder pages
│       ├── lib/        API client, nav config
│       ├── types/      Shared TS types
│       └── styles/     Tailwind entry + base styles
├── docs/               Engineering notes
└── *.txt               Product planning documents
```

---

## Prerequisites

- Python 3.11+ (developed against 3.13)
- Node.js 20+ (developed against 24) and npm

---

## Backend — local setup & run

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # optional; defaults work for local dev

# Run the API (http://localhost:8000)
uvicorn app.main:app --reload
```

Endpoints:

- `GET /health` — liveness probe
- `GET /api` — service metadata
- `GET /docs` — interactive OpenAPI docs

Run tests:

```bash
cd backend
./.venv/bin/pytest        # or: pytest, with the venv activated
```

---

## Frontend — local setup & run

```bash
cd frontend
npm install
cp .env.example .env          # optional; defaults to http://localhost:8000

# Dev server (http://localhost:5173)
npm run dev
```

Other scripts:

```bash
npm run typecheck   # TypeScript project check
npm run build       # production build
npm run preview     # preview the production build
```

The top bar shows a live **Backend online / offline** indicator by calling `GET /api`, so run
the backend alongside the frontend to see it connected.

---

## Current milestone — M1: Project Foundation

**Status: complete.** M1 delivers a clean, extensible full-stack foundation only.

Included:

- FastAPI backend: env-driven config, CORS for the local frontend, `/health` and `/api`
  endpoints, structured package layout, and smoke tests.
- React + TypeScript + Vite + Tailwind frontend: dark institutional shell (sidebar + top bar),
  routed placeholder pages (Dashboard, Strategies, Timeline, Data Health, Backtests, Live Drift,
  Alerts, Settings), and design tokens from `UIDesignSystem.txt`.
- `.env.example` files, `.gitignore`, and this README.

## Intentionally NOT built yet

The following are deferred to later milestones and are **not** present in M1:

- Database engine, models, migrations (config is PostgreSQL-ready; nothing is wired).
- Authentication / API keys.
- Strategy Lineage, Data Integrity, Backtest Reality Check, Live Drift / Execution Attribution.
- Python SDK and ingestion endpoints.
- Live market data providers (no external/paid data sources).
- AI diagnostic layer.
- Alerts, reports, and audit trail logic.

No paid services, no live market data, and no broker/trading actions are part of this project.
