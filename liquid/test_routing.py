import unittest
from routing import choose_action

class RoutingTests(unittest.TestCase):
    def test_observed_contradictory_output_escalates(self):
        # The local model observed a large brown damaged area but suggested routine observation.
        self.assertEqual(choose_action({'visible_anomaly': 'yes', 'next_action': 'routine_observation'}), 'strong_analysis')

    def test_memory_survives_model_dismissal(self):
        result = {'visible_anomaly': 'no', 'next_action': 'routine_observation'}
        self.assertEqual(choose_action(result, unresolved_concern=True), 'strong_analysis')
        self.assertEqual(choose_action(result, review_due=True), 'strong_analysis')
        self.assertEqual(choose_action(result), 'routine_observation')

    def test_uncertain_malformed_and_retake(self):
        for result in (None, {}, {'visible_anomaly': 'uncertain'}, {'visible_anomaly': 'no'}):
            self.assertEqual(choose_action(result), 'strong_analysis')
        self.assertEqual(choose_action({'visible_anomaly': 'no', 'next_action': 'retake_photo'}), 'retake_photo')

if __name__ == '__main__':
    unittest.main()
