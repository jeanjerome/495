import unittest
from dataclasses import replace

from domain.state import IntegrationIntent, has_unreconciled_external_effect, with_status
from domain.vocabulary import OperationalStatus, Phase
from tests.unit.support import ref, state


class StateTest(unittest.TestCase):
    def test_phase_and_status_are_independent(self):
        for phase in Phase:
            original = state(phase)
            for status in OperationalStatus:
                changed = with_status(original, status)
                self.assertEqual(changed.phase, phase)
                self.assertEqual(changed.status, status)

    def test_unreconciled_predicate_covers_both_sources(self):
        self.assertFalse(has_unreconciled_external_effect(state()))
        self.assertTrue(
            has_unreconciled_external_effect(
                replace(state(), other_unreconciled_external_effect=True)
            )
        )
        with_intent = state()
        with_intent = replace(with_intent, integration_intent=IntegrationIntent(ref("candidate"), "main"))
        self.assertTrue(has_unreconciled_external_effect(with_intent))
        self.assertFalse(has_unreconciled_external_effect(replace(with_intent, integration_intent=IntegrationIntent(ref("candidate"), "main", True))))
