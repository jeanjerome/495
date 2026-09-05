import unittest

from domain.outcomes import Accepted, RefusalCode
from domain.revisions import RevisionHistory, next_revision, record_revision
from domain.sealing import SealRegistry, digest_bytes, digest_of, seal
from tests.unit.support import ref


class RevisionsAndSealingTest(unittest.TestCase):
    def test_revisions_are_consecutive_from_one(self):
        history = RevisionHistory()
        self.assertEqual(next_revision(history, "A"), 1)
        for revision in (1, 2, 3):
            result = record_revision(history, "A", revision)
            self.assertIsInstance(result, Accepted)
            history = result.value
        for revision in (3, 5, 0):
            refused = record_revision(history, "A", revision)
            self.assertEqual(refused.code, RefusalCode.NON_CONSECUTIVE_REVISION)
            self.assertIs(refused.state, history)

    def test_sealing_uses_exact_bytes_and_is_immutable(self):
        raw = b'{"a":1}\n'
        first = ref("A", 1, raw)
        registry = SealRegistry()
        mismatch = seal(registry, first, b'{"a": 1}\n')
        self.assertEqual(mismatch.code, RefusalCode.DIGEST_MISMATCH)
        self.assertIs(mismatch.state, registry)
        sealed = seal(registry, first, raw).value
        duplicate = seal(sealed, ref("A", 1, b"other"), b"other")
        self.assertEqual(duplicate.code, RefusalCode.SEALED_ARTIFACT)
        self.assertIs(duplicate.state, sealed)
        second = ref("A", 2, b"next")
        newer = seal(sealed, second, b"next").value
        self.assertEqual(digest_of(newer, "A", 1), digest_bytes(raw))
