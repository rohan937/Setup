# QuantFidelity Marketing Video

A self-contained [Remotion](https://www.remotion.dev/) project that renders a
~45-second, 1920x1080, 30fps cinematic SaaS launch video for **QuantFidelity**.

This is a **separate, standalone project**. It does **not** import from or modify
the main app (`frontend/` or `backend/`). It uses only system/local fonts, no
paid fonts, no external services, and is **silent** (add music later).

## Quick start

```bash
cd marketing-video
npm install

# Open Remotion Studio (live preview + scrubbing)
npm run preview

# Render the final video -> out/quantfidelity-launch.mp4
npm run render

# Render a single still frame for a quick sanity check -> out/frame.png
npm run still

# Type-check without emitting
npm run typecheck
```

## Screenshots (optional, auto-detected)

Drop PNGs into `assets/screenshots/` and they appear automatically in the
screenshots scene. No code changes needed.

Expected files:

- `assets/screenshots/home.png` — labeled "Research Command Center"
- `assets/screenshots/executive-demo.png` — labeled "Executive Demo"
- `assets/screenshots/strategy-overview.png` — labeled "Strategy Workspace"

If a file is missing, the frame **gracefully falls back** to a polished
gradient placeholder with the label — rendering never crashes. As soon as you
add the real PNG, it is used instead.

Recommended source aspect ratio is 16:9 (e.g. 1600x900). The frames crop with
`object-fit: cover`.

> The `assets/` folder is configured as Remotion's public dir (see
> `remotion.config.ts`), so `staticFile("screenshots/home.png")` resolves to
> `assets/screenshots/home.png`.

## Editing copy, timing, and colors

Everything is centralized in **`src/timing.ts`**:

- `SCENES` — scene order, start frames, and durations.
- `SCRIPT` — all on-screen text (hooks, card metrics, reality bullets,
  workflow steps + captions, final brand text, disclaimer).
- `COLORS` — the full palette.
- `FPS`, `VIDEO_DURATION_SECONDS`, `DURATION` — global timing.

Change text or numbers there and the whole video updates.

## Scene breakdown (~45s)

| Time      | Scene             | Content                                            |
| --------- | ----------------- | -------------------------------------------------- |
| 0–4s      | Hook              | `[ backtests look clean ]`                         |
| 4–8s      | Tension           | `[ until production disagrees ]` (deeper blue)     |
| 8–15s     | Backtest card     | SPY Trend Backtest v1 metrics + Reality Check badge|
| 15–20s    | Product reveal    | "QuantFidelity checks what research teams miss."   |
| 20–28s    | Reality check     | 4 findings + "Not ready for promotion."            |
| 28–34s    | Workflow pipeline | Evidence → Reality → Verification → Governance → Promotion |
| 34–40s    | Screenshots       | Three product frames, staggered                    |
| 40–45s    | Final             | Tagline + QuantFidelity wordmark + disclaimer      |

## Audio

The video is **silent by design** (no copyrighted audio). Add a music bed in
CapCut, Premiere, Canva, or any editor after rendering.

## Project structure

```
marketing-video/
├── package.json
├── tsconfig.json
├── remotion.config.ts
├── README.md
├── .gitignore
├── assets/
│   └── screenshots/        # drop home.png / executive-demo.png / strategy-overview.png here
├── out/                    # render output (gitignored)
└── src/
    ├── index.ts            # registerRoot(RemotionRoot)
    ├── RemotionRoot.tsx     # <Composition>
    ├── QuantFidelityLaunchVideo.tsx  # main timeline (Sequences)
    ├── timing.ts           # SCENES + SCRIPT + COLORS (edit here)
    ├── components/
    │   ├── AmbientBackground.tsx
    │   ├── BracketText.tsx
    │   ├── FloatingCard.tsx
    │   ├── MetricRow.tsx
    │   ├── WorkflowPipeline.tsx
    │   ├── ScreenshotFrame.tsx
    │   ├── SceneTitle.tsx
    │   ├── QuantFidelityLogoText.tsx
    │   └── DisclaimerText.tsx
    └── scenes/
        ├── HookScene.tsx
        ├── TensionScene.tsx
        ├── BacktestCardScene.tsx
        ├── ProductRevealScene.tsx
        ├── RealityCheckScene.tsx
        ├── WorkflowScene.tsx
        ├── ScreenshotScene.tsx
        └── FinalScene.tsx
```

## Dependencies

- `remotion` ^4.0.0
- `@remotion/cli` ^4.0.0
- `react` ^18.3.1
- `react-dom` ^18.3.1
- Dev: `typescript`, `@types/react`, `@types/react-dom`

Fonts use a system stack (`Inter, -apple-system, Segoe UI, sans-serif`); no font
downloads required.
