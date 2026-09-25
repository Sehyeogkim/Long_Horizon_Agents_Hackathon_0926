import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock
import urllib.error

from tomato_agent.models import GPT5Model, LiquidModel, load_api_key, estimate_gpt5_cost


class ModelsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)
        self.observation = {"frame_uri": "irrelevant.png", "label": "secret_future_label"}

    def tearDown(self):
        self.temp.cleanup()

    def response(self, text):
        return {"status": "completed", "output": [{"type": "message", "content": [
            {"type": "output_text", "text": text}]}], "usage": {
                "input_tokens": 1000, "output_tokens": 200,
                "input_tokens_details": {"cached_tokens": 400},
                "output_tokens_details": {"reasoning_tokens": 100}}}

    def valid_result(self):
        return {"visible_anomaly": "uncertain", "evidence": "Small dark mark",
                "concern_open": True, "followup_after_hours": 2, "review_required": False}

    @patch("tomato_agent.models._image_url", return_value="data:image/png;base64,AA")
    @patch("tomato_agent.models.load_api_key", return_value="DO_NOT_LOG_THIS_KEY")
    def test_malformed_output_still_counts_billed_usage(self, *_):
        with patch("tomato_agent.models._request_json", return_value=self.response("not JSON")):
            record = GPT5Model(self.path).analyze(self.observation)
        self.assertEqual(record["status"], "error")
        self.assertEqual(record["error"], "malformed_model_json")
        self.assertAlmostEqual(record["api_cost_usd_estimate"], .0028)
        self.assertEqual(record["usage"]["reasoning_tokens"], 100)
        self.assertNotIn("DO_NOT_LOG_THIS_KEY", (self.path / "model_calls.jsonl").read_text())

    @patch("tomato_agent.models._image_url", return_value="data:image/png;base64,AA")
    @patch("tomato_agent.models.load_api_key", return_value="test")
    def test_http_failure_not_retried_and_budget_consumed(self, *_):
        model = GPT5Model(self.path, max_calls=1)
        error = urllib.error.HTTPError("https://example.com?secret", 429, "secret", {}, None)
        with patch("tomato_agent.models._request_json", side_effect=error) as request:
            first = model.analyze(self.observation)
            second = model.analyze(self.observation)
        self.assertEqual(request.call_count, 1)
        self.assertEqual(first["error"], "http_429")
        self.assertIsNone(first["api_cost_usd_estimate"])
        self.assertEqual(second["error"], "call_budget_exhausted")
        self.assertNotIn("secret", (self.path / "model_calls.jsonl").read_text())

    @patch("tomato_agent.models._image_url", return_value="data:image/png;base64,AA")
    @patch("tomato_agent.models.load_api_key", return_value="test")
    def test_prompt_does_not_leak_labels_paths_or_unbounded_memory(self, *_):
        memory = {"summary": "x" * 5000, "evidence": "y" * 5000,
                  "future_label": "LEAKED", "all_history": "LEAKED"}
        with patch("tomato_agent.models._request_json", return_value=self.response(json.dumps(self.valid_result()))) as request:
            record = GPT5Model(self.path).analyze(self.observation, memory)
        payload = request.call_args.args[1]
        serialized = json.dumps(payload)
        self.assertEqual(record["status"], "success")
        self.assertNotIn("secret_future_label", serialized)
        self.assertNotIn("irrelevant.png", serialized)
        self.assertNotIn("LEAKED", serialized)
        self.assertNotIn("x" * 1201, serialized)
        self.assertNotIn("y" * 601, serialized)
        self.assertFalse(payload["store"])
        self.assertEqual(payload["model"], "gpt-5")

    @patch("tomato_agent.models._image_url", return_value="data:image/png;base64,AA")
    @patch("tomato_agent.models.load_api_key", return_value="test")
    def test_out_of_bounds_followup_rejected_with_usage(self, *_):
        result = self.valid_result()
        result["followup_after_hours"] = -1
        with patch("tomato_agent.models._request_json", return_value=self.response(json.dumps(result))):
            record = GPT5Model(self.path).analyze(self.observation)
        self.assertEqual(record["error"], "invalid_result_schema")
        self.assertIsNotNone(record["api_cost_usd_estimate"])

    def test_dotenv_is_literal_and_supports_both_names(self):
        env = self.path / ".env"
        env.write_text("OTHER=ignored\nexport OPEN_AI_API_KEY='$(do-not-execute)'\n")
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(load_api_key(env), "$(do-not-execute)")
        with patch.dict(os.environ, {"OPENAI_API_KEY": "preferred"}, clear=True):
            self.assertEqual(load_api_key(env), "preferred")

    def test_unknown_usage_is_not_free(self):
        self.assertIsNone(estimate_gpt5_cost({"input_tokens": 10, "output_tokens": 2, "cached_input_tokens": None}))

    @patch("tomato_agent.models._image_url", return_value="data:image/png;base64,AA")
    def test_liquid_invalid_feature_rejected(self, *_):
        model = LiquidModel(self.path)
        model.process = Mock()
        model.process.poll.return_value = None
        response = {"usage": {"prompt_tokens": 20, "completion_tokens": 30}, "choices": [{
            "finish_reason": "stop", "message": {"content": json.dumps({"visible_anomaly": "yes",
                "quality": "usable", "evidence": "A mark", "features": ["diagnosed_infection"]})}}]}
        with patch("tomato_agent.models._request_json", return_value=response) as request:
            record = model.observe(self.observation)
        self.assertEqual(record["error"], "invalid_result_schema")
        self.assertEqual(record["usage"]["output_tokens"], 30)
        self.assertEqual(record["api_cost_usd_estimate"], 0)
        self.assertNotIn("secret_future_label", json.dumps(request.call_args.args[1]))

    @patch("tomato_agent.models._image_url", side_effect=lambda path, resize=False: "data:image/png;base64," + path.name)
    def test_temporal_payload_has_ordered_pair_bounded_notes_and_timestamps(self, *_):
        model = LiquidModel(self.path)
        model.process = Mock()
        model.process.poll.return_value = None
        result = {"quality": "usable", "evidence": "Same surface",
                  "change_level": "stable", "recommendation": "LOW_COST_ONLY",
                  }
        response = {"usage": {"prompt_tokens": 500, "completion_tokens": 150}, "choices": [{
            "finish_reason": "stop", "message": {"content": json.dumps(result)}}]}
        observation = dict(self.observation, observation_id="now", elapsed_seconds=3600, observed_at=None)
        memory = {"previous_frame_uri": "before.png", "last_observation_id": "before",
                  "last_observation_elapsed_seconds": 0, "previous_observed_at": None,
                  "summary": "x" * 5000, "previous_evidence": "y" * 5000, "future_label": "LEAKED",
                  "open_questions": [{"question": "z" * 5000, "due_elapsed_seconds": 3000,
                                      "status": "open", "ground_truth": "LEAKED"}] * 8}
        with patch("tomato_agent.models._request_json", return_value=response) as request:
            record = model.observe(observation, memory)
        self.assertEqual(record["status"], "success")
        content = request.call_args.args[1]["messages"][0]["content"]
        images = [p["image_url"]["url"] for p in content if p["type"] == "image_url"]
        self.assertEqual(images, ["data:image/png;base64,before.png", "data:image/png;base64,irrelevant.png"])
        text = json.dumps([p for p in content if p["type"] == "text"])
        for forbidden in ("LEAKED", "secret_future_label", "x" * 901, "y" * 401, "z" * 251):
            self.assertNotIn(forbidden, text)
        self.assertEqual(record["input_context"]["previous"]["elapsed_seconds"], 0)
        self.assertIsNone(record["input_context"]["current"]["observed_at"])
        self.assertEqual(len(record["input_context"]["prior_notes"]["open_questions"]), 3)
        self.assertTrue(record["input_context"]["prior_notes"]["open_questions"][0]["due_now"])
        self.assertEqual(record["input_observation_ids"], ["before", "now"])
        memory["last_observation_elapsed_seconds"] = 3600
        with patch("tomato_agent.models._request_json") as request:
            record = model.observe(observation, memory)
        self.assertEqual(record["error"], "invalid_prior_time")
        request.assert_not_called()

    @patch("tomato_agent.models._image_url", return_value="data:image/png;base64,AA")
    def test_first_image_cannot_claim_temporal_change(self, *_):
        model = LiquidModel(self.path)
        model.process = Mock()
        model.process.poll.return_value = None
        result = {"quality": "usable", "evidence": "Clear surface",
                  "change_level": "stable", "recommendation": "LOW_COST_ONLY",
                  }
        response = {"usage": {"prompt_tokens": 50, "completion_tokens": 50}, "choices": [{
            "finish_reason": "stop", "message": {"content": json.dumps(result)}}]}
        with patch("tomato_agent.models._request_json", return_value=response):
            record = model.observe(dict(self.observation, elapsed_seconds=0))
        self.assertEqual(record["error"], "invalid_temporal_context")
        self.assertEqual(record["usage"]["output_tokens"], 50)

    def test_placeholder_evidence_is_not_a_valid_observation(self):
        from tomato_agent.models import _validate
        for placeholder in ("no_history", "no_evidence", "No evidence.", "stable", "unknown"):
            self.assertFalse(_validate({"quality": "usable", "change_level": "stable",
                             "evidence": placeholder, "recommendation": "LOW_COST_ONLY"}, "liquid"))

    def test_liquid_refuses_existing_server_without_termination(self):
        model = LiquidModel(self.path)
        with patch("tomato_agent.models.socket.socket") as socket_mock, patch("tomato_agent.models.subprocess.Popen") as popen:
            socket_mock.return_value.__enter__.return_value.connect_ex.return_value = 0
            with self.assertRaisesRegex(RuntimeError, "liquid_port_in_use"):
                model.__enter__()
        popen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
