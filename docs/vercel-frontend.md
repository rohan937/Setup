# QuantFidelity Frontend — Vercel Deployment Guide

> **M71 status:** Deployment prep artifacts complete. Actual deployment is performed after M70
> backend deployment is live and the Render URL is known.
> This document records the exact configuration needed for a Vercel deployment.

## Overview

| Item | Value |
|------|-------|
| Framework preset | Vite |
| Root directory | `frontend` |
| Install command | `npm ci` |
| Build command | `npm run build` |
| Output directory | `dist` |
| SPA routing | `frontend/vercel.json` (rewrites all paths to `/index.html`) |
| Required env var | `VITE_API_BASE_URL` |

---

## Prerequisites

- **M70 backend deployed** — you need the Render backend URL before setting `VITE_API_BASE_URL`.
- **Backend CORS updated** — after you know the Vercel URL, set `QF_CORS_ORIGINS` on Render to that exact origin.

---

## Step-by-step Vercel setup

### 1. Import the repository on Vercel

1. Go to **vercel.com/new** and import your GitHub repository.
2. Set **Root Directory** to `frontend`.
3. Vercel should auto-detect Vite. Verify:
   - Framework: **Vite**
   - Build Command: `npm run build`
   - Output Directory: `dist`
   - Install Command: `npm ci`

### 2. Configure environment variables

Set these in the Vercel project **Settings → Environment Variables** tab.
Never paste secrets into the repository.

| Variable | Value | Notes |
|----------|-------|-------|
| `VITE_API_BASE_URL` | `https://your-render-backend.onrender.com` | Render backend URL — no trailing slash |
| `VITE_APP_ENV` | `production` | |
| `VITE_DEMO_MODE` | `false` | Reserved for M73 demo mode |

### 3. SPA routing

`frontend/vercel.json` is already committed and configures all-paths rewrite to `/index.html`
so that React Router deep-links work on refresh:

```json
{
  "rewrites": [
    { "source": "/(.*)", "destination": "/index.html" }
  ]
}
```

Vercel picks this up automatically from the `frontend/` root directory.

### 4. Update backend CORS after deploy

Once you have the Vercel URL (e.g. `https://quantfidelity.vercel.app`), update the Render
backend environment variable:

```
QF_CORS_ORIGINS=https://quantfidelity.vercel.app
```

Then redeploy (or trigger a Render deploy) for CORS to take effect.

---

## Local validation

Run these before deploying to confirm the build works with a production-like URL:

```bash
# Syntax-check the build script
bash -n scripts/frontend_build.sh

# Run typecheck + build locally (default VITE_API_BASE_URL=http://localhost:8000)
bash scripts/frontend_build.sh

# Build with a production-like backend URL
VITE_API_BASE_URL=https://example-render-backend.onrender.com bash scripts/frontend_build.sh

# Preview the production build locally
bash scripts/frontend_preview.sh
# Open http://localhost:4173

# TypeScript type check only
cd frontend && npm run typecheck
```

---

## Auth token note

JWT tokens are stored in `localStorage` under key `qf_access_token` (M68 foundation).
This is sufficient for the current development stage. Production hardening (HttpOnly cookies,
token refresh, CSRF protection) is planned for M72.

---

## Security checklist before going live

- [ ] `VITE_API_BASE_URL` points to the actual Render backend (not localhost)
- [ ] `VITE_APP_ENV=production` is set
- [ ] Backend `QF_CORS_ORIGINS` includes the exact Vercel origin — no wildcard
- [ ] No `.env.local` or `.env` files in the repository
- [ ] `npm run typecheck` passes with zero errors
- [ ] `npm run build` produces a clean `dist/`
- [ ] Deep-link refresh works (verify `/strategies` reloads correctly)
- [ ] Login flow works end-to-end against the production backend

---

## Environment variable reference

| Variable | Purpose | Local default | Production value |
|----------|---------|--------------|-----------------|
| `VITE_API_BASE_URL` | Backend API URL | `http://localhost:8000` | `https://your-render-backend.onrender.com` |
| `VITE_APP_ENV` | App environment | `local` | `production` |
| `VITE_DEMO_MODE` | Demo mode flag | `false` | `false` (M73 will use `true`) |

---

## Next steps after frontend deployment

- **M72**: Production auth/CORS/API-key/rate-limit hardening — HttpOnly cookies, stricter CORS, rate limiting.
- **M73**: Public demo workspace — read-only demo mode, `VITE_DEMO_MODE=true`.
- **M74**: Public demo QA.
- **M75**: Landing page and customer outreach.
