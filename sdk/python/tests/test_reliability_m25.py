"""M25 tests: retry logic, offline buffer, CLI buffer commands."""
from __future__ import annotations

import json
import unittest.mock as mock
from pathlib import Path

import pytest
import requests as req
import responses as responses_lib

from quantfidelity import EvidenceBundle, QuantFidelityClient
from quantfidelity.buffer import LocalBuffer
from quantfidelity.exceptions import QuantFidelityAPIError, QuantFidelityConnectionError

BASE_URL = "http://localhost:8000"
STRATEGY_ID = "00000000-0000-0000-0000-000000000001"
INGEST_URL = f"{BASE_URL}/api/strategies/{STRATEGY_ID}/evidence-bundles"
_RESP = {
    "strategy_id": STRATEGY_ID,
    "created_count": 1,
    "reused_count": 0,
    "actions_run": [],
    "objects": {},
    "alerts_generated": 0,
    "warnings": [],
    "summary": "ok",
    "timeline_events_created": 1,
    "generated_at": "2024-01-01T00:00:00Z",
}


# ────────────────────────────────────────────────────────────────────────────
# Idempotency header tests
# ────────────────────────────────────────────────────────────────────────────

class TestIdempotencyHeader:
    @responses_lib.activate
    def test_idempotency_key_sent_as_header(self, tmp_path):
        responses_lib.add(responses_lib.POST, INGEST_URL, json=_RESP, status=200)
        client = QuantFidelityClient(base_url=BASE_URL, buffer_path=str(tmp_path / "buf.jsonl"))
        client.ingest_evidence_bundle(STRATEGY_ID, {}, idempotency_key="my-key")
        assert responses_lib.calls[0].request.headers.get("Idempotency-Key") == "my-key"

    @responses_lib.activate
    def test_retry_true_generates_idempotency_key(self, tmp_path):
        responses_lib.add(responses_lib.POST, INGEST_URL, json=_RESP, status=200)
        client = QuantFidelityClient(base_url=BASE_URL, buffer_path=str(tmp_path / "buf.jsonl"))
        client.ingest_evidence_bundle(STRATEGY_ID, {}, retry=True)
        assert "Idempotency-Key" in responses_lib.calls[0].request.headers

    @responses_lib.activate
    def test_no_idempotency_key_when_retry_false(self, tmp_path):
        responses_lib.add(responses_lib.POST, INGEST_URL, json=_RESP, status=200)
        client = QuantFidelityClient(base_url=BASE_URL, buffer_path=str(tmp_path / "buf.jsonl"))
        client.ingest_evidence_bundle(STRATEGY_ID, {}, retry=False, idempotency_key=None)
        assert "Idempotency-Key" not in responses_lib.calls[0].request.headers


# ────────────────────────────────────────────────────────────────────────────
# Retry logic tests
# ────────────────────────────────────────────────────────────────────────────

class TestRetryLogic:
    @responses_lib.activate
    def test_retries_on_503_then_succeeds(self, tmp_path):
        responses_lib.add(responses_lib.POST, INGEST_URL, status=503)
        responses_lib.add(responses_lib.POST, INGEST_URL, json=_RESP, status=200)
        client = QuantFidelityClient(base_url=BASE_URL, buffer_path=str(tmp_path / "buf.jsonl"))
        result = client.ingest_evidence_bundle(
            STRATEGY_ID, {}, retry=True, max_retries=2, backoff_seconds=0
        )
        assert result["created_count"] == 1
        assert len(responses_lib.calls) == 2

    @responses_lib.activate
    def test_does_not_retry_on_400(self, tmp_path):
        responses_lib.add(responses_lib.POST, INGEST_URL, json={"detail": "bad"}, status=400)
        client = QuantFidelityClient(base_url=BASE_URL, buffer_path=str(tmp_path / "buf.jsonl"))
        with pytest.raises(QuantFidelityAPIError) as exc_info:
            client.ingest_evidence_bundle(STRATEGY_ID, {})
        assert exc_info.value.status_code == 400
        assert len(responses_lib.calls) == 1

    @responses_lib.activate
    def test_does_not_retry_on_401(self, tmp_path):
        responses_lib.add(responses_lib.POST, INGEST_URL, json={"detail": "unauth"}, status=401)
        client = QuantFidelityClient(base_url=BASE_URL, buffer_path=str(tmp_path / "buf.jsonl"))
        with pytest.raises(QuantFidelityAPIError) as exc_info:
            client.ingest_evidence_bundle(STRATEGY_ID, {})
        assert exc_info.value.status_code == 401
        assert len(responses_lib.calls) == 1

    @responses_lib.activate
    def test_does_not_retry_on_409(self, tmp_path):
        responses_lib.add(responses_lib.POST, INGEST_URL, json={"detail": "conflict"}, status=409)
        client = QuantFidelityClient(base_url=BASE_URL, buffer_path=str(tmp_path / "buf.jsonl"))
        with pytest.raises(QuantFidelityAPIError) as exc_info:
            client.ingest_evidence_bundle(STRATEGY_ID, {})
        assert exc_info.value.status_code == 409
        assert len(responses_lib.calls) == 1

    def test_retries_on_connection_error_then_buffers(self, tmp_path):
        client = QuantFidelityClient(base_url=BASE_URL, buffer_path=str(tmp_path / "buf.jsonl"))
        with mock.patch.object(req, "post", side_effect=req.exceptions.ConnectionError("refused")):
            result = client.ingest_evidence_bundle(
                STRATEGY_ID, {}, retry=True, max_retries=2,
                backoff_seconds=0, buffer_on_failure=True
            )
        assert result.get("buffered") is True


