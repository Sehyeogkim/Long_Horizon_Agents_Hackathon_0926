import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

from tomato_agent.storage import EventStore, StorageError, _sql_string


def event(key="m1", run="run-a", entity="tomato-1", elapsed=10, version=1):
    return {"event_id": key, "run_id": run, "entity_id": entity,
            "dataset_id": "fixture", "sequence_id": "seq-1", "elapsed_seconds": elapsed,
            "record_version": version, "kind": "memory_events", "state": {"note": key},
            "integration_fixture": True}


class FakeRemote:
    def __init__(self):
        self.tables = {}
        self.insert_count = 0
        self.list_count = 0
        self.fail_insert = False
        self.plain_text_ack = False
        self.fail_query = False
        self.queries = []
        self.visibility_delay_reads = 0
        self.visibility_remaining = {}

    def initialize(self):
        return {"serverInfo": {"name": "fixture"}}

    def close(self):
        pass

    def tool(self, name, arguments):
        if name == "list-tables":
            self.list_count += 1
            data = {"tables": [{"name": k} for k in self.tables]}
        elif name == "insert-json":
            if self.fail_insert:
                return {"isError": True, "content": [{"type": "text", "text": "secret fake bearer value"}]}
            self.insert_count += 1
            self.visibility_remaining[arguments["data"]["event_id"]] = self.visibility_delay_reads
            self.tables.setdefault(arguments["table"], []).append(arguments["data"])
            if self.plain_text_ack:
                return {"content": [{"type": "text", "text": "Insert accepted"}]}
            data = {"inserted": 1}
        elif name == "run-query":
            if self.fail_query:
                raise ConnectionError("private server details")
            sql = arguments["sql"]
            self.queries.append(sql)
            table = re.search(r"FROM (\w+)", sql).group(1)
            rows = list(self.tables[table])
            for field in ("run_id", "entity_id", "event_id"):
                match = re.search(field + r" = '((?:\\.|[^'])*)'", sql)
                if match:
                    value = re.sub(r"\\(.)", r"\1", match.group(1))
                    rows = [r for r in rows if r[field] == value]
            cutoff = re.search(r"elapsed_seconds <= ([0-9.e+-]+)", sql)
            if cutoff:
                rows = [r for r in rows if r["elapsed_seconds"] <= float(cutoff.group(1))]
            visible = []
            for row in rows:
                key = row["event_id"]
                if self.visibility_remaining.get(key, 0) > 0:
                    self.visibility_remaining[key] -= 1
                else:
                    visible.append(row)
            data = {"data": [{"event_json": r["event_json"]} for r in visible]}
        else:
            raise AssertionError(name)
        return {"content": [{"type": "text", "text": json.dumps(data)}]}


class EventStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.sleep_patch = patch("tomato_agent.storage.time.sleep")
        self.sleep = self.sleep_patch.start()

    def tearDown(self):
        self.sleep_patch.stop()
        self.temp.cleanup()

    def test_local_restart_temporal_cutoff_and_run_entity_isolation(self):
        with EventStore(self.root) as store:
            for item in (event(), event("future", elapsed=30, version=9),
                         event("other-run", run="other", version=99),
                         event("other-entity", entity="other", version=99)):
                store.append("memory_events", item)
        with EventStore(self.root) as store:
            self.assertIsNone(store.latest_memory("run-a", "tomato-1", 9))
            self.assertEqual(store.latest_memory("run-a", "tomato-1", 20)["event_id"], "m1")
            self.assertEqual(store.latest_memory("run-a", "tomato-1", 30)["event_id"], "future")
            self.assertEqual(len(store.existing_events("run-a")), 3)

    def test_dedup_and_conflicting_retry(self):
        with EventStore(self.root) as store:
            store.append("memory_events", event())
            store.append("memory_events", event())
            changed = event(); changed["state"] = {"changed": True}
            with self.assertRaises(StorageError):
                store.append("memory_events", changed)
        self.assertEqual(len((self.root / "events.jsonl").read_text().splitlines()), 1)

    def test_interrupted_tail_is_recovered_without_losing_prior_event(self):
        with EventStore(self.root) as store:
            store.append("memory_events", event())
        with (self.root / "events.jsonl").open("ab") as handle:
            handle.write(b'{"event_id":')
        with EventStore(self.root) as store:
            store.append("memory_events", event("m2", elapsed=20, version=2))
        with EventStore(self.root) as store:
            self.assertEqual(len(store.existing_events("run-a")), 2)

    def test_remote_restart_without_local_journal_and_no_future_leak(self):
        remote = FakeRemote()
        with patch("tomato_agent.storage._new_client", return_value=remote):
            with EventStore(self.root / "first", "rawtree") as store:
                store.append("memory_events", event())
                store.append("memory_events", event("future", elapsed=30, version=8))
                store.append("memory_events", event("other", run="other", version=9))
            with EventStore(self.root / "fresh", "rawtree") as restarted:
                memory = restarted.latest_memory("run-a", "tomato-1", 20)
                self.assertEqual(memory["event_id"], "m1")
                self.assertEqual(len(restarted.existing_events("run-a", "memory_events")), 2)
                restarted.append("memory_events", event())
            self.assertEqual(remote.insert_count, 3)
            self.assertTrue(any("elapsed_seconds <= 20.0" in sql for sql in remote.queries))

    def test_failure_retains_outbox_and_restart_flushes_it(self):
        remote = FakeRemote(); remote.fail_insert = True
        with patch("tomato_agent.storage._new_client", return_value=remote):
            with self.assertRaisesRegex(StorageError, "outbox retained") as caught:
                with EventStore(self.root, "rawtree") as store:
                    store.append("memory_events", event())
            self.assertNotIn("secret", str(caught.exception))
            self.assertTrue((self.root / "events.jsonl").exists())
            self.assertFalse((self.root / "acknowledgements.jsonl").exists())
            remote.fail_insert = False
            with EventStore(self.root, "rawtree") as store:
                store.flush()
                self.assertEqual(store.latest_memory("run-a", "tomato-1", 20)["state"], {"note": "m1"})
            self.assertEqual(remote.insert_count, 1)

    def test_plain_text_insert_ack_is_followed_by_exact_read_verification(self):
        remote = FakeRemote(); remote.plain_text_ack = True
        with patch("tomato_agent.storage._new_client", return_value=remote):
            with EventStore(self.root, "rawtree") as store:
                store.append("memory_events", event())
                self.assertEqual(store.latest_memory("run-a", "tomato-1", 20)["state"], {"note": "m1"})
        self.assertEqual(remote.insert_count, 1)
        self.assertTrue((self.root / "acknowledgements.jsonl").exists())

    def test_remote_error_does_not_fall_back_to_local_success(self):
        remote = FakeRemote()
        with patch("tomato_agent.storage._new_client", return_value=remote):
            with EventStore(self.root, "rawtree") as store:
                store.append("memory_events", event())
                remote.fail_query = True
                with self.assertRaises(StorageError):
                    store.latest_memory("run-a", "tomato-1", 20)

    def test_positive_table_cache_keeps_remote_verification_and_sees_new_table(self):
        remote = FakeRemote()
        # Unrelated table metadata must never turn into a contents query.
        remote.tables["apple_lha_memory_events"] = [{"do_not_read": True}]
        with patch("tomato_agent.storage._new_client", return_value=remote):
            with EventStore(self.root, "rawtree") as store:
                self.assertIsNone(store.latest_memory("new-run", "tomato-1", 20))
                self.assertEqual(remote.list_count, 1)
                # Simulate a table created after the initial missing result.
                remote.tables["tomato_lha_memory_events"] = []
                store.append("memory_events", event(run="new-run"))
                self.assertEqual(remote.list_count, 2)
                reads_after_insert = len(remote.queries)
                self.assertEqual(store.latest_memory("new-run", "tomato-1", 20)["event_id"], "m1")
                self.assertIsNone(store.latest_memory("unrelated-run", "tomato-1", 20))
                store.append("memory_events", event("m2", run="new-run", elapsed=20, version=2))
                self.assertEqual(remote.list_count, 2)
                self.assertGreater(len(remote.queries), reads_after_insert)
                self.assertEqual(remote.insert_count, 2)
                self.assertTrue(all("FROM tomato_lha_memory_events " in q for q in remote.queries))

    def test_newly_inserted_table_is_discovered_then_cached(self):
        remote = FakeRemote()
        with patch("tomato_agent.storage._new_client", return_value=remote):
            with EventStore(self.root, "rawtree") as store:
                store.append("memory_events", event())
                self.assertEqual(remote.list_count, 2)  # absent, then visible after insert
                store.append("memory_events", event("m2", elapsed=20, version=2))
                self.assertEqual(remote.list_count, 2)
                self.assertEqual(len(store.existing_events("run-a", "memory_events")), 2)

    def test_delayed_visibility_polls_reads_without_reinserting(self):
        remote = FakeRemote(); remote.visibility_delay_reads = 3
        with patch("tomato_agent.storage._new_client", return_value=remote):
            with EventStore(self.root, "rawtree") as store:
                store.append("memory_events", event())
                self.assertEqual(store.latest_memory("run-a", "tomato-1", 20)["event_id"], "m1")
        self.assertEqual(remote.insert_count, 1)
        self.assertEqual(self.sleep.call_count, 3)
        self.assertTrue((self.root / "acknowledgements.jsonl").exists())

    def test_expired_visibility_retains_outbox_and_pending_retry_waits_before_resend(self):
        remote = FakeRemote(); remote.visibility_delay_reads = 100
        with patch("tomato_agent.storage._new_client", return_value=remote):
            with self.assertRaisesRegex(StorageError, "bounded polling"):
                with EventStore(self.root, "rawtree") as store:
                    store.append("memory_events", event())
            self.assertEqual(remote.insert_count, 1)
            self.assertFalse((self.root / "acknowledgements.jsonl").exists())
            remote.visibility_remaining["m1"] = 3
            with EventStore(self.root, "rawtree") as restarted:
                restarted.flush()
                self.assertEqual(restarted.latest_memory("run-a", "tomato-1", 20)["event_id"], "m1")
            self.assertEqual(remote.insert_count, 1)
            self.assertTrue((self.root / "acknowledgements.jsonl").exists())

    def test_quoted_run_id_is_one_sql_literal(self):
        value = "run' OR 1=1 --\\suffix"
        quoted = _sql_string(value)
        self.assertRegex(quoted, r"^'(?:\\.|[^'\\])*'$" )
        remote = FakeRemote()
        with patch("tomato_agent.storage._new_client", return_value=remote):
            with EventStore(self.root, "rawtree") as store:
                store.append("memory_events", event(run=value))
                store.append("memory_events", event("other", run="unrelated"))
                self.assertEqual(len(store.existing_events(value)), 1)
        with self.assertRaises(ValueError):
            _sql_string("line\nbreak")


if __name__ == "__main__":
    unittest.main()
