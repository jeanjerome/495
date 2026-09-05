import math
import unittest

from persistence import JsonArray, JsonObject, canonical_digest, freeze_json, thaw_json
from persistence.canonical import InvalidJsonValue


class CanonicalJsonTest(unittest.TestCase):
    def test_objects_are_deeply_immutable_and_key_order_is_canonical(self):
        first = freeze_json({"b": [2, {"x": True}], "a": 1})
        second = freeze_json({"a": 1, "b": [2, {"x": True}]})
        self.assertIsInstance(first, JsonObject)
        self.assertIsInstance(dict(first.items)["b"], JsonArray)
        self.assertEqual(first, second)
        self.assertEqual(canonical_digest(first), canonical_digest(second))
        self.assertEqual(thaw_json(first), {"a": 1, "b": [2, {"x": True}]})

    def test_non_json_and_non_finite_values_are_refused(self):
        for value in ({1: "key"}, {"x": object()}, math.inf, math.nan):
            with self.subTest(value=repr(value)):
                with self.assertRaises(InvalidJsonValue):
                    freeze_json(value)
