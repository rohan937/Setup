# QuantFidelity Demo Walkthrough

> **For product demonstrations, investor walkthroughs, and QA sessions.**
> This guide assumes you have run the "Reset Clean Realistic Demo" seed.
>
> QuantFidelity is a deterministic strategy **reliability / governance** product.
> Everything below describes evidence, instrumentation, and lifecycle readiness —
> never trading advice, never a recommendation to buy or sell.

---

## 0. Guided Demo Walkthrough (M76)

There is now an **in-app Guided Demo Walkthrough** that drives a presenter (or a
new user) through the demo in six steps. It overlays the real product — each step
explains the current view, lists what to look for, and gives a "Go there" button
that navigates straight to the right page or strategy.

**How to start it:**
- From the **Dashboard**, click the **"Start guided demo"** card, **or**
- Go to **Admin → Demo Controls → "Start Demo Walkthrough"**.

**How to restart it:**
- **Admin → Demo Controls → "Restart Demo Walkthrough"**, **or**
- The Dashboard card (which offers Restart once the walkthrough has been started or completed).

**Behavior:**
- It is **dismissible** and **non-blocking** — you can close it at any time and keep
  clicking around the product normally; reopen it to resume.
- Progress (last step, dismissed, completed) is stored in **localStorage**
  (`qf_demo_walkthrough_v1`), so it survives refreshes on the same browser.
  Restart clears that state.
- If the demo strategies are missing, the walkthrough shows
  **"Run Clean Realistic Demo first."**, linking to **Admin → Demo Controls**.

The six in-app steps map exactly to the [5-minute walkthrough script](#9-5-minute-walkthrough-script-matches-the-in-app-steps) below:
Dashboard → Portfolio → AAPL → FX Carry → Crypto → KO/PEP.

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

## 5. The improving strategy — KO/PEP Pairs Trade (Maya Test)

### 🟠 KO/PEP Pairs Trade (Maya Test) — *Improving, but not promotion-clean*

**Story:** A Coke/Pepsi pairs-trade strategy that has clearly **gotten better** —
v2 improved its trust score, reduced turnover, and raised its reliability versus v1.
But "improved" is **not** the same as "ready to progress." It still has open
governance work: evidence linkage is incomplete and key assumptions haven't been
reviewed. This is the canonical example of the difference between a strategy that
has **improved** and one that is **clean enough to advance a lifecycle stage**.

| Item | Value |
|------|-------|
| v2 vs v1 | improved trust, lower turnover, higher reliability |
| Current lifecycle stage | **Backtest** |
| Next stage | **Backtest Review** |
| Blockers | assumption review pending, missing evidence links, no paper run |

**What to show:**
- Strategy Detail → v2 metrics improved over v1, but lifecycle still at Backtest
- Lifecycle bar → next stage is **Backtest Review**, not yet reached
- Blockers / readiness → assumption review and evidence-link gaps remain
- **Action Queue** → concrete next steps: fix evidence links, review assumptions
- Talking point: improvement is necessary but **not sufficient** to progress —
  QuantFidelity gates on evidence and governance, not just better numbers.

---

## 6. Page-by-page walkthrough

### Dashboard
- Total strategies: **3** · Total runs: **6**
- Open alerts: **~11**
- Recent runs visible with evidence status
- "Start guided demo" card (M76) to launch or restart the in-app walkthrough

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

## 7. Expected dashboard numbers at a glance

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

> Note: the KO/PEP (Maya Test) strategy may be seeded separately from the three
> core demo strategies; when present it appears as an additional Portfolio row and
> is the target of step 6 in the guided walkthrough.

---

## 8. Re-seeding / idempotency

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

## 9. 5-minute walkthrough script (matches the in-app steps)

These six steps match the in-app Guided Demo Walkthrough (M76) exactly. Keep the
language reliability/governance-focused. Never give trading advice. Never say "AI."

### Step 1 — Start at the Dashboard
- **Click:** "Open Dashboard" (or just land on `/`).
- **Say:** "This is the workspace health view for the whole research portfolio —
  strategy counts, reliability, open alerts, and the top actions that need attention first."
- **Look for:** Total strategies and total runs; open alerts and reliability pillars;
  the **Top Priority Actions** card.

### Step 2 — Compare strategies in Portfolio
- **Click:** "Open Portfolio".
- **Say:** "The Portfolio answers one question — which strategies are ready, which
  need review, and which are unsafe to progress. Each row shows health and lifecycle stage."
- **Look for:** AAPL healthy and well-instrumented; FX Carry in review with stale
  evidence; Crypto Momentum blocked and under-instrumented.

### Step 3 — Open the healthy example: AAPL Mean Reversion
- **Click:** "Open AAPL Mean Reversion".
- **Say:** "AAPL is the mature, well-instrumented strategy — this is what good
  evidence and full instrumentation look like."
- **Look for:** High evidence coverage and high trust; low or no open alerts;
  the lifecycle bar advanced furthest.

### Step 4 — Open the review example: FX Carry Strategy
- **Click:** "Open FX Carry Strategy".
- **Say:** "FX Carry has decent research but its evidence is going stale — this shows
  how QuantFidelity catches maintenance problems before they become risk."
- **Look for:** Evidence freshness / SLA warnings; an open review case;
  lifecycle blocked on evidence freshness.

### Step 5 — Open the blocked example: Crypto Momentum
- **Click:** "Open Crypto Momentum".
- **Say:** "Crypto Momentum has an attractive headline Sharpe, but weak assumptions
  and thin evidence — this is why we don't trust a Sharpe number on its own."
- **Look for:** Config policy failures (zero costs, same-close fill); a low trust
  score despite the high Sharpe; lifecycle blocked by assumptions / governance.

### Step 6 — Open the improving example: KO/PEP Pairs Trade (Maya)
- **Click:** "Open KO/PEP Pairs Trade".
- **Say:** "KO/PEP v2 genuinely improved — better trust, lower turnover, higher
  reliability — but it still isn't clean enough to advance. Improvement is necessary,
  not sufficient: it still needs assumption review and evidence linkage."
- **Look for:** Current lifecycle stage **Backtest**, next **Backtest Review**;
  blockers for assumption review, missing evidence links, and no paper run; use the
  **Action Queue** to fix evidence links and review assumptions.

---

## 10. Security / demo notes

- Demo data is self-contained in the local SQLite database (`backend/quantfidelity.db`).
- `workspace_members` and `auth_users` are preserved across clean resets.
- No real market data, no external APIs, no secrets used.
- Guided walkthrough progress lives only in browser localStorage (`qf_demo_walkthrough_v1`).
- Evidence-based descriptions only — not investment advice.

---

*Updated for M76 Guided Demo Walkthrough. Workspace: Alpha Reliability Lab.*
