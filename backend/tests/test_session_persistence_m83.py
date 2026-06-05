"""Tests for the auto-sign-out / session persistence fix (M83).

Root causes of the auto-sign-out bug:
  1. AuthContext.refreshCurrentUser() called clearAuthToken() in its catch block
     for ANY error, including transient 5xx responses and network failures
     (e.g. Render free-tier cold-start timeouts). After such an error the token
     was permanently removed — the user appeared signed out even though their
     token was still valid.
  2. The default token lifetime was 1440 minutes (24 hours). Users who returned
     after more than a day were silently signed out.

Fixes:
  1. Frontend: refreshCurrentUser() now only clears the token on HTTP 401.
     Any other error (5xx, network failure) is swallowed and the session is
     preserved. An "authMessage" state tells the Login page to show a
     "Session expired" banner when sign-out is genuine.
  2. Frontend: HttpError class added to api.ts so callers can check the
     HTTP status code in catch blocks.
  3. Backend config: access_token_expire_minutes default raised from 1440 (24 h)
     to 10080 (7 days). Configurable via QF_ACCESS_TOKEN_EXPIRE_MINUTES.

Backend tests here cover:
  - Token generation includes correct expiry claim.
  - /api/auth/me succeeds with a valid token.
  - /api/auth/me returns 401 for an expired token.
  - /api/auth/me returns 401 for a tampered/invalid token.
  - Changing the JWT secret invalidates the token but leaves the user row intact.
  - New default token lifetime is 7 days.
  - 401 vs 500 distinction: backend sends correct status codes.

Fixtures prefixed m83_ to avoid conftest session-scope collisions.
"""
from __future__ import annotations

import time
import uuid

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app

