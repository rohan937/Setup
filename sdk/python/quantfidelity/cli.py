"""CLI entry point for the QuantFidelity SDK.

Commands:

    qf ingest --base-url http://localhost:8000 \\
              --strategy-id <uuid> \\
              --file bundle.json

    qf example --base-url http://localhost:8000 \\
               --strategy-id <uuid> \\
               [--output bundle.json]

    qf health --base-url http://localhost:8000

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
        help="API key (reserved for future use; no-op in M23)",
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

    return parser


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

    if args.dry_run:
        print("Dry run — payload parsed successfully.  Not sending to server.")
        print(json.dumps(payload, indent=2))
        return 0

    client = QuantFidelityClient(base_url=args.base_url, api_key=args.api_key)
    try:
        result = client.ingest_evidence_bundle(args.strategy_id, payload)
    except QuantFidelityError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2, default=str))
    return 0


def _cmd_example(args: argparse.Namespace) -> int:
    """Handle the ``example`` sub-command."""
    client = QuantFidelityClient(base_url=args.base_url, api_key=args.api_key)
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
    client = QuantFidelityClient(base_url=args.base_url, api_key=args.api_key)
    try:
        result = client.health()
    except QuantFidelityError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2))
    return 0


_COMMAND_HANDLERS = {
    "ingest": _cmd_ingest,
    "example": _cmd_example,
    "health": _cmd_health,
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
