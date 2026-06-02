"""CLI entry point for the QuantFidelity SDK.

Commands:

    qf ingest --base-url http://localhost:8000 \\
              --strategy-id <uuid> \\
              --file bundle.json

    qf example --base-url http://localhost:8000 \\
               --strategy-id <uuid> \\
               [--output bundle.json]

    qf health --base-url http://localhost:8000

    qf buffer list [--buffer-path PATH]

    qf buffer flush --base-url URL [--buffer-path PATH] [--max-items N]

    qf buffer clear [--buffer-path PATH] [--yes]

Exit codes:
  0 — success
  1 — QuantFidelity SDK error (connection, API, validation)
  2 — bad arguments or file not found (argparse default)
"""
from __future__ import annotations

import argparse
import json
import sys

from quantfidelity.client import QuantFidelityClient
from quantfidelity.exceptions import QuantFidelityError


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="qf",
        description=(
            "QuantFidelity SDK CLI — submit evidence bundles and query the "
            "QuantFidelity API from the command line."
        ),
    )
    parser.add_argument(
        "--base-url",
        default="http://localhost:8000",
        metavar="URL",
        help="QuantFidelity server base URL (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--api-key",
        default=None,
        metavar="KEY",
        help=(
            "API key for authentication.  If not provided, falls back to the "
            "QUANTFIDELITY_API_KEY environment variable."
        ),
    )

    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    sub.required = True

    # ── ingest ──────────────────────────────────────────────────────────
    p_ingest = sub.add_parser(
        "ingest",
        help="Ingest an evidence bundle from a JSON file.",
        description=(
            "Read a JSON evidence bundle from FILE and POST it to the "
            "QuantFidelity API for the given strategy."
        ),
    )
    p_ingest.add_argument(
        "--strategy-id",
        required=True,
        metavar="UUID",
        help="UUID of the target strategy.",
    )
    p_ingest.add_argument(
        "--file",
        required=True,
        metavar="PATH",
        help="Path to a JSON file containing the evidence bundle payload.",
    )
    p_ingest.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help=(
            "Parse the JSON and print the payload without sending it "
            "to the server."
        ),
    )
    p_ingest.add_argument(
        "--idempotency-key",
        default=None,
        metavar="KEY",
        help=(
            "Optional idempotency key to attach to the request.  "
            "Auto-generated when --retry is active (default)."
        ),
    )
    p_ingest.add_argument(
        "--buffer-on-failure",
        action="store_true",
        default=False,
        help=(
            "If the request fails after all retries, save the bundle to the "
            "local offline buffer instead of printing an error."
        ),
    )
    p_ingest.add_argument(
        "--buffer-path",
        default=None,
        metavar="PATH",
        help="Path to the offline buffer file (default: ~/.quantfidelity/buffer.jsonl).",
    )
    p_ingest.add_argument(
        "--validate-before-send",
        action="store_true",
        default=False,
        help=(
            "Validate the bundle locally before sending it to the server. "
            "If validation issues are found the command exits with code 1 "
            "unless --force is also set."
        ),
    )
    p_ingest.add_argument(
        "--force",
        action="store_true",
        default=False,
        help=(
            "When used together with --validate-before-send, send the bundle "
            "even if local validation finds issues (prints a warning instead)."
        ),
    )
    p_ingest.add_argument(
        "--json",
        action="store_true",
        default=False,
        help=(
            "Print the full server response as JSON instead of a concise "
            "human-readable summary."
        ),
    )

    # ── example ─────────────────────────────────────────────────────────
    p_example = sub.add_parser(
        "example",
        help="Fetch an example evidence bundle payload from the API.",
        description=(
            "Fetch a fully-populated example EvidenceBundleRequest from the "
            "QuantFidelity API and print it as JSON."
        ),
    )
    p_example.add_argument(
        "--strategy-id",
        required=True,
        metavar="UUID",
        help="UUID of the strategy to build the example for.",
    )
    p_example.add_argument(
        "--output",
        default=None,
        metavar="PATH",
        help="If provided, write the example JSON to this file.",
    )

    # ── health ──────────────────────────────────────────────────────────
    sub.add_parser(
        "health",
        help="Check the QuantFidelity server health.",
    )

    # ── validate ────────────────────────────────────────────────────────
    p_validate = sub.add_parser(
        "validate",
        help="Validate a bundle JSON file locally without sending.",
        description=(
            "Read a JSON evidence bundle from FILE and run SDK-side validation "
            "checks.  Nothing is sent to the server."
        ),
    )
    p_validate.add_argument(
        "--file",
        required=True,
        metavar="PATH",
        help="Path to the JSON bundle file to validate.",
    )

    # ── buffer ──────────────────────────────────────────────────────────
    p_buffer = sub.add_parser(
        "buffer",
        help="Manage the local offline buffer.",
        description=(
            "Commands for listing, flushing, and clearing the local "
            "offline evidence bundle buffer."
        ),
    )
    buf_sub = p_buffer.add_subparsers(dest="buffer_command", metavar="BUFFER_COMMAND")
    buf_sub.required = True

    # buffer list
    p_buf_list = buf_sub.add_parser(
        "list",
        help="List buffered records.",
    )
    p_buf_list.add_argument(
        "--buffer-path",
        default=None,
        metavar="PATH",
        help="Path to the offline buffer file.",
    )

    # buffer flush
    p_buf_flush = buf_sub.add_parser(
        "flush",
        help="Attempt to resend buffered records to the API.",
    )
    p_buf_flush.add_argument(
        "--buffer-path",
        default=None,
        metavar="PATH",
        help="Path to the offline buffer file.",
    )
    p_buf_flush.add_argument(
        "--max-items",
        default=None,
        type=int,
        metavar="N",
        help="Maximum number of records to flush in one run.",
    )

    # buffer clear
    p_buf_clear = buf_sub.add_parser(
        "clear",
        help="Remove all buffered records.",
    )
    p_buf_clear.add_argument(
        "--buffer-path",
        default=None,
        metavar="PATH",
        help="Path to the offline buffer file.",
    )
    p_buf_clear.add_argument(
        "--yes",
        action="store_true",
        default=False,
        help="Skip confirmation prompt.",
    )

    return parser


