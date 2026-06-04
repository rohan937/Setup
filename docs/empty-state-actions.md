# Empty-State Quick Actions

## Overview

Empty states should not be dead ends. When a panel has no artifact to show, it should explain what the missing artifact is, why it matters, and offer the next action — all in product language. These actions reuse existing endpoints (the M75 action functions where available) so the user can move forward without leaving the panel.

The intent is to be **actionable but not noisy**: a short explanation, one primary action, and an optional secondary action. Nothing auto-runs, no advice is given, and no market data or AI is involved.

When the user lacks the write permission required for an action, the action does not fail. Instead it renders a calm, role-aware disabled state (see `RoleAwareAccess`) that shows the user's current role, the required role or permission, and a suggested way forward.

## Improved Empty States

| Panel | What it explains | Primary action | Secondary action |
|-------|------------------|----------------|------------------|
| Regression Test Suite | Regression tests check for metric and trust deterioration between runs, so a strategy that quietly degrades is caught before it ships. | Create default tests | — |
| Config Policy Guardrails | Guardrails enforce policy on costs, fill model, leverage, borrow, and liquidity assumptions, flagging configurations that drift outside agreed bounds. | Create default guardrails | — |
| Evidence SLA Monitor | The SLA defines freshness and evidence obligations — which artifacts must exist and how recent they must be. | Create default SLA | — |
| Shadow Production Monitor | Shadow monitoring needs a paper or live-like run to compare against, so there is something to observe before production. | Go to Developer tab (to upload a paper-run bundle) | — |
| Reliability Snapshot | The snapshot is a cached, deterministic view of reliability state; it appears once it has been computed. | Refresh snapshot | — |
| Reports / Export | A reliability report packages the current governance and observability state into a shareable, durable record. | Generate reliability report | Export report |
| Review Cases | Review cases group related evidence issues so they can be triaged together rather than one finding at a time. | Generate review cases | — |
| Evidence Bundle (upload) | There are two ways to add evidence: a manual JSON bundle upload, or automated ingestion through the SDK / CI. | Load sample bundle | — |
| Strategy list (no strategies) | No strategies exist yet; the panel explains how to create the first one or populate the workspace. | Create Strategy | Reset Clean Realistic Demo (if permitted) · Upload Evidence Bundle |

## The Shared `PanelEmptyState` Component

All of the empty states above are rendered through a single reusable component, `PanelEmptyState`, so the framing is consistent everywhere:

- **Title** — names the missing artifact.
- **Explanation** — one or two calm sentences describing what the artifact is and why it matters.
- **Action buttons** — a primary action and, where relevant, a secondary action, wired to existing endpoints (M75 action functions where available).
- **Optional role-aware disabled note** — when the user lacks the required write permission, the action is shown in a disabled state with a role-aware explanation instead of failing silently or surfacing a blunt error.

The component uses **product language only**. It never gives trading advice, never references AI, and never exposes secrets or suggests editing the database. The result is that every former dead-end panel now explains itself and points to the next concrete step.
