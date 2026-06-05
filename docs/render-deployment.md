# Render Deployment — Required Environment Variables

This document lists every environment variable that **must be set** on Render before
the QuantFidelity backend will start in production. Missing or incorrect values cause
a hard startup failure with a clear error message in the Render deploy logs.

---

## Critical — set these before first deploy

### `QF_ENVIRONMENT`
```
QF_ENVIRONMENT=production
```
Activates production safety checks (startup guards, RBAC enforcement, 401 on
unauthenticated requests, deployment health warnings). Without this the app runs
in permissive local-dev mode.

---

### `QF_DATABASE_URL`
```
QF_DATABASE_URL=postgresql://user:password@host:port/database
```
The Render Postgres **Internal Database URL** (copy from Render dashboard → your
Postgres instance → "Internal Database URL"). Render provides `postgres://` URLs —
the app normalises these to `postgresql://` automatically.

**Why this is critical:** The default is SQLite (`sqlite:///./quantfidelity.db`).
Render's filesystem is **ephemeral**: it is wiped on every deploy. If you use SQLite
in production, every user account, strategy, and piece of evidence is permanently
destroyed on every deployment. The app now **refuses to start** in production with a
SQLite URL and prints this message:

```
[QuantFidelity] Production startup blocked — 1 configuration error(s) must be fixed:
  1. QF_DATABASE_URL is SQLite, which uses Render's ephemeral filesystem. ...
```

---

### `QF_JWT_SECRET_KEY`
```
QF_JWT_SECRET_KEY=<generate with: openssl rand -hex 32>
```
A long random string used to sign and verify JWT tokens. The default is the insecure
dev value `dev-secret-key-change-in-production-do-not-commit`. Anyone who knows this
string can forge tokens and impersonate any user. The app now **refuses to start** in
production with the dev default:

```
[QuantFidelity] Production startup blocked — 1 configuration error(s) must be fixed:
  1. QF_JWT_SECRET_KEY is the insecure dev default. ...
```

Generate a strong secret:
```bash
openssl rand -hex 32
# or
python3 -c "import secrets; print(secrets.token_hex(32))"
```

⚠️ **After rotating the JWT secret**, all existing login sessions (tokens) are
immediately invalidated. Users must log in again. No data is deleted — user accounts
and workspace memberships are stored in the database and are unaffected.

---

### `QF_FRONTEND_URL`
```
QF_FRONTEND_URL=https://quantfidelity.vercel.app
```
The Vercel frontend origin. This is automatically added to the CORS allowed-origins
list. Without it, every browser request from the frontend is CORS-blocked (the
API returns no `Access-Control-Allow-Origin` header).

---

## Recommended — set for a clean production config

### `QF_DEBUG`
```
QF_DEBUG=false
```
Suppresses debug output and disables the FastAPI interactive docs in production.

### `QF_CORS_ORIGINS`
```
QF_CORS_ORIGINS=https://quantfidelity.vercel.app
```
If you have multiple frontend origins, list them comma-separated. `QF_FRONTEND_URL`
adds one URL automatically; `QF_CORS_ORIGINS` replaces the full list (including the
localhost defaults). For most deployments, setting `QF_FRONTEND_URL` alone is enough.

### `QF_REQUIRE_API_KEY_FOR_INGESTION`
```
QF_REQUIRE_API_KEY_FOR_INGESTION=true
```
When `true`, the SDK evidence-bundle ingest endpoint requires a valid API key.
When `false` (the default), any authenticated member can ingest. Enable once you
have issued API keys via the Developer → API Keys page.

---

## Verify the deployment

After setting all variables and deploying, check:

```
GET https://quantfidelity-api.onrender.com/api/health/deployment
```

A healthy production response should show:
```json
{
  "environment": "production",
  "database_driver": "postgresql",
  "database_configured": true,
  "database_persistent_safe": true,
  "database_reachable": true,
  "jwt_secret_safe": true,
  "auth_enabled": true,
  "rbac_enabled": true,
  "cors_configured": true,
  "production_warnings": []
}
```

Any warnings in `production_warnings` describe remaining configuration issues.
Both `database_persistent_safe` and `jwt_secret_safe` must be `true` before
serving real users.

---

## Why accounts disappeared (root cause)

1. **SQLite on Render's ephemeral disk.** The early deployment used the default
   SQLite database, which is written to Render's local filesystem. Render's
   filesytem is stateless: it is reset on every deploy (scale event, restart, or
   new version). Every account, strategy, and piece of evidence stored in SQLite
   was permanently destroyed each time the service restarted.

2. **No startup guard.** The app did not previously fail-fast when `QF_DATABASE_URL`
   was missing. It silently fell back to SQLite, so the problem was invisible until
   data disappeared.

Both root causes are now fixed:
- The app **refuses to start** in production with SQLite or the dev JWT secret.
- `database_persistent_safe` in the health endpoint makes the current state visible.

---

## Running `alembic upgrade head` on Render

After the first deploy with `QF_DATABASE_URL` set, run migrations via the Render
shell or a one-off job:

```bash
# From the Render shell (cd to backend directory)
alembic upgrade head
```

Or add it to the Render start command:
```
cd backend && alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

The app does **not** auto-migrate on startup — run migrations explicitly before or
after deployment.
