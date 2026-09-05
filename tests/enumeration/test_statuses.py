import unittest

from domain.vocabulary import OperationalStatus
from tests.enumeration.sealed_reference import coverage, values


class StatusesEnumerationTest(unittest.TestCase):
    def test_operational_statuses(self):
        coverage(
            "operational_statuses",
            {item.value for item in OperationalStatus},
            values("operational_statuses"),
            5,
        )
