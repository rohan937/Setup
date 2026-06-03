# QuantFidelity Deployment Readiness Guide

## What M65 checks
- Repository hygiene (gitignore, env files, docs, scripts)
- Backend structure (main, config, router, migrations, admin routes, services)
- Frontend structure (package.json, vite.config, pages, API client)
- SDK/CI readiness (quantfidelity package, CLI, tests, examples, GitHub Actions)
- Database/demo readiness (migrations, demo seed, system health service)
- Security/config (env example, API key foundation, CORS, secrets)
- Deployment blockers (manual checklist)

## What M70 adds (Render + PostgreSQL prep)
- `scripts/backend_migrate.sh` — pre-deploy migration runner
- `scripts/backend_start.sh` — production server launcher
- `docs/render-backend.md` — Render deployment guide
- `render.yaml.example` — Render blueprint example
- psycopg2-binary in requirements.txt
- `GET /api/health/deployment` — deployment configuration health endpoint
- Config: `postgres://` → `postgresql://` auto-normalisation, `QF_ENVIRONMENT`, `QF_LOG_LEVEL`
- Deployment readiness checks: render_deployment category (M70 artifacts)

## What M65/M70 does NOT do
- Deploy to Render, Vercel, or any server
- Provision production PostgreSQL
- Push code or containers
- Configure production domains or HTTPS
- Run production migrations
- Set up production monitoring

## Readiness levels
- `local_demo_ready`: Core local demo structure passes. Manual deployment checks remain.
- `deployment_prep_ready`: Score >= 85, no high/critical fails.
- `needs_review`: Score < 75 or high-severity failures.
- `blocked`: Critical failure detected.

## Required environment variables

### Backend (production)

| Variable | Purpose | Default | Required in prod |
|----------|---------|---------|------------------|
| `QF_ENVIRONMENT` | Environment name | `local` | Yes — set to `production` |
| `QF_DATABASE_URL` | PostgreSQL URL | SQLite dev default | Yes |
| `QF_JWT_SECRET_KEY` | JWT signing secret | **insecure dev default** | **Yes — generate a strong secret** |
| `QF_CORS_ORIGINS` | Comma-separated frontend origins | localhost only | Yes |
| `QF_DEBUG` | Debug mode | `true` | Set to `false` |
| `QF_AUTH_ENABLED` | Enable JWT auth | `true` | Yes |
| `QF_RBAC_ENABLED` | Enable RBAC | `true` | Yes |
| `QF_REQUIRE_API_KEY_FOR_INGESTION` | Gate ingestion endpoint | `false` | Recommended `true` |
| `QF_API_KEY_ENV` | Key prefix: local/live | `local` | Set to `live` |
| `QF_LOG_LEVEL` | Log verbosity | `info` | Optional |

**Generate a strong JWT secret:**
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

### Frontend

| Variable | Purpose | Default |
|----------|---------|--------|
| `VITE_API_BASE_URL` | Backend API URL | `http://localhost:8000` |

---

## Backend deployment checklist

```bash
# 1. Install dependencies (includes psycopg2-binary for PostgreSQL)
cd backend && pip install -r requirements.txt

# 2. Set environment variables (copy from .env.example, fill production values)
cp backend/.env.example backend/.env
# Edit backend/.env — never commit it

# 3. Run database migrations
bash scripts/backend_migrate.sh

# 4. Start the application server
bash scripts/backend_start.sh

# 5. Verify deployment health (no secrets exposed)
curl http://localhost:8000/api/health/deployment | python3 -m json.tool

# 6. Check overall deployment readiness score
curl http://localhost:8000/api/admin/deployment-readiness | python3 -m json.tool

# 7. Seed demo data (optional for local/staging)
curl -s -X POST http://localhost:8000/api/admin/seed-demo -H "Content-Type: application/json" \
  -d '{"mode": "extend"}' | python3 -m json.tool
```

---

## Render-specific commands

See `docs/render-backend.md` for the complete Render setup guide.

**Build command:**
```
pip install -r requirements.txt
```

**Pre-deploy command (runs migrations before each deploy):**
```
bash ../scripts/backend_migrate.sh
```

**Start command:**
```
bash ../scripts/backend_start.sh
```

**Health check path:** `/health`

**Deployment health path:** `/api/health/deployment`

---

## Secrets checklist (before public deployment)
- [ ] No `.env` files committed to git (`git log --all -- '*.env'`)
- [ ] `QF_JWT_SECRET_KEY` is a strong random secret (not the dev default)
- [ ] `QF_DATABASE_URL` points to PostgreSQL (not SQLite)
- [ ] `QF_CORS_ORIGINS` is the exact frontend origin — no wildcard
- [ ] `QF_DEBUG=false` in production
- [ ] No API keys in committed code
- [ ] Demo API keys rotated after seeding
- [ ] `/api/health/deployment` returns `jwt_secret_safe: true` and no `production_warnings`

## CORS configuration (production)
Set `QF_CORS_ORIGINS` to your exact frontend origin. Wildcard (`*`) is never safe with credential-based auth:
```
QF_CORS_ORIGINS=https://your-frontend.vercel.app
```

## Security defaults (production)
| Setting | Recommended production value |
|---------|------------------------------|
| `QF_AUTH_ENABLED` | `true` |
| `QF_RBAC_ENABLED` | `true` |
| `QF_REQUIRE_API_KEY_FOR_INGESTION` | `true` |
| `QF_DEBUG` | `false` |
| `QF_ENVIRONMENT` | `production` |

## Next milestones
| Milestone | Description |
|-----------|-------------|
| M71 | Frontend deployment prep — Vercel project, `VITE_API_BASE_URL`, domain |
| M72 | Production auth/CORS/rate-limit hardening |
| M73 | Public demo QA — seed production demo, validate all pages |

---
*QuantFidelity deployment readiness documentation. Updated by M65 and M70.*
