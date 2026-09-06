from __future__ import annotations

import contextlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from typing import Any

from harness495.cli import EXIT_CODES, error_result, exit_code_for, main
from harness495.errors import ChangeError, ConfigurationError
from harness495.serialization import result_bytes

from tests.test_run_change import FAKE_CODEX


ROOT = Path(__file__).resolve().parent.parent


def comparable(document: dict[str, Any]) -> str:
    """Neutralise les durées et les chemins temporaires propres à une exécution."""

    text = json.dumps(document, sort_keys=True)
    text = re.sub(r'"duration_seconds": [0-9.]+', '"duration_seconds": 0', text)
    return re.sub(r"495-run-[^/]+", "495-run-X", text)


class CommandLineTest(unittest.TestCase):
    """Exécute la commande `495` comme un processus, avec un dépôt Git temporaire.

    Le double de Codex enregistre chaque invocation dans un journal et sert de
    sandbox : il exécute la commande reçue après `--` dans le dépôt cible.
    """

    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.repository = self.base / "application"
        self.repository.mkdir()
        self.log = self.base / "codex-invocations.log"
        fake_codex = self.base / "codex"
        fake_codex.write_text(
            f"#!{sys.executable}\n" + textwrap.dedent(FAKE_CODEX), encoding="utf-8"
        )
        fake_codex.chmod(0o755)
        self.contract = {
            "version": 1,
            "environment": ["FAKE_CODEX_LOG", "FAKE_CODEX_MODE", "PATH"],
            "checks": [
                {
                    "name": "result-present",
                    "command": [
                        sys.executable,
                        "-c",
                        "from pathlib import Path; "
                        "raise SystemExit(0 if Path('result.txt').exists() else 5)",
                    ],
                    "timeout_seconds": 5,
                    "filesystem": "read-only",
                }
            ],
        }
        self.contract_path = self.repository / "495.json"
        self.contract_path.write_text(json.dumps(self.contract), encoding="utf-8")
        (self.repository / "README.md").write_text("fixture\n", encoding="utf-8")
        self.git("init", "-b", "main")
        self.git("add", "README.md", "495.json")
        self.commit("test: initialize fixture")

    def git(self, *arguments: str) -> str:
        return subprocess.run(
            ["git", *arguments],
            cwd=self.repository,
            check=True,
            capture_output=True,
            text=True,
        ).stdout

    def commit(self, message: str) -> None:
        self.git(
            "-c",
            "user.name=495 tests",
            "-c",
            "user.email=tests@localhost",
            "commit",
            "-m",
            message,
        )

    def head(self) -> str:
        return self.git("rev-parse", "HEAD").strip()

    def add_candidate(self) -> None:
        (self.repository / "result.txt").write_text("candidate\n", encoding="utf-8")

    def run_cli(
        self,
        *arguments: str,
        mode: str = "unauthenticated",
        cwd: Path | None = None,
        codex_on_path: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment.pop("CODEX_HOME", None)
        if codex_on_path:
            environment["PATH"] = f"{self.base}{os.pathsep}{environment['PATH']}"
        else:
            empty = self.base / "empty-bin"
            empty.mkdir(exist_ok=True)
            environment["PATH"] = str(empty)
        environment["PYTHONPATH"] = str(ROOT / "src")
        environment["FAKE_CODEX_LOG"] = str(self.log)
        environment["FAKE_CODEX_MODE"] = mode
        return subprocess.run(
            [sys.executable, "-m", "harness495.cli", *arguments],
            cwd=cwd or ROOT,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )

    def codex_invocations(self) -> list[list[str]]:
        if not self.log.exists():
            return []
        return [
            json.loads(line)
            for line in self.log.read_text(encoding="utf-8").splitlines()
            if line
        ]

    def single_document(self, completed: subprocess.CompletedProcess[str]) -> dict[str, Any]:
        self.assertEqual("", completed.stderr)
        self.assertTrue(completed.stdout.startswith('{\n  "'), completed.stdout)
        self.assertTrue(completed.stdout.endswith("}\n"), completed.stdout)
        document = json.loads(completed.stdout)
        self.assertEqual(1, document["version"])
        return document

    def test_verify_reports_a_verified_candidate(self) -> None:
        self.add_candidate()

        completed = self.run_cli("verify", "--repository", str(self.repository))

        self.assertEqual(0, completed.returncode, completed.stderr)
        result = self.single_document(completed)
        self.assertEqual("candidate_verified", result["outcome"])
        self.assertEqual("verify", result["command"])
        self.assertEqual("HEAD", result["reference"])
        self.assertEqual(self.head(), result["baseline"])
        self.assertEqual(self.head(), result["head"])
        self.assertEqual(
            [("result.txt", "?")],
            [(item["path"], item["status"]) for item in result["candidate"]["files"]],
        )
        self.assertEqual("PASS", result["checks"][0]["status"])
        self.assertEqual(0, result["checks"][0]["exit_code"])
        self.assertEqual("read-only", result["checks"][0]["sandbox"]["filesystem"])
        self.assertEqual([], result["violations"])
        self.assertEqual([], result["limitations"])
        invocations = self.codex_invocations()
        self.assertTrue(invocations)
        self.assertTrue(all(call[0] == "sandbox" for call in invocations), invocations)
        self.assertNotIn(["login", "status"], invocations)

    def test_verify_defaults_to_the_current_directory_and_its_contract(self) -> None:
        self.add_candidate()

        completed = self.run_cli("verify", cwd=self.repository)

        self.assertEqual(0, completed.returncode, completed.stderr)
        result = self.single_document(completed)
        self.assertEqual("candidate_verified", result["outcome"])
        self.assertTrue(result["contract_digest"].startswith("sha256:"))

    def test_verify_reports_a_failed_control(self) -> None:
        (self.repository / "README.md").write_text("edited\n", encoding="utf-8")

        completed = self.run_cli("verify", "--repository", str(self.repository))

        self.assertEqual(1, completed.returncode, completed.stderr)
        result = self.single_document(completed)
        self.assertEqual("candidate_failed", result["outcome"])
        self.assertEqual("FAIL", result["checks"][0]["status"])
        self.assertEqual(5, result["checks"][0]["exit_code"])
        self.assertEqual(
            [("README.md", "M")],
            [(item["path"], item["status"]) for item in result["candidate"]["files"]],
        )

    def test_verify_without_candidate_runs_no_control(self) -> None:
        completed = self.run_cli("verify", "--repository", str(self.repository))

        self.assertEqual(4, completed.returncode, completed.stderr)
        result = self.single_document(completed)
        self.assertEqual("no_candidate", result["outcome"])
        self.assertIsNone(result["candidate"])
        self.assertEqual([], result["checks"])
        self.assertEqual([], result["violations"])
        self.assertEqual(1, len(result["limitations"]))
        self.assertIn(self.head(), result["limitations"][0])
        self.assertIn("HEAD~1", result["limitations"][0])
        invocations = self.codex_invocations()
        self.assertTrue(invocations)
        self.assertTrue(
            all(call[0] == "sandbox" and call[-2:] == ["-c", "pass"] for call in invocations),
            invocations,
        )

    def test_verify_with_an_earlier_baseline_covers_committed_work(self) -> None:
        initial = self.head()
        self.add_candidate()
        self.git("add", "result.txt")
        self.commit("test: commit the candidate")

        completed = self.run_cli(
            "verify", "--repository", str(self.repository), "--baseline", "HEAD~1"
        )

        self.assertEqual(0, completed.returncode, completed.stderr)
        result = self.single_document(completed)
        self.assertEqual("candidate_verified", result["outcome"])
        self.assertEqual("HEAD~1", result["reference"])
        self.assertEqual(initial, result["baseline"])
        self.assertEqual(self.head(), result["head"])
        self.assertEqual(
            [("result.txt", "A")],
            [(item["path"], item["status"]) for item in result["candidate"]["files"]],
        )

    def test_verify_rejects_a_baseline_outside_the_head_lineage(self) -> None:
        self.git("checkout", "-q", "-b", "other")
        (self.repository / "other.txt").write_text("other\n", encoding="utf-8")
        self.git("add", "other.txt")
        self.commit("test: diverge")
        self.git("checkout", "-q", "main")
        self.add_candidate()

        completed = self.run_cli(
            "verify", "--repository", str(self.repository), "--baseline", "other"
        )

        self.assertEqual(2, completed.returncode, completed.stderr)
        result = self.single_document(completed)
        self.assertEqual("execution_impossible", result["outcome"])
        self.assertEqual("verify", result["command"])
        self.assertIn("n’est pas un ancêtre de HEAD", result["error"]["message"])
        self.assertEqual([], self.codex_invocations())

    def test_invalid_contract_is_a_configuration_error(self) -> None:
        self.add_candidate()
        self.contract["checks"][0]["filesystem"] = "anything"
        self.contract_path.write_text(json.dumps(self.contract), encoding="utf-8")

        completed = self.run_cli("verify", "--repository", str(self.repository))

        self.assertEqual(2, completed.returncode, completed.stderr)
        result = self.single_document(completed)
        self.assertEqual("configuration_invalid", result["outcome"])
        self.assertEqual("verify", result["command"])
        self.assertEqual("configuration", result["error"]["kind"])
        self.assertIn("filesystem", result["error"]["message"])
        self.assertEqual({"command", "error", "outcome", "version"}, set(result))
        self.assertEqual([], self.codex_invocations())

    def test_missing_contract_makes_execution_impossible(self) -> None:
        self.add_candidate()
        self.contract_path.unlink()

        completed = self.run_cli("verify", "--repository", str(self.repository))

        self.assertEqual(2, completed.returncode, completed.stderr)
        result = self.single_document(completed)
        self.assertEqual("execution_impossible", result["outcome"])
        self.assertIn("contrat absent", result["error"]["message"])

    def test_unavailable_sandbox_is_reported_before_any_control(self) -> None:
        self.add_candidate()

        completed = self.run_cli(
            "verify", "--repository", str(self.repository), mode="sandbox_unavailable"
        )

        self.assertEqual(2, completed.returncode, completed.stderr)
        result = self.single_document(completed)
        self.assertEqual("execution_impossible", result["outcome"])
        self.assertIn("sandbox read-only indisponible", result["error"]["message"])
        self.assertEqual(1, len(self.codex_invocations()))

    def test_missing_codex_makes_execution_impossible(self) -> None:
        self.add_candidate()

        completed = self.run_cli(
            "verify", "--repository", str(self.repository), codex_on_path=False
        )

        self.assertEqual(2, completed.returncode, completed.stderr)
        result = self.single_document(completed)
        self.assertEqual("execution_impossible", result["outcome"])
        self.assertIn("codex est absent de PATH", result["error"]["message"])

    def test_legacy_invocation_and_change_produce_the_same_document(self) -> None:
        request_path = self.base / "request.md"
        request_path.write_text("Create the result file.\n", encoding="utf-8")
        codex_home = self.base / "codex-home"
        codex_home.mkdir()
        options = [
            "--repository",
            str(self.repository),
            "--contract",
            str(self.contract_path),
            "--codex-home",
            str(codex_home),
            "--request-file",
            str(request_path),
        ]

        legacy = self.run_cli(*options, mode="success")
        (self.repository / "result.txt").unlink()
        explicit = self.run_cli("change", *options, mode="success")

        self.assertEqual(0, legacy.returncode, legacy.stderr)
        self.assertEqual(0, explicit.returncode, explicit.stderr)
        legacy_result = self.single_document(legacy)
        explicit_result = self.single_document(explicit)
        self.assertEqual("candidate_verified", legacy_result["outcome"])
        self.assertEqual("change", legacy_result["command"])
        self.assertEqual(comparable(legacy_result), comparable(explicit_result))
        self.assertIn(["login", "status"], self.codex_invocations())

    def test_non_positive_agent_timeout_makes_execution_impossible(self) -> None:
        completed = self.run_cli(
            "--repository",
            str(self.repository),
            "--contract",
            str(self.contract_path),
            "--codex-home",
            str(self.base),
            "--request-file",
            str(self.contract_path),
            "--agent-timeout-seconds",
            "0",
        )

        self.assertEqual(2, completed.returncode, completed.stderr)
        result = self.single_document(completed)
        self.assertEqual("execution_impossible", result["outcome"])
        self.assertEqual("change", result["command"])
        self.assertIn("timeout", result["error"]["message"])
        self.assertEqual([], self.codex_invocations())


class HelpAndExitCodeTest(unittest.TestCase):
    def help_output(self, arguments: list[str]) -> tuple[int, str]:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            try:
                code = main(arguments)
            except SystemExit as exit_request:
                code = exit_request.code
        return code, stdout.getvalue()

    def test_leading_option_shows_change_help(self) -> None:
        code, output = self.help_output(["--help"])

        self.assertEqual(0, code)
        self.assertIn("495 change", output)
        self.assertIn("--request-file", output)
        self.assertIn("--codex-home", output)

    def test_general_help_lists_the_commands(self) -> None:
        for arguments in ([], ["-h"]):
            with self.subTest(arguments=arguments):
                code, output = self.help_output(arguments)

                self.assertEqual(0, code)
                self.assertIn("verify", output)
                self.assertIn("change", output)
                self.assertNotIn("--request-file", output)

    def test_exit_codes_are_derived_from_the_outcome(self) -> None:
        self.assertEqual(
            {
                "candidate_verified": 0,
                "candidate_failed": 1,
                "execution_impossible": 2,
                "configuration_invalid": 2,
                "agent_failed": 3,
                "no_candidate": 4,
            },
            EXIT_CODES,
        )
        self.assertEqual(4, exit_code_for({"outcome": "no_candidate"}))
        with self.assertRaises(KeyError):
            exit_code_for({"outcome": "unknown"})

    def test_error_documents_distinguish_invalid_configuration(self) -> None:
        invalid = error_result(ConfigurationError("champ manquant"), "verify")
        impossible = error_result(ChangeError("precondition", "dépôt absent"), "verify")

        self.assertEqual("configuration_invalid", invalid["outcome"])
        self.assertEqual("configuration", invalid["error"]["kind"])
        self.assertEqual("execution_impossible", impossible["outcome"])
        self.assertEqual(2, exit_code_for(invalid))
        self.assertEqual(2, exit_code_for(impossible))

    def test_result_bytes_are_indented_utf8_with_sorted_keys(self) -> None:
        encoded = result_bytes({"b": "é", "a": [1]})

        self.assertEqual(b'{\n  "a": [\n    1\n  ],\n  "b": "\xc3\xa9"\n}\n', encoded)


if __name__ == "__main__":
    unittest.main()
