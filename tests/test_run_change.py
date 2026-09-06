from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"

from harness495 import change as run_change
from harness495.cli import error_result, exit_code_for
from harness495.composition import run_codex_change
from harness495.contract import validate_contract
from harness495.errors import ChangeError
from harness495.serialization import result_bytes


FAKE_CODEX = r"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path


def option(name):
    return sys.argv[sys.argv.index(name) + 1]


# Le mode et le journal viennent de l’environnement lorsque le contrat le
# transmet, sinon de fichiers voisins de l’exécutable : une opération qui ne
# transmet que PATH reste pilotable par les tests.
HERE = Path(sys.argv[0]).resolve().parent
MODE_FILE = HERE / "fake-codex-mode"
MODE = os.environ.get("FAKE_CODEX_MODE") or (
    MODE_FILE.read_text(encoding="utf-8").strip() if MODE_FILE.exists() else "success"
)
LOG = os.environ.get("FAKE_CODEX_LOG") or str(HERE / "fake-codex-invocations.log")
with open(LOG, "a", encoding="utf-8") as log:
    log.write(json.dumps(sys.argv[1:]) + "\n")

if sys.argv[1:] == ["--version"]:
    print("codex-cli test")
    raise SystemExit(0)

if sys.argv[1:] == ["login", "status"]:
    if MODE == "unauthenticated":
        print("Not logged in", file=sys.stderr)
        raise SystemExit(1)
    print("Logged in using test credentials")
    raise SystemExit(0)

def proposal(repository, mode):
    # Propose un contrôle seulement lorsque le dépôt contient scripts/check.sh.
    checks = []
    questions = []
    if (repository / "scripts" / "check.sh").exists():
        checks.append({
            "name": "check",
            "command": ["sh", "scripts/check.sh"],
            "timeout_seconds": 60 if mode == "attested_timeout" else None,
            "filesystem": "read-only",
            "evidence": "scripts/check.sh est le script de contrôle du dépôt",
        })
    else:
        questions.append("Aucun script de contrôle trouvé ; quelle commande lance les tests ?")
    if mode == "duplicate_check":
        checks.append(dict(checks[0]))
    if mode == "unknown_executable":
        checks[0]["command"] = ["tool-495-absent", "check"]
    if mode == "modifies_repository":
        (repository / "proposal-note.txt").write_text("written\n", encoding="utf-8")
    response = {
        "status": "completed",
        "summary": "proposal from observed files",
        "checks": checks,
        "environment": ["PATH", "API_TOKEN"] if mode == "secret_environment" else ["PATH"],
        "questions": questions,
        "limitations": ["only scripts/ was inspected"],
    }
    if mode == "invalid_response":
        response.pop("checks")
    if mode == "blocked":
        response["status"] = "blocked"
        response["questions"] = ["Need a decision"]
    return response


def intervention(repository, mode, request):
    if "Demande :" not in request:
        print("request missing", file=sys.stderr)
        raise SystemExit(8)
    if mode != "no_candidate":
        (repository / "result.txt").write_text("candidate\n", encoding="utf-8")
    response = {
        "status": "completed",
        "summary": "candidate created",
        "questions": [],
        "limitations": [],
    }
    if mode == "invalid_response":
        response.pop("questions")
    if mode == "blocked":
        response["status"] = "blocked"
        response["questions"] = ["Need a decision"]
    return response


if sys.argv[1] == "exec":
    mode = MODE
    repository = Path(option("-C"))
    response_path = Path(option("--output-last-message"))
    schema = json.loads(Path(option("--output-schema")).read_text(encoding="utf-8"))
    request = sys.stdin.read()
    if mode == "timeout":
        time.sleep(5)
    if option("--sandbox") == "read-only":
        if "evidence" not in json.dumps(schema) or "Demande :" in request:
            print("proposal schema or prompt missing", file=sys.stderr)
            raise SystemExit(8)
        response = proposal(repository, mode)
    else:
        if "checks" in schema["properties"]:
            print("unexpected proposal schema", file=sys.stderr)
            raise SystemExit(8)
        response = intervention(repository, mode, request)
    response_path.write_text(json.dumps(response), encoding="utf-8")
    if mode == "malformed_events":
        print("not json")
        raise SystemExit(0)
    print(json.dumps({"type": "thread.started", "thread_id": "test"}))
    print(json.dumps({
        "type": "item.completed",
        "item": {"type": "command_execution", "exit_code": 0},
    }))
    print(json.dumps({
        "type": "turn.completed",
        "usage": {"input_tokens": 10, "output_tokens": 4},
    }))
    if mode == "agent_failure":
        print("client failed", file=sys.stderr)
        raise SystemExit(9)
    raise SystemExit(0)

