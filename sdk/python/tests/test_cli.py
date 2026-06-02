"""Tests for the QuantFidelity CLI (sdk/python/quantfidelity/cli.py).

Tests cover argument parsing, file reading, dry-run behavior, and the
integration between CLI commands and QuantFidelityClient using mocks.
No server is required.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest import mock

import pytest

from quantfidelity.cli import _build_parser, main


STRATEGY_ID = "00000000-0000-0000-0000-000000000001"

_MINIMAL_RESPONSE = {
    "strategy_id": STRATEGY_ID,
    "created_count": 1,
    "reused_count": 0,
    "actions_run": [],
    "objects": {},
    "alerts_generated": 0,
    "warnings": [],
    "summary": "Bundle ingested.",
    "timeline_events_created": 1,
    "generated_at": "2024-01-01T00:00:00Z",
}


# ---------------------------------------------------------------------------
# Parser unit tests
# ---------------------------------------------------------------------------


def test_parser_ingest_requires_strategy_id():
    parser = _build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["ingest", "--file", "bundle.json"])


def test_parser_ingest_requires_file():
    parser = _build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["ingest", "--strategy-id", STRATEGY_ID])


def test_parser_ingest_parses_correctly():
    parser = _build_parser()
    args = parser.parse_args(
        ["ingest", "--strategy-id", STRATEGY_ID, "--file", "bundle.json"]
    )
    assert args.strategy_id == STRATEGY_ID
    assert args.file == "bundle.json"
    assert args.dry_run is False


def test_parser_ingest_dry_run_flag():
    parser = _build_parser()
    args = parser.parse_args(
        ["ingest", "--strategy-id", STRATEGY_ID, "--file", "b.json", "--dry-run"]
    )
    assert args.dry_run is True


def test_parser_example_requires_strategy_id():
    parser = _build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["example"])


def test_parser_example_parses_correctly():
    parser = _build_parser()
    args = parser.parse_args(["example", "--strategy-id", STRATEGY_ID])
    assert args.strategy_id == STRATEGY_ID
    assert args.output is None


def test_parser_example_output_flag():
    parser = _build_parser()
    args = parser.parse_args(
        ["example", "--strategy-id", STRATEGY_ID, "--output", "out.json"]
    )
    assert args.output == "out.json"


def test_parser_health_no_args():
    parser = _build_parser()
    args = parser.parse_args(["health"])
    assert args.command == "health"


def test_parser_base_url_default():
    parser = _build_parser()
    args = parser.parse_args(["health"])
    assert args.base_url == "http://localhost:8000"


def test_parser_base_url_custom():
    parser = _build_parser()
    args = parser.parse_args(["--base-url", "http://qf.internal", "health"])
    assert args.base_url == "http://qf.internal"


def test_parser_api_key():
    parser = _build_parser()
    args = parser.parse_args(["--api-key", "test-key", "health"])
    assert args.api_key == "test-key"


def test_parser_no_command_exits():
    with pytest.raises(SystemExit):
        _build_parser().parse_args([])


# ---------------------------------------------------------------------------
# ingest command integration
# ---------------------------------------------------------------------------


def test_ingest_dry_run_prints_payload_no_http_call(
    tmp_path: Path, capsys: pytest.CaptureFixture
):
    bundle_file = tmp_path / "bundle.json"
    payload = {"strategy_run": {"run_name": "test", "run_type": "backtest"}}
    bundle_file.write_text(json.dumps(payload))

    with mock.patch("quantfidelity.client.QuantFidelityClient.ingest_evidence_bundle") as mock_ingest:
        with pytest.raises(SystemExit) as exc_info:
            main([
                "ingest",
                "--strategy-id", STRATEGY_ID,
                "--file", str(bundle_file),
                "--dry-run",
            ])
        assert exc_info.value.code == 0
        mock_ingest.assert_not_called()

    captured = capsys.readouterr()
    assert "Dry run" in captured.out
    assert '"run_name"' in captured.out


def test_ingest_file_not_found_exits_1(capsys: pytest.CaptureFixture):
    with pytest.raises(SystemExit) as exc_info:
        main([
            "ingest",
            "--strategy-id", STRATEGY_ID,
            "--file", "/nonexistent/bundle.json",
        ])
    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "not found" in captured.err.lower() or "error" in captured.err.lower()


def test_ingest_invalid_json_exits_1(tmp_path: Path, capsys: pytest.CaptureFixture):
    bad_file = tmp_path / "bad.json"
    bad_file.write_text("{not valid json}")

    with pytest.raises(SystemExit) as exc_info:
        main([
            "ingest",
            "--strategy-id", STRATEGY_ID,
            "--file", str(bad_file),
        ])
    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "json" in captured.err.lower() or "error" in captured.err.lower()


def test_ingest_success_prints_response(
    tmp_path: Path, capsys: pytest.CaptureFixture
):
    bundle_file = tmp_path / "bundle.json"
    bundle_file.write_text(json.dumps({"strategy_run": {"run_name": "bt", "run_type": "backtest"}}))

    with mock.patch(
        "quantfidelity.client.QuantFidelityClient.ingest_evidence_bundle",
        return_value=_MINIMAL_RESPONSE,
    ):
        with pytest.raises(SystemExit) as exc_info:
            main([
                "ingest",
                "--strategy-id", STRATEGY_ID,
                "--file", str(bundle_file),
                "--json",
            ])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert result["created_count"] == 1


def test_ingest_connection_error_exits_1(
    tmp_path: Path, capsys: pytest.CaptureFixture
):
    from quantfidelity.exceptions import QuantFidelityConnectionError

    bundle_file = tmp_path / "bundle.json"
    bundle_file.write_text(json.dumps({}))

    with mock.patch(
        "quantfidelity.client.QuantFidelityClient.ingest_evidence_bundle",
        side_effect=QuantFidelityConnectionError("connection refused"),
    ):
        with pytest.raises(SystemExit) as exc_info:
            main([
                "ingest",
                "--strategy-id", STRATEGY_ID,
                "--file", str(bundle_file),
            ])
    assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# example command integration
# ---------------------------------------------------------------------------


def test_example_prints_json(capsys: pytest.CaptureFixture):
    example_payload = {"strategy_run": {"run_name": "example", "run_type": "backtest"}}

    with mock.patch(
        "quantfidelity.client.QuantFidelityClient.get_evidence_bundle_example",
        return_value=example_payload,
    ):
        with pytest.raises(SystemExit) as exc_info:
            main(["example", "--strategy-id", STRATEGY_ID])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert parsed["strategy_run"]["run_name"] == "example"


def test_example_writes_output_file(tmp_path: Path, capsys: pytest.CaptureFixture):
    example_payload = {"strategy_run": {"run_name": "ex", "run_type": "backtest"}}
    out_file = tmp_path / "example_out.json"

    with mock.patch(
        "quantfidelity.client.QuantFidelityClient.get_evidence_bundle_example",
        return_value=example_payload,
    ):
        with pytest.raises(SystemExit) as exc_info:
            main([
                "example",
                "--strategy-id", STRATEGY_ID,
                "--output", str(out_file),
            ])
    assert exc_info.value.code == 0
    assert out_file.exists()
    written = json.loads(out_file.read_text())
    assert written["strategy_run"]["run_name"] == "ex"


def test_example_api_error_exits_1(capsys: pytest.CaptureFixture):
    from quantfidelity.exceptions import QuantFidelityAPIError

    with mock.patch(
        "quantfidelity.client.QuantFidelityClient.get_evidence_bundle_example",
        side_effect=QuantFidelityAPIError(404, "not found"),
    ):
        with pytest.raises(SystemExit) as exc_info:
            main(["example", "--strategy-id", STRATEGY_ID])
    assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# health command integration
# ---------------------------------------------------------------------------


def test_health_success_exits_0(capsys: pytest.CaptureFixture):
    with mock.patch(
        "quantfidelity.client.QuantFidelityClient.health",
        return_value={"status": "ok"},
    ):
        with pytest.raises(SystemExit) as exc_info:
            main(["health"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert result["status"] == "ok"


def test_health_connection_error_exits_1(capsys: pytest.CaptureFixture):
    from quantfidelity.exceptions import QuantFidelityConnectionError

    with mock.patch(
        "quantfidelity.client.QuantFidelityClient.health",
        side_effect=QuantFidelityConnectionError("refused"),
    ):
        with pytest.raises(SystemExit) as exc_info:
            main(["health"])
    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "Error" in captured.err


# ---------------------------------------------------------------------------
# M24: CLI api-key tests
# ---------------------------------------------------------------------------


def test_cli_api_key_flag_passed_to_client():
    """--api-key CLI flag is returned by _resolve_api_key."""
    from quantfidelity.cli import _resolve_api_key

    class FakeArgs:
        api_key = "qf_local_fromflag"

    result = _resolve_api_key(FakeArgs())
    assert result == "qf_local_fromflag"


def test_cli_api_key_from_env_var(monkeypatch):
    """QUANTFIDELITY_API_KEY env var is used when --api-key not provided."""
    monkeypatch.setenv("QUANTFIDELITY_API_KEY", "qf_local_fromenv")
    from quantfidelity.cli import _resolve_api_key

    class FakeArgs:
        api_key = None

    result = _resolve_api_key(FakeArgs())
    assert result == "qf_local_fromenv"


def test_cli_api_key_flag_overrides_env_var(monkeypatch):
    """--api-key flag takes precedence over env var."""
    monkeypatch.setenv("QUANTFIDELITY_API_KEY", "qf_local_fromenv")
    from quantfidelity.cli import _resolve_api_key

    class FakeArgs:
        api_key = "qf_local_fromflag"

    result = _resolve_api_key(FakeArgs())
    assert result == "qf_local_fromflag"


def test_cli_no_key_returns_none(monkeypatch):
    """Returns None when neither flag nor env var is set."""
    monkeypatch.delenv("QUANTFIDELITY_API_KEY", raising=False)
    from quantfidelity.cli import _resolve_api_key

    class FakeArgs:
        api_key = None

    result = _resolve_api_key(FakeArgs())
    assert result is None


# ---------------------------------------------------------------------------
# M42: env var support tests
# ---------------------------------------------------------------------------


class TestEnvVarSupportM42:
    def test_base_url_from_env_var(self, monkeypatch):
        """QUANTFIDELITY_BASE_URL env var is used when --base-url not overridden."""
        monkeypatch.setenv("QUANTFIDELITY_BASE_URL", "http://qf.test")
        from quantfidelity.cli import _resolve_base_url

        class FakeArgs:
            base_url = "http://localhost:8000"

        result = _resolve_base_url(FakeArgs())
        assert result == "http://qf.test"

    def test_base_url_flag_overrides_env(self, monkeypatch):
        """--base-url flag takes precedence over QUANTFIDELITY_BASE_URL env var."""
        monkeypatch.setenv("QUANTFIDELITY_BASE_URL", "http://env.test")
        from quantfidelity.cli import _resolve_base_url

        class FakeArgs:
            base_url = "http://flag.test"

        result = _resolve_base_url(FakeArgs())
        assert result == "http://flag.test"

    def test_idempotency_key_from_env(self, monkeypatch):
        """QUANTFIDELITY_IDEMPOTENCY_KEY env var is used when --idempotency-key not set."""
        monkeypatch.setenv("QUANTFIDELITY_IDEMPOTENCY_KEY", "env-key")
        from quantfidelity.cli import _resolve_idempotency_key

        class FakeArgs:
            idempotency_key = None

        result = _resolve_idempotency_key(FakeArgs())
        assert result == "env-key"

    def test_idempotency_key_flag_overrides_env(self, monkeypatch):
        """--idempotency-key flag takes precedence over env var."""
        monkeypatch.setenv("QUANTFIDELITY_IDEMPOTENCY_KEY", "env-key")
        from quantfidelity.cli import _resolve_idempotency_key

        class FakeArgs:
            idempotency_key = "flag-key"

        result = _resolve_idempotency_key(FakeArgs())
        assert result == "flag-key"

    def test_ingest_concise_summary_no_secret(
        self, tmp_path: Path, capsys: pytest.CaptureFixture, monkeypatch
    ):
        """Default ingest output is concise and does not contain secrets."""
        monkeypatch.delenv("QUANTFIDELITY_API_KEY", raising=False)
        bundle_file = tmp_path / "bundle.json"
        bundle_file.write_text(
            json.dumps({"strategy_run": {"run_name": "ci-test", "run_type": "backtest"}})
        )
        fake_result = {
            "strategy_id": STRATEGY_ID,
            "created_count": 2,
            "reused_count": 1,
        }
        with mock.patch(
            "quantfidelity.client.QuantFidelityClient.ingest_evidence_bundle",
            return_value=fake_result,
        ):
            with pytest.raises(SystemExit) as exc_info:
                main([
                    "ingest",
                    "--strategy-id", STRATEGY_ID,
                    "--file", str(bundle_file),
                ])
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "Bundle ingested." in captured.out
        assert "qf_local_" not in captured.out
        assert "secret" not in captured.out.lower()

    def test_validate_ci_bundle(self, capsys: pytest.CaptureFixture):
        """ci_bundle.json passes local validation."""
        ci_bundle_path = (
            Path(__file__).parent.parent / "examples" / "ci_bundle.json"
        )
        if not ci_bundle_path.exists():
            pytest.skip(f"ci_bundle.json not found at {ci_bundle_path}")
        with pytest.raises(SystemExit) as exc_info:
            main(["validate", "--file", str(ci_bundle_path)])
        assert exc_info.value.code == 0
