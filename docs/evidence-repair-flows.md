# Evidence Repair Flows + Strategy Management (M75)

QuantFidelity identifies missing evidence (M27 health, M48 freshness) and
prioritizes it (M74 Action Queue). M75 makes those findings **actionable from the
web UI**: link existing evidence to runs, trigger the existing generate/create
endpoints with one click, and perform basic strategy management (edit / archive).

Everything here is deterministic and local — no AI, no external data, no trading
actions.

---

## What "missing evidence" means

A strategy run is an evidence anchor. Each run can link to:

| Link | Meaning |
|------|---------|
| **Dataset snapshot** | the price/data snapshot the run used |
| **Signal snapshot** | the signal values the run consumed |
| **Universe snapshot** | the tradable symbol set |
| **Strategy version** | the code/config version that produced the run |

When a link is absent, run-level trust scoring and drift comparisons are
incomplete. The UI says, in product language:

> "This run is not linked to a dataset snapshot."
> "Linking evidence lets QuantFidelity verify data quality and compare drift correctly."

---

## Linking existing evidence

### From the UI

1. Open a strategy → **Overview** tab → **Action Queue**. An item such as
   *"Fix evidence links"* (action type `link_evidence`) opens the **Evidence
   Repair** modal for the affected run.
2. Or open the **Runs** tab and click **Link evidence** on any run that is missing
   a link.
3. The modal shows the run, the missing link types, and a dropdown of **compatible**
   evidence for each, annotated with a useful score:
   - dataset → health score + row count
   - signal → quality score + symbol count
   - universe → symbol count
   - version → version label
   The latest/highest-quality option is flagged *recommended*.
4. Select one or more and click **Link Evidence**. On success the modal closes,
   the strategy and Action Queue refresh, and the repaired item disappears.

### Endpoints

```
GET   /api/strategies/{id}/repair-options
PATCH /api/strategies/{id}/runs/{run_id}/links
```

`repair-options` returns linkable `dataset_snapshots`, `signal_snapshots`,
`universe_snapshots`, `strategy_versions`, and the list of `runs_missing_links`.

`PATCH …/links` accepts any subset of:

```json
{
  "dataset_snapshot_id": "…",
  "signal_snapshot_id": "…",
  "universe_snapshot_id": "…",
  "strategy_version_id": "…"
}
```

**Validation (compatibility):**

- the run must belong to the strategy in the URL,
- a **dataset snapshot** must belong to a dataset in the **same project** as the strategy,
- **signal / universe / version** must belong to the **same strategy**.

Incompatible or cross-strategy links are rejected with `400`. A successful link
writes a `run_evidence_linked` timeline event and best-effort refreshes the
reliability snapshot cache. Linking requires the **write-research** permission.

---

## When to upload a new bundle instead

Linking only works with evidence that **already exists**. If a dropdown is empty
("No compatible signal snapshots found"), there is nothing to link — you should
add evidence first:

- Use the **Evidence Bundle uploader** on the **Developer** tab (or the Evidence
  Bundles page) to ingest a bundle, **or**
- log the evidence via the SDK/CLI ingestion path.

Then re-open the repair modal and the new snapshot will be selectable.

---

## One-click governance / reporting actions

The Action Queue buttons also call existing endpoints directly and refresh:

| Action type | Endpoint reused |
|-------------|-----------------|
| `generate_report` | `POST /reports/strategy/{id}` |
| `create_regression_tests` | `POST /strategies/{id}/regression-tests/defaults` |
| `create_policy` | `POST /strategies/{id}/config-policies/default` |
| `create_sla` | `POST /strategies/{id}/evidence-sla/default` |
| `run_alert_check` | `POST /alerts/generate` |
| `upload_bundle` | switches to the Developer tab uploader |

No duplicate endpoints were added — M75 reuses the existing M14/M53/M54/M56/M11
routes.

---

## Strategy management (edit / archive)

### Edit

`PATCH /api/strategies/{id}` updates `name`, `description`, `status`, and
`asset_class` (partial; invalid status/asset class → `400`). In the UI: the
**Manage ▾** menu on the Strategy Detail header, or the **⋯** row menu on the
Strategies list → **Edit**.

### Archive (soft delete)

`DELETE /api/strategies/{id}?confirm=true` sets the strategy status to
`archived`. `confirm=true` is required (a missing confirm returns `400`); the UI
also requires a typed checkbox acknowledgement. After archiving, the UI navigates
back to the Strategies list. A `strategy_archived` timeline event is written.

Both actions require the **write-research** permission; viewers receive `403`.

### Why archive instead of hard delete

A strategy fans out into many cascade relationships — runs, versions, dataset /
signal / universe snapshots, backtest audits, reliability scores, reports, alerts,
review cases, policies, and timeline events. A hard delete would either destroy
that evidence trail or risk FK-integrity errors. **Archiving is reversible, keeps
the full audit trail, and simply removes the strategy from the active working
view.** The Strategies list has an **Active / Archived / All** filter
(`GET /api/strategies?status=active|archived|all`).

---

## Language policy

All copy uses product language ("Fix evidence links", "Create guardrails",
"Archive strategy") — never raw "missing FK" wording, never "AI", and never
trading-recommendation language.
