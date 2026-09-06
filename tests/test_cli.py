from __future__ import annotations

import contextlib
import io
import json
import os
import re
import stat
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
        self.log = self.base / "fake-codex-invocations.log"
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
        (self.base / "fake-codex-mode").write_text(mode, encoding="utf-8")
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


    # --- configure ---

    def add_check_script(self) -> None:
        """Ajoute le script que le double de Codex reconnaît comme contrôle attesté."""

        script = self.repository / "scripts" / "check.sh"
        script.parent.mkdir()
        script.write_text("#!/bin/sh\ntest -f result.txt\n", encoding="utf-8")
        script.chmod(script.stat().st_mode | stat.S_IXUSR)
        self.git("add", "scripts/check.sh")
        self.commit("test: add the check script")

    def propose(
        self, mode: str = "success", *extra: str
    ) -> subprocess.CompletedProcess[str]:
        codex_home = self.base / "codex-home"
        codex_home.mkdir(exist_ok=True)
        return self.run_cli(
            "configure",
            "propose",
            "--repository",
            str(self.repository),
            "--codex-home",
            str(codex_home),
            *extra,
            mode=mode,
        )

    def write_proposal(
        self, completed: subprocess.CompletedProcess[str], name: str = "proposal.json"
    ) -> Path:
        path = self.base / name
        path.write_text(completed.stdout, encoding="utf-8")
        return path

    def test_configure_propose_returns_a_proposal_without_writing(self) -> None:
        self.add_check_script()
        head = self.head()

        completed = self.propose()

        self.assertEqual(0, completed.returncode, completed.stderr)
        result = self.single_document(completed)
        self.assertEqual("proposal_ready", result["outcome"])
        self.assertEqual("configure propose", result["command"])
        self.assertEqual(head, result["baseline"])
        self.assertEqual("codex-cli test", result["client_version"])
        self.assertEqual(
            {
                "checks": [
                    {
                        "command": ["sh", "scripts/check.sh"],
                        "filesystem": "read-only",
                        "name": "check",
                        "timeout_seconds": None,
                    }
                ],
                "environment": ["PATH"],
                "version": 1,
            },
            result["contract"],
        )
        self.assertEqual(
            {"check": "scripts/check.sh est le script de contrôle du dépôt"},
            result["evidence"],
        )
        self.assertTrue(result["commands"]["check"].endswith("sh"))
        self.assertEqual([], result["questions"])
        self.assertEqual([], result["violations"])
        self.assertIn("n’atteste ni la pertinence", result["limitations"][0])
        self.assertIn("ne sont pas bornés dans le temps", result["limitations"][1])
        self.assertEqual("read-only", result["agent"]["sandbox"]["filesystem"])
        self.assertEqual(
            ["only scripts/ was inspected"], result["agent"]["response"]["limitations"]
        )
        self.assertEqual("", self.git("status", "--porcelain"))
        self.assertEqual(head, self.head())
        invocations = self.codex_invocations()
        self.assertIn(["login", "status"], invocations)
        exec_call = next(call for call in invocations if call[0] == "exec")
        self.assertEqual("read-only", exec_call[exec_call.index("--sandbox") + 1])
        self.assertNotIn("sandbox", [call[0] for call in invocations])

    def test_configure_propose_applies_the_user_timeout(self) -> None:
        self.add_check_script()

        completed = self.propose("success", "--timeout-seconds", "45")
        attested = self.propose("attested_timeout", "--timeout-seconds", "45")
        rejected = self.propose("success", "--timeout-seconds", "0")

        self.assertEqual(0, completed.returncode, completed.stderr)
        result = self.single_document(completed)
        self.assertEqual(45, result["contract"]["checks"][0]["timeout_seconds"])
        self.assertIn("le timeout de check vaut 45 s", result["limitations"][1])
        self.assertEqual(0, attested.returncode, attested.stderr)
        result = self.single_document(attested)
        self.assertEqual(60, result["contract"]["checks"][0]["timeout_seconds"])
        self.assertEqual(1, len(result["limitations"]))
        self.assertEqual(2, rejected.returncode, rejected.stderr)
        result = self.single_document(rejected)
        self.assertEqual("execution_impossible", result["outcome"])
        self.assertIn("timeout des contrôles", result["error"]["message"])

    def test_configure_propose_reports_an_agent_that_writes(self) -> None:
        self.add_check_script()

        completed = self.propose("modifies_repository")

        self.assertEqual(3, completed.returncode, completed.stderr)
        result = self.single_document(completed)
        self.assertEqual("agent_failed", result["outcome"])
        self.assertIsNone(result["contract"])
        self.assertEqual(
            ["l’agent a modifié le dépôt pendant l’inspection en lecture seule"],
            result["violations"],
        )
        self.assertEqual("?? proposal-note.txt\n", self.git("status", "--porcelain"))

    def test_configure_propose_reports_an_invalid_response(self) -> None:
        self.add_check_script()

        completed = self.propose("invalid_response")

        self.assertEqual(3, completed.returncode, completed.stderr)
        result = self.single_document(completed)
        self.assertEqual("agent_failed", result["outcome"])
        self.assertIsNone(result["contract"])
        self.assertIn("non conforme", result["agent"]["response_error"])
        self.assertEqual(["réponse de l’agent invalide"], result["violations"])

    def test_configure_propose_without_detectable_check(self) -> None:
        completed = self.propose()

        self.assertEqual(4, completed.returncode, completed.stderr)
        result = self.single_document(completed)
        self.assertEqual("no_checks_detected", result["outcome"])
        self.assertIsNone(result["contract"])
        self.assertEqual({}, result["evidence"])
        self.assertEqual(
            ["Aucun script de contrôle trouvé ; quelle commande lance les tests ?"],
            result["questions"],
        )
        self.assertEqual([], result["violations"])
        self.assertTrue(any("configure validate" in item for item in result["limitations"]))

    def test_configure_propose_rejects_a_proposal_violating_the_contract(self) -> None:
        self.add_check_script()

        for mode, expected in (
            ("duplicate_check", "nom de contrôle dupliqué"),
            ("secret_environment", "ressemble à un secret"),
        ):
            with self.subTest(mode=mode):
                completed = self.propose(mode)

                self.assertEqual(3, completed.returncode, completed.stderr)
                result = self.single_document(completed)
                self.assertEqual("agent_failed", result["outcome"])
                self.assertIsNone(result["contract"])
                self.assertIn(expected, result["violations"][0])

    def test_configure_propose_reports_an_unknown_executable_as_null(self) -> None:
        self.add_check_script()

        completed = self.propose("unknown_executable")

        self.assertEqual(0, completed.returncode, completed.stderr)
        result = self.single_document(completed)
        self.assertEqual("proposal_ready", result["outcome"])
        self.assertEqual({"check": None}, result["commands"])

    def test_configure_propose_requires_authentication_and_a_positive_timeout(self) -> None:
        self.add_check_script()
        codex_home = self.base / "codex-home"
        codex_home.mkdir()

        unauthenticated = self.propose("unauthenticated")
        zero_timeout = self.run_cli(
            "configure",
            "propose",
            "--repository",
            str(self.repository),
            "--codex-home",
            str(codex_home),
            "--agent-timeout-seconds",
            "0",
            mode="success",
        )

        self.assertEqual(2, unauthenticated.returncode, unauthenticated.stderr)
        result = self.single_document(unauthenticated)
        self.assertEqual("execution_impossible", result["outcome"])
        self.assertEqual("configure propose", result["command"])
        self.assertIn("Not logged in", result["error"]["message"])
        self.assertEqual(2, zero_timeout.returncode, zero_timeout.stderr)
        self.assertIn("timeout", self.single_document(zero_timeout)["error"]["message"])
        self.assertNotIn("exec", [call[0] for call in self.codex_invocations()])

    def test_configure_validate_accepts_a_valid_contract(self) -> None:
        completed = self.run_cli("configure", "validate", "--repository", str(self.repository))

        self.assertEqual(0, completed.returncode, completed.stderr)
        result = self.single_document(completed)
        self.assertEqual("configuration_valid", result["outcome"])
        self.assertEqual("configure validate", result["command"])
        self.assertEqual("495.json", result["contract_path"])
        self.assertTrue(result["contract_digest"].startswith("sha256:"))
        self.assertEqual({"name": "codex-sandbox", "version": "codex-cli test"}, result["runner"])
        self.assertEqual(
            {"result-present": str(Path(sys.executable).resolve())}, result["commands"]
        )
        self.assertEqual([], result["limitations"])
        invocations = self.codex_invocations()
        self.assertEqual(["--version"], invocations[0])
        self.assertTrue(all(call[0] == "sandbox" for call in invocations[1:]), invocations)
        self.assertNotIn(["login", "status"], invocations)

    def test_configure_validate_reports_an_invalid_contract(self) -> None:
        self.contract["checks"][0]["timeout_seconds"] = 0
        self.contract_path.write_text(json.dumps(self.contract), encoding="utf-8")

        completed = self.run_cli("configure", "validate", "--repository", str(self.repository))

        self.assertEqual(2, completed.returncode, completed.stderr)
        result = self.single_document(completed)
        self.assertEqual("configuration_invalid", result["outcome"])
        self.assertEqual("configure validate", result["command"])
        self.assertIn("timeout_seconds", result["error"]["message"])
        self.assertEqual([], self.codex_invocations())

    def test_configure_validate_reports_missing_tools_and_sandbox(self) -> None:
        unavailable = self.run_cli(
            "configure", "validate", "--repository", str(self.repository), mode="sandbox_unavailable"
        )
        self.contract["checks"][0]["command"] = ["tool-495-absent", "--check"]
        self.contract_path.write_text(json.dumps(self.contract), encoding="utf-8")
        missing = self.run_cli("configure", "validate", "--repository", str(self.repository))

        self.assertEqual(2, unavailable.returncode, unavailable.stderr)
        result = self.single_document(unavailable)
        self.assertEqual("execution_impossible", result["outcome"])
        self.assertIn("sandbox read-only indisponible", result["error"]["message"])
        self.assertEqual(2, missing.returncode, missing.stderr)
        result = self.single_document(missing)
        self.assertEqual("execution_impossible", result["outcome"])
        self.assertIn(
            "exécutable de contrôle introuvable : result-present : tool-495-absent",
            result["error"]["message"],
        )

    def test_verify_reports_a_missing_tool_before_any_control(self) -> None:
        self.add_candidate()
        self.contract["checks"][0]["command"] = ["tool-495-absent", "--check"]
        self.contract_path.write_text(json.dumps(self.contract), encoding="utf-8")

        completed = self.run_cli("verify", "--repository", str(self.repository))

        self.assertEqual(2, completed.returncode, completed.stderr)
        result = self.single_document(completed)
        self.assertEqual("execution_impossible", result["outcome"])
        self.assertIn("exécutable de contrôle introuvable", result["error"]["message"])
        self.assertEqual([], self.codex_invocations())

    def test_configure_write_records_a_proposal_reused_by_validate_and_verify(self) -> None:
        self.add_check_script()
        proposal = self.write_proposal(self.propose())
        target = self.repository / "proposed.json"

        written = self.run_cli(
            "configure",
            "write",
            "--repository",
            str(self.repository),
            "--proposal",
            str(proposal),
            "--contract",
            str(target),
        )
        validated = self.run_cli(
            "configure", "validate", "--repository", str(self.repository), "--contract", str(target)
        )
        self.add_candidate()
        verified = self.run_cli(
            "verify", "--repository", str(self.repository), "--contract", str(target)
        )
        (self.repository / "result.txt").unlink()
        (self.repository / "README.md").write_text("edited\n", encoding="utf-8")
        failed = self.run_cli(
            "verify", "--repository", str(self.repository), "--contract", str(target)
        )

        self.assertEqual(0, written.returncode, written.stderr)
        result = self.single_document(written)
        self.assertEqual("configuration_written", result["outcome"])
        self.assertEqual("configure write", result["command"])
        self.assertEqual("proposed.json", result["contract_path"])
        self.assertFalse(result["overwritten"])
        self.assertEqual({"name": "codex-sandbox", "version": "codex-cli test"}, result["runner"])
        self.assertTrue(result["commands"]["check"].endswith("sh"))
        stored = json.loads(target.read_text(encoding="utf-8"))
        self.assertEqual(json.loads(proposal.read_text(encoding="utf-8"))["contract"], stored)
        self.assertTrue(target.read_text(encoding="utf-8").startswith('{\n  "checks"'))
        self.assertEqual(0, validated.returncode, validated.stderr)
        self.assertEqual("configuration_valid", self.single_document(validated)["outcome"])
        self.assertEqual(
            result["contract_digest"], self.single_document(validated)["contract_digest"]
        )
        self.assertEqual(0, verified.returncode, verified.stderr)
        verified_result = self.single_document(verified)
        self.assertEqual("candidate_verified", verified_result["outcome"])
        self.assertEqual(["check"], [check["name"] for check in verified_result["checks"]])
        self.assertEqual(
            ["proposed.json", "result.txt"],
            [item["path"] for item in verified_result["candidate"]["files"]],
        )
        self.assertEqual(1, failed.returncode, failed.stderr)
        self.assertEqual("candidate_failed", self.single_document(failed)["outcome"])

    def test_configure_write_refuses_to_overwrite_without_authorization(self) -> None:
        self.add_check_script()
        proposal = self.write_proposal(self.propose())
        original = self.contract_path.read_text(encoding="utf-8")

        refused = self.run_cli(
            "configure",
            "write",
            "--repository",
            str(self.repository),
            "--proposal",
            str(proposal),
        )
        overwritten = self.run_cli(
            "configure",
            "write",
            "--repository",
            str(self.repository),
            "--proposal",
            str(proposal),
            "--overwrite",
        )

        self.assertEqual(2, refused.returncode, refused.stderr)
        result = self.single_document(refused)
        self.assertEqual("execution_impossible", result["outcome"])
        self.assertEqual("configure write", result["command"])
        self.assertIn("--overwrite requis", result["error"]["message"])
        self.assertEqual(0, overwritten.returncode, overwritten.stderr)
        result = self.single_document(overwritten)
        self.assertEqual("configuration_written", result["outcome"])
        self.assertTrue(result["overwritten"])
        self.assertEqual("495.json", result["contract_path"])
        self.assertNotEqual(original, self.contract_path.read_text(encoding="utf-8"))
        self.assertEqual(
            json.loads(proposal.read_text(encoding="utf-8"))["contract"],
            json.loads(self.contract_path.read_text(encoding="utf-8")),
        )
        self.assertEqual(" M 495.json\n", self.git("status", "--porcelain"))

    def test_configure_write_rejects_files_that_are_not_proposals(self) -> None:
        self.add_check_script()
        proposal = self.write_proposal(self.propose("unknown_executable"))
        target = self.repository / "proposed.json"
        contract_only = self.base / "contract.json"
        contract_only.write_text(json.dumps(self.contract), encoding="utf-8")
        without_contract = self.write_proposal(self.propose("blocked"), "blocked.json")

        unknown = self.run_cli(
            "configure", "write", "--repository", str(self.repository),
            "--proposal", str(proposal), "--contract", str(target),
        )
        plain = self.run_cli(
            "configure", "write", "--repository", str(self.repository),
            "--proposal", str(contract_only), "--contract", str(target),
        )
        blocked = self.run_cli(
            "configure", "write", "--repository", str(self.repository),
            "--proposal", str(without_contract), "--contract", str(target),
        )
        outside = self.run_cli(
            "configure", "write", "--repository", str(self.repository),
            "--proposal", str(proposal), "--contract", str(self.base / "elsewhere.json"),
        )

        self.assertEqual(2, unknown.returncode, unknown.stderr)
        self.assertIn(
            "exécutable de contrôle introuvable",
            self.single_document(unknown)["error"]["message"],
        )
        self.assertEqual(2, plain.returncode, plain.stderr)
        self.assertIn(
            "n’est pas une proposition", self.single_document(plain)["error"]["message"]
        )
        self.assertEqual(2, blocked.returncode, blocked.stderr)
        self.assertIn(
            "n’est pas une proposition", self.single_document(blocked)["error"]["message"]
        )
        self.assertEqual(2, outside.returncode, outside.stderr)
        self.assertIn(
            "situé dans le dépôt", self.single_document(outside)["error"]["message"]
        )
        self.assertFalse(target.exists())
        self.assertFalse((self.base / "elsewhere.json").exists())

    def test_configure_without_operation_shows_its_help(self) -> None:
        completed = self.run_cli("configure")

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertIn("propose", completed.stdout)
        self.assertIn("validate", completed.stdout)
        self.assertIn("write", completed.stdout)
        self.assertEqual("", completed.stderr)


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
                self.assertIn("configure", output)
                self.assertIn("change", output)
                self.assertNotIn("--request-file", output)

    def test_exit_codes_are_derived_from_the_outcome(self) -> None:
        self.assertEqual(
            {
                "candidate_verified": 0,
                "proposal_ready": 0,
                "configuration_valid": 0,
                "configuration_written": 0,
                "candidate_failed": 1,
                "execution_impossible": 2,
                "configuration_invalid": 2,
                "agent_failed": 3,
                "no_candidate": 4,
                "no_checks_detected": 4,
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
