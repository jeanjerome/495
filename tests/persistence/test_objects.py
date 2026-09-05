import os
import tempfile
import unittest
from pathlib import Path

from persistence import ObjectStore, Persisted, PersistenceErrorCode
from persistence.objects import digest_bytes


class ObjectStoreTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "repository"
        self.store = ObjectStore(self.root)

    def test_put_get_and_duplicate_preserve_exact_bytes(self):
        raw = b'{"a":1}\n'
        first = self.store.put(raw)
        self.assertIsInstance(first, Persisted)
        self.assertFalse(first.value.already_present)
        self.assertEqual(first.value.digest, digest_bytes(raw))
        duplicate = self.store.put(raw)
        self.assertTrue(duplicate.value.already_present)
        self.assertEqual(self.store.get(first.value.digest).value, raw)
        self.assertEqual(list((self.root / "objects/sha256").glob(".object-*")), [])

    def test_missing_invalid_and_corrupt_objects_are_refused(self):
        invalid = self.store.get("latest")
        self.assertEqual(invalid.code, PersistenceErrorCode.INVALID_DIGEST)
        missing_digest = "sha256:" + "0" * 64
        self.assertEqual(self.store.get(missing_digest).code, PersistenceErrorCode.OBJECT_MISSING)
        stored = self.store.put(b"original").value
        path = self.root / stored.relative_path
        path.write_bytes(b"modified")
        self.assertEqual(self.store.get(stored.digest).code, PersistenceErrorCode.OBJECT_CORRUPT)

    def test_existing_different_bytes_under_digest_are_never_replaced(self):
        raw = b"expected"
        digest = digest_bytes(raw)
        path = self.root / "objects/sha256" / digest.removeprefix("sha256:")
        path.parent.mkdir(parents=True)
        path.write_bytes(b"collision")
        refused = self.store.put(raw)
        self.assertEqual(refused.code, PersistenceErrorCode.OBJECT_COLLISION)
        self.assertEqual(path.read_bytes(), b"collision")

    def test_symbolic_link_at_object_path_is_refused(self):
        raw = b"target"
        digest = digest_bytes(raw)
        directory = self.root / "objects/sha256"
        directory.mkdir(parents=True)
        external = self.root / "external"
        external.write_bytes(raw)
        os.symlink(external, directory / digest.removeprefix("sha256:"))
        refusal = self.store.put(raw)
        self.assertEqual(refusal.code, PersistenceErrorCode.SYMLINK_REFUSED)
