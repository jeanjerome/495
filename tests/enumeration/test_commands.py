import unittest

from domain.commands import TRANSITION_ARITY
from domain.vocabulary import CommandName
from tests.enumeration.sealed_reference import coverage, values


class CommandsEnumerationTest(unittest.TestCase):
    def test_commands(self):
        actual = {item.value for item in CommandName}
        self.assertEqual({name for name, _ in TRANSITION_ARITY}, set(CommandName))
        coverage("commands", actual, values("commands"), 12)
