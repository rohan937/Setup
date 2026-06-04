# Home / Workbench

The **Home / Workbench** page is the calm, first-thing-you-see landing surface that answers a single question: **"What should I do today?"**

Where the **Dashboard** is a data-heavy analytics surface (charts, distributions, trend lines, drill-downs), the **Home** page is a warm, action-oriented workbench. It greets the user, summarizes the state of the workspace in a few compact cards, surfaces the highest-priority work, and points to the next sensible step. Home is for orientation and momentum; Dashboard is for analysis.

QuantFidelity is a deterministic reliability, governance, and observability product for quant strategies. The Home page reflects that posture: it never gives trading advice, uses no AI, and pulls in no external market data. It only reflects the reliability and governance state already present in the workspace.

## Route and navigation

- **`/home`** — the Home / Workbench page. This is the **default post-login landing** route.
- **`/dashboard`** — the existing analytics Dashboard, unchanged in purpose.

Both routes live under the **Overview** navigation group. The nav order within Overview is:

1. **Home**
2. **Dashboard**
3. **Portfolio**
4. **Command Center**

## Page sections

### Welcome header

A brief greeting that grounds the user in their context. It shows the **workspace name**, the **current user**, a **role badge** (owner, admin, member, or viewer), and an **environment badge** indicating whether the session is **local** or **production**. The header sets a calm, professional tone and makes the active workspace and identity unambiguous.

### Workspace snapshot

A row of compact cards giving an at-a-glance read on the workspace:

- **Total strategies**
- **Healthy**
- **Review**
- **Blocked / critical**
- **Open alerts**
- **Pending action items**

These cards are composed entirely from the existing **portfolio overview** endpoint — no new backend is introduced. The snapshot is meant to be scanned in seconds, not studied.

### Today's recommended actions

An aggregated, prioritized list of the **highest-priority M74 Action Queue items** across all strategies. Each item shows:

- The **strategy name**
- A **severity** indicator
- A short **"why it matters"** explanation
- A **button** that navigates directly to the strategy on the **correct tab** for resolving the item

This is the heart of the "what should I do today?" answer: a single, ranked place to see the most important reliability and governance work waiting across the portfolio.

### Demo progress / guided walkthrough card

A card that helps users experience the product through the guided demo. Depending on state, it offers **Start guided demo**, **Continue**, or **Restart**. If demo data is missing, the card links to **Demo Controls** so the user can seed it. The walkthrough is purely instructional; it never alters reliability conclusions.

### Strategy status summary

A short narrative summary of where each strategy stands. When the **clean-demo** data is present, it tells the intended demo story:

- **AAPL** — healthy and well-instrumented.
- **FX Carry** — in review, with stale evidence.
- **Crypto Momentum** — blocked and under-instrumented.
- **Maya KO / PEP** — improving, but not yet promotion-clean.

When demo data is not present, the section falls back to a **generic summary** derived from the workspace's actual strategies and their statuses.

### Quick actions

A compact set of buttons for the most common next steps:

- **Create Strategy**
- **Upload Evidence Bundle**
- **Open Command Center**
- **Start Guided Demo**
- **Run Demo Reset** — shown **only if** the current user has the `can_seed_demo` permission.

Actions the user cannot perform are handled with the role-aware UX so the user always understands what they can still do and how to proceed.

## How a new user should proceed after login

1. **Land on Home.** The default post-login route brings the user straight to the workbench.
2. **Read the workspace snapshot.** Get an immediate sense of totals, health, alerts, and pending items.
3. **Start the guided demo** (if exploring) **or open the top recommended action** (if there's real work to do).
4. **Fix it.** Resolve the item through the **Action Queue** and the relevant repair flows on the strategy's correct tab.

This flow is designed to take a new user from "I just logged in" to "I'm making progress" without guesswork.

## Composition note

The Home / Workbench page is composed **entirely from existing endpoints** — the **portfolio overview**, **strategies**, **demo status**, and **current user** endpoints. There is **no new backend**, **no AI**, and **no trading advice**. Home simply reflects the reliability and governance state already present in the workspace, presented as a calm starting point for the day's work.
