# Strategy Action Queue (M74)

The Action Queue is QuantFidelity's unified, deterministic "what to do next" list
for a strategy. It consolidates outstanding work across the entire evidence
lifecycle into a single prioritized list that answers four questions for every
item:

1. **What** is the most important thing to fix?
2. **Why** does it matter?
3. **How severe** is it, and what is its status?
4. **Where** do I click to fix it?

> The Action Queue prioritizes research **evidence** tasks. It does **not** provide
> trading recommendations. Everything below is computed deterministically from
> existing evidence — no AI, no live market data, no external APIs.

---

## Endpoint

```
GET /api/strategies/{strategy_id}/action-queue?limit=10
```

- **Read-only.** No timeline events are written.
- `limit` (default `10`) caps the number of returned items. The counts in the
  response always reflect the full set, not the truncated list.
- `404` if the strategy does not exist.

### Response shape

```jsonc
{
  "strategy_id": "…",
  "strategy_name": "AAPL Mean Reversion v1",
  "generated_at": "2026-06-04T12:00:00Z",
  "items": [ ActionItem, … ],          // top N by priority
  "total_action_count": 7,
  "completed_count": 0,
  "pending_count": 5,
  "blocked_count": 1,
  "optional_count": 1,
  "deterministic_summary": "…",
  "disclaimer": "Action Queue prioritizes research evidence tasks. It does not provide trading recommendations."
}
```

### ActionItem fields

| Field | Meaning |
|-------|---------|
| `id` | Stable id: `{strategy_hex}:{dedup_key}` |
| `title` | Short product-language label ("Create config guardrails") |
| `description` | One-line context |
| `why_it_matters` | The evidence reason it matters |
| `severity` | `critical` \| `high` \| `medium` \| `low` \| `info` |
| `priority_rank` | 1-based position in the sorted list |
| `status` | `pending` \| `done` \| `blocked` \| `optional` |
| `category` | `evidence` \| `readiness` \| `governance` \| `freshness` \| `run_quality` \| `assumptions` \| `reporting` \| `shadow` \| `developer` |
| `source` | Which subsystem raised it (`readiness`, `freshness`, `promotion_gates`, `report`, …) |
| `target_tab` | Strategy Detail tab to open (`overview`, `evidence`, `runs`, `governance`, `lineage`, `exports`, `developer`) |
| `target_panel_label` | Human label of the destination panel |
| `action_label` | Button text ("Link or upload evidence") |
| `action_type` | `navigate` \| `generate_report` \| `create_policy` \| `create_regression_tests` \| `create_sla` \| `upload_bundle` \| `refresh_snapshot` \| … |
| `related_object_id` / `related_object_type` | Optional pointer to the underlying object (e.g. a `strategy_run`) |
| `deterministic_reason` | The exact data condition that generated the item |
| `created_from` | One or more sources that contributed (after dedup/merge) |

---

## How items are generated

The service (`app/services/action_queue.py`) is split into two layers:

### 1. Backbone — direct DB existence checks (always safe)

These never throw and form the reliable spine of the queue:

- **No runs logged** → "Log your first strategy run".
- **Latest run missing linked evidence** (dataset / signal / universe / version FK
  is null) → "Link evidence to the latest run".
- **No paper/live run** → "Log a paper run before shadow monitoring" (optional).
- **No reliability report** → "Generate a reliability report".
- **No regression tests** → "Create default regression tests".
- **No config policy** → "Create config guardrails".
- **No evidence SLA policy** → "Create an evidence SLA policy".

### 2. Enrichment — guarded service calls

Each of these is wrapped in `try/except` so one broken subsystem can never break
the queue:

- **Strategy health** → open-alert triage + missing-evidence layers.
- **Readiness** → blockers when the verdict is `blocked` / `requires_review` /
  `under_instrumented`.
- **Evidence freshness** → "Refresh stale evidence" / "Refresh aging evidence soon".
- **Promotion gates** → "Resolve promotion blockers".
- **Assumption health** → "Review strategy assumptions" when `review` / `weak`.

---

## Deduplication

Multiple subsystems often point at the same underlying issue. Items are merged by
a `dedup_key`:

- The same key collapses into one item.
- Merged items keep the **most severe** severity and **most urgent** status.
- Each contributing subsystem is recorded in `created_from`, and their reasons are
  concatenated into `deterministic_reason`.

For example, the strategy-health `missing_evidence` entry "No strategy_reliability
report generated yet" is routed onto the same `generate_report` key as the direct
report check, so the queue shows **one** report action with
`created_from: ["report", "reliability"]` rather than two near-duplicates.

---

## Priority sorting

Items are sorted by, in order:

1. **Severity** — `critical` > `high` > `medium` > `low` > `info`.
2. **Status** — `blocked` > `pending` > `optional` > `done`.
3. **Category** — readiness / governance / freshness ahead of reporting, so
   progression-blocking work surfaces before nice-to-have reporting setup.
4. Title (stable tie-break).

`priority_rank` is then assigned 1..N over the sorted, truncated list.

---

## Frontend surfaces

- **Strategy Detail → Overview tab.** The backend queue replaces the M73 local
  queue. If the endpoint fails, the page gracefully falls back to the locally
  computed M73 queue with a short note. Each row shows priority number, severity
  chip, status chip, title, why-it-matters, category · source, and an action
  button that switches to the relevant tab.
- **Command Center.** The operating console: a strategy selector plus a summary
  strip (total / blocking / pending / optional) and the queue grouped into
  **Immediate blockers**, **Evidence fixes**, **Governance setup**, and
  **Reporting & export**. Action buttons deep-link to the strategy with
  `?tab=<target_tab>`.
- **Dashboard.** A compact, fail-safe "Top Priority Actions" card aggregating the
  highest-severity items across strategies, linking through to the Command Center.

Deep links use `/strategies/{id}?tab=<target_tab>`; Strategy Detail reads the
`tab` query parameter on mount to open the right tab.

---

## Language policy

- Product language only: "Fix evidence linkage", "Create guardrails", "Refresh
  stale signal evidence".
- No raw backend/debug phrasing in user-facing copy.
- No "AI" language.
- No trading-recommendation or investment-advice language. The disclaimer is shown
  wherever the queue is rendered.

---

## Tests

`backend/tests/test_action_queue_m74.py` covers:

- Endpoint returns `200`; unknown strategy returns `404`; response/item field shapes.
- Empty strategy produces setup actions (runs, report, regression, config, SLA).
- Missing report → `generate_report`; missing regression tests / config / SLA →
  governance actions.
- Latest run missing evidence → `link_run_evidence` with `related_object_type =
  strategy_run`.
- Configured strategy drops its setup actions (dedup of "done").
- Sequential `priority_rank`, unique ids (dedup), non-decreasing severity order,
  consistent counts.
- No investment-advice language; no AI language; disclaimer present.
