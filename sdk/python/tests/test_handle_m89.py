"""M89 tests: StrategyHandle, module-level init/strategy helpers, exception types,
env-var configuration, and API key security.

Uses the ``responses`` library to mock HTTP calls so no server is required.
"""
from __future__ import annotations

import os
import unittest.mock as mock

import pytest
import responses as responses_lib

import quantfidelity as qf
from quantfidelity import (
    EvidenceBundle,
    QuantFidelityClient,
    QuantFidelityAPIError,
    QuantFidelityAuthError,
    QuantFidelityNotFoundError,
)
from quantfidelity.handle import StrategyHandle

BASE_URL = "http://test:8000"
STRATEGY_UUID = "00000000-0000-0000-0000-000000000042"
STRATEGIES_URL = f"{BASE_URL}/api/strategies"
STRATEGY_URL = f"{BASE_URL}/api/strategies/{STRATEGY_UUID}"
INGEST_URL = f"{BASE_URL}/api/strategies/{STRATEGY_UUID}/evidence-bundles"
REPORTS_URL = f"{BASE_URL}/api/reports/strategy/{STRATEGY_UUID}"
RELIABILITY_URL = f"{BASE_URL}/api/strategies/{STRATEGY_UUID}/reliability-score"
SHADOW_URL = f"{BASE_URL}/api/strategies/{STRATEGY_UUID}/shadow-monitor/refresh"

_MINIMAL_INGEST_RESPONSE = {
    "strategy_id": STRATEGY_UUID,
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
    "summary": "Evidence bundle ingested.",
    "timeline_events_created": 1,
    "generated_at": "2024-01-01T00:00:00Z",
}

_STRATEGY_LIST = [
    {"id": STRATEGY_UUID, "slug": "spy-trend", "name": "SPY Trend"},
]


# ────────────────────────────────────────────────────────────────────────────
# TestModuleInit
# ────────────────────────────────────────────────────────────────────────────


class TestModuleInit:
    def setup_method(self):
        """Reset module-level default client before each test."""
        qf._default_client = None

    def teardown_method(self):
        """Clean up env vars and reset client."""
        qf._default_client = None
        for var in ("QF_BASE_URL", "QUANTFIDELITY_BASE_URL", "QF_API_KEY", "QUANTFIDELITY_API_KEY"):
            os.environ.pop(var, None)

    def test_init_returns_client(self):
        result = qf.init(BASE_URL)
        assert isinstance(result, QuantFidelityClient)

    def test_init_sets_default_client(self):
        qf.init(BASE_URL)
        assert qf._default_client is not None

    def test_strategy_returns_handle(self):
        qf.init(BASE_URL)
        handle = qf.strategy("spy-trend")
        assert isinstance(handle, StrategyHandle)

    def test_strategy_without_init_uses_env(self):
        os.environ["QF_BASE_URL"] = BASE_URL
        handle = qf.strategy("spy-trend")
        assert isinstance(handle, StrategyHandle)

    def test_init_reads_qf_api_key(self):
        os.environ["QF_API_KEY"] = "qf_test_key_123"
        client = qf.init(BASE_URL)
        assert client._api_key == "qf_test_key_123"

    def test_init_reads_quantfidelity_api_key(self):
        os.environ["QUANTFIDELITY_API_KEY"] = "qf_prod_key_456"
        client = qf.init(BASE_URL)
        assert client._api_key == "qf_prod_key_456"


# ────────────────────────────────────────────────────────────────────────────
# TestClientEnvVars
# ────────────────────────────────────────────────────────────────────────────


class TestClientEnvVars:
    def teardown_method(self):
        for var in ("QF_BASE_URL", "QUANTFIDELITY_BASE_URL", "QF_API_KEY", "QUANTFIDELITY_API_KEY"):
            os.environ.pop(var, None)

    def test_default_base_url_is_localhost(self):
        # Remove any env vars that could override the default
        os.environ.pop("QF_BASE_URL", None)
        os.environ.pop("QUANTFIDELITY_BASE_URL", None)
        client = QuantFidelityClient()
        assert "localhost:8000" in client._base_url

    def test_reads_qf_base_url(self):
        os.environ["QF_BASE_URL"] = "http://qf-server:9000"
        client = QuantFidelityClient()
        assert client._base_url == "http://qf-server:9000"

    def test_reads_quantfidelity_base_url(self):
        os.environ["QUANTFIDELITY_BASE_URL"] = "http://prod-server:8080"
        client = QuantFidelityClient()
        assert client._base_url == "http://prod-server:8080"

    def test_reads_qf_api_key(self):
        os.environ["QF_API_KEY"] = "qf_env_key_789"
        client = QuantFidelityClient()
        assert client._api_key == "qf_env_key_789"

    def test_explicit_args_override_env(self):
        os.environ["QF_BASE_URL"] = "http://env-server:9000"
        client = QuantFidelityClient(base_url="http://explicit-server:7000")
        assert client._base_url == "http://explicit-server:7000"


# ────────────────────────────────────────────────────────────────────────────
# TestExceptionTypes
# ────────────────────────────────────────────────────────────────────────────


