from __future__ import annotations

import copy
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest import mock

from harness495.configuration import (
    PROPOSAL_RESPONSE_SCHEMA,
    load_proposal,
    propose_configuration,
    proposal_prompt,
    validate_configuration,
    write_configuration,
)
from harness495.contract import load_contract, write_contract
from harness495.errors import ChangeError, ConfigurationError
from harness495.process import execute_process
from harness495.verification import resolve_executable

from tests.test_verification import FakeRunner


def proposal_response(**changes: Any) -> dict[str, Any]:
    response: dict[str, Any] = {
        "status": "completed",
        "summary": "the repository exposes one check script",
        "checks": [
            {
                "name": "check",
                "command": ["sh", "scripts/check.sh"],
                "timeout_seconds": 60,
                "filesystem": "read-only",
                "evidence": "scripts/check.sh est le script de contrôle du dépôt",
            }
        ],
        "environment": ["PATH"],
        "questions": [],
        "limitations": ["seul scripts/ a été inspecté"],
    }
    response.update(changes)
    return response


class FakeAgent:
    """Double d’AgentClient qui rend une réponse fixée et enregistre l’invocation."""

    def __init__(
        self,
        response: dict[str, Any] | None,
        *,
        effect: Callable[[Path], None] | None = None,
        **overrides: Any,
    ) -> None:
        self.response = response
        self.effect = effect
        self.overrides = overrides
        self.invocations: list[dict[str, Any]] = []
        self.ready_checked = False

    def version(self, *, repository: Path, environment: dict[str, str]) -> str:
        return "fake-agent 1"

    def validate_ready(self, *, repository: Path, environment: dict[str, str]) -> None:
        self.ready_checked = True

    def invoke(self, **arguments: Any) -> dict[str, Any]:
        self.invocations.append(arguments)
        if self.effect is not None:
            self.effect(arguments["repository"])
        agent = {
            "client": "fake",
            "command": [],
            "duration_seconds": 0.0,
            "events": None,
            "events_error": None,
            "exit_code": 0,
            "limitations": [],
            "response": self.response,
            "response_error": None,
            "sandbox": {
                "filesystem": arguments["filesystem"],
                "network_for_commands": "disabled",
            },
            "stderr": "",
            "timed_out": False,
        }
        agent.update(self.overrides)
        return agent


class ConfigurationTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.repository = self.base / "application"
        (self.repository / "scripts").mkdir(parents=True)
        (self.repository / "README.md").write_text("fixture\n", encoding="utf-8")
        script = self.repository / "scripts" / "check.sh"
        script.write_text("#!/bin/sh\ntest -f result.txt\n", encoding="utf-8")
        script.chmod(script.stat().st_mode | stat.S_IXUSR)
        self.git("init", "-b", "main")
        self.git("add", "README.md", "scripts/check.sh")
        self.commit("test: initialize fixture")
        self.contract_path = self.repository / "495.json"

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

    def status(self) -> str:
        return self.git("status", "--porcelain")

    def propose(
        self, agent: FakeAgent, timeout: int = 3, timeout_seconds: int | None = None
    ) -> dict[str, Any]:
        return propose_configuration(
            repository=self.repository,
            agent_client=agent,
            agent_timeout_seconds=timeout,
            client_environment={"CODEX_HOME": str(self.base / "codex-home")},
            timeout_seconds=timeout_seconds,
        )

    def write_proposal(self, contract: Any) -> Path:
        path = self.base / "proposal.json"
        path.write_text(
            json.dumps({"command": "configure propose", "contract": contract, "version": 1}),
            encoding="utf-8",
        )
        return path

    # --- propose ---

    def test_valid_response_becomes_a_contract_with_evidence(self) -> None:
        agent = FakeAgent(proposal_response())

        result = self.propose(agent)

        self.assertEqual("proposal_ready", result["outcome"])
        self.assertEqual("configure propose", result["command"])
        self.assertEqual(1, result["version"])
        self.assertEqual(self.git("rev-parse", "HEAD").strip(), result["baseline"])
        self.assertEqual("fake-agent 1", result["client_version"])
        self.assertEqual(
            {
                "checks": [
                    {
                        "command": ["sh", "scripts/check.sh"],
                        "filesystem": "read-only",
                        "name": "check",
                        "timeout_seconds": 60,
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
        self.assertEqual(["check"], list(result["commands"]))
        self.assertTrue(Path(result["commands"]["check"]).is_absolute())
        self.assertTrue(result["commands"]["check"].endswith("sh"))
        self.assertEqual([], result["questions"])
        self.assertEqual([], result["violations"])
        self.assertEqual(1, len(result["limitations"]))
        self.assertIn("n’atteste ni la pertinence", result["limitations"][0])
        self.assertEqual("read-only", result["agent"]["sandbox"]["filesystem"])
        self.assertEqual({"inherited": ["PATH"], "missing": []}, result["environment"])
        self.assertEqual(4 * 1024 * 1024, result["output_limit_bytes"])
        self.assertTrue(agent.ready_checked)
        invocation = agent.invocations[0]
        self.assertEqual("read-only", invocation["filesystem"])
        self.assertIs(PROPOSAL_RESPONSE_SCHEMA, invocation["response_schema"])
        self.assertEqual(proposal_prompt(), invocation["prompt"])
        self.assertIn("evidence", invocation["prompt"])
        self.assertNotIn("CODEX_HOME", invocation["environment"].get("PATH", ""))
        self.assertEqual("", self.status())
        self.assertFalse(self.contract_path.exists())

    def test_unattested_timeout_stays_null_without_a_user_value(self) -> None:
        response = proposal_response()
        response["checks"][0]["timeout_seconds"] = None
        agent = FakeAgent(response)

        result = self.propose(agent)

        self.assertEqual("proposal_ready", result["outcome"])
        self.assertIsNone(result["contract"]["checks"][0]["timeout_seconds"])
        self.assertEqual([], result["questions"])
        self.assertEqual(2, len(result["limitations"]))
        self.assertIn("aucun timeout n’est attesté par le dépôt pour check", result["limitations"][1])
        self.assertIn("--timeout-seconds", result["limitations"][1])

    def test_user_timeout_completes_only_unattested_checks(self) -> None:
        response = proposal_response()
        response["checks"][0]["timeout_seconds"] = None
        response["checks"].append(
            {
                "name": "lint",
                "command": ["sh", "scripts/check.sh"],
                "timeout_seconds": 30,
                "filesystem": "read-only",
                "evidence": "ci.yml fixe 30 s",
            }
        )
        agent = FakeAgent(response)

        result = self.propose(agent, timeout_seconds=120)

        self.assertEqual("proposal_ready", result["outcome"])
        self.assertEqual(
            [120, 30], [check["timeout_seconds"] for check in result["contract"]["checks"]]
        )
        self.assertEqual(2, len(result["limitations"]))
        self.assertIn("le timeout de check vaut 120 s", result["limitations"][1])
        self.assertNotIn("lint", result["limitations"][1])

    def test_attested_timeouts_leave_no_timeout_limitation(self) -> None:
        result = self.propose(FakeAgent(proposal_response()), timeout_seconds=120)

        self.assertEqual("proposal_ready", result["outcome"])
        self.assertEqual(60, result["contract"]["checks"][0]["timeout_seconds"])
        self.assertEqual(1, len(result["limitations"]))

    def test_contract_accepts_a_null_timeout_but_not_zero(self) -> None:
        contract = proposal_contract()
        contract["checks"][0]["timeout_seconds"] = None
        self.contract_path.write_text(json.dumps(contract), encoding="utf-8")
        runner = FakeRunner()

        result = validate_configuration(
            repository=self.repository, contract_path=self.contract_path, control_runner=runner
        )
        self.assertEqual("configuration_valid", result["outcome"])

        contract["checks"][0]["timeout_seconds"] = 0
        self.contract_path.write_text(json.dumps(contract), encoding="utf-8")
        with self.assertRaisesRegex(ConfigurationError, "entier positif ou null"):
            validate_configuration(
                repository=self.repository, contract_path=self.contract_path, control_runner=runner
            )

    def test_process_without_timeout_runs_to_completion(self) -> None:
        result = execute_process(
            [sys.executable, "-c", "print('done')"],
            cwd=self.repository,
            environment={"PATH": os.environ["PATH"]},
            timeout_seconds=None,
        )

        self.assertEqual(0, result["exit_code"])
        self.assertFalse(result["timed_out"])
        self.assertEqual("done\n", result["stdout"])

    def test_invalid_response_is_an_agent_failure_without_contract(self) -> None:
        agent = FakeAgent(None, response_error="réponse de l’agent non conforme")

        result = self.propose(agent)

        self.assertEqual("agent_failed", result["outcome"])
        self.assertIsNone(result["contract"])
        self.assertEqual({}, result["evidence"])
        self.assertEqual({}, result["commands"])
        self.assertEqual(["réponse de l’agent invalide"], result["violations"])

    def test_blocked_response_is_an_agent_failure_with_its_questions(self) -> None:
        agent = FakeAgent(
            proposal_response(status="blocked", questions=["Which package manager?"])
        )

        result = self.propose(agent)

        self.assertEqual("agent_failed", result["outcome"])
        self.assertIsNone(result["contract"])
        self.assertEqual(["Which package manager?"], result["questions"])
        self.assertEqual(["agent bloqué"], result["violations"])

    def test_response_without_check_reports_nothing_to_propose(self) -> None:
        agent = FakeAgent(
            proposal_response(checks=[], questions=["Quelle commande lance les tests ?"])
        )

        result = self.propose(agent)

        self.assertEqual("no_checks_detected", result["outcome"])
        self.assertIsNone(result["contract"])
        self.assertEqual(["Quelle commande lance les tests ?"], result["questions"])
        self.assertEqual([], result["violations"])
        self.assertEqual(2, len(result["limitations"]))
        self.assertIn("configure validate", result["limitations"][1])

    def test_proposal_violating_the_contract_is_not_corrected(self) -> None:
        duplicated = proposal_response()
        duplicated["checks"].append(copy.deepcopy(duplicated["checks"][0]))
        secret = proposal_response(environment=["PATH", "API_TOKEN"])
        zero_timeout = proposal_response()
        zero_timeout["checks"][0]["timeout_seconds"] = 0
        empty_command = proposal_response()
        empty_command["checks"][0]["command"] = []

        for label, response, expected in (
            ("duplicated", duplicated, "nom de contrôle dupliqué"),
            ("secret", secret, "ressemble à un secret"),
            ("zero_timeout", zero_timeout, "entier positif"),
            ("empty_command", empty_command, "doit être non vide"),
        ):
            with self.subTest(label=label):
                result = self.propose(FakeAgent(response))

                self.assertEqual("agent_failed", result["outcome"])
                self.assertIsNone(result["contract"])
                self.assertEqual(1, len(result["violations"]))
                self.assertIn("proposition non conforme", result["violations"][0])
                self.assertIn(expected, result["violations"][0])

    def test_agent_that_modifies_the_repository_is_not_trusted(self) -> None:
        def write_note(repository: Path) -> None:
            (repository / "note.txt").write_text("written\n", encoding="utf-8")

        agent = FakeAgent(proposal_response(), effect=write_note)

        result = self.propose(agent)

        self.assertEqual("agent_failed", result["outcome"])
        self.assertIsNone(result["contract"])
        self.assertEqual(
            ["l’agent a modifié le dépôt pendant l’inspection en lecture seule"],
            result["violations"],
        )

    def test_unresolved_executable_is_reported_as_null_not_as_failure(self) -> None:
        response = proposal_response()
        response["checks"][0]["command"] = ["tool-495-absent", "check"]
        agent = FakeAgent(response)

        result = self.propose(agent)

        self.assertEqual("proposal_ready", result["outcome"])
        self.assertEqual({"check": None}, result["commands"])
        self.assertIsNotNone(result["contract"])

    def test_dirty_repository_is_accepted_for_a_proposal(self) -> None:
        (self.repository / "draft.txt").write_text("draft\n", encoding="utf-8")
        agent = FakeAgent(proposal_response())

        result = self.propose(agent)

        self.assertEqual("proposal_ready", result["outcome"])
        self.assertEqual([], result["violations"])

    # --- executable resolution ---

    def test_executable_resolution(self) -> None:
        environment = {"PATH": os.environ["PATH"]}

        self.assertEqual(
            str((self.repository / "scripts" / "check.sh").resolve()),
            resolve_executable(
                ["scripts/check.sh"], repository=self.repository, environment=environment
            ),
        )
        self.assertIsNone(
            resolve_executable(
                ["scripts/missing.sh"], repository=self.repository, environment=environment
            )
        )
        self.assertIsNone(
            resolve_executable(
                ["README.md"], repository=self.repository, environment=environment
            )
        )
        self.assertIsNone(
            resolve_executable(
                ["./README.md"], repository=self.repository, environment=environment
            )
        )
        located = resolve_executable(["sh"], repository=self.repository, environment=environment)
        assert located is not None
        self.assertTrue(Path(located).is_absolute())
        self.assertIsNone(
            resolve_executable(
                ["tool-495-absent"], repository=self.repository, environment=environment
            )
        )
        self.assertIsNone(
            resolve_executable(
                ["sh"], repository=self.repository, environment={"PATH": str(self.base)}
            )
        )
        self.assertIsNotNone(
            resolve_executable(["sh"], repository=self.repository, environment={})
        )

    # --- write_contract ---

    def test_contract_is_written_exclusively_and_never_overwritten_silently(self) -> None:
        contract = proposal_contract()

        overwritten = write_contract(
            self.contract_path, contract, repository=self.repository, overwrite=False
        )

        self.assertFalse(overwritten)
        self.assertEqual(contract, json.loads(self.contract_path.read_text("utf-8")))
        self.assertTrue(self.contract_path.read_text("utf-8").startswith('{\n  "checks"'))

        self.contract_path.write_text("{not json", encoding="utf-8")
        with self.assertRaisesRegex(ChangeError, "--overwrite requis"):
            write_contract(
                self.contract_path, contract, repository=self.repository, overwrite=False
            )
        self.assertEqual("{not json", self.contract_path.read_text("utf-8"))

        overwritten = write_contract(
            self.contract_path, contract, repository=self.repository, overwrite=True
        )
        self.assertTrue(overwritten)
        self.assertEqual(contract, json.loads(self.contract_path.read_text("utf-8")))
        self.assertEqual(["495.json", "README.md", "scripts"], sorted(
            path.name for path in self.repository.iterdir() if path.name != ".git"
        ))

    def test_contract_outside_the_repository_is_refused(self) -> None:
        outside = self.base / "495.json"

        with self.assertRaisesRegex(ChangeError, "situé dans le dépôt"):
            write_contract(
                outside, proposal_contract(), repository=self.repository, overwrite=False
            )

        self.assertFalse(outside.exists())

    # --- validate ---

    def test_present_contract_is_validated_with_commands_and_runner(self) -> None:
        self.contract_path.write_text(json.dumps(proposal_contract()), encoding="utf-8")
        runner = FakeRunner()

        result = validate_configuration(
            repository=self.repository,
            contract_path=self.contract_path,
            control_runner=runner,
        )

        self.assertEqual("configuration_valid", result["outcome"])
        self.assertEqual("configure validate", result["command"])
        self.assertEqual("495.json", result["contract_path"])
        self.assertTrue(result["contract_digest"].startswith("sha256:"))
        self.assertEqual({"name": "codex-sandbox", "version": "fake-runner 1"}, result["runner"])
        self.assertEqual(4 * 1024 * 1024, result["output_limit_bytes"])
        self.assertEqual(["check"], list(result["commands"]))
        self.assertTrue(result["commands"]["check"].endswith("sh"))
        self.assertEqual([["read-only"]], runner.validated_profiles)
        self.assertEqual([], runner.calls)
        self.assertEqual([], result["limitations"])

    def test_invalid_contract_is_a_configuration_error(self) -> None:
        contract = proposal_contract()
        contract["checks"][0]["filesystem"] = "anything"
        self.contract_path.write_text(json.dumps(contract), encoding="utf-8")
        runner = FakeRunner()

        with self.assertRaisesRegex(ConfigurationError, "filesystem"):
            validate_configuration(
                repository=self.repository,
                contract_path=self.contract_path,
                control_runner=runner,
            )

        self.assertEqual([], runner.validated_profiles)

    def test_missing_executable_makes_validation_impossible_before_the_probe(self) -> None:
        contract = proposal_contract()
        contract["checks"][0]["command"] = ["tool-495-absent"]
        self.contract_path.write_text(json.dumps(contract), encoding="utf-8")
        runner = FakeRunner()

        with self.assertRaisesRegex(
            ChangeError, "exécutable de contrôle introuvable : check : tool-495-absent"
        ) as context:
            validate_configuration(
                repository=self.repository,
                contract_path=self.contract_path,
                control_runner=runner,
            )

        self.assertNotIsInstance(context.exception, ConfigurationError)
        self.assertEqual([], runner.validated_profiles)

    def test_unavailable_sandbox_makes_validation_impossible(self) -> None:
        self.contract_path.write_text(json.dumps(proposal_contract()), encoding="utf-8")
        runner = FakeRunner()
        runner.validate_profiles = mock.Mock(
            side_effect=ChangeError("precondition", "sandbox read-only indisponible")
        )

        with self.assertRaisesRegex(ChangeError, "sandbox read-only indisponible"):
            validate_configuration(
                repository=self.repository,
                contract_path=self.contract_path,
                control_runner=runner,
            )

    # --- write ---

    def test_explicit_write_validates_then_records_the_contract(self) -> None:
        contract = proposal_contract()
        proposal = self.write_proposal(contract)
        runner = FakeRunner()

        result = write_configuration(
            repository=self.repository,
            proposal_path=proposal,
            contract_path=self.contract_path,
            overwrite=False,
            control_runner=runner,
        )

        self.assertEqual("configuration_written", result["outcome"])
        self.assertEqual("configure write", result["command"])
        self.assertEqual("495.json", result["contract_path"])
        self.assertFalse(result["overwritten"])
        self.assertEqual({"name": "codex-sandbox", "version": "fake-runner 1"}, result["runner"])
        self.assertEqual(["check"], list(result["commands"]))
        self.assertEqual([["read-only"]], runner.validated_profiles)
        loaded, digest = load_contract(self.contract_path)
        self.assertEqual(contract, loaded)
        self.assertEqual(result["contract_digest"], digest)
        self.assertEqual("?? 495.json\n", self.status())

    def test_write_refuses_to_overwrite_without_authorization(self) -> None:
        self.contract_path.write_text("{original}", encoding="utf-8")
        proposal = self.write_proposal(proposal_contract())
        runner = FakeRunner()

        with self.assertRaisesRegex(ChangeError, "--overwrite requis") as context:
            write_configuration(
                repository=self.repository,
                proposal_path=proposal,
                contract_path=self.contract_path,
                overwrite=False,
                control_runner=runner,
            )

        self.assertNotIsInstance(context.exception, ConfigurationError)
        self.assertEqual("{original}", self.contract_path.read_text("utf-8"))
        self.assertEqual([], runner.validated_profiles)

        result = write_configuration(
            repository=self.repository,
            proposal_path=proposal,
            contract_path=self.contract_path,
            overwrite=True,
            control_runner=runner,
        )

        self.assertEqual("configuration_written", result["outcome"])
        self.assertTrue(result["overwritten"])
        self.assertEqual(proposal_contract(), load_contract(self.contract_path)[0])

    def test_write_accepts_only_proposals_with_a_contract(self) -> None:
        runner = FakeRunner()
        not_a_proposal = self.base / "contract.json"
        not_a_proposal.write_text(json.dumps(proposal_contract()), encoding="utf-8")
        without_contract = self.write_proposal(None)
        broken = self.base / "broken.json"
        broken.write_text("{not json", encoding="utf-8")

        for label, path, expected in (
            ("plain contract", not_a_proposal, "n’est pas une proposition"),
            ("null contract", without_contract, "n’est pas une proposition"),
            ("broken json", broken, "JSON invalide"),
            ("missing", self.base / "missing.json", "proposition absent"),
        ):
            with self.subTest(label=label):
                with self.assertRaisesRegex(ChangeError, expected) as context:
                    write_configuration(
                        repository=self.repository,
                        proposal_path=path,
                        contract_path=self.contract_path,
                        overwrite=False,
                        control_runner=runner,
                    )
                self.assertNotIsInstance(context.exception, ConfigurationError)

        self.assertFalse(self.contract_path.exists())
        self.assertEqual([], runner.validated_profiles)

    def test_write_rejects_an_edited_proposal_that_breaks_the_contract(self) -> None:
        contract = proposal_contract()
        contract["environment"].append("API_TOKEN")
        proposal = self.write_proposal(contract)
        runner = FakeRunner()

        with self.assertRaisesRegex(ConfigurationError, "ressemble à un secret"):
            write_configuration(
                repository=self.repository,
                proposal_path=proposal,
                contract_path=self.contract_path,
                overwrite=False,
                control_runner=runner,
            )

        self.assertFalse(self.contract_path.exists())

    def test_write_rejects_a_contract_path_outside_the_repository(self) -> None:
        proposal = self.write_proposal(proposal_contract())
        outside = self.base / "495.json"

        with self.assertRaisesRegex(ChangeError, "situé dans le dépôt"):
            write_configuration(
                repository=self.repository,
                proposal_path=proposal,
                contract_path=outside,
                overwrite=False,
                control_runner=FakeRunner(),
            )

        self.assertFalse(outside.exists())

    def test_load_proposal_extracts_the_contract(self) -> None:
        contract = proposal_contract()
        proposal = self.write_proposal(contract)

        self.assertEqual(contract, load_proposal(proposal))


def proposal_contract() -> dict[str, Any]:
    return {
        "checks": [
            {
                "command": ["sh", "scripts/check.sh"],
                "filesystem": "read-only",
                "name": "check",
                "timeout_seconds": 60,
            }
        ],
        "environment": ["PATH"],
        "version": 1,
    }


if __name__ == "__main__":
    unittest.main()
