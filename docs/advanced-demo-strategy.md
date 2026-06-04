# Advanced Demo Strategy — US Equity Quality-Momentum Rotation (M78)

A single, realistic, **multi-version** demo strategy with a full historical
evidence trail, so you can click through every part of QuantFidelity and see it
working: strategy-detail tabs, action queue, lifecycle visual, evidence matrix,
backtests, reports, audits, alerts, review cases, regression tests, config
policies, SLA monitor, audit trail, run replay, drift, promotion gates, command
center, and dashboard/home.

> **Demo data only.** All numbers are deterministic synthetic values — **not real
> trading performance**. No AI, no external market data, no broker/trading
> execution.

---

## The strategy story

**US Equity Quality-Momentum Rotation** is a systematic long/flat US large-cap
rotation. It ranks a 20-symbol liquid universe (AAPL, MSFT, NVDA, … V) by
quality, 12-month momentum, and a volatility filter, rebalancing monthly.

It evolved through four versions. The point of the demo: **the highest Sharpe is
not the most reliable strategy.** v1 has the best headline numbers and the worst
trust; v3/v4 trade lower headline performance for far higher reliability.

| Version | Story | Sharpe | Ann. return | Vol | Max DD | Turnover | Trust |
|--------|-------|-------:|-----------:|----:|------:|--------:|------:|
| **v1 Research Prototype** | Same-close fill, **zero costs**, no guardrails, very high turnover | 1.80 | 16.0% | 12.0% | −18.0% | 8.5× | ~48 (weak) |
| **v2 Cost-Aware Backtest** | Realistic costs + next-bar-open fills; drawdown/turnover still high | 1.35 | 12.0% | 11.0% | −15.0% | 5.2× | ~69 (review) |
| **v3 Liquidity + Turnover Controls** | Liquidity filter, sector cap, turnover target | 1.25 | 10.5% | 9.5% | −10.0% | 2.4× | ~83 (good) |
| **v4 Paper Candidate** | Refined; high coverage and trust, low turnover | 1.18 | 9.8% | 9.0% | −8.5% | 1.9× | ~86 (good) |

### Why v4 is more reliable than v1 despite a lower Sharpe
- **v1** earns its 1.8 Sharpe on a same-close fill model and **zero transaction
  costs** — assumptions that vanish in live trading. Its config policy fails, its
  backtest-audit trust is low, and it raises high-severity alerts.
- **v4** assumes realistic costs and slippage, next-bar-open fills, a max position
  weight, a liquidity filter, a sector cap, and a turnover target. Its Sharpe is
  lower (1.18) but the result is **trustworthy**: high evidence coverage, strong
  audit trust, low turnover, and a passing config policy.

QuantFidelity exists to make that difference visible.

---

## What gets created

Roughly **30 core artifacts** (plus governance + timeline) for the one strategy:

| Artifact | Count |
|----------|------:|
| Strategy versions (v1–v4) | 4 |
| Config snapshots (weak → strong) | 4 |
| Universe snapshots | 4 |
| Signal snapshots (`quality_momentum_score`) | 4 |
| Dataset snapshots (OHLCV, health improving) | 4 |
| Strategy runs (1 research, 4 backtest, 1 paper, 1 live-like) | 7 |
| Backtest audits | 5 |
| Reliability scores (progression + current) | 5 |
| Reports (Initial Research / Cost Model / Regression Improvement / Paper Candidate Readiness) | 4 |
| Alerts (7 resolved + 3 open) | 10 |
| Research review cases (1 resolved, 1 acknowledged, 1 open) | 3 |
| Regression test suite + run, config policy + evaluations, evidence SLA + evaluation | ✓ (best-effort) |
| Audit-timeline events across the full story | many |

The latest run is a **live-like / shadow** run, so the lifecycle visual shows the
strategy at the **Shadow** stage, **blocked from Production Candidate** — close
but not production-clean (the paper run is new and the SLA/report need review).

---

## How to run it

