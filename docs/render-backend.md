# QuantFidelity Backend — Render Deployment Guide

> **M70 status:** Deployment prep artifacts complete. Actual deployment is performed in a later step.
> This document records the exact configuration needed for a Render Web Service deployment.

## Overview

| Item | Value |
|------|-------|
| Service type | Web Service |
| Runtime | Python 3 |
| Root directory | `backend` |
| Build command | `pip install -r requirements.txt` |
| Pre-deploy command | `bash ../scripts/backend_migrate.sh` |
| Start command | `bash ../scripts/backend_start.sh` |
| Health check path | `/health` |
| Deployment health path | `/api/health/deployment` |

---

## Step-by-step Render setup (do not perform until M71 frontend prep is complete)

### 1. Create a Render PostgreSQL database

1. In the Render dashboard, create a new **PostgreSQL** instance.
2. Note the **Internal Database URL** — it looks like:
   `postgres://user:password@dpg-XXXX-a/quantfidelity`
3. Keep it in a safe place. You will set it as `QF_DATABASE_URL` below.

### 2. Create a Render Web Service

1. Connect your GitHub repository.
2. Set **Root Directory** to `backend`.
3. Set **Build Command**:
   ```
   pip install -r requirements.txt
   ```
4. Set **Pre-deploy Command** (runs migrations before each deploy):
   ```
   bash ../scripts/backend_migrate.sh
   ```
5. Set **Start Command**:
   ```
   bash ../scripts/backend_start.sh
   ```
6. Set **Health Check Path** to `/health`.

### 3. Configure environment variables on Render

Set the following in the Render service **Environment** tab. Never paste these into the repository.

| Variable | Value | Notes |
|----------|-------|-------|
| `QF_ENVIRONMENT` | `production` | |
| `QF_DATABASE_URL` | (paste Internal Database URL from step 1) | Render `postgres://` URL is auto-normalised to `postgresql://` |
| `QF_JWT_SECRET_KEY` | (generate below) | **Never use the dev default** |
| `QF_CORS_ORIGINS` | `https://your-frontend.vercel.app` | Exact origin — no trailing slash |
| `QF_DEBUG` | `false` | |
| `QF_AUTH_ENABLED` | `true` | |
| `QF_RBAC_ENABLED` | `true` | |
| `QF_REQUIRE_API_KEY_FOR_INGESTION` | `true` | Recommended for production |
| `QF_API_KEY_ENV` | `live` | Switches key prefix from `qf_local_` to `qf_live_` |
| `QF_ACCESS_TOKEN_EXPIRE_MINUTES` | `1440` | 24 hours |
| `QF_LOG_LEVEL` | `info` | |

**Generate a strong JWT secret:**
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

### 4. Verify the deployment

After Render finishes deploying:

```bash
# Liveness check
curl https://your-backend.onrender.com/health

# Deployment config check (no secrets returned)
curl https://your-backend.onrender.com/api/health/deployment | python3 -m json.tool
```

Expected `deployment_health` response on a healthy production deployment:
```json
{
  "status": "ok",
  "environment": "production",
  "database_configured": true,
  "database_reachable": true,
  "database_driver": "postgresql",
  "auth_enabled": true,
  "rbac_enabled": true,
  "cors_configured": true,
  "jwt_secret_safe": true,
  "production_warnings": []
}
```

If `production_warnings` is non-empty, fix the listed issues before routing traffic.

---

## Local validation commands

Run these before deploying to confirm everything works locally with the same script paths:

```bash
# Syntax-check the scripts
bash -n scripts/backend_migrate.sh
bash -n scripts/backend_start.sh

# Run migrations locally (SQLite)
bash scripts/backend_migrate.sh

# Start the server locally (Ctrl+C to stop)
bash scripts/backend_start.sh

# Check deployment health locally
curl http://localhost:8000/api/health/deployment | python3 -m json.tool

# Run M70 tests
cd backend && python3 -m pytest tests/test_deployment_m70.py tests/test_deployment_readiness_m65.py -q
```

---

## Security checklist before going live

- [ ] `QF_JWT_SECRET_KEY` is a strong random secret (not the dev default)
- [ ] `QF_ENVIRONMENT=production` is set
- [ ] `QF_DATABASE_URL` points to the Render PostgreSQL instance (not SQLite)
- [ ] `QF_CORS_ORIGINS` is set to the exact Vercel frontend URL
- [ ] `QF_DEBUG=false`
- [ ] No `.env` files in the repository (`git log --all -- '*.env'`)
- [ ] `QF_REQUIRE_API_KEY_FOR_INGESTION=true` if the ingestion endpoint is public
- [ ] All API keys from local dev/demo seeding are revoked before launch
- [ ] `/api/health/deployment` returns `jwt_secret_safe: true` and no `production_warnings`

---

## Production CORS note

In production, set `QF_CORS_ORIGINS` to the **exact** Vercel frontend origin:

```
QF_CORS_ORIGINS=https://your-frontend.vercel.app
```

Never use `*` (wildcard) in production — the application does not support it and it bypasses credential-based auth.

---

## Database URL normalisation

Render provides `postgres://` connection strings. The QuantFidelity settings module automatically normalises these to `postgresql://` for SQLAlchemy compatibility. You can paste the Render URL directly — no manual substitution needed.

---

## Next steps after backend deployment

- **M71**: Frontend Deployment Prep — Vercel project setup, `VITE_API_BASE_URL` pointing to this Render service.
- **M72**: Production auth/CORS/rate-limit hardening.
- **M73**: Public demo QA.
