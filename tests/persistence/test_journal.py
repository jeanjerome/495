import json
import tempfile
import unittest
from pathlib import Path

from persistence import Journal, Persisted, PersistenceErrorCode
from tests.persistence.support import draft


class JournalTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "repository"
        self.journal = Journal(self.root)

    def test_append_builds_consecutive_hash_chain(self):
        first = self.journal.append(draft())
        self.assertIsInstance(first, Persisted)
        second = self.journal.append(draft("command-2", 1))
        self.assertIsInstance(second, Persisted)
        events = second.value.events
        self.assertEqual(tuple(event.sequence for event in events), (1, 2))
        self.assertEqual(events[1].previous_hash, events[0].event_hash)
        self.assertEqual(events[1].state_version_after, 2)
        self.assertEqual(self.journal.read().value.events, events)
        for line in self.journal.path.read_bytes().splitlines():
            self.assertEqual(json.dumps(json.loads(line), ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode(), line)

    def test_corrupt_complete_line_blocks_without_quarantine(self):
        self.journal.append(draft())
        self.journal.append(draft("command-2", 1))
        lines = self.journal.path.read_bytes().splitlines(keepends=True)
        document = json.loads(lines[0])
        document["event_hash"] = "sha256:" + "f" * 64
        lines[0] = (json.dumps(document, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n").encode()
        self.journal.path.write_bytes(b"".join(lines))
        refusal = self.journal.read()
        self.assertEqual(refusal.code, PersistenceErrorCode.HASH_MISMATCH)
        self.assertEqual(list((self.root / "quarantine").iterdir()), [])

    def test_partial_tail_is_quarantined_and_journal_is_repaired(self):
        accepted = self.journal.append(draft()).value
        partial = b'{"partial":'
        with self.journal.path.open("ab") as stream:
            stream.write(partial)
        recovered = self.journal.read()
        self.assertIsInstance(recovered, Persisted)
        self.assertEqual(recovered.value.events, accepted.events)
        quarantine_path = self.root / recovered.value.quarantined_tail
        self.assertEqual(quarantine_path.read_bytes(), partial)
        self.assertTrue(self.journal.path.read_bytes().endswith(b"\n"))

    def test_complete_noncanonical_tail_is_corruption_not_partial_tail(self):
        self.journal.append(draft())
        document = json.loads(self.journal.path.read_bytes())
        self.journal.path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        refusal = self.journal.read()
        self.assertEqual(refusal.code, PersistenceErrorCode.JOURNAL_CORRUPT)
        self.assertEqual(list((self.root / "quarantine").iterdir()), [])

    def test_append_refuses_wrong_state_version_without_new_line(self):
        self.journal.append(draft())
        before = self.journal.path.read_bytes()
        refusal = self.journal.append(draft("command-2", 0))
        self.assertEqual(refusal.code, PersistenceErrorCode.STATE_VERSION_MISMATCH)
        self.assertEqual(self.journal.path.read_bytes(), before)
