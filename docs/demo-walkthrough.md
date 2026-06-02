# QuantFidelity Demo Walkthrough

This guide walks through the full QuantFidelity demo experience using the three
pre-seeded strategies: AAPL Mean Reversion (healthy), FX Carry Strategy (review),
and Crypto Momentum (under-instrumented).

---

## Prerequisites

Backend running:
```
cd backend && uvicorn app.main:app --reload
```

Frontend running:
```
cd frontend && npm run dev
```

The frontend defaults to `http://localhost:5173` and the backend to `http://localhost:8000`.

---

## Step 1: Seed Demo Data

**Option A — Admin UI**

1. Open `http://localhost:5173/admin/system-health`
2. Scroll to the **Demo Mode** section
3. Click **Seed / Extend Demo Data**
4. Watch the result panel — it shows created counts, reused counts, and generated artifacts

**Option B — API directly**

```bash
curl -X POST http://localhost:8000/api/admin/seed-demo \
  -H "Content-Type: application/json" \
  -d '{}'
```

**Option C — Makefile target (if added)**

```bash
make demo-seed
```

The seed operation is idempotent. Running it multiple times with `mode: "extend"`
(the default) will reuse existing demo entities and only create what is missing.

---

## Step 2: Dashboard

Open `http://localhost:5173`

The dashboard shows:
- Total strategy count and health summary
- Portfolio overview with reliability scores
- Recent timeline activity
- Open alerts count

With demo data seeded you should see 3 strategies and at least 1 open alert.

---

## Step 3: Portfolio Overview

Open `http://localhost:5173/portfolio`

The portfolio page shows all three demo strategies side by side:
- Health status chips (healthy / review / insufficient evidence)
- Reliability scores with trend indicators
- Evidence coverage scores
- Open alert counts per strategy

Use this page to get a quick at-a-glance comparison before drilling into individual
strategies.

---

## Step 4: Strategy Detail — AAPL Mean Reversion (Healthy)

Navigate to the AAPL Mean Reversion strategy from the Strategies list or Portfolio page.

What to observe:
- Health status: **healthy**, high reliability score
- Multiple completed backtest audits with good trust scores
- Active timeline with frequent evidence events
- Assumption health: all categories green or watch
- No open alerts
- Config snapshots showing disciplined parameter management
- Evidence coverage score in the high range

This strategy serves as the benchmark for a well-instrumented, production-ready quant strategy.

---

## Step 5: Strategy Detail — FX Carry Strategy (Review)

Navigate to the FX Carry Strategy.

What to observe:
- Health status: **review**
- Open alerts flagging fill realism issues and cost sensitivity
- Backtest audit with elevated cost fragility level
- Assumption health showing fill realism and cost sensitivity categories in review
- Config diff showing recent parameter changes that weakened assumptions
- Evidence coverage score in the mid range
- Suggested checks in the assumption health panel

This strategy demonstrates a common real-world scenario: a strategy that has been
live long enough to accumulate evidence but now has drift in its key assumptions.

---

## Step 6: Crypto Momentum (Under-Instrumented)

Navigate to the Crypto Momentum strategy.

What to observe:
- Health status: **insufficient_evidence** or **watch**
- Low reliability score due to limited evidence
- Sparse timeline — few events logged
- Assumption health: most categories in insufficient_evidence state
- No completed backtest audits or only one
- Evidence coverage score in the low range
- Many suggested checks pointing to missing evidence types

This strategy demonstrates what the system looks like when a strategy is new or
when a team has not yet established evidence-logging discipline. The system surfaces
exactly what evidence is missing.

---

## Step 7: Evidence Coverage Matrix

Open `http://localhost:5173/evidence/coverage`

The coverage matrix shows all three demo strategies as columns against evidence
categories as rows. At a glance you can see:
- AAPL has broad, deep coverage across all categories
- FX has partial coverage with gaps in cost and fill categories
- Crypto has thin coverage across most categories

Use the filter controls to narrow by evidence category or strategy status.

---

## Step 8: Alerts Page

Open `http://localhost:5173/alerts`

With demo data seeded you should see alerts for the FX and Crypto strategies.
Typical demo alerts include:
- Fill realism concern on FX Carry
- Cost sensitivity warning on FX Carry
- Stale evidence alert on Crypto Momentum

Click into an alert to see the detail, linked strategy, and suggested resolution steps.

---

## Step 9: Comparison Report

Open `http://localhost:5173/strategies/compare`

1. Select **AAPL Mean Reversion** and **FX Carry Strategy** from the strategy picker
2. Click **Generate Comparison Report**
3. Review the generated report sections:
   - Side-by-side reliability scores and health status
   - Assumption gap analysis
   - Evidence coverage differential
   - Suggested review agenda items

The comparison report is deterministic — re-generating with the same strategy IDs
produces the same output.

---

## Step 10: Strategy Export

Navigate to the AAPL Mean Reversion strategy detail page.

1. Find the **Export** section or button
2. Generate a JSON export — includes all strategy metadata, runs, config snapshots, and reliability scores
3. Generate a Markdown export — formatted summary suitable for sharing with stakeholders

Exports are point-in-time snapshots. They do not include live backend data after the export is generated.

---

## Reset Demo Data

**Option A — Admin UI**

1. Open `http://localhost:5173/admin/system-health`
2. Scroll to **Demo Mode**
3. Check the confirmation checkbox: "I understand this only resets demo data"
4. Click **Reset Demo Data**

**Option B — API directly**

```bash
curl -X POST http://localhost:8000/api/admin/seed-demo \
  -H "Content-Type: application/json" \
  -d '{"mode": "reset_demo_only", "confirm_reset": true}'
```

After reset, you can re-seed at any time to get a fresh copy of the demo data.

---

## Safety Notes

- `reset_demo_only` mode only deletes the **QuantFidelity Demo Org** and all entities
  owned by that organization. No other organizations or their data are touched.
- Non-demo organizations are never deleted or modified by any seed or reset operation.
- All demo data is deterministic — re-seeding always produces the same strategies,
  runs, config snapshots, and evidence structure.
- The `confirm_reset: true` flag is required for reset operations as an intentional
  safety gate to prevent accidental data loss.
- Demo seed operations are safe to run in development and staging environments.
  Do not run against a production database with real user data.
