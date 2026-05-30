# M1 — Project Foundation (engineering notes)

Scope: clean, extensible full-stack foundation only. No product modules.

## Decisions

- **Backend**: FastAPI with an app-factory (`create_app`) so later milestones can build
  test/prod variants. Config via `pydantic-settings`, all env vars prefixed `QF_`. CORS limited
  to the local frontend origins. Routes split into `routes/health.py` (`/health`) and
  `routes/meta.py` (`/api`), aggregated in `api/router.py`.
- **DB**: deliberately not wired. `QF_DATABASE_URL` exists in config and `.env.example` so the
  PostgreSQL path is reserved without adding an engine/session/models yet.
- **Frontend**: React + TS + Vite + Tailwind. Routing via `react-router-dom`. Design tokens
  (colors, fonts, radii) in `tailwind.config.js` mirror `UIDesignSystem.txt`. The top bar pings
  `GET /api` to show a live backend status indicator.
- **Placeholders**: pages render honest empty states ("No data yet", em-dash scores) rather
  than fabricated product data.

## Validation performed

- `pytest` — 2 passed (health + api root).
- Backend boots under uvicorn; `/health` and `/api` return expected JSON.
- `npm run typecheck` — clean.
- `npm run build` — succeeds.

## Reserved for later milestones

models/, services/, db/ packages are present but empty (docstring only). Strategy lineage, data
integrity, backtest checks, live drift, SDK, providers, AI, and alerts are all out of scope here.
