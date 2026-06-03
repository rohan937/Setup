# QuantFidelity Deployment Readiness Guide

## What M65 checks
- Repository hygiene (gitignore, env files, docs, scripts)
- Backend structure (main, config, router, migrations, admin routes, services)
- Frontend structure (package.json, vite.config, pages, API client)
- SDK/CI readiness (quantfidelity package, CLI, tests, examples, GitHub Actions)
- Database/demo readiness (migrations, demo seed, system health service)
- Security/config (env example, API key foundation, CORS, secrets)
- Deployment blockers (manual checklist for M66+)

## What M65 does NOT do
- Deploy to Render, Vercel, or any server
- Provision production PostgreSQL
- Push code or containers
- Configure production domains or HTTPS
- Run production migrations
- Set up production monitoring

## Readiness levels
- `local_demo_ready`: Core local demo structure passes. Manual deployment checks remain.
- `deployment_prep_ready`: Score >= 85, no high/critical fails. Ready to start M66.
- `needs_review`: Score < 75 or high-severity failures. Resolve before M66.
- `blocked`: Critical failure detected.

## Required environment variables

### Backend (for production deployment)
| Variable | Purpose | Default | Required in prod |
|----------|---------|---------|------------------|
| `DATABASE_URL` | PostgreSQL URL | `sqlite:///./quantfidelity.db` | Yes |
| `QF_REQUIRE_API_KEY_FOR_INGESTION` | Enforce API keys on ingestion endpoint | `false` | Recommended |
| `QF_API_KEY_HASH_SECRET` | Optional HMAC pepper for key hashing | — | Optional |
| `QF_ENVIRONMENT` | Environment name | `development` | Optional |

### Frontend (for production deployment)
| Variable | Purpose | Default |
|----------|---------|--------|
| `VITE_API_BASE_URL` | Backend API URL | `http://localhost:8000` |

## Pre-deployment command checklist

```bash
# 1. Run all backend tests
cd backend && python3 -m pytest --tb=short -q

# 2. Frontend typecheck
cd frontend && npx tsc -b --noEmit

# 3. Frontend build
cd frontend && npm run build

# 4. SDK tests
cd sdk/python && python3 -m pytest -q

# 5. Run migrations (local SQLite)
cd backend && alembic upgrade head

# 6. Seed demo data
curl -s -X POST http://localhost:8000/api/admin/seed-demo | python3 -m json.tool

# 7. Refresh reliability snapshots for demo strategies
# (use demo strategy IDs after seeding)

# 8. Check deployment readiness
curl -s http://localhost:8000/api/admin/deployment-readiness | python3 -m json.tool
```

## Secrets checklist (before public deployment)
- [ ] No `.env` files committed to git
- [ ] No API keys in committed code
- [ ] Use Render/Vercel environment variable settings for secrets
- [ ] Rotate any exposed local/demo API keys
- [ ] Verify git history with `git log --all -- .env` to check for accidental commits

## CORS configuration (M68)
In production, set `ALLOWED_ORIGINS` or configure `CORSMiddleware` in `backend/app/main.py` to allow only the deployed frontend domain.

## Next milestones
| Milestone | Description |
|-----------|-------------|
| M66 | Backend deployment prep — Render service, PostgreSQL, migrations, health checks |
| M67 | Frontend deployment prep — Vercel project, env vars, domain |
| M68 | Production auth/CORS/rate-limit hardening |
| M69 | Public demo QA — seed production demo, validate all pages |
| M70 | Landing page and demo narrative |

---
*QuantFidelity deployment readiness documentation. Updated by M65.*
