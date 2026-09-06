from __future__ import annotations

import contextlib
import copy
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

import run_bootstrap  # noqa: E402


class BootstrapRunnerTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        previous_root = run_bootstrap.ROOT
        run_bootstrap.ROOT = self.root
        self.addCleanup(setattr, run_bootstrap, "ROOT", previous_root)

        (self.root / "bootstrap").mkdir()
        (self.root / "tools").mkdir()
        (self.root / "tools/check.py").write_text("value = 1\n", encoding="utf-8")
        self.contract = {
            "checks": [
                {
                    "command": ["{python}", "-c", "raise SystemExit(0)"],
                    "name": "tests",
                    "timeout_seconds": 5,
                }
            ],
            "files": ["bootstrap/contract.json", "tools/*.py"],
            "report_directory": ".495/runs",
            "version": 1,
        }
        self.contract_path = self.root / "bootstrap/contract.json"
        self.write_contract()

    def write_contract(self) -> None:
        self.contract_path.write_bytes(run_bootstrap.canonical_bytes(self.contract))

    def run_silently(self, *, save_report: bool = False) -> int:
        with contextlib.redirect_stdout(io.StringIO()):
            with contextlib.redirect_stderr(io.StringIO()):
                return run_bootstrap.run_command(
                    self.contract_path, save_report=save_report
                )

    def test_contract_has_a_canonical_digest(self) -> None:
        compact = json.dumps(self.contract, ensure_ascii=False).encode("utf-8")
        self.contract_path.write_bytes(compact)

        loaded, raw = run_bootstrap.load_contract(self.contract_path)

        self.assertEqual(self.contract, loaded)
        self.assertEqual(run_bootstrap.canonical_bytes(self.contract), raw)

    def test_unknown_contract_field_is_rejected(self) -> None:
        self.contract["security"] = {"network": "disabled"}

        with self.assertRaises(run_bootstrap.ContractError):
            run_bootstrap.validate_contract(self.contract)

    def test_each_file_pattern_must_match(self) -> None:
        self.contract["files"].append("missing/*.py")

        with self.assertRaises(run_bootstrap.ContractError):
            run_bootstrap.candidate_manifest(self.contract)

    def test_success_does_not_create_a_report_by_default(self) -> None:
        self.assertEqual(0, self.run_silently())
        self.assertFalse((self.root / ".495").exists())

    def test_report_is_created_only_when_requested(self) -> None:
        self.assertEqual(0, self.run_silently(save_report=True))

        reports = list((self.root / ".495/runs").glob("*.json"))
        self.assertEqual(1, len(reports))
        report = json.loads(reports[0].read_text(encoding="utf-8"))
        self.assertEqual("PASS", report["status"])
        self.assertEqual(1, report["version"])
        self.assertEqual([], report["violations"])

    def test_failed_command_keeps_its_output(self) -> None:
        self.contract["checks"][0]["command"] = [
            "{python}",
            "-c",
            "import sys; print('sortie'); print('erreur', file=sys.stderr); sys.exit(3)",
        ]
        self.write_contract()

        self.assertEqual(1, self.run_silently(save_report=True))

        report_path = next((self.root / ".495/runs").glob("*.json"))
        result = json.loads(report_path.read_text(encoding="utf-8"))["checks"][0]
        self.assertEqual("FAIL", result["status"])
        self.assertEqual(3, result["exit_code"])
        self.assertEqual("sortie\n", result["stdout"])
        self.assertEqual("erreur\n", result["stderr"])

    def test_commands_inherit_the_current_environment(self) -> None:
        self.contract["checks"][0]["command"] = [
            "{python}",
            "-c",
            "import os; raise SystemExit(os.environ.get('RUNNER_TEST') != 'visible')",
        ]
        self.write_contract()

        with mock.patch.dict(os.environ, {"RUNNER_TEST": "visible"}):
            self.assertEqual(0, self.run_silently())

    def test_python_token_keeps_the_active_environment(self) -> None:
        with mock.patch.object(run_bootstrap.sys, "executable", "/tmp/venv/bin/python"):
            command = run_bootstrap.command_arguments(self.contract["checks"][0])

        self.assertEqual("/tmp/venv/bin/python", command[0])

    def test_candidate_change_makes_the_result_fail(self) -> None:
        self.contract["checks"][0]["command"] = [
            "{python}",
            "-c",
            "from pathlib import Path; Path('tools/generated.py').write_text('x')",
        ]
        self.write_contract()

        self.assertEqual(1, self.run_silently())

    def test_duplicate_check_names_are_rejected(self) -> None:
        self.contract["checks"].append(copy.deepcopy(self.contract["checks"][0]))

        with self.assertRaises(run_bootstrap.ContractError):
            run_bootstrap.validate_contract(self.contract)


if __name__ == "__main__":
    unittest.main()
