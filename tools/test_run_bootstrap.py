from __future__ import annotations

import copy
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path


TOOLS = Path(__file__).resolve().parent
REPOSITORY = TOOLS.parent
sys.path.insert(0, str(TOOLS))

import run_bootstrap  # noqa: E402


class BootstrapRunnerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = json.loads(
            (REPOSITORY / "bootstrap/contract.json").read_text(encoding="utf-8")
        )

    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        previous_root = run_bootstrap.ROOT
        run_bootstrap.ROOT = self.root
        self.addCleanup(setattr, run_bootstrap, "ROOT", previous_root)

        for path in (
            "bootstrap",
            "docs",
            "src/domain",
            "tests/unit",
            "tests/enumeration",
        ):
            (self.root / path).mkdir(parents=True, exist_ok=True)
        for path in (
            "src/domain/__init__.py",
            "tests/__init__.py",
            "tests/unit/__init__.py",
            "tests/enumeration/__init__.py",
        ):
            (self.root / path).write_text("", encoding="utf-8")

        self.contract_path = self.root / "bootstrap/contract.json"
        self.contract_raw = run_bootstrap.canonical_bytes(self.contract)
        self.contract_path.write_bytes(self.contract_raw)
        self.contract_digest = run_bootstrap.sha256_bytes(self.contract_raw)

    def authorize(self) -> None:
        (self.root / "docs/implementation.md").write_text(
            "AUTORISÉ — contrat "
            f"{self.contract_digest} — test-local — 2026-09-06\n",
            encoding="utf-8",
        )

    def add_passing_tests(self) -> None:
        (self.root / "tests/unit/test_smoke.py").write_text(
            "import unittest\n\n"
            "class SmokeTest(unittest.TestCase):\n"
            "    def test_true(self):\n"
            "        self.assertTrue(True)\n",
            encoding="utf-8",
        )
        (self.root / "tests/enumeration/test_domain.py").write_text(
            "import sys\n"
            "import unittest\n\n"
            "class DomainTest(unittest.TestCase):\n"
            "    def test_domain(self):\n"
            "        print('COVERAGE sample 1/1', file=sys.stderr)\n"
            "        self.assertEqual(1, 1)\n",
            encoding="utf-8",
        )

    def run_silently(self) -> int:
        with contextlib.redirect_stdout(io.StringIO()):
            with contextlib.redirect_stderr(io.StringIO()):
                return run_bootstrap.run_command(self.contract_path)

    def test_run_requires_exact_contract_authorization(self) -> None:
        self.assertEqual(2, self.run_silently())
        self.assertFalse((self.root / "bootstrap/runs").exists())

    def test_passing_checks_generate_progress_report(self) -> None:
        self.authorize()
        self.add_passing_tests()

        self.assertEqual(0, self.run_silently())

        reports = list((self.root / "bootstrap/runs").glob("*.json"))
        self.assertEqual(1, len(reports))
        report = json.loads(reports[0].read_text(encoding="utf-8"))
        self.assertEqual("PASS", report["status"])
        self.assertEqual("progress", report["qualification"])
        self.assertFalse(report["acceptance_eligible"])
        self.assertEqual([1, 1], [item["test_count"] for item in report["checks"]])
        self.assertEqual(
            [{"covered": 1, "declared": 1, "domain": "sample"}],
            report["checks"][1]["coverage"],
        )

    def test_candidate_scope_rejects_unmatched_file(self) -> None:
        (self.root / "tests/unexpected.txt").write_text(
            "hors périmètre", encoding="utf-8"
        )

        _, violations = run_bootstrap.candidate_manifest(self.contract)

        self.assertIn(
            "fichier candidat hors périmètre : tests/unexpected.txt",
            violations,
        )

    def test_qualified_security_requires_a_mechanism(self) -> None:
        contract = copy.deepcopy(self.contract)
        contract["security"]["network_restriction"] = {
            "mechanism": "none",
            "qualified": True,
        }

        with self.assertRaises(run_bootstrap.ContractError):
            run_bootstrap.validate_contract(contract)


if __name__ == "__main__":
    unittest.main()
