from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

from harness495.errors import ChangeError
from harness495.process import (
    OUTPUT_LIMIT_BYTES,
    execute_process,
    strip_incomplete_utf8_sequence,
)


def python(script: str, *, timeout_seconds: int | None = 30, stdin: str | None = None) -> dict[str, Any]:
    return execute_process(
        [sys.executable, "-c", script],
        cwd=Path(tempfile.gettempdir()),
        environment={"PATH": os.environ["PATH"]},
        timeout_seconds=timeout_seconds,
        stdin=stdin,
    )


EXCESS = OUTPUT_LIMIT_BYTES + 1_000_000


class BoundedOutputTest(unittest.TestCase):
    def test_ordinary_output_is_kept_whole_and_not_truncated(self) -> None:
        result = python(
            "import sys; print('out'); print('err', file=sys.stderr); raise SystemExit(3)"
        )

        self.assertEqual("out\n", result["stdout"])
        self.assertEqual("err\n", result["stderr"])
        self.assertEqual(4, result["stdout_bytes"])
        self.assertEqual(4, result["stderr_bytes"])
        self.assertFalse(result["stdout_truncated"])
        self.assertFalse(result["stderr_truncated"])
        self.assertEqual(3, result["exit_code"])
        self.assertFalse(result["timed_out"])
        self.assertGreater(result["duration_seconds"], 0)

    def test_output_exactly_at_the_limit_is_not_truncated(self) -> None:
        result = python(
            f"import sys; sys.stdout.buffer.write(b'a' * {OUTPUT_LIMIT_BYTES})"
        )

        self.assertEqual(OUTPUT_LIMIT_BYTES, result["stdout_bytes"])
        self.assertEqual(OUTPUT_LIMIT_BYTES, len(result["stdout"]))
        self.assertFalse(result["stdout_truncated"])

    def test_large_stdout_keeps_a_prefix_and_reports_the_total(self) -> None:
        result = python(
            "import sys\n"
            f"sys.stdout.buffer.write(b'x' * {EXCESS})\n"
            "print('after', file=sys.stderr)\n"
            "raise SystemExit(5)"
        )

        self.assertEqual(EXCESS, result["stdout_bytes"])
        self.assertTrue(result["stdout_truncated"])
        self.assertEqual("x" * OUTPUT_LIMIT_BYTES, result["stdout"])
        self.assertEqual("after\n", result["stderr"])
        self.assertFalse(result["stderr_truncated"])
        self.assertEqual(5, result["exit_code"])
        self.assertFalse(result["timed_out"])

    def test_large_stderr_keeps_a_prefix_and_reports_the_total(self) -> None:
        result = python(
            "import sys\n"
            "print('before')\n"
            f"sys.stderr.buffer.write(b'e' * {EXCESS})\n"
        )

        self.assertEqual("before\n", result["stdout"])
        self.assertFalse(result["stdout_truncated"])
        self.assertEqual(EXCESS, result["stderr_bytes"])
        self.assertTrue(result["stderr_truncated"])
        self.assertEqual("e" * OUTPUT_LIMIT_BYTES, result["stderr"])
        self.assertEqual(0, result["exit_code"])

    def test_both_streams_beyond_the_limit_do_not_block_the_process(self) -> None:
        result = python(
            "import sys\n"
            "chunk_out, chunk_err = b'o' * 65536, b'E' * 65536\n"
            f"for _ in range({EXCESS // 65536 + 1}):\n"
            "    sys.stdout.buffer.write(chunk_out)\n"
            "    sys.stderr.buffer.write(chunk_err)\n"
            "raise SystemExit(0)",
            timeout_seconds=60,
        )

        self.assertFalse(result["timed_out"])
        self.assertEqual(0, result["exit_code"])
        self.assertTrue(result["stdout_truncated"])
        self.assertTrue(result["stderr_truncated"])
        self.assertGreater(result["stdout_bytes"], OUTPUT_LIMIT_BYTES)
        self.assertGreater(result["stderr_bytes"], OUTPUT_LIMIT_BYTES)
        self.assertEqual(OUTPUT_LIMIT_BYTES, len(result["stdout"]))
        self.assertEqual(OUTPUT_LIMIT_BYTES, len(result["stderr"]))

    def test_timeout_with_a_large_output_reports_both(self) -> None:
        result = python(
            "import sys, time\n"
            f"sys.stdout.buffer.write(b'y' * {EXCESS}); sys.stdout.flush()\n"
            "time.sleep(30)",
            timeout_seconds=2,
        )

        self.assertTrue(result["timed_out"])
        self.assertIsNone(result["exit_code"])
        self.assertTrue(result["stdout_truncated"])
        self.assertEqual(EXCESS, result["stdout_bytes"])
        self.assertEqual(OUTPUT_LIMIT_BYTES, len(result["stdout"]))
        self.assertLess(result["duration_seconds"], 20)

    def test_multibyte_sequence_cut_at_the_limit_is_dropped(self) -> None:
        # « € » occupe trois octets et la borne n’est pas un multiple de trois :
        # le préfixe brut se termine au milieu d’une séquence.
        self.assertEqual(1, OUTPUT_LIMIT_BYTES % 3)
        count = OUTPUT_LIMIT_BYTES // 3 + 10
        result = python(
            f"import sys; sys.stdout.buffer.write('€'.encode() * {count})"
        )

        self.assertTrue(result["stdout_truncated"])
        self.assertEqual("€" * (OUTPUT_LIMIT_BYTES // 3), result["stdout"])
        self.assertNotIn("�", result["stdout"])
        self.assertEqual(count * 3, result["stdout_bytes"])

    def test_invalid_bytes_are_replaced_rather_than_fatal(self) -> None:
        result = python("import sys; sys.stdout.buffer.write(b'ok\\xff\\xfe')")

        self.assertEqual("ok��", result["stdout"])
        self.assertFalse(result["stdout_truncated"])

    def test_stdin_is_delivered_even_when_larger_than_a_pipe_buffer(self) -> None:
        payload = "p" * 300_000 + "\n"
        result = python(
            "import sys; data = sys.stdin.read(); print(len(data))", stdin=payload
        )

        self.assertEqual(f"{len(payload)}\n", result["stdout"])
        self.assertEqual(0, result["exit_code"])

    def test_child_that_ignores_stdin_does_not_fail_the_execution(self) -> None:
        result = python("print('ignored')", stdin="x" * 300_000)

        self.assertEqual("ignored\n", result["stdout"])
        self.assertEqual(0, result["exit_code"])

    def test_missing_executable_is_a_process_error(self) -> None:
        with self.assertRaisesRegex(ChangeError, "impossible de lancer"):
            execute_process(
                ["tool-495-absent"],
                cwd=Path(tempfile.gettempdir()),
                environment={},
                timeout_seconds=1,
            )


class IncompleteSequenceTest(unittest.TestCase):
    def test_complete_prefixes_are_untouched(self) -> None:
        for data in (b"", b"abc", "é".encode(), "€".encode(), "😀".encode(), b"a\xff"):
            with self.subTest(data=data):
                self.assertEqual(data, strip_incomplete_utf8_sequence(data))

    def test_incomplete_sequences_are_removed(self) -> None:
        cases = {
            b"ab" + "é".encode()[:1]: b"ab",
            b"ab" + "€".encode()[:1]: b"ab",
            b"ab" + "€".encode()[:2]: b"ab",
            b"ab" + "😀".encode()[:3]: b"ab",
            "😀".encode()[:1]: b"",
        }
        for data, expected in cases.items():
            with self.subTest(data=data):
                self.assertEqual(expected, strip_incomplete_utf8_sequence(data))


if __name__ == "__main__":
    unittest.main()
