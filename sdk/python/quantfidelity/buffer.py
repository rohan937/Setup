"""Local offline buffer for QuantFidelity SDK evidence bundles.

Stores failed ingestion attempts as JSONL records so they can be retried later.
NEVER stores API keys or authentication credentials.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from quantfidelity.client import QuantFidelityClient

DEFAULT_BUFFER_PATH = Path.home() / ".quantfidelity" / "buffer.jsonl"


class LocalBuffer:
    """Local JSONL file buffer for offline evidence bundle storage.

    Parameters
    ----------
    path:
        Path to the JSONL buffer file.  Defaults to
        ``~/.quantfidelity/buffer.jsonl``.
    """

    def __init__(self, path: str | Path | None = None) -> None:
        if path is None:
            self.path = DEFAULT_BUFFER_PATH
        else:
            self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    def _read_all(self) -> list[dict[str, Any]]:
        """Read all records from the JSONL file."""
        if not self.path.exists():
            return []
        records: list[dict[str, Any]] = []
        with open(self.path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        return records

    def _write_all(self, records: list[dict[str, Any]]) -> None:
        """Write all records to the JSONL file, replacing its contents."""
        with open(self.path, "w", encoding="utf-8") as fh:
            for record in records:
                fh.write(json.dumps(record, default=str) + "\n")

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def add(
        self,
        *,
        base_url: str,
        strategy_id: str,
        payload: dict[str, Any],
        idempotency_key: str | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        """Add a failed bundle to the buffer.

        Does NOT store API key or authentication credentials.

        Returns
        -------
        dict
            The buffered record including ``buffer_id``.
        """
        record: dict[str, Any] = {
            "buffer_id": str(uuid.uuid4()),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "base_url": base_url,
            "strategy_id": strategy_id,
            "idempotency_key": idempotency_key,
            "payload": payload,
            "attempts": 1,
            "last_error": error,
        }
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, default=str) + "\n")
        return record

    def list_records(self) -> list[dict[str, Any]]:
        """Return all buffered records.  Returns ``[]`` if file doesn't exist."""
        return self._read_all()

    def clear(self) -> int:
        """Remove all buffered records.

        Returns
        -------
        int
            Number of records removed.
        """
        records = self._read_all()
        count = len(records)
        if self.path.exists():
            self.path.unlink()
        return count

    def flush(
        self,
        client: "QuantFidelityClient",
        *,
        max_items: int | None = None,
    ) -> dict[str, Any]:
        """Attempt to resend buffered records using the given client.

        Successfully sent records are removed from the buffer.
        Failed records remain with ``attempts`` incremented and
        ``last_error`` updated.

        Parameters
        ----------
        client:
            A :class:`~quantfidelity.client.QuantFidelityClient` instance
            used to send the buffered requests.
        max_items:
            If set, only attempt to flush at most this many records.

        Returns
        -------
        dict
            ``{"flushed": N, "failed": M, "remaining": K}``
        """
        all_records = self._read_all()
        records_to_try = all_records[:max_items] if max_items is not None else all_records

        flushed_ids: list[str] = []
        updated_records: list[dict[str, Any]] = []

        for record in records_to_try:
            try:
                headers: dict[str, str] = {"Content-Type": "application/json"}
                if client._api_key:
                    headers["Authorization"] = f"Bearer {client._api_key}"
                if record.get("idempotency_key"):
                    headers["Idempotency-Key"] = record["idempotency_key"]

                resp = client._requests.post(
                    f"{client._base_url}/api/strategies/{record['strategy_id']}/evidence-bundles",
                    data=json.dumps(record["payload"], default=str),
                    headers=headers,
                    timeout=client._timeout,
                )
                if resp.ok:
                    flushed_ids.append(record["buffer_id"])
                else:
                    record = dict(record)
                    record["attempts"] = record.get("attempts", 1) + 1
                    record["last_error"] = f"HTTP {resp.status_code}"
                    updated_records.append(record)
            except Exception as exc:
                record = dict(record)
                record["attempts"] = record.get("attempts", 1) + 1
                record["last_error"] = str(exc)
                updated_records.append(record)

        # Rewrite buffer: keep records not in flushed_ids (preserving order)
        updated_map = {r["buffer_id"]: r for r in updated_records}
        remaining = [
            updated_map.get(r["buffer_id"], r)
            for r in all_records
            if r["buffer_id"] not in flushed_ids
        ]
        self._write_all(remaining)

        return {
            "flushed": len(flushed_ids),
            "failed": len(updated_records),
            "remaining": len(remaining),
        }
