#!/usr/bin/env python3
"""Sync verified TR-6 frame metadata through official RawTree MCP.

Images remain local. --snapshot-only performs no inserts. A successful insert
is confirmed by querying stable frame IDs and hashes before local acknowledgement.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import fcntl
import json
import os
from pathlib import Path
import sys
import time

from rawtree_mcp_probe import Client
from rawtree_mcp_stdio import PACKAGE, PROJECT_ROOT

TABLE = "tomato_lha_tr6_frames"
DEFAULT_MANIFEST = PROJECT_ROOT / "data/samples/tr6_tomato/manifest.jsonl"
DEFAULT_SNAPSHOT = PROJECT_ROOT / "data/catalog/tomato/tr6_rawtree_snapshot.json"
ACK_PATH = PROJECT_ROOT / "data/catalog/tomato/tr6_rawtree_ack.jsonl"
ATTEMPT_PATH = PROJECT_ROOT / "data/catalog/tomato/tr6_rawtree_attempts.jsonl"
MAX_FRAMES = 10000
POLL_DELAYS = (0, 0.3, 0.7, 1.5, 3)
SELECT_FIELDS = ("frame_id", "dataset_id", "source_version", "frame_uri", "sha256", "bytes", "archive_path", "timestamp_candidate", "timestamp_verified", "entity_id", "entity_identity_verified", "synthetic", "license", "source_url", "metadata_sha256", "frame_sha256", "file_bytes", "source_archive_path", "captured_at_local", "timestamp_from_filename", "collection_status", "source_crc32_verified", "zip_crc32")


class SyncError(RuntimeError):
    pass


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def sql_string(value):
    if not isinstance(value, str) or any(ord(c) < 32 for c in value):
        raise SyncError("Invalid SQL string value")
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + f".tmp.{os.getpid()}")
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
    temp.replace(path)


def payload(result, *, acknowledgement=False):
    if result.get("isError"):
        raise SyncError("RawTree MCP returned an error; remote details withheld")
    if isinstance(result.get("structuredContent"), dict):
        return result["structuredContent"]
    for block in result.get("content", []):
        if block.get("type") == "text":
            try:
                return json.loads(block["text"])
            except (ValueError, KeyError):
                continue
    if acknowledgement:
        return {}
    raise SyncError("RawTree MCP returned an unrecognized query response")


def load_manifest(path):
    raw = path.read_bytes()
    rows = [json.loads(line) for line in raw.decode().splitlines() if line.strip()]
    if not rows or len(rows) >= MAX_FRAMES:
        raise SyncError("Manifest must contain 1–9,999 frames")
    return rows, hashlib.sha256(raw).hexdigest()


def normalized_row(row, *, verify_file=True):
    frame_id = row.get("frame_id")
    uri = row.get("frame_uri") or row.get("local_path")
    digest = row.get("frame_sha256", row.get("sha256"))
    if not all(isinstance(value, str) and value for value in (frame_id, uri, digest)):
        raise SyncError("Manifest requires frame_id, frame_uri/local_path, and sha256")
    if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest.lower()):
        raise SyncError("Invalid frame SHA256")
    source_path = Path(uri)
    if not source_path.is_absolute():
        source_path = PROJECT_ROOT / source_path
    source_path = source_path.resolve()
    try:
        relative_uri = str(source_path.relative_to(PROJECT_ROOT))
    except ValueError:
        raise SyncError("Frame must be inside the project directory") from None
    size = row.get("frame_bytes", row.get("bytes", row.get("size_bytes")))
    if verify_file:
        if not source_path.is_file():
            raise SyncError("A manifest frame has not been downloaded")
        actual_bytes = source_path.read_bytes()
        if hashlib.sha256(actual_bytes).hexdigest() != digest.lower():
            raise SyncError("Local frame hash differs from manifest")
        if size is not None and size != len(actual_bytes):
            raise SyncError("Local frame size differs from manifest")
        size = len(actual_bytes)
    if not isinstance(size, int) or size < 1:
        raise SyncError("Manifest requires positive file size")
    if row.get("ingestion_status") != "verified" or row.get("source_crc32_verified") is not True:
        raise SyncError("Only CRC-verified downloaded manifest rows may be synced")
    value = {
        "schema_version": 1,
        "frame_id": frame_id,
        "dataset_id": row.get("dataset_id", "figshare_tr6_tomato_30783827"),
        "source_version": str(row.get("source_version", row.get("dataset_version", "figshare_30783827_v1"))),
        "frame_uri": relative_uri,
        "sha256": digest.lower(),
        "bytes": size,
        "archive_path": row.get("archive_path", row.get("source_archive_path", "")),
        "timestamp_candidate": row.get("timestamp_candidate", row.get("timestamp_from_filename", "")) or "",
        "timestamp_verified": False,
        "entity_id": "unknown",
        "entity_identity_verified": False,
        "synthetic": False,
        "license": row.get("license", "CC BY 4.0"),
        "source_url": row.get("source_record_url", row.get("source_url", "https://figshare.com/articles/dataset/30783827")),
    }
    value.update(frame_sha256=value["sha256"], file_bytes=size,
                 source_archive_path=value["archive_path"],
                 captured_at_local=value["timestamp_candidate"],
                 timestamp_from_filename=value["timestamp_candidate"],
                 collection_status="verified", source_crc32_verified=True,
                 zip_crc32=str(row.get("zip_crc32", "")))
    # Timestamp-shaped filenames do not prove capture timing or specimen identity.
    value["metadata_sha256"] = hashlib.sha256(canonical(value).encode()).hexdigest()
    return value


class SyncClient:
    def __init__(self, client, record):
        self.client, self.record = client, record
        self.table_exists = False

    def query(self, name, sql):
        queried_at = now()
        result = payload(self.client.tool("run-query", {"sql": sql}))
        rows = result.get("data")
        if not isinstance(rows, list):
            raise SyncError("Query did not return rows")
        self.record["queries"].append({"name": name, "sql": sql, "queried_at_utc": queried_at,
                                       "rows": len(rows), "statistics": result.get("statistics", {})})
        return rows

    def discover(self):
        result = payload(self.client.tool("list-tables", {}))
        self.table_exists = any(row.get("name") == TABLE for row in result.get("tables", []))
        return self.table_exists

    def frames(self, scope, ids=None):
        if not self.table_exists and not self.discover():
            return []
        where = scope
        if ids is not None:
            where += " AND toString(frame_id) IN (" + ",".join(sql_string(x) for x in ids) + ")"
        rows = self.query("frame_metadata", "SELECT " + ", ".join(SELECT_FIELDS) + f" FROM {TABLE} WHERE {where} ORDER BY toString(frame_id) LIMIT {MAX_FRAMES}")
        if len(rows) >= MAX_FRAMES:
            raise SyncError("Frame query exceeds the bounded snapshot limit")
        return rows

    def wait_for(self, expected, scope):
        for delay in POLL_DELAYS:
            if delay:
                time.sleep(delay)
            rows = self.frames(scope, list(expected))
            found = verified_matches(expected, rows)
            if len(found) == len(expected):
                return found
        return found


def verified_matches(expected, remote):
    found = set()
    for row in remote:
        frame_id = row.get("frame_id")
        if frame_id not in expected:
            continue
        if row.get("sha256") != expected[frame_id]["sha256"] or row.get("metadata_sha256") != expected[frame_id]["metadata_sha256"]:
            raise SyncError("Existing frame ID has conflicting metadata; no overwrite attempted")
        found.add(frame_id)
    return found


def write_ack(frame_ids, expected, manifest_hash):
    ACK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with ACK_PATH.open("a") as handle:
        for frame_id in sorted(frame_ids):
            handle.write(canonical({"frame_id": frame_id, "source_version": expected[frame_id]["source_version"],
                                    "metadata_sha256": expected[frame_id]["metadata_sha256"],
                                    "manifest_sha256": manifest_hash, "verified_at_utc": now()}) + "\n")
        handle.flush(); os.fsync(handle.fileno())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    parser.add_argument("--snapshot-only", action="store_true")
    parser.add_argument("--batch-size", type=int, default=150)
    parser.add_argument("--expected-frames", type=int, default=2244)
    args = parser.parse_args()
    if not 1 <= args.batch_size <= 250:
        parser.error("--batch-size must be between 1 and 250")
    record = {"schema_version": 1, "generated_at_utc": now(), "source": "RawTree MCP run-query",
              "status": "error", "table": TABLE, "connection": {"ok": False, "transport": "stdio", "package": PACKAGE},
              "queries": [], "frames": [], "samples": [], "warnings": [],
              "sync": {"inserted_this_run": 0, "submitted_this_run": 0, "already_present": 0, "verified_frames": 0, "pending_frames": None},
              "counts": {"physical_rows": 0, "unique_frame_ids": 0, "duplicate_rows": 0,
                         "unique_image_hashes": 0, "duplicate_content_files": 0}}
    client = None
    lock_handle = None
    try:
        if not args.snapshot_only:
            lock_path = ACK_PATH.with_suffix(".lock")
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            lock_handle = lock_path.open("a")
            try:
                fcntl.flock(lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise SyncError("Another TR-6 sync is already running") from None
        raw_rows, manifest_hash = load_manifest(args.manifest)
        rows = [normalized_row(row, verify_file=not args.snapshot_only) for row in raw_rows]
        expected = {row["frame_id"]: row for row in rows}
        if len(expected) != len(rows):
            raise SyncError("Duplicate frame IDs in local manifest")
        datasets = {row["dataset_id"] for row in rows}; versions = {row["source_version"] for row in rows}
        if len(datasets) != 1 or len(versions) != 1:
            raise SyncError("One dataset and source version are required per sync")
        dataset, version = next(iter(datasets)), next(iter(versions))
        record.update(dataset_id=dataset, source_version=version,
                      manifest={"path": str(args.manifest.relative_to(PROJECT_ROOT)) if args.manifest.is_relative_to(PROJECT_ROOT) else str(args.manifest),
                                "sha256": manifest_hash, "rows": len(rows), "expected_source_frames": args.expected_frames})
        scope = "dataset_id = " + sql_string(dataset) + " AND source_version = " + sql_string(version)
        client = Client(timeout=50)
        server = client.initialize()
        remote = SyncClient(client, record)
        connection = remote.query("connection", "SELECT 1 AS connection_ok")
        if connection != [{"connection_ok": 1}]:
            raise SyncError("Connection verification returned an unexpected value")
        record["connection"].update(ok=True, server=server.get("serverInfo"))
        existing = remote.frames(scope)
        present = verified_matches(expected, existing)
        record["sync"]["already_present"] = len(present)
        # Prior acknowledgement is a hint to wait for query visibility, never a
        # substitute for an actual read from the database.
        previous = set()
        for journal_path in (ACK_PATH, ATTEMPT_PATH):
            if journal_path.exists():
                for line in journal_path.read_text().splitlines():
                    try:
                        ack = json.loads(line)
                    except ValueError:
                        continue
                    if ack.get("source_version") == version and ack.get("frame_id") in expected:
                        previous.add(ack["frame_id"])
        if previous - present:
            subset = {key: expected[key] for key in previous - present}
            present |= remote.wait_for(subset, scope)
        missing = [row for row in rows if row["frame_id"] not in present]
        if not args.snapshot_only:
            for start in range(0, len(missing), args.batch_size):
                batch = missing[start:start + args.batch_size]
                subset = {row["frame_id"]: row for row in batch}
                # Check each batch immediately before insertion, including a
                # bounded visibility window for prior attempted writes.
                latest = remote.frames(scope, list(subset))
                found = verified_matches(subset, latest)
                batch = [row for row in batch if row["frame_id"] not in found]
                if batch:
                    ATTEMPT_PATH.parent.mkdir(parents=True, exist_ok=True)
                    with ATTEMPT_PATH.open("a") as handle:
                        for row in batch:
                            handle.write(canonical({"frame_id": row["frame_id"], "source_version": version,
                                                   "metadata_sha256": row["metadata_sha256"], "attempted_at_utc": now()}) + "\n")
                        handle.flush(); os.fsync(handle.fileno())
                    payload(client.tool("insert-json", {"table": TABLE, "data": batch}), acknowledgement=True)
                    record["sync"]["submitted_this_run"] += len(batch)
                matched = remote.wait_for(subset, scope)
                if len(matched) != len(subset):
                    raise SyncError("Batch not visible within bounded verification; rerun to resume")
                record["sync"]["inserted_this_run"] += len(batch)
                write_ack(matched, expected, manifest_hash)
                print(json.dumps({"verified_batch": len(matched), "processed": min(start+args.batch_size, len(missing)), "missing_at_start": len(missing)}), flush=True)
        final_rows = remote.frames(scope)
        matched = verified_matches(expected, final_rows)
        record["sync"].update(verified_frames=len(matched), pending_frames=len(expected)-len(matched))
        if remote.table_exists:
            counts = remote.query("counts", f"SELECT count() AS physical_rows, uniqExact(toString(frame_id)) AS unique_frame_ids, uniqExact(toString(sha256)) AS unique_image_hashes FROM {TABLE} WHERE {scope}")[0]
            record["counts"] = {"physical_rows": int(counts["physical_rows"]), "unique_frame_ids": int(counts["unique_frame_ids"]),
                                "duplicate_rows": int(counts["physical_rows"])-int(counts["unique_frame_ids"]),
                                "unique_image_hashes": int(counts["unique_image_hashes"]),
                                "duplicate_content_files": int(counts["unique_frame_ids"])-int(counts["unique_image_hashes"])}
        unique = {row["frame_id"]: row for row in final_rows if row.get("frame_id") in expected}
        record["frames"] = list(unique.values())
        ordered = sorted(record["frames"], key=lambda r: (r.get("timestamp_candidate", ""), r["frame_id"]))
        record["samples"] = ordered[:6] + (ordered[-3:] if len(ordered)>6 else [])
        record["warnings"] = ["Snapshot of actual RawTree query results, not a live stream.",
                              "Filename timestamps are unverified; specimen identity is unknown.",
                              "Image binaries remain local. No GPT inference was performed."]
        complete = (len(matched) == len(rows) == args.expected_frames
                    and record["counts"]["unique_frame_ids"] == args.expected_frames
                    and not record["counts"]["duplicate_rows"])
        record["status"] = "verified" if complete else "partial"
    except Exception as exc:
        record["status"] = "error"
        record["error"] = str(exc) if isinstance(exc, SyncError) else type(exc).__name__
    finally:
        record["generated_at_utc"] = now()
        if client:
            record = client.sanitize(record)
            client.close()
        atomic_json(args.snapshot, record)
        if lock_handle:
            lock_handle.close()
    print(json.dumps({"status": record["status"], "snapshot": str(args.snapshot), "counts": record["counts"], "sync": record["sync"], "error": record.get("error")}))
    return 1 if record["status"] == "error" else 0


if __name__ == "__main__":
    raise SystemExit(main())
