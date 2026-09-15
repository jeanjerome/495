"""Dependencies between the packages of harness495 point one way.

The rules are import-linter contracts in ``pyproject.toml`` (``[tool.importlinter]``); this test
runs them under pytest so that the suite alone enforces them. import-linter reports each broken
contract with the import chain that breaks it. A contract between the code and its configuration,
not a behaviour: no scenario, but the Given/When/Then shape (``docs/decisions/0013``). Rationale:
docs/decisions/0011-package-boundaries.md.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from importlinter.cli import lint_imports

PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"

CONTRACTS = 5
"""How many contracts ``pyproject.toml`` declares: a contract dropped from the configuration
would otherwise leave the run green with one rule fewer."""


def test_given_the_declared_contracts_when_they_are_run_then_every_one_holds(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given the contracts declared in pyproject.toml
    monkeypatch.chdir(PYPROJECT.parent)
    # When import-linter runs them over the package
    exit_code = lint_imports(config_filename=str(PYPROJECT), no_cache=True, no_logo=True)
    report = capsys.readouterr().out
    # Then every one of them is kept, and none has gone missing
    assert exit_code == 0, report
    assert f"Contracts: {CONTRACTS} kept, 0 broken" in report, report
