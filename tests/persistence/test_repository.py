import threading
import tempfile
import unittest
from pathlib import Path

from persistence import LocalRepository, Persisted, PersistenceErrorCode, thaw_json


class LocalRepositoryTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "repository"
        self.repository = LocalRepository(self.root)

    def execute(self, command_id="command-1", version=0, command=None, result=None, objects=()):
        return self.repository.execute(
            command_id=command_id,
            expected_state_version=version,
            command=command or {"name": "CreateIncrement"},
            result=result or {"accepted": True},
            object_writes=objects,
        )

    def test_same_command_is_replayed_without_new_event(self):
        first = self.execute()
        replayed = self.execute(result={"accepted": False})
        self.assertIsInstance(first, Persisted)
        self.assertIsInstance(replayed, Persisted)
        self.assertFalse(first.value.replayed)
        self.assertTrue(replayed.value.replayed)
        self.assertEqual(replayed.value.projection.sequence, 1)
        self.assertEqual(thaw_json(replayed.value.command.result), {"accepted": True})
        self.assertEqual(len(self.repository.journal.path.read_bytes().splitlines()), 1)

    def test_same_identifier_with_different_command_is_refused(self):
        self.execute()
        before = self.repository.journal.path.read_bytes()
        refusal = self.execute(command={"name": "CloseIncrement"})
        self.assertEqual(refusal.code, PersistenceErrorCode.COMMAND_CONFLICT)
        self.assertEqual(self.repository.journal.path.read_bytes(), before)

    def test_state_version_mismatch_precedes_object_writes(self):
        refusal = self.execute(version=1, objects=(b"must-not-be-written",))
        self.assertEqual(refusal.code, PersistenceErrorCode.STATE_VERSION_MISMATCH)
        object_directory = self.root / "objects/sha256"
        self.assertFalse(object_directory.exists())

    def test_reconstruction_is_repeatable_and_verifies_objects(self):
        self.execute(objects=(b"object",))
        first = self.repository.reconstruct()
        second = LocalRepository(self.root).reconstruct()
        self.assertEqual(first, second)
        digest = first.value.object_digests[0]
        object_path = self.root / "objects/sha256" / digest.removeprefix("sha256:")
        object_path.unlink()
        refusal = self.repository.reconstruct()
        self.assertEqual(refusal.code, PersistenceErrorCode.OBJECT_MISSING)
        self.assertIsInstance(self.repository.reconstruct(verify_objects=False), Persisted)

    def test_two_writers_with_same_version_cannot_both_append(self):
        barrier = threading.Barrier(2)
        results = []

        def write(command_id):
            repository = LocalRepository(self.root)
            barrier.wait()
            results.append(
                repository.execute(
                    command_id=command_id,
                    expected_state_version=0,
                    command={"name": command_id},
                    result={"accepted": True},
                )
            )

        threads = (
            threading.Thread(target=write, args=("command-a",)),
            threading.Thread(target=write, args=("command-b",)),
        )
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=5)
            self.assertFalse(thread.is_alive())
        self.assertEqual(sum(isinstance(item, Persisted) for item in results), 1)
        self.assertEqual(
            sum(getattr(item, "code", None) is PersistenceErrorCode.STATE_VERSION_MISMATCH for item in results),
            1,
        )
        self.assertEqual(self.repository.reconstruct().value.sequence, 1)
