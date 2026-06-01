"""Tests for QuantFidelityClient (sdk/python/quantfidelity/client.py).

Uses the ``responses`` library to mock HTTP calls so no server is required.
"""
from __future__ import annotations

import json

import pytest
import responses as responses_lib

from quantfidelity import EvidenceBundle, QuantFidelityClient
from quantfidelity.exceptions import QuantFidelityAPIError, QuantFidelityConnectionError

BASE_URL = "http://localhost:8000"
STRATEGY_ID = "00000000-0000-0000-0000-000000000001"
INGEST_URL = f"{BASE_URL}/api/strategies/{STRATEGY_ID}/evidence-bundles"
EXAMPLE_URL = f"{BASE_URL}/api/strategies/{STRATEGY_ID}/evidence-bundles/example"
HEALTH_URL = f"{BASE_URL}/health"
API_URL = f"{BASE_URL}/api"

_MINIMAL_RESPONSE = {
    "strategy_id": STRATEGY_ID,
    "created_count": 1,
    "reused_count": 0,
    "actions_run": [],
    "objects": {
        "strategy_run": {
            "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            "name": "backtest-q1",
            "type": "strategy_run",
            "status": "created",
        }
    },
    "alerts_generated": 0,
    "warnings": [],
    "summary": "Evidence bundle ingested for strategy.",
    "timeline_events_created": 1,
    "generated_at": "2024-01-01T00:00:00Z",
}


# ---------------------------------------------------------------------------
# Client construction
# ---------------------------------------------------------------------------


def test_client_stores_base_url():
    client = QuantFidelityClient(base_url=BASE_URL)
    assert client._base_url == BASE_URL


def test_client_strips_trailing_slash():
    client = QuantFidelityClient(base_url="http://localhost:8000/")
    assert client._base_url == "http://localhost:8000"


def test_client_default_timeout():
    client = QuantFidelityClient()
    assert client._timeout == 30


def test_client_custom_timeout():
    client = QuantFidelityClient(timeout=60)
    assert client._timeout == 60


def test_client_api_key_stored():
    client = QuantFidelityClient(api_key="test-key")
    assert client._api_key == "test-key"


def test_client_api_key_none_by_default():
    client = QuantFidelityClient()
    assert client._api_key is None


def test_client_repr_no_key():
    client = QuantFidelityClient(base_url=BASE_URL)
    r = repr(client)
    assert BASE_URL in r
    assert "api_key=None" in r


def test_client_repr_with_key():
    client = QuantFidelityClient(base_url=BASE_URL, api_key="secret")
    r = repr(client)
    assert "api_key=***" in r
    assert "secret" not in r


# ---------------------------------------------------------------------------
# ingest_evidence_bundle — success paths
# ---------------------------------------------------------------------------


@responses_lib.activate
def test_ingest_with_bundle_object_succeeds():
    responses_lib.add(
        responses_lib.POST,
        INGEST_URL,
        json=_MINIMAL_RESPONSE,
        status=200,
    )
    client = QuantFidelityClient(base_url=BASE_URL)
    bundle = EvidenceBundle().with_strategy_run("backtest-q1", run_type="backtest")
    result = client.ingest_evidence_bundle(STRATEGY_ID, bundle)
    assert result["created_count"] == 1
    assert result["summary"] == "Evidence bundle ingested for strategy."


@responses_lib.activate
def test_ingest_with_plain_dict_succeeds():
    responses_lib.add(
        responses_lib.POST,
        INGEST_URL,
        json=_MINIMAL_RESPONSE,
        status=200,
    )
    client = QuantFidelityClient(base_url=BASE_URL)
    payload = {"strategy_run": {"run_name": "bt", "run_type": "backtest"}}
    result = client.ingest_evidence_bundle(STRATEGY_ID, payload)
    assert result["strategy_id"] == STRATEGY_ID


@responses_lib.activate
def test_ingest_sends_correct_url():
    responses_lib.add(
        responses_lib.POST,
        INGEST_URL,
        json=_MINIMAL_RESPONSE,
        status=200,
    )
    client = QuantFidelityClient(base_url=BASE_URL)
    client.ingest_evidence_bundle(STRATEGY_ID, {})
    assert responses_lib.calls[0].request.url == INGEST_URL