def _resolve_api_key(args: argparse.Namespace) -> str | None:
    """Resolve API key from --api-key flag or QUANTFIDELITY_API_KEY env var.

    --api-key flag takes precedence over env var.
    """
    import os

    if args.api_key:
        return args.api_key
    return os.environ.get("QUANTFIDELITY_API_KEY") or None


def _resolve_base_url(args: argparse.Namespace) -> str:
    """Resolve server base URL from --base-url flag or QUANTFIDELITY_BASE_URL env var.

    --base-url flag (when non-default) takes precedence over env var.
    """
    import os

    env_url = os.environ.get("QUANTFIDELITY_BASE_URL")
    flag_url = getattr(args, "base_url", None)
    if flag_url and flag_url != "http://localhost:8000":
        return flag_url
    if env_url:
        return env_url
    return flag_url or "http://localhost:8000"


def _resolve_idempotency_key(args: argparse.Namespace) -> str | None:
    """Resolve idempotency key from --idempotency-key flag or QUANTFIDELITY_IDEMPOTENCY_KEY env var.

    --idempotency-key flag takes precedence over env var.
    """
    import os

    flag_key = getattr(args, "idempotency_key", None)
    if flag_key:
        return flag_key
    return os.environ.get("QUANTFIDELITY_IDEMPOTENCY_KEY") or None


def _cmd_validate(args: argparse.Namespace) -> int:
    """Handle the ``validate`` sub-command."""
    try:
        with open(args.file, encoding="utf-8") as fh:
            raw = fh.read()
    except FileNotFoundError:
        print(f"Error: file not found: {args.file}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"Error reading {args.file}: {exc}", file=sys.stderr)
        return 1

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"Error: invalid JSON: {exc}", file=sys.stderr)
        return 1

    from quantfidelity.bundle import EvidenceBundle  # noqa: PLC0415

    bundle = EvidenceBundle.from_dict(payload)
    issues = bundle.validate()
    if not issues:
        print("Bundle is valid. No issues found.")
        return 0

    print(f"Bundle has {len(issues)} validation issue(s):")
    for issue in issues:
        print(f"  - {issue}")
    return 1


