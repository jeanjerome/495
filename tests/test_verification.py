from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest import mock

from harness495.composition import verify_with_codex_sandbox
from harness495.errors import ChangeError, ConfigurationError
from harness495.verification import verify_candidate
from harness495.workspace import resolve_baseline

from tests.test_run_change import FAKE_CODEX


class FakeRunner:
    """Double de ControlRunner qui enregistre ses appels et rend des résultats fixés."""

    def __init__(
        self,
        results: dict[str, dict[str, Any]] | None = None,
        effects: dict[str, Callable[[Path], None]] | None = None,
    ) -> None:
        self.results = results or {}
        self.effects = effects or {}
        self.calls: list[str] = []
        self.validated_profiles: list[list[str]] = []
        self.environments: list[dict[str, str]] = []

    def validate_profiles(
        self, *, repository: Path, contract: dict[str, Any], environment: dict[str, str]
    ) -> None:
        self.validated_profiles.append(
            sorted({check["filesystem"] for check in contract["checks"]})
        )
        self.environments.append(environment)

    def run(
        self, *, repository: Path, check: dict[str, Any], environment: dict[str, str]
    ) -> dict[str, Any]:
        self.calls.append(check["name"])
        effect = self.effects.get(check["name"])
        if effect is not None:
            effect(repository)
        result = {
            "command": check["command"],
            "exit_code": 0,
            "name": check["name"],
            "status": "PASS",
            "stderr": "",
            "stdout": "",
            "timed_out": False,
        }
        result.update(self.results.get(check["name"], {}))
        return result


class VerificationTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.repository = self.base / "application"
        self.repository.mkdir()
        self.contract = {
            "version": 1,
            "environment": ["PATH"],
            "checks": [
                {
                    "name": "tests",
                    "command": ["true"],
                    "timeout_seconds": 3,
                    "filesystem": "read-only",
                }
            ],
        }
        self.contract_path = self.repository / "495.json"
        (self.repository / "README.md").write_text("fixture\n", encoding="utf-8")
        self.contract_path.write_text(json.dumps(self.contract), encoding="utf-8")
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

    def modify_candidate(self) -> None:
        (self.repository / "result.txt").write_text("candidate\n", encoding="utf-8")

    def write_checks(self, *names: str) -> None:
        self.contract["checks"] = [
            {
                "name": name,
                "command": ["true"],
                "timeout_seconds": 3,
                "filesystem": "read-only",
            }
            for name in names
        ]
        self.contract_path.write_text(json.dumps(self.contract), encoding="utf-8")
        self.git("add", "495.json")
        self.commit("test: update checks")

    def verify(self, runner: FakeRunner, reference: str = "HEAD") -> dict[str, Any]:
        return verify_candidate(
            repository=self.repository,
            contract_path=self.contract_path,
            reference=reference,
            control_runner=runner,
        )

    def test_modified_repository_yields_a_verified_candidate(self) -> None:
        self.modify_candidate()
        runner = FakeRunner()

        result = self.verify(runner)

        self.assertEqual("candidate_verified", result["outcome"])
        self.assertEqual("verify", result["command"])
        self.assertEqual(1, result["version"])
        self.assertEqual("HEAD", result["reference"])
        self.assertEqual(self.head(), result["baseline"])
        self.assertEqual(self.head(), result["head"])
        self.assertEqual(self.head(), result["candidate"]["baseline"])
        self.assertTrue(result["candidate"]["digest"].startswith("sha256:"))
        self.assertEqual(
            [("result.txt", "?")],
            [(item["path"], item["status"]) for item in result["candidate"]["files"]],
        )
        self.assertEqual(["tests"], runner.calls)
        self.assertEqual([["read-only"]], runner.validated_profiles)
        self.assertEqual("PASS", result["checks"][0]["status"])
        self.assertEqual([], result["violations"])
        self.assertEqual([], result["limitations"])
        self.assertNotIn("candidate_after_checks", result)
        self.assertTrue(result["contract_digest"].startswith("sha256:"))
        self.assertEqual({"inherited": ["PATH"], "missing": []}, result["environment"])
        environment = runner.environments[0]
        self.assertNotIn("CODEX_HOME", environment)
        self.assertFalse(Path(environment["HOME"]).is_relative_to(self.repository))

    def test_failed_control_is_a_failed_candidate(self) -> None:
        self.modify_candidate()
        runner = FakeRunner(
            results={"tests": {"exit_code": 7, "status": "FAIL", "stderr": "bad\n"}}
        )

        result = self.verify(runner)

        self.assertEqual("candidate_failed", result["outcome"])
        self.assertEqual(7, result["checks"][0]["exit_code"])
        self.assertEqual("bad\n", result["checks"][0]["stderr"])
        self.assertEqual([], result["violations"])
        self.assertIsNotNone(result["candidate"])

    def test_control_timeout_is_a_failed_candidate(self) -> None:
        self.modify_candidate()
        runner = FakeRunner(
            results={"tests": {"exit_code": None, "status": "FAIL", "timed_out": True}}
        )

        result = self.verify(runner)

        self.assertEqual("candidate_failed", result["outcome"])
        self.assertTrue(result["checks"][0]["timed_out"])
        self.assertIsNone(result["checks"][0]["exit_code"])
        self.assertEqual([], result["violations"])

    def test_clean_tree_has_no_candidate_and_runs_no_control(self) -> None:
        runner = FakeRunner()

        result = self.verify(runner)

        self.assertEqual("no_candidate", result["outcome"])
        self.assertIsNone(result["candidate"])
        self.assertEqual([], result["checks"])
        self.assertEqual([], result["violations"])
        self.assertEqual([], runner.calls)
        self.assertEqual(1, len(runner.validated_profiles))
        self.assertEqual(1, len(result["limitations"]))
        self.assertIn(self.head(), result["limitations"][0])
        self.assertIn("HEAD~1", result["limitations"][0])

    def test_preconditions_are_reported_even_without_candidate(self) -> None:
        runner = FakeRunner()
        runner.validate_profiles = mock.Mock(
            side_effect=ChangeError("precondition", "sandbox read-only indisponible")
        )

        with self.assertRaisesRegex(ChangeError, "sandbox read-only indisponible"):
            self.verify(runner)

        self.assertEqual([], runner.calls)

    def test_control_that_modifies_the_candidate_stops_the_sequence(self) -> None:
        self.write_checks("first", "second")
        self.modify_candidate()

        def write_output(repository: Path) -> None:
            (repository / "control-output.txt").write_text("changed", encoding="utf-8")

        runner = FakeRunner(effects={"first": write_output})

        result = self.verify(runner)

        self.assertEqual("candidate_failed", result["outcome"])
        self.assertEqual(["first"], runner.calls)
        self.assertEqual(1, len(result["checks"]))
        self.assertEqual("PASS", result["checks"][0]["status"])
        self.assertEqual(
            ["le contrôle first a modifié l’état Git visible"], result["violations"]
        )
        self.assertEqual(
            ["control-output.txt", "result.txt"],
            [item["path"] for item in result["candidate_after_checks"]["files"]],
        )
        self.assertNotEqual(
            result["candidate"]["digest"], result["candidate_after_checks"]["digest"]
        )

    def test_controls_run_once_each_in_declared_order(self) -> None:
        self.write_checks("lint", "tests", "build")
        self.modify_candidate()
        runner = FakeRunner(results={"tests": {"exit_code": 1, "status": "FAIL"}})

        result = self.verify(runner)

        self.assertEqual(["lint", "tests", "build"], runner.calls)
        self.assertEqual(
            ["lint", "tests", "build"], [check["name"] for check in result["checks"]]
        )
        self.assertEqual(
            ["PASS", "FAIL", "PASS"], [check["status"] for check in result["checks"]]
        )
        self.assertEqual("candidate_failed", result["outcome"])
        self.assertEqual([], result["violations"])

    def test_earlier_reference_includes_committed_work(self) -> None:
        initial = self.head()
        self.git("-c", "tag.gpgsign=false", "tag", "v1")
        self.modify_candidate()
        self.git("add", "result.txt")
        self.commit("test: commit the candidate")
        runner = FakeRunner()

        for reference in ("HEAD~1", "v1", initial[:8], "main~1"):
            with self.subTest(reference=reference):
                result = self.verify(runner, reference=reference)

                self.assertEqual("candidate_verified", result["outcome"])
                self.assertEqual(reference, result["reference"])
                self.assertEqual(initial, result["baseline"])
                self.assertEqual(self.head(), result["head"])
                self.assertNotEqual(result["baseline"], result["head"])
                self.assertEqual(
                    [("result.txt", "A")],
                    [
                        (item["path"], item["status"])
                        for item in result["candidate"]["files"]
                    ],
                )

    def test_reference_outside_head_lineage_is_rejected(self) -> None:
        self.git("checkout", "-q", "-b", "other")
        (self.repository / "other.txt").write_text("other\n", encoding="utf-8")
        self.git("add", "other.txt")
        self.commit("test: diverge")
        self.git("checkout", "-q", "main")
        self.modify_candidate()
        runner = FakeRunner()

        with self.assertRaisesRegex(ChangeError, "n’est pas un ancêtre de HEAD"):
            self.verify(runner, reference="other")

        self.assertEqual([], runner.calls)

    def test_unresolvable_reference_is_rejected(self) -> None:
        self.modify_candidate()
        runner = FakeRunner()

        with self.assertRaisesRegex(ChangeError, "référence Git irrésoluble : nope"):
            self.verify(runner, reference="nope")

        with self.assertRaisesRegex(ChangeError, "référence Git irrésoluble : --output"):
            self.verify(runner, reference="--output")

        self.assertEqual([], runner.calls)

    def test_invalid_repository_is_rejected(self) -> None:
        runner = FakeRunner()
        plain = self.base / "plain"
        plain.mkdir()

        with self.assertRaisesRegex(ChangeError, "dépôt absent"):
            verify_candidate(
                repository=self.base / "missing",
                contract_path=self.contract_path,
                control_runner=runner,
            )
        with self.assertRaisesRegex(ChangeError, "not a git repository"):
            verify_candidate(
                repository=plain, contract_path=self.contract_path, control_runner=runner
            )
        nested = self.repository / "nested"
        nested.mkdir()
        with self.assertRaisesRegex(ChangeError, "racine Git"):
            verify_candidate(
                repository=nested, contract_path=self.contract_path, control_runner=runner
            )
        self.assertEqual([], runner.calls)

    def test_repository_without_head_is_rejected(self) -> None:
        empty = self.base / "empty"
        empty.mkdir()
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=empty, check=True)
        (empty / "file.txt").write_text("x\n", encoding="utf-8")

        with self.assertRaises(ChangeError):
            resolve_baseline(empty)

    def test_invalid_contract_is_distinct_from_missing_contract(self) -> None:
        self.modify_candidate()
        runner = FakeRunner()

        self.contract_path.write_text("{not json", encoding="utf-8")
        with self.assertRaisesRegex(ConfigurationError, "JSON invalide"):
            self.verify(runner)

        self.contract_path.write_text(
            json.dumps({"version": 1, "environment": []}), encoding="utf-8"
        )
        with self.assertRaisesRegex(ConfigurationError, "exactement"):
            self.verify(runner)

        self.contract_path.unlink()
        with self.assertRaisesRegex(ChangeError, "contrat absent") as context:
            self.verify(runner)
        self.assertNotIsInstance(context.exception, ConfigurationError)

        self.assertEqual([], runner.calls)
        self.assertEqual([], runner.validated_profiles)

    def test_codex_sandbox_verification_needs_no_authentication(self) -> None:
        fake_codex = self.base / "codex"
        fake_codex.write_text(
            f"#!{sys.executable}\n" + textwrap.dedent(FAKE_CODEX), encoding="utf-8"
        )
        fake_codex.chmod(0o755)
        self.contract["environment"] = ["FAKE_CODEX_MODE", "PATH"]
        self.contract["checks"][0]["command"] = [
            sys.executable,
            "-c",
            "from pathlib import Path; raise SystemExit(0 if Path('result.txt').exists() else 5)",
        ]
        self.contract_path.write_text(json.dumps(self.contract), encoding="utf-8")
        self.git("add", "495.json")
        self.commit("test: contract with a real command")

        with mock.patch.dict(os.environ, {"FAKE_CODEX_MODE": "unauthenticated"}):
            without_candidate = verify_with_codex_sandbox(
                repository=self.repository,
                contract_path=self.contract_path,
                executable=fake_codex,
            )
            self.modify_candidate()
            verified = verify_with_codex_sandbox(
                repository=self.repository,
                contract_path=self.contract_path,
                executable=fake_codex,
            )
            (self.repository / "result.txt").unlink()
            (self.repository / "README.md").write_text("edited\n", encoding="utf-8")
            failed = verify_with_codex_sandbox(
                repository=self.repository,
                contract_path=self.contract_path,
                executable=fake_codex,
            )

        self.assertEqual("no_candidate", without_candidate["outcome"])
        self.assertEqual("candidate_verified", verified["outcome"])
        self.assertEqual(0, verified["checks"][0]["exit_code"])
        self.assertEqual("read-only", verified["checks"][0]["sandbox"]["filesystem"])
        self.assertEqual("candidate_failed", failed["outcome"])
        self.assertEqual(5, failed["checks"][0]["exit_code"])
        self.assertEqual(
            [("README.md", "M")],
            [(item["path"], item["status"]) for item in failed["candidate"]["files"]],
        )


if __name__ == "__main__":
    unittest.main()
