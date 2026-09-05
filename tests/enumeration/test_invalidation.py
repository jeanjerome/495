import unittest

from domain.invalidation import invalidated_by
from domain.vocabulary import ChangeKind
from tests.enumeration.sealed_reference import VOCABULARY, coverage


class InvalidationEnumerationTest(unittest.TestCase):
    def test_invalidation_rules(self):
        expected = {
            "mandatory_requirement_or_scenario",
            "decision_or_interface_contract",
            "policy_verifier_environment_or_baseline",
            "candidate",
            "destination_branch_advanced",
            "unconsumed_related_to_note",
        }
        actual = {item.value for item in ChangeKind}
        coverage("invalidation_rules", actual, expected, 6)
        self.assertEqual(len(VOCABULARY["invalidation_rules"]["values"]), 6)
        for change in ChangeKind:
            self.assertIsInstance(invalidated_by(change), frozenset)
