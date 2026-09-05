import unittest

from domain.vocabulary import ArtifactKind, CloseReason, LinkType
from tests.enumeration.sealed_reference import VOCABULARY, coverage, values


class ArtifactsEnumerationTest(unittest.TestCase):
    def test_artifact_kinds(self):
        coverage("artifact_kinds", {item.value for item in ArtifactKind}, values("artifact_kinds"), 13)

    def test_link_types(self):
        expected = set(VOCABULARY["link_types"]["executory"]) | set(VOCABULARY["link_types"]["informational"])
        coverage("link_types", {item.value for item in LinkType}, expected, 6)

    def test_close_reasons(self):
        coverage("close_reasons", {item.value for item in CloseReason}, values("close_reasons"), 5)