if sys.argv[1] == "sandbox":
    if MODE == "sandbox_unavailable":
        print("sandbox unavailable", file=sys.stderr)
        raise SystemExit(125)
    separator = sys.argv.index("--")
    repository = Path(option("-C"))
    completed = subprocess.run(sys.argv[separator + 1 :], cwd=repository)
    raise SystemExit(completed.returncode)

print("unexpected fake invocation", file=sys.stderr)
raise SystemExit(64)
"""


class ChangeRunnerTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.repository = self.base / "application"
        self.repository.mkdir()
        self.codex_home = self.base / "codex-home"
        self.codex_home.mkdir()
        self.fake_codex = self.base / "codex"
        self.fake_codex.write_text(
            f"#!{sys.executable}\n" + textwrap.dedent(FAKE_CODEX),
            encoding="utf-8",
        )
        self.fake_codex.chmod(0o755)

        self.contract = {
            "version": 1,
            "environment": ["FAKE_CODEX_MODE", "PATH"],
            "checks": [
                {
                    "name": "tests",
                    "command": [sys.executable, "-c", "print('control passed')"],
                    "timeout_seconds": 3,
                    "filesystem": "read-only",
                }
            ],
        }
        self.contract_path = self.repository / "495.json"
        (self.repository / "README.md").write_text("fixture\n", encoding="utf-8")
        self.write_contract()
        self.git("init", "-b", "main")
        self.git("add", "README.md", "495.json")
        self.git(
            "-c",
            "user.name=495 tests",
            "-c",
            "user.email=tests@localhost",
            "commit",
            "-m",
            "test: initialize fixture",
        )

    def git(self, *arguments: str) -> str:
        return subprocess.run(
            ["git", *arguments],
            cwd=self.repository,
            check=True,
            capture_output=True,
            text=True,
        ).stdout

    def write_contract(self) -> None:
        self.contract_path.write_text(json.dumps(self.contract), encoding="utf-8")

    def run_scenario(self, mode: str = "success", *, agent_timeout: int = 3):
        with mock.patch.dict(os.environ, {"FAKE_CODEX_MODE": mode}):
            result = run_codex_change(
                repository=self.repository,
                contract_path=self.contract_path,
                request="Create the result file.",
                codex_home=self.codex_home,
                agent_timeout_seconds=agent_timeout,
                executable=self.fake_codex,
            )
        return result, exit_code_for(result)

    def update_committed_contract(self) -> None:
        self.write_contract()
        self.git("add", "495.json")
        self.git(
            "-c",
            "user.name=495 tests",
            "-c",
            "user.email=tests@localhost",
            "commit",
            "-m",
            "test: update fixture",
        )

    def test_valid_candidate_and_control_are_verified(self) -> None:
        result, exit_code = self.run_scenario()

        self.assertEqual(0, exit_code)
        self.assertEqual("candidate_verified", result["outcome"])
        self.assertEqual("change", result["command"])
        self.assertEqual("HEAD", result["reference"])
        self.assertEqual(result["baseline"], result["head"])
        self.assertEqual([], result["limitations"])
        self.assertEqual(["result.txt"], [item["path"] for item in result["candidate"]["files"]])
        self.assertEqual("PASS", result["checks"][0]["status"])
        self.assertTrue(result["contract_digest"].startswith("sha256:"))
        self.assertEqual(1, result["agent"]["events"]["command_count"])
        self.assertEqual(
            {"input_tokens": 10, "output_tokens": 4},
            result["agent"]["events"]["usage"],
        )
        command = result["agent"]["command"]
        include_only = command[command.index("shell_environment_policy.inherit=all") + 2]
        self.assertIn("FAKE_CODEX_MODE", include_only)
        self.assertNotIn("CODEX_HOME", include_only)
        self.assertNotIn(str(self.codex_home), json.dumps(result))

    def test_invalid_agent_response_is_distinct_from_control_failure(self) -> None:
        result, exit_code = self.run_scenario("invalid_response")

        self.assertEqual(3, exit_code)
        self.assertEqual("agent_failed", result["outcome"])
        self.assertIn("non conforme", result["agent"]["response_error"])
        self.assertEqual([], result["checks"])
        self.assertIsNotNone(result["candidate"])

    def test_absence_of_candidate_is_an_agent_failure(self) -> None:
        result, exit_code = self.run_scenario("no_candidate")

        self.assertEqual(3, exit_code)
        self.assertEqual("agent_failed", result["outcome"])
        self.assertIn("aucun candidat observé", result["violations"])
        self.assertEqual([], result["checks"])

    def test_nonzero_agent_keeps_partial_candidate_without_controls(self) -> None:
        result, exit_code = self.run_scenario("agent_failure")

        self.assertEqual(3, exit_code)
        self.assertEqual(9, result["agent"]["exit_code"])
        self.assertIsNotNone(result["candidate"])
        self.assertEqual([], result["checks"])

    def test_blocked_agent_does_not_run_controls(self) -> None:
        result, exit_code = self.run_scenario("blocked")

        self.assertEqual(3, exit_code)
        self.assertIn("agent bloqué", result["violations"])
        self.assertEqual([], result["checks"])

    def test_malformed_event_stream_is_an_agent_failure(self) -> None:
        result, exit_code = self.run_scenario("malformed_events")

        self.assertEqual(3, exit_code)
        self.assertIn("JSONL invalide", result["agent"]["events_error"])
        self.assertTrue(
            any("flux d’événements" in violation for violation in result["violations"])
        )

    def test_agent_timeout_kills_the_invocation(self) -> None:
        result, exit_code = self.run_scenario("timeout", agent_timeout=1)

        self.assertEqual(3, exit_code)
        self.assertTrue(result["agent"]["timed_out"])
        self.assertIsNone(result["agent"]["exit_code"])
        self.assertIsNone(result["candidate"])

    def test_failed_control_keeps_diagnostics(self) -> None:
        self.contract["checks"][0]["command"] = [
            sys.executable,
            "-c",
            "import sys; print('bad candidate', file=sys.stderr); raise SystemExit(7)",
        ]
        self.update_committed_contract()

        result, exit_code = self.run_scenario()

        self.assertEqual(1, exit_code)
        self.assertEqual("candidate_failed", result["outcome"])
        self.assertEqual(7, result["checks"][0]["exit_code"])
        self.assertEqual("bad candidate\n", result["checks"][0]["stderr"])

    def test_control_timeout_is_not_a_verified_candidate(self) -> None:
        self.contract["checks"][0]["command"] = [
            sys.executable,
            "-c",
            "import time; time.sleep(5)",
        ]
        self.contract["checks"][0]["timeout_seconds"] = 1
        self.update_committed_contract()

        result, exit_code = self.run_scenario()

        self.assertEqual(1, exit_code)
        self.assertTrue(result["checks"][0]["timed_out"])
        self.assertIsNone(result["checks"][0]["exit_code"])

    def test_control_that_changes_git_state_is_reported(self) -> None:
        self.contract["checks"][0]["command"] = [
            sys.executable,
            "-c",
            "from pathlib import Path; Path('control-output.txt').write_text('changed')",
        ]
        self.contract["checks"][0]["filesystem"] = "workspace-write"
        self.update_committed_contract()

        result, exit_code = self.run_scenario()

        self.assertEqual(1, exit_code)
        self.assertEqual("candidate_failed", result["outcome"])
        self.assertIn("a modifié l’état Git visible", result["violations"][0])
        self.assertIsNotNone(result["candidate_after_checks"])

    def test_dirty_repository_is_rejected_before_agent(self) -> None:
        (self.repository / "local.txt").write_text("dirty\n", encoding="utf-8")

        with self.assertRaisesRegex(ChangeError, "doit être propre"):
            self.run_scenario()

    def test_contract_rejects_ambient_home_variables(self) -> None:
        contract = copy.deepcopy(self.contract)
        contract["environment"].append("HOME")

        with self.assertRaisesRegex(ChangeError, "défini par 495"):
            validate_contract(contract)

    def test_contract_rejects_secret_environment_variables(self) -> None:
        contract = copy.deepcopy(self.contract)
        contract["environment"].append("SERVICE_TOKEN")

        with self.assertRaisesRegex(ChangeError, "ressemble à un secret"):
            validate_contract(contract)

    def test_contract_rejects_environment_patterns(self) -> None:
        contract = copy.deepcopy(self.contract)
        contract["environment"].append("PREFIX_*")

        with self.assertRaisesRegex(ChangeError, "nom invalide"):
            validate_contract(contract)

    def test_missing_authentication_is_rejected_before_agent(self) -> None:
        with self.assertRaisesRegex(ChangeError, "Not logged in"):
            self.run_scenario("unauthenticated")

        self.assertEqual("", self.git("status", "--short"))

    def test_missing_control_sandbox_is_rejected_before_agent(self) -> None:
        with self.assertRaisesRegex(ChangeError, "sandbox read-only indisponible"):
            self.run_scenario("sandbox_unavailable")

        self.assertEqual("", self.git("status", "--short"))

    def test_codex_home_with_user_skills_is_rejected(self) -> None:
        (self.codex_home / "skills" / "personal").mkdir(parents=True)

        with self.assertRaisesRegex(ChangeError, "skills utilisateur"):
            self.run_scenario()

    def test_cli_prints_one_json_result(self) -> None:
        request_path = self.base / "request.md"
        request_path.write_text("Create the result file.\n", encoding="utf-8")
        environment = os.environ.copy()
        environment["PATH"] = f"{self.base}{os.pathsep}{environment['PATH']}"
        environment["FAKE_CODEX_MODE"] = "success"

        completed = subprocess.run(
            [
                str(Path(sys.executable).parent / "495"),
                "--repository",
                str(self.repository),
                "--contract",
                str(self.contract_path),
                "--codex-home",
                str(self.codex_home),
                "--request-file",
                str(request_path),
            ],
            cwd=TOOLS.parent,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(0, completed.returncode, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual("candidate_verified", result["outcome"])
        self.assertEqual("", completed.stderr)

    def test_compatibility_script_exposes_the_cli(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(TOOLS / "run_change.py"), "--help"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertIn("--repository", completed.stdout)

    def test_application_case_uses_injected_agent_and_controls(self) -> None:
        def invoke(**arguments):
            (arguments["repository"] / "result.txt").write_text(
                "candidate\n", encoding="utf-8"
            )
            return {
                "client": "other-client",
                "events_error": None,
                "exit_code": 0,
                "response": {
                    "status": "completed",
                    "summary": "candidate created",
                    "questions": [],
                    "limitations": [],
                },
                "response_error": None,
                "timed_out": False,
            }

        agent = mock.Mock()
        agent.version.return_value = "other-client 1"
        agent.invoke.side_effect = invoke
        controls = mock.Mock()
        controls.run.return_value = {"name": "tests", "status": "PASS"}

        result = run_change.run_change(
            repository=self.repository,
            contract_path=self.contract_path,
            request="Create the result file.",
            agent_timeout_seconds=3,
            agent_client=agent,
            control_runner=controls,
            client_environment={"CLIENT_HOME": str(self.base / "client-home")},
        )

        self.assertEqual(0, exit_code_for(result))
        self.assertEqual("candidate_verified", result["outcome"])
        self.assertEqual("other-client 1", result["client_version"])
        agent.validate_ready.assert_called_once()
        controls.validate_profiles.assert_called_once()
        controls.run.assert_called_once()

    def test_error_result_is_valid_json_output(self) -> None:
        result = error_result(ChangeError("precondition", "missing"), "change")
        encoded = result_bytes(result)

        self.assertEqual(result, json.loads(encoded))
        self.assertEqual("execution_impossible", result["outcome"])
        self.assertEqual("change", result["command"])


if __name__ == "__main__":
    unittest.main()
