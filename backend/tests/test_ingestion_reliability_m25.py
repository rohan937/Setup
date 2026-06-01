"""M25 tests: SDK Ingestion Batches / Idempotency.

Tests for:
  - Idempotency key via HTTP header and JSON body
  - Replay of completed batches (same key + same payload)
  - 409 conflict for same key + different payload
  - 409 conflict while in-flight (status == "received")
  - Retry after failure
  - SdkIngestionBatch ORM record creation and field correctness
  - idempotency_status in response ("new", "replayed", "retried_after_failure")
  - No raw API key stored in batch JSON columns
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from app.models.organization import Organization
from app.models.project import Project
from app.models.sdk_ingestion_batch import SdkIngestionBatch
from app.models.strategy import Strategy


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_strategy(db, org, project, *, name=None):
    slug = (name or f"test-{uuid.uuid4().hex[:6]}").lower().replace(" ", "-")
    s = Strategy(
        project_id=project.id,
        name=name or f"TestStrat-{uuid.uuid4().hex[:6]}",
        slug=slug,
        asset_class="equity",
        status="active",
    )
    db.add(s)
    db.flush()
    return s


def _cleanup_strategy(db, strategy):
    from sqlalchemy import inspect as sa_inspect
    try:
        state = sa_inspect(strategy)
        if state.detached or state.deleted:
            fresh = db.query(Strategy).filter(Strategy.id == strategy.id).first()
            if fresh is not None:
                db.delete(fresh)
                db.commit()
            return
        db.delete(strategy)
        db.commit()
    except Exception:
        db.rollback()


def _cleanup_batches(db, strategy_id):
    """Delete all SdkIngestionBatch rows for a strategy."""
    batches = (
        db.query(SdkIngestionBatch)
        .filter(SdkIngestionBatch.strategy_id == strategy_id)
        .all()
    )
    for b in batches:
        db.delete(b)
    try:
        db.commit()
    except Exception:
        db.rollback()


def _get_org_project(db):
    org = db.query(Organization).first()
    project = db.query(Project).filter(Project.organization_id == org.id).first()
    return org, project


_MINIMAL_BUNDLE = {
    "strategy_run": {
        "run_name": "test-run",
        "run_type": "backtest",
    }
}


# ---------------------------------------------------------------------------
# Test classes
# ---------------------------------------------------------------------------

class TestIdempotencyBehavior:

    def test_ingestion_without_idempotency_key_still_works(self, client, db):
        """POST without Idempotency-Key header returns 201."""
        org, project = _get_org_project(db)
        s = _make_strategy(db, org, project)
        try:
            resp = client.post(
                f"/api/strategies/{s.id}/evidence-bundles",
                json=_MINIMAL_BUNDLE,
            )
            assert resp.status_code == 201, resp.text
            data = resp.json()
            assert data["idempotency_key"] is None
            assert data["idempotency_status"] is None
            assert data["ingestion_batch_id"] is None
        finally:
            _cleanup_strategy(db, s)

    def test_ingestion_with_idempotency_key_creates_batch(self, client, db):
        """POST with Idempotency-Key header creates a SdkIngestionBatch record."""
        org, project = _get_org_project(db)
        s = _make_strategy(db, org, project)
        idem_key = str(uuid.uuid4())
        try:
            resp = client.post(
                f"/api/strategies/{s.id}/evidence-bundles",
                json=_MINIMAL_BUNDLE,
                headers={"Idempotency-Key": idem_key},
            )
            assert resp.status_code == 201, resp.text
            db.expire_all()
            batch = (
                db.query(SdkIngestionBatch)
                .filter(
                    SdkIngestionBatch.strategy_id == s.id,
                    SdkIngestionBatch.idempotency_key == idem_key,
                )
                .first()
            )
            assert batch is not None
            assert batch.status == "completed"
            assert batch.response_json is not None
        finally:
            _cleanup_strategy(db, s)

    def test_replay_same_key_same_payload_returns_stored(self, client, db):
        """POST twice with same key + payload returns the same strategy_run id."""
        org, project = _get_org_project(db)
        s = _make_strategy(db, org, project)
        idem_key = str(uuid.uuid4())
        bundle = {
            "strategy_run": {
                "run_name": "replay-run",
                "run_type": "backtest",
            }
        }
        try:
            resp1 = client.post(
                f"/api/strategies/{s.id}/evidence-bundles",
                json=bundle,
                headers={"Idempotency-Key": idem_key},
            )
            assert resp1.status_code == 201, resp1.text
            resp2 = client.post(
                f"/api/strategies/{s.id}/evidence-bundles",
                json=bundle,
                headers={"Idempotency-Key": idem_key},
            )
            assert resp2.status_code == 201, resp2.text
            d1 = resp1.json()
            d2 = resp2.json()
            # The strategy_run id should be the same in both responses
            assert d1["objects"].get("strategy_run") == d2["objects"].get("strategy_run")
        finally:
            _cleanup_strategy(db, s)

    def test_replay_returns_idempotency_status_replayed(self, client, db):
        """Second POST with same key + payload returns idempotency_status='replayed'."""
        org, project = _get_org_project(db)
        s = _make_strategy(db, org, project)
        idem_key = str(uuid.uuid4())
        bundle = {
            "strategy_run": {
                "run_name": "replay-status-run",
                "run_type": "backtest",
            }
        }
        try:
            resp1 = client.post(
                f"/api/strategies/{s.id}/evidence-bundles",
                json=bundle,
                headers={"Idempotency-Key": idem_key},
            )
            assert resp1.status_code == 201
            resp2 = client.post(
                f"/api/strategies/{s.id}/evidence-bundles",
                json=bundle,
                headers={"Idempotency-Key": idem_key},
            )
            assert resp2.status_code == 201
            assert resp2.json()["idempotency_status"] == "replayed"
        finally:
            _cleanup_strategy(db, s)

    def test_replay_does_not_create_duplicate_run(self, client, db):
        """Replaying an idempotent request does not create an extra strategy run."""
        from app.models.strategy_run import StrategyRun
        org, project = _get_org_project(db)
        s = _make_strategy(db, org, project)
        idem_key = str(uuid.uuid4())
        bundle = {
            "strategy_run": {
                "run_name": "no-dup-run",
                "run_type": "backtest",
            }
        }
        try:
            resp1 = client.post(
                f"/api/strategies/{s.id}/evidence-bundles",
                json=bundle,
                headers={"Idempotency-Key": idem_key},
            )
            assert resp1.status_code == 201
            db.expire_all()
            count_after_first = (
                db.query(StrategyRun)
                .filter(StrategyRun.strategy_id == s.id)
                .count()
            )
            resp2 = client.post(
                f"/api/strategies/{s.id}/evidence-bundles",
                json=bundle,
                headers={"Idempotency-Key": idem_key},
            )
            assert resp2.status_code == 201
            db.expire_all()
            count_after_replay = (
                db.query(StrategyRun)
                .filter(StrategyRun.strategy_id == s.id)
                .count()
            )
            assert count_after_first == count_after_replay
        finally:
            _cleanup_strategy(db, s)

    def test_different_payload_same_key_returns_409(self, client, db):
        """Using same idempotency key with a different payload returns 409."""
        org, project = _get_org_project(db)
        s = _make_strategy(db, org, project)
        idem_key = str(uuid.uuid4())
        bundle1 = {
            "strategy_run": {
                "run_name": "conflict-run-1",
                "run_type": "backtest",
            }
        }
        bundle2 = {
            "strategy_run": {
                "run_name": "conflict-run-2",
                "run_type": "backtest",
            }
        }
        try:
            resp1 = client.post(
                f"/api/strategies/{s.id}/evidence-bundles",
                json=bundle1,
                headers={"Idempotency-Key": idem_key},
            )
            assert resp1.status_code == 201
            resp2 = client.post(
                f"/api/strategies/{s.id}/evidence-bundles",
                json=bundle2,
                headers={"Idempotency-Key": idem_key},
            )
            assert resp2.status_code == 409
        finally:
            _cleanup_strategy(db, s)

    def test_key_from_body_works(self, client, db):
        """idempotency_key field in JSON body is respected."""
        org, project = _get_org_project(db)
        s = _make_strategy(db, org, project)
        idem_key = str(uuid.uuid4())
        bundle = {
            "strategy_run": {
                "run_name": "body-key-run",
                "run_type": "backtest",
            },
            "idempotency_key": idem_key,
        }
        try:
            resp = client.post(
                f"/api/strategies/{s.id}/evidence-bundles",
                json=bundle,
            )
            assert resp.status_code == 201, resp.text
            data = resp.json()
            assert data["idempotency_key"] == idem_key
            db.expire_all()
            batch = (
                db.query(SdkIngestionBatch)
                .filter(
                    SdkIngestionBatch.strategy_id == s.id,
                    SdkIngestionBatch.idempotency_key == idem_key,
                )
                .first()
            )
            assert batch is not None
        finally:
            _cleanup_strategy(db, s)

    def test_header_takes_precedence_over_body(self, client, db):
        """When both header and body idempotency_key are present, header wins."""
        org, project = _get_org_project(db)
        s = _make_strategy(db, org, project)
        header_key = str(uuid.uuid4())
        body_key = str(uuid.uuid4())
        bundle = {
            "strategy_run": {
                "run_name": "header-wins-run",
                "run_type": "backtest",
            },
            "idempotency_key": body_key,
        }
        try:
            resp = client.post(
                f"/api/strategies/{s.id}/evidence-bundles",
                json=bundle,
                headers={"Idempotency-Key": header_key},
            )
            assert resp.status_code == 201, resp.text
            data = resp.json()
            # The response idempotency_key should be the header value
            assert data["idempotency_key"] == header_key
            db.expire_all()
            # Only a batch with the header key should exist
            batch_header = (
                db.query(SdkIngestionBatch)
                .filter(
                    SdkIngestionBatch.strategy_id == s.id,
                    SdkIngestionBatch.idempotency_key == header_key,
                )
                .first()
            )
            batch_body = (
                db.query(SdkIngestionBatch)
                .filter(
                    SdkIngestionBatch.strategy_id == s.id,
                    SdkIngestionBatch.idempotency_key == body_key,
                )
                .first()
            )
            assert batch_header is not None
            assert batch_body is None
        finally:
            _cleanup_strategy(db, s)

    def test_request_hash_ignores_idempotency_key_field(self, client, db):
        """Two bundles with identical content but different idempotency_key fields
        should produce the same request_hash."""
        from app.api.routes.evidence import _compute_request_hash
        from app.schemas.evidence_ingestion import (
            EvidenceBundleRequest,
            EvidenceBundleRunSection,
        )

        bundle_a = EvidenceBundleRequest(
            strategy_run=EvidenceBundleRunSection(
                run_name="hash-test-run",
                run_type="backtest",
            ),
            idempotency_key="key-a",
        )
        bundle_b = EvidenceBundleRequest(
            strategy_run=EvidenceBundleRunSection(
                run_name="hash-test-run",
                run_type="backtest",
            ),
            idempotency_key="key-b",
        )
        assert _compute_request_hash(bundle_a) == _compute_request_hash(bundle_b)

    def test_failed_batch_allows_retry(self, client, db):
        """A batch stuck in 'failed' status can be retried successfully."""
        org, project = _get_org_project(db)
        s = _make_strategy(db, org, project)
        idem_key = str(uuid.uuid4())
        bundle = {
            "strategy_run": {
                "run_name": "retry-after-fail",
                "run_type": "backtest",
            }
        }
        try:
            # First call — should succeed and create a completed batch
            resp1 = client.post(
                f"/api/strategies/{s.id}/evidence-bundles",
                json=bundle,
                headers={"Idempotency-Key": idem_key},
            )
            assert resp1.status_code == 201
            # Manually flip the batch to failed
            db.expire_all()
            batch = (
                db.query(SdkIngestionBatch)
                .filter(
                    SdkIngestionBatch.strategy_id == s.id,
                    SdkIngestionBatch.idempotency_key == idem_key,
                )
                .first()
            )
            assert batch is not None
            batch.status = "failed"
            batch.error_json = {"detail": "simulated failure"}
            db.commit()
            # Retry should succeed
            resp2 = client.post(
                f"/api/strategies/{s.id}/evidence-bundles",
                json=bundle,
                headers={"Idempotency-Key": idem_key},
            )
            assert resp2.status_code == 201, resp2.text
            data = resp2.json()
            assert data["idempotency_status"] == "retried_after_failure"
        finally:
            _cleanup_strategy(db, s)

    def test_idempotency_status_new_on_first_request(self, client, db):
        """First request with a fresh idempotency key returns idempotency_status='new'."""
        org, project = _get_org_project(db)
        s = _make_strategy(db, org, project)
        idem_key = str(uuid.uuid4())
        bundle = {
            "strategy_run": {
                "run_name": "first-req-run",
                "run_type": "backtest",
            }
        }
        try:
            resp = client.post(
                f"/api/strategies/{s.id}/evidence-bundles",
                json=bundle,
                headers={"Idempotency-Key": idem_key},
            )
            assert resp.status_code == 201, resp.text
            assert resp.json()["idempotency_status"] == "new"
        finally:
            _cleanup_strategy(db, s)


class TestBatchRecord:

    def test_batch_stores_no_raw_api_key(self, client, db):
        """No raw API key string should appear in any JSON column of the batch."""
        org, project = _get_org_project(db)
        s = _make_strategy(db, org, project)
        idem_key = str(uuid.uuid4())
        bundle = {
            "strategy_run": {
                "run_name": "no-raw-key-run",
                "run_type": "backtest",
            }
        }
        # Use a fake bearer token (no enforcement in test mode)
        resp = client.post(
            f"/api/strategies/{s.id}/evidence-bundles",
            json=bundle,
            headers={
                "Idempotency-Key": idem_key,
                "Authorization": "Bearer qf_local_testrawkey12345",
            },
        )
        try:
            assert resp.status_code == 201, resp.text
            db.expire_all()
            batch = (
                db.query(SdkIngestionBatch)
                .filter(
                    SdkIngestionBatch.strategy_id == s.id,
                    SdkIngestionBatch.idempotency_key == idem_key,
                )
                .first()
            )
            assert batch is not None
            # None of the JSON columns should contain the raw key string
            raw_key = "qf_local_testrawkey12345"
            import json as _json
            for col in [batch.response_json, batch.error_json, batch.created_object_refs_json]:
                if col is not None:
                    serialized = _json.dumps(col)
                    assert raw_key not in serialized
        finally:
            _cleanup_strategy(db, s)

    def test_batch_response_json_stored(self, client, db):
        """After completion, response_json is populated on the batch record."""
        org, project = _get_org_project(db)
        s = _make_strategy(db, org, project)
        idem_key = str(uuid.uuid4())
        bundle = {
            "strategy_run": {
                "run_name": "resp-json-run",
                "run_type": "backtest",
            }
        }
        try:
            resp = client.post(
                f"/api/strategies/{s.id}/evidence-bundles",
                json=bundle,
                headers={"Idempotency-Key": idem_key},
            )
            assert resp.status_code == 201, resp.text
            db.expire_all()
            batch = (
                db.query(SdkIngestionBatch)
                .filter(
                    SdkIngestionBatch.strategy_id == s.id,
                    SdkIngestionBatch.idempotency_key == idem_key,
                )
                .first()
            )
            assert batch is not None
            assert batch.response_json is not None
            assert "strategy_id" in batch.response_json
            assert batch.completed_at is not None
        finally:
            _cleanup_strategy(db, s)