@responses_lib.activate
def test_ingest_sends_json_content_type():
    responses_lib.add(
        responses_lib.POST,
        INGEST_URL,
        json=_MINIMAL_RESPONSE,
        status=200,
    )
    client = QuantFidelityClient(base_url=BASE_URL)
    client.ingest_evidence_bundle(STRATEGY_ID, {})
    assert responses_lib.calls[0].request.headers["Content-Type"] == "application/json"


@responses_lib.activate
def test_ingest_empty_bundle_sends_empty_object():
    responses_lib.add(
        responses_lib.POST,
        INGEST_URL,
        json=_MINIMAL_RESPONSE,
        status=200,
    )
    client = QuantFidelityClient(base_url=BASE_URL)
    client.ingest_evidence_bundle(STRATEGY_ID, EvidenceBundle())
    sent = json.loads(responses_lib.calls[0].request.body)
    assert sent == {}


# ---------------------------------------------------------------------------
# ingest_evidence_bundle — error paths
# ---------------------------------------------------------------------------


@responses_lib.activate
def test_ingest_400_raises_api_error():
    responses_lib.add(
        responses_lib.POST,
        INGEST_URL,
        json={"detail": "Strategy not found"},
        status=400,
    )
    client = QuantFidelityClient(base_url=BASE_URL)
    with pytest.raises(QuantFidelityAPIError) as exc_info:
        client.ingest_evidence_bundle(STRATEGY_ID, {})
    assert exc_info.value.status_code == 400
    assert "Strategy not found" in str(exc_info.value)


@responses_lib.activate
def test_ingest_404_raises_api_error():
    responses_lib.add(
        responses_lib.POST,
        INGEST_URL,
        json={"detail": "not found"},
        status=404,
    )
    client = QuantFidelityClient(base_url=BASE_URL)
    with pytest.raises(QuantFidelityAPIError) as exc_info:
        client.ingest_evidence_bundle(STRATEGY_ID, {})
    assert exc_info.value.status_code == 404


@responses_lib.activate
def test_ingest_422_raises_api_error_with_detail():
    responses_lib.add(
        responses_lib.POST,
        INGEST_URL,
        json={"detail": [{"loc": ["body", "strategy_run", "run_name"], "msg": "field required"}]},
        status=422,
    )
    client = QuantFidelityClient(base_url=BASE_URL)
    with pytest.raises(QuantFidelityAPIError) as exc_info:
        client.ingest_evidence_bundle(STRATEGY_ID, {})
    assert exc_info.value.status_code == 422


@responses_lib.activate
def test_ingest_500_raises_api_error():
    responses_lib.add(
        responses_lib.POST,
        INGEST_URL,
        body="Internal Server Error",
        status=500,
    )
    client = QuantFidelityClient(base_url=BASE_URL)
    with pytest.raises(QuantFidelityAPIError) as exc_info:
        client.ingest_evidence_bundle(STRATEGY_ID, {})
    assert exc_info.value.status_code == 500


def test_ingest_connection_error_raises_connection_error():
    """Patch requests to raise a ConnectionError."""
    import unittest.mock as mock

    client = QuantFidelityClient(base_url="http://does-not-exist:9999")
    import requests as req

    with mock.patch.object(
        req,
        "post",
        side_effect=req.exceptions.ConnectionError("refused"),
    ):
        with pytest.raises(QuantFidelityConnectionError):
            client.ingest_evidence_bundle(STRATEGY_ID, {})


# ---------------------------------------------------------------------------
# get_evidence_bundle_example
# ---------------------------------------------------------------------------


@responses_lib.activate
def test_get_example_returns_dict():
    example_payload = {
        "strategy_run": {"run_name": "example-run", "run_type": "backtest"}
    }
    responses_lib.add(
        responses_lib.GET,
        EXAMPLE_URL,
        json=example_payload,
        status=200,
    )
    client = QuantFidelityClient(base_url=BASE_URL)
    result = client.get_evidence_bundle_example(STRATEGY_ID)
    assert result["strategy_run"]["run_name"] == "example-run"


@responses_lib.activate
def test_get_example_404_raises_api_error():
    responses_lib.add(
        responses_lib.GET,
        EXAMPLE_URL,
        json={"detail": "Strategy not found"},
        status=404,
    )
    client = QuantFidelityClient(base_url=BASE_URL)
    with pytest.raises(QuantFidelityAPIError) as exc_info:
        client.get_evidence_bundle_example(STRATEGY_ID)
    assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# health and api_root
