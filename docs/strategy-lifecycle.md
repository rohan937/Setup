# Strategy Lifecycle (M76)

The Strategy Lifecycle is a read-only, **deterministic** visual that shows where a
strategy sits along QuantFidelity's research-progression path and exactly what is
keeping it from advancing to the next stage. It infers a strategy's stage purely
from existing research evidence — its runs, its readiness verdict, its promotion
gates, and the M74 action queue — and surfaces concrete repair actions. There is
**no AI** in the inference, no external data, and **no trading advice**: the
lifecycle stage describes the maturity of the *reliability evidence*, never a
recommendation to trade. As the response itself states:

> Lifecycle stage is inferred from research evidence. It is not a trading recommendation.

## Endpoint

```
GET /api/strategies/{id}/lifecycle
```

- **Read-only.** Computes and returns the lifecycle; it never mutates state.
- **404** when `{id}` does not match a known strategy (the service raises
  `ValueError("Strategy not found")`, which the route maps to a 404).

### Response shape

```jsonc
{
  "strategy_id": "…",
  "strategy_name": "KO/PEP Pairs Trade (Maya Test)",
  "generated_at": "2026-06-04T12:00:00Z",

  "stages": [                       // all 6 stages, each tagged with a state
    { "key": "research",        "label": "Research",        "index": 0, "state": "completed" },
    { "key": "backtest",        "label": "Backtest",        "index": 1, "state": "current"   },
    { "key": "backtest_review", "label": "Backtest Review", "index": 2, "state": "blocked"   },
    { "key": "paper_candidate", "label": "Paper Candidate", "index": 3, "state": "upcoming"  },
    { "key": "shadow",          "label": "Shadow",          "index": 4, "state": "upcoming"  },
    { "key": "production_candidate", "label": "Production Candidate", "index": 5, "state": "upcoming" }
  ],

  "current_stage": "backtest",            // inferred stage key
  "current_stage_label": "Backtest",
  "next_stage": "backtest_review",        // null if already at the final stage
  "next_stage_label": "Backtest Review",

  "blocked": true,                        // true when there are blockers AND a next stage exists
  "blocked_stage": "backtest_review",     // the stage being blocked (== next_stage when blocked)
  "blocked_stage_label": "Backtest Review",

  "blockers": [                           // derived from the M74 action queue
    {
      "reason": "Assumption health needs review",
      "detail": "Why this matters for reliability …",
      "severity": "high",
      "action_type": "navigate",
      "action_label": "Review assumptions",
      "target_tab": "governance",
      "related_run_id": null
    }
  ],

  "suggested_actions": ["Review assumptions", "Fix evidence links", "Upload paper run bundle"],
  "deterministic_summary": "KO/PEP Pairs Trade (Maya Test): currently at Backtest. next recommended stage is Backtest Review. blocked — assumption health needs review.",
  "disclaimer": "Lifecycle stage is inferred from research evidence. It is not a trading recommendation."
}
```

### Field reference

| Field | Type | Meaning |
|-------|------|---------|
| `strategy_id` | string | The strategy's UUID. |
| `strategy_name` | string | Display name. |
| `generated_at` | datetime (UTC) | When the lifecycle was computed. |
| `stages` | array | All 6 stages in order, each with `key`, `label`, `index`, and `state` (`completed` / `current` / `blocked` / `upcoming`). |
| `current_stage` | string | Inferred current stage key. |
| `current_stage_label` | string | Human label for the current stage. |
| `next_stage` | string \| null | The next stage key, or `null` at the final stage. |
| `next_stage_label` | string \| null | Human label for the next stage. |
| `blocked` | bool | `true` when blockers exist **and** a next stage exists. |
| `blocked_stage` | string \| null | The blocked stage key (equals `next_stage` when blocked). |
| `blocked_stage_label` | string \| null | Human label for the blocked stage. |
| `blockers` | array | Progression blockers (see below). Capped at 6. |
| `suggested_actions` | array | Distinct blocker action labels, capped at 5. |
| `deterministic_summary` | string | One-line plain-English summary built from name, stage, next stage, and the first blocker. |
| `disclaimer` | string | Reliability-not-trading-advice notice. |

Each entry in `blockers` has: `reason`, `detail`, `severity`
(`critical` / `high` / `medium` / `low` / `info`), `action_type`
(`link_evidence` / `navigate` / `create_policy` / …), `action_label`,
`target_tab` (nullable), and `related_run_id` (nullable).

## Stage definitions

The 6 canonical stages, in order:

| # | Key | Label | Meaning |
|---|-----|-------|---------|
| 0 | `research` | Research | Idea/exploration stage — no qualifying run evidence yet. |
| 1 | `backtest` | Backtest | A backtest run exists, but the evidence isn't review-ready. |
| 2 | `backtest_review` | Backtest Review | Backtest evidence is ready to be reviewed for quality and assumptions. |
| 3 | `paper_candidate` | Paper Candidate | A paper run exists (or the paper gate stage is reached) — candidate for paper trading consideration. |
| 4 | `shadow` | Shadow | A live/shadow run exists (or the shadow-production gate stage is reached). |
| 5 | `production_candidate` | Production Candidate | The production promotion gate passes — fully evidenced candidate. |

