"""Durable event journal and optional synchronous RawTree MCP persistence.

Single writer per journal/run. RawTree has no assumed unique-key constraint: each
write checks event_id and payload, then verifies the inserted event by reading it.
"""
from __future__ import annotations

import copy
import json
import math
import os
from pathlib import Path
import sys
import time
from typing import Any

KINDS = frozenset({"observations", "agent_events", "memory_events", "model_calls", "evaluation_results"})
TABLE_PREFIX = "tomato_lha_"
MAX_READ_ROWS = 10000
VERIFICATION_DELAYS = (0.0, 0.3, 0.7, 1.5, 3.0)


class StorageError(RuntimeError):
    """A durable write, remote operation, or journal consistency check failed."""


def _canonical(event: dict) -> str:
    return json.dumps(event, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def _sql_string(value: str) -> str:
    if not isinstance(value, str) or any(ord(c) < 32 for c in value):
        raise ValueError("SQL identifiers must be non-control strings")
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def _new_client():
    scripts = Path(__file__).resolve().parents[1] / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    from rawtree_mcp_probe import Client
    return Client()


def _tool_payload(result: dict, *, allow_text_ack: bool = False) -> Any:
    if result.get("isError"):
        # Never forward a server body: it can contain credentials or request data.
        raise StorageError("RawTree MCP operation failed; local outbox retained")
    if isinstance(result.get("structuredContent"), dict):
        return result["structuredContent"]
    for item in result.get("content", []):
        if item.get("type") == "text":
            try:
                return json.loads(item["text"])
            except (ValueError, KeyError):
                continue
    if allow_text_ack and any(item.get("type") == "text" for item in result.get("content", [])):
        # insert-json may acknowledge with plain text. This is not sufficient
        # proof: _sync always queries the exact payload before marking it synced.
        return {"acknowledged": True}
    raise StorageError("RawTree MCP returned an unrecognized response")


class EventStore:
    def __init__(self, root: Path, backend: str = "local"):
        if backend not in ("local", "rawtree"):
            raise ValueError("backend must be local or rawtree")
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.backend = backend
        self.journal_path = self.root / "events.jsonl"
        self.ack_path = self.root / "acknowledgements.jsonl"
        self._events: dict[str, dict] = {}
        self._acked: set[str] = set()
        self._known_tables: set[str] = set()
        self._client = None
        self._closed = False
        for event in self._read_journal(self.journal_path):
            self._validate(event.get("kind"), event)
            key = event["event_id"]
            if key in self._events and _canonical(event) != _canonical(self._events[key]):
                raise StorageError("Conflicting event_id in local journal")
            self._events[key] = event
        for record in self._read_journal(self.ack_path):
            self._acked.add(record["event_id"])

    @staticmethod
    def _read_journal(path: Path) -> list[dict]:
        if not path.exists():
            return []
        data = path.read_bytes()
        lines = data.splitlines(keepends=True)
        records = []
        for index, line in enumerate(lines):
            try:
                record = json.loads(line)
                if not isinstance(record, dict):
                    raise ValueError("not an object")
                records.append(record)
            except (ValueError, UnicodeError):
                # Recover only an interrupted final append; malformed complete
                # records must not disappear silently.
                if index == len(lines) - 1 and not line.endswith(b"\n"):
                    with path.open("r+b") as handle:
                        handle.truncate(sum(len(x) for x in lines[:index]))
                        handle.flush()
                        os.fsync(handle.fileno())
                    break
                raise StorageError("Malformed local event journal") from None
        # A valid JSON tail without newline must be terminated before appending.
        if data and not data.endswith(b"\n") and len(records) == len(lines):
            with path.open("ab") as handle:
                handle.write(b"\n")
                handle.flush()
                os.fsync(handle.fileno())
        return records

    @staticmethod
    def _validate(kind: str, event: dict) -> None:
        if kind not in KINDS or event.get("kind") != kind:
            raise ValueError("Invalid event kind")
        for field in ("event_id", "run_id", "entity_id", "dataset_id", "sequence_id"):
            if not isinstance(event.get(field), str) or not event[field]:
                raise ValueError(f"Missing event field: {field}")
        elapsed = event.get("elapsed_seconds")
        if isinstance(elapsed, bool) or not isinstance(elapsed, (float, int)) or not math.isfinite(elapsed):
            raise ValueError("elapsed_seconds must be a finite number")
        version = event.get("record_version")
        if isinstance(version, bool) or not isinstance(version, int) or version < 0:
            raise ValueError("record_version must be a nonnegative integer")
        if kind == "memory_events" and not isinstance(event.get("state"), dict):
            raise ValueError("Memory event requires state object")
        _canonical(event)

    def _ensure_open(self):
        if self._closed:
            raise StorageError("EventStore is closed")

    def _remote(self):
        self._ensure_open()
        if self._client is None:
            client = None
            try:
                client = _new_client()
                client.initialize()
                self._client = client
            except Exception:
                if client:
                    client.close()
                raise StorageError("RawTree MCP connection failed; local outbox retained") from None
        return self._client

    def _call(self, name: str, arguments: dict) -> Any:
        try:
            return _tool_payload(self._remote().tool(name, arguments), allow_text_ack=name == "insert-json")
        except StorageError:
            raise
        except Exception:
            raise StorageError("RawTree MCP operation failed; local outbox retained") from None

    def _table_exists(self, kind: str) -> bool:
        table = TABLE_PREFIX + kind
        if table in self._known_tables:
            return True
        payload = self._call("list-tables", {})
        allowed_tables = {TABLE_PREFIX + item for item in KINDS}
        self._known_tables.update(
            row["name"] for row in payload.get("tables", [])
            if row.get("name") in allowed_tables
        )
        # Missing tables are never cached: insert-json or another writer may
        # create one later. A positive cache only bypasses metadata discovery;
        # every payload read and post-insert verification still goes to MCP.
        return table in self._known_tables

    def _remote_events(self, kind: str, where: str) -> list[dict]:
        if not self._table_exists(kind):
            return []
        sql = f"SELECT event_json FROM {TABLE_PREFIX}{kind} WHERE {where} LIMIT {MAX_READ_ROWS}"
        payload = self._call("run-query", {"sql": sql})
        rows = payload.get("data")
        if not isinstance(rows, list):
            raise StorageError("RawTree query did not return data rows")
        if len(rows) >= MAX_READ_ROWS:
            raise StorageError("RawTree resume query exceeds MVP row limit; pagination required")
        events = []
        for row in rows:
            try:
                event = json.loads(row["event_json"])
                self._validate(kind, event)
            except (KeyError, ValueError, TypeError):
                raise StorageError("Remote event violates the event contract") from None
            events.append(event)
        return self._deduplicate(events)

    @staticmethod
    def _deduplicate(events: list[dict]) -> list[dict]:
        unique = {}
        for event in events:
            key = event["event_id"]
            if key in unique and _canonical(event) != _canonical(unique[key]):
                raise StorageError("Conflicting event_id payloads")
            unique[key] = event
        return list(unique.values())

    @staticmethod
    def _append_line(path: Path, event: dict):
        with path.open("a", encoding="utf-8") as handle:
            handle.write(_canonical(event) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def append(self, kind: str, event: dict) -> None:
        self._ensure_open()
        self._validate(kind, event)
        event = copy.deepcopy(event)
        key = event["event_id"]
        existing = self._events.get(key)
        if existing is not None and _canonical(existing) != _canonical(event):
            raise StorageError("event_id already exists with a different payload")
        if existing is None:
            self._append_line(self.journal_path, event)
            self._events[key] = event
        if self.backend == "rawtree" and key not in self._acked:
            self._sync(event, pending_retry=existing is not None)

    def _find_remote_event(self, event: dict, where: str, *, poll: bool) -> bool:
        for delay in (VERIFICATION_DELAYS if poll else (0.0,)):
            if delay:
                time.sleep(delay)
            rows = self._remote_events(event["kind"], where)
            if rows:
                if any(_canonical(row) != _canonical(event) for row in rows):
                    raise StorageError("Remote event_id has a different payload; outbox retained")
                return True
        return False

    def _sync(self, event: dict, *, pending_retry: bool = False):
        kind = event["kind"]
        where = "run_id = " + _sql_string(event["run_id"]) + " AND event_id = " + _sql_string(event["event_id"])
        # An earlier write may have succeeded but still be invisible. Give
        # pending events the same bounded read window before considering resend.
        existing = self._find_remote_event(event, where, poll=pending_retry)
        if not existing:
            # Queryable envelope plus exact canonical payload avoids lossy
            # reconstruction of nested memory state from dynamic SQL columns.
            row = {key: event[key] for key in ("event_id", "run_id", "entity_id", "dataset_id", "sequence_id", "elapsed_seconds", "record_version", "kind")}
            row["event_json"] = _canonical(event)
            row["integration_fixture"] = bool(event.get("integration_fixture", False))
            self._call("insert-json", {"table": TABLE_PREFIX + kind, "data": row})
            # Successful insert is never retried in this attempt. Poll only
            # reads, then retain the outbox if the visibility window expires.
            if not self._find_remote_event(event, where, poll=True):
                raise StorageError("RawTree write not verified after bounded polling; local outbox retained")
        self._append_line(self.ack_path, {"event_id": event["event_id"]})
        self._acked.add(event["event_id"])

    def latest_memory(self, run_id: str, entity_id: str, as_of_seconds: float) -> dict | None:
        self._ensure_open()
        if not math.isfinite(as_of_seconds):
            raise ValueError("as_of_seconds must be finite")
        if self.backend == "rawtree":
            where = ("run_id = " + _sql_string(run_id) + " AND entity_id = " + _sql_string(entity_id)
                     + " AND elapsed_seconds <= " + repr(float(as_of_seconds)))
            rows = self._remote_events("memory_events", where)
        else:
            rows = list(self._events.values())
        candidates = [event for event in rows if event["kind"] == "memory_events"
                      and event["run_id"] == run_id and event["entity_id"] == entity_id
                      and event["elapsed_seconds"] <= as_of_seconds]
        if not candidates:
            return None
        return copy.deepcopy(max(candidates, key=lambda e: (e["record_version"], e["elapsed_seconds"], e["event_id"])))

    def existing_events(self, run_id: str, kind: str | None = None) -> list[dict]:
        self._ensure_open()
        if kind is not None and kind not in KINDS:
            raise ValueError("Invalid event kind")
        if self.backend == "rawtree":
            rows = []
            for selected_kind in ([kind] if kind else sorted(KINDS)):
                rows.extend(self._remote_events(selected_kind, "run_id = " + _sql_string(run_id)))
        else:
            rows = list(self._events.values())
        result = [e for e in rows if e["run_id"] == run_id and (kind is None or e["kind"] == kind)]
        return copy.deepcopy(sorted(self._deduplicate(result), key=lambda e: (e["elapsed_seconds"], e["record_version"], e["event_id"])))

    def flush(self) -> None:
        self._ensure_open()
        if self.backend == "rawtree":
            for key, event in self._events.items():
                if key not in self._acked:
                    self._sync(event, pending_retry=True)

    def __enter__(self):
        self._ensure_open()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            if exc_type is None:
                self.flush()
        finally:
            if self._client:
                self._client.close()
                self._client = None
            self._closed = True
        return False