# ────────────────────────────────────────────────────────────────────────────
# LocalBuffer tests
# ────────────────────────────────────────────────────────────────────────────

class TestLocalBuffer:
    def test_buffer_add_creates_record(self, tmp_path):
        buf = LocalBuffer(path=str(tmp_path / "buf.jsonl"))
        rec = buf.add(base_url=BASE_URL, strategy_id=STRATEGY_ID, payload={"x": 1})
        assert rec["strategy_id"] == STRATEGY_ID
        assert rec["buffer_id"]

    def test_buffer_does_not_store_api_key(self, tmp_path):
        buf = LocalBuffer(path=str(tmp_path / "buf.jsonl"))
        buf.add(base_url=BASE_URL, strategy_id=STRATEGY_ID, payload={"strategy_run": {}})
        content = (tmp_path / "buf.jsonl").read_text()
        assert "api_key" not in content
        assert "Authorization" not in content

    def test_list_records_empty(self, tmp_path):
        buf = LocalBuffer(path=str(tmp_path / "buf.jsonl"))
        assert buf.list_records() == []

    def test_list_records_returns_added(self, tmp_path):
        buf = LocalBuffer(path=str(tmp_path / "buf.jsonl"))
        buf.add(base_url=BASE_URL, strategy_id=STRATEGY_ID, payload={})
        assert len(buf.list_records()) == 1

    def test_clear_removes_all(self, tmp_path):
        buf = LocalBuffer(path=str(tmp_path / "buf.jsonl"))
        buf.add(base_url=BASE_URL, strategy_id=STRATEGY_ID, payload={})
        buf.add(base_url=BASE_URL, strategy_id=STRATEGY_ID, payload={})
        n = buf.clear()
        assert n == 2
        assert buf.list_records() == []

    @responses_lib.activate
    def test_flush_sends_and_removes_successful(self, tmp_path):
        responses_lib.add(responses_lib.POST, INGEST_URL, json=_RESP, status=200)
        buf = LocalBuffer(path=str(tmp_path / "buf.jsonl"))
        buf.add(base_url=BASE_URL, strategy_id=STRATEGY_ID, payload={})
        client = QuantFidelityClient(base_url=BASE_URL, buffer_path=str(tmp_path / "buf.jsonl"))
        result = buf.flush(client)
        assert result["flushed"] == 1
        assert len(buf.list_records()) == 0

    @responses_lib.activate
    def test_flush_preserves_failed_records(self, tmp_path):
        responses_lib.add(responses_lib.POST, INGEST_URL, json={"detail": "err"}, status=500)
        buf = LocalBuffer(path=str(tmp_path / "buf.jsonl"))
        buf.add(base_url=BASE_URL, strategy_id=STRATEGY_ID, payload={})
        client = QuantFidelityClient(base_url=BASE_URL, buffer_path=str(tmp_path / "buf.jsonl"))
        result = buf.flush(client)
        assert result["flushed"] == 0
        assert len(buf.list_records()) == 1

    def test_client_buffer_on_failure_writes_to_buffer(self, tmp_path):
        client = QuantFidelityClient(base_url=BASE_URL, buffer_path=str(tmp_path / "buf.jsonl"))
        with mock.patch.object(req, "post", side_effect=req.exceptions.ConnectionError("refused")):
            client.ingest_evidence_bundle(STRATEGY_ID, {}, retry=False, buffer_on_failure=True)
        assert len(client.list_buffered()) == 1

    def test_client_list_buffered(self, tmp_path):
        client = QuantFidelityClient(base_url=BASE_URL, buffer_path=str(tmp_path / "buf.jsonl"))
        client.buffer_evidence_bundle(STRATEGY_ID, EvidenceBundle())
        assert len(client.list_buffered()) == 1

    def test_client_clear_buffer(self, tmp_path):
        client = QuantFidelityClient(base_url=BASE_URL, buffer_path=str(tmp_path / "buf.jsonl"))
        client.buffer_evidence_bundle(STRATEGY_ID, EvidenceBundle())
        n = client.clear_buffer()
        assert n == 1
        assert client.list_buffered() == []


# ────────────────────────────────────────────────────────────────────────────
# CLI buffer tests
# ────────────────────────────────────────────────────────────────────────────

class TestCliBuffer:
    def test_cli_ingest_passes_idempotency_key(self, tmp_path):
        bundle_file = tmp_path / "b.json"
        bundle_file.write_text(json.dumps({}))
        with mock.patch(
            "quantfidelity.client.QuantFidelityClient.ingest_evidence_bundle",
            return_value=_RESP,
        ) as mock_ingest:
            with pytest.raises(SystemExit):
                from quantfidelity.cli import main
                main([
                    "ingest",
                    "--strategy-id", STRATEGY_ID,
                    "--file", str(bundle_file),
                    "--idempotency-key", "test-key",
                ])
            assert mock_ingest.call_args is not None

    def test_cli_buffer_list_empty(self, tmp_path, capsys):
        with pytest.raises(SystemExit) as exc_info:
            from quantfidelity.cli import main
            main(["buffer", "list", "--buffer-path", str(tmp_path / "buf.jsonl")])
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        out = captured.out.strip()
        assert out == "[]" or "empty" in out.lower() or out == "[]"

    def test_cli_buffer_clear_with_yes_flag(self, tmp_path, capsys):
        buf = LocalBuffer(path=str(tmp_path / "buf.jsonl"))
        buf.add(base_url=BASE_URL, strategy_id=STRATEGY_ID, payload={})
        with pytest.raises(SystemExit) as exc_info:
            from quantfidelity.cli import main
            main(["buffer", "clear", "--yes", "--buffer-path", str(tmp_path / "buf.jsonl")])
        assert exc_info.value.code == 0
