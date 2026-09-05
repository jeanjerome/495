import unittest

from domain.attempts import allowed_attempt_transitions, finish_reason_triggers
from domain.vocabulary import AttemptPhase, AttemptStateName, FinishReason
from tests.enumeration.sealed_reference import VOCABULARY, coverage, values


class AttemptsEnumerationTest(unittest.TestCase):
    def test_attempt_states(self):
        coverage("attempt_states", {item.value for item in AttemptStateName}, values("attempt_states"), 3)

    def test_attempt_state_pairs(self):
        actual = {(left.value, right.value) for left in AttemptStateName for right in AttemptStateName}
        expected_values = values("attempt_states")
        expected = {(left, right) for left in expected_values for right in expected_values}
        coverage("attempt_state_pairs", actual, expected, 9)
        expected_transitions = {
            (item["from"], item["to"])
            for item in VOCABULARY["attempt_states"]["transitions"]
        }
        self.assertEqual(
            {(left.value, right.value) for left, right in allowed_attempt_transitions()},
            expected_transitions,
        )

    def test_attempt_finish_reasons(self):
        actual = {item.value for item in FinishReason}
        coverage("attempt_finish_reasons", actual, values("attempt_finish_reasons"), 6)
        self.assertEqual({reason for reason, _ in finish_reason_triggers()}, set(FinishReason))

    def test_attempt_entry_conditions(self):
        actual = {item.value for item in AttemptPhase}
        expected = {
            item["attempt_phase"]
            for item in VOCABULARY["attempt_entry_conditions"]["values"]
        }
        coverage("attempt_entry_conditions", actual, expected, 5)

    def test_attempt_exit_conditions(self):
        actual = {item.value for item in AttemptPhase}
        expected = {
            item["attempt_phase"]
            for item in VOCABULARY["attempt_exit_conditions"]["values"]
        }
        coverage("attempt_exit_conditions", actual, expected, 5)