class TestExceptionTypes:
    @responses_lib.activate
    def test_auth_error_on_401(self):
        responses_lib.add(
            responses_lib.GET,
            STRATEGIES_URL,
            json={"detail": "Unauthorized"},
            status=401,
        )
        client = QuantFidelityClient(base_url=BASE_URL)
        with pytest.raises(QuantFidelityAuthError):
            client.list_strategies()

    @responses_lib.activate
    def test_auth_error_on_403(self):
        responses_lib.add(
            responses_lib.GET,
            STRATEGIES_URL,
            json={"detail": "Forbidden"},
            status=403,
        )
        client = QuantFidelityClient(base_url=BASE_URL)
        with pytest.raises(QuantFidelityAuthError):
            client.list_strategies()

    @responses_lib.activate
    def test_not_found_on_404(self):
        responses_lib.add(
            responses_lib.GET,
            f"{BASE_URL}/api/strategies/bad-id",
            json={"detail": "Not found"},
            status=404,
        )
        client = QuantFidelityClient(base_url=BASE_URL)
        with pytest.raises(QuantFidelityNotFoundError):
            client.get_strategy("bad-id")

    def test_auth_error_is_api_error(self):
        assert issubclass(QuantFidelityAuthError, QuantFidelityAPIError)

    def test_not_found_is_api_error(self):
        assert issubclass(QuantFidelityNotFoundError, QuantFidelityAPIError)

    @responses_lib.activate
    def test_no_api_key_in_exception_message(self):
        responses_lib.add(
            responses_lib.GET,
            STRATEGIES_URL,
            json={"detail": "Unauthorized"},
            status=401,
        )
        api_key = "super_secret_qf_key"
        client = QuantFidelityClient(base_url=BASE_URL, api_key=api_key)
        with pytest.raises(QuantFidelityAuthError) as exc_info:
            client.list_strategies()
        assert api_key not in str(exc_info.value)


# ────────────────────────────────────────────────────────────────────────────
# TestStrategyHandle
# ────────────────────────────────────────────────────────────────────────────


