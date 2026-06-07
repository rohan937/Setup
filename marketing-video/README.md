# QuantFidelity — AI Product Walkthrough

A self-contained [Remotion](https://www.remotion.dev/) project that renders a
**~72-second, 1920x1080, 30fps DARK, premium AI-style product walkthrough** for
**QuantFidelity** (M101–M108 aesthetic).

This is a **separate, standalone project**. It does **not** import from or modify
the main app (`frontend/` or `backend/`). It uses only system/local fonts, no
paid fonts, no external services, and is **silent** (add music later).

The walkthrough is a **9-scene, cursor-driven product demo**: it opens on a
confident-looking backtest, exposes the hidden assumptions, then drives the
`AnimatedCursor` through the Research Command Center, the Strategy Workspace,
and the Reality / Evidence / Governance tabs — clicking, hovering, and revealing
panels like a real screen recording — before closing on the system map and
brand.

## Quick start

```bash
cd marketing-video
npm install

# Open Remotion Studio (live preview + scrubbing)
npm run preview

# Render the final video -> out/quantfidelity-ai-product-walkthrough.mp4
npm run render

# Type-check without emitting
npm run typecheck
```

## Screenshots — 404-safe (`SafeScreenshotFrame`)

The screenshot path is now **`public/screenshots/`** (Remotion's public dir; see
`remotion.config.ts`, `Config.setPublicDir("public")`).

Screenshots are **opt-in and 404-safe**. `SafeScreenshotFrame` only calls
`staticFile` / `<Img>` for a file whose name is listed in
`AVAILABLE_SCREENSHOTS` (in `src/timing.ts`). Any other name renders a polished
dark **mock** frame instead — so there are **zero 404 logs, no decode attempts,
and no crashes**, even when no PNGs exist.

To activate real screenshots (two steps — both required):

1. **Drop the PNGs** into `public/screenshots/`, e.g.
   `public/screenshots/home.png`, `executive-demo.png`,
   `strategy-overview.png`, `reality-tab.png`, `governance-tab.png`.
2. **Add their filenames** to `AVAILABLE_SCREENSHOTS` in `src/timing.ts` to
   activate them:
   ```ts
   export const AVAILABLE_SCREENSHOTS: string[] = [
     "home.png",
     "strategy-overview.png",
     "reality-check.png",
     "evidence.png",
     "governance.png",
   ];
   ```

Until a name appears in that array, `SafeScreenshotFrame` renders a polished
dark mock and **never** calls `staticFile` for it — that is the 404-safe design.

Filenames referenced by the montage scene (`SCRIPT.montage.shots` in
`src/timing.ts`): `home.png`, `strategy-overview.png`, `reality-check.png`,
`evidence.png`, `governance.png`. Recommended source aspect ratio is 16:9
(e.g. 1600x900); frames crop with `object-fit: cover`.

## Editing copy, timing, and colors

Everything is centralized in **`src/timing.ts`**:

- `SCENES` — the 9 scenes (order, start frames, durations).
- `SCRIPT` — all on-screen text **and mock UI data** (captions, backtest card
  metrics, hidden-warning rows, command-center summary numbers, workspace score
  cards, reality-check panel, evidence panel, governance panel + risk narrative,
  montage labels, final system map + disclaimer).
- `COLORS` — the DARK palette.
- `STAGES` — the 5 lifecycle stages.
- `AVAILABLE_SCREENSHOTS` — the 404-safe screenshot allow-list.
- `FPS`, `VIDEO_DURATION_SECONDS`, `DURATION` — global timing.

## DARK palette

| Token            | Value                       |
| ---------------- | --------------------------- |
| `bg`             | `#0B1020`                   |
| `surface`        | `#111827`                   |
| `elevated`       | `#162033`                   |
| `border`         | `rgba(255,255,255,0.08)`    |
| `textPrimary`    | `#F8FAFC`                   |
| `textSecondary`  | `#94A3B8`                   |
| `textMuted`      | `#64748B`                   |
| `blue`           | `#4F8CFF`                   |
| `purple`         | `#8B5CF6`                   |
| `cyan`           | `#06B6D4`                   |
| `success`        | `#00D492`                   |
| `warning`        | `#FFB547`                   |
| `danger`         | `#FF6B6B`                   |

## Scene breakdown (~72s, 9 scenes)

| Time     | Scene           | Content                                                        |
| -------- | --------------- | ------------------------------------------------------------- |
| 0–5s     | `hook`          | A clean-looking SPY backtest card — "looks production-ready"  |
| 5–10s    | `hidden`        | The hidden problems: 0 bps costs, missing paper run           |
| 10–18s   | `commandCenter` | Research Command Center: summary numbers + strategy rows      |
| 18–28s   | `workspace`     | Strategy Workspace: tabs + score cards + lifecycle pipeline   |
| 28–39s   | `reality`       | Backtest Reality Check: 72/100, Review, turnover tooltip      |
| 39–49s   | `evidence`      | Evidence Verification: 91/100, Verified, root hash            |
| 49–60s   | `governance`    | Promotion Readiness: gates + generated risk narrative         |
| 60–66s   | `montage`       | Fast montage of the product surfaces                          |
| 66–72s   | `final`         | Tagline + QuantFidelity system map + disclaimer               |

## Components (`src/components/`)

All dark-themed and animation-driven via props (`appear` / `progress` 0–1) so
scenes own the timing.

| Component                        | Role                                                       |
| -------------------------------- | ---------------------------------------------------------- |
| `AmbientBackground`              | Dark bg + drifting blue/purple/cyan glows + subtle sweep   |
| `AnimatedCursor`                 | macOS arrow cursor; hover ring + click ripple + label pill |
| `ClickRipple`                    | Expanding/fading brand ring                                |
| `ProductFrame`                   | Floating dark app window (titlebar dots, glow, appear)     |
| `AppHeaderMock`                  | Slim app top bar (wordmark, API-online dot, user pill)     |
| `SidebarMock`                    | Dark grouped nav with active highlight                     |
| `StrategyCardMock`               | Strategy row (name, asset badge, reliability, stage)       |
| `ScoreCardMock`                  | Metric/score card with tone color + focus glow             |
| `LifecycleMock`                  | 5-stage pipeline with animated connector flow              |
| `TabBarMock`                     | Workspace tab bar with animated active underline           |
| `RealityCheckPanelMock`          | "Backtest Reality Check" panel + tooltip                   |
| `EvidenceVerificationPanelMock`  | "Evidence Verification" panel + root hash                  |
| `GovernancePanelMock`            | "Promotion Readiness" panel + generate button              |
| `NarrativePanelMock`             | AI risk-narrative reveal                                   |
| `SafeScreenshotFrame`            | **404-safe** screenshot/mock frame                         |
| `tone.ts`                        | Shared tone → color / glyph / score-band helpers           |

Each scene lives in `src/scenes/` (`HookScene`, `HiddenScene`,
`CommandCenterScene`, `WorkspaceScene`, `RealityScene`, `EvidenceScene`,
`GovernanceScene`, `MontageScene`, `FinalScene`) plus a shared `Caption`
helper. Scenes are wired into the composition in
`src/QuantFidelityLaunchVideo.tsx`, each inside its own `<Sequence>` so its
`useCurrentFrame()` is local. The obsolete light-era scenes/components have been
removed — the whole `src/` tree is type-checked.

## Audio

The video is **silent by design** (no copyrighted audio). Add a music bed in
any editor after rendering.

## Dependencies

- `remotion` ^4.0.0, `@remotion/cli` ^4.0.0
- `react` / `react-dom` ^18.3.1
- Dev: `typescript`, `@types/react`, `@types/react-dom`

Fonts use a system stack (`Inter, -apple-system, Segoe UI, sans-serif`); no font
downloads required.
