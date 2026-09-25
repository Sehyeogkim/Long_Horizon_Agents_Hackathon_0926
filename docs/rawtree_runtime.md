# Tomato agent event storage and recovery

`tomato_agent/storage.py` provides durable local JSONL storage and official RawTree MCP storage through the same `EventStore` interface. RawTree mode always retains a local journal. It reuses the official stdio MCP client in `scripts/rawtree_mcp_probe.py` without substituting direct REST calls.

## Usage contract

```python
from pathlib import Path
from tomato_agent.storage import EventStore

with EventStore(Path("data/runs/example/journal"), backend="local") as store:
    store.append("memory_events", {
        "event_id": "example:tomato-1:memory:1",
        "run_id": "example",
        "entity_id": "tomato-1",
        "dataset_id": "example-dataset",
        "sequence_id": "sequence-1",
        "elapsed_seconds": 10.0,
        "record_version": 1,
        "kind": "memory_events",
        "state": {"open_questions": []},
    })
    memory_event = store.latest_memory("example", "tomato-1", as_of_seconds=10.0)
    state = memory_event["state"] if memory_event else None
    events = store.existing_events("example", kind="memory_events")
    store.flush()
```

- `root` is the local journal directory, independent of the API key configuration location.
- `backend="rawtree"` connects through the official MCP wrapper using `RAWTREE_API_KEY`. The key is never a command-line argument.
- Allowed kinds: `observations`, `agent_events`, `memory_events`, `model_calls`, `evaluation_results`.
- Physical tables: `tomato_lha_{kind}`. Existing apple and unrelated project table contents are not read or modified.
- `latest_memory` returns the **entire memory event**, not only its `state`; it returns `None` when no event qualifies.
- `existing_events` reads only the requested run, deduplicates by `event_id`, and returns events ordered by replay time, version, and ID.

## Journal and remote write sequence

1. Validate common fields and JSON serialization. Reusing an event ID with a different payload is an error.
2. Append to `events.jsonl`, then flush and fsync.
3. In RawTree mode, query the project table by run/event ID. An identical existing payload is not inserted again.
4. Insert missing events with MCP `insert-json`. Each remote row contains queryable common fields and canonical `event_json` preserving the entire original event. Model observations are not converted into ground truth.
5. Read the same ID through MCP `run-query`. If it is not visible immediately after a successful write, attempt at most five reads with delays of 0, 0.3, 0.7, 1.5, and 3 seconds: 5.5 seconds of added waiting, excluding network time. Do not repeat the insert within that attempt. Append a completion record to `acknowledgements.jsonl` only after the payload matches. A textual server acknowledgement alone is not proof of persistence.

Within an `EventStore`, confirmed tomato table names are cached to avoid repeated `list-tables` calls. Missing tables are not cached, so tables created later can be discovered. Payload reads and post-write verification still make real MCP calls.

Failures raise `StorageError` and retain unfinished local events. Error messages do not print remote response bodies or keys. After restoring connectivity, reopen the same root and call `flush()` to process pending events in order. Before resending, use the same bounded five-read window to discover earlier writes that were not yet visible. Resend only if the event remains absent. This also reduces duplicate inserts when a write succeeded but its response was lost.

Normal context exit calls `flush()`. An exceptional exit closes the connection without automatically resending. Failed RawTree reads are not replaced by successful local results. Explicit local mode reads only the local journal.

## Time and experiment isolation

Remote memory queries first constrain `run_id`, `entity_id`, and `elapsed_seconds <= as_of_seconds` in SQL. The same filters are applied to returned events before choosing the highest `record_version`. A future version is never selected before applying the cutoff.

`elapsed_seconds` must represent the replay time when information became available in that run. The storage layer cannot detect a memory derived from future information but assigned an earlier timestamp. Callers must preserve source observation order and model-result availability. Do not invent actual capture dates for undated footage.

RawTree mode reads remote data to restore state even when the local journal is empty. Preserving the complete event JSON also preserves nested `state` values. SQL string values escape quotes and backslashes; table names come only from a fixed allowlist.

## Verification results

The following 12 local tests passed on 2026-09-25:

- Persistence across restarts, temporal cutoff, and run/entity isolation.
- Deduplication of same-ID retries and detection of conflicting payloads.
- Recovery of an interrupted final JSONL write.
- Remote memory recovery from an empty local directory, excluding future versions.
- Outbox retention after a remote write failure and replay after restart.
- Exact payload verification after a textual insert acknowledgement.
- No local-success fallback during remote failures.
- Safe SQL literals for run IDs containing quotes.
- Caching confirmed table metadata, discovering tables created later, and isolating new runs.
- Discovering a table created by the first insert and avoiding subsequent listing calls.
- Bounded read polling for delayed visibility without repeating the insert.
- Retaining the outbox after polling expires and waiting before resending on restart.

```sh
python3 -m unittest discover -s tests -p test_storage.py -v
```

Live official RawTree MCP validation also passed **write/readback, restart with an empty local directory, future cutoff, cross-run isolation, and duplicate retry** checks.

| Item | Verified value |
| --- | --- |
| Table | `tomato_lha_memory_events` |
| Test run | `storage_fixture_ee6c8c98c6584a3191237fea0216ed1e` |
| Isolation comparison run | The same ID plus `_isolated` |
| Rows retained | Three fixture memory events, all `integration_fixture=true` |
| Main-run memory | Version 1 at 10 seconds; version 2 at 30 seconds |
| Query at 20 seconds | Returns the 10-second memory |
| Query at 30 seconds | Returns the 30-second memory |
| Query at 9 seconds | `None` |
| Resending the same event after restart | Main run remains at two events |

These rows are not real tomato observations or model inferences. They also carry `dataset_id=integration_fixture` and `state.not_real_observation=true`, and must be excluded from evaluation. After handling the server's textual write acknowledgement, validation continued with the same run and left only the three final fixture rows.

A pending day03 observation from the real `tomato_c_demo_v1` run was also recovered after it was not visible immediately following insertion. With the fix, `flush()` confirmed the existing row using one remote query and reduced pending events from 1 to 0. Recovery made zero insert calls and zero model calls.

## MVP limits

- One writer is assumed. Read-before-write does not provide database uniqueness under concurrent writers. Do not write the same root/run from multiple processes concurrently.
- SQL reads are capped at 10,000 rows per kind/run. Reaching the cap raises an error instead of returning an incomplete report; longer runs require pagination.
- A malformed complete JSON record raises an error. Only an incomplete final append is recovered.
- Remote outbox synchronization is sequential. There is no automatic background delivery or unbounded retry loop.