_URL = "sqlite+pysqlite:///:memory:"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def m83_engine():
    eng = create_engine(_URL, connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture()
def m83_db(m83_engine):
    s = Session(m83_engine)
    yield s
    s.close()


@pytest.fixture()
def m83_client(m83_db):
    def _override():
        yield m83_db
    prior = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = _override
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    if prior is not None:
        app.dependency_overrides[get_db] = prior
    else:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture()
def m83_user(m83_client):
    """Register a user and return (token, email)."""
    r = m83_client.post(
        "/api/auth/register",
        json={"email": "m83@test.com", "display_name": "M83", "password": "password123"},
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"], "m83@test.com"


# ---------------------------------------------------------------------------
# 1. Token lifetime
# ---------------------------------------------------------------------------

class TestTokenLifetime:
    def test_new_default_token_lifetime_is_7_days(self):
        """The default access_token_expire_minutes should be 7 days (10080)."""
        settings = get_settings()
        assert settings.access_token_expire_minutes == 10080, (
            f"Expected 10080 (7 days), got {settings.access_token_expire_minutes}. "
            "Check that the default was updated from 1440 (24 h) to 10080 (7 days) "
            "in app/core/config.py."
        )

    def test_login_token_has_exp_claim(self, m83_client, m83_user):
        token, _ = m83_user
        settings = get_settings()
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        assert "exp" in payload, "JWT must contain an 'exp' claim"

    def test_login_token_expiry_matches_config(self, m83_client, m83_user):
        """The token's exp claim should be approximately now + configured lifetime."""
        import datetime

        token, _ = m83_user
        settings = get_settings()
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        issued_roughly = time.time()
        expected_exp = issued_roughly + settings.access_token_expire_minutes * 60
        actual_exp = payload["exp"]
        # Allow ±60 s of clock skew / test execution time.
        assert abs(actual_exp - expected_exp) < 60, (
            f"Token exp={actual_exp}, expected ~{expected_exp} "
            f"(now + {settings.access_token_expire_minutes} min)"
        )

    def test_login_token_has_sub_and_email(self, m83_client, m83_user):
        token, email = m83_user
        settings = get_settings()
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        assert payload.get("sub"), "JWT must have a 'sub' field"
        assert payload.get("email") == email, "JWT must include the user email"
        assert payload.get("type") == "access", "JWT must have type='access'"


# ---------------------------------------------------------------------------
# 2. /api/auth/me — valid token
# ---------------------------------------------------------------------------

class TestMeEndpoint:
    def test_me_with_valid_token_returns_200(self, m83_client, m83_user):
        token, email = m83_user
        r = m83_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200, r.text
        assert r.json()["user"]["email"] == email

    def test_me_without_token_returns_401(self, m83_client):
        r = m83_client.get("/api/auth/me")
        assert r.status_code == 401, r.text

    def test_me_with_garbage_token_returns_401(self, m83_client):
        r = m83_client.get(
            "/api/auth/me", headers={"Authorization": "Bearer not-a-real-token"}
        )
        assert r.status_code == 401, r.text


# ---------------------------------------------------------------------------
# 3. Expired token returns 401
# ---------------------------------------------------------------------------

class TestExpiredToken:
    def test_expired_token_returns_401(self, m83_client, m83_user):
        """A token with exp in the past must be rejected with 401, not 500."""
        from app.core.security import create_access_token

        token_exp = create_access_token(
            user_id=str(uuid.uuid4()),
            email="expired@test.com",
            expires_minutes=-1,  # already expired
        )
        r = m83_client.get(
            "/api/auth/me", headers={"Authorization": f"Bearer {token_exp}"}
        )
        assert r.status_code == 401, (
            f"Expected 401 for an expired token, got {r.status_code}: {r.text}"
        )

    def test_token_signed_with_wrong_secret_returns_401(self, m83_client, m83_user):
        """A token signed with a different secret must be rejected with 401."""
        import datetime as dt
        exp = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=7)
        bad_token = jwt.encode(
            {"sub": "someuser", "email": "x@x.com", "exp": exp, "type": "access"},
            "wrong-secret",
            algorithm="HS256",
        )
        r = m83_client.get(
            "/api/auth/me", headers={"Authorization": f"Bearer {bad_token}"}
        )
        assert r.status_code == 401, (
            f"Expected 401 for tampered token, got {r.status_code}: {r.text}"
        )


# ---------------------------------------------------------------------------
# 4. Secret rotation: token invalidated but account survives
# ---------------------------------------------------------------------------

class TestSecretRotation:
    def test_old_token_invalid_after_secret_change_but_user_survives(
        self, m83_client, m83_db, monkeypatch
    ):
        """Changing the JWT secret invalidates tokens but NOT user accounts.

        This simulates what happens if an operator rotates QF_JWT_SECRET_KEY
        on Render. The existing session token becomes invalid → 401, but the
        user row is still in the DB and a new login succeeds.
        """
        from app.core import config as cfg

        # Register user with the current (dev) secret.
        r = m83_client.post(
            "/api/auth/register",
            json={"email": "rotation@test.com", "display_name": "R", "password": "password123"},
        )
        old_token = r.json()["access_token"]

        # Simulate secret rotation: patch config to return new secret.
        monkeypatch.setenv("QF_JWT_SECRET_KEY", "brand-new-secret-" + str(uuid.uuid4().hex))
        cfg.get_settings.cache_clear()
        try:
            # Old token → 401 (signed with old secret)
            r401 = m83_client.get(
                "/api/auth/me", headers={"Authorization": f"Bearer {old_token}"}
            )
            assert r401.status_code == 401, (
                f"Expected 401 after secret rotation, got {r401.status_code}"
            )

            # User account still exists — a fresh login succeeds.
            login_r = m83_client.post(
                "/api/auth/login",
                json={"email": "rotation@test.com", "password": "password123"},
            )
            assert login_r.status_code == 200, (
                f"Login after secret rotation failed: {login_r.text}"
            )
            new_token = login_r.json()["access_token"]

            # New token → 200
            me_r = m83_client.get(
                "/api/auth/me", headers={"Authorization": f"Bearer {new_token}"}
            )
            assert me_r.status_code == 200, me_r.text
        finally:
            cfg.get_settings.cache_clear()


# ---------------------------------------------------------------------------
# 5. Login / register return tokens (smoke tests)
# ---------------------------------------------------------------------------

class TestAuthSmoke:
    def test_login_returns_token(self, m83_client, m83_user):
        _, email = m83_user
        r = m83_client.post(
            "/api/auth/login",
            json={"email": email, "password": "password123"},
        )
        assert r.status_code == 200, r.text
        assert "access_token" in r.json()

    def test_wrong_password_returns_401(self, m83_client, m83_user):
        _, email = m83_user
        r = m83_client.post(
            "/api/auth/login",
            json={"email": email, "password": "wrongpassword"},
        )
        assert r.status_code == 401

    def test_register_returns_token(self, m83_client):
        r = m83_client.post(
            "/api/auth/register",
            json={"email": "newuser@test.com", "display_name": "N", "password": "password123"},
        )
        assert r.status_code == 200, r.text
        assert "access_token" in r.json()

    def test_me_returns_correct_user_after_login(self, m83_client, m83_user):
        token, email = m83_user
        r = m83_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        body = r.json()
        assert body["user"]["email"] == email
        assert body["role"] is not None  # owner of default workspace
