import unittest

from domain.invalidation import invalidated_by
from domain.links import LinkGraph, add_link
from domain.outcomes import Accepted, RefusalCode
from domain.vocabulary import ChangeKind, Gate, LinkType
from tests.unit.support import ref


class LinksAndInvalidationTest(unittest.TestCase):
    def test_link_types_are_modeled_and_unknown_type_is_refused(self):
        self.assertTrue(LinkType.DEPENDS_ON.executory)
        self.assertFalse(LinkType.RELATED_TO.executory)
        refused = add_link(LinkGraph(), ref("A"), ref("B"), "unknown")
        self.assertEqual(refused.code, RefusalCode.UNKNOWN_LINK_TYPE)

    def test_dependency_cycle_is_refused_with_ordered_nodes(self):
        a, b, c = ref("A"), ref("B"), ref("C")
        graph = add_link(LinkGraph(), a, b, LinkType.DEPENDS_ON).value
        graph = add_link(graph, b, c, LinkType.DEPENDS_ON).value
        refused = add_link(graph, c, a, LinkType.DEPENDS_ON)
        self.assertEqual(refused.code, RefusalCode.DEPENDENCY_CYCLE)
        self.assertEqual(refused.details, ("C", "A", "B", "C"))
        self.assertIs(refused.state, graph)

    def test_related_cycles_are_accepted_and_informational_changes_invalidate_nothing(self):
        a, b = ref("A"), ref("B")
        graph = add_link(LinkGraph(), a, b, LinkType.RELATED_TO).value
        self.assertIsInstance(add_link(graph, b, a, LinkType.RELATED_TO), Accepted)
        self.assertEqual(invalidated_by(ChangeKind.UNCONSUMED_RELATED_TO_NOTE), frozenset())
        self.assertEqual(
            invalidated_by(ChangeKind.CANDIDATE), frozenset((Gate.G3, Gate.G4))
        )
        for change in ChangeKind:
            self.assertEqual(invalidated_by(change), invalidated_by(change))