def _cmd_ingest(args: argparse.Namespace) -> int:
    """Handle the ``ingest`` sub-command."""
    try:
        with open(args.file, encoding="utf-8") as fh:
            raw = fh.read()
    except FileNotFoundError:
        print(f"Error: file not found: {args.file}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"Error reading {args.file}: {exc}", file=sys.stderr)
        return 1

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"Error: {args.file} is not valid JSON: {exc}", file=sys.stderr)
        return 1

    # Optional local validation before sending
    if getattr(args, "validate_before_send", False):
        from quantfidelity.bundle import EvidenceBundle  # noqa: PLC0415

        bundle_obj = EvidenceBundle.from_dict(payload)
        issues = bundle_obj.validate()
        if issues:
            if getattr(args, "force", False):
                print(
                    f"Warning: {len(issues)} validation issue(s) found"
                    " (--force set, continuing):",
                    file=sys.stderr,
                )
                for issue in issues:
                    print(f"  - {issue}", file=sys.stderr)
            else:
                print(
                    f"Bundle has {len(issues)} validation issue(s)"
                    " (use --force to send anyway):",
                    file=sys.stderr,
                )
                for issue in issues:
                    print(f"  - {issue}", file=sys.stderr)
                return 1

    if args.dry_run:
        print("Dry run — payload parsed successfully.  Not sending to server.")
        print(json.dumps(payload, indent=2))
        return 0

    buffer_path = getattr(args, "buffer_path", None)
    client = QuantFidelityClient(
        base_url=_resolve_base_url(args),
        api_key=_resolve_api_key(args),
        buffer_path=buffer_path,
    )
    try:
        result = client.ingest_evidence_bundle(
            args.strategy_id,
            payload,
            idempotency_key=_resolve_idempotency_key(args),
            buffer_on_failure=getattr(args, "buffer_on_failure", False),
        )
    except QuantFidelityError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if getattr(args, "json", False):
        print(json.dumps(result, indent=2, default=str))
    else:
        print("Bundle ingested.")
        print(f"  strategy_id:   {result.get('strategy_id', '—')}")
        print(f"  created:       {result.get('created_count', '—')}")
        print(f"  reused:        {result.get('reused_count', '—')}")
        if result.get("idempotency_status"):
            print(f"  idempotency:   {result['idempotency_status']}")
        if result.get("ingestion_batch_id"):
            print(f"  batch_id:      {result['ingestion_batch_id']}")
    return 0


def _cmd_example(args: argparse.Namespace) -> int:
    """Handle the ``example`` sub-command."""
    client = QuantFidelityClient(base_url=_resolve_base_url(args), api_key=_resolve_api_key(args))
    try:
        example = client.get_evidence_bundle_example(args.strategy_id)
    except QuantFidelityError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    json_text = json.dumps(example, indent=2)
    print(json_text)

    if args.output:
        try:
            with open(args.output, "w", encoding="utf-8") as fh:
                fh.write(json_text)
            print(f"\nExample written to {args.output}", file=sys.stderr)
        except OSError as exc:
            print(f"Warning: could not write to {args.output}: {exc}", file=sys.stderr)

    return 0


def _cmd_health(args: argparse.Namespace) -> int:
    """Handle the ``health`` sub-command."""
    client = QuantFidelityClient(base_url=_resolve_base_url(args), api_key=_resolve_api_key(args))
    try:
        result = client.health()
    except QuantFidelityError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2))
    return 0


def _cmd_buffer_list(args: argparse.Namespace) -> int:
    """Handle the ``buffer list`` sub-command."""
    from quantfidelity.buffer import LocalBuffer
    buf = LocalBuffer(path=getattr(args, "buffer_path", None))
    records = buf.list_records()
    print(json.dumps(records, indent=2, default=str))
    return 0


def _cmd_buffer_flush(args: argparse.Namespace) -> int:
    """Handle the ``buffer flush`` sub-command."""
    buffer_path = getattr(args, "buffer_path", None)
    client = QuantFidelityClient(
        base_url=_resolve_base_url(args),
        api_key=_resolve_api_key(args),
        buffer_path=buffer_path,
    )
    try:
        result = client.flush_buffer(max_items=getattr(args, "max_items", None))
    except QuantFidelityError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2))
    return 0


def _cmd_buffer_clear(args: argparse.Namespace) -> int:
    """Handle the ``buffer clear`` sub-command."""
    if not getattr(args, "yes", False):
        answer = input("Are you sure you want to clear the buffer? [y/N] ").strip().lower()
        if answer not in ("y", "yes"):
            print("Aborted.", file=sys.stderr)
            return 1

    from quantfidelity.buffer import LocalBuffer
    buf = LocalBuffer(path=getattr(args, "buffer_path", None))
    count = buf.clear()
    print(f"Cleared {count} buffered record(s).")
    return 0


def _cmd_buffer(args: argparse.Namespace) -> int:
    """Dispatch buffer sub-subcommands."""
    buffer_handlers = {
        "list": _cmd_buffer_list,
        "flush": _cmd_buffer_flush,
        "clear": _cmd_buffer_clear,
    }
    handler = buffer_handlers.get(args.buffer_command)
    if handler is None:  # pragma: no cover
        print(f"Unknown buffer command: {args.buffer_command}", file=sys.stderr)
        return 2
    return handler(args)


_COMMAND_HANDLERS = {
    "ingest": _cmd_ingest,
    "validate": _cmd_validate,
    "example": _cmd_example,
    "health": _cmd_health,
    "buffer": _cmd_buffer,
}


def main(argv: list[str] | None = None) -> None:
    """Entry point for the ``qf`` CLI command."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    handler = _COMMAND_HANDLERS.get(args.command)
    if handler is None:  # pragma: no cover
        parser.print_help()
        sys.exit(2)

    exit_code = handler(args)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
