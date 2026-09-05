import unittest

from domain.vocabulary import Gate, GateVerdict
from policy import PolicyOperator
from validation import FactState
from tests.enumeration.sealed_reference import coverage


class DecisionEngineEnumerationTest(unittest.TestCase):
    def test_policy_operators(self):
        expected = {
            "all_of", "any_of", "check_passed", "approval_present",
            "artifact_present", "digest_matches", "capability_satisfied",
            "within_budget",
        }
        coverage("policy_operators", {item.value for item in PolicyOperator}, expected, 8)

    def test_fact_states(self):
        expected = {"SATISFIED", "VIOLATED", "UNRESOLVED"}
        coverage("fact_states", {item.value for item in FactState}, expected, 3)

    def test_gate_verdicts(self):
        expected = {"PASS", "FAIL", "INDETERMINATE"}
        coverage("gate_verdicts", {item.value for item in GateVerdict}, expected, 3)

    def test_gates(self):
        expected = {"G0", "G1", "G2", "G3", "G4", "G5"}
        coverage("gates", {item.value for item in Gate}, expected, 6)
