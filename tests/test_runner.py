"""Offline replay checks. Fakes never start a server or make network requests."""
import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout

from PIL import Image

from tomato_agent.runner import append_durable, run
from tomato_agent.storage import EventStore


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        image = self.root / "fruit.png"
        Image.new("RGB", (8, 8), "red").save(image)
        self.rows = [{"dataset_id": "fixture", "sequence_id": "seq", "entity_id": "fruit",
            "observation_id": f"o{i}", "frame_uri": str(image),
            "frame_sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
            "elapsed_seconds": i * 3600, "label": "DO_NOT_SEND", "future_state": "DO_NOT_SEND",
            "disease_label": "DO_NOT_SEND", "ground_truth": "DO_NOT_SEND", "synthetic": True}
            for i in range(3)]
        self.manifest = self.root / "observations.jsonl"
        self.manifest.write_text("".join(json.dumps(row) + "\n" for row in self.rows))
        self.cheap_calls, self.strong_calls = [], []
        self.cheap_contexts = []
        self.cheap_memories = []
        self.first_recommendation = "HIGH_COST_ANALYSIS"
        self.fail_strong_once = False
        case = self

        class FakeLiquid:
            def __init__(self, output_dir):
                self.run_id = Path(output_dir).name

            def __enter__(self):
                case.cheap_contexts.append(self.run_id)
                return self

            def __exit__(self, *_):
                pass

            def observe(self, observation, memory=None):
                case.cheap_memories.append(copy.deepcopy(memory))
                case.cheap_calls.append((self.run_id, copy.deepcopy(observation)))
                return case.call("liquid", {"quality": "usable",
                                            "evidence": "No visible damage",
                                            "change_level": "stable" if memory and memory.get("previous_frame_uri") else "no_history",
                                            "recommendation": case.first_recommendation if observation["elapsed_seconds"] == 0 else "LOW_COST_ONLY"})

        class FakeStrong:
            def __init__(self, output_dir, max_calls):
                self.run_id, self.max_calls = Path(output_dir).name, max_calls

            def analyze(self, observation, memory=None):
                case.strong_calls.append((self.run_id, copy.deepcopy(observation), copy.deepcopy(memory), self.max_calls))
                if case.fail_strong_once:
                    case.fail_strong_once = False
                    return case.call("gpt-5", None, status="error")
                return case.call("gpt-5", {"visible_anomaly": "uncertain", "evidence": "Check again later",
                    "concern_open": observation["elapsed_seconds"] == 0,
                    "followup_after_hours": 2, "review_required": False})

        self.liquid_factory, self.strong_factory = FakeLiquid, FakeStrong

    def tearDown(self):
        self.temp.cleanup()

    def call(self, model, result, status="success"):
        import uuid
        return {"provider": model, "model": model, "status": status, "result": result,
                "call_id": uuid.uuid4().hex, "api_cost_usd_estimate": 0.001 if model == "gpt-5" else 0,
                "usage": {"input_tokens": 10, "output_tokens": 5, "cached_input_tokens": 0, "reasoning_tokens": 0},
                "latency_ms": 1, "error": None if status == "success" else "fake_error"}

    def replay(self, variant, **kwargs):
        with redirect_stdout(io.StringIO()):
            return run(self.manifest, self.root / "runs", variant=variant, run_id="fixture_" + variant,
                       backend="local", liquid_factory=self.liquid_factory,
                       strong_factory=self.strong_factory, **kwargs)

    def events(self, variant, kind=None):
        with EventStore(self.root / "runs" / ("fixture_" + variant) / "store", backend="local") as store:
            return store.existing_events("fixture_" + variant, kind)

    def test_a_all_strong_no_liquid_bc_each_observation_liquid(self):
        for variant in "ABC":
            self.replay(variant)
        self.assertEqual(sum(run_id == "fixture_A" for run_id, *_ in self.strong_calls), 3)
        self.assertNotIn("fixture_A", self.cheap_contexts)
        for variant in "BC":
            ids = [obs["observation_id"] for run_id, obs in self.cheap_calls if run_id == "fixture_" + variant]
            self.assertEqual(ids, ["o0", "o1", "o2"])

    def test_completed_resume_does_not_repeat_calls(self):
        self.replay("C", limit=1)
        first_cheap, first_strong = len(self.cheap_calls), len(self.strong_calls)
        self.replay("C", limit=1)
        self.assertEqual((len(self.cheap_calls), len(self.strong_calls)), (first_cheap, first_strong))
        self.replay("C")
        self.assertEqual([obs["observation_id"] for _, obs in self.cheap_calls], ["o0", "o1", "o2"])
        self.assertEqual([obs["observation_id"] for _, obs, *_ in self.strong_calls], ["o0"])
        self.assertEqual(len(self.events("C", "agent_events")), 3)

    def test_due_question_can_stay_low_and_runs_are_isolated(self):
        self.replay("C")
        self.replay("B")
        c = self.events("C", "agent_events")
        self.assertEqual(sum(e["action"] == "HIGH_COST_ANALYSIS" for e in c), 1)
        self.assertEqual(c[-1]["action"], "LOW_COST_ONLY")
        self.assertTrue(self.cheap_memories[2]["open_questions"])
        for run_id, _, memory, _ in self.strong_calls:
            if run_id == "fixture_B":
                self.assertIsNone(memory)
        for event in self.events("B", "memory_events"):
            self.assertNotIn("summary", event["state"])
            self.assertNotIn("open_questions", event["state"])

    def test_first_can_stay_low_and_next_uses_immediate_low_observation(self):
        self.first_recommendation = "LOW_COST_ONLY"
        self.replay("C")
        self.assertEqual(self.strong_calls, [])
        self.assertEqual(self.cheap_memories[1]["last_observation_id"], "o0")
        self.assertEqual(self.cheap_memories[2]["last_observation_id"], "o1")
        self.assertEqual(self.cheap_memories[2]["previous_frame_uri"], self.rows[1]["frame_uri"])
        self.assertEqual(self.cheap_memories[2]["first_observation_elapsed_seconds"], 0)
        self.assertNotIn("last_strong_elapsed_seconds", self.cheap_memories[2])

    def test_changed_implementation_blocks_resume(self):
        from unittest.mock import patch
        self.replay("A", limit=1)
        with patch("tomato_agent.runner.implementation_identity", return_value={"changed": True}):
            with self.assertRaisesRegex(ValueError, "configuration differs"):
                self.replay("A")
        self.assertEqual(len(self.strong_calls), 1)

    def test_manifest_labels_never_pass_to_models(self):
        self.replay("C")
        for call in self.cheap_calls + self.strong_calls:
            self.assertNotIn("DO_NOT_SEND", json.dumps(call))

    def test_crash_after_durable_call_reuses_paid_response(self):
        class FailMemoryOnce(EventStore):
            def append(self, kind, event):
                if kind == "memory_events":
                    raise RuntimeError("simulated interruption before memory write")
                super().append(kind, event)

        with self.assertRaisesRegex(RuntimeError, "simulated interruption"):
            self.replay("C", limit=1, store_factory=FailMemoryOnce)
        self.assertEqual(len(self.strong_calls), 1)
        self.replay("C", limit=1)
        self.assertEqual(len(self.strong_calls), 1)
        self.assertEqual(len(self.cheap_calls), 1)
        self.assertEqual(len(self.events("C", "agent_events")), 1)

    def test_paid_call_count_limit_survives_resume(self):
        self.replay("A", limit=1, max_gpt_calls=1)
        with self.assertRaisesRegex(RuntimeError, "budget limit"):
            self.replay("A", max_gpt_calls=1)
        self.assertEqual(len(self.strong_calls), 1)

    def test_failed_paid_call_counted_and_not_cached_as_success(self):
        self.fail_strong_once = True
        with self.assertRaisesRegex(RuntimeError, "GPT analysis failed"):
            self.replay("C", limit=1, max_gpt_calls=1)
        with self.assertRaisesRegex(RuntimeError, "budget limit"):
            self.replay("C", limit=1, max_gpt_calls=1)
        self.assertEqual(len(self.strong_calls), 1)
        self.assertEqual(len(self.cheap_calls), 1)
        self.assertEqual(len(self.events("C", "agent_events")), 0)

    def test_fsynced_adapter_response_recovered_before_event_append(self):
        original = self.strong_factory

        class JournalingStrong(original):
            def __init__(self, output_dir, max_calls):
                super().__init__(output_dir, max_calls)
                self.output_dir = Path(output_dir)

            def analyze(self, observation, memory=None):
                result = super().analyze(observation, memory)
                result.update(provider="openai", observation_id=observation["observation_id"],
                              request_attempt_id=observation["_request_attempt_id"])
                append_durable(self.output_dir / "model_calls.jsonl", result)
                return result

        class FailStrongEvent(EventStore):
            def append(self, kind, event):
                if kind == "model_calls" and event["tier"] == "strong":
                    raise RuntimeError("interrupted between adapter journal and event append")
                super().append(kind, event)

        self.strong_factory = JournalingStrong
        with self.assertRaisesRegex(RuntimeError, "interrupted between"):
            self.replay("C", limit=1, store_factory=FailStrongEvent)
        self.assertEqual(len(self.strong_calls), 1)
        self.assertEqual(len(self.events("C", "model_calls")), 1)  # Only cheap event durable.
        self.replay("C", limit=1)
        self.assertEqual(len(self.strong_calls), 1)
        self.assertEqual(len(self.cheap_calls), 1)
        paid = [e for e in self.events("C", "model_calls") if e["tier"] == "strong"]
        self.assertEqual(len(paid), 1)
        self.assertEqual(paid[0]["call"]["observation_id"], "o0")
        self.assertEqual(len(self.events("C", "agent_events")), 1)

    def test_unmatched_paid_intent_blocks_replay(self):
        original = self.strong_factory

        class LostResponse(original):
            def analyze(self, observation, memory=None):
                super().analyze(observation, memory)
                raise RuntimeError("paid request sent but response lost")

        self.strong_factory = LostResponse
        with self.assertRaisesRegex(RuntimeError, "response lost"):
            self.replay("A", limit=1)
        self.strong_factory = original
        with self.assertRaisesRegex(RuntimeError, "unknown outcome"):
            self.replay("A", limit=1)
        self.assertEqual(len(self.strong_calls), 1)

    def test_unknown_billing_blocks_next_cloud_request(self):
        original = self.strong_factory

        class UnknownCost(original):
            def analyze(self, observation, memory=None):
                result = super().analyze(observation, memory)
                result["api_cost_usd_estimate"] = None
                return result

        self.strong_factory = UnknownCost
        self.replay("A", limit=1)
        self.strong_factory = original
        with self.assertRaisesRegex(RuntimeError, "unknown billing"):
            self.replay("A")
        self.assertEqual(len(self.strong_calls), 1)

    def test_nested_and_case_variant_labels_never_reach_model(self):
        for row in self.rows:
            row["state"] = {"temperature": 20, "Disease_Label": "DO_NOT_SEND",
                            "history": [{"GROUND_TRUTH": "DO_NOT_SEND", "humidity": 50}],
                            "nested": {"future_state": "DO_NOT_SEND", "target": "DO_NOT_SEND"}}
        self.manifest.write_text("".join(json.dumps(row) + "\n" for row in self.rows))
        self.replay("C")
        for call in self.cheap_calls + self.strong_calls:
            self.assertNotIn("DO_NOT_SEND", json.dumps(call))
            self.assertEqual(call[1]["state"]["temperature"], 20)
            self.assertEqual(call[1]["state"]["history"], [{"humidity": 50}])


if __name__ == "__main__":
    unittest.main()