### Option A — Admin → Demo Controls (recommended)
1. Sign in as an **owner/admin** account (an account with `can_seed_demo`).
2. Go to **Admin → Demo Controls**.
3. Find the **Advanced Strategy Demo** card and click **Seed Advanced Strategy**.
4. The result shows the strategy name, id, artifact counts, and an **Open
   Strategy →** link.

### Option B — Authenticated API
```bash
curl -s -X POST https://quantfidelity-api.onrender.com/api/admin/demo/advanced-strategy \
  -H "Authorization: Bearer <OWNER_OR_ADMIN_TOKEN>"
```
(Locally, the same endpoint at `http://localhost:8000`. With no auth token in local
dev, the request is treated as a permissive pseudo-owner.)

### Option C — CLI script (local or Render shell)
```bash
cd backend
python3 scripts/seed_advanced_demo_strategy.py
```
Runs against whatever `DATABASE_URL` points to (local SQLite or Render Postgres).

### Option D — Single-slice evidence bundle (Developer → Evidence Bundles)
For demonstrating the **upload flow** itself, an exportable bundle is provided at
[`docs/samples/advanced-demo-strategy-bundle.json`](samples/advanced-demo-strategy-bundle.json).
It is the **v4 Paper Candidate slice** (version, config, universe, signal,
dataset + snapshot, run) and, on ingest, runs a backtest audit + reliability
score. Open **Developer → Evidence Bundles**, select a strategy, paste or upload
the file, and ingest. This attaches one realistic evidence chain to an existing
strategy — it does **not** create the multi-version story.

> The admin seed (Options A–C) remains the **recommended** path: it creates the
> full strategy with all four versions, seven runs, audits, reports, alerts, and
> review cases. The bundle is a lightweight way to show the manual/SDK upload
> path. (`generate_strategy_report` / `generate_alerts` and `idempotency_key` are
> intentionally omitted from the sample so it ingests cleanly on both local SQLite
> and deployed Postgres; generate the report afterward with **Generate Report**.)

**Idempotency:** every path is safe to run repeatedly — it reuses existing
artifacts (deduped by natural keys) and **never duplicates the strategy**. The
response `status` is `created` on first run and `refreshed` thereafter.

---

## What to click during the demo

1. **Home / Dashboard** — the new strategy appears in the workspace snapshot and
   recommended actions.
2. **Strategies → US Equity Quality-Momentum Rotation**.
3. **Overview tab** — the **Lifecycle** bar (Shadow stage, blocked from Production
   Candidate) and the **Action Queue** (resolve promotion blockers, link the
   latest run's evidence, refresh stale evidence).
4. **Evidence tab** — four versions' universe/signal/config snapshots.
5. **Runs tab** — 7 runs; open one to **Run Replay** and the **Backtest Audit**
   (note v1's low trust vs v4's high trust); **Shadow Monitor** compares the
   live-like run to the backtest; **Drift** compares runs.
6. **Governance tab** — Promotion Gates, Regression Tests, Config Policy
   Guardrails (v1 fails, v4 passes), Evidence SLA Monitor, Review Cases (one
   resolved, one acknowledged, one open).
7. **Exports tab** — four historical reports showing the v1 → v4 progression.
8. **Lineage / Audit Trail** — the timeline of the whole story.
9. **Command Center** — pick the strategy to see its lifecycle + action queue.

### What to observe
- v1 has the **best Sharpe and the worst trust**; v3/v4 have lower Sharpe and
  **much higher trust**.
- Old high-severity alerts (same-close fill, missing costs, high turnover) are
  **resolved**; current medium/low alerts (stale report, new paper run, SLA
  review) are **open**.
- The strategy is **advanced but not production-clean** — the lifecycle and action
  queue make the remaining work explicit.

---

## Notes
- Frontend: <https://quantfidelity.vercel.app> · Backend:
  <https://quantfidelity-api.onrender.com>.
- The seed does **not** touch the clean realistic demo seed — it adds one extra
  strategy to the same default workspace/project.
- Permission: seeding requires `can_seed_demo` (owner/admin). Viewers receive a
  role-aware access message.