## How the stage is inferred

Stage inference lives in `_infer_current_stage` in
`backend/app/services/strategy_lifecycle.py`. It is deterministic and
**conservative** — a run alone does not advance the stage unless the supporting
verdicts agree. It reuses the promotion-gate engine's `current_stage` and
`promotion_verdict` (from `evaluate_promotion_gates`) and the readiness verdict
(from `compute_strategy_readiness`).

The logic, in order:

1. **No runs → `research`.** If the strategy has no runs at all, it stays in Research.
2. **Production gate passes → `production_candidate`.** If the production promotion
   gate verdict is `pass` or `conditional_pass` **and** the gate's `current_stage`
   is `production_candidate`, the stage is Production Candidate.
3. **Live run or shadow gate → `shadow`.** If there is a `live` run, or the gate's
   `current_stage` is `shadow_production`, the stage is Shadow.
4. **Paper run or paper gate → `paper_candidate`.** If there is a `paper` run, or
   the gate's `current_stage` is `paper_candidate`, the stage is Paper Candidate.
5. **Backtest run → `backtest` / `backtest_review`.** If there is a `backtest` run,
   the stage advances to Backtest Review **only** when the readiness verdict is
   `ready_for_backtest_review` or `ready_for_paper_trading_consideration`.
   Otherwise it stays at Backtest. (So: a strategy whose only runs are research
   runs — no backtest/paper/live — falls through to `research`.)

Run types are read from each `StrategyRun.run_type` (`backtest`, `paper`, `live`;
research-only runs leave all three flags false). `next_stage` is simply the stage
immediately after `current_stage`, or `null` at the final stage.

## What blocks progression

Blockers are not invented here — they are derived from the **M74 action queue**
(`get_action_queue`) so that the lifecycle stays consistent with the rest of the
product. `_collect_blockers` pulls the queue (up to 25 items) and keeps an item as
a blocker only when all three of the following hold:

- **Category** is one of: `readiness`, `governance`, `assumptions`, `freshness`,
  `run_quality`, `evidence`.
- **Severity** is one of: `critical`, `high`, `medium`.
- **Status** is one of: `blocked`, `pending`.

Each surviving item becomes a blocker carrying its `reason` (the queue item's
title), `detail` (why it matters), `severity`, `action_type`, `action_label`,
`target_tab`, and an optional `related_run_id` (set only when the queue item's
related object is a `strategy_run`). The list is capped at 6.

Common blocker reasons:

- Assumption health needs review / assumptions are weak.
- The latest run is missing evidence links.
- Evidence is stale (freshness).
- Promotion gate blockers.
- No paper run / no live run yet.
- Missing governance checks — regression tests, config policy, or SLA.
- No reliability report generated.

`blocked` is `true` only when there is at least one blocker **and** a `next_stage`
exists; `blocked_stage` then equals `next_stage`.

## How the Action Queue and Repair Flows move a strategy forward

Because lifecycle blockers are the same M74 action-queue items, each blocker maps
directly onto an existing **Action Queue** action and, where relevant, an **M75
Evidence Repair** flow. The `action_type` on each blocker drives the destination:

| Blocker need | `action_type` | What it does |
|--------------|---------------|--------------|
| Latest run missing evidence links | `link_evidence` | Opens the M75 evidence repair modal to attach evidence. |
| Promotion gate blockers | `navigate` (→ governance) | Reviews promotion gates. |
| Missing guardrails / config policy | `create_policy` | Creates a guardrail/policy. |
| No reliability report | `generate_report` | Generates the reliability report. |
| No paper run yet | `upload_bundle` (→ Developer tab) | Uploads a paper run bundle. |
| Assumptions need review | `navigate` (→ governance) | Reviews assumptions. |

Clearing the underlying action-queue item removes the blocker, which in turn lets
the strategy advance to its next stage on the next recompute.

## Worked example — KO/PEP Pairs Trade (Maya Test)

A strategy with a backtest run but review-not-ready evidence:

- **current_stage:** `backtest` (Backtest)
- **next_stage:** `backtest_review` (Backtest Review)
- **blocked:** `true`, `blocked_stage` = `backtest_review`

Blockers and their matching actions:

| Reason | Action |
|--------|--------|
| Assumption health needs review | Review assumptions (`navigate` → governance) |
| Latest run is missing evidence links | Fix evidence links (`link_evidence` → repair modal) |
| No paper / live run | Upload paper run bundle (`upload_bundle` → Developer tab) |

`deterministic_summary` reads roughly:
*"KO/PEP Pairs Trade (Maya Test): currently at Backtest. next recommended stage is
Backtest Review. blocked — assumption health needs review."*

Resolving the assumption review and linking the missing run evidence lets readiness
reach `ready_for_backtest_review`, advancing the strategy to **Backtest Review**.

## Where it renders

- **Strategy Detail → Overview tab** — the full lifecycle visual.
- **Command Center** — the full lifecycle visual.
- **Portfolio list** — a compact lifecycle stage chip per strategy.
- **Dashboard** — a compact lifecycle summary.