# ---------------------------------------------------------------------------


@responses_lib.activate
def test_health_returns_ok():
    responses_lib.add(
        responses_lib.GET,
        HEALTH_URL,
        json={"status": "ok"},
        status=200,
    )
    client = QuantFidelityClient(base_url=BASE_URL)
    result = client.health()
    assert result["status"] == "ok"


@responses_lib.activate
def test_api_root_returns_metadata():
    responses_lib.add(
        responses_lib.GET,
        API_URL,
        json={"name": "QuantFidelity API", "version": "0.1.0"},
        status=200,
    )
    client = QuantFidelityClient(base_url=BASE_URL)
    result = client.api_root()
    assert "name" in result


# ---------------------------------------------------------------------------
# API error details
# ---------------------------------------------------------------------------


def test_api_error_stores_status_code():
    from quantfidelity.exceptions import QuantFidelityAPIError

    err = QuantFidelityAPIError(404, "not found")
    assert err.status_code == 404


def test_api_error_string_detail():
    from quantfidelity.exceptions import QuantFidelityAPIError

    err = QuantFidelityAPIError(400, "bad request", {"detail": "bad input"})
    assert "bad input" in str(err)


def test_api_error_list_detail():
    from quantfidelity.exceptions import QuantFidelityAPIError

    err = QuantFidelityAPIError(
        422,
        "unprocessable",
        {"detail": [{"msg": "field required"}, {"msg": "invalid value"}]},
    )
    assert "field required" in str(err)
    assert "invalid value" in str(err)


# ---------------------------------------------------------------------------
# M24: API key activation tests
# ---------------------------------------------------------------------------


def test_api_key_sent_as_authorization_bearer():
    """When api_key is provided, Authorization header is set."""
    client = QuantFidelityClient(base_url=BASE_URL, api_key="qf_local_testkey")
    headers = client._headers()
    assert "Authorization" in headers
    assert headers["Authorization"] == "Bearer qf_local_testkey"


def test_no_api_key_no_auth_header():
    """When api_key is None, no Authorization header is sent."""
    client = QuantFidelityClient(base_url=BASE_URL)
    headers = client._headers()
    assert "Authorization" not in headers


@responses_lib.activate
def test_ingest_sends_auth_header_when_key_set():
    """API key is sent in Authorization header during ingest."""
    responses_lib.add(responses_lib.POST, INGEST_URL, json=_MINIMAL_RESPONSE, status=200)
    client = QuantFidelityClient(base_url=BASE_URL, api_key="qf_local_testkey123")
    client.ingest_evidence_bundle(STRATEGY_ID, {})
    assert responses_lib.calls[0].request.headers.get("Authorization") == "Bearer qf_local_testkey123"


@responses_lib.activate
def test_ingest_no_auth_header_when_no_key():
    """No Authorization header when api_key is None."""
    responses_lib.add(responses_lib.POST, INGEST_URL, json=_MINIMAL_RESPONSE, status=200)
    client = QuantFidelityClient(base_url=BASE_URL)
    client.ingest_evidence_bundle(STRATEGY_ID, {})
    assert "Authorization" not in responses_lib.calls[0].request.headers


@responses_lib.activate
def test_401_raises_api_error():
    """401 response raises QuantFidelityAPIError."""
    responses_lib.add(
        responses_lib.POST,
        INGEST_URL,
        json={"detail": "Valid API key required."},
        status=401,
    )
    client = QuantFidelityClient(base_url=BASE_URL)
    with pytest.raises(QuantFidelityAPIError) as exc_info:
        client.ingest_evidence_bundle(STRATEGY_ID, {})
    assert exc_info.value.status_code == 401


def test_api_key_not_in_repr():
    """API key is masked in repr."""
    client = QuantFidelityClient(base_url=BASE_URL, api_key="secret123")
    assert "secret123" not in repr(client)


def test_api_key_not_in_exception_message():
    """API key is never included in exception messages."""
    import unittest.mock as mock
    import requests as req

    client = QuantFidelityClient(base_url=BASE_URL, api_key="super_secret_key")
    with mock.patch.object(req, "post", side_effect=req.exceptions.ConnectionError("refused")):
        try:
            client.ingest_evidence_bundle(STRATEGY_ID, {})
        except Exception as e:
            assert "super_secret_key" not in str(e)