class TestStrategyHandle:
    def _make_client(self):
        return QuantFidelityClient(base_url=BASE_URL)

    def test_handle_repr(self):
        client = self._make_client()
        handle = StrategyHandle(client, "spy-trend")
        r = repr(handle)
        assert "spy-trend" in r

    def test_handle_uuid_resolves_directly(self):
        client = self._make_client()
        handle = StrategyHandle(client, STRATEGY_UUID)
        # Should not need to call list_strategies — resolves directly
        resolved = handle._resolve()
        assert resolved == STRATEGY_UUID

    @responses_lib.activate
    def test_handle_slug_resolves_via_list(self):
        responses_lib.add(
            responses_lib.GET,
            STRATEGIES_URL,
            json=_STRATEGY_LIST,
            status=200,
        )
        client = self._make_client()
        handle = StrategyHandle(client, "spy-trend")
        resolved = handle._resolve()
        assert resolved == STRATEGY_UUID

    @responses_lib.activate
    def test_handle_slug_not_found_raises(self):
        responses_lib.add(
            responses_lib.GET,
            STRATEGIES_URL,
            json=[],
            status=200,
        )
        client = self._make_client()
        handle = StrategyHandle(client, "nonexistent-slug")
        with pytest.raises(QuantFidelityNotFoundError):
            handle._resolve()

    @responses_lib.activate
    def test_log_run_ingests_bundle(self):
        responses_lib.add(
            responses_lib.POST,
            INGEST_URL,
            json=_MINIMAL_INGEST_RESPONSE,
            status=200,
        )
        client = self._make_client()
        handle = StrategyHandle(client, STRATEGY_UUID)
        result = handle.log_run("backtest-q1", metrics={"sharpe": 1.4})
        assert result["created_count"] == 1

    @responses_lib.activate
    def test_log_run_uses_backtest_run_type(self):
        import json as _json
        responses_lib.add(
            responses_lib.POST,
            INGEST_URL,
            json=_MINIMAL_INGEST_RESPONSE,
            status=200,
        )
        client = self._make_client()
        handle = StrategyHandle(client, STRATEGY_UUID)
        handle.log_run("backtest-q1")
        sent = _json.loads(responses_lib.calls[0].request.body)
        assert sent["strategy_run"]["run_type"] == "backtest"

    @responses_lib.activate
    def test_log_paper_run_uses_paper_type(self):
        import json as _json
        responses_lib.add(
            responses_lib.POST,
            INGEST_URL,
            json=_MINIMAL_INGEST_RESPONSE,
            status=200,
        )
        client = self._make_client()
        handle = StrategyHandle(client, STRATEGY_UUID)
        handle.log_paper_run("paper-run-q1")
        sent = _json.loads(responses_lib.calls[0].request.body)
        assert sent["strategy_run"]["run_type"] == "paper"

    @responses_lib.activate
    def test_log_dataset_builds_correct_bundle(self):
        import json as _json
        responses_lib.add(
            responses_lib.POST,
            INGEST_URL,
            json=_MINIMAL_INGEST_RESPONSE,
            status=200,
        )
        client = self._make_client()
        handle = StrategyHandle(client, STRATEGY_UUID)
        handle.log_dataset("SP500 OHLCV")
        sent = _json.loads(responses_lib.calls[0].request.body)
        assert "dataset" in sent

    @responses_lib.activate
    def test_log_signal_builds_signal_section(self):
        import json as _json
        responses_lib.add(
            responses_lib.POST,
            INGEST_URL,
            json=_MINIMAL_INGEST_RESPONSE,
            status=200,
        )
        client = self._make_client()
        handle = StrategyHandle(client, STRATEGY_UUID)
        rows = [{"symbol": "AAPL", "timestamp": "2024-01-01", "signal": 1.0}]
        handle.log_signal("return_zscore", rows=rows)
        sent = _json.loads(responses_lib.calls[0].request.body)
        assert "signal_snapshot" in sent

    @responses_lib.activate
    def test_log_config_builds_config_section(self):
        import json as _json
        responses_lib.add(
            responses_lib.POST,
            INGEST_URL,
            json=_MINIMAL_INGEST_RESPONSE,
            status=200,
        )
        client = self._make_client()
        handle = StrategyHandle(client, STRATEGY_UUID)
        handle.log_config("config-v1", params={"lookback": 20})
        sent = _json.loads(responses_lib.calls[0].request.body)
        assert "config_snapshot" in sent

    @responses_lib.activate
    def test_log_universe_builds_universe_section(self):
        import json as _json
        responses_lib.add(
            responses_lib.POST,
            INGEST_URL,
            json=_MINIMAL_INGEST_RESPONSE,
            status=200,
        )
        client = self._make_client()
        handle = StrategyHandle(client, STRATEGY_UUID)
        handle.log_universe("sp500-2024", symbols=["AAPL", "MSFT", "GOOG"])
        sent = _json.loads(responses_lib.calls[0].request.body)
        assert "universe_snapshot" in sent

    @responses_lib.activate
    def test_generate_report_calls_reports_endpoint(self):
        responses_lib.add(
            responses_lib.POST,
            REPORTS_URL,
            json={"report_id": "rpt-001", "status": "generated"},
            status=200,
        )
        client = self._make_client()
        handle = StrategyHandle(client, STRATEGY_UUID)
        result = handle.generate_report()
        assert result["report_id"] == "rpt-001"
        assert responses_lib.calls[0].request.url == REPORTS_URL

    @responses_lib.activate
    def test_refresh_score_calls_reliability_endpoint(self):
        responses_lib.add(
            responses_lib.POST,
            RELIABILITY_URL,
            json={"score": 87.5, "status": "computed"},
            status=200,
        )
        client = self._make_client()
        handle = StrategyHandle(client, STRATEGY_UUID)
        result = handle.refresh_score()
        assert result["score"] == 87.5
        assert responses_lib.calls[0].request.url == RELIABILITY_URL

    @responses_lib.activate
    def test_shadow_monitor_calls_shadow_endpoint(self):
        responses_lib.add(
            responses_lib.POST,
            SHADOW_URL,
            json={"drift_detected": False, "status": "ok"},
            status=200,
        )
        client = self._make_client()
        handle = StrategyHandle(client, STRATEGY_UUID)
        result = handle.shadow_monitor()
        assert result["drift_detected"] is False
        assert responses_lib.calls[0].request.url == SHADOW_URL


# ────────────────────────────────────────────────────────────────────────────
# TestBundlePaperRunAlias
# ────────────────────────────────────────────────────────────────────────────


class TestBundlePaperRunAlias:
    def test_with_paper_run_sets_run_type(self):
        b = EvidenceBundle().with_paper_run("paper-run-001", metrics={})
        d = b.to_dict()
        assert d["strategy_run"]["run_type"] == "paper"

    def test_with_paper_run_metrics(self):
        metrics = {"sharpe": 0.9, "max_drawdown": -0.08}
        b = EvidenceBundle().with_paper_run("paper-run-001", metrics=metrics)
        d = b.to_dict()
        assert d["strategy_run"]["metrics_json"] == metrics


# ────────────────────────────────────────────────────────────────────────────
# TestApiKeySecurityInSDK
# ────────────────────────────────────────────────────────────────────────────


class TestApiKeySecurityInSDK:
    def test_client_repr_hides_key(self):
        client = QuantFidelityClient(api_key="qf_secret")
        r = repr(client)
        assert "qf_secret" not in r
        assert "***" in r

    @responses_lib.activate
    def test_exception_str_does_not_contain_key(self):
        api_key = "qf_very_secret_key_do_not_leak"
        responses_lib.add(
            responses_lib.GET,
            STRATEGIES_URL,
            json={"detail": "Unauthorized"},
            status=401,
        )
        client = QuantFidelityClient(base_url=BASE_URL, api_key=api_key)
        with pytest.raises(QuantFidelityAuthError) as exc_info:
            client.list_strategies()
        assert api_key not in str(exc_info.value)
