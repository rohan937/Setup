"""Smoke tests for the M1 foundation endpoints."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["service"] == "QuantFidelity"


def test_api_root():
    resp = client.get("/api")
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "QuantFidelity"
    assert body["api_version"].startswith("/api")
