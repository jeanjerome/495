import unittest

from domain.phases import TRANSITIONS
from domain.vocabulary import Phase
from tests.enumeration.sealed_reference import VOCABULARY, coverage, values


class PhasesEnumerationTest(unittest.TestCase):
    def test_phases(self):
        coverage("phases", {item.value for item in Phase}, values("phases"), 9)

    def test_phase_pairs(self):
        actual = {(left.value, right.value) for left in Phase for right in Phase}
        expected_values = values("phases")
        expected = {(left, right) for left in expected_values for right in expected_values}
        coverage("phase_pairs", actual, expected, 81)

    def test_transition_edges(self):
        actual = {
            (
                edge.origin.value,
                edge.target.value,
                edge.command.value,
                edge.gate.value if edge.gate else None,
                edge.kind.value,
            )
            for edge in TRANSITIONS
        }
        expected = {
            (entry["from"], entry["to"], entry["command"], entry.get("gate"), entry["kind"])
            for entry in VOCABULARY["phase_transitions"]["values"]
        }
        coverage("transition_edges", actual, expected, 25)
