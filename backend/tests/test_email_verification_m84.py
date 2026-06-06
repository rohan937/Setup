"""M84 email-verification + password-reset + verified-email gating tests.

These exercise the full M84 surface end-to-end against an in-memory SQLite
database using the StaticPool TestClient pattern from
``tests/test_session_persistence_m83.py``.

KEY techniques
--------------
* Only token *hashes* are stored. To drive ``verify-email`` / ``reset-password``
  we generate the RAW token directly in the test via
  ``create_email_token(db, user, token_type, hours)`` (it returns the raw token)
  and then post it to the endpoint.
* To test EXPIRY we create a token, then directly rewind the stored
  ``AuthEmailToken.expires_at`` to the past and flush, then call the endpoint
  and expect 400.
* The console email provider is the default; no network is touched in tests.

All fixtures are prefixed ``m84_`` to avoid colliding with ``conftest.py``'s
session-scoped ``seed_data(db)`` fixture.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  (register all models on Base.metadata)
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.auth_email_token import AuthEmailToken
from app.models.auth_user import AuthUser
from app.models.organization import Organization
from app.models.project import Project
from app.models.strategy import Strategy
from app.services.email_tokens import create_email_token

_URL = "sqlite+pysqlite:///:memory:"


# ---------------------------------------------------------------------------
# Fixtures (all m84_ prefixed)
# ---------------------------------------------------------------------------

@pytest.fixture()
def m84_engine():
    eng = create_engine(
        _URL, connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture()
def m84_db(m84_engine):
    s = Session(m84_engine)
    yield s
    s.close()


@pytest.fixture()
def m84_client(m84_db):
    def _override():
        yield m84_db

    prior = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = _override
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    if prior is not None:
        app.dependency_overrides[get_db] = prior
    else:
        app.dependency_overrides.pop(get_db, None)


def _register(client, email="m84@test.com", password="password123", display_name="M84"):
    r = client.post(
        "/api/auth/register",
        json={"email": email, "display_name": display_name, "password": password},
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _user_by_email(db: Session, email: str) -> AuthUser:
    user = db.query(AuthUser).filter(AuthUser.email == email).first()
    assert user is not None, f"no user for {email}"
    return user


@pytest.fixture()
def m84_registered(m84_client, m84_db):
    """Register an unverified user; return (token, email, AuthUser)."""
    email = "m84@test.com"
    token = _register(m84_client, email=email)
    user = _user_by_email(m84_db, email)
    return token, email, user


# ---------------------------------------------------------------------------
# Registration -> unverified user + verification token row
# ---------------------------------------------------------------------------

def test_registration_creates_unverified_user(m84_client, m84_db):
    _register(m84_client, email="unverified@test.com")
    user = _user_by_email(m84_db, "unverified@test.com")
    assert user.email_verified is False
    assert user.email_verified_at is None


def test_registration_creates_email_verification_token(m84_client, m84_db):
    _register(m84_client, email="tokenrow@test.com")
    user = _user_by_email(m84_db, "tokenrow@test.com")
    tokens = (
        m84_db.query(AuthEmailToken)
        .filter(
            AuthEmailToken.user_id == str(user.id),
            AuthEmailToken.token_type == "email_verification",
        )
        .all()
    )
    assert len(tokens) == 1
    assert tokens[0].used_at is None


# ---------------------------------------------------------------------------
# verify-email
# ---------------------------------------------------------------------------

def test_valid_verification_token_verifies_user(m84_client, m84_db, m84_registered):
    _, email, user = m84_registered
    raw = create_email_token(m84_db, user, "email_verification", 48)
    m84_db.commit()

    r = m84_client.post("/api/auth/verify-email", json={"token": raw})
    assert r.status_code == 200, r.text

    m84_db.expire_all()
    refreshed = _user_by_email(m84_db, email)
    assert refreshed.email_verified is True
    assert refreshed.email_verified_at is not None


def test_expired_verification_token_returns_400(m84_client, m84_db, m84_registered):
    _, _, user = m84_registered
    raw = create_email_token(m84_db, user, "email_verification", 48)
    # Rewind the stored token's expiry into the past.
    row = (
        m84_db.query(AuthEmailToken)
        .filter(
            AuthEmailToken.user_id == str(user.id),
            AuthEmailToken.token_type == "email_verification",
            AuthEmailToken.used_at.is_(None),
        )
        .order_by(AuthEmailToken.created_at.desc())
        .first()
    )
    row.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    m84_db.flush()
    m84_db.commit()

    r = m84_client.post("/api/auth/verify-email", json={"token": raw})
    assert r.status_code == 400, r.text


def test_invalid_verification_token_returns_400(m84_client, m84_registered):
    r = m84_client.post(
        "/api/auth/verify-email", json={"token": "garbage-not-a-real-token"}
    )
    assert r.status_code == 400, r.text


def test_verification_token_is_single_use(m84_client, m84_db, m84_registered):
    _, _, user = m84_registered
    raw = create_email_token(m84_db, user, "email_verification", 48)
    m84_db.commit()

    first = m84_client.post("/api/auth/verify-email", json={"token": raw})
    assert first.status_code == 200, first.text

    second = m84_client.post("/api/auth/verify-email", json={"token": raw})
    assert second.status_code == 400, second.text


# ---------------------------------------------------------------------------
# resend-verification
# ---------------------------------------------------------------------------

def test_resend_verification_for_unverified_user(m84_client, m84_registered):
    token, _, _ = m84_registered
    r = m84_client.post(
        "/api/auth/resend-verification",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    assert "sent" in r.json()["message"].lower()


def test_resend_verification_for_verified_user_is_safe_noop(
    m84_client, m84_db, m84_registered
):
    token, email, user = m84_registered
    # Verify the user first.
    raw = create_email_token(m84_db, user, "email_verification", 48)
    m84_db.commit()
    assert (
        m84_client.post("/api/auth/verify-email", json={"token": raw}).status_code
        == 200
    )

    r = m84_client.post(
        "/api/auth/resend-verification",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    assert "already verified" in r.json()["message"].lower()


# ---------------------------------------------------------------------------
# forgot-password (no existence leak)
# ---------------------------------------------------------------------------

def test_forgot_password_same_message_for_known_and_unknown_email(
    m84_client, m84_registered
):
    _, email, _ = m84_registered

    known = m84_client.post("/api/auth/forgot-password", json={"email": email})
    unknown = m84_client.post(
        "/api/auth/forgot-password", json={"email": "nobody-here@test.com"}
    )

    assert known.status_code == 200, known.text
    assert unknown.status_code == 200, unknown.text
    assert known.json()["message"] == unknown.json()["message"]


# ---------------------------------------------------------------------------
# reset-password
# ---------------------------------------------------------------------------

def test_reset_password_with_valid_token_allows_login_with_new_password(
    m84_client, m84_db, m84_registered
):
    _, email, user = m84_registered
    raw = create_email_token(m84_db, user, "password_reset", 2)
    m84_db.commit()

    r = m84_client.post(
        "/api/auth/reset-password",
        json={"token": raw, "new_password": "brandnewpass1"},
    )
    assert r.status_code == 200, r.text

    login = m84_client.post(
        "/api/auth/login", json={"email": email, "password": "brandnewpass1"}
    )
    assert login.status_code == 200, login.text


def test_reset_password_invalidates_old_password(m84_client, m84_db, m84_registered):
    _, email, user = m84_registered
    raw = create_email_token(m84_db, user, "password_reset", 2)
    m84_db.commit()

    assert (
        m84_client.post(
            "/api/auth/reset-password",
            json={"token": raw, "new_password": "brandnewpass1"},
        ).status_code
        == 200
    )

    old_login = m84_client.post(
        "/api/auth/login", json={"email": email, "password": "password123"}
    )
    assert old_login.status_code == 401, old_login.text


def test_reset_password_with_weak_password_returns_422(
    m84_client, m84_db, m84_registered
):
    _, _, user = m84_registered
    raw = create_email_token(m84_db, user, "password_reset", 2)
    m84_db.commit()

    r = m84_client.post(
        "/api/auth/reset-password",
        json={"token": raw, "new_password": "short"},
    )
    assert r.status_code == 422, r.text


# ---------------------------------------------------------------------------
# change-password
# ---------------------------------------------------------------------------

def test_change_password_with_correct_current_password(m84_client, m84_registered):
    token, email, _ = m84_registered
    r = m84_client.post(
        "/api/auth/change-password",
        headers={"Authorization": f"Bearer {token}"},
        json={"current_password": "password123", "new_password": "changedpass1"},
    )
    assert r.status_code == 200, r.text

    login = m84_client.post(
        "/api/auth/login", json={"email": email, "password": "changedpass1"}
    )
    assert login.status_code == 200, login.text


def test_change_password_with_wrong_current_password_returns_400(
    m84_client, m84_registered
):
    token, _, _ = m84_registered
    r = m84_client.post(
        "/api/auth/change-password",
        headers={"Authorization": f"Bearer {token}"},
        json={"current_password": "wrongcurrent", "new_password": "changedpass1"},
    )
    assert r.status_code == 400, r.text


# ---------------------------------------------------------------------------
# Verified-email gating
# ---------------------------------------------------------------------------

def test_unverified_user_blocked_from_api_key_creation(m84_client, m84_registered):
    token, _, _ = m84_registered
    r = m84_client.post(
        "/api/api-keys",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "k1", "scopes": ["evidence:write"]},
    )
    assert r.status_code == 403, r.text
    assert r.json()["detail"] == "Email verification required."


def _make_strategy(db: Session) -> str:
    """Create an org/project/strategy and return the strategy id (str)."""
    now = datetime.now(timezone.utc)
    org = db.query(Organization).order_by(Organization.created_at).first()
    assert org is not None, "registration should have created the default org"
    project = Project(
        organization_id=org.id if isinstance(org.id, str) else str(org.id),
        name="P1",
        slug="p1",
        created_at=now,
        updated_at=now,
    )
    db.add(project)
    db.flush()
    strat = Strategy(
        project_id=str(project.id),
        name="S1",
        slug="s1",
        created_at=now,
        updated_at=now,
    )
    db.add(strat)
    db.flush()
    db.commit()
    return str(strat.id)


def test_unverified_user_blocked_from_evidence_ingestion(
    m84_client, m84_db, m84_registered
):
    token, _, _ = m84_registered
    strategy_id = _make_strategy(m84_db)
    r = m84_client.post(
        f"/api/strategies/{strategy_id}/evidence-bundles",
        headers={"Authorization": f"Bearer {token}"},
        json={"strategy_version": {"version_label": "v1"}},
    )
    assert r.status_code == 403, r.text


def test_verified_user_can_create_api_key(m84_client, m84_db, m84_registered):
    token, _, user = m84_registered
    # Verify the user first.
    raw = create_email_token(m84_db, user, "email_verification", 48)
    m84_db.commit()
    assert (
        m84_client.post("/api/auth/verify-email", json={"token": raw}).status_code
        == 200
    )

    r = m84_client.post(
        "/api/api-keys",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "verified-key", "scopes": ["evidence:write"]},
    )
    assert r.status_code == 201, r.text
    assert r.json()["raw_key"]


# ---------------------------------------------------------------------------
# Invite-only registration guard
# ---------------------------------------------------------------------------

def test_invite_only_registration_blocks_public_signup(m84_client, monkeypatch):
    from app.core import config as cfg

    monkeypatch.setenv("QF_INVITE_ONLY_REGISTRATION", "true")
    cfg.get_settings.cache_clear()
    try:
        r = m84_client.post(
            "/api/auth/register",
            json={
                "email": "inviteonly@test.com",
                "display_name": "IO",
                "password": "password123",
            },
        )
        assert r.status_code == 403, r.text
    finally:
        cfg.get_settings.cache_clear()
