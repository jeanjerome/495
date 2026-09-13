"""Dependencies between the packages of harness495 point one way.

The rules are import-linter contracts in ``pyproject.toml`` (``[tool.importlinter]``); this test
runs them under pytest so that the suite alone enforces them. import-linter reports each broken
contract with the import chain that breaks it. Rationale: docs/decisions/0011-package-boundaries.md.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from importlinter.cli import lint_imports

PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


def test_the_import_contracts_hold(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(PYPROJECT.parent)
    exit_code = lint_imports(config_filename=str(PYPROJECT), no_cache=True, no_logo=True)
    report = capsys.readouterr().out
    assert exit_code == 0, report
    assert "Contracts: 4 kept, 0 broken" in report, report
