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
│   │   ├── models/         SQLAlchemy ORM models (16 tables)
│   │   ├── schemas/        Pydantic response models
│   │   ├── services/       Domain services (seed, run_comparison, data_quality, alerts, dataset_comparison, reports)
│   │   └── db/             SQLAlchemy engine, session, declarative base
│   └── tests/              Pytest tests (430 tests)
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

## Current milestone — M14: Reliability Reports v1

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
- AI diagnostic layer (bounded to deterministic evidence) — M15+
- Full overfit / parameter sensitivity engine (walk-forward, parameter sweeps)
- Regime analysis and market condition attribution
- PDF export, scheduled report delivery, AI-generated report text

No paid services, no live market data, and no broker/trading actions are part of this project.
