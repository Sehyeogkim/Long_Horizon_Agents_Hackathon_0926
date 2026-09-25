import unittest
from tomato_agent.policy import choose_path, update_memory, LOW, HIGH


def cheap(anomaly="no", quality="usable", features=None, recommendation=LOW):
    return {"status": "success", "result": {"quality": quality,
        "evidence": "visible appearance", "change_level": "uncertain" if anomaly == "uncertain" else "stable",
        "recommendation": recommendation}}


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.obs = {"observation_id": "o2", "elapsed_seconds": 86400, "frame_uri": "frame.png"}
        self.memory = {"last_strong_elapsed_seconds": 0, "last_observation_elapsed_seconds": 0,
                       "previous_anomaly": "no", "previous_features": ["none"]}

    def test_every_low_path_preserves_strong_time_and_does_not_confirm_health(self):
        decision = choose_path(self.obs, cheap(), self.memory)
        self.assertEqual(decision["action"], LOW)
        state = update_memory(self.obs, cheap(), None, self.memory, decision)
        self.assertEqual(state["last_cheap_elapsed_seconds"], 86400)
        self.assertEqual(state["last_strong_elapsed_seconds"], 0)
        self.assertNotIn("healthy", state)

    def test_open_question_due_does_not_force_escalation(self):
        self.memory["open_questions"] = [{"status": "open", "due_elapsed_seconds": 172800}]
        self.assertEqual(choose_path(self.obs, cheap(), self.memory)["action"], LOW)
        self.obs["elapsed_seconds"] = 172800
        self.assertEqual(choose_path(self.obs, cheap(), self.memory)["action"], LOW)

    def test_blur_does_not_erase_due_question(self):
        self.memory["open_questions"] = [{"status": "open", "due_elapsed_seconds": 86400}]
        call = cheap("uncertain", "unusable")
        decision = choose_path(self.obs, call, self.memory)
        self.assertEqual(decision["action"], LOW)
        self.assertTrue(decision["review_required"])
        state = update_memory(self.obs, call, None, self.memory, decision)
        self.assertEqual(state["open_questions"][0]["status"], "open")
        self.assertEqual(state["last_strong_elapsed_seconds"], 0)

    def test_first_can_be_low_but_maxgap_invalid_and_uncertain_escalate(self):
        self.assertEqual(choose_path(self.obs, cheap(), {})["action"], LOW)
        self.assertEqual(choose_path(self.obs, cheap(), self.memory, max_gap_hours=24)["action"], HIGH)
        self.assertEqual(choose_path(self.obs, {"status": "error"}, self.memory)["action"], HIGH)
        self.assertEqual(choose_path(self.obs, cheap("uncertain"), self.memory)["action"], HIGH)

    def test_c_known_anomaly_and_b_no_semantic_memory(self):
        self.memory.update(previous_anomaly="yes", previous_features=["spot"], last_strong_anomaly="yes")
        call = cheap("yes", features=["spot"])
        self.assertEqual(choose_path(self.obs, call, self.memory, "C")["action"], LOW)
        self.assertEqual(choose_path(self.obs, call, self.memory, "B")["action"], LOW)
        changed = cheap("yes", features=["spot", "wrinkling"], recommendation=HIGH)
        self.assertEqual(choose_path(self.obs, changed, self.memory, "C")["action"], HIGH)

    def test_maxgap_anchors_first_observation_when_no_strong_exists(self):
        memory = {"first_observation_elapsed_seconds": 0}
        self.assertEqual(choose_path(self.obs, cheap(), memory, max_gap_hours=24)["action"], HIGH)

    def test_low_review_does_not_postpone_open_question(self):
        self.memory["open_questions"] = [{"status": "open", "question": "Does the mark persist?",
                                          "due_elapsed_seconds": 7200}]
        state = update_memory(self.obs, cheap(), None, self.memory,
                              {"action": LOW, "review_required": False})
        self.assertEqual(state["open_questions"][0]["due_elapsed_seconds"], 7200)
        self.assertEqual(state["open_questions"][0]["last_local_review_elapsed_seconds"], 86400)

    def test_invalid_recommendation_escalates(self):
        call = cheap(recommendation="IGNORE")
        self.assertEqual(choose_path(self.obs, call, self.memory)["action"], HIGH)

    def test_failed_strong_never_moves_precision_clock(self):
        state = update_memory(self.obs, cheap(), {"status": "error"}, self.memory,
                              {"action": HIGH, "review_required": False})
        self.assertEqual(state["last_strong_elapsed_seconds"], 0)

    def test_success_resolves_questions_without_diagnostic_label(self):
        self.memory["open_questions"] = [{"status": "open", "due_elapsed_seconds": 86400}]
        strong = {"status": "success", "result": {"visible_anomaly": "no", "evidence": "No visible concern",
                  "concern_open": False, "followup_after_hours": 72, "review_required": False}}
        state = update_memory(self.obs, cheap(), strong, self.memory,
                              {"action": HIGH, "review_required": False})
        self.assertEqual(state["open_questions"][0]["status"], "closed")
        self.assertEqual(state["last_strong_elapsed_seconds"], 86400)


if __name__ == "__main__":
    unittest.main()
