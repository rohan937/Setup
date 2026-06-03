# QuantFidelity Demo Walkthrough

> **For product demonstrations, investor walkthroughs, and QA sessions.**
> This guide assumes you have run the "Reset Clean Realistic Demo" seed.

---

## 1. Seed the clean demo

```bash
# Option A: via curl (no auth required in local dev)
curl -s -X POST http://localhost:8000/api/admin/seed-demo \
  -H "Content-Type: application/json" \
  -d '{
    "mode": "clean_realistic_demo",
    "confirm_reset": true,
    "include_reports": false,
    "include_alerts": true,
    "include_backtest_audits": true
  }' | python3 -m json.tool

# Option B: via the UI
# Navigate to Admin → Demo Controls → "Reset Clean Realistic Demo"
# Check the confirmation box and click the button.
```

**Expected response:**
```json
{
  "mode": "clean_realistic_demo",
  "summary": "Clean realistic demo seeded: Alpha Reliability Lab / Strategy Reliability Demo Portfolio. 3 strategies, 28 artifacts. ...",
  "strategy_ids": ["<uuid>", "<uuid>", "<uuid>"]
}
```

---

## 2. Register / log in

If this is a fresh local environment:

```bash
# Register the first user (becomes workspace owner automatically)
curl -s -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "demo@example.com", "display_name": "Demo User", "password": "demopass123"}' \
  | python3 -m json.tool
```

Or use the UI: click **Login / Register** in the top bar.

---

## 3. Demo workspace overview

| Item | Value |
|------|-------|
| Workspace | Alpha Reliability Lab |
| Project | Strategy Reliability Demo Portfolio |
| Strategies | 3 |
| Strategy runs | 6 |
| Backtest audits | 5 |
| Alerts | ~11 |
| Review cases | 2 |

---

## 4. The three demo strategies

### 🟢 AAPL Mean Reversion v1 — *Healthy / Well-instrumented*

**Story:** A disciplined equity mean-reversion strategy. Every evidence layer is
present: config snapshot with realistic assumptions, clean OHLCV dataset, z-score
signal snapshot, universe snapshot, research + two backtest runs. Backtest audits
show realistic costs. Reliability score is high.

| Metric | Value |
|--------|-------|
| Sharpe | ~1.43–1.52 |
| Annual return | ~16–18% |
| Max drawdown | ~-10% |
| Turnover | ~1.7× |
| Trust score | high (pass) |

**What to show:**
- Strategy Detail page → all evidence layers filled
- Command Center → healthy status
- Backtest Audits → low issue count, realistic cost model
- Promotion Gates → mostly green
- Evidence Matrix → complete coverage

---

### 🟡 FX Carry Strategy Q1 — *Review / Stale evidence*

**Story:** An FX carry strategy with decent headline metrics but evidence that
is aging. The signal snapshot is 30+ days old (deliberate stale date). One run
has no dataset link. Two backtest runs show deteriorating trust. Two alerts are
open. One review case is open: "FX Carry Evidence Freshness Review."

| Metric | Value |
|--------|-------|
| Sharpe | ~0.91 (run 1), ~0.73 (run 2) |
| Annual return | ~9% → ~7% (deteriorating) |
| Max drawdown | ~-16% → -18% |
| Trust score | 63 → 56 (declining) |

**What to show:**
- Alerts page → 2–3 alerts for FX Carry
- Review Cases → "FX Carry Evidence Freshness Review" open
- Evidence Freshness → signal snapshot marked aging/stale
- Command Center → review status
- SLA Monitor → one or two SLA violations
- Promotion Gates → blocked or requires review

---

### 🔴 Crypto Momentum Intraday — *Weak / Under-instrumented*

**Story:** A crypto momentum strategy with inflated headline Sharpe (~2.84) from
unrealistic assumptions: zero transaction costs, same-close fill model, 3× leverage,
very high turnover (15×). Signal evidence is sparse (3 rows, 1 missing value).
Dataset has a suspicious price spike. Backtest audit trust is weak.
Multiple high alerts and an open review case.

| Metric | Value |
|--------|-------|
| Sharpe | ~2.84 (misleading) |
| Annual return | ~52% (from unrealistic costs) |
| Transaction cost | 0 bps |
| Fill model | same_close |
| Trust score | weak |

**What to show:**
- Backtest Audit → critical issues: zero costs, same-close fill, high turnover
- Alerts → high/critical severity alerts
- Review Cases → "Crypto Momentum Backtest Reliability Degradation" open, high severity
- Config Policy → fail (missing cost assumptions)
- Robustness Score → fragile
- Command Center → blocked

---

## 5. Page-by-page walkthrough

### Dashboard
- Total strategies: **3** · Total runs: **6**
- Open alerts: **~11**
- Recent runs visible with evidence status

### Portfolio
- AAPL = healthy bar color
- FX Carry = amber / review
- Crypto = red / blocked

### Strategies
- List view: 3 strategies with health status badges
- Click AAPL → full evidence chain visible
- Click FX Carry → stale signal warning visible
- Click Crypto → sparse evidence warning, inflated Sharpe

### Backtests
- AAPL audits: 2 audits, high trust
- FX Carry audits: 2 audits, moderate trust (~56–63)
- Crypto audit: 1 audit, weak trust

### Alerts
- ~11 alerts: backtest trust, evidence quality, missing evidence
- FX Carry and Crypto have the most alerts

### Review Cases (Governance → Review Cases)
- FX Carry: evidence freshness (medium severity, open)
- Crypto: backtest reliability degradation (high severity, open)

### Command Center
- AAPL: green / clear
- FX Carry: amber / review
- Crypto: red / blocked

---

## 6. Expected dashboard numbers at a glance

After clean realistic demo seed:

| Page | Expected |
|------|---------|
| Dashboard — total strategies | 3 |
| Dashboard — total runs | 6 |
| Dashboard — open alerts | ~11 |
| Strategies list | 3 rows |
| Backtest audits | 5 |
| Reliability scores | 3 |
| Review cases | 2 open |
| Signal snapshots | 3 |
| Universe snapshots | 3 |
| Config snapshots | 4 |
| Dataset snapshots | 3 |

---

## 7. Re-seeding / idempotency

Running the seed again in `extend` mode won't duplicate data:

```bash
curl -s -X POST http://localhost:8000/api/admin/seed-demo \
  -H "Content-Type: application/json" \
  -d '{"mode": "extend", "include_alerts": true, "include_backtest_audits": true}'
```

To fully reset and start fresh:

```bash
curl -s -X POST http://localhost:8000/api/admin/seed-demo \
  -H "Content-Type: application/json" \
  -d '{"mode": "clean_realistic_demo", "confirm_reset": true, "include_alerts": true, "include_backtest_audits": true}'
```

---

## 8. Security / demo notes

- Demo data is self-contained in the local SQLite database (`backend/quantfidelity.db`).
- `workspace_members` and `auth_users` are preserved across clean resets.
- No real market data, no external APIs, no secrets used.
- Evidence-based descriptions only — not investment advice.

---

*Updated by demo data cleanup. Workspace: Alpha Reliability Lab.*
